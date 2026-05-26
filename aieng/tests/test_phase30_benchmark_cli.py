from __future__ import annotations

from aieng.benchmark.run import _mean_ci95, _scenario_registry


def test_phase30_registry_contains_four_required_scenarios() -> None:
    registry = _scenario_registry()
    for scenario in (
        "mass_reduction",
        "diagnose_broken_cae_setup",
        "stress_concentrator",
        "setup_correction_missing_items",
    ):
        assert scenario in registry
        assert set(registry[scenario]) == {"A", "B"}


def test_phase30_confidence_interval_helper() -> None:
    result = _mean_ci95([1.0, 0.5, 0.0, 1.0, 0.5])
    assert result["mean"] == 0.6
    assert result["ci95_low"] < result["mean"] < result["ci95_high"]
