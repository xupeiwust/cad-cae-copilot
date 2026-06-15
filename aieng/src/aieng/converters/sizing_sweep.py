"""Parametric sizing sweep — rank dimension variants by real static FEA metrics.

This is the *brain* of the optimize→verify loop closure for static analysis: given
the per-variant results of sweeping ONE editable dimension (each variant solved with
the real static solver), it ranks the variants against an objective
(minimize mass / displacement / stress) subject to a stress (and optional
displacement) constraint, and recommends the best feasible value.

Honesty boundary (the whole point):
- A variant earns ``executed_solver_result`` credibility ONLY when its
  ``solver_executed`` flag is true; an unsolved/failed variant is ``unverified``
  and can never be recommended as if it were verified.
- ``safe_to_apply`` is true only when the recommended variant is feasible AND
  actually solved. The baseline geometry is never modified here — acceptance flows
  through the existing approval-gated ``cad.edit_parameter``.
- Mass is a geometric quantity supplied by the caller; stress/displacement come
  from the solver. No proxy/surrogate substitution.

Pure and dependency-free (imports only the shared credibility classifier) so both
the ``aieng`` core and the ``aieng-ui`` backend can use it.
"""
from __future__ import annotations

from typing import Any

from .credibility import classify_credibility

# Objective → the metric key it minimizes.
_OBJECTIVE_METRIC: dict[str, str] = {
    "min_mass": "mass",
    "min_displacement": "max_displacement",
    "min_stress": "max_von_mises_stress",
}

# Per-variant status vocabulary.
STATUS_FEASIBLE = "feasible"      # solved, objective known, all constraints satisfied
STATUS_INFEASIBLE = "infeasible"  # solved but a constraint is violated
STATUS_UNKNOWN = "unknown"        # solved but a needed metric is missing (never a false pass)
STATUS_ERROR = "error"            # variant did not solve / errored


def extract_static_metrics(computed_metrics: dict[str, Any] | None) -> dict[str, float | None]:
    """Pull worst-case static scalars out of a ``computed_metrics.json`` payload.

    Reads ``max_von_mises_stress`` / ``max_displacement`` from ``global_metrics``
    and every ``load_cases[].metrics`` block, returning the worst (max) of each
    across load cases. Robust to either ``{"value": x}`` or bare-scalar entries;
    a metric absent everywhere comes back ``None`` (never fabricated).
    """
    out: dict[str, float | None] = {"max_von_mises_stress": None, "max_displacement": None}
    if not isinstance(computed_metrics, dict):
        return out

    def _scalar(entry: Any) -> float | None:
        if isinstance(entry, dict):
            entry = entry.get("value")
        if isinstance(entry, (int, float)) and not isinstance(entry, bool):
            return float(entry)
        return None

    blocks: list[dict[str, Any]] = []
    if isinstance(computed_metrics.get("global_metrics"), dict):
        blocks.append(computed_metrics["global_metrics"])
    for case in computed_metrics.get("load_cases") or []:
        if isinstance(case, dict) and isinstance(case.get("metrics"), dict):
            blocks.append(case["metrics"])

    for key in out:
        worst: float | None = None
        for block in blocks:
            val = _scalar(block.get(key))
            if val is not None and (worst is None or val > worst):
                worst = val
        out[key] = worst
    return out


def _evaluate_variant(
    variant: dict[str, Any],
    *,
    objective_metric: str,
    allowable_stress: float | None,
    displacement_limit: float | None,
) -> dict[str, Any]:
    """Classify ONE variant: status + reason + credibility stamp (does not rank)."""
    value = variant.get("value")
    metrics = variant.get("metrics") if isinstance(variant.get("metrics"), dict) else {}
    solver_executed = bool(variant.get("solver_executed"))
    error = variant.get("error")

    credibility = classify_credibility("solver", solver_executed=solver_executed)

    entry: dict[str, Any] = {
        "value": value,
        "metrics": metrics,
        "solver_executed": solver_executed,
        "credibility": credibility,
    }

    if error or not solver_executed:
        entry["status"] = STATUS_ERROR
        entry["reason"] = str(error) if error else "variant did not solve"
        return entry

    stress = metrics.get("max_von_mises_stress")
    disp = metrics.get("max_displacement")
    objective_value = metrics.get(objective_metric)

    # A missing metric needed for the objective or a constraint → unknown, never
    # a silent pass.
    missing: list[str] = []
    if objective_value is None:
        missing.append(objective_metric)
    if allowable_stress is not None and stress is None:
        missing.append("max_von_mises_stress")
    if displacement_limit is not None and disp is None:
        missing.append("max_displacement")
    if missing:
        entry["status"] = STATUS_UNKNOWN
        entry["reason"] = f"missing metric(s): {', '.join(sorted(set(missing)))}"
        return entry

    violations: list[str] = []
    if allowable_stress is not None and stress > allowable_stress:
        violations.append(
            f"max_von_mises_stress {stress:g} > allowable {allowable_stress:g}"
        )
    if displacement_limit is not None and disp > displacement_limit:
        violations.append(
            f"max_displacement {disp:g} > limit {displacement_limit:g}"
        )

    if violations:
        entry["status"] = STATUS_INFEASIBLE
        entry["reason"] = "; ".join(violations)
    else:
        entry["status"] = STATUS_FEASIBLE
        entry["reason"] = "all constraints satisfied"
    entry["objective_value"] = objective_value
    return entry


