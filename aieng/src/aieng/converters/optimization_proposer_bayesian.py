"""Bayesian optimisation proposer for the iterative loop (Issue #66).

An ask/tell shim around ``scikit-optimize`` that builds a GP surrogate from
evaluated candidates and proposes the next point by maximising Expected
Improvement (EI).  When scikit-optimize is unavailable, or when there are not
enough observations, it falls back to whole-domain Latin hypercube sampling.

Stateless — all state lives in the .aieng package (ranking, patches, evaluations).
Baseline is never modified.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from .optimization_sampler import _filter_safe_variables, latin_hypercube_sample
from .optimization_proposer import (
    DESIGN_CANDIDATES_DIR,
    OPTIMIZATION_VARIABLES_PATH,
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    OPTIMIZATION_ITERATIONS_PATH,
    _read_json,
    _dumps,
    _replace_members,
    _num,
    _incumbent_variable_values,
)


def _has_skopt() -> bool:
    try:
        import skopt  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _read_all_patches(zf: zipfile.ZipFile, names: set[str]) -> dict[str, dict[str, Any]]:
    """Read every candidate patch in the package."""
    patches: dict[str, dict[str, Any]] = {}
    for n in names:
        if n.startswith(DESIGN_CANDIDATES_DIR) and n.endswith(".json"):
            cid = n[len(DESIGN_CANDIDATES_DIR) : -len(".json")]
            patch = _read_json(zf, n, names)
            if isinstance(patch, dict):
                patches[cid] = patch
    return patches


def _evaluated_points(
    patches: dict[str, dict[str, Any]],
    ranking: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Map candidate_id -> {values: {vid: float}, score: float|None, feasible: bool}."""
    scores: dict[str, float | None] = {}
    feasible: dict[str, bool] = {}
    if isinstance(ranking, dict):
        for c in ranking.get("candidates") or []:
            if isinstance(c, dict):
                cid = c.get("candidate_id")
                if cid is not None:
                    scores[cid] = c.get("score")
                    feasible[cid] = c.get("feasibility") == "feasible"
    evaluated: dict[str, dict[str, Any]] = {}
    for cid, patch in patches.items():
        vals: dict[str, float | None] = {}
        for ch in patch.get("variable_changes") or []:
            if isinstance(ch, dict) and ch.get("variable_id") is not None:
                vals[ch["variable_id"]] = _num(ch.get("new_value"))
        evaluated[cid] = {
            "values": vals,
            "score": scores.get(cid),
            "feasible": feasible.get(cid, False),
        }
    return evaluated


