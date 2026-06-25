"""Run the issue #179 packaged-path evidence flow against a Docker workbench."""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.sse import sse_client


CAD_CODE = """\
from build123d import *

PLATE_LENGTH = 100
PLATE_WIDTH = 60
PLATE_THICKNESS = 8
HOLE_RADIUS = 3.3
RIB_LENGTH = 70
RIB_THICKNESS = 6
RIB_HEIGHT = 22

with BuildPart() as bp:
    Box(PLATE_LENGTH, PLATE_WIDTH, PLATE_THICKNESS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((-38, -20, 0), (-38, 20, 0), (38, -20, 0), (38, 20, 0)):
        Hole(HOLE_RADIUS, depth=PLATE_THICKNESS)

base_plate = bp.part
base_plate.label = "base_plate"
base_plate.color = Color(0.45, 0.58, 0.70)

rib = Box(
    RIB_LENGTH,
    RIB_THICKNESS,
    RIB_HEIGHT,
    align=(Align.CENTER, Align.CENTER, Align.MIN),
).moved(Location((0, 0, PLATE_THICKNESS)))
rib.label = "rib_main"
rib.color = Color(0.75, 0.42, 0.20)

result = Compound(children=[base_plate, rib])
"""

MANAGED_PROBE_CODE = """\
from build123d import *

PROBE_SIZE = 1
probe_cube = Box(PROBE_SIZE, PROBE_SIZE, PROBE_SIZE)
probe_cube.label = "probe_cube"
probe_cube.color = Color(0.45, 0.58, 0.70)
result = Compound(children=[probe_cube])
"""


def _result_text(result: Any) -> str:
    return "\n".join(getattr(block, "text", "") for block in result.content)


def _result_json(result: Any) -> dict[str, Any]:
    return json.loads(_result_text(result))