def rank_sizing_sweep(
    variants: list[dict[str, Any]],
    *,
    objective: str = "min_mass",
    stress_limit: float | None = None,
    safety_factor: float = 1.0,
    displacement_limit: float | None = None,
    parameter_name: str | None = None,
) -> dict[str, Any]:
    """Rank swept dimension variants by a static-FEA objective + constraints.

    Args:
        variants: one dict per swept value — ``{value, metrics, solver_executed, [error]}``
            where ``metrics`` carries scalar ``max_von_mises_stress`` / ``max_displacement``
            / ``mass`` (any may be missing).
        objective: ``min_mass`` (default) / ``min_displacement`` / ``min_stress``.
        stress_limit: allowable stress numerator (e.g. material yield). The
            effective allowable is ``stress_limit / safety_factor``.
        safety_factor: divides ``stress_limit`` to set the allowable (default 1.0).
        displacement_limit: optional max-displacement constraint.
        parameter_name: the swept parameter's name, echoed into the report.

    Returns:
        A self-describing report: ranked variants (feasible-known first, by
        objective ascending), ``feasible_count``, ``recommended`` value, an honest
        ``credibility`` stamp, and ``safe_to_apply`` (true only when the
        recommendation is feasible AND solver-verified). Never mutates anything.
    """
    objective = objective if objective in _OBJECTIVE_METRIC else "min_mass"
    objective_metric = _OBJECTIVE_METRIC[objective]
    sf = safety_factor if isinstance(safety_factor, (int, float)) and safety_factor > 0 else 1.0
    allowable_stress = (stress_limit / sf) if isinstance(stress_limit, (int, float)) else None

    evaluated = [
        _evaluate_variant(
            v,
            objective_metric=objective_metric,
            allowable_stress=allowable_stress,
            displacement_limit=displacement_limit,
        )
        for v in variants
    ]

    # Stable ordering: feasible (by objective asc) → infeasible → unknown → error.
    status_order = {STATUS_FEASIBLE: 0, STATUS_INFEASIBLE: 1, STATUS_UNKNOWN: 2, STATUS_ERROR: 3}

    def _sort_key(e: dict[str, Any]) -> tuple[int, float]:
        primary = status_order.get(e["status"], 4)
        obj = e.get("objective_value")
        return (primary, obj if isinstance(obj, (int, float)) else float("inf"))

    ranked = sorted(evaluated, key=_sort_key)
    for i, e in enumerate(ranked):
        e["rank"] = i + 1

    feasible = [e for e in ranked if e["status"] == STATUS_FEASIBLE]
    recommended = feasible[0] if feasible else None
    all_solved = bool(evaluated) and all(e["solver_executed"] for e in evaluated)

    if recommended is not None:
        recommendation_reason = (
            f"value={recommended['value']} minimizes {objective} "
            f"({objective_metric}={recommended.get('objective_value')}) among "
            f"{len(feasible)} feasible variant(s)"
        )
        safe_to_apply = recommended["solver_executed"]
    elif not evaluated:
        recommendation_reason = "no variants supplied"
        safe_to_apply = False
    elif any(e["status"] in (STATUS_INFEASIBLE, STATUS_FEASIBLE) for e in evaluated):
        recommendation_reason = (
            "no feasible variant — every solved variant violates the constraint; "
            "widen the sweep range, relax the constraint, or change material"
        )
        safe_to_apply = False
    else:
        recommendation_reason = (
            "no variant could be evaluated (unsolved or missing metrics); "
            "results are unverified"
        )
        safe_to_apply = False

    # Overall credibility: executed only when every variant actually solved.
    overall_credibility = classify_credibility(
        "solver",
        solver_executed=all_solved,
        notes=None if all_solved else "one or more variants did not produce solver metrics",
    )

    return {
        "objective": objective,
        "objective_metric": objective_metric,
        "parameter_name": parameter_name,
        "constraint": {
            "stress_limit": stress_limit,
            "safety_factor": sf,
            "allowable_stress": allowable_stress,
            "displacement_limit": displacement_limit,
        },
        "variants": ranked,
        "variant_count": len(ranked),
        "feasible_count": len(feasible),
        "recommended": recommended,
        "recommendation_reason": recommendation_reason,
        "safe_to_apply": safe_to_apply,
        "credibility": overall_credibility,
        "honesty": {
            "solver_executed_all": all_solved,
            "baseline_modified": False,
            "production_ready": False,
        },
    }
