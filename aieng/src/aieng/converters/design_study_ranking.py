"""Design study candidate RANKING and COMPARISON v0 (PR3).

Reads already-executed design-study candidates, classifies feasibility,
scores them against the problem objective and constraints, and produces
a conservative ranking with honest diagnostics.

Hard safety contract (same as PR1/PR2):
  - Baseline geometry is NEVER overwritten.
  - No candidate is auto-promoted into the baseline.
  - No new candidates are executed, no geometry recompiled, no CAE run.
  - Ranking is advisory only — not engineering certification.
  - Missing metrics produce low-confidence / needs_more_evaluation outcomes.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.design_study_evaluation import evaluate_design_study_candidate
from aieng.converters.design_study_execution import (
    CANDIDATE_WORKSPACE_ROOT,
    DESIGN_STUDY_ITERATIONS_PATH,
    DESIGN_STUDY_REPORT_PATH,
)
from aieng.converters.optimization_pareto import (
    PARETO_FRONT_PATH,
    compute_pareto_front,
    write_pareto_front_artifact,
)

DESIGN_STUDY_CANDIDATE_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
DESIGN_STUDY_SCORING_REPORT_PATH = "diagnostics/design_study_scoring_report.json"

# feasibility classifications
FEAS_FEASIBLE = "feasible"
FEAS_INFEASIBLE = "infeasible"
FEAS_UNKNOWN = "unknown"
FEAS_FAILED = "failed"

# confidence levels
CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"

# recommendations
REC_ACCEPT = "accept_candidate"
REC_REJECT = "reject_candidate"
REC_NEEDS_MORE = "needs_more_evaluation"
REC_REFINE = "refine_candidate"
REC_REQUEST_INPUT = "request_user_input"

# next actions
NEXT_ACCEPT = "accept_candidate"
NEXT_RUN_MORE = "run_more_evaluation"
NEXT_PROPOSE_REFINEMENT = "propose_refinement"
NEXT_REQUEST_INPUT = "request_user_input"
NEXT_NO_VIABLE = "no_viable_candidate"


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def _sanitize_cid(candidate_id: str) -> str:
    """Sanitize candidate id for path construction."""
    return candidate_id.replace("..", "").strip("/")


# ── metric extraction ─────────────────────────────────────────────────────────

_OBJECTIVE_METRIC_KEYS: dict[str, list[str]] = {
    "mass": ["mass_kg", "mass", "total_mass"],
    "volume": ["volume_mm3", "volume", "total_volume"],
    "stress": ["max_stress", "von_mises_max", "stress_max"],
    "deflection": ["max_deflection", "displacement_max", "deflection_max"],
    "safety_factor": ["min_safety_factor", "safety_factor_min"],
}


def _objective_to_metric_keys(objective_metric: str) -> list[str]:
    return _OBJECTIVE_METRIC_KEYS.get(objective_metric, [objective_metric])


def _get_metric(metrics: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in metrics:
            return metrics[k]
    return None


def _extract_metrics(
    iteration: dict[str, Any],
    evaluation: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    verification: dict[str, Any] | None,
) -> dict[str, Any]:
    """Gather metrics from all available candidate artifacts."""
    metrics: dict[str, Any] = {}
    sources: list[str] = []

    # 1. iteration metrics (from execution)
    iter_metrics = iteration.get("metrics")
    if isinstance(iter_metrics, dict) and iter_metrics:
        for k, v in iter_metrics.items():
            if v is not None:
                metrics[k] = v
        sources.append("iteration.metrics")

    # 2. evaluation metrics.  Prefer candidate-local evaluation.json because it
    # is the only place that can preserve source paths, load-case ids, units and
    # constraint evidence.  It may be legacy flat metrics or the normalized v0
    # shape produced by design_study_evaluation.
    if evaluation:
        ev_metrics = evaluation.get("metrics")
        if isinstance(ev_metrics, dict) and ev_metrics:
            for k, v in ev_metrics.items():
                if isinstance(v, dict) and "value" in v:
                    metrics[k] = v.get("value")
                elif v is not None:
                    metrics[k] = v
            sources.append("evaluation.json")
        ev_norm = evaluation.get("normalized_metrics")
        if isinstance(ev_norm, dict):
            canonical_to_flat = {
                "mass": "mass_kg",
                "volume": "volume_mm3",
                "max_stress": "max_stress",
                "max_deflection": "max_deflection",
                "min_safety_factor": "min_safety_factor",
                "compliance": "compliance",
                "stiffness": "stiffness",
            }
            for canonical, entry in ev_norm.items():
                if not isinstance(entry, dict):
                    continue
                key = canonical_to_flat.get(canonical, canonical)
                if entry.get("value") is not None:
                    metrics[key] = entry.get("value")
                if entry.get("proxy_derived"):
                    metrics["proxy_derived"] = True
            if ev_norm and "evaluation.json" not in sources:
                sources.append("evaluation.json")
        if evaluation.get("confidence"):
            metrics["evaluation_confidence"] = evaluation.get("confidence")
        if evaluation.get("evaluation_status"):
            metrics["evaluation_status"] = evaluation.get("evaluation_status")
        if evaluation.get("feasibility"):
            metrics["evaluation_feasibility"] = evaluation.get("feasibility")

    # 3. manifest metrics (geometry execution)
    if manifest:
        for key in ("volume_mm3", "mass_kg", "surface_area_mm2", "bounding_box_mm"):
            val = manifest.get(key)
            if val is not None:
                metrics[key] = val
        if any(k in manifest for k in ("volume_mm3", "mass_kg", "geometry_kind")):
            sources.append("geometry_execution_manifest.json")

    # 4. verification status
    if verification:
        vstatus = verification.get("status")
        if vstatus:
            metrics["verification_status"] = vstatus

    return {"metrics": metrics, "sources": sources}


def _has_critical_metrics(problem: dict[str, Any] | None,
                          metrics: dict[str, Any]) -> bool:
    """Check if we have metrics for the objective."""
    if not problem:
        return False
    objective = problem.get("objective")
    if not isinstance(objective, dict):
        return False
    metric = objective.get("metric")
    if not metric:
        return False
    metric_keys = _objective_to_metric_keys(metric)
    return any(k in metrics and metrics[k] is not None for k in metric_keys)


def _find_missing_metrics(problem: dict[str, Any] | None,
                          metrics: dict[str, Any]) -> list[str]:
    """List metrics needed but not available."""
    missing: set[str] = set()
    if not problem:
        return []

    objective = problem.get("objective")
    if isinstance(objective, dict):
        metric = objective.get("metric")
        if metric:
            keys = _objective_to_metric_keys(metric)
            if not any(k in metrics and metrics[k] is not None for k in keys):
                missing.add(metric)

    constraints = problem.get("constraints") or []
    for c in constraints:
        if not isinstance(c, dict):
            continue
        ctype = c.get("type")
        if ctype == "max_stress" and _get_metric(metrics, "max_stress", "von_mises_max", "stress_max") is None:
            missing.add("max_stress")
        elif ctype == "max_deflection" and _get_metric(metrics, "max_deflection", "displacement_max", "deflection_max") is None:
            missing.add("max_deflection")
        elif ctype == "min_safety_factor" and _get_metric(metrics, "min_safety_factor", "safety_factor_min") is None:
            missing.add("min_safety_factor")
        elif ctype == "mass_limit" and _get_metric(metrics, "mass_kg", "mass", "total_mass") is None:
            missing.add("mass")
        elif ctype == "volume_limit" and _get_metric(metrics, "volume_mm3", "volume", "total_volume") is None:
            missing.add("volume")

    return sorted(missing)


# ── feasibility classification ────────────────────────────────────────────────

def _eval_simple_expr(expr: str, metrics: dict[str, Any]) -> str | None:
    """Very limited expression evaluator for constraint expressions."""
    expr = expr.strip()
    for op_str, op_func in (
        (">=", lambda a, b: a >= b),
        ("<=", lambda a, b: a <= b),
        (">", lambda a, b: a > b),
        ("<", lambda a, b: a < b),
        ("==", lambda a, b: a == b),
    ):
        if op_str in expr:
            parts = expr.split(op_str, 1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                left_val = metrics.get(left)
                if left_val is None:
                    return None  # can't evaluate — not a violation
                try:
                    right_val = float(right)
                except ValueError:
                    return None
                if not op_func(left_val, right_val):
                    return f"{left}={left_val} violates {expr}"
                return None
    return None


def _check_single_constraint(constraint: dict[str, Any],
                             metrics: dict[str, Any]) -> str | None:
    """Check one constraint. Returns violation string or None."""
    ctype = constraint.get("type")
    expr = constraint.get("expr")

    # Direct metric-based constraints
    if ctype == "max_stress":
        limit = constraint.get("limit")
        actual = _get_metric(metrics, "max_stress", "von_mises_max", "stress_max")
        if limit is not None and actual is not None and actual > limit:
            return f"max_stress {actual} > limit {limit}"
    elif ctype == "max_deflection":
        limit = constraint.get("limit")
        actual = _get_metric(metrics, "max_deflection", "displacement_max", "deflection_max")
        if limit is not None and actual is not None and actual > limit:
            return f"max_deflection {actual} > limit {limit}"
    elif ctype == "min_safety_factor":
        limit = constraint.get("limit")
        actual = _get_metric(metrics, "min_safety_factor", "safety_factor_min")
        if limit is not None and actual is not None and actual < limit:
            return f"min_safety_factor {actual} < limit {limit}"
    elif ctype == "mass_limit":
        limit = constraint.get("limit")
        actual = _get_metric(metrics, "mass_kg", "mass", "total_mass")
        if limit is not None and actual is not None and actual > limit:
            return f"mass {actual} > limit {limit}"
    elif ctype == "volume_limit":
        limit = constraint.get("limit")
        actual = _get_metric(metrics, "volume_mm3", "volume", "total_volume")
        if limit is not None and actual is not None and actual > limit:
            return f"volume {actual} > limit {limit}"
    elif ctype == "preserve_interface":
        preserved = constraint.get("preserved", True)
        actual = metrics.get("interfaces_preserved")
        if actual is not None and not actual and preserved:
            return "interface not preserved"

    # Try to parse simple expr like "wall_t >= 2.5"
    if isinstance(expr, str):
        return _eval_simple_expr(expr, metrics)

    return None


def _evaluate_constraints(constraints: list[Any],
                          metrics: dict[str, Any]) -> list[str]:
    """Evaluate constraints against metrics. Returns list of violation strings."""
    violations: list[str] = []
    if not isinstance(constraints, list):
        return violations

    for c in constraints:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or "unnamed"
        violation = _check_single_constraint(c, metrics)
        if violation:
            violations.append(f"{cid}: {violation}")

    return violations


def _classify_feasibility(
    iteration: dict[str, Any],
    problem: dict[str, Any] | None,
    metrics: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Return (feasibility, reasons, warnings)."""
    reasons: list[str] = []
    warnings: list[str] = []

    exec_status = iteration.get("execution_status")
    validation_status = iteration.get("validation_status")

    # Rule 1-3: failed validation / compile_failed / rejected -> failed
    if validation_status == "rejected" or exec_status == "rejected":
        reasons.append("candidate was rejected during validation")
        return FEAS_FAILED, reasons, warnings
    if exec_status == "compile_failed":
        reasons.append("candidate compile failed")
        return FEAS_FAILED, reasons, warnings
    if exec_status == "failed":
        reasons.append("candidate execution failed")
        return FEAS_FAILED, reasons, warnings

    # Rule 4: metrics missing -> unknown
    if not metrics:
        reasons.append("no metrics available for feasibility assessment")
        return FEAS_UNKNOWN, reasons, warnings

    # Rule 5-7: evaluate constraints
    constraints = problem.get("constraints") if problem else []
    violations = _evaluate_constraints(constraints, metrics)

    if violations:
        reasons.extend(violations)
        return FEAS_INFEASIBLE, reasons, warnings

    # Check for partial metrics (objective-related)
    has_critical = _has_critical_metrics(problem, metrics)
    if not has_critical:
        warnings.append("partial metrics — feasibility assessed with low confidence")
        return FEAS_UNKNOWN, reasons, warnings

    reasons.append("constraints satisfied and required metrics present")
    return FEAS_FEASIBLE, reasons, warnings


