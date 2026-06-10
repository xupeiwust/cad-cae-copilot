"""Iterative-optimization convergence verdict + iteration history (#61).

Phase 2 drives an outer loop around the Phase-1 tools. After each round
(propose → run → evaluate → rank), the agent records the round's incumbent into
``analysis/optimization_iterations.json`` and reads a deterministic convergence
verdict to decide stop/continue.

This module is the *substrate* for that:
- ``evaluate_convergence`` is a PURE function over the iteration history + the
  study's convergence/budget config. It implements the five criteria from
  ``docs/phase2_iterative_optimization_plan.md`` §3.
- ``record_iteration_and_check`` reads the current ranking, appends an iteration
  snapshot, evaluates convergence, and writes the history artifact back.

The verdict is **advisory** — it tells the agent whether to stop; it never
accepts/promotes a candidate, runs a solver, or modifies the baseline.
Acceptance stays the only hard gate (``opt.accept_candidate``).
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

DESIGN_STUDY_CANDIDATE_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"
OPTIMIZATION_STUDY_PATH = "analysis/optimization_study.json"
OPTIMIZATION_ITERATIONS_PATH = "analysis/optimization_iterations.json"
OPTIMIZATION_ITERATIONS_FORMAT = "aieng.optimization_iterations"

# Default convergence thresholds — used when the study config omits a field.
# All are explicit, documented numbers (no hidden magic in the criteria logic).
_DEFAULTS = {
    "min_rel_improvement": 0.01,   # < 1% relative objective gain counts as "no progress"
    "patience": 2,                 # consecutive no-progress iterations before converged
    "feasible_patience": 3,        # iterations allowed with no feasible incumbent
    "max_consecutive_failures": 3, # consecutive all-failed rounds before giving up
    "max_iterations": 20,          # hard iteration cap
    "max_evaluations": 200,        # hard total-candidate cap
}

# Verdict reason codes (all present in OPTIMIZATION_REASON_CODES; proposer_exhausted
# is added by this change).
RC_CONVERGED_DELTA = "converged_objective_delta"
RC_BUDGET = "budget_exhausted"
RC_NEEDS_INPUT = "needs_user_input"
RC_PROPOSER_EXHAUSTED = "proposer_exhausted"
RC_MAX_FAILURES = "max_consecutive_failures"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_convergence_config(study: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a study's optional ``convergence`` + ``budget`` blocks over defaults."""
    cfg = dict(_DEFAULTS)
    if isinstance(study, dict):
        conv = study.get("convergence")
        if isinstance(conv, dict):
            for k in ("min_rel_improvement", "patience", "feasible_patience",
                      "max_consecutive_failures"):
                if conv.get(k) is not None:
                    cfg[k] = conv[k]
        budget = study.get("budget")
        if isinstance(budget, dict):
            if budget.get("max_iterations") is not None:
                cfg["max_iterations"] = budget["max_iterations"]
            if budget.get("max_candidates") is not None:
                cfg["max_evaluations"] = budget["max_candidates"]
    return cfg


def evaluate_convergence(
    iterations: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    proposer_exhausted: bool = False,
) -> dict[str, Any]:
    """Pure convergence verdict over the iteration history.

    Each iteration record is expected to carry at least:
      ``index``, ``incumbent_objective`` (float|None), ``feasible`` (bool),
      ``evaluations_total`` (int), ``failures_this_round`` (int).

    Returns ``{converged, verdict, reason_codes, details}``. ``converged`` is True
    when any criterion fires. ``verdict`` is one of ``continue`` / ``converged`` /
    ``stop_budget`` / ``stop_no_progress`` / ``stop_no_feasible`` /
    ``stop_failures`` / ``stop_proposer_exhausted``.
    """
    cfg = {**_DEFAULTS, **(config or {})}
    reason_codes: list[str] = []
    details: dict[str, Any] = {}
    n = len(iterations)

    # ── proposer exhausted (caller signals it cannot suggest a new point) ────
    if proposer_exhausted:
        return {
            "converged": True, "verdict": "stop_proposer_exhausted",
            "reason_codes": [RC_PROPOSER_EXHAUSTED],
            "details": {"reason": "proposer reported no new candidate to try"},
            "iteration_count": n,
        }

    if n == 0:
        return {
            "converged": False, "verdict": "continue", "reason_codes": [],
            "details": {"reason": "no iterations recorded yet"}, "iteration_count": 0,
        }

    last = iterations[-1]

    # ── evaluation budget ────────────────────────────────────────────────────
    evals = int(_num(last.get("evaluations_total")) or 0)
    if evals >= cfg["max_evaluations"]:
        reason_codes.append(RC_BUDGET)
        details["evaluations_total"] = evals
        details["max_evaluations"] = cfg["max_evaluations"]

    # ── max iterations ───────────────────────────────────────────────────────
    if n >= cfg["max_iterations"]:
        if RC_BUDGET not in reason_codes:
            reason_codes.append(RC_BUDGET)
        details["iteration_count"] = n
        details["max_iterations"] = cfg["max_iterations"]

    # ── consecutive all-failed rounds ────────────────────────────────────────
    consec_fail = 0
    for it in reversed(iterations):
        if int(_num(it.get("failures_this_round")) or 0) > 0 and not it.get("had_success", True):
            consec_fail += 1
        else:
            break
    if consec_fail >= cfg["max_consecutive_failures"]:
        reason_codes.append(RC_MAX_FAILURES)
        details["consecutive_failures"] = consec_fail

    # ── no feasible progress ─────────────────────────────────────────────────
    feasible_indices = [i for i, it in enumerate(iterations) if it.get("feasible")]
    if not feasible_indices:
        if n >= cfg["feasible_patience"]:
            reason_codes.append(RC_NEEDS_INPUT)
            details["no_feasible_for"] = n
    else:
        # ── objective-delta stagnation (only meaningful with feasible incumbents) ─
        objs = [
            _num(it.get("incumbent_objective"))
            for it in iterations if it.get("feasible")
        ]
        objs = [o for o in objs if o is not None]
        patience = int(cfg["patience"])
        if len(objs) >= patience + 1:
            window = objs[-(patience + 1):]
            no_progress = True
            for prev, cur in zip(window, window[1:]):
                denom = abs(prev) if prev not in (0, None) else 1.0
                rel_gain = (prev - cur) / denom  # minimization: positive = improvement
                if rel_gain >= cfg["min_rel_improvement"]:
                    no_progress = False
                    break
            if no_progress:
                reason_codes.append(RC_CONVERGED_DELTA)
                details["objective_window"] = window
                details["min_rel_improvement"] = cfg["min_rel_improvement"]

    if not reason_codes:
        return {
            "converged": False, "verdict": "continue", "reason_codes": [],
            "details": details, "iteration_count": n,
        }

    # verdict precedence: explicit convergence > budget > no-feasible > failures
    if RC_CONVERGED_DELTA in reason_codes:
        verdict = "converged"
    elif RC_BUDGET in reason_codes:
        verdict = "stop_budget"
    elif RC_NEEDS_INPUT in reason_codes:
        verdict = "stop_no_feasible"
    else:
        verdict = "stop_failures"

    return {
        "converged": True, "verdict": verdict, "reason_codes": reason_codes,
        "details": details, "iteration_count": n,
    }


