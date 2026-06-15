"""Tests for the pure sizing-sweep ranker (optimize→verify loop closure)."""
from __future__ import annotations

from aieng.converters.sizing_sweep import (
    STATUS_ERROR,
    STATUS_FEASIBLE,
    STATUS_INFEASIBLE,
    STATUS_UNKNOWN,
    extract_static_metrics,
    rank_sizing_sweep,
)


def _variant(value, *, stress=None, disp=None, mass=None, solved=True, error=None):
    metrics = {}
    if stress is not None:
        metrics["max_von_mises_stress"] = stress
    if disp is not None:
        metrics["max_displacement"] = disp
    if mass is not None:
        metrics["mass"] = mass
    v = {"value": value, "metrics": metrics, "solver_executed": solved}
    if error is not None:
        v["error"] = error
    return v


# ---------------------------------------------------------------------------
# extract_static_metrics
# ---------------------------------------------------------------------------


def test_extract_static_metrics_from_load_cases() -> None:
    cm = {
        "load_cases": [
            {"id": "lc1", "metrics": {
                "max_displacement": {"value": 1.2, "unit": "mm"},
                "max_von_mises_stress": {"value": 80.0, "unit": "MPa"},
            }},
            {"id": "lc2", "metrics": {
                "max_displacement": {"value": 2.5, "unit": "mm"},
                "max_von_mises_stress": {"value": 60.0, "unit": "MPa"},
            }},
        ]
    }
    m = extract_static_metrics(cm)
    # worst-case across load cases
    assert m["max_displacement"] == 2.5
    assert m["max_von_mises_stress"] == 80.0


def test_extract_static_metrics_handles_global_and_missing() -> None:
    assert extract_static_metrics(None) == {"max_von_mises_stress": None, "max_displacement": None}
    m = extract_static_metrics({"global_metrics": {"max_von_mises_stress": 42.0}})
    assert m["max_von_mises_stress"] == 42.0
    assert m["max_displacement"] is None


# ---------------------------------------------------------------------------
# rank_sizing_sweep — feasibility + recommendation
# ---------------------------------------------------------------------------


def test_min_mass_under_stress_constraint_picks_lightest_feasible() -> None:
    variants = [
        _variant(2.0, stress=240.0, mass=1.0),  # infeasible (over allowable)
        _variant(3.0, stress=160.0, mass=1.5),  # feasible, lightest feasible
        _variant(4.0, stress=120.0, mass=2.0),  # feasible, heavier
    ]
    report = rank_sizing_sweep(
        variants, objective="min_mass", stress_limit=200.0, safety_factor=1.0
    )
    assert report["constraint"]["allowable_stress"] == 200.0
    assert report["feasible_count"] == 2
    assert report["recommended"]["value"] == 3.0
    assert report["safe_to_apply"] is True
    # ranking: feasible first, by mass ascending
    assert [v["value"] for v in report["variants"]] == [3.0, 4.0, 2.0]
    assert report["variants"][0]["status"] == STATUS_FEASIBLE
    assert report["variants"][-1]["status"] == STATUS_INFEASIBLE


def test_safety_factor_tightens_allowable() -> None:
    variants = [_variant(3.0, stress=160.0, mass=1.5)]
    # yield 300, SF 2 → allowable 150; 160 > 150 → infeasible
    report = rank_sizing_sweep(
        variants, objective="min_mass", stress_limit=300.0, safety_factor=2.0
    )
    assert report["constraint"]["allowable_stress"] == 150.0
    assert report["recommended"] is None
    assert report["feasible_count"] == 0
    assert "no feasible variant" in report["recommendation_reason"]
    assert report["safe_to_apply"] is False


def test_min_displacement_objective() -> None:
    variants = [
        _variant(3.0, stress=100.0, disp=0.5, mass=1.5),
        _variant(5.0, stress=80.0, disp=0.2, mass=2.5),
    ]
    report = rank_sizing_sweep(variants, objective="min_displacement", stress_limit=200.0)
    assert report["objective_metric"] == "max_displacement"
    assert report["recommended"]["value"] == 5.0  # lowest displacement


def test_unsolved_variant_is_error_and_never_recommended() -> None:
    variants = [
        _variant(3.0, solved=False, error="solver returned non-zero"),
        _variant(4.0, stress=100.0, mass=2.0),
    ]
    report = rank_sizing_sweep(variants, objective="min_mass", stress_limit=200.0)
    statuses = {v["value"]: v["status"] for v in report["variants"]}
    assert statuses[3.0] == STATUS_ERROR
    assert report["recommended"]["value"] == 4.0
    # overall credibility downgraded because not all variants solved
    assert report["credibility"]["tier"] == "unverified"
    assert report["honesty"]["solver_executed_all"] is False


def test_missing_constraint_metric_is_unknown_not_pass() -> None:
    # solved but no stress reported, while a stress constraint is active
    variants = [_variant(3.0, disp=0.5, mass=1.5, solved=True)]
    report = rank_sizing_sweep(variants, objective="min_mass", stress_limit=200.0)
    assert report["variants"][0]["status"] == STATUS_UNKNOWN
    assert report["recommended"] is None
    assert report["safe_to_apply"] is False


def test_all_solved_earns_executed_solver_credibility() -> None:
    variants = [
        _variant(3.0, stress=160.0, mass=1.5),
        _variant(4.0, stress=120.0, mass=2.0),
    ]
    report = rank_sizing_sweep(variants, objective="min_mass", stress_limit=200.0)
    assert report["credibility"]["tier"] == "executed_solver_result"
    assert report["honesty"]["baseline_modified"] is False
    assert report["honesty"]["production_ready"] is False


def test_displacement_constraint_independent_of_stress() -> None:
    variants = [
        _variant(3.0, stress=100.0, disp=1.0, mass=1.5),  # disp over limit
        _variant(5.0, stress=120.0, disp=0.4, mass=2.5),  # ok
    ]
    report = rank_sizing_sweep(
        variants, objective="min_mass", stress_limit=200.0, displacement_limit=0.5
    )
    assert report["recommended"]["value"] == 5.0
    infeasible = next(v for v in report["variants"] if v["value"] == 3.0)
    assert infeasible["status"] == STATUS_INFEASIBLE
    assert "max_displacement" in infeasible["reason"]


def test_empty_variants() -> None:
    report = rank_sizing_sweep([], objective="min_mass", stress_limit=200.0)
    assert report["recommended"] is None
    assert report["recommendation_reason"] == "no variants supplied"
    assert report["credibility"]["tier"] == "unverified"


def test_no_constraint_ranks_by_objective_only() -> None:
    variants = [_variant(3.0, mass=1.5), _variant(4.0, mass=2.0)]
    report = rank_sizing_sweep(variants, objective="min_mass")
    assert report["constraint"]["allowable_stress"] is None
    assert report["feasible_count"] == 2  # unconstrained → all known are feasible
    assert report["recommended"]["value"] == 3.0
