"""CAE evidence credibility ladder.

Pure helper for issue #433. It classifies available CAE evidence without
claiming certification or mutating packages. Runtime/report surfaces can consume
this later, but the helper is intentionally standalone so the ladder semantics
are testable before UI integration.
"""

from __future__ import annotations

from typing import Any


CREDIBILITY_LEVELS: tuple[str, ...] = (
    "no_result_artifact",
    "artifact_present",
    "solver_completed",
    "numerical_result_parsed",
    "plausibility_checked",
    "design_target_compared",
    "benchmark_calibrated",
    "human_review_supported",
)


def assess_cae_credibility(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Return a conservative credibility tier for CAE evidence.

    The ladder is monotonic but not a safety claim. Failing plausibility or
    calibration checks cap the tier and mark the result as failed/warning.
    Missing mesh/convergence evidence lowers confidence language even when other
    artifacts exist.
    """
    data = evidence or {}
    limitations: list[str] = [
        "Credibility tier is review guidance, not certification or production sign-off."
    ]
    missing_next: list[str] = []
    status = "insufficient"
    tier = "no_result_artifact"

    artifacts = data.get("result_artifacts") or data.get("artifacts") or []
    if not artifacts:
        missing_next.append("result_artifacts")
        return _result(tier, status, limitations, missing_next)

    tier = "artifact_present"
    status = "warning"

    solver = data.get("solver_run") if isinstance(data.get("solver_run"), dict) else {}
    solver_completed = bool(
        solver.get("solved") is True
        or solver.get("completed") is True
        or str(solver.get("status") or solver.get("state") or "").lower() in {"completed", "success", "ok", "passed"}
    )
    if not solver_completed:
        missing_next.append("solver_completed")
        return _result(tier, status, limitations, missing_next)

    tier = "solver_completed"

    metrics = data.get("parsed_metrics") or data.get("computed_metrics")
    if not _has_content(metrics):
        missing_next.append("parsed_metrics")
        return _result(tier, status, limitations, missing_next)

    tier = "numerical_result_parsed"

    mesh = data.get("mesh_convergence") or data.get("mesh_quality")
    if not isinstance(mesh, dict) or not mesh:
        limitations.append("Mesh quality or convergence evidence is unknown.")
    else:
        mesh_status = str(mesh.get("status") or mesh.get("verdict") or "").lower()
        if mesh.get("converged") is False or mesh_status in {"failed", "not_converged", "poor"}:
            limitations.append("Mesh quality or convergence check did not pass; benchmark credibility is capped.")

    plausibility = data.get("plausibility_checks")
    plausibility_status = _status(plausibility)
    if plausibility_status == "failed":
        limitations.append("Plausibility checks failed; do not use this as design-target support.")
        return _result(tier, "failed", limitations, ["plausibility_checked"])
    if plausibility_status != "passed":
        missing_next.append("plausibility_checked")
        return _result(tier, status, limitations, missing_next)

    tier = "plausibility_checked"

    design_target = data.get("design_target_comparison")
    design_status = _status(design_target)
    if design_status not in {"passed", "failed", "warning"}:
        missing_next.append("design_target_compared")
        return _result(tier, status, limitations, missing_next)

    tier = "design_target_compared"
    status = "failed" if design_status == "failed" else "warning"

    benchmark = data.get("benchmark_comparison") or data.get("calibration")
    benchmark_status = _status(benchmark)
    mesh_caps_benchmark = any("benchmark credibility is capped" in item for item in limitations)
    if benchmark_status == "failed":
        limitations.append("Benchmark or calibration comparison failed.")
        return _result(tier, "failed", limitations, ["benchmark_calibrated"])
    if benchmark_status != "passed" or mesh_caps_benchmark:
        missing_next.append("benchmark_calibrated")
        return _result(tier, status, limitations, missing_next)

    tier = "benchmark_calibrated"
    status = "warning"

    review = data.get("human_review")
    review_status = _status(review)
    if review_status != "supported":
        missing_next.append("human_review_supported")
        return _result(tier, status, limitations, missing_next)

    tier = "human_review_supported"
    status = "supported"
    limitations.append("Human review supports a claim, but does not certify the design.")
    return _result(tier, status, limitations, missing_next)


def _result(tier: str, status: str, limitations: list[str], missing_next: list[str]) -> dict[str, Any]:
    score = CREDIBILITY_LEVELS.index(tier)
    return {
        "schema_version": "0.1",
        "tier": tier,
        "tier_index": score,
        "ordered_levels": list(CREDIBILITY_LEVELS),
        "status": status,
        "limitations": limitations,
        "missing_next": missing_next,
        "certified": False,
    }


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _status(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    raw = value.get("status", value.get("verdict", value.get("result", "")))
    if isinstance(raw, bool):
        return "passed" if raw else "failed"
    return str(raw or "").strip().lower()
