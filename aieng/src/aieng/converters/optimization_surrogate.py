"""Surrogate-assisted candidate proposal with explicit honesty gates (v0, #205).

Fits a lightweight, **deterministic** Gaussian-process surrogate (RBF kernel,
fixed hyperparameters, numpy-only — no scikit-optimize dependency) over already
**evaluated** candidate metrics, and proposes new candidate patches by an
upper-confidence-bound acquisition. Predictions carry an explicit uncertainty
(predictive std) and are marked **advisory** — they guide search only and are
never treated as solver/verification evidence.

Hard boundaries:
- never executes a solver, never accepts a candidate, never promotes a baseline;
- degrades honestly (``needs_more_evidence`` / ``no_safe_variables``) when the
  evaluated evidence is missing or too sparse to fit a surrogate;
- writes only proposals (``patches/design_candidates/surrogate_*.json`` +
  ``analysis/design_study_surrogate_proposals.json``) — baseline unchanged.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.credibility import classify_credibility
from aieng.converters.design_study import DESIGN_CANDIDATES_DIR, DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.design_study_ranking import DESIGN_STUDY_CANDIDATE_RANKING_PATH
from aieng.converters.optimization_proposer_bayesian import (
    _evaluated_points,
    _read_all_patches,
    _safe_var_bounds,
    _values_to_vector,
    _vector_to_values,
)
from aieng.converters.optimization_sampler import (
    _filter_safe_variables,
    latin_hypercube_sample,
)

SURROGATE_PROPOSALS_PATH = "analysis/design_study_surrogate_proposals.json"
CANDIDATE_PATCH_FORMAT = "aieng.design_candidate_patch"

_MIN_TRAIN = 3          # fewer evaluated candidates than this -> needs_more_evidence
_QUERY_COUNT = 64       # deterministic query points for the acquisition sweep
_UCB_KAPPA = 1.0        # exploration weight in mean + kappa*std
_LENGTHSCALE = 0.5      # RBF lengthscale in normalized [0,1] space
_NOISE = 1e-3


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".surrogate.tmp.aieng")
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


def _normalize(vec: list[float], bounds: list[tuple[float, float]]) -> list[float]:
    out = []
    for v, (lo, hi) in zip(vec, bounds):
        span = hi - lo
        out.append((v - lo) / span if span else 0.0)
    return out


def _gp_predict(X_train, y_train, X_query):
    """Deterministic GP (RBF kernel, fixed hyperparams). Returns (mean, std) arrays."""
    import numpy as np

    Xt = np.asarray(X_train, dtype=float)
    yt = np.asarray(y_train, dtype=float)
    Xq = np.asarray(X_query, dtype=float)
    ymu = float(yt.mean())
    ysd = float(yt.std()) or 1.0
    yn = (yt - ymu) / ysd

    def rbf(A, B):
        d2 = ((A[:, None, :] - B[None, :, :]) ** 2).sum(axis=-1)
        return np.exp(-d2 / (2.0 * _LENGTHSCALE ** 2))

    K = rbf(Xt, Xt) + _NOISE * np.eye(len(Xt))
    Kinv = np.linalg.inv(K)
    Ks = rbf(Xq, Xt)
    mean_n = Ks @ Kinv @ yn
    var_n = np.clip(1.0 - np.einsum("ij,jk,ik->i", Ks, Kinv, Ks), 0.0, None)
    return mean_n * ysd + ymu, np.sqrt(var_n) * ysd


def _loo_validation(X, y) -> dict[str, Any]:
    """Leave-one-out cross-validation of the surrogate against the evaluated points.

    For each evaluated candidate, refit the GP on the others and predict its
    score; the residuals form an honest *surrogate-vs-evaluated* error band
    (PhysicsX discipline) — the number you would otherwise show with no envelope.
    Deterministic and pure. Returns ``has_evaluated_points: False`` when there
    are too few points to validate.
    """
    import numpy as np

    Xa = np.asarray(X, dtype=float)
    ya = np.asarray(y, dtype=float)
    n = len(ya)
    if n < 3:
        return {
            "method": "leave_one_out_cv",
            "n_points": int(n),
            "has_evaluated_points": False,
            "is_solver_evidence": False,
            "note": "Too few evaluated points to cross-validate the surrogate.",
        }

    preds = np.empty(n, dtype=float)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        mean_i, _ = _gp_predict(Xa[mask], ya[mask], Xa[i : i + 1])
        preds[i] = float(mean_i[0])

    resid = preds - ya
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    mae = float(np.mean(np.abs(resid)))
    max_abs = float(np.max(np.abs(resid)))
    yspan = float(ya.max() - ya.min()) or 1.0
    # Pearson r between predicted and actual; undefined if either is constant.
    if float(np.std(preds)) == 0.0 or float(np.std(ya)) == 0.0:
        pearson = 0.0
    else:
        pearson = float(np.corrcoef(preds, ya)[0, 1])

    return {
        "method": "leave_one_out_cv",
        "n_points": int(n),
        "has_evaluated_points": True,
        "rmse": round(rmse, 6),
        "mae": round(mae, 6),
        "max_abs_error": round(max_abs, 6),
        "relative_rmse": round(rmse / yspan, 6),
        "pearson_r": round(pearson, 6),
        "score_span": round(yspan, 6),
        "is_solver_evidence": False,
        "note": "Surrogate-vs-evaluated leave-one-out error; advisory, not a solver-verified bound.",
    }


def propose_surrogate_candidates(
    problem: dict[str, Any] | None,
    patches: dict[str, dict[str, Any]],
    ranking: dict[str, Any] | None,
    *,
    n_proposals: int = 3,
) -> dict[str, Any]:
    """Pure surrogate proposal over evaluated candidate metrics (advisory)."""
    problem = problem if isinstance(problem, dict) else {}
    variables = problem.get("design_variables") or problem.get("variables") or []
    safe_vars = _filter_safe_variables(variables)
    honesty = {
        "advisory": True,
        "is_solver_evidence": False,
        "predictions_are_verification_evidence": False,
        "baseline_modified": False,
        "acceptance_gated_separately": True,
        "note": "Surrogate predictions guide search only; they are not solver/verification "
                "evidence and never trigger execution, acceptance, or baseline promotion.",
    }

    def _degraded(reason: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out = {
            "format": "aieng.design_study.surrogate_proposals.v0",
            "format_version": FORMAT_VERSION,
            "schema_version": "0.1",
            "status": "needs_more_evidence",
            "reason_codes": [reason],
            "surrogate": None,
            "training_evidence": {"candidate_ids": [], "n_train": 0},
            "proposals": [],
            "honesty": honesty,
            "credibility": classify_credibility("surrogate", is_solver_evidence=False),
            "validation": {
                "method": "leave_one_out_cv",
                "has_evaluated_points": False,
                "is_solver_evidence": False,
                "note": "No surrogate fitted; nothing to cross-validate.",
            },
        }
        out.update(extra or {})
        return out

    if not safe_vars:
        return _degraded("no_safe_variables")

    bounds = _safe_var_bounds(safe_vars)
    evaluated = _evaluated_points(patches, ranking)
    train_ids: list[str] = []
    X: list[list[float]] = []
    y: list[float] = []
    for cid, rec in sorted(evaluated.items()):
        vec = _values_to_vector(rec.get("values") or {}, safe_vars)
        score = rec.get("score")
        if vec is None or not isinstance(score, (int, float)):
            continue
        train_ids.append(cid)
        X.append(_normalize(vec, bounds))
        y.append(float(score))

    if len(train_ids) < _MIN_TRAIN:
        return _degraded("insufficient_evaluated_evidence", {"training_evidence": {
            "candidate_ids": train_ids, "n_train": len(train_ids), "min_required": _MIN_TRAIN}})

    # Deterministic query sweep over the safe-variable space. latin_hypercube_sample
    # returns candidate patches, so read each point's values off variable_changes.
    query_candidates = latin_hypercube_sample(safe_vars, count=_QUERY_COUNT, seed=0)
    q_vecs, q_norm = [], []
    for qc in query_candidates:
        qvals = {ch.get("variable_id"): ch.get("new_value")
                 for ch in (qc.get("variable_changes") or []) if isinstance(ch, dict)}
        vec = _values_to_vector(qvals, safe_vars)
        if vec is None:
            continue
        q_vecs.append(vec)
        q_norm.append(_normalize(vec, bounds))
    if not q_norm:
        return _degraded("no_query_points")

    mean, std = _gp_predict(X, y, q_norm)
    validation = _loo_validation(X, y)
    yspan = (max(y) - min(y)) or 1.0
    # Higher ranking score is better -> upper-confidence-bound acquisition.
    scored = sorted(
        range(len(q_norm)),
        key=lambda i: float(mean[i]) + _UCB_KAPPA * float(std[i]),
        reverse=True,
    )

    n_train = len(train_ids)
    global_conf = "low" if n_train < 5 else "medium"  # surrogate predictions are never "high"
    proposals: list[dict[str, Any]] = []
    for rank, i in enumerate(scored[:max(0, n_proposals)], start=1):
        values = _vector_to_values(q_vecs[i], safe_vars)
        rel_unc = float(std[i]) / yspan
        proposals.append({
            "proposal_rank": rank,
            "variable_changes": [{"variable_id": vid, "new_value": val} for vid, val in values.items()],
            "surrogate_prediction": {
                "predicted_score": round(float(mean[i]), 6),
                "uncertainty_std": round(float(std[i]), 6),
                # Explicit ±1σ envelope so the number is never shown bare (#219).
                "predicted_score_band": [
                    round(float(mean[i]) - float(std[i]), 6),
                    round(float(mean[i]) + float(std[i]), 6),
                ],
                "acquisition_ucb": round(float(mean[i]) + _UCB_KAPPA * float(std[i]), 6),
                "confidence": "low" if rel_unc > 0.5 else global_conf,
                "advisory": True,
                "is_solver_evidence": False,
            },
        })

    return {
        "format": "aieng.design_study.surrogate_proposals.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": "ok",
        "reason_codes": [],
        "surrogate": {
            "kind": "gp_rbf_numpy",
            "deterministic": True,
            "lengthscale": _LENGTHSCALE,
            "noise": _NOISE,
            "acquisition": "upper_confidence_bound",
            "kappa": _UCB_KAPPA,
            "objective_target": "ranking_score",
            "global_confidence": global_conf,
        },
        "training_evidence": {
            "candidate_ids": train_ids,
            "n_train": n_train,
            "score_min": round(min(y), 6),
            "score_max": round(max(y), 6),
        },
        "proposals": proposals,
        "honesty": honesty,
        "validation": validation,
        "credibility": classify_credibility(
            "surrogate",
            is_solver_evidence=False,
            uncertainty_std=round(float(max(std)), 6) if len(std) else None,
        ),
    }


def write_surrogate_proposals(
    package_path: str | Path,
    *,
    n_proposals: int = 3,
) -> dict[str, Any]:
    """Read design-study artifacts, fit the surrogate, and write advisory proposals.

    Writes ``analysis/design_study_surrogate_proposals.json`` and one proposed
    candidate patch per proposal under ``patches/design_candidates/surrogate_*.json``
    (valid, ``applied:false``). Runs no solver, accepts nothing, and never mutates
    baseline geometry.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "error", "reason": "package not found", "baseline_modified": False}
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            patches = _read_all_patches(zf, names)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}", "baseline_modified": False}

    result = propose_surrogate_candidates(problem, patches, ranking, n_proposals=n_proposals)

    members: dict[str, bytes] = {SURROGATE_PROPOSALS_PATH: _dumps(result)}
    written_patches: list[str] = []
    for idx, prop in enumerate(result.get("proposals", []), start=1):
        cid = f"surrogate_{idx:03d}"
        patch = {
            "format": CANDIDATE_PATCH_FORMAT,
            "schema_version": "0.1",
            "candidate_id": cid,
            "reasoning": "surrogate-proposed (advisory); not executed, not accepted",
            "variable_changes": prop["variable_changes"],
            "surrogate_prediction": prop["surrogate_prediction"],
            "provenance": {
                "proposed_by": "optimization_surrogate",
                "applied": False,
                "advisory": True,
                "is_solver_evidence": False,
            },
        }
        path = f"{DESIGN_CANDIDATES_DIR}{cid}.json"
        members[path] = _dumps(patch)
        written_patches.append(path)

    _replace_members(package_path, members)
    return {
        "status": result["status"],
        "n_proposals": len(result.get("proposals", [])),
        "reason_codes": result.get("reason_codes", []),
        "written_patches": written_patches,
        "artifacts": [SURROGATE_PROPOSALS_PATH, *written_patches],
        "baseline_modified": False,
    }
