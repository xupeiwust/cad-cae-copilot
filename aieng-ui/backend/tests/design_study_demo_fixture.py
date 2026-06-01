"""Canonical design-study demo fixture (PR1–PR4 full-flow regression).

Provides deterministic data + package assembly for the agent-guided parameter
study pipeline: validate → execute → rank → accept.

All data is static (no external solver, no random generation).
"""
from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).with_name("fixtures") / "design_study_demo"

# ── static metric maps for deterministic evaluation ───────────────────────────

CANDIDATE_STATIC_METRICS: dict[str, dict[str, Any]] = {
    "candidate_good": {
        "volume_mm3": 850.0,   # lower than baseline 1000
        "mass_kg": 2.3,
        "max_stress": 180.0,   # within 200 limit
        "max_deflection": 4.2, # within 5 limit
        "interfaces_preserved": True,
    },
    "candidate_unknown": {
        # No volume metric → ranking will classify as unknown
        "executed": True,
        "geometry_kind": "brep",
    },
    "candidate_infeasible": {
        "volume_mm3": 820.0,   # lower volume
        "mass_kg": 2.2,
        "max_stress": 250.0,   # EXCEEDS 200 limit → infeasible
        "max_deflection": 3.5,
        "interfaces_preserved": True,
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
            "candidate_bad_bounds": copy.deepcopy(_load_json("candidate_bad_bounds.json")),
            "candidate_protected": copy.deepcopy(_load_json("candidate_protected.json")),
            "candidate_unknown": copy.deepcopy(_load_json("candidate_unknown.json")),
            "candidate_infeasible": copy.deepcopy(_load_json("candidate_infeasible.json")),
        },
    }


# ── artifact path constants ───────────────────────────────────────────────────

BASELINE_SHAPE_IR_PATH = "geometry/shape_ir.json"
DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"
DESIGN_CANDIDATES_DIR = "patches/design_candidates/"

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
        f"{prefix}analysis/evaluation.json",
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
    """Create a deterministic .aieng package with the demo fixture data.

    Returns the loaded fixture data dict.
    """
    data = load_demo_inputs()
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "aieng.package", "version": "0.1.0"}))
        zf.writestr(BASELINE_SHAPE_IR_PATH, json.dumps(data["baseline_shape_ir"]))
        zf.writestr(DESIGN_STUDY_PROBLEM_PATH, json.dumps(data["problem"]))
        for cid, cand in data["candidates"].items():
            zf.writestr(f"{DESIGN_CANDIDATES_DIR}{cid}.json", json.dumps(cand))
    return data


def inject_static_evaluation(package_path: Path, candidate_id: str) -> None:
    """Inject static evaluation metrics into a candidate workspace.

    Writes ``candidates/<cid>/analysis/evaluation.json`` with pre-computed
    metrics so ranking can proceed without a real recompiler/CAE run.
    """
    metrics = CANDIDATE_STATIC_METRICS.get(candidate_id, {})
    evaluation = {
        "format": "aieng.design_study_candidate_evaluation",
        "format_version": "0.1.0",
        "evaluation_status": "complete" if metrics else "partial",
        "compile_status": "compile_succeeded",
        "metrics": metrics,
        "errors": [],
        "warnings": [],
        "reason": "static evaluation for demo fixture",
        "baseline_modified": False,
    }
    _append_to_package(package_path, {
        f"candidates/{candidate_id}/analysis/evaluation.json": json.dumps(evaluation).encode(),
    })


def _append_to_package(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".demo.tmp.aieng")
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