# ── scoring ───────────────────────────────────────────────────────────────────

def _proxy_penalty(metrics: dict[str, Any]) -> float:
    """Penalize if metrics appear proxy-only or partial."""
    penalty = 0.0
    non_trivial = [k for k in metrics if k not in (
        "executed", "geometry_kind", "representation_kind", "artifacts",
        "evaluation_status", "evaluation_confidence", "evaluation_feasibility",
    )]
    if metrics.get("proxy_derived") is True:
        penalty += 0.2
    if not non_trivial:
        penalty += 0.5
    elif len(non_trivial) < 2:
        penalty += 0.2
    if metrics.get("verification_status") not in (None, "passed", "ok"):
        penalty += 0.3
    return penalty


def _compute_objective_score(
    obj_metric: str,
    obj_sense: str,
    candidate_val: float,
    baseline_val: float | None,
    metrics: dict[str, Any],
    problem: dict[str, Any],
) -> tuple[float, str]:
    """Compute a deterministic score for the objective."""
    if baseline_val is not None and baseline_val != 0:
        ratio = candidate_val / abs(baseline_val)
    else:
        ratio = None

    lower_is_better = (
        obj_sense in ("minimize", "reduce")
        or obj_metric in ("mass", "volume", "stress", "deflection")
    )
    higher_is_better = (
        obj_sense in ("maximize", "improve")
        or obj_metric in ("safety_factor",)
    )

    if lower_is_better:
        if ratio is not None:
            score = 1.0 - ratio  # improvement > 0, regression < 0
        else:
            score = 0.0
    elif higher_is_better:
        if ratio is not None:
            score = ratio - 1.0
        else:
            score = 0.0
    else:
        score = 0.0

    # Confidence based on data quality
    if baseline_val is not None and _has_critical_metrics(problem, metrics):
        confidence = CONF_HIGH
    elif _has_critical_metrics(problem, metrics):
        confidence = CONF_MEDIUM
    else:
        confidence = CONF_LOW

    return score, confidence


