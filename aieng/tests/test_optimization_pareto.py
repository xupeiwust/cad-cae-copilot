"""Tests for two-objective Pareto-front identification."""
from __future__ import annotations

import json
import zipfile
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aieng.converters.optimization_pareto import (
    PARETO_FRONT_PATH,
    compute_pareto_front,
    write_pareto_front_artifact,
)


def _load_schema(name: str) -> dict:
    return json.loads(files("aieng.schemas").joinpath(name).read_text(encoding="utf-8"))


def _validate(document: dict) -> list[str]:
    validator = Draft202012Validator(_load_schema("pareto_front.schema.json"))
    return sorted(
        (f"{'$' + ''.join(f'[{p}]' if isinstance(p, int) else f'.{p}' for p in e.absolute_path)}: {e.message}")
        for e in validator.iter_errors(document)
    )


def _candidate(cid: str, feasibility: str, metrics: dict) -> dict:
    return {
        "candidate_id": cid,
        "feasibility": feasibility,
        "metrics_used": metrics,
    }


# ── hand-computed minimization case ───────────────────────────────────────────

def test_minimize_minimize_hand_computed_front():
    """A 7-candidate minimization/minimization case with a known non-dominated set."""
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        # The trade-off frontier: improving one objective worsens the other.
        _candidate("c1", "feasible", {"mass_kg": 1.0, "max_stress": 200.0}),
        _candidate("c2", "feasible", {"mass_kg": 2.0, "max_stress": 100.0}),
        _candidate("c3", "feasible", {"mass_kg": 1.5, "max_stress": 150.0}),
        # Dominated candidates
        _candidate("c4", "feasible", {"mass_kg": 3.0, "max_stress": 300.0}),  # dominated by c1
        _candidate("c5", "feasible", {"mass_kg": 2.5, "max_stress": 120.0}),  # dominated by c2
        _candidate("c6", "feasible", {"mass_kg": 1.0, "max_stress": 250.0}),  # dominated by c1
        _candidate("c7", "feasible", {"mass_kg": 5.0, "max_stress": 400.0}),  # dominated by c1
    ]

    result = compute_pareto_front(candidates, objectives)

    assert result["status"] == "ok"
    assert result["candidate_count"] == 7
    assert set(result["front_candidate_ids"]) == {"c1", "c2", "c3"}
    assert set(result["dominated_candidate_ids"]) == {"c4", "c5", "c6", "c7"}
    assert len(result["front"]) == 3
    # Frontier ordered by objective 1 (mass) ascending.
    assert [item["candidate_id"] for item in result["front"]] == ["c1", "c3", "c2"]
    assert all("not a proven surface" in lim for lim in result["limitations"])


# ── mixed sense case ──────────────────────────────────────────────────────────

def test_minimize_maximize_mixed_sense():
    """Minimize mass while maximizing safety factor."""
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "safety_factor", "sense": "maximize"},
    ]
    candidates = [
        _candidate("a", "feasible", {"mass_kg": 1.0, "min_safety_factor": 2.0}),
        _candidate("b", "feasible", {"mass_kg": 2.0, "min_safety_factor": 3.0}),
        _candidate("c", "feasible", {"mass_kg": 1.5, "min_safety_factor": 2.5}),
        # Dominated: worse in both objectives after sense normalization.
        _candidate("d", "feasible", {"mass_kg": 2.0, "min_safety_factor": 1.5}),
        _candidate("e", "feasible", {"mass_kg": 3.0, "min_safety_factor": 2.5}),
    ]

    result = compute_pareto_front(candidates, objectives)

    assert result["status"] == "ok"
    assert set(result["front_candidate_ids"]) == {"a", "b", "c"}
    assert set(result["dominated_candidate_ids"]) == {"d", "e"}


# ── feasibility and data-quality filtering ────────────────────────────────────

