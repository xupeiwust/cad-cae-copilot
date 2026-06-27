from __future__ import annotations

from app.cae_credibility import CREDIBILITY_LEVELS, assess_cae_credibility


def _base() -> dict:
    return {
        "result_artifacts": ["simulation/runs/run_001/outputs/result.frd"],
        "solver_run": {"status": "completed"},
        "parsed_metrics": {"max_von_mises_mpa": 120.0},
    }


def test_cae_credibility_no_artifact_is_insufficient() -> None:
    result = assess_cae_credibility({})

    assert result["tier"] == "no_result_artifact"
    assert result["status"] == "insufficient"
    assert result["missing_next"] == ["result_artifacts"]
    assert result["certified"] is False


def test_cae_credibility_solver_completed_but_metrics_missing() -> None:
    result = assess_cae_credibility({
        "result_artifacts": ["result.frd"],
        "solver_run": {"state": "completed"},
    })

    assert result["tier"] == "solver_completed"
    assert result["missing_next"] == ["parsed_metrics"]
    assert result["certified"] is False


def test_cae_credibility_parsed_metrics_wait_for_plausibility_and_notes_mesh_unknown() -> None:
    result = assess_cae_credibility(_base())

    assert result["tier"] == "numerical_result_parsed"
    assert result["missing_next"] == ["plausibility_checked"]
    assert any("Mesh quality or convergence evidence is unknown" in item for item in result["limitations"])


def test_cae_credibility_plausibility_failure_caps_tier() -> None:
    evidence = _base() | {"plausibility_checks": {"status": "failed"}}

    result = assess_cae_credibility(evidence)

    assert result["tier"] == "numerical_result_parsed"
    assert result["status"] == "failed"
    assert "design-target support" in " ".join(result["limitations"])


def test_cae_credibility_design_target_compared_before_benchmark() -> None:
    evidence = _base() | {
        "mesh_convergence": {"status": "passed", "converged": True},
        "plausibility_checks": {"status": "passed"},
        "design_target_comparison": {"status": "failed"},
    }

    result = assess_cae_credibility(evidence)

    assert result["tier"] == "design_target_compared"
    assert result["status"] == "failed"
    assert result["missing_next"] == ["benchmark_calibrated"]


def test_cae_credibility_mesh_failure_caps_benchmark_credit() -> None:
    evidence = _base() | {
        "mesh_convergence": {"status": "not_converged", "converged": False},
        "plausibility_checks": {"status": "passed"},
        "design_target_comparison": {"status": "passed"},
        "benchmark_comparison": {"status": "passed"},
    }

    result = assess_cae_credibility(evidence)

    assert result["tier"] == "design_target_compared"
    assert result["missing_next"] == ["benchmark_calibrated"]
    assert any("benchmark credibility is capped" in item for item in result["limitations"])


def test_cae_credibility_benchmark_and_human_review_supported() -> None:
    evidence = _base() | {
        "mesh_convergence": {"status": "passed", "converged": True},
        "plausibility_checks": {"status": "passed"},
        "design_target_comparison": {"status": "passed"},
        "benchmark_comparison": {"status": "passed"},
        "human_review": {"status": "supported"},
    }

    result = assess_cae_credibility(evidence)

    assert result["tier"] == "human_review_supported"
    assert result["status"] == "supported"
    assert result["ordered_levels"] == list(CREDIBILITY_LEVELS)
    assert result["certified"] is False
    assert "does not certify the design" in " ".join(result["limitations"])