def _score_balanced(
    metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
) -> tuple[float, str, list[str]]:
    """Score a balanced objective using multiple metrics deterministically."""
    reasons: list[str] = []
    sub_metrics = ["mass", "volume", "stress", "deflection", "safety_factor"]
    scores: list[float] = []

    for sm in sub_metrics:
        keys = _objective_to_metric_keys(sm)
        cval = _get_metric(metrics, *keys)
        bval = _get_metric(baseline_metrics, *keys)
        if cval is not None and bval is not None and bval != 0:
            ratio = cval / abs(bval)
            if sm in ("mass", "volume", "stress", "deflection"):
                sub_score = 1.0 - ratio  # lower is better
            else:
                sub_score = ratio - 1.0  # higher is better
            scores.append(sub_score)
            reasons.append(f"balanced sub-metric {sm}: {sub_score:+.4f}")
        elif cval is not None:
            reasons.append(f"balanced sub-metric {sm}: no baseline, skipped")
        else:
            reasons.append(f"balanced sub-metric {sm}: missing, skipped")

    if scores:
        avg = sum(scores) / len(scores)
        confidence = CONF_MEDIUM if len(scores) >= 3 else CONF_LOW
        return round(avg, 6), confidence, reasons

    return 0.0, CONF_LOW, reasons + ["no balanced sub-metrics available"]


