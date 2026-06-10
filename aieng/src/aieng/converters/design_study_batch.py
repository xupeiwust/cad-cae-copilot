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
