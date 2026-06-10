"""Deterministic candidate parameter generation (sampler) for design studies.

Reads ``analysis/optimization_variables.json`` (resolved variable bindings) and
emits candidate patches into ``patches/design_candidates/<cid>.json`` in the
existing format consumed by the executor/evaluator/ranker pipeline.

Supports three sampling algorithms:
- **grid** — Cartesian product of discretised values per variable.
- **random** — Uniform random draw from each variable's domain.
- **latin_hypercube** — Stratified random sampling (LHS) for better coverage.

All algorithms are deterministic given a seed and respect variable bounds,
types, and ``safe_to_modify``. The sampler never modifies the baseline.
"""

from __future__ import annotations

import datetime
import hashlib
import itertools
import json
import math
import random
import zipfile
from pathlib import Path
from typing import Any

from aieng.audit_event import (
    AUDIT_EVENTS_PATH,
    build_audit_event,
    parse_audit_events_jsonl,
    serialize_audit_events_jsonl,
)
from aieng.optimization_artifacts import (
    OPTIMIZATION_DECISION_LOG_PATH,
    validate_optimization_artifact_set,
)

from .design_study import validate_design_candidate_patch

SAMPLE_CANDIDATES_DIR = "patches/design_candidates/"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
OPTIMIZATION_STUDY_PATH = "analysis/optimization_study.json"
DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"

_VARIABLE_TYPES = {"continuous", "integer", "discrete", "categorical", "boolean"}
_BOUNDED_TYPES = {"continuous", "integer"}
_DISCRETE_TYPES = {"discrete", "categorical"}


# ── helpers ──────────────────────────────────────────────────────────────────


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _bound(var: dict[str, Any], name: str, default: float) -> float:
    value = var.get(name)
    return default if value is None else float(value)


def _sample_value(
    var: dict[str, Any],
    *,
    normalised_frac: float,
) -> Any:
    """Draw ONE value for a variable given a normalised fraction in [0, 1].

    ``normalised_frac`` is a uniform or LHS-stratified quantile. For bounded
    types the value is linearly interpolated; for discrete types the fraction
    indexes into ``allowed_values``; for boolean it rounds the fraction.
    """
    vtype = var.get("type", "continuous")
    if vtype == "boolean":
        return normalised_frac >= 0.5

    if vtype in _BOUNDED_TYPES:
        lo = _bound(var, "min_value", 0.0)
        hi = _bound(var, "max_value", 1.0)
        raw = lo + normalised_frac * (hi - lo)
        if vtype == "integer":
            return int(round(raw))
        return raw

    if vtype in _DISCRETE_TYPES:
        allowed = var.get("allowed_values") or [None]
        idx = min(int(normalised_frac * len(allowed)), len(allowed) - 1)
        return allowed[idx]

    return normalised_frac