def _assert_http_url(url: str) -> str:
    scheme = urlparse(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {scheme or '(missing)'}")
    return url


def _get_json(url: str) -> dict[str, Any]:
    http_url = _assert_http_url(url)
    with urllib.request.urlopen(http_url, timeout=15) as response:  # noqa: S310
        return json.load(response)


def _get_size(url: str) -> tuple[int, int]:
    http_url = _assert_http_url(url)
    with urllib.request.urlopen(http_url, timeout=15) as response:  # noqa: S310
        return response.status, len(response.read())


async def _managed_cad_mutation(mcp_url: str) -> dict[str, Any]:
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("aieng_agent_readme", {})
            await session.call_tool("aieng_list_projects", {})
            created = _result_json(
                await session.call_tool(
                    "aieng_create_project",
                    {"name": "Issue 179 managed approval probe"},
                )
            )
            await session.call_tool(
                "aieng_agent_context", {"project_id": str(created["id"])}
            )
            await session.call_tool("aieng_guide", {"topic": "cad"})
            result = _result_json(
                await session.call_tool(
                    "cad_execute_build123d",
                    {
                        "project_id": str(created["id"]),
                        "name": "Approval fail-safe probe",
                        "code": MANAGED_PROBE_CODE,
                        "thumbnail": False,
                    },
                )
            )
            if result.get("status") == "ok":
                return {
                    "status": "ok",
                    "project_id": result.get("project_id"),
                    "geometry_report_summary": result.get("geometry_report_summary"),
                }
            if result.get("code") == "approval_surface_unavailable":
                return {
                    "status": "error",
                    "code": result.get("code"),
                    "message": result.get("message"),
                    "recoverable": result.get("recoverable"),
                }
            raise RuntimeError(
                f"managed CAD mutation had an unexpected result: {result}"
            )


def _face_pointer(context: dict[str, Any]) -> str | None:
    pointers = _face_pointers(context)
    return pointers[0] if pointers else None


def _face_pointers(context: dict[str, Any]) -> list[str]:
    digest = (context.get("brep_graph") or {}).get("digest", "")
    pointers: list[str] = []
    for line in digest.splitlines():
        if line.startswith("- @face:"):
            parts = line.split()
            if len(parts) > 1:
                pointers.append(parts[1])
    return pointers


def _face_id(pointer: str) -> str:
    if not pointer.startswith("@face:"):
        raise ValueError(f"expected @face pointer, got: {pointer}")
    return pointer[len("@face:"):]


def _pointer_in_context(context: dict[str, Any], pointer: str) -> bool:
    digest = (context.get("brep_graph") or {}).get("digest", "")
    return any(line.startswith(f"- {pointer} ") for line in digest.splitlines())


def _m1_cae_setup_patches(load_pointer: str, fixed_pointer: str) -> list[dict[str, Any]]:
    """Canonical M1 linear-static setup patches for a 500N aluminium bracket smoke."""
    load_face = _face_id(load_pointer)
    fixed_face = _face_id(fixed_pointer)
    return [
        {
            "action_type": "create_file",
            "path": "simulation/solver_settings.json",
            "content": {"solver": "CalculiX", "analysis_type": "linear_static"},
        },
        {
            "action_type": "create_file",
            "path": "simulation/cae_imports/parsed_materials.json",
            "content": {
                "materials": [
                    {
                        "name": "Al6061-T6",
                        "youngs_modulus_pa": 69e9,
                        "poisson_ratio": 0.33,
                        "density_kg_m3": 2700,
                        "yield_strength_pa": 276e6,
                    }
                ]
            },
        },
        {
            "action_type": "create_file",
            "path": "simulation/setup.yaml",
            "content": {
                "schema_version": "0.1",
                "ai_generated": True,
                "analysis_type": "static_structural",
                "material_name": "Al6061-T6",
                "boundary_conditions": [
                    {
                        "id": "bc_fixed_base",
                        "type": "fixed",
                        "target_feature": "fixed_base",
                        "reason": "M1 dogfood fixed support face",
                    }
                ],
                "loads": [
                    {
                        "id": "load_500n",
                        "type": "force",
                        "target_feature": "load_top",
                        "value_n": 500.0,
                        "direction": [0.0, 0.0, -1.0],
                        "reason": "M1 dogfood 500N downward load",
                    }
                ],
                "mesh": {"target_size_mm": 8.0},
                "assumptions": [
                    "Face selections are dogfood smoke targets, not certified engineering setup.",
                ],
            },
        },
        {
            "action_type": "create_file",
            "path": "simulation/cae_mapping.json",
            "content": {
                "schema_version": "0.1",
                "ai_generated": True,
                "mappings": [
                    {
                        "cae_entity": "FIXED_BASE",
                        "maps_to": {
                            "feature_id": "fixed_base",
                            "role": "fixed_support",
                            "target_pointers": [fixed_pointer],
                        },
                        "face_ids": [fixed_face],
                    },
                    {
                        "cae_entity": "LOAD_TOP",
                        "maps_to": {
                            "feature_id": "load_top",
                            "role": "load_application",
                            "target_pointers": [load_pointer],
                        },
                        "face_ids": [load_face],
                    },
                ],
            },
        },
    ]


async def _client_managed_flow(
    mcp_url: str,
    backend_url: str,
    viewer_face_pointer: str | None,
    *,
    run_solver: bool = False,
) -> dict[str, Any]:
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            prompts = await session.list_prompts()
            resources = await session.list_resources()
            onboarding = await session.get_prompt("aieng_mcp_first_onboarding")
            discipline = await session.read_resource(
                "aieng://guides/mcp-first-discipline"
            )

            readme = _result_json(await session.call_tool("aieng_agent_readme", {}))
            projects_before = _result_json(
                await session.call_tool("aieng_list_projects", {})
            )
            await session.call_tool("aieng_guide", {"topic": "cad"})
            await session.call_tool("aieng_guide", {"topic": "cae"})
            created = _result_json(
                await session.call_tool(
                    "aieng_create_project",
                    {"name": "Issue 179 packaged dogfood bracket"},
                )
            )
            project_id = str(created["id"])
            await session.call_tool("aieng_agent_context", {"project_id": project_id})

            await session.call_tool(
                "cad_confirm_modeling_plan",
                {
                    "project_id": project_id,
                    "summary": "Build the issue #179 packaged dogfood bracket.",
                    "steps": [
                        "Create a named base plate with four clearance holes.",
                        "Add a named stiffening rib.",
                        "Review geometry and run CAE preflight.",
                    ],
                    "scope": "Issue #179 packaged dogfood evidence",
                    "assumptions": ["Dimensions are illustrative millimeters."],
                },
            )
            cad = _result_json(
                await session.call_tool(
                    "cad_execute_build123d",
                    {
                        "project_id": project_id,
                        "name": "Issue 179 packaged dogfood bracket",
                        "code": CAD_CODE,
                        "mode": "replace",
                        "model_kind": "mechanical",
                        "response_detail": "compact",
                        "thumbnail": False,
                        "timeout": 90,
                    },
                )
            )
            if cad.get("status") != "ok":
                raise RuntimeError(f"CAD build failed: {cad}")

            context = _result_json(
                await session.call_tool(
                    "aieng_agent_context", {"project_id": project_id}
                )
            )
            discovered_face_pointer = _face_pointer(context)
            if not discovered_face_pointer:
                raise RuntimeError("agent context did not expose a face pointer")
            discovered_face_pointers = _face_pointers(context)
            if viewer_face_pointer and not _pointer_in_context(
                context, viewer_face_pointer
            ):
                raise RuntimeError(
                    f"viewer face pointer does not exist in the new project: {viewer_face_pointer}"
                )
            handoff_face_pointer = viewer_face_pointer or discovered_face_pointer
            fixed_face_pointer = next(
                (p for p in discovered_face_pointers if p != handoff_face_pointer),
                discovered_face_pointer,
            )
            cae_setup = _result_json(
                await session.call_tool(
                    "cae_apply_setup_patch",
                    {
                        "project_id": project_id,
                        "patches": _m1_cae_setup_patches(
                            load_pointer=handoff_face_pointer,
                            fixed_pointer=fixed_face_pointer,
                        ),
                    },
                )
            )
            mesh = _result_json(
                await session.call_tool(
                    "cae_generate_mesh",
                    {"project_id": project_id, "mesh_size_mm": 8.0},
                )
            )
            preflight = _result_json(
                await session.call_tool(
                    "cae_prepare_solver_run",
                    {
                        "project_id": project_id,
                        "run_id": "run_001",
                        "load_case_id": "load_case_001",
                        "extract_results": True,
                        "refresh_summary": True,
                    },
                )
            )
            solver_input = _result_json(
                await session.call_tool(
                    "cae_generate_solver_input",
                    {"project_id": project_id, "run_id": "run_001", "overwrite": True},
                )
            )
            post_input_preflight = _result_json(
                await session.call_tool(
                    "cae_prepare_solver_run",
                    {
                        "project_id": project_id,
                        "run_id": "run_001",
                        "load_case_id": "load_case_001",
                        "extract_results": True,
                        "refresh_summary": True,
                    },
                )
            )
            solver_run = None
            extracted_results = None
            field_regions = None
            if run_solver:
                solver_run = _result_json(
                    await session.call_tool(
                        "cae_run_solver",
                        {"project_id": project_id, "run_id": "run_001"},
                    )
                )
                extracted_results = _result_json(
                    await session.call_tool(
                        "cae_extract_solver_results",
                        {"project_id": project_id, "run_id": "run_001"},
                    )
                )
                field_regions = _result_json(
                    await session.call_tool(
                        "cae_extract_field_regions",
                        {"project_id": project_id, "run_id": "run_001"},
                    )
                )

    summary = _get_json(f"{backend_url}/api/projects/{project_id}")
    project = summary.get("project") or summary
    web_asset = project.get("web_asset")
    if not web_asset:
        raise RuntimeError(f"project did not publish a viewer asset: {project}")
    asset_status, asset_bytes = _get_size(
        f"{backend_url}/assets/projects/{project_id}/{web_asset}"
    )

    return {
        "tool_count": len(tools.tools),
        "prompt_count": len(prompts.prompts),
        "resource_count": len(resources.resources),
        "onboarding_messages": len(onboarding.messages),
        "discipline_chunks": len(discipline.contents),
        "registry_hash": readme.get("registry", {}).get("registry_hash"),
        "project_count_before": len(projects_before.get("projects") or []),
        "project_id": project_id,
        "project_status": project.get("status"),
        "named_parts": project.get("named_parts"),
        "geometry_report_summary": context.get("cad", {}).get(
            "geometry_report_summary"
        ),
        "web_asset": web_asset,
        "web_asset_http_status": asset_status,
        "web_asset_bytes": asset_bytes,
        "discovered_face_pointer": discovered_face_pointer,
        "discovered_face_pointers": discovered_face_pointers,
        "viewer_face_pointer": viewer_face_pointer,
        "viewer_face_pointer_verified": bool(
            viewer_face_pointer and _pointer_in_context(context, viewer_face_pointer)
        ),
        "pointer_handed_back_to_agent": handoff_face_pointer,
        "fixed_face_pointer": fixed_face_pointer,
        "cae_setup_status": cae_setup.get("status"),
        "cae_setup_changed_artifacts": [
            item.get("path") for item in (cae_setup.get("changed_artifacts") or [])
        ],
        "cae_mesh_status": mesh.get("status"),
        "cae_mesh_node_count": mesh.get("node_count"),
        "cae_mesh_element_count": mesh.get("element_count"),
        "face_count": context.get("brep_graph", {}).get("face_count"),
        "cae_ready_to_run": preflight.get("ready_to_run"),
        "cae_missing_items": preflight.get("preflight", {}).get("missing_items"),
        "cae_recommended_next_calls": preflight.get("recommended_next_calls"),
        "cae_solver_input_status": solver_input.get("status"),
        "cae_solver_input_path": solver_input.get("out_path"),
        "cae_source_deck_synthesis": solver_input.get("source_deck_synthesis"),
        "cae_post_input_ready_to_run": post_input_preflight.get("ready_to_run"),
        "cae_post_input_missing_items": (post_input_preflight.get("preflight") or {}).get("missing_items"),
        "solver_run_requested": run_solver,
        "solver_run": solver_run,
        "extracted_results": extracted_results,
        "field_regions": field_regions,
        "honesty": {
            "solver_executed": bool(solver_run and solver_run.get("status") == "completed"),
            "solver_execution_is_opt_in": True,
            "engineering_certification_claimed": False,
        },
    }


async def _main_async(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "0.1",
        "image": args.image,
        "image_digest": args.image_digest,
    }
    if args.managed_mcp_url:
        result["managed_cad_mutation"] = await _managed_cad_mutation(
            args.managed_mcp_url
        )
    if args.client_mcp_url:
        result["client_managed_flow"] = await _client_managed_flow(
            args.client_mcp_url,
            args.backend_url,
            args.face_pointer,
            run_solver=args.run_solver,
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", default="ghcr.io/armpro24-blip/aieng-workbench:latest"
    )
    parser.add_argument("--image-digest")
    parser.add_argument("--managed-mcp-url")
    parser.add_argument("--client-mcp-url")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--face-pointer",
        help="Pointer copied from the full viewer and pasted back into the agent flow.",
    )
    parser.add_argument(
        "--run-solver",
        action="store_true",
        help="Opt in to approval-gated cae.run_solver plus result/field extraction.",
    )
    parser.add_argument("--output")
    args = parser.parse_args()

    result = asyncio.run(_main_async(args))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
