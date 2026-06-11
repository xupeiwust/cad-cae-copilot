"""Deterministic local-refinement proposer for the iterative loop (#62).

Phase 1 generates the *initial* design (grid/random/LHS). Phase 2 needs to
propose the *next* batch from previous results. This module is the first,
zero-dependency proposer: a **trust-region local refinement** — sample around the
current incumbent within a radius that shrinks each iteration. SLSQP / Bayesian /
GA (Slice B) are later drop-ins under the same ``propose_next_candidates`` entry.

It reads the ranking for the incumbent and the incumbent's variable values from
its candidate patch, then emits new candidate patches in the existing
``patches/design_candidates/<cid>.json`` format the executor already consumes.
When there is no feasible incumbent, it falls back to whole-domain Latin
hypercube sampling (reusing ``optimization_sampler``) and records the fallback.

Deterministic given a seed. Baseline is never modified.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from random import Random
from typing import Any

from aieng.converters.optimization_sampler import (
    SAMPLE_CANDIDATES_DIR,
    _filter_safe_variables,
    latin_hypercube_sample,
)

DESIGN_STUDY_CANDIDATE_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
OPTIMIZATION_ITERATIONS_PATH = "analysis/optimization_iterations.json"
DESIGN_CANDIDATES_DIR = SAMPLE_CANDIDATES_DIR  # "patches/design_candidates/"

_BOUNDED_TYPES = {"continuous", "integer"}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    tmp = package_path.with_suffix(".optprop.tmp.aieng")
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


def _incumbent_variable_values(
    zf: zipfile.ZipFile, names: set[str], incumbent_id: str | None,
) -> dict[str, Any]:
    """Read the incumbent candidate's {variable_id: value} from its patch."""
    if not incumbent_id:
        return {}
    patch = _read_json(zf, f"{DESIGN_CANDIDATES_DIR}{incumbent_id}.json", names)
    values: dict[str, Any] = {}
    if isinstance(patch, dict):
        for ch in patch.get("variable_changes") or []:
            if isinstance(ch, dict) and ch.get("variable_id") is not None:
                values[ch["variable_id"]] = ch.get("new_value")
    return values


def _refine_value(var: dict[str, Any], center: float | None, radius_frac: float,
                  rng: Random) -> Any:
    """Sample one value in a shrunk window around ``center``, clamped to bounds."""
    lo = _num(var.get("min_value"))
    hi = _num(var.get("max_value"))
    vtype = var.get("type", "continuous")
    if lo is None or hi is None or hi <= lo:
        # unbounded/degenerate — keep center (or midpoint) without inventing a range
        return center if center is not None else lo
    if center is None:
        center = (lo + hi) / 2.0
    half = radius_frac * (hi - lo) / 2.0
    win_lo = max(lo, center - half)
    win_hi = min(hi, center + half)
    raw = rng.uniform(win_lo, win_hi)
    if vtype == "integer":
        return int(round(raw))
    return round(raw, 6)


