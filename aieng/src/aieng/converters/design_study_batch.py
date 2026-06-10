"""Batch execution of sampled design-study candidates into derived workspaces (#39).

The sampler (`opt.propose_candidates`) emits N candidate patches into
``patches/design_candidates/<cid>.json``; the single-shot executor
(`execute_design_study_candidate`) runs exactly one. This module bridges them:
it discovers the candidate set and runs each one through the existing executor,
so each candidate gets its own isolated ``candidates/<cid>/`` workspace.

Hard safety contract (inherited from `design_study_execution`):
  - The baseline geometry is NEVER overwritten — every candidate is applied to a
    derived copy in its own workspace.
  - No candidate is auto-accepted/promoted into the baseline.
  - This is bounded, explicit batch execution — NOT an optimizer/search/Pareto
    loop. The set of candidates to run is fixed before execution begins.
  - Compile/evaluation is OPTIONAL and injected via ``recompiler``; with none,
    evaluation is honestly partial.

Failure handling: a candidate whose build/compile fails is recorded cleanly
(execution_status ``compile_failed`` / ``failed``, with a ``candidate_build_failed``
reason code in the batch summary) and the batch CONTINUES with the next
candidate. One bad candidate never aborts the run.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable

from aieng.converters.design_study_execution import (
    CANDIDATE_WORKSPACE_ROOT,
    DESIGN_CANDIDATES_DIR,
    execute_design_study_candidate,
)

OPTIMIZATION_STUDY_PATH = "analysis/optimization_study.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"

# execution statuses the batch summary treats as a clean build failure
_FAILED_EXECUTION_STATUSES = {"compile_failed", "failed"}


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:  # noqa: BLE001 - missing/corrupt artifact is non-fatal
            return None
    return None


def discover_candidate_ids(package_path: str | Path) -> list[str]:
    """Return the ordered, de-duplicated set of candidate ids present in a package.

    Discovery prefers the explicit ``candidate_ids`` list recorded by the sampler
    (``optimization_study.json`` then ``optimization_variables.json``) so the run
    order is stable and matches what the agent proposed; any candidate files on
    disk that are not yet listed are appended afterwards so nothing is silently
    skipped.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return []

    listed: list[str] = []
    on_disk: list[str] = []
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            for source in (OPTIMIZATION_STUDY_PATH, OPTIMIZATION_VARIABLES_PATH):
                doc = _read_json(zf, source, names)
                if isinstance(doc, dict):
                    for cid in doc.get("candidate_ids") or []:
                        if isinstance(cid, str) and cid:
                            listed.append(cid)
            for name in names:
                if name.startswith(DESIGN_CANDIDATES_DIR) and name.endswith(".json"):
                    on_disk.append(name[len(DESIGN_CANDIDATES_DIR):-len(".json")])
    except Exception:  # noqa: BLE001 - unreadable package yields no candidates
        return []

    ordered: list[str] = []
    seen: set[str] = set()
    for cid in listed + sorted(on_disk):
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)
    return ordered