def _score_candidate(
    iteration: dict[str, Any],
    problem: dict[str, Any] | None,
    metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    feasibility: str,
) -> tuple[float, str, dict[str, Any], list[str]]:
    """Return (score, confidence, objective_delta, reasons)."""
    reasons: list[str] = []

    # Failed/infeasible candidates get penalized scores
    if feasibility == FEAS_FAILED:
        return -1.0, CONF_LOW, {}, ["candidate failed — lowest possible score"]
    if feasibility == FEAS_INFEASIBLE:
        return -0.5, CONF_LOW, {}, ["candidate infeasible — penalized score"]
    if feasibility == FEAS_UNKNOWN:
        return 0.0, CONF_LOW, {}, ["insufficient metrics — neutral score with low confidence"]

    # Feasible candidate — score based on objective improvement
    if not problem:
        return 0.0, CONF_LOW, {}, ["no problem definition — cannot score"]

    objective = problem.get("objective")
    if not isinstance(objective, dict):
        return 0.0, CONF_LOW, {}, ["no objective defined — cannot score"]

    obj_metric = objective.get("metric")
    obj_sense = objective.get("sense", "minimize")

    if not obj_metric:
        return 0.0, CONF_LOW, {}, ["objective metric not specified — cannot score"]

    # Balanced objective
    if obj_metric == "balanced" or obj_sense == "balanced":
        score, confidence, balanced_reasons = _score_balanced(metrics, baseline_metrics)
        delta: dict[str, Any] = {"metric": "balanced", "candidate_value": None, "baseline_value": None}
        proxy_penalty = _proxy_penalty(metrics)
        if proxy_penalty > 0:
            score = max(-1.0, score - proxy_penalty)
            balanced_reasons.append(f"proxy/partial evidence penalty: -{proxy_penalty}")
        return round(score, 6), confidence, delta, balanced_reasons

    metric_keys = _objective_to_metric_keys(obj_metric)
    candidate_val = _get_metric(metrics, *metric_keys)

    if candidate_val is None:
        return 0.0, CONF_LOW, {}, [f"objective metric {obj_metric} not available — cannot score"]

    baseline_val = _get_metric(baseline_metrics, *metric_keys)

    # Compute delta
    delta = {
        "metric": obj_metric,
        "candidate_value": candidate_val,
        "baseline_value": baseline_val,
    }
    if baseline_val is not None and baseline_val != 0:
        delta_pct = (candidate_val - baseline_val) / abs(baseline_val) * 100
        delta["delta_percent"] = round(delta_pct, 4)
        delta["delta_absolute"] = round(candidate_val - baseline_val, 6)
    else:
        delta_pct = None
        delta["delta_percent"] = None
        delta["delta_absolute"] = round(candidate_val - baseline_val, 6) if baseline_val is not None else None

    score, confidence = _compute_objective_score(
        obj_metric, obj_sense, candidate_val, baseline_val, metrics, problem
    )

    if delta_pct is not None:
        reasons.append(f"objective {obj_metric}: {delta_pct:+.2f}% vs baseline")
    else:
        reasons.append(f"objective {obj_metric}: candidate={candidate_val}, no baseline")

    # Penalize proxy/partial evidence
    proxy_penalty = _proxy_penalty(metrics)
    if proxy_penalty > 0:
        score = max(-1.0, score - proxy_penalty)
        reasons.append(f"proxy/partial evidence penalty: -{proxy_penalty}")
    if metrics.get("evaluation_confidence") == CONF_LOW:
        confidence = CONF_LOW
    elif metrics.get("evaluation_confidence") == CONF_MEDIUM and confidence == CONF_HIGH:
        confidence = CONF_MEDIUM

    return round(score, 6), confidence, delta, reasons


