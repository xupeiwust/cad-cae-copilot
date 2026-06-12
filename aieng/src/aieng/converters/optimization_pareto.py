"""Two-objective Pareto-front identification for design-study candidates.

Computes the non-dominated set of feasible, evaluated candidates and writes an
advisory ``analysis/pareto_front.json`` artifact.  This is deterministic,
budget-bounded front identification only — not a proven Pareto surface.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH

PARETO_FRONT_PATH = "analysis/pareto_front.json"

FEAS_FEASIBLE = "feasible"

STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_INSUFFICIENT_DATA = "insufficient_data"

FRONTIER_LIMITATION = (
    "Frontier is over evaluated candidates within budget, not a proven surface."
)

# Mirrors the mapping in design_study_ranking.py so that objective metrics such
# as "mass" resolve to concrete keys like "mass_kg" in candidate metrics.
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


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    """Atomic zip rewrite: preserve existing members, overwrite/add new ones."""
    tmp = package_path.with_suffix(".pareto.tmp.aieng")
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


def _normalize_for_dominance(
    values: list[float], objectives: list[dict[str, Any]]
) -> list[float]:
    """Convert every objective to a minimization direction.

    Minimize/reduce objectives keep their value; maximize/improve objectives are
    negated so that "lower is better" unifies dominance logic.
    """
    normalized: list[float] = []
    for value, obj in zip(values, objectives):
        sense = obj.get("sense", "minimize")
        if sense in ("maximize", "improve"):
            normalized.append(-value)
        else:
            normalized.append(value)
    return normalized


def _dominates(
    candidate_values: list[float],
    target_values: list[float],
    objectives: list[dict[str, Any]],
) -> bool:
    """Return True if candidate_values strictly dominate target_values."""
    cand = _normalize_for_dominance(candidate_values, objectives)
    targ = _normalize_for_dominance(target_values, objectives)
    strictly_better = False
    for c, t in zip(cand, targ):
        if c > t:
            return False
        if c < t:
            strictly_better = True
    return strictly_better


def _sort_key_for_front(
    item: dict[str, Any], objectives: list[dict[str, Any]]
) -> float:
    """Stable ordering for frontier display: objective-1 ascending."""
    value = item["values"][0]
    sense = objectives[0].get("sense", "minimize")
    return -value if sense in ("maximize", "improve") else value


def _empty_result(status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "objectives": [],
        "front": [],
        "dominated": [],
        "front_candidate_ids": [],
        "dominated_candidate_ids": [],
        "candidate_count": 0,
        "limitations": [reason, FRONTIER_LIMITATION],
    }


def compute_pareto_front(
    candidates: list[dict[str, Any]], objectives: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compute the non-dominated set over exactly two objectives.

    Parameters
    ----------
    candidates:
        Candidate data dicts as produced by the ranking path.  Each must contain
        ``candidate_id``, ``feasibility``, and ``metrics_used``.
    objectives:
        Objective dicts from the design-study problem.  Each should contain
        ``metric`` and optionally ``sense`` (default ``"minimize"``).

    Returns
    -------
    dict
        A result dict with ``status``, ``objectives``, ``front``,
        ``dominated``, ``front_candidate_ids``, ``dominated_candidate_ids``,
        ``candidate_count``, and ``limitations``.
    """
    if len(objectives) != 2:
        return _empty_result(
            STATUS_SKIPPED,
            "MVP supports exactly two objectives; Pareto front not computed.",
        )

    obj_defs: list[dict[str, Any]] = []
    for idx, obj in enumerate(objectives):
        if not isinstance(obj, dict):
            return _empty_result(
                STATUS_INSUFFICIENT_DATA,
                f"Objective at index {idx} is not a valid object.",
            )
        metric = obj.get("metric")
        if not metric:
            return _empty_result(
                STATUS_INSUFFICIENT_DATA,
                f"Objective at index {idx} has no metric.",
            )
        obj_defs.append({
            "id": obj.get("id") or f"objective_{idx + 1}",
            "metric": metric,
            "sense": obj.get("sense", "minimize"),
            "unit": obj.get("unit"),
        })

    eligible: list[dict[str, Any]] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        if cand.get("feasibility") != FEAS_FEASIBLE:
            continue
        metrics = cand.get("metrics_used") or {}
        values: list[float] = []
        usable = True
        for obj in obj_defs:
            keys = _objective_to_metric_keys(obj["metric"])
            raw = _get_metric(metrics, *keys)
            if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
                usable = False
                break
            values.append(float(raw))
        if not usable:
            continue
        eligible.append({
            "candidate_id": cand.get("candidate_id") or "unknown",
            "values": values,
        })

    if len(eligible) < 2:
        return _empty_result(
            STATUS_INSUFFICIENT_DATA,
            "At least two feasible candidates with both objective metrics are required.",
        )

    front_items: list[dict[str, Any]] = []
    dominated_ids: list[str] = []

    for idx, candidate in enumerate(eligible):
        dominated = False
        for jdx, other in enumerate(eligible):
            if idx == jdx:
                continue
            if _dominates(other["values"], candidate["values"], obj_defs):
                dominated = True
                break
        if dominated:
            dominated_ids.append(candidate["candidate_id"])
        else:
            front_items.append(candidate)

    # Deterministic ordering: primary objective, then candidate_id as a stable
    # tie-breaker.  dominated_ids are sorted for stable JSON output.
    front_items.sort(key=lambda item: (_sort_key_for_front(item, obj_defs), item["candidate_id"]))
    dominated_ids.sort()

    front: list[dict[str, Any]] = []
    for rank, item in enumerate(front_items, start=1):
        front.append({
            "candidate_id": item["candidate_id"],
            "rank": rank,
            "value_1": item["values"][0],
            "value_2": item["values"][1],
        })

    front_candidate_ids = [item["candidate_id"] for item in front]

    return {
        "status": STATUS_OK,
        "objectives": obj_defs,
        "front": front,
        "dominated": dominated_ids,
        "front_candidate_ids": front_candidate_ids,
        "dominated_candidate_ids": dominated_ids,
        "candidate_count": len(eligible),
        "limitations": [FRONTIER_LIMITATION],
    }