def run_design_study_batch(
    package_path: str | Path,
    *,
    candidate_ids: list[str] | None = None,
    recompiler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    """Execute a fixed set of design-study candidates, each into its own workspace.

    Parameters
    ----------
    package_path:
        Path to the ``.aieng`` package.
    candidate_ids:
        Explicit, ordered ids to run. When ``None``, all candidates discovered in
        the package are run (see :func:`discover_candidate_ids`).
    recompiler:
        Optional injected recompiler forwarded verbatim to
        ``execute_design_study_candidate``. It MUST operate on a throwaway copy of
        the baseline. With ``None``, each candidate stops at ``patch_applied`` and
        evaluation is honestly partial.
    max_candidates:
        Optional hard cap on how many candidates are executed this call. When the
        discovered/requested set exceeds it, the remainder is reported as
        ``skipped`` (never silently dropped).

    Returns
    -------
    A summary dict: ``status``, ``requested``, ``executed``, ``succeeded``,
    ``failed``, ``rejected``, ``skipped`` counts, a per-candidate ``results``
    list, ``skipped_candidate_ids``, ``baseline_modified: False``, and
    ``claim_advancement: "none"``.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {
            "status": "error",
            "code": "package_not_found",
            "message": "package not found",
            "results": [],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

    if max_candidates is not None and max_candidates < 0:
        return {
            "status": "error",
            "code": "invalid_max_candidates",
            "message": "max_candidates must be a non-negative integer",
            "results": [],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

    if candidate_ids is not None and not isinstance(candidate_ids, (list, tuple)):
        # Guard against a bare string slipping through (it would iterate into
        # characters below); fail with a structured error, not garbage candidates.
        return {
            "status": "error",
            "code": "invalid_candidate_ids",
            "message": "candidate_ids must be a list of strings",
            "results": [],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

    requested = candidate_ids if candidate_ids is not None else discover_candidate_ids(pkg)
    # de-dup while preserving order; drop blanks
    ordered: list[str] = []
    seen: set[str] = set()
    for cid in requested:
        if isinstance(cid, str) and cid and cid not in seen:
            seen.add(cid)
            ordered.append(cid)

    if not ordered:
        return {
            "status": "ok",
            "requested": 0,
            "executed": 0,
            "succeeded": 0,
            "failed": 0,
            "rejected": 0,
            "skipped": 0,
            "results": [],
            "skipped_candidate_ids": [],
            "warnings": ["no candidates found to execute — run opt.propose_candidates first"],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

    to_run = ordered
    skipped_ids: list[str] = []
    if max_candidates is not None and len(ordered) > max_candidates:
        to_run = ordered[:max_candidates]
        skipped_ids = ordered[max_candidates:]

    results: list[dict[str, Any]] = []
    succeeded = failed = rejected = 0
    for cid in to_run:
        # execute_design_study_candidate is defensive: candidate-level problems
        # (missing patch, bad path, compile failure) come back as a status dict,
        # never an exception. We still guard so one unexpected raise can't abort
        # the whole batch.
        try:
            res = execute_design_study_candidate(pkg, cid, recompiler=recompiler)
        except Exception as exc:  # noqa: BLE001 - isolate one candidate's failure
            res = {
                "status": "failed",
                "candidate_id": cid,
                "execution_status": "failed",
                "recommendation": "request_user_input",
                "reason": f"{type(exc).__name__}: {exc}",
                "baseline_modified": False,
            }

        exec_status = res.get("execution_status")
        reason_codes: list[str] = []
        if res.get("status") != "ok" or exec_status in _FAILED_EXECUTION_STATUSES:
            failed += 1
            reason_codes.append("candidate_build_failed")
        elif exec_status == "rejected":
            rejected += 1
            reason_codes.append("constraint_violation")
        else:
            succeeded += 1

        results.append(
            {
                "candidate_id": res.get("candidate_id", cid),
                "status": res.get("status"),
                "execution_status": exec_status,
                "recommendation": res.get("recommendation"),
                "candidate_workspace": res.get("candidate_workspace"),
                "reason_codes": reason_codes,
            }
        )

    warnings: list[str] = []
    if skipped_ids:
        warnings.append(
            f"max_candidates ({max_candidates}) reached; skipped {len(skipped_ids)} "
            f"candidate(s). Re-run to execute the remainder."
        )

    return {
        "status": "ok",
        "requested": len(ordered),
        "executed": len(to_run),
        "succeeded": succeeded,
        "failed": failed,
        "rejected": rejected,
        "skipped": len(skipped_ids),
        "results": results,
        "skipped_candidate_ids": skipped_ids,
        "warnings": warnings,
        "baseline_modified": False,
        "claim_advancement": "none",
    }


def discover_executed_candidate_ids(package_path: str | Path) -> list[str]:
    """Return candidate ids that have a derived workspace (i.e. have been executed).

    Evaluation targets candidates that actually have a ``candidates/<cid>/``
    workspace — a proposed-but-not-executed patch has no metrics to evaluate.
    Ordered to match :func:`discover_candidate_ids` where possible, with any
    extra on-disk workspaces appended.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return []
    workspace_ids: set[str] = set()
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            for name in zf.namelist():
                if name.startswith(CANDIDATE_WORKSPACE_ROOT) and name != CANDIDATE_WORKSPACE_ROOT:
                    rest = name[len(CANDIDATE_WORKSPACE_ROOT):]
                    cid = rest.split("/", 1)[0]
                    if cid:
                        workspace_ids.add(cid)
    except Exception:  # noqa: BLE001 - unreadable package yields nothing
        return []
    if not workspace_ids:
        return []
    ordered = [cid for cid in discover_candidate_ids(pkg) if cid in workspace_ids]
    seen = set(ordered)
    for cid in sorted(workspace_ids):
        if cid not in seen:
            ordered.append(cid)
    return ordered


def run_design_study_evaluation_batch(
    package_path: str | Path,
    *,
    candidate_ids: list[str] | None = None,
    cae: bool = False,
    cae_options: dict[str, Any] | None = None,
    max_candidates: int | None = None,
    cae_evaluator: Callable[..., dict[str, Any]] | None = None,
    evaluator: Callable[[Any, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate a fixed set of executed candidates from candidate-local evidence.

    For each candidate this runs the existing single-candidate evaluator
    (``evaluate_design_study_candidate``), which normalizes mass / volume /
    max_stress / max_deflection / min_safety_factor from candidate-local
    artifacts, evaluates declared constraints, and classifies feasibility. When
    a metric is absent the evaluator records it honestly (``unknown`` constraint
    status / ``insufficient_data`` evaluation) — it never fabricates a value.

    Parameters
    ----------
    candidate_ids:
        Explicit, ordered ids to evaluate. When ``None``, all *executed*
        candidates (those with a ``candidates/<cid>/`` workspace) are evaluated.
    cae:
        When True, first run the candidate-local CAE evaluation step
        (``request_design_study_candidate_cae_evaluation``) to derive the
        candidate's CAE setup and normalize any CAE evidence, then evaluate.
        Solver execution stays disabled unless explicitly enabled via
        ``cae_options`` (and is best-effort/skipped in v0).
    cae_options:
        Forwarded kwargs for the CAE evaluation step (e.g. ``mode``,
        ``allow_solver_execution``). Ignored when ``cae`` is False.
    max_candidates:
        Optional hard cap; the remainder is reported as ``skipped``.
    cae_evaluator / evaluator:
        Injection seams for testing; default to the real backend functions.

    Returns a summary dict mirroring :func:`run_design_study_batch`:
    per-candidate ``results`` plus counts of ``complete`` / ``partial`` /
    ``insufficient_data`` / ``failed`` evaluations and a feasibility tally.
    Baseline is never modified.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {
            "status": "error",
            "code": "package_not_found",
            "message": "package not found",
            "results": [],
            "baseline_modified": False,
            "claim_advancement": "none",
        }
    if max_candidates is not None and max_candidates < 0:
        return {
            "status": "error",
            "code": "invalid_max_candidates",
            "message": "max_candidates must be a non-negative integer",
            "results": [],
            "baseline_modified": False,
            "claim_advancement": "none",
        }
    if candidate_ids is not None and not isinstance(candidate_ids, (list, tuple)):
        return {
            "status": "error",
            "code": "invalid_candidate_ids",
            "message": "candidate_ids must be a list of strings",
            "results": [],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

    if evaluator is None:
        from aieng.converters.design_study_evaluation import evaluate_design_study_candidate as evaluator  # noqa: E501
    if cae and cae_evaluator is None:
        from aieng.converters.design_study_cae_evaluation import (
            request_design_study_candidate_cae_evaluation as cae_evaluator,
        )

    requested = (
        candidate_ids if candidate_ids is not None else discover_executed_candidate_ids(pkg)
    )
    ordered: list[str] = []
    seen: set[str] = set()
    for cid in requested:
        if isinstance(cid, str) and cid and cid not in seen:
            seen.add(cid)
            ordered.append(cid)

    if not ordered:
        return {
            "status": "ok",
            "requested": 0,
            "evaluated": 0,
            "complete": 0,
            "partial": 0,
            "insufficient_data": 0,
            "failed": 0,
            "skipped": 0,
            "feasibility": {},
            "results": [],
            "skipped_candidate_ids": [],
            "warnings": ["no executed candidates found to evaluate — run opt.run_candidates first"],
            "baseline_modified": False,
            "claim_advancement": "none",
        }

    to_run = ordered
    skipped_ids: list[str] = []
    if max_candidates is not None and len(ordered) > max_candidates:
        to_run = ordered[:max_candidates]
        skipped_ids = ordered[max_candidates:]

    results: list[dict[str, Any]] = []
    complete = partial = insufficient = failed = 0
    feasibility_tally: dict[str, int] = {}

    for cid in to_run:
        reason_codes: list[str] = []
        cae_status: str | None = None
        try:
            if cae:
                cae_res = cae_evaluator(pkg, cid, **(cae_options or {})) or {}
                cae_status = cae_res.get("status")
            res = evaluator(pkg, cid) or {}
        except Exception as exc:  # noqa: BLE001 - isolate one candidate's failure
            failed += 1
            results.append(
                {
                    "candidate_id": cid,
                    "status": "failed",
                    "evaluation_status": "failed",
                    "feasibility": "unknown",
                    "confidence": "low",
                    "cae_status": cae_status,
                    "reason_codes": ["candidate_evaluation_failed"],
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        eval_status = res.get("evaluation_status")
        feasibility = res.get("feasibility", "unknown")
        feasibility_tally[feasibility] = feasibility_tally.get(feasibility, 0) + 1

        if res.get("status") == "failed":
            failed += 1
            reason_codes.append("candidate_evaluation_failed")
        elif eval_status == "complete":
            complete += 1
        elif eval_status == "partial":
            partial += 1
            reason_codes.append("missing_metric")
        else:  # insufficient_data
            insufficient += 1
            reason_codes.append("missing_metric")

        results.append(
            {
                "candidate_id": res.get("candidate_id", cid),
                "status": res.get("status"),
                "evaluation_status": eval_status,
                "feasibility": feasibility,
                "confidence": res.get("confidence"),
                "cae_status": cae_status,
                "reason_codes": reason_codes,
            }
        )

    warnings: list[str] = []
    if skipped_ids:
        warnings.append(
            f"max_candidates ({max_candidates}) reached; skipped {len(skipped_ids)} "
            f"candidate(s). Re-run to evaluate the remainder."
        )
    if insufficient or partial:
        warnings.append(
            "some candidates have missing CAE metrics; their constraints/feasibility are "
            "recorded as unknown rather than fabricated. Run opt.evaluate_candidates with "
            "cae=true (or provide solver evidence) to complete them."
        )

    return {
        "status": "ok",
        "requested": len(ordered),
        "evaluated": len(to_run),
        "complete": complete,
        "partial": partial,
        "insufficient_data": insufficient,
        "failed": failed,
        "skipped": len(skipped_ids),
        "feasibility": feasibility_tally,
        "results": results,
        "skipped_candidate_ids": skipped_ids,
        "warnings": warnings,
        "baseline_modified": False,
        "claim_advancement": "none",
    }
