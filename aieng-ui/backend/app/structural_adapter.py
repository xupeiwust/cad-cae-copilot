"""Structural CAD/CAE adapter — Pilot B first slice: manifest + preflight.

This module is intentionally non-executing. It exposes a safe capability
manifest and a read-only environment preflight for the existing structural CAE
toolchain around Gmsh / CalculiX / FRD postprocessing.

It does NOT:
  - generate mesh;
  - run a solver;
  - parse FRD files during preflight;
  - mutate any project or package;
  - advance engineering claims.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import Settings
from .external_adapters import AdapterPreflightResult, ExternalToolCapability
from .project_io import get_project, resolve_project_path

ADAPTER_ID = "structural"
ADAPTER_LABEL = "Structural CAE"

_CLAIM_BOUNDARY_PREFLIGHT_NOTE = (
    "Structural adapter preflight is a read-only environment check. It does "
    "not execute meshing or solver tools, does not advance engineering claims, "
    "and does not certify any design. A qualified engineer must review the "
    "underlying evidence before accepting any simulation conclusion."
)

_SAFETY_NOTE = (
    "External mesh/solver tools are treated as untrusted execution backends. "
    "Mesh generation and solver execution require explicit approval. Missing "
    "Gmsh / CalculiX dependencies are reported honestly; success is "
    "never faked."
)

_SAFETY_NOTE_PREPARE = (
    "Structural run preflight is read-only. It checks whether the selected "
    "project appears ready for a solver run review, but it does not generate "
    "mesh, does not run CalculiX, does not parse FRD files, and does not "
    "mutate the .aieng package."
)

_STALE_ON_MESH_REGEN = [
    "simulation/runs/*",
    "results/computed_metrics.json",
    "results/result_summary.json",
    "results/field_summary.json",
    "reports/copilot_loop/*",
]

_STALE_ON_SOLVER_RERUN = [
    "results/computed_metrics.json",
    "results/result_summary.json",
    "results/field_summary.json",
    "reports/copilot_loop/*",
]


def structural_capabilities() -> list[ExternalToolCapability]:
    """Return the static structural adapter manifest."""
    return [
        ExternalToolCapability(
            id="structural.prepare_solver_run",
            label="Prepare structural solver run",
            category="solver",
            mutates_package=True,
            mutates_external_model=False,
            runs_external_process=False,
            expensive=False,
            requires_approval=True,
            input_artifacts=["simulation/solver_input.inp", "simulation/load_cases/*"],
            output_artifacts=["simulation/runs/run_001/solver_input.inp"],
            stale_artifacts_on_success=[
                "simulation/runs/*/outputs/*",
                "results/computed_metrics.json",
                "results/result_summary.json",
                "reports/copilot_loop/*",
            ],
            claim_advancement="none",
        ),
        ExternalToolCapability(
            id="structural.generate_mesh",
            label="Generate structural mesh",
            category="mesh",
            mutates_package=True,
            mutates_external_model=False,
            runs_external_process=True,
            expensive=True,
            requires_approval=True,
            input_artifacts=["cad/source.FCStd", "geometry/source.step"],
            output_artifacts=["mesh/structural.msh", "simulation/mesh/mesh_metadata.json"],
            stale_artifacts_on_success=list(_STALE_ON_MESH_REGEN),
            claim_advancement="none",
        ),
        ExternalToolCapability(
            id="structural.run_solver",
            label="Run structural solver",
            category="solver",
            mutates_package=True,
            mutates_external_model=False,
            runs_external_process=True,
            expensive=True,
            requires_approval=True,
            input_artifacts=["simulation/runs/*/solver_input.inp"],
            output_artifacts=[
                "simulation/runs/*/solver_run.json",
                "simulation/runs/*/outputs/result.frd",
                "results/computed_metrics.json",
            ],
            stale_artifacts_on_success=list(_STALE_ON_SOLVER_RERUN),
            claim_advancement="none",
        ),
        ExternalToolCapability(
            id="structural.extract_results",
            label="Extract structural solver results",
            category="postprocess",
            mutates_package=True,
            mutates_external_model=False,
            runs_external_process=False,
            expensive=False,
            requires_approval=True,
            input_artifacts=["simulation/runs/*/outputs/result.frd"],
            output_artifacts=["results/computed_metrics.json", "results/result_summary.json"],
            stale_artifacts_on_success=["results/result_summary.json", "reports/copilot_loop/*"],
            claim_advancement="none",
        ),
    ]


def _which_existing(*names: str) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            path = Path(found)
            if path.exists():
                return path
    return None


def _is_ci() -> bool:
    return os.environ.get("CI", "").lower() in {"1", "true", "yes"}


def preflight_structural_adapter(settings: Settings) -> dict[str, Any]:
    """Return a read-only readiness snapshot for the structural toolchain."""
    gmsh_cmd = _which_existing("gmsh", "gmsh.exe")
    ccx_cmd = _which_existing("ccx", "ccx_linux", "ccx2.21", "ccx_static", "ccx.exe")

    checked_paths = {
        "aieng_root": {"path": str(settings.aieng_root), "present": settings.aieng_root.exists()},
        "gmsh": {"path": str(gmsh_cmd) if gmsh_cmd else "gmsh", "present": gmsh_cmd is not None},
        "ccx": {"path": str(ccx_cmd) if ccx_cmd else "ccx", "present": ccx_cmd is not None},
    }

    missing_dependencies: list[str] = []
    warnings: list[str] = []

    if not checked_paths["aieng_root"]["present"]:
        missing_dependencies.append("aieng_root")
    if gmsh_cmd is None:
        missing_dependencies.append("gmsh")
        warnings.append("Gmsh executable was not found. Mesh generation is unavailable until Gmsh is installed.")
    if ccx_cmd is None:
        missing_dependencies.append("ccx")
        warnings.append("CalculiX executable (ccx) was not found. Solver execution is unavailable until ccx is installed.")
    if _is_ci():
        warnings.append("Running in CI: mesh/solver execution is intentionally not exercised here.")

    if not missing_dependencies:
        status = "ready"
        ok = True
    elif {"gmsh", "ccx"} <= set(missing_dependencies):
        status = "unavailable"
        ok = False
    else:
        status = "partial"
        ok = False

    preflight = AdapterPreflightResult(
        ok=ok,
        status=status,  # type: ignore[arg-type]
        missing_dependencies=missing_dependencies,
        warnings=warnings,
        errors=[],
        estimated_outputs=[
            "simulation/runs/run_001/solver_input.inp",
            "simulation/runs/run_001/outputs/result.frd",
            "results/computed_metrics.json",
        ] if status in {"ready", "partial"} else [],
        requires_approval=True,
    )

    environment = {
        "gmsh_cmd": str(gmsh_cmd) if gmsh_cmd else None,
        "ccx_cmd": str(ccx_cmd) if ccx_cmd else None,
        "aieng_root": str(settings.aieng_root),
        "is_ci": _is_ci(),
    }

    return {
        "schema_version": "0.1",
        "adapter_id": ADAPTER_ID,
        "adapter_label": ADAPTER_LABEL,
        "preflight": preflight.model_dump(),
        "capabilities": [cap.model_dump() for cap in structural_capabilities()],
        "environment": environment,
        "checked_paths": checked_paths,
        "safety_note": _SAFETY_NOTE,
        "claim_boundary": _CLAIM_BOUNDARY_PREFLIGHT_NOTE,
    }


def prepare_structural_run_preview(
    settings: Settings,
    project_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only structural solver-run readiness preview for one project.

    This is intentionally narrower than the environment preflight: it inspects
    a selected .aieng package for mesh / solver-settings / load-case / deck
    presence and reports whether a future approval-gated solver execution would
    be ready. It never runs a subprocess and never mutates the package.
    """

    body = payload or {}
    run_id = str(body.get("run_id") or body.get("runId") or "run_001")
    load_case_id = str(body.get("load_case_id") or body.get("loadCaseId") or "load_case_001")
    solver = str(body.get("solver") or "CalculiX")
    input_deck_path_str = body.get("input_deck_path") or body.get("inputDeckPath")
    extract_results = bool(body.get("extract_results", body.get("extractResults", True)))
    refresh_summary = bool(body.get("refresh_summary", body.get("refreshSummary", True)))

    try:
        project = get_project(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "ok": False,
                "tool": "structural.prepare_solver_run",
                "status": "error",
                "code": "project_not_found",
                "message": "Project not found.",
                "claim_advancement": "none",
                "claim_boundary": _CLAIM_BOUNDARY_PREFLIGHT_NOTE,
            }
        raise

    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        return {
            "ok": False,
            "tool": "structural.prepare_solver_run",
            "status": "error",
            "code": "package_not_found",
            "message": "Project has no .aieng package.",
            "claim_advancement": "none",
            "claim_boundary": _CLAIM_BOUNDARY_PREFLIGHT_NOTE,
        }

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
    except Exception as exc:
        return {
            "ok": False,
            "tool": "structural.prepare_solver_run",
            "status": "error",
            "code": "package_read_error",
            "message": f"Failed to read package: {exc}",
            "claim_advancement": "none",
            "claim_boundary": _CLAIM_BOUNDARY_PREFLIGHT_NOTE,
        }

    has_mesh = any(name.startswith("simulation/mesh/") for name in names)
    has_solver_settings = "simulation/solver_settings.json" in names
    has_load_case = f"simulation/load_cases/{load_case_id}.json" in names

    if input_deck_path_str:
        has_input_deck = Path(str(input_deck_path_str)).exists()
        input_deck_artifact = str(input_deck_path_str)
    else:
        input_deck_artifact = f"simulation/runs/{run_id}/solver_input.inp"
        has_input_deck = input_deck_artifact in names

    ccx_cmd = _which_existing("ccx", "ccx_linux", "ccx2.21", "ccx_static", "ccx.exe")
    ccx_available = ccx_cmd is not None

    missing_items: list[str] = []
    if not has_mesh:
        missing_items.append("simulation/mesh/ (no mesh files found in package)")
    if not has_solver_settings:
        missing_items.append("simulation/solver_settings.json")
    if not has_load_case:
        missing_items.append(f"simulation/load_cases/{load_case_id}.json")
    if not has_input_deck:
        missing_items.append(input_deck_artifact)
    if not ccx_available:
        missing_items.append("CalculiX executable (ccx) not found on PATH")

    ready_to_run = not missing_items
    planned_artifacts: list[dict[str, str]] = [
        {
            "path": f"simulation/runs/{run_id}/solver_run.json",
            "kind": "solver_run_record",
            "role": "run_metadata",
        },
        {
            "path": f"simulation/runs/{run_id}/solver_log.txt",
            "kind": "solver_log",
            "role": "solver_stdout",
        },
        {
            "path": f"simulation/runs/{run_id}/outputs/result.frd",
            "kind": "frd_result",
            "role": "primary_result",
        },
    ]
    if extract_results:
        planned_artifacts.append(
            {
                "path": "results/computed_metrics.json",
                "kind": "computed_metrics",
                "role": "extracted_metrics",
            }
        )
    if refresh_summary:
        planned_artifacts.extend(
            [
                {
                    "path": "results/result_summary.json",
                    "kind": "result_summary",
                    "role": "postprocessing_summary",
                },
                {
                    "path": "results/evidence_index.json",
                    "kind": "evidence_index",
                    "role": "evidence_index",
                },
                {
                    "path": "results/postprocessing_summary.md",
                    "kind": "markdown_report",
                    "role": "human_readable_summary",
                },
            ]
        )

    warnings = [
        "No solver execution was performed.",
        "This is a read-only structural preflight preview only.",
    ]
    if not ready_to_run:
        warnings.append(f"Run is not ready: {len(missing_items)} item(s) missing.")

    return {
        "ok": True,
        "tool": "structural.prepare_solver_run",
        "status": "completed",
        "project_id": project_id,
        "package_path": str(package_path),
        "solver": solver,
        "run_id": run_id,
        "load_case_id": load_case_id,
        "requires_approval": True,
        "solver_execution_performed": False,
        "ready_to_run": ready_to_run,
        "input_deck_artifact": input_deck_artifact,
        "preflight": {
            "has_mesh": has_mesh,
            "has_solver_settings": has_solver_settings,
            "has_load_case": has_load_case,
            "has_input_deck": has_input_deck,
            "ccx_available": ccx_available,
            "missing_items": missing_items,
        },
        "planned_artifacts": planned_artifacts,
        "warnings": warnings,
        "errors": [],
        "safety_note": _SAFETY_NOTE_PREPARE,
        "claim_advancement": "none",
        "claim_boundary": _CLAIM_BOUNDARY_PREFLIGHT_NOTE,
    }