def _determine_recommendation(feasibility: str, confidence: str,
                              score: float, metrics: dict[str, Any]) -> str:
    if feasibility == FEAS_FAILED:
        return REC_REJECT
    if feasibility == FEAS_INFEASIBLE:
        return REC_REJECT
    if feasibility == FEAS_UNKNOWN:
        return REC_NEEDS_MORE
    if feasibility == FEAS_FEASIBLE:
        if confidence == CONF_HIGH and score > 0:
            return REC_ACCEPT
        if score > 0:
            return REC_REFINE
        return REC_NEEDS_MORE
    return REC_REQUEST_INPUT


# ── ranking assembly ──────────────────────────────────────────────────────────

def _get_baseline_metrics(problem: dict[str, Any] | None,
                          _iterations: list[dict[str, Any]]) -> dict[str, Any]:
    """Try to find baseline metrics from the problem."""
    baseline: dict[str, Any] = {}
    if problem:
        pm = problem.get("baseline_metrics")
        if isinstance(pm, dict):
            baseline.update(pm)
    return baseline


def _build_ranking(
    problem: dict[str, Any] | None,
    candidates_data: list[dict[str, Any]],
    baseline_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build the ranking artifact."""
    if not candidates_data:
        return {
            "format": "aieng.design_study.candidate_ranking.v0",
            "format_version": FORMAT_VERSION,
            "schema_version": "0.1",
            "status": "insufficient_data",
            "problem_id": problem.get("id") if problem else None,
            "objective": problem.get("objective") if problem else None,
            "constraints": problem.get("constraints") if problem else [],
            "baseline_metrics": baseline_metrics,
            "candidates": [],
            "best_candidate_id": None,
            "safe_to_accept": False,
            "next_action": NEXT_REQUEST_INPUT,
            "limitations": [
                "No executed candidates found — cannot rank.",
                "Run candidates via execute_design_study_candidate first.",
            ],
        }

    # Sort by score descending (penalized scores sink to bottom)
    sorted_candidates = sorted(candidates_data, key=lambda c: c["score"], reverse=True)

    ranked = []
    for rank, cand in enumerate(sorted_candidates, start=1):
        ranked.append({
            "rank": rank,
            "candidate_id": cand["candidate_id"],
            "feasibility": cand["feasibility"],
            "score": cand["score"],
            "confidence": cand["confidence"],
            "recommendation": cand["recommendation"],
            "metrics_used": cand["metrics_used"],
            "constraint_violations": cand["constraint_violations"],
            "objective_delta": cand["objective_delta"],
            "reasons": cand["reasons"],
        })

    # Determine best candidate
    best_id = None
    safe_to_accept = False
    next_action = NEXT_NO_VIABLE

    feasible_candidates = [c for c in ranked if c["feasibility"] == FEAS_FEASIBLE]

    if feasible_candidates:
        best = feasible_candidates[0]
        best_id = best["candidate_id"]
        if best["confidence"] == CONF_HIGH and best["score"] > 0:
            safe_to_accept = True
            next_action = NEXT_ACCEPT
        elif best["score"] > 0:
            next_action = NEXT_RUN_MORE
        else:
            next_action = NEXT_PROPOSE_REFINEMENT
    else:
        unknown_candidates = [c for c in ranked if c["feasibility"] == FEAS_UNKNOWN]
        if unknown_candidates:
            next_action = NEXT_RUN_MORE
        else:
            next_action = NEXT_NO_VIABLE

    limitations = [
        "Ranking is advisory — not engineering certification.",
        "Missing metrics produce low-confidence recommendations.",
        "No Pareto optimization or search is performed.",
    ]
    if not baseline_metrics:
        limitations.append("Baseline metrics unavailable — deltas are incomplete.")

    return {
        "format": "aieng.design_study.candidate_ranking.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": "ranked",
        "problem_id": problem.get("id") if problem else None,
        "objective": problem.get("objective") if problem else None,
        "constraints": problem.get("constraints") if problem else [],
        "baseline_metrics": baseline_metrics,
        "candidates": ranked,
        "best_candidate_id": best_id,
        "safe_to_accept": safe_to_accept,
        "next_action": next_action,
        "limitations": limitations,
    }


def _build_scoring_report(
    ranking: dict[str, Any],
    candidates_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the scoring diagnostics report."""
    feasible = [c for c in candidates_data if c["feasibility"] == FEAS_FEASIBLE]
    infeasible = [c for c in candidates_data if c["feasibility"] == FEAS_INFEASIBLE]
    unknown = [c for c in candidates_data if c["feasibility"] == FEAS_UNKNOWN]
    failed = [c for c in candidates_data if c["feasibility"] == FEAS_FAILED]

    conf_dist = {
        CONF_HIGH: len([c for c in candidates_data if c["confidence"] == CONF_HIGH]),
        CONF_MEDIUM: len([c for c in candidates_data if c["confidence"] == CONF_MEDIUM]),
        CONF_LOW: len([c for c in candidates_data if c["confidence"] == CONF_LOW]),
    }

    missing_summary: dict[str, list[str]] = {}
    for c in candidates_data:
        for m in c.get("metrics_missing") or []:
            missing_summary.setdefault(m, []).append(c["candidate_id"])

    constraint_summary = {
        "candidates_evaluated": len(candidates_data),
        "violations_found": len(infeasible),
        "violation_details": [
            {"candidate_id": c["candidate_id"], "violations": c["constraint_violations"]}
            for c in infeasible
        ],
    }

    reasons_no_best: list[str] = []
    if not feasible:
        reasons_no_best.append("No feasible candidates found.")
    elif not any(c["confidence"] == CONF_HIGH for c in feasible):
        reasons_no_best.append("No feasible candidate has high-confidence metrics.")
    elif not any(c["score"] > 0 for c in feasible):
        reasons_no_best.append("No feasible candidate improves over baseline.")

    return {
        "format": "aieng.design_study_scoring_report",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "candidates_loaded": len(candidates_data),
        "candidates_ranked": len([c for c in candidates_data if c["score"] is not None]),
        "candidates_failed": len(failed),
        "candidates_unknown": len(unknown),
        "metrics_missing_summary": missing_summary,
        "constraint_evaluation_summary": constraint_summary,
        "objective_evaluation_summary": {
            "objective": ranking.get("objective"),
            "candidates_with_baseline_comparison": len([
                c for c in candidates_data
                if c.get("objective_delta", {}).get("baseline_value") is not None
            ]),
        },
        "confidence_distribution": conf_dist,
        "reasons_for_no_best_candidate": reasons_no_best,
        "source_artifact_paths": [
            DESIGN_STUDY_PROBLEM_PATH,
            DESIGN_STUDY_ITERATIONS_PATH,
            DESIGN_STUDY_REPORT_PATH,
        ],
        "warnings": ranking.get("limitations", []),
        "errors": [],
        "provenance": {
            "created_by": "aieng.design_study_ranking",
            "baseline_modified": False,
            "candidates_executed": False,
        },
    }


# ── package I/O ───────────────────────────────────────────────────────────────

def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".dsrank.tmp.aieng")
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


