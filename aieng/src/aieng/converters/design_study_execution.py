"""Design study candidate EXECUTION into a derived workspace (v0, PR2).

Safely applies a VALIDATED design-study candidate patch into a derived candidate workspace,
optionally recompiles/evaluates it through an injected recompiler, and records the iteration.

Hard safety contract:
  - The baseline geometry is NEVER overwritten (geometry/shape_ir.json,
    parts/<pid>/geometry/shape_ir.json, and other baseline artifacts are untouched).
  - No candidate is ever auto-accepted/promoted into the baseline.
  - No optimization/search, no autonomous loop — exactly one explicitly-requested candidate runs.
  - Compile/evaluation is OPTIONAL and injected: with no recompiler, evaluation is honestly partial.
    The recompiler MUST operate on a throwaway copy; this module only ADDS candidates/<id>/* members
    plus the iteration/report diagnostics to the package.

Derived workspace layout (candidate_id is path-sanitized):
  candidates/<id>/patch.json
  candidates/<id>/geometry/shape_ir.json                         (single-part)
  candidates/<id>/parts/<selected_part_id>/geometry/shape_ir.json (assembly part-scoped)
  candidates/<id>/provenance/candidate.json
  candidates/<id>/provenance/geometry_execution_manifest.json    (when compiled)
  candidates/<id>/diagnostics/verification.json                  (when compiled)
  candidates/<id>/analysis/evaluation.json
"""
from __future__ import annotations

import copy
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

from aieng import FORMAT_VERSION
from aieng.converters.design_study import (
    DESIGN_STUDY_PROBLEM_PATH,
    validate_design_candidate_patch,
    validate_design_study_problem,
)

DESIGN_CANDIDATES_DIR = "patches/design_candidates/"
CANDIDATE_WORKSPACE_ROOT = "candidates/"
DESIGN_STUDY_ITERATIONS_PATH = "analysis/design_study_iterations.json"
DESIGN_STUDY_REPORT_PATH = "diagnostics/design_study_report.json"
BASELINE_SHAPE_IR_PATH = "geometry/shape_ir.json"

# execution status ladder (furthest reached wins)
EXEC_VALIDATED = "validated"
EXEC_REJECTED = "rejected"
EXEC_PATCH_APPLIED = "patch_applied"
EXEC_COMPILE_SUCCEEDED = "compile_succeeded"
EXEC_COMPILE_FAILED = "compile_failed"
EXEC_EVAL_PARTIAL = "evaluation_partial"
EXEC_EVAL_COMPLETE = "evaluation_complete"

# conservative recommendation vocabulary
REC_NEEDS_MORE = "needs_more_evaluation"
REC_REJECT = "reject_candidate"
REC_REFINE = "refine_candidate"
REC_REQUEST_INPUT = "request_user_input"
REC_COMPILE_FAILED = "compile_failed"


def _sanitize_id(cid: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(cid or "candidate"))
    return s.strip("._") or "candidate"


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


# ── Shape IR path resolution (path declared by the design study variable) ─────

def _path_tokens(path: str) -> list[str]:
    raw = str(path or "").strip().lstrip("#").strip("/")
    if not raw:
        return []
    sep = "/" if "/" in raw else "."
    tokens = [t for t in raw.split(sep) if t != ""]
    if tokens and tokens[0] in ("shape_ir", "geometry"):
        tokens = tokens[1:]
    return tokens


def _as_index(token: str) -> int | None:
    try:
        return int(token)
    except (TypeError, ValueError):
        return None


def _set_by_path(doc: Any, path: str, value: Any) -> bool:
    """Set an EXISTING path in the Shape IR doc. Returns False (fails safely) if the path
    does not already resolve — never creates new keys/indices."""
    tokens = _path_tokens(path)
    if not tokens:
        return False
    cur = doc
    for tok in tokens[:-1]:
        if isinstance(cur, dict) and tok in cur:
            cur = cur[tok]
        elif isinstance(cur, list) and _as_index(tok) is not None and 0 <= _as_index(tok) < len(cur):
            cur = cur[_as_index(tok)]
        else:
            return False
    last = tokens[-1]
    if isinstance(cur, dict):
        if last not in cur:
            return False
        cur[last] = value
        return True
    if isinstance(cur, list):
        i = _as_index(last)
        if i is None or not (0 <= i < len(cur)):
            return False
        cur[i] = value
        return True
    return False


