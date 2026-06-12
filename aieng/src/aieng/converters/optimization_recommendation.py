"""Advisory recommendation / explanation over a candidate ranking (#41).

The ranking step (`rank_design_study_candidates`) already does the engineering
work: constraint filtering, weighted objective scoring, feasibility
classification, and `best_candidate_id` / `safe_to_accept` selection. This module
sits ON TOP of that artifact and turns it into a human-readable, reason-coded
recommendation — explaining *why* the top candidate is recommended (or why none
is), citing explicit metrics, and stating the caveats.

It is strictly advisory: it never accepts/promotes a candidate, never runs a
solver, never recompiles geometry, and never modifies the baseline. Acceptance
remains a separate, approval-gated step (#42). The recommendation is written to
`analysis/optimization_recommendation.json` for traceability.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

DESIGN_STUDY_CANDIDATE_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
DESIGN_STUDY_SCORING_REPORT_PATH = "diagnostics/design_study_scoring_report.json"
OPTIMIZATION_RECOMMENDATION_PATH = "analysis/optimization_recommendation.json"
OPTIMIZATION_RECOMMENDATION_FORMAT = "aieng.optimization_recommendation"

# Reason codes are drawn from the shared OPTIMIZATION_REASON_CODES vocabulary in
# aieng.optimization_artifacts; kept as literals here to avoid a hard import cycle
# but validated against that set by tests.
_RC_ADVISORY = "advisory_recommendation"
_RC_ADVISORY_TRADE_OFF_SET = "advisory_trade_off_set"
_RC_HUMAN_APPROVAL = "human_approval_required"
_RC_NEEDS_MORE = "needs_more_evaluation"
_RC_NEEDS_INPUT = "needs_user_input"
_RC_CONSTRAINT = "constraint_violation"
_RC_MISSING_METRIC = "missing_metric"
_RC_UNKNOWN_FEAS = "unknown_feasibility"


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
    tmp = package_path.with_suffix(".optreco.tmp.aieng")
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


def _has_pareto_frontier(ranking: dict[str, Any]) -> bool:
    """Return True when the ranking carries a usable multi-objective frontier."""
    if not isinstance(ranking, dict):
        return False
    pareto = ranking.get("pareto_front")
    if not isinstance(pareto, dict):
        return False
    if pareto.get("status") != "ok":
        return False
    front_ids = pareto.get("front_candidate_ids") or []
    return len(front_ids) >= 2


def _fmt_delta(objective_delta: dict[str, Any] | None) -> str | None:
    if not isinstance(objective_delta, dict):
        return None
    metric = objective_delta.get("metric")
    pct = objective_delta.get("delta_percent")
    base = objective_delta.get("baseline_value")
    cand = objective_delta.get("candidate_value")
    if metric is None or cand is None:
        return None
    if pct is not None:
        direction = "reduction" if pct > 0 else "increase"
        return f"{metric}: {base} → {cand} ({abs(pct):.1f}% {direction} vs baseline)"
    if base is not None:
        return f"{metric}: {base} → {cand} vs baseline"
    return f"{metric}: {cand} (no baseline to compare)"


def explain_recommendation(package_path: str | Path) -> dict[str, Any]:
    """Build an advisory recommendation from an existing candidate ranking.

    Reads ``analysis/design_study_candidate_ranking.json`` (and the scoring
    report when present), composes a reason-coded explanation, and writes
    ``analysis/optimization_recommendation.json``. Returns a summary dict.

    If no ranking artifact exists, returns ``status: "needs_user_input"`` asking
    the caller to run ranking first — it does not silently rank.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {"status": "error", "code": "package_not_found", "message": "package not found",
                "baseline_modified": False}

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            scoring = _read_json(zf, DESIGN_STUDY_SCORING_REPORT_PATH, names)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "read_failed",
                "message": f"{type(exc).__name__}: {exc}", "baseline_modified": False}

    if not isinstance(ranking, dict):
        return {
            "status": "needs_user_input",
            "code": "no_ranking",
            "message": (
                "no ranking found — run opt.rank_candidates "
                "(POST /api/projects/{id}/design-study/rank) first"
            ),
            "baseline_modified": False,
        }

    candidates = [c for c in (ranking.get("candidates") or []) if isinstance(c, dict)]
    best_id = ranking.get("best_candidate_id")
    safe_to_accept = bool(ranking.get("safe_to_accept"))
    next_action = ranking.get("next_action")
    objective = ranking.get("objective")
    constraints = ranking.get("constraints") or []

    # ── Pareto-aware advisory path (multi-objective) ────────────────────────
    if _has_pareto_frontier(ranking):
        pareto = ranking["pareto_front"]
        front_ids = list(pareto.get("front_candidate_ids") or [])
        front_rows = [r for r in (pareto.get("front") or []) if isinstance(r, dict)]
        n_front = len(front_ids)

        reason_codes: list[str] = [_RC_ADVISORY, _RC_ADVISORY_TRADE_OFF_SET, _RC_NEEDS_INPUT]
        rationale: list[str] = [
            f"{n_front} non-dominated candidates form an advisory trade-off set.",
            "No single global candidate is promoted because the study balances multiple objectives.",
        ]
        caveats: list[str] = [
            "Frontier is advisory and over evaluated candidates only; it is not a proven Pareto surface.",
            "Acceptance requires a human-chosen frontier point routed through the approval-gated accept step.",
        ]
        if isinstance(pareto.get("limitations"), list):
            caveats.extend(str(lim) for lim in pareto["limitations"])

        # Summarize each frontier point with its objective values.
        front_summary: list[dict[str, Any]] = [
            {
                "candidate_id": r.get("candidate_id"),
                "rank": r.get("rank"),
                "objective_values": r.get("objective_values") if isinstance(r.get("objective_values"), dict) else {},
            }
            for r in front_rows
        ]

        headline = (
            f"Multi-objective study: {n_front} non-dominated candidates form an advisory Pareto trade-off set."
        )

        # de-dup reason codes preserving order
        seen: set[str] = set()
        reason_codes = [rc for rc in reason_codes if not (rc in seen or seen.add(rc))]

        recommendation = {
            "format": OPTIMIZATION_RECOMMENDATION_FORMAT,
            "format_version": FORMAT_VERSION,
            "schema_version": "0.1",
            "status": "ok",
            "headline": headline,
            "recommended_candidate_id": None,
            "next_action": "request_user_input",
            "safe_to_accept": False,
            "advisory_only": True,
            "requires_human_review": True,
            "reason_codes": reason_codes,
            "rationale": rationale,
            "caveats": caveats,
            "recommended_candidate": None,
            "alternatives": front_summary,
            "pareto_front": {
                "status": pareto.get("status"),
                "objective_metrics": pareto.get("objective_metrics"),
                "front_candidate_ids": front_ids,
                "front": front_summary,
                "dominated_candidate_ids": list(pareto.get("dominated_candidate_ids") or []),
            },
            "feasibility_summary": {},
            "objective": objective,
            "constraints_considered": constraints,
            "honesty": {
                "production_sign_off": False,
                "baseline_modified": False,
                "solver_executed": False,
                "advisory_only": True,
            },
            "source_artifacts": [
                p for p in (DESIGN_STUDY_CANDIDATE_RANKING_PATH, DESIGN_STUDY_SCORING_REPORT_PATH)
                if (p == DESIGN_STUDY_CANDIDATE_RANKING_PATH) or isinstance(scoring, dict)
            ],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

        _replace_members(pkg, {OPTIMIZATION_RECOMMENDATION_PATH: _dumps(recommendation)})

        return {
            "status": "ok",
            "recommended_candidate_id": None,
            "next_action": "request_user_input",
            "safe_to_accept": False,
            "headline": headline,
            "reason_codes": reason_codes,
            "advisory_only": True,
            "requires_human_review": True,
            "baseline_modified": False,
            "artifacts": [OPTIMIZATION_RECOMMENDATION_PATH],
        }

    # ── Single-objective advisory path ──────────────────────────────────────
    best = next((c for c in candidates if c.get("candidate_id") == best_id), None)
    reason_codes = [_RC_ADVISORY]
    rationale = []
    caveats = []

    # ── headline + rationale ────────────────────────────────────────────────
    if best is not None:
        delta_str = _fmt_delta(best.get("objective_delta"))
        headline = (
            f"Recommend candidate {best_id} (rank {best.get('rank')}, "
            f"{best.get('feasibility')}, confidence {best.get('confidence')})."
        )
        if delta_str:
            rationale.append(f"Top-ranked feasible candidate — {delta_str}.")
        else:
            rationale.append("Top-ranked feasible candidate.")
        metrics_used = best.get("metrics_used") or {}
        if metrics_used:
            shown = ", ".join(f"{k}={v}" for k, v in sorted(metrics_used.items()))
            rationale.append(f"Metrics: {shown}.")
        for r in best.get("reasons") or []:
            rationale.append(str(r))
        if best.get("constraint_violations"):
            reason_codes.append(_RC_CONSTRAINT)
            rationale.append(
                "Constraint issues: " + "; ".join(str(v) for v in best["constraint_violations"]) + "."
            )
    else:
        headline = "No candidate is recommended for acceptance yet."
        rationale.append(
            "No feasible, improving candidate with sufficient confidence was found."
        )
        # explain why, from the scoring report when available
        if isinstance(scoring, dict):
            for reason in scoring.get("reasons_for_no_best_candidate") or []:
                rationale.append(str(reason))

    # ── next-action → reason codes ──────────────────────────────────────────
    if next_action == "accept_candidate":
        reason_codes.append(_RC_HUMAN_APPROVAL)
        rationale.append(
            "Eligible to accept, but acceptance is human-approval-gated (opt.accept_candidate)."
        )
    elif next_action == "run_more_evaluation":
        reason_codes.append(_RC_NEEDS_MORE)
        rationale.append("Recommend more evaluation before accepting (low confidence or unknowns).")
    elif next_action in ("propose_refinement",):
        reason_codes.append(_RC_NEEDS_MORE)
        rationale.append("Recommend proposing refined candidates — best so far does not improve the objective.")
    elif next_action in ("no_viable_candidate", "request_user_input"):
        reason_codes.append(_RC_NEEDS_INPUT)

    # ── caveats from the candidate set / scoring report ─────────────────────
    feas_counts: dict[str, int] = {}
    any_missing = False
    for c in candidates:
        feas_counts[c.get("feasibility")] = feas_counts.get(c.get("feasibility"), 0) + 1
        if c.get("feasibility") == "unknown":
            any_missing = True
    if feas_counts.get("unknown"):
        any_missing = True
    if isinstance(scoring, dict) and scoring.get("metrics_missing_summary"):
        any_missing = True
    if any_missing:
        reason_codes.append(_RC_MISSING_METRIC)
        caveats.append(
            "Some candidates have missing CAE metrics; their feasibility is unknown, not assumed."
        )
    if best is not None and best.get("confidence") != "high":
        caveats.append("Recommended candidate is not high-confidence; treat as provisional.")
    if best is not None and best.get("feasibility") == "unknown":
        reason_codes.append(_RC_UNKNOWN_FEAS)
    if not candidates:
        caveats.append("No ranked candidates were found.")

    # de-dup reason codes preserving order
    seen = set()
    reason_codes = [rc for rc in reason_codes if not (rc in seen or seen.add(rc))]

    alternatives = [
        {
            "candidate_id": c.get("candidate_id"),
            "rank": c.get("rank"),
            "score": c.get("score"),
            "feasibility": c.get("feasibility"),
            "confidence": c.get("confidence"),
        }
        for c in candidates
        if c.get("candidate_id") != best_id
    ][:5]

    recommendation = {
        "format": OPTIMIZATION_RECOMMENDATION_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": "ok",
        "headline": headline,
        "recommended_candidate_id": best_id,
        "next_action": next_action,
        "safe_to_accept": safe_to_accept,
        "advisory_only": True,
        "requires_human_review": True,
        "reason_codes": reason_codes,
        "rationale": rationale,
        "caveats": caveats,
        "recommended_candidate": best,
        "alternatives": alternatives,
        "feasibility_summary": feas_counts,
        "objective": objective,
        "constraints_considered": constraints,
        "honesty": {
            "production_sign_off": False,
            "baseline_modified": False,
            "solver_executed": False,
            "advisory_only": True,
        },
        "source_artifacts": [
            p for p in (DESIGN_STUDY_CANDIDATE_RANKING_PATH, DESIGN_STUDY_SCORING_REPORT_PATH)
            if (p == DESIGN_STUDY_CANDIDATE_RANKING_PATH) or isinstance(scoring, dict)
        ],
        "baseline_modified": False,
        "claim_advancement": "none",
    }

    _replace_members(pkg, {OPTIMIZATION_RECOMMENDATION_PATH: _dumps(recommendation)})

    return {
        "status": "ok",
        "recommended_candidate_id": best_id,
        "next_action": next_action,
        "safe_to_accept": safe_to_accept,
        "headline": headline,
        "reason_codes": reason_codes,
        "advisory_only": True,
        "requires_human_review": True,
        "baseline_modified": False,
        "artifacts": [OPTIMIZATION_RECOMMENDATION_PATH],
    }