# ── main entry ────────────────────────────────────────────────────────────────

def rank_design_study_candidates(package_path: str | Path) -> dict[str, Any]:
    """Rank already-executed design-study candidates.

    Reads the problem, iterations, and per-candidate evaluation artifacts,
    classifies feasibility, scores against the objective, and writes:
      - analysis/design_study_candidate_ranking.json
      - diagnostics/design_study_scoring_report.json

    Does NOT execute new candidates, does NOT recompile geometry, does NOT
    run CAE, and does NOT modify baseline geometry.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "failed", "reason": "package not found"}

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            if not isinstance(problem, dict):
                problem = None
            iterations_doc = _read_json(zf, DESIGN_STUDY_ITERATIONS_PATH, names)
            if not isinstance(iterations_doc, dict):
                iterations_doc = None
            iterations = [i for i in (iterations_doc.get("iterations") or [])
                          if isinstance(i, dict)] if iterations_doc else []

            # Pre-load per-candidate artifacts.  Ranking may build or refresh
            # candidate-local evaluation artifacts from existing evidence, but
            # it still never executes candidates, recompiles geometry, or runs
            # CAE/solver tools.
            candidate_artifacts: dict[str, dict[str, Any]] = {}
            for it in iterations:
                cid = it.get("candidate_id") or "unknown"
                sid = _sanitize_cid(cid)
                ev = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{sid}/analysis/evaluation.json", names)
                mf = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{sid}/provenance/geometry_execution_manifest.json", names)
                vr = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{sid}/diagnostics/verification.json", names)
                candidate_artifacts[cid] = {
                    "evaluation": ev if isinstance(ev, dict) else None,
                    "manifest": mf if isinstance(mf, dict) else None,
                    "verification": vr if isinstance(vr, dict) else None,
                }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    if problem is None:
        return {
            "status": "insufficient_data",
            "reason": "analysis/design_study_problem.json not found",
            "design_study_present": False,
        }

    if not iterations:
        ranking = _build_ranking(problem, [], {})
        report = _build_scoring_report(ranking, [])
        members = {
            DESIGN_STUDY_CANDIDATE_RANKING_PATH: _dumps(ranking),
            DESIGN_STUDY_SCORING_REPORT_PATH: _dumps(report),
        }
        _rewrite_package_members(package_path, members)
        return {
            "status": "insufficient_data",
            "reason": "no executed candidates found",
            "design_study_present": True,
            "artifacts": [DESIGN_STUDY_CANDIDATE_RANKING_PATH, DESIGN_STUDY_SCORING_REPORT_PATH],
        }

    baseline_metrics = _get_baseline_metrics(problem, iterations)
    candidates_data: list[dict[str, Any]] = []
    evaluation_artifacts: list[str] = []

    # Build/refresh candidate-local normalized evaluation artifacts when a
    # workspace exists.  This consumes only local static/neutral/proxy evidence.
    for it in iterations:
        if it.get("validation_status") == "rejected" or it.get("execution_status") == "rejected":
            continue
        res = evaluate_design_study_candidate(package_path, it.get("candidate_id") or "unknown")
        if isinstance(res, dict) and res.get("artifacts"):
            evaluation_artifacts.extend([a for a in res["artifacts"] if a not in evaluation_artifacts])

    # Re-read candidate artifacts after optional evaluation refresh.
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            for it in iterations:
                cid = it.get("candidate_id") or "unknown"
                sid = _sanitize_cid(cid)
                ev = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{sid}/analysis/evaluation.json", names)
                mf = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{sid}/provenance/geometry_execution_manifest.json", names)
                vr = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{sid}/diagnostics/verification.json", names)
                candidate_artifacts[cid] = {
                    "evaluation": ev if isinstance(ev, dict) else None,
                    "manifest": mf if isinstance(mf, dict) else None,
                    "verification": vr if isinstance(vr, dict) else None,
                }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    for it in iterations:
        cid = it.get("candidate_id") or "unknown"
        artifacts = candidate_artifacts.get(cid) or {}
        extracted = _extract_metrics(
            it,
            artifacts.get("evaluation"),
            artifacts.get("manifest"),
            artifacts.get("verification"),
        )
        metrics = extracted["metrics"]

        feasibility, feas_reasons, feas_warnings = _classify_feasibility(it, problem, metrics)
        score, confidence, delta, score_reasons = _score_candidate(
            it, problem, metrics, baseline_metrics, feasibility
        )
        recommendation = _determine_recommendation(feasibility, confidence, score, metrics)
        metrics_used = {k: v for k, v in metrics.items() if v is not None}
        metrics_missing = _find_missing_metrics(problem, metrics)
        constraint_violations = _evaluate_constraints(
            problem.get("constraints") if problem else [], metrics
        )

        all_reasons = list(feas_reasons) + list(score_reasons) + list(feas_warnings)

        candidates_data.append({
            "candidate_id": cid,
            "iteration_id": it.get("iteration_id"),
            "feasibility": feasibility,
            "score": score,
            "confidence": confidence,
            "recommendation": recommendation,
            "metrics_used": metrics_used,
            "metrics_missing": metrics_missing,
            "constraint_violations": constraint_violations,
            "objective_delta": delta,
            "reasons": all_reasons,
            "execution_status": it.get("execution_status"),
            "validation_status": it.get("validation_status"),
        })

    objectives = problem.get("objectives") if isinstance(problem.get("objectives"), list) else []
    pareto_result = None
    pareto_artifact_path: str | None = None
    if len(objectives) == 2:
        pareto_result = compute_pareto_front(candidates_data, objectives)

    ranking = _build_ranking(problem, candidates_data, baseline_metrics)
    if pareto_result is not None:
        ranking["pareto_front"] = {
            "status": pareto_result["status"],
            "front_candidate_ids": pareto_result["front_candidate_ids"],
            "dominated_candidate_ids": pareto_result["dominated_candidate_ids"],
            "objective_metrics": [obj["metric"] for obj in pareto_result["objectives"]],
            "limitations": pareto_result["limitations"],
        }
        if pareto_result["status"] == "ok":
            # Replace the generic single-objective limitation with the honest frontier text.
            ranking["limitations"] = [
                "Pareto front is computed advisory-only over evaluated feasible candidates; it is not a proven surface."
                if "No Pareto optimization or search is performed" in lim
                else lim
                for lim in ranking["limitations"]
            ]
            if not any("not a proven surface" in lim for lim in ranking["limitations"]):
                ranking["limitations"].append(
                    "Pareto front is computed advisory-only over evaluated feasible candidates; it is not a proven surface."
                )
        else:
            # Preserve the original single-objective limitations when the frontier
            # could not be computed; the embedded block carries the status/reason.
            pass

    report = _build_scoring_report(ranking, candidates_data)

    members = {
        DESIGN_STUDY_CANDIDATE_RANKING_PATH: _dumps(ranking),
        DESIGN_STUDY_SCORING_REPORT_PATH: _dumps(report),
    }
    _rewrite_package_members(package_path, members)

    if pareto_result is not None and pareto_result["status"] == "ok":
        write_pareto_front_artifact(
            package_path,
            pareto_result,
            study_id=problem.get("id"),
            design_study_problem_ref=DESIGN_STUDY_PROBLEM_PATH,
            design_study_problem_id=problem.get("id"),
        )
        pareto_artifact_path = PARETO_FRONT_PATH

    artifacts = [DESIGN_STUDY_CANDIDATE_RANKING_PATH, DESIGN_STUDY_SCORING_REPORT_PATH] + evaluation_artifacts
    if pareto_artifact_path:
        artifacts.append(pareto_artifact_path)

    return {
        "status": "ok",
        "design_study_present": True,
        "candidate_count": len(candidates_data),
        "best_candidate_id": ranking["best_candidate_id"],
        "safe_to_accept": ranking["safe_to_accept"],
        "next_action": ranking["next_action"],
        "artifacts": artifacts,
    }