def _build_pareto_front_document(
    pareto_result: dict[str, Any],
    *,
    study_id: str | None = None,
    design_study_problem_ref: str = DESIGN_STUDY_PROBLEM_PATH,
    design_study_problem_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the analysis/pareto_front.json document."""
    doc: dict[str, Any] = {
        "format": "aieng.pareto_front",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "study_id": study_id or pareto_result.get("study_id"),
        "design_study_problem_ref": design_study_problem_ref,
        "objectives": pareto_result.get("objectives", []),
        "front": pareto_result.get("front", []),
        "dominated": pareto_result.get("dominated", []),
        "candidate_count": pareto_result.get("candidate_count", 0),
        "limitations": pareto_result.get("limitations", []),
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
        "provenance": {
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "created_by": "aieng.optimization_pareto",
            "claim_advancement": "none",
        },
    }
    if design_study_problem_id is not None or pareto_result.get("design_study_problem_id") is not None:
        doc["design_study_problem_id"] = design_study_problem_id or pareto_result.get("design_study_problem_id")
    return doc


def write_pareto_front_artifact(
    package_path: str | Path,
    pareto_result: dict[str, Any],
    *,
    study_id: str | None = None,
    design_study_problem_ref: str = DESIGN_STUDY_PROBLEM_PATH,
    design_study_problem_id: str | None = None,
) -> Path:
    """Write ``analysis/pareto_front.json`` into the ``.aieng`` package atomically.

    Parameters
    ----------
    package_path:
        Path to the ``.aieng`` ZIP package.
    pareto_result:
        Result dict returned by :func:`compute_pareto_front`.
    study_id:
        Optional study identifier; falls back to ``pareto_result["study_id"]``.
    design_study_problem_ref:
        Reference path to the design-study problem artifact.
    design_study_problem_id:
        Optional problem ``id``.

    Returns
    -------
    Path
        The package path.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        raise FileNotFoundError(f"package not found: {package_path}")

    if pareto_result.get("status") != STATUS_OK:
        raise ValueError(
            f"cannot write Pareto artifact with status {pareto_result.get('status')!r}"
        )
    if not isinstance(pareto_result.get("objectives"), list) or len(pareto_result["objectives"]) != 2:
        raise ValueError("Pareto artifact requires exactly two objectives")

    doc = _build_pareto_front_document(
        pareto_result,
        study_id=study_id,
        design_study_problem_ref=design_study_problem_ref,
        design_study_problem_id=design_study_problem_id,
    )
    _rewrite_package_members(package_path, {PARETO_FRONT_PATH: _dumps(doc)})
    return package_path
