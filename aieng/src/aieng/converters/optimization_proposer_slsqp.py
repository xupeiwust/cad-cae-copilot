"""SLSQP optimizer proposer for the iterative loop (#65).

An ask/tell shim around ``scipy.optimize.minimize(method="SLSQP")`` that builds a
local quadratic model from evaluated candidates and proposes the next point via
finite-difference gradients.  When gradients are missing it emits FD-perturbation
candidates; when complete it runs one SLSQP step.  Falls back to whole-domain LHS
when SciPy is unavailable or there is no feasible incumbent.

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

_BLANKET_REASON_CODES = frozenset(
    {
        "select_slsqp",
        "select_bayesian",
        "select_genetic",
        "no_surrogate_available",
    }
)


def _has_scipy() -> bool:
    try:
        import scipy.optimize  # noqa: F401
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
    """Map candidate_id -> {values: {vid: float}, score: float|None}."""
    scores: dict[str, float | None] = {}
    if isinstance(ranking, dict):
        for c in ranking.get("candidates") or []:
            if isinstance(c, dict):
                scores[c.get("candidate_id")] = c.get("score")
    evaluated: dict[str, dict[str, Any]] = {}
    for cid, patch in patches.items():
        vals: dict[str, float | None] = {}
        for ch in patch.get("variable_changes") or []:
            if isinstance(ch, dict) and ch.get("variable_id") is not None:
                vals[ch["variable_id"]] = _num(ch.get("new_value"))
        evaluated[cid] = {"values": vals, "score": scores.get(cid)}
    return evaluated


def _fd_perturbation_value(
    var: dict[str, Any],
    center: float | None,
    fd_frac: float,
    direction: int,
) -> float | None:
    """Return a perturbed value for finite-differencing, clamped to bounds."""
    if center is None:
        return None
    lo = _num(var.get("min_value"))
    hi = _num(var.get("max_value"))
    if lo is None or hi is None or hi <= lo:
        return None
    dx = max(fd_frac * (hi - lo), 1e-6)
    raw = center + direction * dx
    raw = max(lo, min(hi, raw))
    if var.get("type") == "integer":
        return int(round(raw))
    return round(raw, 6)


def _compute_gradient_fd(
    incumbent_values: dict[str, Any],
    safe_vars: list[dict[str, Any]],
    evaluated: dict[str, dict[str, Any]],
    fd_frac: float,
) -> tuple[dict[str, float | None], list[str]]:
    """Compute central/one-sided FD gradients.  Returns (gradient, missing_vids)."""
    gradient: dict[str, float | None] = {}
    missing: list[str] = []
    inc_score = None
    for cid, data in evaluated.items():
        if cid == "incumbent":
            continue
        # We don't use a special incumbent key; the caller passes incumbent_id separately.
        pass

    for var in safe_vars:
        vid = var["id"]
        x0 = _num(incumbent_values.get(vid))
        if x0 is None:
            gradient[vid] = None
            missing.append(vid)
            continue
        lo = _num(var.get("min_value"))
        hi = _num(var.get("max_value"))
        if lo is None or hi is None or hi <= lo:
            gradient[vid] = None
            missing.append(vid)
            continue
        dx = max(fd_frac * (hi - lo), 1e-6)

        f_score: float | None = None
        b_score: float | None = None
        for _cid, data in evaluated.items():
            if data.get("score") is None:
                continue
            xv = _num(data["values"].get(vid))
            if xv is None:
                continue
            # All other variables must match the incumbent
            match = True
            for v2 in safe_vars:
                v2id = v2["id"]
                if v2id == vid:
                    continue
                xv2 = _num(data["values"].get(v2id))
                x02 = _num(incumbent_values.get(v2id))
                if xv2 is None or x02 is None:
                    match = False
                    break
                if abs(xv2 - x02) > 1e-6:
                    match = False
                    break
            if not match:
                continue
            if abs(xv - (x0 + dx)) < 1e-6:
                f_score = data["score"]
            if abs(xv - (x0 - dx)) < 1e-6:
                b_score = data["score"]

        if f_score is not None and b_score is not None:
            gradient[vid] = (f_score - b_score) / (2 * dx)
        elif f_score is not None:
            inc_score = next(
                (d["score"] for d in evaluated.values() if d.get("score") is not None),
                None,
            )
            if inc_score is not None:
                gradient[vid] = (f_score - inc_score) / dx
            else:
                gradient[vid] = None
                missing.append(vid)
        elif b_score is not None:
            inc_score = next(
                (d["score"] for d in evaluated.values() if d.get("score") is not None),
                None,
            )
            if inc_score is not None:
                gradient[vid] = (inc_score - b_score) / dx
            else:
                gradient[vid] = None
                missing.append(vid)
        else:
            gradient[vid] = None
            missing.append(vid)
    return gradient, missing


def _slsqp_next_point(
    incumbent_values: dict[str, Any],
    safe_vars: list[dict[str, Any]],
    gradient: dict[str, float | None],
) -> list[float]:
    """Run one SLSQP step on the local quadratic model and return raw coordinates."""
    import numpy as np
    from scipy.optimize import minimize

    var_ids = [v["id"] for v in safe_vars]
    x0_arr = np.array([_num(incumbent_values.get(vid)) or 0.0 for vid in var_ids], dtype=float)
    g_arr = np.array([gradient.get(vid) or 0.0 for vid in var_ids], dtype=float)

    bounds = []
    for var in safe_vars:
        lo = _num(var.get("min_value"))
        hi = _num(var.get("max_value"))
        bounds.append((lo, hi))

    def local_obj(x: np.ndarray) -> float:
        dx = x - x0_arr
        # Maximize local quadratic model  -> minimize its negative
        return -(float(np.dot(g_arr, dx)) + 0.5 * float(np.dot(dx, dx)))

    def local_jac(x: np.ndarray) -> np.ndarray:
        dx = x - x0_arr
        return -(g_arr + dx)

    result = minimize(
        local_obj,
        x0_arr,
        method="SLSQP",
        jac=local_jac,
        bounds=bounds,
        options={"maxiter": 1, "ftol": 1e-6},
    )
    return [float(v) for v in result.x]


def propose_slsqp_candidates(
    package_path: str | Path,
    *,
    count: int = 1,
    seed: int = 0,
    fd_frac: float = 0.01,
) -> dict[str, Any]:
    """Propose the next candidate(s) using a local SLSQP step with FD gradients.

    Parameters
    ----------
    package_path:
        Path to the .aieng package.
    count:
        Number of candidates to propose.  When FD gradients are missing,
        up to ``count`` perturbation candidates are emitted.  When gradients
        are available, a single SLSQP step is emitted (additional count is
        ignored to avoid wasting evaluations).
    seed:
        Random seed used only for LHS fallback.
    fd_frac:
        Finite-difference step size as a fraction of the bound width.

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

    if not _has_scipy():
        # Graceful degradation — LHS fallback with honest reason codes
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
            "reason_codes": ["no_surrogate_available", "no_gradient_available"],
            "candidate_ids": [c["candidate_id"] for c in candidates],
            "candidate_count": len(candidates),
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

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
    reason_codes: list[str] = ["select_slsqp"]

    # ── no feasible incumbent → whole-domain LHS fallback ──────────────────────
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

    evaluated = _evaluated_points(patches, ranking)

    # If incumbent itself has no score yet, propose it (or a copy) as first evaluation
    inc_eval = evaluated.get(incumbent_id)
    if inc_eval is None or inc_eval.get("score") is None:
        # Build a patch at the incumbent values so it can be evaluated
        changes = []
        for var in safe_vars:
            vid = var["id"]
            val = incumbent_values.get(vid)
            if var.get("type") == "integer" and isinstance(val, float):
                val = int(round(val))
            changes.append({"variable_id": vid, "new_value": val})
        candidate = {
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_slsqp_baseline_iter{iteration + 1}_000",
            "variable_changes": changes,
            "reasoning": (
                f"Baseline evaluation of incumbent {incumbent_id} "
                "before SLSQP gradient step."
            ),
        }
        members = {f"{DESIGN_CANDIDATES_DIR}{candidate['candidate_id']}.json": _dumps(candidate)}
        _replace_members(pkg, members)
        return {
            "status": "ok",
            "strategy": "slsqp_baseline_eval",
            "iteration": iteration + 1,
            "incumbent_candidate_id": incumbent_id,
            "reason_codes": ["select_slsqp", "needs_more_evaluation"],
            "candidate_ids": [candidate["candidate_id"]],
            "candidate_count": 1,
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

    # ── compute FD gradients ───────────────────────────────────────────────────
    gradient, missing_fd = _compute_gradient_fd(
        incumbent_values, safe_vars, evaluated, fd_frac
    )

    if missing_fd:
        reason_codes.append("no_gradient_available")
        candidates: list[dict[str, Any]] = []
        for i, vid in enumerate(missing_fd[:count]):
            var = next(v for v in safe_vars if v["id"] == vid)
            x0 = _num(incumbent_values.get(vid))
            perturbed = _fd_perturbation_value(var, x0, fd_frac, direction=1)
            if perturbed is None:
                continue
            new_vals = dict(incumbent_values)
            new_vals[vid] = perturbed
            changes = [{"variable_id": v["id"], "new_value": new_vals[v["id"]]} for v in safe_vars]
            candidates.append({
                "format": "aieng.design_candidate_patch",
                "candidate_id": f"cand_slsqp_fd_iter{iteration + 1}_{i:03d}",
                "variable_changes": changes,
                "reasoning": (
                    f"SLSQP finite-difference perturbation (+{fd_frac}) for '{vid}' "
                    f"around incumbent {incumbent_id}."
                ),
            })
        if not candidates:
            return {
                "status": "error",
                "code": "proposer_exhausted",
                "message": "could not build any FD perturbation candidates",
                "proposer_exhausted": True,
                "baseline_modified": False,
            }
        members = {f"{DESIGN_CANDIDATES_DIR}{c['candidate_id']}.json": _dumps(c) for c in candidates}
        _replace_members(pkg, members)
        return {
            "status": "ok",
            "strategy": "slsqp_fd_collection",
            "iteration": iteration + 1,
            "incumbent_candidate_id": incumbent_id,
            "reason_codes": reason_codes,
            "candidate_ids": [c["candidate_id"] for c in candidates],
            "candidate_count": len(candidates),
            "baseline_modified": False,
            "claim_advancement": "none",
            "artifacts": list(members.keys()),
        }

    # ── SLSQP step on local quadratic model ────────────────────────────────────
    raw_next = _slsqp_next_point(incumbent_values, safe_vars, gradient)
    changes = []
    for vi, var in enumerate(safe_vars):
        val = raw_next[vi]
        if var.get("type") == "integer":
            val = int(round(val))
        else:
            val = round(float(val), 6)
        changes.append({"variable_id": var["id"], "new_value": val})

    candidate = {
        "format": "aieng.design_candidate_patch",
        "candidate_id": f"cand_slsqp_iter{iteration + 1}_000",
        "variable_changes": changes,
        "reasoning": (
            f"SLSQP local step from incumbent {incumbent_id} "
            f"(iteration {iteration + 1}, FD gradient, identity Hessian)."
        ),
    }
    members = {f"{DESIGN_CANDIDATES_DIR}{candidate['candidate_id']}.json": _dumps(candidate)}
    _replace_members(pkg, members)
    return {
        "status": "ok",
        "strategy": "slsqp",
        "iteration": iteration + 1,
        "incumbent_candidate_id": incumbent_id,
        "reason_codes": reason_codes,
        "candidate_ids": [candidate["candidate_id"]],
        "candidate_count": 1,
        "baseline_modified": False,
        "claim_advancement": "none",
        "artifacts": list(members.keys()),
    }