# ── package I/O: snapshot incumbent from ranking + evaluate ──────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:  # noqa: BLE001
            return None
    return None


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".optconv.tmp.aieng")
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


def _incumbent_objective(ranking: dict[str, Any]) -> tuple[str | None, float | None, bool]:
    """Return (incumbent_id, objective_value, feasible) from a ranking artifact."""
    best_id = ranking.get("best_candidate_id")
    candidates = [c for c in (ranking.get("candidates") or []) if isinstance(c, dict)]
    best = next((c for c in candidates if c.get("candidate_id") == best_id), None)
    if best is None:
        # no feasible incumbent — fall back to the top-ranked candidate for reporting
        best = candidates[0] if candidates else None
        feasible = False
    else:
        feasible = best.get("feasibility") == "feasible"
    if best is None:
        return None, None, False
    delta = best.get("objective_delta") if isinstance(best.get("objective_delta"), dict) else {}
    obj = _num(delta.get("candidate_value"))
    return best.get("candidate_id"), obj, feasible


def record_iteration_and_check(
    package_path: str | Path,
    *,
    evaluations_total: int | None = None,
    failures_this_round: int = 0,
    had_success: bool = True,
    proposer_exhausted: bool = False,
) -> dict[str, Any]:
    """Append an iteration snapshot from the current ranking, then evaluate convergence.

    Reads ``design_study_candidate_ranking.json`` for the incumbent, appends a
    record to ``optimization_iterations.json``, evaluates convergence over the
    accumulated history, and writes the artifact back. Returns the verdict plus
    the recorded iteration. Never modifies the baseline.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {"status": "error", "code": "package_not_found", "message": "package not found",
                "baseline_modified": False}

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            study = _read_json(zf, OPTIMIZATION_STUDY_PATH, names)
            history = _read_json(zf, OPTIMIZATION_ITERATIONS_PATH, names)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "read_failed",
                "message": f"{type(exc).__name__}: {exc}", "baseline_modified": False}

    if not isinstance(ranking, dict):
        return {
            "status": "needs_user_input", "code": "no_ranking",
            "message": "no ranking found — run opt.rank_candidates first",
            "baseline_modified": False,
        }

    iterations = (
        [r for r in (history.get("iterations") or []) if isinstance(r, dict)]
        if isinstance(history, dict) else []
    )
    incumbent_id, objective, feasible = _incumbent_objective(ranking)
    prev_evals = int(_num(iterations[-1].get("evaluations_total")) if iterations else 0) or 0
    n_candidates = len([c for c in (ranking.get("candidates") or []) if isinstance(c, dict)])
    evals_total = evaluations_total if evaluations_total is not None else n_candidates

    record = {
        "index": len(iterations) + 1,
        "incumbent_candidate_id": incumbent_id,
        "incumbent_objective": objective,
        "feasible": feasible,
        "evaluations_total": evals_total,
        "failures_this_round": failures_this_round,
        "had_success": had_success,
        "best_candidate_id": ranking.get("best_candidate_id"),
        "safe_to_accept": ranking.get("safe_to_accept"),
    }
    iterations.append(record)

    config = resolve_convergence_config(study)
    verdict = evaluate_convergence(iterations, config, proposer_exhausted=proposer_exhausted)
    record["convergence_verdict"] = verdict["verdict"]

    history_doc = {
        "format": OPTIMIZATION_ITERATIONS_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "iterations": iterations,
        "latest_verdict": verdict,
        "config_used": config,
        "provenance": {
            "created_by": "aieng.optimization_convergence",
            "baseline_modified": False,
            "autonomous_loop": False,
            "claim_advancement": "none",
        },
        "baseline_modified": False,
    }
    _replace_members(pkg, {OPTIMIZATION_ITERATIONS_PATH: _dumps(history_doc)})

    return {
        "status": "ok",
        "converged": verdict["converged"],
        "verdict": verdict["verdict"],
        "reason_codes": verdict["reason_codes"],
        "iteration_index": record["index"],
        "incumbent_candidate_id": incumbent_id,
        "incumbent_objective": objective,
        "feasible": feasible,
        "baseline_modified": False,
        "artifacts": [OPTIMIZATION_ITERATIONS_PATH],
    }
