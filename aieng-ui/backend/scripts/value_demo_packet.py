"""Canonical value-demo packet for issue #368.

This script does not run CAD, mesh, or solver tools. It emits the fixed
prompt/tool sequence and evidence checklist for the real CAD->CAE value demo so
external agents and reviewers run the same small case every time.
"""

from __future__ import annotations

import argparse
import json
from typing import Any


VALUE_DEMO_CAD_CODE = """from build123d import *

# Single connected solid, 100 x 20 x 10 mm, centered at the origin.
# The integration test for the real solve loop uses the same dimensions.
beam = Box(100.0, 20.0, 10.0)
beam.label = "value_demo_cantilever"
beam.color = Color(0.18, 0.45, 0.85)
result = beam
"""

VALUE_DEMO_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "onboard",
        "tool": "aieng.agent_readme, aieng.guide, aieng.create_project",
        "prompt": (
            "Start a new AIENG project named value-demo-cantilever. Read the "
            "CAD and CAE guides before creating geometry or running analysis."
        ),
        "expected": ["project_id"],
    },
    {
        "id": "build_cad",
        "tool": "cad.execute_build123d",
        "prompt": (
            "Create the single connected cantilever beam from the canonical "
            "VALUE_DEMO_CAD_CODE. Use mode=replace, model_kind=mechanical, "
            "response_detail=compact, thumbnail=true."
        ),
        "expected": [
            "geometry/generated.step",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "named part value_demo_cantilever",
        ],
    },
    {
        "id": "pick_faces",
        "tool": "aieng.agent_context",
        "prompt": (
            "Inspect the topology and copy the @face pointer on the xmin end as "
            "FIXED_END and the @face pointer on the xmax end as LOAD_END."
        ),
        "expected": ["two resolved end-face pointers", "no invented face ids"],
    },
    {
        "id": "solve_pipeline",
        "tool": "cae.run_simulation_pipeline",
        "prompt": (
            "Run a linear static solve: Al6061-T6 material, fixed support on "
            "FIXED_END, total 50 N downward load on LOAD_END, mesh_size_mm=6, "
            "run_id=value_demo_run_001. Use the copied face pointers. Stop for "
            "normal workbench approval before the solver executes."
        ),
        "expected": [
            "simulation/mesh/mesh.inp",
            "simulation/runs/value_demo_run_001/solver_input.inp",
            "simulation/runs/value_demo_run_001/solver_run.json",
            "simulation/runs/value_demo_run_001/outputs/result.frd",
            "results/computed_metrics.json",
            "results/result_summary.json",
        ],
    },
    {
        "id": "viewer_check",
        "tool": "workbench viewer",
        "prompt": (
            "Open the result fields in the viewer and show von Mises stress and "
            "displacement magnitude. The demo passes only when the field source "
            "is the real FRD result from value_demo_run_001."
        ),
        "expected": [
            "real FRD-derived stress field",
            "real FRD-derived displacement field",
            "no synthetic fallback used",
        ],
    },
    {
        "id": "report",
        "tool": "report.generate",
        "prompt": (
            "Generate the engineering report and write a short plain-language "
            "summary that cites max displacement, max von Mises stress, safety "
            "factor when available, the load case id, and the credibility tier."
        ),
        "expected": [
            "engineering report HTML",
            "metric citations from results/computed_metrics.json",
            "honesty boundaries included",
        ],
    },
)

EXPECTED_EVIDENCE = (
    "geometry/generated.step",
    "geometry/topology_map.json",
    "graph/feature_graph.json",
    "simulation/setup.yaml",
    "simulation/cae_mapping.json",
    "simulation/mesh/mesh.inp",
    "simulation/runs/value_demo_run_001/solver_input.inp",
    "simulation/runs/value_demo_run_001/solver_run.json",
    "simulation/runs/value_demo_run_001/outputs/result.frd",
    "results/computed_metrics.json",
    "results/result_summary.json",
    "engineering report HTML from report.generate or GET /api/projects/{id}/report",
)

HONESTY_BOUNDARIES = (
    "The demo is linear static only.",
    "The numbers are mesh-dependent until a convergence study is run.",
    "A CalculiX exit code plus FRD extraction is solver evidence, not certification.",
    "Synthetic fallback fields are a failed demo condition for issue #368.",
    "No physical validation, fatigue, buckling, contact, or bolt preload is claimed.",
)


def build_packet() -> dict[str, Any]:
    return {
        "issue": 368,
        "name": "CAD->CAE value demo: single-solid cantilever",
        "geometry": {
            "kind": "single_connected_solid",
            "dimensions_mm": {"x": 100.0, "y": 20.0, "z": 10.0},
            "cad_code": VALUE_DEMO_CAD_CODE,
        },
        "steps": list(VALUE_DEMO_STEPS),
        "expected_evidence": list(EXPECTED_EVIDENCE),
        "honesty_boundaries": list(HONESTY_BOUNDARIES),
        "recording_checklist": [
            "Create project and CAD in the workbench",
            "Show copied fixed/load face pointers",
            "Show approval before solver execution",
            "Show real FRD fields in the viewer",
            "Show report.generate output with cited metrics and limitations",
        ],
    }


def build_markdown() -> str:
    packet = build_packet()
    lines = [
        f"# {packet['name']}",
        "",
        "Canonical packet for issue #368. This file is generated from the script",
        "constants; the script itself never runs CAD, meshing, or solver tools.",
        "",
        "## CAD Code",
        "",
        "```python",
        packet["geometry"]["cad_code"].rstrip(),
        "```",
        "",
        "## Prompt / Tool Sequence",
        "",
    ]
    for index, step in enumerate(packet["steps"], start=1):
        lines.extend(
            [
                f"{index}. `{step['tool']}`",
                f"   Prompt: {step['prompt']}",
                "   Expected: " + "; ".join(step["expected"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Evidence Checklist",
            "",
            *[f"- `{item}`" if "/" in item else f"- {item}" for item in packet["expected_evidence"]],
            "",
            "## Honesty Boundaries",
            "",
            *[f"- {item}" for item in packet["honesty_boundaries"]],
            "",
            "## Recording Checklist",
            "",
            *[f"- {item}" for item in packet["recording_checklist"]],
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the issue #368 value-demo packet.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--print-cad-code", action="store_true")
    args = parser.parse_args()

    if args.print_cad_code:
        print(VALUE_DEMO_CAD_CODE, end="")
        return 0
    if args.format == "json":
        print(json.dumps(build_packet(), indent=2, sort_keys=True))
    else:
        print(build_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