def propose_next_candidates(
    package_path: str | Path,
    *,
    count: int = 4,
    shrink: float = 0.5,
    seed: int = 0,
    algorithm: str = "trust_region",
) -> dict[str, Any]:
    """Propose the next batch of candidates by local refinement around the incumbent.

    The trust-region radius fraction is ``shrink ** iteration`` (iteration count
    read from ``optimization_iterations.json``), so later rounds search closer to
    the incumbent. With no feasible incumbent, falls back to whole-domain LHS.

    ``algorithm`` selects the proposer strategy:
      * ``"trust_region"`` (default) — shrunk-box local refinement.
      * ``"slsqp"`` — SLSQP local step on a quadratic model with FD gradients.

    Writes candidate patches to ``patches/design_candidates/<cid>.json`` and
    returns a summary. Baseline never modified.
    """
    alg = algorithm.lower().replace("-", "_")
    if alg == "slsqp":
        from .optimization_proposer_slsqp import propose_slsqp_candidates
        return propose_slsqp_candidates(package_path, count=count, seed=seed)
    pkg = Path(package_path)
    if not pkg.exists():
        return {"status": "error", "code": "package_not_found", "message": "package not found",
                "baseline_modified": False}
    if count < 1:
        return {"status": "error", "code": "bad_input", "message": "count must be >= 1",
                "baseline_modified": False}

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            variables_doc = _read_json(zf, OPTIMIZATION_VARIABLES_PATH, names)
            history = _read_json(zf, OPTIMIZATION_ITERATIONS_PATH, names)
            existing_ids = {
                n[len(DESIGN_CANDIDATES_DIR):-len(".json")]
                for n in names
                if n.startswith(DESIGN_CANDIDATES_DIR) and n.endswith(".json")
            }
            incumbent_values: dict[str, Any] = {}
            incumbent_id = None
            if isinstance(ranking, dict):
                incumbent_id = ranking.get("best_candidate_id")
                incumbent_values = _incumbent_variable_values(zf, names, incumbent_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "read_failed",
                "message": f"{type(exc).__name__}: {exc}", "baseline_modified": False}

    if not isinstance(variables_doc, dict):
        return {"status": "error", "code": "missing_variables",
                "message": f"{OPTIMIZATION_VARIABLES_PATH} not found", "baseline_modified": False}
    safe_vars = _filter_safe_variables(variables_doc.get("variables") or [])
    if not safe_vars:
        return {"status": "error", "code": "no_variables",
                "message": "no safe-to-modify variables to refine", "baseline_modified": False}

    iteration = (
        len(history.get("iterations") or []) if isinstance(history, dict) else 0
    )
    reason_codes: list[str] = []

    # ── no feasible incumbent → whole-domain LHS fallback ────────────────────
    if not incumbent_id or not incumbent_values:
        reason_codes.append("no_incumbent_fallback")
        candidates = latin_hypercube_sample(safe_vars, count=count, seed=seed)
        strategy = "lhs_fallback"
        radius_frac = 1.0
    else:
        # ── trust-region local refinement ───────────────────────────────────
        reason_codes.append("local_refinement")
        radius_frac = float(shrink) ** max(0, iteration)
        if iteration > 0:
            reason_codes.append("trust_region_shrink")
        rng = Random(seed)
        candidates = []
        for i in range(count):
            changes = []
            for var in safe_vars:
                vid = var["id"]
                center = _num(incumbent_values.get(vid))
                val = _refine_value(var, center, radius_frac, rng)
                changes.append({"variable_id": vid, "new_value": val})
            candidates.append({
                "format": "aieng.design_candidate_patch",
                "candidate_id": f"cand_iter{iteration + 1}_{i:03d}",
                "variable_changes": changes,
                "reasoning": (
                    f"Local refinement around incumbent {incumbent_id} "
                    f"(iteration {iteration + 1}, radius {radius_frac:.3f})."
                ),
            })
        strategy = "trust_region"

    if not candidates:
        return {"status": "error", "code": "proposer_exhausted",
                "message": "proposer produced no candidates", "proposer_exhausted": True,
                "baseline_modified": False}

    # de-dup ids against existing candidates on disk
    members: dict[str, bytes] = {}
    written_ids: list[str] = []
    for cand in candidates:
        cid = cand["candidate_id"]
        suffix = 0
        base = cid
        while cid in existing_ids:
            suffix += 1
            cid = f"{base}_{suffix}"
        existing_ids.add(cid)
        cand["candidate_id"] = cid
        members[f"{DESIGN_CANDIDATES_DIR}{cid}.json"] = _dumps(cand)
        written_ids.append(cid)

    _replace_members(pkg, members)

    return {
        "status": "ok",
        "strategy": strategy,
        "iteration": iteration + 1,
        "radius_fraction": radius_frac,
        "incumbent_candidate_id": incumbent_id,
        "reason_codes": reason_codes,
        "candidate_ids": written_ids,
        "candidate_count": len(written_ids),
        "baseline_modified": False,
        "claim_advancement": "none",
        "artifacts": list(members.keys()),
    }