def test_infeasible_candidates_excluded_from_frontier():
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        _candidate("good", "feasible", {"mass_kg": 1.0, "max_stress": 100.0}),
        _candidate("bad", "infeasible", {"mass_kg": 0.5, "max_stress": 50.0}),
        _candidate("unknown", "unknown", {"mass_kg": 0.6, "max_stress": 60.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    assert result["status"] == "insufficient_data"
    assert result["front_candidate_ids"] == []
    assert result["dominated_candidate_ids"] == []


def test_candidates_missing_metric_are_skipped():
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        _candidate("c1", "feasible", {"mass_kg": 1.0, "max_stress": 100.0}),
        _candidate("c2", "feasible", {"mass_kg": 2.0}),  # missing stress
        _candidate("c3", "feasible", {"max_stress": 50.0}),  # missing mass
        _candidate("c4", "feasible", {"mass_kg": 1.5, "max_stress": 90.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    assert result["status"] == "ok"
    assert set(result["front_candidate_ids"]) == {"c1", "c4"}
    assert result["candidate_count"] == 2


# ── unsupported counts ────────────────────────────────────────────────────────

def test_single_objective_returns_skipped():
    objectives = [{"metric": "mass", "sense": "minimize"}]
    candidates = [
        _candidate("c1", "feasible", {"mass_kg": 1.0}),
        _candidate("c2", "feasible", {"mass_kg": 2.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    assert result["status"] == "skipped"
    assert result["front"] == []
    assert result["dominated"] == []


def test_three_objectives_returns_skipped():
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
        {"metric": "deflection", "sense": "minimize"},
    ]
    candidates = [
        _candidate("c1", "feasible", {"mass_kg": 1.0, "max_stress": 100.0, "max_deflection": 1.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    assert result["status"] == "skipped"


def test_insufficient_eligible_candidates():
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        _candidate("c1", "feasible", {"mass_kg": 1.0, "max_stress": 100.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    assert result["status"] == "insufficient_data"


# ── artifact writing ──────────────────────────────────────────────────────────

def _make_pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"name": "study"}))
        zf.writestr("analysis/design_study_problem.json", json.dumps({
            "format": "aieng.design_study_problem",
            "id": "study_001",
            "variables": [],
        }))
    return pkg


def test_write_pareto_front_artifact_creates_valid_json(tmp_path: Path):
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        _candidate("c1", "feasible", {"mass_kg": 1.0, "max_stress": 200.0}),
        _candidate("c2", "feasible", {"mass_kg": 2.0, "max_stress": 100.0}),
        _candidate("c3", "feasible", {"mass_kg": 3.0, "max_stress": 300.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    pkg = _make_pkg(tmp_path)

    write_pareto_front_artifact(pkg, result, study_id="study_001")

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert PARETO_FRONT_PATH in names
        doc = json.loads(zf.read(PARETO_FRONT_PATH))

    assert doc["format"] == "aieng.pareto_front"
    assert doc["schema_version"] == "0.1"
    assert doc["study_id"] == "study_001"
    assert doc["design_study_problem_ref"] == "analysis/design_study_problem.json"
    assert doc["claim_policy"]["advisory_only"] is True
    assert doc["claim_policy"]["baseline_unchanged"] is True
    assert doc["provenance"]["created_by"] == "aieng.optimization_pareto"
    assert len(doc["front"]) == 2
    assert set(doc["dominated"]) == {"c3"}

    schema_issues = _validate(doc)
    assert schema_issues == [], schema_issues


def test_write_pareto_front_artifact_without_study_id_allows_null(tmp_path: Path):
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        _candidate("c1", "feasible", {"mass_kg": 1.0, "max_stress": 200.0}),
        _candidate("c2", "feasible", {"mass_kg": 2.0, "max_stress": 100.0}),
    ]
    result = compute_pareto_front(candidates, objectives)
    pkg = _make_pkg(tmp_path)

    write_pareto_front_artifact(pkg, result)

    with zipfile.ZipFile(pkg) as zf:
        doc = json.loads(zf.read(PARETO_FRONT_PATH))

    assert doc["study_id"] is None
    schema_issues = _validate(doc)
    assert schema_issues == [], schema_issues


def test_write_pareto_front_artifact_missing_package_raises():
    with pytest.raises(FileNotFoundError):
        write_pareto_front_artifact(Path("/nonexistent/path/study.aieng"), {"status": "ok"})


# ── determinism ───────────────────────────────────────────────────────────────

def test_compute_pareto_front_is_deterministic():
    objectives = [
        {"metric": "mass", "sense": "minimize"},
        {"metric": "stress", "sense": "minimize"},
    ]
    candidates = [
        # Frontier: two candidates tied on mass, plus a lighter/stronger point.
        _candidate("c_tie_b", "feasible", {"mass_kg": 1.0, "max_stress": 150.0}),
        _candidate("c_tie_a", "feasible", {"mass_kg": 1.0, "max_stress": 150.0}),
        _candidate("c_light", "feasible", {"mass_kg": 0.8, "max_stress": 180.0}),
        # Dominated candidates.
        _candidate("c_dom_b", "feasible", {"mass_kg": 2.0, "max_stress": 200.0}),
        _candidate("c_dom_a", "feasible", {"mass_kg": 1.5, "max_stress": 250.0}),
    ]
    result1 = compute_pareto_front(candidates, objectives)
    result2 = compute_pareto_front(list(reversed(candidates)), objectives)
    assert [item["candidate_id"] for item in result1["front"]] == [
        item["candidate_id"] for item in result2["front"]
    ]
    assert result1["dominated_candidate_ids"] == result2["dominated_candidate_ids"]
    assert set(result1["dominated_candidate_ids"]) == {"c_dom_a", "c_dom_b"}