# ── package readers ───────────────────────────────────────────────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def _baseline_shape_ir_ref(problem: dict[str, Any], candidate: dict[str, Any],
                           names: set[str]) -> str:
    """Part-scoped studies edit the selected part's Shape IR; else the package Shape IR."""
    part = candidate.get("selected_part_id") or problem.get("selected_part_id")
    if part and problem.get("assembly_aware"):
        part_path = f"parts/{part}/{BASELINE_SHAPE_IR_PATH}"
        if part_path in names:
            return part_path
    return BASELINE_SHAPE_IR_PATH


# ── iteration + report bookkeeping ────────────────────────────────────────────

def _append_iteration(zf_names_iters: Any, record: dict[str, Any]) -> dict[str, Any]:
    iters = zf_names_iters if isinstance(zf_names_iters, dict) else {}
    existing = iters.get("iterations") if isinstance(iters.get("iterations"), list) else []
    record["iteration_id"] = f"iter_{len(existing) + 1:03d}"
    existing.append(record)
    return {
        "format": "aieng.design_study_iterations", "format_version": FORMAT_VERSION,
        "schema_version": "0.1", "iterations": existing,
        "provenance": {"created_by": "aieng.design_study_execution", "baseline_modified": False,
                       "autonomous_loop": False},
    }


def _build_report(iterations_doc: dict[str, Any], problem_status: str) -> dict[str, Any]:
    iters = iterations_doc.get("iterations") or []
    by_exec: dict[str, int] = {}
    by_rec: dict[str, int] = {}
    for it in iters:
        by_exec[it.get("execution_status")] = by_exec.get(it.get("execution_status"), 0) + 1
        by_rec[it.get("recommendation")] = by_rec.get(it.get("recommendation"), 0) + 1
    return {
        "format": "aieng.design_study_report", "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "problem_status": problem_status,
        "iteration_count": len(iters),
        "by_execution_status": by_exec,
        "by_recommendation": by_rec,
        "candidates": [{"iteration_id": it.get("iteration_id"), "candidate_id": it.get("candidate_id"),
                        "execution_status": it.get("execution_status"),
                        "recommendation": it.get("recommendation"),
                        "workspace": it.get("candidate_workspace")} for it in iters],
        "limitations": [
            "Candidate execution is explicit and single-shot; no optimizer/search/Pareto loop.",
            "Compile/evaluation may be partial. Baseline geometry is never overwritten, and no "
            "candidate is auto-accepted into the baseline.",
        ],
        "provenance": {"created_by": "aieng.design_study_execution", "baseline_modified": False},
    }


# ── main entry ─────────────────────────────────────────────────────────────────