def _grid_values(var: dict[str, Any], *, n: int = 5) -> list[Any]:
    """Discretise a variable into ``n`` evenly spaced values (or its allowed values)."""
    vtype = var.get("type", "continuous")
    if vtype == "boolean":
        return [False, True]
    if vtype in _DISCRETE_TYPES:
        return list(var.get("allowed_values") or [])
    lo = _bound(var, "min_value", 0.0)
    hi = _bound(var, "max_value", 1.0)
    if n < 2:
        n = 2
    if vtype == "integer":
        lo_i, hi_i = int(round(lo)), int(round(hi))
        values = [
            int(round(lo_i + (hi_i - lo_i) * i / (n - 1)))
            for i in range(n)
        ]
        return list(dict.fromkeys(values))
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def _filter_safe_variables(variables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only variables that are safe to modify and are known types."""
    safe: list[dict[str, Any]] = []
    for var in variables:
        if not isinstance(var, dict):
            continue
        if var.get("safe_to_modify") is not True:
            continue
        if var.get("type") not in _VARIABLE_TYPES:
            continue
        safe.append(var)
    return safe


def _validate_variable(var: dict[str, Any]) -> list[str]:
    """Return validation issues for a single variable. Empty list = OK."""
    issues: list[str] = []
    vid = var.get("id")
    vtype = var.get("type")
    if not vid:
        issues.append("variable missing 'id'")
        return issues
    if vtype not in _VARIABLE_TYPES:
        return [f"variable '{vid}' has unknown type '{vtype}'"]
    if vtype in _BOUNDED_TYPES:
        lo, hi = var.get("min_value"), var.get("max_value")
        if lo is None or hi is None:
            issues.append(f"variable '{vid}' ({vtype}) missing min_value or max_value")
        elif not _is_number(lo) or not _is_number(hi):
            issues.append(f"variable '{vid}' ({vtype}) bounds must be numeric")
        elif not math.isfinite(float(lo)) or not math.isfinite(float(hi)):
            issues.append(f"variable '{vid}' ({vtype}) bounds must be finite")
        elif lo > hi:
            issues.append(f"variable '{vid}' has min_value > max_value")
    elif vtype in _DISCRETE_TYPES:
        av = var.get("allowed_values")
        if not isinstance(av, list) or not av:
            issues.append(f"variable '{vid}' ({vtype}) has empty allowed_values")
    return issues


# ── sampling algorithms ──────────────────────────────────────────────────────


def grid_sample(
    variables: list[dict[str, Any]],
    *,
    counts: dict[str, int] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Grid-search candidate generation: Cartesian product of discretised values.

    ``counts`` maps variable id -> number of levels (default 5 per variable).
    ``limit`` optionally truncates generation; callers that use it are
    responsible for reporting the dropped combinations.
    """
    safe = _filter_safe_variables(variables)
    if not safe:
        return []

    grids: list[tuple[str, list[Any]]] = []
    for var in safe:
        vid = var["id"]
        n = (counts or {}).get(vid, 5)
        grids.append((vid, _grid_values(var, n=n)))

    total = math.prod(len(values) for _, values in grids)
    product = itertools.product(*(values for _, values in grids))
    combos = itertools.islice(product, limit) if limit is not None else product
    candidates: list[dict[str, Any]] = []
    for idx, combo in enumerate(combos):
        changes = [
            {"variable_id": grids[pos][0], "new_value": value}
            for pos, value in enumerate(combo)
        ]
        candidates.append({
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_grid_{idx:04d}",
            "variable_changes": changes,
            "reasoning": f"Grid search: combination {idx + 1} of {total}.",
        })
    return candidates


def random_sample(
    variables: list[dict[str, Any]],
    *,
    count: int,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Random-search candidate generation: uniform random within bounds.

    Deterministic given ``seed``.
    """
    safe = _filter_safe_variables(variables)
    if not safe or count < 1:
        return []

    rng = random.Random(seed)
    candidates: list[dict[str, Any]] = []
    for idx in range(count):
        per_var_seed = rng.randint(0, 2**31 - 1)
        local = random.Random(per_var_seed)
        changes: list[dict[str, Any]] = []
        for var in safe:
            frac = local.random()
            val = _sample_value(var, normalised_frac=frac)
            changes.append({"variable_id": var["id"], "new_value": val})
        candidates.append({
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_random_{idx:04d}",
            "variable_changes": changes,
            "reasoning": f"Random search: draw {idx + 1} of {count}.",
        })
    return candidates


def latin_hypercube_sample(
    variables: list[dict[str, Any]],
    *,
    count: int,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Latin hypercube sampling: stratified random for better coverage.

    Each variable's [0, 1] range is divided into ``count`` equal strata,
    one sample is drawn from each stratum, and the values are randomly
    permuted across candidates per variable.

    Deterministic given ``seed``.
    """
    safe = _filter_safe_variables(variables)
    if not safe or count < 1:
        return []

    rng = random.Random(seed)

    # Build per-candidate stratified fractions
    n_vars = len(safe)
    strata = [
        [(i + rng.random()) / count for i in range(count)]
        for _ in range(n_vars)
    ]

    # Randomly permute each variable's strata independently
    for s in strata:
        rng.shuffle(s)

    candidates: list[dict[str, Any]] = []
    for idx in range(count):
        changes: list[dict[str, Any]] = []
        for vi, var in enumerate(safe):
            frac = strata[vi][idx]
            val = _sample_value(var, normalised_frac=frac)
            changes.append({"variable_id": var["id"], "new_value": val})
        candidates.append({
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_lhs_{idx:04d}",
            "variable_changes": changes,
            "reasoning": f"Latin hypercube: stratified draw {idx + 1} of {count}.",
        })
    return candidates


# ── public entrypoint ────────────────────────────────────────────────────────


def sample_candidates(
    variables: list[dict[str, Any]],
    *,
    algorithm: str = "grid",
    count: int | None = None,
    seed: int = 0,
    max_candidates: int = 50,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Generate candidate patches from resolved optimization variables.

    Parameters
    ----------
    variables:
        List of variable dicts from ``analysis/optimization_variables.json``.
        Each must carry at minimum ``id``, ``type``, bounds/allowed_values,
        and ``safe_to_modify``.
    algorithm:
        One of ``"grid"``, ``"random"``, ``"latin_hypercube"``.
    count:
        Number of candidates for random/LHS. Auto-computed for grid from
        the Cartesian product size. Clamped to ``max_candidates``.
    seed:
        Random seed for reproducibility (used by random and LHS; grid ignores
        seed because it is purely deterministic).
    max_candidates:
        Hard cap on emitted candidates beyond which sampling is truncated.
    counts:
        Per-variable level counts for grid search (default 5 per variable).

    Returns
    -------
    A dictionary with keys:
      ``algorithm``, ``seed``, ``candidates`` (list of candidate-patch dicts),
      ``total_generated``, ``capped``, ``dropped_count``, ``warnings``.
    """
    safe = _filter_safe_variables(variables)
    issues: list[str] = []
    for var in safe:
        issues.extend(_validate_variable(var))
    warnings: list[str] = list(issues)

    if not safe:
        return {
            "algorithm": algorithm,
            "seed": seed,
            "candidates": [],
            "total_generated": 0,
            "capped": False,
            "dropped_count": 0,
            "warnings": ["no safe-to-modify variables available — no candidates generated"],
        }

    alg = algorithm.lower().replace("-", "_")
    if max_candidates < 1:
        return {
            "algorithm": alg,
            "seed": seed,
            "candidates": [],
            "total_generated": 0,
            "capped": False,
            "dropped_count": 0,
            "warnings": ["max_candidates must be a positive integer"],
        }
    if count is not None and count < 1:
        return {
            "algorithm": alg,
            "seed": seed,
            "candidates": [],
            "total_generated": 0,
            "capped": False,
            "dropped_count": 0,
            "warnings": ["count must be a positive integer"],
        }
    if issues:
        return {
            "algorithm": alg,
            "seed": seed,
            "candidates": [],
            "total_generated": 0,
            "capped": False,
            "dropped_count": 0,
            "warnings": warnings,
        }

    if alg == "grid":
        grid_lengths = [
            len(_grid_values(var, n=(counts or {}).get(var["id"], 5)))
            for var in safe
        ]
        total = math.prod(grid_lengths)
        candidates = grid_sample(safe, counts=counts, limit=max_candidates)
    elif alg == "random":
        n = count if count is not None else 10
        total = n
        candidates = random_sample(safe, count=min(n, max_candidates), seed=seed)
    elif alg in ("latin_hypercube", "lhs"):
        n = count if count is not None else len(safe) * 3
        total = n
        candidates = latin_hypercube_sample(safe, count=min(n, max_candidates), seed=seed)
    else:
        return {
            "algorithm": algorithm,
            "seed": seed,
            "candidates": [],
            "total_generated": 0,
            "capped": False,
            "dropped_count": 0,
            "warnings": [f"unknown algorithm '{algorithm}' — use grid, random, or latin_hypercube"],
        }

    capped = total > max_candidates
    dropped = max(0, total - max_candidates)
    if capped:
        warnings.append(
            f"candidate cap ({max_candidates}) reached; dropped {dropped} of {total} "
            f"generated candidates. Increase max_candidates or reduce count."
        )

    return {
        "algorithm": "latin_hypercube" if alg == "lhs" else alg,
        "seed": seed,
        "candidates": candidates,
        "total_generated": total,
        "capped": capped,
        "dropped_count": dropped,
        "warnings": warnings,
    }


# ── package I/O ──────────────────────────────────────────────────────────────


def sample_candidates_package(
    package_path: str | Path,
    *,
    algorithm: str | None = None,
    count: int | None = None,
    seed: int | None = None,
    max_candidates: int | None = None,
    overwrite: bool = False,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Read a package's optimization variables, run the sampler, write candidates.

    The sampler reads ``analysis/optimization_variables.json`` (required) and
    optionally ``analysis/optimization_study.json`` to discover the algorithm,
    requested count, max count, and seed.  Explicit parameters override the
    study config.

    Candidate patches are written to ``patches/design_candidates/<cid>.json``.

    Returns the sampler result dict with an added ``artifacts_written`` key.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {"status": "error", "code": "package_not_found", "message": "package not found"}

    # Read existing artifacts
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            if DESIGN_STUDY_PROBLEM_PATH not in names:
                return {
                    "status": "error",
                    "code": "missing_design_study_problem",
                    "message": f"{DESIGN_STUDY_PROBLEM_PATH} not found in package",
                }
            if OPTIMIZATION_VARIABLES_PATH not in names:
                return {
                    "status": "error", "code": "missing_variables",
                    "message": f"{OPTIMIZATION_VARIABLES_PATH} not found in package. "
                               "Run opt.define_variables or create optimization_variables.json first.",
                }
            variables_doc: dict[str, Any] = json.loads(zf.read(OPTIMIZATION_VARIABLES_PATH))
            design_study_problem: dict[str, Any] = json.loads(
                zf.read(DESIGN_STUDY_PROBLEM_PATH)
            )
            study: dict[str, Any] | None = None
            if OPTIMIZATION_STUDY_PATH in names:
                study = json.loads(zf.read(OPTIMIZATION_STUDY_PATH))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "read_failed", "message": f"{type(exc).__name__}: {exc}"}

    variables = variables_doc.get("variables", [])
    if not isinstance(variables, list) or not variables:
        return {
            "status": "error", "code": "empty_variables",
            "message": "optimization_variables.json has no variables",
        }
    source_documents = {"variables": variables_doc}
    if study is not None:
        source_documents["study"] = study
    source_issues = validate_optimization_artifact_set(
        source_documents,
        design_study_problem=design_study_problem,
    )
    if source_issues:
        return {
            "status": "error",
            "code": "invalid_optimization_source",
            "message": "optimization source artifacts are invalid or inconsistent",
            "issues": source_issues,
        }

    # Resolve parameters: explicit > study config > defaults
    resolved_algo: str = "grid"
    resolved_count: int = 10
    resolved_seed: int = 0
    resolved_max: int = 50

    if study and isinstance(study, dict):
        if study.get("algorithm") and isinstance(study["algorithm"], dict):
            study_algo = study["algorithm"].get("name", "")
            if algorithm is None:
                resolved_algo = study_algo if study_algo else "grid"
            if study["algorithm"].get("seed") is not None and seed is None:
                resolved_seed = int(study["algorithm"]["seed"])
        if study.get("sampling") and isinstance(study["sampling"], dict):
            sampling = study["sampling"]
            if count is None:
                resolved_count = sampling.get("requested_candidate_count") or sampling.get("max_candidate_count") or resolved_count
            if sampling.get("seed") is not None and seed is None:
                resolved_seed = int(sampling["seed"])
            if max_candidates is None and sampling.get("max_candidate_count"):
                resolved_max = int(sampling["max_candidate_count"])
        if study.get("budget") and isinstance(study["budget"], dict):
            budget_max = study["budget"].get("max_candidates")
            if budget_max is not None:
                resolved_max = min(resolved_max, int(budget_max))

    # Explicit overrides
    if algorithm is not None:
        resolved_algo = algorithm
    if count is not None:
        resolved_count = count
    if seed is not None:
        resolved_seed = seed
    if max_candidates is not None:
        resolved_max = max_candidates
        if study and isinstance(study.get("budget"), dict):
            budget_max = study["budget"].get("max_candidates")
            if budget_max is not None:
                resolved_max = min(resolved_max, int(budget_max))

    result = sample_candidates(
        variables,
        algorithm=resolved_algo,
        count=resolved_count,
        seed=resolved_seed,
        max_candidates=resolved_max,
        counts=counts,
    )

    if not result["candidates"]:
        return {
            "status": "error",
            "code": "sampling_failed",
            **result,
            "artifacts_written": [],
        }

    candidate_issues: list[str] = []
    for candidate in result["candidates"]:
        record = validate_design_candidate_patch(design_study_problem, candidate)
        if record["status"] == "rejected":
            candidate_issues.extend(
                f"{candidate['candidate_id']}: {issue}"
                for issue in record.get("errors", [])
            )
    if candidate_issues:
        return {
            "status": "error",
            "code": "generated_candidates_invalid",
            "message": "generated candidates are incompatible with the design-study problem",
            "issues": candidate_issues,
            **result,
            "artifacts_written": [],
        }

    # Write candidates and update the study's candidate_ids
    artifacts_written: list[str] = []
    existing_ids: set[str] = set()
    study_candidate_ids: list[str] = []

    if study and isinstance(study, dict):
        study_candidate_ids = list(study.get("candidate_ids") or [])
        existing_ids = set(study_candidate_ids)

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            existing_names = set(zf.namelist())
            for name in existing_names:
                if name.startswith(SAMPLE_CANDIDATES_DIR) and name.endswith(".json"):
                    cid = name.split("/")[-1].removesuffix(".json")
                    existing_ids.add(cid)
    except Exception:
        existing_ids = set()

    # Prepare updated members
    members: dict[str, bytes] = {}
    for cand in result["candidates"]:
        cid: str = cand["candidate_id"]
        if not overwrite:
            base_id = cid
            attempt = 0
            while cid in existing_ids:
                attempt += 1
                digest = hashlib.sha256(
                    f"{base_id}:{resolved_seed}:{attempt}".encode("utf-8")
                ).hexdigest()[:8]
                cid = f"{base_id}_{digest}"
            cand["candidate_id"] = cid
        existing_ids.add(cid)
        path = f"{SAMPLE_CANDIDATES_DIR}{cid}.json"
        members[path] = _dumps(cand)
        artifacts_written.append(path)
        if cid not in study_candidate_ids:
            study_candidate_ids.append(cid)

    emitted_candidate_ids = [
        candidate["candidate_id"] for candidate in result["candidates"]
    ]
    variables_doc["candidate_ids"] = list(
        dict.fromkeys(list(variables_doc.get("candidate_ids") or []) + emitted_candidate_ids)
    )
    variable_candidate_ids: dict[str, list[str]] = {}
    for candidate in result["candidates"]:
        for change in candidate.get("variable_changes") or []:
            variable_candidate_ids.setdefault(change["variable_id"], []).append(
                candidate["candidate_id"]
            )
    for variable in variables_doc.get("variables") or []:
        if not isinstance(variable, dict):
            continue
        linked = variable_candidate_ids.get(variable.get("id"), [])
        variable["candidate_ids"] = list(
            dict.fromkeys(list(variable.get("candidate_ids") or []) + linked)
        )
    members[OPTIMIZATION_VARIABLES_PATH] = _dumps(variables_doc)

    # Update study's candidate_ids if study exists
    if study and study_candidate_ids:
        study["candidate_ids"] = study_candidate_ids
        members[OPTIMIZATION_STUDY_PATH] = _dumps(study)

    if result["dropped_count"]:
        decision_log = _updated_cap_decision_log(
            pkg,
            variables_doc=variables_doc,
            study=study,
            candidate_ids=emitted_candidate_ids,
            total_generated=result["total_generated"],
            max_candidates=resolved_max,
        )
        members[OPTIMIZATION_DECISION_LOG_PATH] = _dumps(decision_log)

    metadata_artifacts = [OPTIMIZATION_VARIABLES_PATH]
    if study and study_candidate_ids:
        metadata_artifacts.append(OPTIMIZATION_STUDY_PATH)
    if result["dropped_count"]:
        metadata_artifacts.append(OPTIMIZATION_DECISION_LOG_PATH)

    validation_documents: dict[str, dict[str, Any]] = {"variables": variables_doc}
    if study is not None:
        validation_documents["study"] = study
    if result["dropped_count"]:
        validation_documents["decision_log"] = decision_log
    write_issues = validate_optimization_artifact_set(
        validation_documents,
        design_study_problem=design_study_problem,
    )
    if write_issues:
        return {
            "status": "error",
            "code": "invalid_optimization_write",
            "message": "candidate linkage update would violate optimization contracts",
            "issues": write_issues,
            **result,
            "artifacts_written": [],
        }

    members[AUDIT_EVENTS_PATH] = _updated_audit_log(
        pkg,
        candidate_ids=emitted_candidate_ids,
        artifacts_written=artifacts_written + metadata_artifacts,
        algorithm=result["algorithm"],
        dropped_count=result["dropped_count"],
    )

    # Write to package atomically
    _rewrite_package_members(pkg, members)

    return {
        "status": "ok",
        **result,
        "artifacts_written": artifacts_written + metadata_artifacts + [AUDIT_EVENTS_PATH],
        "candidate_artifacts_written": artifacts_written,
        "candidate_count": len(result["candidates"]),
        "baseline_modified": False,
        "claim_advancement": "none",
    }


def _updated_cap_decision_log(
    package_path: Path,
    *,
    variables_doc: dict[str, Any],
    study: dict[str, Any] | None,
    candidate_ids: list[str],
    total_generated: int,
    max_candidates: int,
) -> dict[str, Any]:
    existing: dict[str, Any] | None = None
    try:
        with zipfile.ZipFile(package_path, "r") as package:
            if OPTIMIZATION_DECISION_LOG_PATH in package.namelist():
                existing = json.loads(package.read(OPTIMIZATION_DECISION_LOG_PATH))
    except Exception:
        existing = None

    study_id = variables_doc.get("study_id")
    problem_id = variables_doc.get("design_study_problem_id")
    if existing is None:
        existing = {
            "format": "aieng.optimization_decision_log",
            "schema_version": "0.1",
            "study_id": study_id,
            "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
            "design_study_problem_id": problem_id,
            "entries": [],
            "candidate_ids": [],
            "provenance": {
                "created_at": _utcnow(),
                "created_by": "aieng.optimization_sampler",
                "claim_advancement": "none",
            },
            "claim_policy": {
                "advisory_only": True,
                "baseline_unchanged": True,
                "human_approval_required_for_acceptance": True,
                "claim_advancement": "none",
            },
        }
        if problem_id is None:
            existing.pop("design_study_problem_id")

    decision_number = len(existing.get("entries") or []) + 1
    existing.setdefault("entries", []).append(
        {
            "decision_id": f"decision_cap_{decision_number:04d}",
            "timestamp": _utcnow(),
            "decision": "truncate_candidate_set_at_configured_cap",
            "reason_codes": ["candidate_cap_reached", "budget_exhausted"],
            "requires_human_review": False,
            "candidate_ids": candidate_ids,
            "note": (
                f"Generated {total_generated} candidate combinations and emitted "
                f"{max_candidates}; {total_generated - max_candidates} were dropped."
            ),
        }
    )
    existing["candidate_ids"] = list(
        dict.fromkeys(list(existing.get("candidate_ids") or []) + candidate_ids)
    )
    documents = {"variables": variables_doc, "decision_log": existing}
    if study is not None:
        documents["study"] = study
    issues = validate_optimization_artifact_set(documents)
    if issues:
        raise ValueError("invalid optimization decision log: " + "; ".join(issues))
    return existing


def _updated_audit_log(
    package_path: Path,
    *,
    candidate_ids: list[str],
    artifacts_written: list[str],
    algorithm: str,
    dropped_count: int,
) -> bytes:
    events: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(package_path, "r") as package:
            if AUDIT_EVENTS_PATH in package.namelist():
                events = parse_audit_events_jsonl(
                    package.read(AUDIT_EVENTS_PATH).decode("utf-8")
                )
    except Exception:
        events = []
    events.append(
        build_audit_event(
            tool="opt.propose_candidates",
            event_type="optimization_candidates_proposed",
            status="completed",
            artifacts_written=artifacts_written,
            evidence_created=[],
            state_changes={
                "algorithm": algorithm,
                "candidate_ids": candidate_ids,
                "dropped_count": dropped_count,
                "baseline_modified": False,
            },
            geometry_revision=None,
            revalidation_status=None,
        )
    )
    return serialize_audit_events_jsonl(events).encode("utf-8")


def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    """Atomically rewrite multiple members in a zip package."""
    tmp = package_path.with_suffix(".tmp.aieng")
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
