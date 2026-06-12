"""Shape-study demo fixture (bracket fillet radius + hole diameter).

Provides deterministic data + package assembly for a shape-bearing parameter
study.  Candidates are evaluated with deterministic static metrics and a fake
geometry snapshot so that ``cad.critique`` can flag a manufacturing-rule
violation without running an external solver or geometry kernel.
"""
from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters.optimization_variables import resolve_optimization_variables

FIXTURE_DIR = Path(__file__).with_name("fixtures") / "design_study_shape_demo"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"

# ── static metric maps for deterministic evaluation ───────────────────────────

CANDIDATE_STATIC_METRICS: dict[str, dict[str, Any]] = {
    "candidate_good": {
        "volume_mm3": 880.0,
        "mass_kg": 2.2,
        "max_stress": 160.0,
        "max_deflection": 3.3,
        "interfaces_preserved": True,
    },
    "candidate_larger_hole": {
        "volume_mm3": 890.0,
        "mass_kg": 2.25,
        "max_stress": 162.0,
        "max_deflection": 3.35,
        "interfaces_preserved": True,
    },
    "candidate_sharp_fillet": {
        # Numerically attractive, but manufacturing-rule critique makes it infeasible.
        "volume_mm3": 850.0,
        "mass_kg": 2.1,
        "max_stress": 155.0,
        "max_deflection": 3.2,
        "interfaces_preserved": True,
    },
    "candidate_overstressed": {
        "volume_mm3": 870.0,
        "mass_kg": 2.15,
        "max_stress": 250.0,   # exceeds 200 limit -> infeasible
        "max_deflection": 3.0,
        "interfaces_preserved": True,
    },
    "candidate_unknown": {
        # No structural metrics -> ranking will classify as unknown.
        "executed": True,
        "geometry_kind": "brep",
    },
}


def _load_json(name: str) -> Any:
    path = FIXTURE_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_demo_inputs() -> dict[str, Any]:
    """Return deep-copied fixture data."""
    return {
        "baseline_shape_ir": copy.deepcopy(_load_json("baseline_shape_ir.json")),
        "problem": copy.deepcopy(_load_json("design_study_problem.json")),
        "candidates": {
            "candidate_good": copy.deepcopy(_load_json("candidate_good.json")),
            "candidate_larger_hole": copy.deepcopy(_load_json("candidate_larger_hole.json")),
            "candidate_sharp_fillet": copy.deepcopy(_load_json("candidate_sharp_fillet.json")),
            "candidate_overstressed": copy.deepcopy(_load_json("candidate_overstressed.json")),
            "candidate_unknown": copy.deepcopy(_load_json("candidate_unknown.json")),
        },
    }


# ── artifact path constants ───────────────────────────────────────────────────

BASELINE_SHAPE_IR_PATH = "geometry/shape_ir.json"
DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"
DESIGN_CANDIDATES_DIR = "patches/design_candidates/"
BASELINE_SETUP_PATH = "simulation/setup.yaml"
BASELINE_SETUP_CONTENT = "mesh:\n  size: 2.0\n"

PR1_ARTIFACTS = {
    "diagnostics/design_study_problem_diagnostics.json",
    "diagnostics/design_study_candidate_validation.json",
}

PR2_ARTIFACTS = {
    "analysis/design_study_iterations.json",
    "diagnostics/design_study_report.json",
}

PR3_ARTIFACTS = {
    "analysis/design_study_candidate_ranking.json",
    "diagnostics/design_study_scoring_report.json",
}

PR4_ARTIFACTS = {
    "analysis/design_study_acceptance.json",
    "diagnostics/design_study_acceptance_report.json",
}

ALL_STUDY_ARTIFACTS = PR1_ARTIFACTS | PR2_ARTIFACTS | PR3_ARTIFACTS | PR4_ARTIFACTS


def expected_candidate_artifacts(candidate_id: str) -> set[str]:
    """Artifacts expected under a candidate workspace after execution."""
    prefix = f"candidates/{candidate_id}/"
    return {
        f"{prefix}patch.json",
        f"{prefix}geometry/shape_ir.json",
        f"{prefix}provenance/candidate.json",
    }


def expected_cae_evaluation_artifacts(candidate_id: str) -> set[str]:
    """Artifacts expected under a candidate workspace after CAE evaluation."""
    prefix = f"candidates/{candidate_id}/"
    return {
        f"{prefix}analysis/evaluation.json",
        f"{prefix}diagnostics/evaluation_report.json",
        f"{prefix}analysis/cae_evaluation_request.json",
        f"{prefix}diagnostics/cae_evaluation_request.json",
        f"{prefix}simulation/setup.yaml",
    }