def execute_design_study_candidate(
    package_path: str | Path,
    candidate_id: str,
    *,
    recompiler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute ONE validated candidate into a derived workspace. Never mutates baseline.

    ``recompiler(candidate_shape_ir, context) -> dict`` is OPTIONAL; when omitted, evaluation is
    honestly partial. It must return e.g. ``{"compile_status": "compile_succeeded"|"compile_failed",
    "geometry_execution": {...}|None, "verification": {...}|None, "metrics": {...}, "errors": [...],
    "warnings": [...]}`` and MUST work on a throwaway copy (never the baseline).
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "failed", "reason": "package not found"}
    sid = _sanitize_id(candidate_id)
    cand_member = f"{DESIGN_CANDIDATES_DIR}{sid}.json"
    ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            candidate = _read_json(zf, cand_member, names)
            iters_doc = _read_json(zf, DESIGN_STUDY_ITERATIONS_PATH, names) or {}
            baseline_ref = _baseline_shape_ir_ref(problem or {}, candidate or {}, names)
            baseline_shape_ir = _read_json(zf, baseline_ref, names)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    if problem is None:
        return _finish(package_path, iters_doc, "missing", {
            "candidate_id": sid, "execution_status": "failed", "recommendation": REC_REQUEST_INPUT,
            "errors": ["analysis/design_study_problem.json is missing or invalid"],
            "warnings": [], "baseline_modified": False, "candidate_workspace": None,
        }, extra={"design_study_present": False})
    if candidate is None:
        return _finish(package_path, iters_doc, validate_design_study_problem(problem)["status"], {
            "candidate_id": sid, "execution_status": "failed", "recommendation": REC_REQUEST_INPUT,
            "errors": [f"candidate '{sid}' not found at {cand_member}"],
            "warnings": [], "baseline_modified": False, "candidate_workspace": None,
        })

    problem_status = validate_design_study_problem(problem)["status"]
    validation = validate_design_candidate_patch(problem, candidate)
    reasoning = candidate.get("reasoning")
    base_record = {
        "candidate_id": sid,
        "proposed_by": candidate.get("provenance", {}).get("proposed_by")
        if isinstance(candidate.get("provenance"), dict) else None,
        "reasoning_summary": (str(reasoning)[:200] if reasoning else None),
        "validation_status": validation["status"],
        "candidate_workspace": ws,
        "baseline_modified": False,
        "errors": list(validation.get("errors") or []),
        "warnings": list(validation.get("warnings") or []),
    }

    # ── rejected: record, do NOT apply / do NOT create geometry ──────────────
    if validation["status"] == "rejected":
        base_record.update(execution_status=EXEC_REJECTED, recommendation=REC_REJECT,
                           applied_changes=[], candidate_workspace=None)
        return _finish(package_path, iters_doc, problem_status, base_record)

    # ── valid: apply patch to a DERIVED copy of the baseline Shape IR ────────
    if not isinstance(baseline_shape_ir, dict):
        base_record.update(execution_status="failed", recommendation=REC_REQUEST_INPUT,
                           applied_changes=[], candidate_workspace=None,
                           errors=base_record["errors"] + [f"baseline Shape IR not found at {baseline_ref}"])
        return _finish(package_path, iters_doc, problem_status, base_record)

    derived = copy.deepcopy(baseline_shape_ir)
    applied_changes = []
    any_path_failed = False
    for ch in validation.get("normalized_changes") or []:
        ok = _set_by_path(derived, ch.get("path"), ch.get("new_value"))
        if not ok:
            any_path_failed = True
        applied_changes.append({
            "variable_id": ch.get("variable_id"), "path": ch.get("path"),
            "old_value": ch.get("old_value"), "new_value": ch.get("new_value"),
            "status": "applied" if ok else "path_not_found",
        })

    if any_path_failed:
        # baseline untouched, no derived geometry written — author must fix the path
        base_record.update(execution_status="failed", recommendation=REC_REQUEST_INPUT,
                           applied_changes=applied_changes, candidate_workspace=None,
                           errors=base_record["errors"] + ["one or more variable paths not found in Shape IR"])
        return _finish(package_path, iters_doc, problem_status, base_record)

    # derived geometry path inside the candidate workspace
    part = candidate.get("selected_part_id") or problem.get("selected_part_id")
    if part and problem.get("assembly_aware") and baseline_ref.startswith("parts/"):
        derived_geom_member = f"{ws}parts/{part}/{BASELINE_SHAPE_IR_PATH}"
    else:
        derived_geom_member = f"{ws}{BASELINE_SHAPE_IR_PATH}"

    provenance = {
        "format": "aieng.design_study_candidate_provenance", "format_version": FORMAT_VERSION,
        "based_on_problem": DESIGN_STUDY_PROBLEM_PATH,
        "based_on_candidate_patch": cand_member,
        "baseline_shape_ir_ref": baseline_ref,
        "selected_part_id": part,
        "source_ir_node": (baseline_shape_ir.get("id")
                           or (baseline_shape_ir.get("parts") or [{}])[0].get("id")
                           if isinstance(baseline_shape_ir.get("parts"), list) else None),
        "applied_changes": applied_changes,
        "baseline_modified": False,
        "derived_workspace_only": True,
    }

    members = {
        f"{ws}patch.json": _dumps(candidate),
        derived_geom_member: _dumps(derived),
        f"{ws}provenance/candidate.json": _dumps(provenance),
    }

    execution_status = EXEC_PATCH_APPLIED
    recommendation = REC_NEEDS_MORE
    evaluation: dict[str, Any] = {
        "format": "aieng.design_study_candidate_evaluation", "format_version": FORMAT_VERSION,
        "evaluation_status": "partial", "compile_status": "skipped",
        "metrics": {}, "errors": [], "warnings": [],
        "reason": "no recompiler provided — compile/evaluation skipped (honest partial)",
        "baseline_modified": False,
    }

    # ── optional compile/evaluation via injected recompiler (throwaway copy) ─
    if recompiler is not None:
        try:
            res = recompiler(derived, {"candidate_id": sid, "selected_part_id": part,
                                       "baseline_ref": baseline_ref}) or {}
        except Exception as exc:  # noqa: BLE001 - recompiler must never break execution
            res = {"compile_status": "compile_failed", "errors": [f"{type(exc).__name__}: {exc}"]}
        compile_status = res.get("compile_status") or "compile_failed"
        metrics = res.get("metrics") or {}
        ge = res.get("geometry_execution")
        verification = res.get("verification")
        regression_diff = res.get("regression_diff")
        evaluation.update(compile_status=compile_status, metrics=metrics,
                          errors=list(res.get("errors") or []), warnings=list(res.get("warnings") or []))
        if regression_diff is not None:
            evaluation["regression_diff"] = regression_diff
        if ge is not None:
            members[f"{ws}provenance/geometry_execution_manifest.json"] = _dumps(ge)
        if verification is not None:
            members[f"{ws}diagnostics/verification.json"] = _dumps(verification)

        if compile_status == "compile_succeeded":
            execution_status = EXEC_COMPILE_SUCCEEDED
            # conservative: only "complete" if we actually have a usable objective metric
            has_metric = bool(metrics) and any(
                v is not None for k, v in metrics.items() if k not in ("executed",))
            if has_metric:
                evaluation["evaluation_status"] = "complete"
                execution_status = EXEC_EVAL_COMPLETE
                recommendation = REC_REFINE   # never auto-accept in v0
            else:
                evaluation["evaluation_status"] = "partial"
                recommendation = REC_NEEDS_MORE
            evaluation["reason"] = "candidate compiled in an isolated workspace; baseline untouched"
        else:
            execution_status = EXEC_COMPILE_FAILED
            recommendation = REC_COMPILE_FAILED
            evaluation["evaluation_status"] = "failed"
            evaluation["reason"] = "candidate compile failed (baseline untouched)"

    members[f"{ws}analysis/evaluation.json"] = _dumps(evaluation)

    base_record.update(
        execution_status=execution_status,
        recommendation=recommendation,
        applied_changes=applied_changes,
        compile_status=evaluation.get("compile_status"),
        evaluation_status=evaluation.get("evaluation_status"),
        metrics=evaluation.get("metrics", {}),
    )
    return _finish(package_path, iters_doc, problem_status, base_record, extra_members=members)


def _finish(package_path: Path, iters_doc: dict[str, Any], problem_status: str,
            record: dict[str, Any], *, extra_members: dict[str, bytes] | None = None,
            extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append the iteration, rebuild the report, and atomically write all new members."""
    record.setdefault("metrics", {})
    iterations_doc = _append_iteration(iters_doc, record)
    report = _build_report(iterations_doc, problem_status)
    members = dict(extra_members or {})
    members[DESIGN_STUDY_ITERATIONS_PATH] = _dumps(iterations_doc)
    members[DESIGN_STUDY_REPORT_PATH] = _dumps(report)

    tmp = package_path.with_suffix(".dsexec.tmp.aieng")
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

    result = {
        "status": "ok",
        "candidate_id": record.get("candidate_id"),
        "iteration_id": record.get("iteration_id"),
        "execution_status": record.get("execution_status"),
        "recommendation": record.get("recommendation"),
        "candidate_workspace": record.get("candidate_workspace"),
        "baseline_modified": False,
    }
    if extra:
        result.update(extra)
    return result