def _safe_var_bounds(safe_vars: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Return skopt-compatible dimension bounds."""
    bounds: list[tuple[float, float]] = []
    for var in safe_vars:
        lo = _num(var.get("min_value"))
        hi = _num(var.get("max_value"))
        if lo is None or hi is None:
            lo, hi = 0.0, 1.0
        bounds.append((float(lo), float(hi)))
    return bounds


def _values_to_vector(
    values: dict[str, float | None],
    safe_vars: list[dict[str, Any]],
) -> list[float] | None:
    """Convert a {vid: value} map to a list ordered by safe_vars."""
    vec: list[float] = []
    for var in safe_vars:
        v = _num(values.get(var["id"]))
        if v is None:
            return None
        vec.append(float(v))
    return vec


def _vector_to_values(
    vec: list[float],
    safe_vars: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert a vector back to {vid: value}, rounding integers."""
    out: dict[str, Any] = {}
    for val, var in zip(vec, safe_vars):
        if var.get("type") == "integer":
            out[var["id"]] = int(round(float(val)))
        else:
            out[var["id"]] = round(float(val), 6)
    return out


def _all_continuous_or_integer(safe_vars: list[dict[str, Any]]) -> bool:
    return all(var.get("type") in ("continuous", "integer") for var in safe_vars)


def propose_bayesian_candidates(
    package_path: str | Path,
    *,
    count: int = 1,
    seed: int = 0,
) -> dict[str, Any]:
    """Propose the next candidate(s) using Bayesian optimisation.

    Parameters
    ----------
    package_path:
        Path to the .aieng package.
    count:
        Number of candidates to propose.
    seed:
        Random seed for skopt and LHS fallback.

    Returns
    -------
    Summary dict with keys ``status``, ``strategy``, ``candidate_ids``,
    ``baseline_modified``, etc.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {
            "status": "error",
            "code": "package_not_found",
            "message": "package not found",
            "baseline_modified": False,
        }
    if count < 1:
        return {
            "status": "error",
            "code": "bad_input",
            "message": "count must be >= 1",
            "baseline_modified": False,
        }

    # ── scikit-optimize availability check ───────────────────────────────────
    if not _has_skopt():
        try:
            with zipfile.ZipFile(pkg, "r") as zf:
                names = set(zf.namelist())
                variables_doc = _read_json(zf, OPTIMIZATION_VARIABLES_PATH, names)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "code": "read_failed",
                "message": f"{type(exc).__name__}: {exc}",
                "baseline_modified": False,
            }
        if not isinstance(variables_doc, dict):
            return {
                "status": "error",
                "code": "missing_variables",
                "message": f"{OPTIMIZATION_VARIABLES_PATH} not found",
                "baseline_modified": False,
            }
        safe_vars = _filter_safe_variables(variables_doc.get("variables") or [])
        if not safe_vars:
            return {
                "status": "error",
                "code": "no_variables",
                "message": "no safe-to-modify variables",
                "baseline_modified": False,
            }
        candidates = latin_hypercube_sample(safe_vars, count=count, seed=seed)
        if not candidates:
            return {
                "status": "error",
                "code": "proposer_exhausted",
                "message": "proposer produced no candidates",
                "proposer_exhausted": True,
                "baseline_modified": False,
            }
        members = {f"{DESIGN_CANDIDATES_DIR}{c['candidate_id']}.json": _dumps(c) for c in candidates}
        _replace_members(pkg, members)
        return {
            "status": "ok",
            "strategy": "lhs_fallback",
            "reason_codes": ["no_surrogate_available"],
            "candidate_ids": [c["candidate_id"] for c in candidates],
            "candidate_count": len(candidates),
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

    # ── Read package contents ────────────────────────────────────────────────
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            variables_doc = _read_json(zf, OPTIMIZATION_VARIABLES_PATH, names)
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            history = _read_json(zf, OPTIMIZATION_ITERATIONS_PATH, names)
            patches = _read_all_patches(zf, names)
            incumbent_id = ranking.get("best_candidate_id") if isinstance(ranking, dict) else None
            incumbent_values = _incumbent_variable_values(zf, names, incumbent_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "code": "read_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "baseline_modified": False,
        }

    if not isinstance(variables_doc, dict):
        return {
            "status": "error",
            "code": "missing_variables",
            "message": f"{OPTIMIZATION_VARIABLES_PATH} not found",
            "baseline_modified": False,
        }
    safe_vars = _filter_safe_variables(variables_doc.get("variables") or [])
    if not safe_vars:
        return {
            "status": "error",
            "code": "no_variables",
            "message": "no safe-to-modify variables to refine",
            "baseline_modified": False,
        }

    iteration = len(history.get("iterations") or []) if isinstance(history, dict) else 0
    reason_codes: list[str] = ["select_bayesian"]

    # ── no feasible incumbent → whole-domain LHS fallback ────────────────────
    if not incumbent_id or not incumbent_values:
        reason_codes.append("no_incumbent_fallback")
        candidates = latin_hypercube_sample(safe_vars, count=count, seed=seed)
        if not candidates:
            return {
                "status": "error",
                "code": "proposer_exhausted",
                "message": "proposer produced no candidates",
                "proposer_exhausted": True,
                "baseline_modified": False,
            }
        members = {f"{DESIGN_CANDIDATES_DIR}{c['candidate_id']}.json": _dumps(c) for c in candidates}
        _replace_members(pkg, members)
        return {
            "status": "ok",
            "strategy": "lhs_fallback",
            "iteration": iteration + 1,
            "reason_codes": reason_codes,
            "candidate_ids": [c["candidate_id"] for c in candidates],
            "candidate_count": len(candidates),
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

    # ── discrete variables → fallback (skopt works best on continuous spaces) ─
    if not _all_continuous_or_integer(safe_vars):
        reason_codes.append("no_surrogate_available")
        candidates = latin_hypercube_sample(safe_vars, count=count, seed=seed)
        if not candidates:
            return {
                "status": "error",
                "code": "proposer_exhausted",
                "message": "proposer produced no candidates",
                "proposer_exhausted": True,
                "baseline_modified": False,
            }
        members = {f"{DESIGN_CANDIDATES_DIR}{c['candidate_id']}.json": _dumps(c) for c in candidates}
        _replace_members(pkg, members)
        return {
            "status": "ok",
            "strategy": "lhs_fallback",
            "iteration": iteration + 1,
            "reason_codes": reason_codes,
            "candidate_ids": [c["candidate_id"] for c in candidates],
            "candidate_count": len(candidates),
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

    evaluated = _evaluated_points(patches, ranking)

    # Build training data for skopt
    X_train: list[list[float]] = []
    y_train: list[float] = []
    for cid, data in evaluated.items():
        score = data.get("score")
        if score is None:
            continue
        vec = _values_to_vector(data["values"], safe_vars)
        if vec is None:
            continue
        X_train.append(vec)
        y_train.append(float(score))

    # Need at least a few observations to fit a GP
    if len(y_train) < 3:
        reason_codes.append("no_surrogate_available")
        candidates = latin_hypercube_sample(safe_vars, count=count, seed=seed)
        if not candidates:
            return {
                "status": "error",
                "code": "proposer_exhausted",
                "message": "proposer produced no candidates",
                "proposer_exhausted": True,
                "baseline_modified": False,
            }
        members = {f"{DESIGN_CANDIDATES_DIR}{c['candidate_id']}.json": _dumps(c) for c in candidates}
        _replace_members(pkg, members)
        return {
            "status": "ok",
            "strategy": "lhs_fallback",
            "iteration": iteration + 1,
            "reason_codes": reason_codes,
            "candidate_ids": [c["candidate_id"] for c in candidates],
            "candidate_count": len(candidates),
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

    # ── Bayesian optimisation via scikit-optimize ───────────────────────────
    import numpy as np
    from skopt import Optimizer

    dims = _safe_var_bounds(safe_vars)
    optimizer = Optimizer(
        dimensions=dims,
        base_estimator="gp",
        acq_func="EI",
        random_state=seed,
        n_initial_points=0,
    )

    # skopt always minimises; our scores are already oriented so that
    # higher = better (positive score = improvement over baseline).
    # Therefore we minimise -score to maximise improvement.
    y_minimize = [-y for y in y_train]
    for x, y in zip(X_train, y_minimize):
        optimizer.tell(x, y)

    candidates: list[dict[str, Any]] = []
    for i in range(count):
        x_next = optimizer.ask()
        # Ensure we get a plain list of floats
        if isinstance(x_next, (list, tuple, np.ndarray)):
            x_next = [float(v) for v in x_next]
        else:
            x_next = [float(x_next)]

        vals = _vector_to_values(x_next, safe_vars)
        changes = [{"variable_id": vid, "new_value": v} for vid, v in vals.items()]
        candidates.append({
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_bayes{iteration + 1}_{i:03d}",
            "variable_changes": changes,
            "reasoning": (
                f"Bayesian optimisation proposal (iteration {iteration + 1}, "
                f"GP-EI acquisition, seed {seed})."
            ),
        })
        # Tell the optimizer a dummy conservative value so the next ask is different
        optimizer.tell(x_next, min(y_minimize))

    members = {f"{DESIGN_CANDIDATES_DIR}{c['candidate_id']}.json": _dumps(c) for c in candidates}
    _replace_members(pkg, members)
    return {
        "status": "ok",
        "strategy": "bayesian",
        "iteration": iteration + 1,
        "incumbent_candidate_id": incumbent_id,
        "reason_codes": reason_codes,
        "candidate_ids": [c["candidate_id"] for c in candidates],
        "candidate_count": len(candidates),
        "baseline_modified": False,
        "claim_advancement": "none",
        "artifacts": list(members.keys()),
    }