def expected_accepted_artifacts(candidate_id: str) -> set[str]:
    """Artifacts expected under an accepted workspace after acceptance."""
    prefix = f"accepted/{candidate_id}/"
    return {
        f"{prefix}patch.json",
        f"{prefix}geometry/shape_ir.json",
        f"{prefix}analysis/evaluation.json",
        f"{prefix}provenance/acceptance.json",
    }


# ── package assembly ──────────────────────────────────────────────────────────

def write_demo_package(package_path: Path) -> dict[str, Any]:
    """Create a deterministic .aieng package with the shape-study fixture data.

    Returns the loaded fixture data dict.
    """
    data = load_demo_inputs()
    package_path.parent.mkdir(parents=True, exist_ok=True)

    variables_doc = resolve_optimization_variables(
        data["problem"], study_id="shape_bracket_001"
    )
    # `resolve_optimization_variables` leaves created_at as None; stamp it for determinism.
    variables_doc["provenance"]["created_at"] = "2026-06-12T00:00:00Z"

    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "aieng.package", "version": "0.1.0"}))
        zf.writestr(BASELINE_SHAPE_IR_PATH, json.dumps(data["baseline_shape_ir"]))
        zf.writestr(DESIGN_STUDY_PROBLEM_PATH, json.dumps(data["problem"]))
        zf.writestr(OPTIMIZATION_VARIABLES_PATH, json.dumps(variables_doc))
        zf.writestr(BASELINE_SETUP_PATH, BASELINE_SETUP_CONTENT)
        for cid, cand in data["candidates"].items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json", json.dumps(cand))
    return data


def inject_static_evaluation(package_path: Path, candidate_id: str) -> None:
    """Inject deterministic static metrics into a candidate workspace."""
    metrics = CANDIDATE_STATIC_METRICS.get(candidate_id, {})
    _append_to_package(package_path, {
        f"candidates/{candidate_id}/analysis/static_metrics.json": json.dumps(metrics).encode(),
    })


def inject_candidate_geometry(package_path: Path, candidate_id: str) -> None:
    """Inject a fake topology_map + feature_graph for cad.critique.

    ``candidate_sharp_fillet`` is crafted to trigger a high-severity
    ``min_wall_thickness`` manufacturing-rule finding.  All other candidates
    receive a passing bracket geometry snapshot.
    """
    if candidate_id == "candidate_sharp_fillet":
        # Thin wall triggers min_wall_thickness (high severity because feature name contains "wall").
        topo = {
            "entities": [
                {
                    "id": "body_bracket",
                    "type": "solid",
                    "name": "bracket",
                    "bounding_box": [0.0, 0.0, 0.0, 100.0, 60.0, 1.5],
                }
            ]
        }
        fg = {
            "features": [
                {
                    "type": "named_part",
                    "name": "wall",
                    "geometry_refs": {"body": "body_bracket"},
                },
                {
                    "type": "mounting_hole",
                    "name": "mounting_hole_pattern",
                    "parameters": {"hole_diameter_mm": 0.5},
                    "geometry_refs": {"body": "body_bracket"},
                },
            ]
        }
    else:
        # Passing geometry: wall thickness 20 mm, standard 8 mm hole.
        topo = {
            "entities": [
                {
                    "id": "body_bracket",
                    "type": "solid",
                    "name": "bracket",
                    "bounding_box": [0.0, 0.0, 0.0, 100.0, 60.0, 20.0],
                }
            ]
        }
        hole_dia = 8.0
        if candidate_id == "candidate_larger_hole":
            hole_dia = 10.0
        elif candidate_id == "candidate_unknown":
            hole_dia = 6.0
        fg = {
            "features": [
                {
                    "type": "named_part",
                    "name": "base_plate",
                    "geometry_refs": {"body": "body_bracket"},
                },
                {
                    "type": "mounting_hole",
                    "name": "mounting_hole_pattern",
                    "parameters": {"hole_diameter_mm": hole_dia},
                    "geometry_refs": {"body": "body_bracket"},
                },
            ]
        }

    _append_to_package(package_path, {
        f"candidates/{candidate_id}/geometry/topology_map.json": json.dumps(topo).encode(),
        f"candidates/{candidate_id}/graph/feature_graph.json": json.dumps(fg).encode(),
    })


def _append_to_package(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".shape.tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
