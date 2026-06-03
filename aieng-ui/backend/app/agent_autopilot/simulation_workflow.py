"""Deterministic /simulate solver workflow state (v3).

Pure and side-effect-free. Given a readiness report plus the observed results of
``cae.prepare_solver_run`` and ``cae.run_solver``, computes the workflow phase
fields the /simulate routing uses to gate an approval-gated prepare → run flow.

This module never runs the solver, never touches CAD, and never bypasses
approval. It only describes *where the run is* so the engine can:
  * refuse to prepare/run while required inputs are missing or a referenced
    target is unknown (known=false);
  * refuse ``cae.run_solver`` before a successful ``cae.prepare_solver_run``;
  * refuse a ``final`` that claims solver results when the solver has not run.
"""

from __future__ import annotations

from typing import Any

PREPARE_SOLVER_TOOL = "cae.prepare_solver_run"
RUN_SOLVER_TOOL = "cae.run_solver"

# Conservative phrases that assert the solver ran / produced results. Used to
# block a `final` that claims results before solver_executed is true. Kept
# narrow to avoid false positives on plan text ("the solver has NOT run").
_RESULT_CLAIM_TERMS = (
    "max stress",
    "maximum stress",
    "peak stress",
    "von mises",
    "von-mises",
    "factor of safety",
    "safety factor",
    "results show",
    "the results are",
    "simulation shows",
    "solver completed",
    "simulation completed",
    "analysis completed",
    "stress is ",
    "displacement is ",
    "deflection is ",
    "求解完成",
    "仿真结果",
    "应力为",
    "位移为",
    "安全系数为",
)


def final_claims_results(text: Any) -> bool:
    """True when free text asserts solver results / completion (conservative)."""
    if not isinstance(text, str) or not text.strip():
        return False
    lowered = text.lower()
    return any(term in lowered for term in _RESULT_CLAIM_TERMS)


def _result_ok(executed: Any) -> bool:
    if not isinstance(executed, dict):
        return False
    status = str(executed.get("status") or "").lower()
    if status in {"error", "failed", "failure"} or executed.get("error"):
        return False
    return True


def _first_str(source: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _str_list(source: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str) and item.strip()]
    return []


def _blocked_targets(readiness: dict[str, Any]) -> list[str]:
    targets = readiness.get("targets") if isinstance(readiness.get("targets"), dict) else {}
    blocked: list[str] = []
    for kind in ("parts", "artifacts"):
        for entry in targets.get(kind, []) or []:
            if isinstance(entry, dict) and entry.get("known") is False:
                value = entry.get("value")
                if value:
                    blocked.append(str(value))
    return blocked


def build_simulation_workflow_state(
    readiness: dict[str, Any] | None,
    *,
    prepared: dict[str, Any] | None = None,
    executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the /simulate workflow phase. Pure.

    ``readiness`` is a report from ``build_simulation_readiness_report``.
    ``prepared`` is the successful ``cae.prepare_solver_run`` output (or None);
    ``executed`` is the latest ``cae.run_solver`` output (success or failure, or
    None). The result never asserts execution unless ``executed`` succeeded.
    """
    readiness = readiness if isinstance(readiness, dict) else {}
    missing_required = list(readiness.get("missing_required_inputs") or [])
    blocked_targets = _blocked_targets(readiness)
    ready_for_solver = bool(readiness.get("ready_for_solver"))

    ready_to_prepare = ready_for_solver and not missing_required and not blocked_targets
    solver_deck_prepared = isinstance(prepared, dict) and bool(prepared)
    solver_executed = _result_ok(executed)
    solver_run_failed = isinstance(executed, dict) and bool(executed) and not solver_executed

    prepared_dict = prepared if isinstance(prepared, dict) else {}
    deck_path = _first_str(prepared_dict, "deck_path", "input_deck", "inp_path", "deck", "input_path")
    manifest_path = _first_str(prepared_dict, "manifest_path", "manifest", "handoff_path")

    executed_dict = executed if isinstance(executed, dict) else {}
    result_artifacts = _str_list(executed_dict, "result_artifacts", "artifacts", "written_artifacts") if solver_executed else []

    ready_to_run_solver = ready_to_prepare and solver_deck_prepared and not solver_executed
    solver_run_approval_required = ready_to_run_solver

    if solver_executed:
        solver_status = "executed"
    elif solver_run_failed:
        solver_status = "failed"
    elif blocked_targets:
        solver_status = "blocked_unknown_target"
    elif missing_required:
        solver_status = "blocked_missing_inputs"
    elif solver_deck_prepared:
        solver_status = "deck_prepared"
    elif ready_to_prepare:
        solver_status = "ready_to_prepare"
    else:
        solver_status = "not_run"

    return {
        "ready_to_prepare_solver_run": ready_to_prepare,
        "solver_deck_prepared": solver_deck_prepared,
        "deck_path": deck_path,
        "manifest_path": manifest_path,
        "ready_to_run_solver": ready_to_run_solver,
        "solver_run_approval_required": solver_run_approval_required,
        "solver_executed": solver_executed,
        "solver_status": solver_status,
        "result_artifacts": result_artifacts,
        "blocked_targets": blocked_targets,
        "missing_required_inputs": missing_required,
    }
