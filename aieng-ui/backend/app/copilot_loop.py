"""Closed-loop Copilot stepper state and thin orchestration.

This module intentionally composes existing runtime tools and package
inspection helpers. It does not introduce a CAD adapter, solver, optimizer, or
claim-advancement path.
"""

from __future__ import annotations

import difflib
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import runtime as _rt
from .config import Settings, now_iso, read_json, write_json
from .package_inspection import (
    _generate_cad_recommendations_with_verification,
    _generate_cae_preprocessing_summary,
    _generate_cae_result_summary,
    read_package_json,
)
from .project_io import (
    project_dir,
    resolve_project_path,
    get_project,
    write_artifact_to_package,
)


LOOP_STATUS_VALUES = {
    "not_started",
    "running",
    "waiting_for_approval",
    "completed",
    "skipped",
    "partial",
    "error",
}


STEP_DEFS: list[dict[str, Any]] = [
    {
        "id": "inspect_evidence",
        "title": "Inspect package evidence",
        "kind": "read_only",
        "requiresApproval": False,
        "summary": "Read existing .aieng evidence, summaries, metrics, and stale-status markers.",
        "limitation": "Read-only inspection does not validate engineering correctness.",
    },
    {
        "id": "recommend_modification",
        "title": "Recommend CAD modification",
        "kind": "read_only",
        "requiresApproval": False,
        "summary": "Generate ranked CAD modification hypotheses from available metrics, targets, and feature evidence.",
        "limitation": "Recommendations are hypotheses, not solver evidence.",
    },
    {
        "id": "verify_proposal",
        "title": "Verify proposal",
        "kind": "review",
        "requiresApproval": False,
        "summary": "Run pre-execution checks before any CAD mutation.",
        "limitation": "Verification is heuristic and does not replace re-simulation or human review.",
    },
    {
        "id": "apply_cad_edit",
        "title": "Approve/apply CAD parameter edit",
        "kind": "mutation",
        "requiresApproval": True,
        "summary": "Submit the chosen parameter change to the approval-gated runtime.",
        "limitation": "Only declared parameter edits are supported; topology-changing edits are out of scope.",
    },
    {
        "id": "mark_stale",
        "title": "Mark stale downstream artifacts",
        "kind": "postprocess",
        "requiresApproval": False,
        "summary": "Show geometry-dependent artifacts that require revalidation after the CAD edit.",
        "limitation": "Old solver results remain in the package for audit but must not validate the new geometry.",
    },
    {
        "id": "prepare_solver",
        "title": "Prepare mesh / solver run",
        "kind": "read_only",
        "requiresApproval": False,
        "summary": "Run solver preflight and list missing mesh/setup/input-deck/runtime requirements.",
        "limitation": "Preflight does not execute a solver and does not prove physical correctness.",
    },
    {
        "id": "run_mesh_solver",
        "title": "Run mesh / solver",
        "kind": "expensive",
        "requiresApproval": True,
        "summary": "Run an approval-gated mesh or solver operation when the package is ready.",
        "limitation": "Missing Gmsh/CalculiX is reported honestly; success is not faked.",
    },
    {
        "id": "extract_results",
        "title": "Extract solver results",
        "kind": "postprocess",
        "requiresApproval": False,
        "summary": "Extract available FRD result metrics into computed_metrics.json.",
        "limitation": "Only supported fields/formats are extracted; unavailable result files are skipped.",
    },
    {
        "id": "refresh_summary",
        "title": "Refresh CAE summary",
        "kind": "postprocess",
        "requiresApproval": False,
        "summary": "Regenerate CAE summary/evidence artifacts from current package contents.",
        "limitation": "Summary refresh is derived bookkeeping, not engineering certification.",
    },
    {
        "id": "compare_targets",
        "title": "Compare design targets",
        "kind": "review",
        "requiresApproval": False,
        "summary": "Compare before/after metrics and target status when evidence is available.",
        "limitation": "Target comparison is based on available computed metrics and does not certify the design.",
    },
    {
        "id": "generate_report",
        "title": "Generate loop report",
        "kind": "review",
        "requiresApproval": False,
        "summary": "Write an evidence-backed loop report with warnings and claim boundaries.",
        "limitation": "The report does not advance engineering claims automatically.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loop_dir(settings: Settings, project_id: str) -> Path:
    return project_dir(settings, project_id) / "copilot_loops"


def _loop_path(settings: Settings, project_id: str, loop_id: str) -> Path:
    return _loop_dir(settings, project_id) / f"{loop_id}.json"


def _resolve_package(settings: Settings, project_id: str) -> Path:
    project = get_project(settings, project_id)
    pkg = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg is None or not pkg.exists():
        raise HTTPException(status_code=404, detail="project has no .aieng package")
    return pkg


def _new_step(defn: dict[str, Any]) -> dict[str, Any]:
    return {
        **defn,
        "status": "not_started",
        "artifacts": [],
        "warnings": [],
        "errors": [],
        "toolCalls": [],
        "updated_at": None,
    }


def _save_loop(settings: Settings, project_id: str, loop: dict[str, Any]) -> dict[str, Any]:
    loop["updated_at"] = now_iso()
    write_json(_loop_path(settings, project_id, loop["loop_id"]), loop)
    return loop


def load_loop(settings: Settings, project_id: str, loop_id: str) -> dict[str, Any]:
    path = _loop_path(settings, project_id, loop_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="copilot loop not found")
    return read_json(path, {})


def _decision_for_loop(loop: dict[str, Any]) -> str:
    """Derive an approval decision label for the apply_cad_edit step.

    Returns one of: "approved", "rejected", "blocked", "pending", "none".
    The decision is a UI label, not an engineering claim.
    """
    context = loop.get("context") or {}
    if context.get("apply_rejected"):
        return "rejected"
    apply_step = next(
        (s for s in (loop.get("steps") or []) if s.get("id") == "apply_cad_edit"),
        None,
    )
    if not apply_step:
        return "none"
    status = apply_step.get("status")
    if status == "completed":
        return "approved"
    if status == "waiting_for_approval":
        return "pending"
    if status == "skipped":
        # No proposal / verification failed / no executable change.
        summary = (apply_step.get("summary") or "").lower()
        if "verification failed" in summary or "blocked" in summary:
            return "blocked"
        return "none"
    if status == "error":
        return "error"
    return "none"


def _proposal_summary_for_loop(loop: dict[str, Any]) -> dict[str, Any] | None:
    proposal = (loop.get("context") or {}).get("selected_proposal")
    if not isinstance(proposal, dict):
        return None
    change = proposal.get("parameter_change") or {}
    return {
        "proposal_id": proposal.get("proposal_id"),
        "feature_ref": proposal.get("feature_ref"),
        "action_type": proposal.get("action_type"),
        "parameter_name": change.get("name"),
        "parameter_from": change.get("from"),
        "parameter_to": change.get("to"),
        "rationale": proposal.get("rationale"),
    }


def _verification_status_for_loop(loop: dict[str, Any]) -> str | None:
    """Verification verdict: "pass" | "warn" | "fail" | "skipped" | None."""
    for step in loop.get("steps") or []:
        if step.get("id") != "verify_proposal":
            continue
        if step.get("status") == "skipped":
            return "skipped"
        verdict = ((step.get("data") or {}).get("verdict") or {}).get("verdict")
        if verdict:
            return str(verdict)
        return None
    return None


def _metric_summary_for_loop(loop: dict[str, Any]) -> dict[str, Any] | None:
    """Summarize before/after metric deltas if any.

    Returns counts by direction. Returns None when no comparison was produced
    so the UI can honestly render "Not available".
    """
    comparison = (loop.get("context") or {}).get("metric_comparison") or {}
    metrics = comparison.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        return None
    counts = {"improved": 0, "regressed": 0, "unchanged": 0, "unknown": 0, "total": 0}
    for row in metrics:
        if not isinstance(row, dict):
            continue
        direction = str(row.get("direction") or "unknown")
        counts["total"] += 1
        if direction == "improved":
            counts["improved"] += 1
        elif direction == "regressed":
            counts["regressed"] += 1
        elif direction == "unchanged":
            counts["unchanged"] += 1
        else:
            counts["unknown"] += 1
    return counts


def _target_summary_for_loop(loop: dict[str, Any]) -> dict[str, Any] | None:
    """Counts of design target comparison statuses, or None if unavailable."""
    after = (loop.get("context") or {}).get("after") or {}
    targets = after.get("design_target_comparisons")
    items: list[Any] = []
    if isinstance(targets, dict):
        items = list(targets.get("items") or [])
    elif isinstance(targets, list):
        items = list(targets)
    if not items:
        return None
    counts = {"pass": 0, "fail": 0, "unknown": 0, "not_evaluated": 0, "total": 0}
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        counts["total"] += 1
        if status in counts:
            counts[status] += 1
        else:
            counts["unknown"] += 1
    return counts


def _stale_artifact_count_for_loop(loop: dict[str, Any]) -> int:
    context = loop.get("context") or {}
    stale = context.get("stale_artifacts") or []
    if stale:
        return len([s for s in stale if s])
    mark_stale = next(
        (s for s in (loop.get("steps") or []) if s.get("id") == "mark_stale"),
        None,
    )
    if mark_stale:
        artifacts = mark_stale.get("artifacts") or []
        return len([a for a in artifacts if isinstance(a, dict)])
    return 0


def _report_path_for_loop(loop: dict[str, Any]) -> str | None:
    report = (loop.get("context") or {}).get("report")
    if isinstance(report, dict):
        path = report.get("artifact_path")
        if path:
            return str(path)
    return None


def _build_loop_summary(loop: dict[str, Any]) -> dict[str, Any]:
    """Derive the list-endpoint summary from a persisted loop document.

    Every field tolerates missing/legacy context. Anything we cannot derive is
    `None` so the UI can render "Unknown" honestly.
    """
    steps = loop.get("steps") or []
    terminal = {"completed", "skipped", "partial", "error"}
    terminal_count = sum(1 for s in steps if s.get("status") in terminal)
    waiting = any(s.get("status") == "waiting_for_approval" for s in steps)
    warning_count = sum(len(s.get("warnings") or []) for s in steps if isinstance(s, dict))
    error_count = sum(len(s.get("errors") or []) for s in steps if isinstance(s, dict))
    return {
        "schema_version": loop.get("schema_version"),
        "loop_id": loop.get("loop_id"),
        "status": loop.get("status"),
        "created_at": loop.get("created_at"),
        "updated_at": loop.get("updated_at"),
        "current_step_id": loop.get("current_step_id"),
        "step_total": len(steps),
        "step_terminal_count": terminal_count,
        "waiting_for_approval": waiting,
        "decision": _decision_for_loop(loop),
        "proposal_summary": _proposal_summary_for_loop(loop),
        "verification_status": _verification_status_for_loop(loop),
        "report_path": _report_path_for_loop(loop),
        "stale_artifact_count": _stale_artifact_count_for_loop(loop),
        "warning_count": warning_count,
        "error_count": error_count,
        "metric_summary": _metric_summary_for_loop(loop),
        "target_summary": _target_summary_for_loop(loop),
        "strictness": loop.get("strictness"),
    }


def list_loops(settings: Settings, project_id: str) -> dict[str, Any]:
    """Return persisted loops for a project, newest first.

    The summary is derived from the persisted loop document; no migration of
    the on-disk format is required for older loops. Fields that cannot be
    derived are `None` so the UI can render "Unknown" honestly.
    """
    loop_dir = _loop_dir(settings, project_id)
    summaries: list[dict[str, Any]] = []
    if loop_dir.exists():
        for path in loop_dir.glob("*.json"):
            try:
                loop = read_json(path, {})
            except Exception:
                continue
            if not isinstance(loop, dict) or not loop.get("loop_id"):
                continue
            summaries.append(_build_loop_summary(loop))
    summaries.sort(key=lambda s: s.get("updated_at") or s.get("created_at") or "", reverse=True)
    return {"loops": summaries}


def start_loop(settings: Settings, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    package_path = _resolve_package(settings, project_id)
    loop_id = uuid.uuid4().hex[:12]
    loop = {
        "schema_version": "0.1",
        "loop_id": loop_id,
        "project_id": project_id,
        "package_path": str(package_path),
        "status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "strictness": payload.get("strictness") or "default",
        "selected_proposal_id": payload.get("proposal_id"),
        "current_step_id": "inspect_evidence",
        "steps": [_new_step(s) for s in STEP_DEFS],
        "context": {
            "baseline": _read_metrics_snapshot(package_path, settings=settings, project_id=project_id),
            "claim_boundary": {
                "claims_advanced": False,
                "claim_advancement_requires_explicit_workflow": True,
            },
        },
    }
    _loop_dir(settings, project_id).mkdir(parents=True, exist_ok=True)
    return _save_loop(settings, project_id, loop)


def _find_step(loop: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in loop.get("steps", []):
        if step.get("id") == step_id:
            return step
    raise HTTPException(status_code=500, detail=f"missing loop step: {step_id}")


def _next_step(loop: dict[str, Any]) -> dict[str, Any] | None:
    for step in loop.get("steps", []):
        if step.get("status") == "not_started":
            return step
        if step.get("status") == "waiting_for_approval":
            return step
    return None


def _set_step(
    step: dict[str, Any],
    status: str,
    *,
    summary: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    if status not in LOOP_STATUS_VALUES:
        raise ValueError(f"invalid step status: {status}")
    step["status"] = status
    step["updated_at"] = _now()
    if summary is not None:
        step["summary"] = summary
    if warnings is not None:
        step["warnings"] = warnings
    if errors is not None:
        step["errors"] = errors
    if artifacts is not None:
        step["artifacts"] = artifacts
    if tool_calls is not None:
        step["toolCalls"] = tool_calls
    if data is not None:
        step["data"] = data


def advance_loop(settings: Settings, project_id: str, loop_id: str) -> dict[str, Any]:
    loop = load_loop(settings, project_id, loop_id)
    package_path = _resolve_package(settings, project_id)
    loop["package_path"] = str(package_path)
    step = _next_step(loop)
    if step is None:
        loop["status"] = "completed"
        loop["current_step_id"] = None
        return _save_loop(settings, project_id, loop)
    if step.get("status") == "waiting_for_approval":
        loop["current_step_id"] = step.get("id")
        return _save_loop(settings, project_id, loop)

    step_id = step["id"]
    loop["current_step_id"] = step_id
    _set_step(step, "running")

    handlers = {
        "inspect_evidence": _advance_inspect,
        "recommend_modification": _advance_recommend,
        "verify_proposal": _advance_verify,
        "apply_cad_edit": _advance_apply,
        "mark_stale": _advance_mark_stale,
        "prepare_solver": _advance_prepare_solver,
        "run_mesh_solver": _advance_run_mesh_solver,
        "extract_results": _advance_extract_results,
        "refresh_summary": _advance_refresh_summary,
        "compare_targets": _advance_compare_targets,
        "generate_report": _advance_generate_report,
    }
    try:
        handlers[step_id](settings, project_id, package_path, loop, step)
    except HTTPException:
        # Re-raise FastAPI errors so the caller sees a real HTTP status; persist
        # nothing partial — the step stays "running" in memory only.
        raise
    except Exception as exc:  # noqa: BLE001 — convert handler failures to honest step errors
        _set_step(
            step,
            "error",
            summary=f"Step '{step_id}' raised an unexpected exception.",
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    if step.get("status") == "running":
        # Defensive: a handler returned without setting a terminal status. Mark
        # it as error rather than leak "running" into the persisted state.
        _set_step(
            step,
            "error",
            summary=f"Step '{step_id}' completed without reporting a status.",
            errors=["handler returned without setting step status"],
        )

    upcoming = _next_step(loop)
    loop["current_step_id"] = upcoming.get("id") if upcoming else None
    if all(s.get("status") in {"completed", "skipped", "partial", "error"} for s in loop.get("steps", [])):
        loop["status"] = "completed"
    return _save_loop(settings, project_id, loop)


def approve_loop(settings: Settings, project_id: str, loop_id: str) -> dict[str, Any]:
    loop = load_loop(settings, project_id, loop_id)
    step = next((s for s in loop.get("steps", []) if s.get("status") == "waiting_for_approval"), None)
    if step is None:
        raise HTTPException(status_code=409, detail="loop is not waiting for approval")
    run_id = _step_run_id(step)
    if not run_id:
        raise HTTPException(status_code=409, detail="approval step has no runtime run")
    run = _rt.resume_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    _apply_run_outcome_to_step(loop, step, _rt.run_to_dict(run), approved=True)
    return _save_loop(settings, project_id, loop)


def reject_loop(settings: Settings, project_id: str, loop_id: str) -> dict[str, Any]:
    loop = load_loop(settings, project_id, loop_id)
    step = next((s for s in loop.get("steps", []) if s.get("status") == "waiting_for_approval"), None)
    if step is None:
        raise HTTPException(status_code=409, detail="loop is not waiting for approval")
    run_id = _step_run_id(step)
    if run_id:
        run = _rt.reject_run(run_id)
        run_dict = _rt.run_to_dict(run) if run is not None else None
    else:
        run_dict = None
    _set_step(
        step,
        "skipped",
        summary="User rejected approval; operation was not executed.",
        warnings=["reason=user_rejected"],
        tool_calls=[{"toolName": _step_tool_name(step), "status": "rejected", "runId": run_id}],
        data={"runtime_run": run_dict, "reason": "user_rejected"},
    )
    if step["id"] == "apply_cad_edit":
        loop.setdefault("context", {})["apply_rejected"] = True
    return _save_loop(settings, project_id, loop)


def get_report(settings: Settings, project_id: str, loop_id: str) -> dict[str, Any]:
    loop = load_loop(settings, project_id, loop_id)
    report = loop.get("context", {}).get("report")
    if not report:
        raise HTTPException(status_code=404, detail="loop report not generated")
    return report


_CLAIM_BOUNDARY_DIFF_NOTE = (
    "This report diff is a review aid. It does not certify either design, does "
    "not advance engineering claims, and does not interpret missing report "
    "content. A qualified engineer must review the underlying reports and "
    "evidence."
)


_CLAIM_BOUNDARY_EXPORT_NOTE = (
    "This decision review export is a reviewable record of one or two Copilot "
    "loops. It does not certify either design, does not advance engineering "
    "claims, and must be reviewed by a qualified engineer before being cited "
    "in any acceptance decision."
)


def _highlight(
    *,
    id: str,
    label: str,
    left: Any,
    right: Any,
    status: str,
    severity: str = "info",
    summary: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "status": status,
        "severity": severity,
        "left": None if left is None else str(left),
        "right": None if right is None else str(right),
        "summary": summary,
    }


def _proposal_to_string(proposal: dict[str, Any] | None) -> str | None:
    if not proposal:
        return None
    feature = proposal.get("feature_ref") or "?"
    action = proposal.get("action_type") or "?"
    pname = proposal.get("parameter_name") or "?"
    pfrom = proposal.get("parameter_from")
    pto = proposal.get("parameter_to")
    return f"{feature}/{action}/{pname}:{pfrom}->{pto}"


def _metric_summary_to_string(summary: dict[str, Any] | None) -> str | None:
    if not summary or not summary.get("total"):
        return None
    return (
        f"{summary.get('improved', 0)} improved / "
        f"{summary.get('regressed', 0)} regressed / "
        f"{summary.get('unchanged', 0)} unchanged / "
        f"{summary.get('unknown', 0)} unknown of {summary.get('total', 0)}"
    )


def _target_summary_to_string(summary: dict[str, Any] | None) -> str | None:
    if not summary or not summary.get("total"):
        return None
    return (
        f"{summary.get('pass', 0)} pass / "
        f"{summary.get('fail', 0)} fail / "
        f"{summary.get('unknown', 0)} unknown / "
        f"{summary.get('not_evaluated', 0)} not_evaluated of {summary.get('total', 0)}"
    )


def _target_comparison_items_for_loop(loop: dict[str, Any]) -> list[dict[str, Any]]:
    targets = ((loop.get("context") or {}).get("after") or {}).get("design_target_comparisons")
    if not isinstance(targets, dict):
        return []
    return [item for item in (targets.get("items") or []) if isinstance(item, dict)]


def _claim_boundary_in_report(text: str | None) -> bool:
    if not text:
        return False
    needles = ("does not certify", "claim boundary")
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _build_highlights(
    left_loop: dict[str, Any],
    right_loop: dict[str, Any],
    left_text: str | None,
    right_text: str | None,
) -> list[dict[str, Any]]:
    """Derive structured "What Changed" highlights from two persisted loops.

    Each highlight is severity-tagged so the UI can sort by importance.
    Sources of truth, in order:
      1. v0.2 `_build_loop_summary` fields (proposal, decision, counts).
      2. Report text presence (for claim boundary / report availability).
    """
    left = _build_loop_summary(left_loop)
    right = _build_loop_summary(right_loop)
    items: list[dict[str, Any]] = []

    # Approval decision — most important.
    lv, rv = left.get("decision"), right.get("decision")
    if lv == rv:
        items.append(_highlight(
            id="approval_decision",
            label="Approval decision",
            left=lv,
            right=rv,
            status="unchanged",
            severity="info",
            summary=f"Both loops have decision `{lv}`.",
        ))
    else:
        items.append(_highlight(
            id="approval_decision",
            label="Approval decision",
            left=lv,
            right=rv,
            status="changed",
            severity="critical",
            summary=f"Approval decision changed: `{lv}` → `{rv}`.",
        ))

    # Proposal.
    lp = _proposal_to_string(left.get("proposal_summary"))
    rp = _proposal_to_string(right.get("proposal_summary"))
    if lp is None and rp is None:
        items.append(_highlight(
            id="proposal",
            label="Proposal",
            left=None,
            right=None,
            status="missing",
            severity="info",
            summary="Neither loop selected a CAD modification proposal.",
        ))
    elif lp == rp:
        items.append(_highlight(
            id="proposal",
            label="Proposal",
            left=lp,
            right=rp,
            status="unchanged",
            severity="info",
            summary="Both loops selected the same CAD modification proposal.",
        ))
    else:
        items.append(_highlight(
            id="proposal",
            label="Proposal",
            left=lp,
            right=rp,
            status="changed",
            severity="warning",
            summary=f"Proposal changed: `{lp or 'none'}` → `{rp or 'none'}`.",
        ))

    # Verification status.
    lvs, rvs = left.get("verification_status"), right.get("verification_status")
    if lvs is None and rvs is None:
        items.append(_highlight(
            id="verification_status",
            label="Verification status",
            left=None,
            right=None,
            status="unknown",
            severity="info",
            summary="Verification was not evaluated on either loop.",
        ))
    elif lvs == rvs:
        items.append(_highlight(
            id="verification_status",
            label="Verification status",
            left=lvs,
            right=rvs,
            status="unchanged",
            severity="info",
            summary=f"Both loops verified as `{lvs}`.",
        ))
    else:
        # A drop from pass→warn or pass→fail is more concerning.
        ranking = {"pass": 0, "warn": 1, "fail": 2}
        sev = "warning"
        if ranking.get(str(rvs), -1) > ranking.get(str(lvs), -1):
            sev = "critical"
        items.append(_highlight(
            id="verification_status",
            label="Verification status",
            left=lvs,
            right=rvs,
            status="changed",
            severity=sev,
            summary=f"Verification status changed: `{lvs}` → `{rvs}`.",
        ))

    # Stale artifacts count.
    lsc = int(left.get("stale_artifact_count") or 0)
    rsc = int(right.get("stale_artifact_count") or 0)
    items.append(_highlight(
        id="stale_artifacts",
        label="Stale artifacts",
        left=lsc,
        right=rsc,
        status="unchanged" if lsc == rsc else "changed",
        severity="warning" if lsc != rsc else "info",
        summary=(
            f"Stale artifact count unchanged at {lsc}."
            if lsc == rsc
            else f"Stale artifact count changed: {lsc} → {rsc}."
        ),
    ))

    # Metric summary.
    lms = _metric_summary_to_string(left.get("metric_summary"))
    rms = _metric_summary_to_string(right.get("metric_summary"))
    if lms is None and rms is None:
        items.append(_highlight(
            id="metric_summary",
            label="Metrics summary",
            left=None,
            right=None,
            status="missing",
            severity="info",
            summary="Neither loop has a before/after metric delta.",
        ))
    elif lms == rms:
        items.append(_highlight(
            id="metric_summary",
            label="Metrics summary",
            left=lms,
            right=rms,
            status="unchanged",
            severity="info",
            summary="Metric summary unchanged based on available computed metrics.",
        ))
    else:
        items.append(_highlight(
            id="metric_summary",
            label="Metrics summary",
            left=lms,
            right=rms,
            status="changed",
            severity="warning",
            summary="Metric summary changed based on available computed metrics. This does not certify either design.",
        ))

    # Design target summary.
    lts = _target_summary_to_string(left.get("target_summary"))
    rts = _target_summary_to_string(right.get("target_summary"))
    if lts is None and rts is None:
        items.append(_highlight(
            id="target_summary",
            label="Design target summary",
            left=None,
            right=None,
            status="missing",
            severity="info",
            summary="Neither loop produced a design target comparison.",
        ))
    elif lts == rts:
        items.append(_highlight(
            id="target_summary",
            label="Design target summary",
            left=lts,
            right=rts,
            status="unchanged",
            severity="info",
            summary="Design target summary unchanged.",
        ))
    else:
        items.append(_highlight(
            id="target_summary",
            label="Design target summary",
            left=lts,
            right=rts,
            status="changed",
            severity="warning",
            summary="Design target summary changed.",
        ))

    # Warning / error counts.
    lw = int(left.get("warning_count") or 0)
    rw = int(right.get("warning_count") or 0)
    le = int(left.get("error_count") or 0)
    re_ = int(right.get("error_count") or 0)
    items.append(_highlight(
        id="warnings_errors",
        label="Warnings / errors",
        left=f"{lw} warn / {le} err",
        right=f"{rw} warn / {re_} err",
        status="unchanged" if (lw, le) == (rw, re_) else "changed",
        severity="warning" if (lw, le) != (rw, re_) else "info",
        summary=(
            f"Warnings and errors unchanged ({lw}/{le})."
            if (lw, le) == (rw, re_)
            else f"Warnings/errors changed: {lw} warn/{le} err → {rw} warn/{re_} err."
        ),
    ))

    # Report availability.
    lha = left_text is not None
    rha = right_text is not None
    if lha and rha:
        items.append(_highlight(
            id="report_availability",
            label="Report availability",
            left="present",
            right="present",
            status="unchanged",
            severity="info",
            summary="Both loop reports are available for diff.",
        ))
    elif not lha and not rha:
        items.append(_highlight(
            id="report_availability",
            label="Report availability",
            left="missing",
            right="missing",
            status="missing",
            severity="warning",
            summary="Neither loop has a generated report; diff is suppressed.",
        ))
    else:
        items.append(_highlight(
            id="report_availability",
            label="Report availability",
            left="present" if lha else "missing",
            right="present" if rha else "missing",
            status="missing",
            severity="warning",
            summary=(
                "Right report is missing; diff is suppressed."
                if lha else
                "Left report is missing; diff is suppressed."
            ),
        ))

    # Claim boundary presence in each report.
    lcb = _claim_boundary_in_report(left_text)
    rcb = _claim_boundary_in_report(right_text)
    if lha and not lcb:
        items.append(_highlight(
            id="claim_boundary_left",
            label="Claim boundary (left)",
            left="missing",
            right=None,
            status="missing",
            severity="critical",
            summary="Left report does not contain a claim-boundary statement. This is a critical gap in an evidence-grounded review.",
        ))
    if rha and not rcb:
        items.append(_highlight(
            id="claim_boundary_right",
            label="Claim boundary (right)",
            left=None,
            right="missing",
            status="missing",
            severity="critical",
            summary="Right report does not contain a claim-boundary statement. This is a critical gap in an evidence-grounded review.",
        ))
    if (lha and lcb) and (rha and rcb):
        items.append(_highlight(
            id="claim_boundary_presence",
            label="Claim boundary",
            left="present",
            right="present",
            status="unchanged",
            severity="info",
            summary="Both reports include a claim-boundary statement.",
        ))
    elif not lha and not rha:
        # Neither report exists; no claim-boundary check needed beyond the
        # report availability highlight above.
        pass

    return items


# Max report text we will read or include in the response body. Keeps the
# diff endpoint cheap and protects the frontend from huge payloads.
_REPORT_TEXT_CAP = 200_000
_REPORT_MEMBER_RE = re.compile(r"^reports/copilot_loop/[A-Za-z0-9_\-]+\.md$")


def _safe_report_member(report_path: str | None) -> str | None:
    """Validate a package-internal report path.

    Loop-generated reports always live at `reports/copilot_loop/<id>.md` inside
    the .aieng zip. Anything else (path traversal, backslashes, parent refs,
    absolute paths, foreign prefixes) is rejected so a tampered persisted
    state file cannot be used to read arbitrary package members.
    """
    if not report_path or not isinstance(report_path, str):
        return None
    # Reject path traversal / absolute / windows-style separators.
    if ".." in report_path.split("/"):
        return None
    if report_path.startswith("/") or "\\" in report_path or ":" in report_path:
        return None
    if not _REPORT_MEMBER_RE.match(report_path):
        return None
    return report_path


def _resolve_safe_local_report(settings: Settings, project_id: str, loop_id: str) -> Path | None:
    """Local-fallback for the package-internal report, restricted to the
    project's own `copilot_loops/` directory.
    """
    if not isinstance(loop_id, str) or not re.fullmatch(r"[A-Za-z0-9_\-]+", loop_id):
        return None
    base = (project_dir(settings, project_id) / "copilot_loops").resolve()
    candidate = (project_dir(settings, project_id) / "copilot_loops" / f"{loop_id}.md").resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def _read_report_text(settings: Settings, project_id: str, loop: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Return (markdown text or None, warnings). Prefers the package-internal
    artifact (the authoritative location) and falls back to the local tmp
    copy under the project workspace.
    """
    warnings: list[str] = []
    report_path = _report_path_for_loop(loop)
    member = _safe_report_member(report_path) if report_path else None
    if report_path and member is None:
        warnings.append(
            "Persisted report_path is not a known safe location and was ignored."
        )

    if member:
        try:
            package_path = _resolve_package(settings, project_id)
            with zipfile.ZipFile(package_path, "r") as zf:
                if member in zf.namelist():
                    raw = zf.read(member)
                    return raw.decode("utf-8", errors="replace"), warnings
        except HTTPException:
            # No package on disk — we'll try the local fallback next.
            pass
        except Exception as exc:  # noqa: BLE001 — package may be unreadable; report honestly
            warnings.append(f"Could not read report from package: {type(exc).__name__}")

    loop_id = loop.get("loop_id")
    if isinstance(loop_id, str):
        local = _resolve_safe_local_report(settings, project_id, loop_id)
        if local is not None:
            try:
                text = local.read_text(encoding="utf-8")
                warnings.append(
                    "Loaded local report copy; package-side artifact was not found."
                )
                return text, warnings
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Local report copy is unreadable: {type(exc).__name__}")

    return None, warnings


def compare_reports(
    settings: Settings,
    project_id: str,
    left_loop_id: str,
    right_loop_id: str,
) -> dict[str, Any]:
    """Diff two persisted loop reports within the same project.

    Loops are resolved from the project's own `copilot_loops/` directory, so
    a loop ID from a different project cannot be addressed here. Missing
    reports produce a clean "unavailable" response with warnings — never a
    500 — and missing reports are never auto-generated.
    """
    left_loop = read_json(_loop_path(settings, project_id, left_loop_id), None)
    if not isinstance(left_loop, dict):
        raise HTTPException(status_code=404, detail=f"left copilot loop not found: {left_loop_id}")
    right_loop = read_json(_loop_path(settings, project_id, right_loop_id), None)
    if not isinstance(right_loop, dict):
        raise HTTPException(status_code=404, detail=f"right copilot loop not found: {right_loop_id}")

    left_text, left_warnings = _read_report_text(settings, project_id, left_loop)
    right_text, right_warnings = _read_report_text(settings, project_id, right_loop)

    warnings: list[str] = []
    if left_text is None:
        warnings.append(f"Left loop {left_loop_id} report has not been generated yet or is missing.")
    if right_text is None:
        warnings.append(f"Right loop {right_loop_id} report has not been generated yet or is missing.")
    warnings.extend(left_warnings)
    warnings.extend(right_warnings)

    left_truncated = right_truncated = False
    if left_text is not None and len(left_text) > _REPORT_TEXT_CAP:
        left_text = left_text[:_REPORT_TEXT_CAP]
        left_truncated = True
        warnings.append("Left report exceeded the size cap and was truncated for diff.")
    if right_text is not None and len(right_text) > _REPORT_TEXT_CAP:
        right_text = right_text[:_REPORT_TEXT_CAP]
        right_truncated = True
        warnings.append("Right report exceeded the size cap and was truncated for diff.")

    unified_diff: str | None = None
    added_lines = 0
    removed_lines = 0
    if left_text is not None and right_text is not None:
        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()
        diff_iter = difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"left:{left_loop_id}",
            tofile=f"right:{right_loop_id}",
            lineterm="",
            n=3,
        )
        diff_lines = list(diff_iter)
        unified_diff = "\n".join(diff_lines)
        for line in diff_lines:
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                added_lines += 1
            elif line.startswith("-"):
                removed_lines += 1

    highlights = _build_highlights(left_loop, right_loop, left_text, right_text)

    return {
        "schema_version": "0.2",
        "left_loop_id": left_loop_id,
        "right_loop_id": right_loop_id,
        "left_report_path": _report_path_for_loop(left_loop),
        "right_report_path": _report_path_for_loop(right_loop),
        "left_report_exists": left_text is not None,
        "right_report_exists": right_text is not None,
        "left_report_truncated": left_truncated,
        "right_report_truncated": right_truncated,
        "left_text": left_text,
        "right_text": right_text,
        "unified_diff": unified_diff,
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "highlights": highlights,
        "warnings": warnings,
        "claim_boundary": _CLAIM_BOUNDARY_DIFF_NOTE,
    }


_LOOP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")


# Maximum embedded raw-report length per side when `include_reports=true`.
# Larger reports are truncated with an explicit warning; the export always
# keeps a workspace-relative link to the full report so reviewers can drill in.
_EMBEDDED_REPORT_CAP = 4_000


def _report_link_from_review_path(report_path: str | None) -> str | None:
    """Return a workspace-relative link from a review-export location.

    The export lives at ``reports/copilot_loop_review/<ts>.md`` and reports
    live at ``reports/copilot_loop/<id>.md``. The relative link from one
    to the other is ``../copilot_loop/<id>.md``. Anything not matching
    that shape is returned unchanged (the caller will treat it as a raw
    path) so we never fabricate a misleading link.
    """
    if not report_path:
        return None
    prefix = "reports/copilot_loop/"
    if report_path.startswith(prefix):
        return "../copilot_loop/" + report_path[len(prefix):]
    return report_path


def _validate_loop_id(loop_id: Any) -> str:
    if not isinstance(loop_id, str) or not _LOOP_ID_PATTERN.fullmatch(loop_id):
        raise HTTPException(status_code=400, detail="invalid loop_id format")
    return loop_id


def _format_value(value: Any) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _build_review_markdown(
    *,
    project_id: str,
    loops: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    include_reports: bool,
    include_diff: bool,
    include_highlights: bool,
    diff_payload: dict[str, Any] | None,
    report_texts: list[str | None],
    warnings_collected: list[str],
) -> str:
    lines: list[str] = []
    n = len(loops)
    title_kind = "Two-loop comparison" if n == 2 else "Single-loop record"
    lines.append(f"# Copilot Loop Decision Review — {title_kind}")
    lines.append("")
    lines.append("## Claim boundary")
    lines.append("")
    lines.append(_CLAIM_BOUNDARY_EXPORT_NOTE)
    lines.append("")
    lines.append("> This decision review export does not certify design safety, does not auto-advance engineering claims, and must be reviewed by a qualified engineer.")
    lines.append("")
    lines.append("## Review summary")
    lines.append("")
    lines.append(f"- Project: `{project_id}`")
    lines.append(f"- Loop count: {n}")
    lines.append(f"- Generated at: {now_iso()}")
    for idx, summary in enumerate(summaries):
        side = "Single" if n == 1 else ("Left" if idx == 0 else "Right")
        lines.append(f"- {side} loop: `{summary.get('loop_id')}` "
                     f"(status: `{summary.get('status') or 'unknown'}`, "
                     f"decision: `{summary.get('decision') or 'unknown'}`)")
    lines.append("")

    for idx, summary in enumerate(summaries):
        side = "Single loop" if n == 1 else ("Left loop" if idx == 0 else "Right loop")
        lines.append(f"## {side}: `{summary.get('loop_id')}`")
        lines.append("")
        proposal = summary.get("proposal_summary") or {}
        proposal_line = _proposal_to_string(proposal) or "Not available"
        lines.append(f"- Created: {_format_value(summary.get('created_at'))}")
        lines.append(f"- Updated: {_format_value(summary.get('updated_at'))}")
        lines.append(f"- Status: `{_format_value(summary.get('status'))}`")
        lines.append(f"- Decision: `{_format_value(summary.get('decision'))}`")
        lines.append(f"- Verification: `{_format_value(summary.get('verification_status'))}`")
        lines.append(f"- Proposal: {proposal_line}")
        lines.append(f"- Stale artifacts: {summary.get('stale_artifact_count') or 0}")
        lines.append(f"- Warnings / errors: {summary.get('warning_count') or 0} / {summary.get('error_count') or 0}")
        lines.append(f"- Metrics: {_metric_summary_to_string(summary.get('metric_summary')) or 'Not available'}")
        lines.append(f"- Design targets: {_target_summary_to_string(summary.get('target_summary')) or 'Not available'}")
        report_path = summary.get("report_path")
        report_link = _report_link_from_review_path(report_path)
        if report_path and report_link:
            lines.append(f"- Report: [`{report_path}`]({report_link})")
        elif report_path:
            lines.append(f"- Report: `{report_path}`")
        else:
            lines.append("- Report: Not available")
        lines.append("")
        comparison_items = _target_comparison_items_for_loop(loops[idx])
        if comparison_items:
            lines.append("### Design target comparison")
            lines.append("")
            lines.append("| Target | Status | Reason | Actual | Expected |")
            lines.append("|---|---|---|---|---|")
            for item in comparison_items:
                actual = item.get("actual")
                actual_value = actual.get("value") if isinstance(actual, dict) else actual
                expected = item.get("expected") if isinstance(item.get("expected"), dict) else {}
                expected_text = json.dumps(expected, sort_keys=True) if expected else "n/a"
                reason = item.get("reason_code") or item.get("notes") or ""
                reason_text = f"`{reason}`" if item.get("reason_code") else str(reason).replace("|", "/")
                lines.append(
                    f"| `{item.get('target_id')}` | `{item.get('status')}` | "
                    f"{reason_text} | "
                    f"{_format_value(actual_value)} | {expected_text} |"
                )
            lines.append("")

    if n == 2 and include_highlights:
        lines.append("## What changed (structured highlights)")
        lines.append("")
        highlights = (diff_payload or {}).get("highlights") or []
        if not highlights:
            lines.append("No structured highlights available.")
            lines.append("")
        else:
            lines.append("| Highlight | Status | Severity | Left | Right | Summary |")
            lines.append("|---|---|---|---|---|---|")
            for item in highlights:
                lines.append(
                    f"| {item.get('label')} | `{item.get('status')}` | `{item.get('severity')}` | "
                    f"{_format_value(item.get('left'))} | {_format_value(item.get('right'))} | "
                    f"{item.get('summary')} |"
                )
            lines.append("")

    if include_reports and n >= 1:
        for idx, text in enumerate(report_texts):
            side = "Single loop" if n == 1 else ("Left loop" if idx == 0 else "Right loop")
            lines.append(f"## {side} report")
            lines.append("")
            summary = summaries[idx]
            report_path = summary.get("report_path")
            report_link = _report_link_from_review_path(report_path)
            if report_path and report_link:
                lines.append(f"Full report: [`{report_path}`]({report_link})")
                lines.append("")
            if text is None:
                lines.append("_Report not available._")
            else:
                excerpt = text
                truncated = False
                if len(excerpt) > _EMBEDDED_REPORT_CAP:
                    excerpt = excerpt[:_EMBEDDED_REPORT_CAP]
                    truncated = True
                lines.append("```markdown")
                lines.append(excerpt)
                if truncated:
                    lines.append("")
                    lines.append(
                        f"[…truncated at {_EMBEDDED_REPORT_CAP} chars — see linked full report above]"
                    )
                lines.append("```")
                if truncated:
                    warnings_collected.append(
                        f"{side} report exceeded the embedded-report cap and was truncated in the export."
                    )
            lines.append("")

    if n == 2 and include_diff and diff_payload is not None:
        unified = diff_payload.get("unified_diff")
        lines.append("## Report diff (unified)")
        lines.append("")
        lines.append(f"- Added lines: {diff_payload.get('added_lines', 0)}")
        lines.append(f"- Removed lines: {diff_payload.get('removed_lines', 0)}")
        lines.append("")
        if unified:
            excerpt = unified
            truncated = False
            cap = _EMBEDDED_REPORT_CAP * 4  # diff is allowed to be larger than a single report excerpt
            if len(excerpt) > cap:
                excerpt = excerpt[:cap]
                truncated = True
            lines.append("```diff")
            lines.append(excerpt)
            if truncated:
                lines.append("")
                lines.append(f"[…truncated at {cap} chars — load the full diff from the compare panel]")
            lines.append("```")
            if truncated:
                warnings_collected.append("Unified diff exceeded the export cap and was truncated.")
        else:
            lines.append("_Unified diff not available._")
        lines.append("")

    if warnings_collected:
        lines.append("## Warnings collected during export")
        lines.append("")
        for w in warnings_collected:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Limitations")
    lines.append("")
    lines.append("- This export is a textual review record. It does not certify the design.")
    lines.append("- Computed metrics are evidence inputs, not engineering claims.")
    lines.append("- Missing data is shown as `Not available`/`Unknown`; nothing is fabricated.")
    lines.append("- Rejected loops are decision records, not engineering failures.")
    lines.append("- A qualified engineer must review the underlying reports and evidence.")
    lines.append("")
    return "\n".join(lines)


def export_review(
    settings: Settings,
    project_id: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a Markdown decision-review artifact for one or two loops.

    The export path is constructed entirely server-side from a constant
    prefix and a UTC timestamp; user input never reaches the filesystem
    path. Loop IDs are regex-validated and resolved through project-scoped
    storage so cross-project access is impossible.
    """
    payload = payload or {}
    loop_ids = payload.get("loop_ids")
    if not isinstance(loop_ids, list) or not (1 <= len(loop_ids) <= 2):
        raise HTTPException(status_code=400, detail="loop_ids must contain 1 or 2 values")
    validated_ids = [_validate_loop_id(lid) for lid in loop_ids]

    include_reports = bool(payload.get("include_reports", False))
    include_diff = bool(payload.get("include_diff", False))
    include_highlights = bool(payload.get("include_highlights", True))

    loops: list[dict[str, Any]] = []
    for lid in validated_ids:
        loop = read_json(_loop_path(settings, project_id, lid), None)
        if not isinstance(loop, dict):
            raise HTTPException(status_code=404, detail=f"copilot loop not found: {lid}")
        loops.append(loop)

    summaries = [_build_loop_summary(loop) for loop in loops]
    report_texts: list[str | None] = []
    warnings_collected: list[str] = []
    for idx, loop in enumerate(loops):
        text, side_warnings = _read_report_text(settings, project_id, loop)
        report_texts.append(text)
        if text is None:
            side = "single" if len(loops) == 1 else ("left" if idx == 0 else "right")
            warnings_collected.append(
                f"{side.capitalize()} loop {loop.get('loop_id')} has no readable report."
            )
        warnings_collected.extend(side_warnings)

    diff_payload: dict[str, Any] | None = None
    if len(loops) == 2 and (include_diff or include_highlights):
        diff_payload = compare_reports(
            settings, project_id, validated_ids[0], validated_ids[1]
        )
        for w in diff_payload.get("warnings") or []:
            if w not in warnings_collected:
                warnings_collected.append(w)

    markdown = _build_review_markdown(
        project_id=project_id,
        loops=loops,
        summaries=summaries,
        include_reports=include_reports,
        include_diff=include_diff,
        include_highlights=include_highlights,
        diff_payload=diff_payload,
        report_texts=report_texts,
        warnings_collected=warnings_collected,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_member = f"reports/copilot_loop_review/{timestamp}.md"
    local_dir = project_dir(settings, project_id) / "copilot_loop_review"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / f"{timestamp}.md"
    local_path.write_text(markdown, encoding="utf-8")

    package_warning: str | None = None
    try:
        package_path = _resolve_package(settings, project_id)
        write_artifact_to_package(package_path, export_member, local_path, overwrite=True)
    except HTTPException as exc:
        package_warning = (
            f"Export saved locally only; could not write into .aieng package: {exc.detail}."
        )
    except Exception as exc:  # noqa: BLE001 — surface honestly, do not raise
        package_warning = (
            f"Export saved locally only; could not write into .aieng package: {type(exc).__name__}."
        )
    if package_warning:
        warnings_collected.append(package_warning)

    return {
        "schema_version": "0.1",
        "project_id": project_id,
        "loop_ids": validated_ids,
        "export_path": export_member,
        "export_local_path": str(local_path),
        "export_text": markdown,
        "warnings": warnings_collected,
        "claim_boundary": _CLAIM_BOUNDARY_EXPORT_NOTE,
        "included": {
            "reports": include_reports,
            "diff": include_diff,
            "highlights": include_highlights,
        },
    }


def _step_run_id(step: dict[str, Any]) -> str | None:
    calls = step.get("toolCalls") or []
    if calls and isinstance(calls[0], dict):
        run_id = calls[0].get("runId")
        return str(run_id) if run_id else None
    return None


def _step_tool_name(step: dict[str, Any]) -> str:
    calls = step.get("toolCalls") or []
    if calls and isinstance(calls[0], dict):
        return str(calls[0].get("toolName") or "")
    return ""


def _run_runtime_tool(
    *,
    project_id: str,
    message: str,
    tool_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = _rt.RunRecord(
        run_id=uuid.uuid4().hex[:12],
        message=message,
        created_at=now_iso(),
        status="pending",
        project_id=project_id,
    )
    ctx: dict[str, Any] = {"project_id": project_id}
    if tool_input:
        ctx["tool_input"] = tool_input
    _rt.execute_run(run, ctx)
    return _rt.run_to_dict(run)


def _tool_call_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    calls = run.get("tool_calls") or []
    results = run.get("tool_results") or []
    out: list[dict[str, Any]] = []
    for i, call in enumerate(calls):
        result = results[i] if i < len(results) else {}
        out.append(
            {
                "toolName": call.get("name"),
                "status": result.get("status") or run.get("status"),
                "runId": run.get("run_id"),
            }
        )
    return out


def _first_tool_output(run: dict[str, Any]) -> Any:
    results = run.get("tool_results") or []
    if not results:
        return None
    return results[0].get("output")


def _run_status_to_step(run: dict[str, Any], output: Any) -> tuple[str, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if isinstance(output, dict):
        warnings.extend(str(w) for w in (output.get("warnings") or []))
        errors.extend(str(e) for e in (output.get("errors") or []))
        if output.get("ok") is False or output.get("status") == "error":
            errors.append(output.get("message") or output.get("code") or "tool returned an error")
            return "error", warnings, errors
        if output.get("status") in {"partial", "failed"}:
            if output.get("status") == "failed":
                return "error", warnings, errors
            return "partial", warnings, errors
    if run.get("status") == "awaiting_approval":
        return "waiting_for_approval", warnings, errors
    if run.get("status") in {"failed", "cancelled"}:
        errors.extend(str(e) for e in (run.get("errors") or []))
        return "error", warnings, errors
    if run.get("status") == "rejected":
        return "skipped", warnings + ["reason=user_rejected"], errors
    return "completed", warnings, errors


def _apply_run_outcome_to_step(
    loop: dict[str, Any],
    step: dict[str, Any],
    run: dict[str, Any],
    *,
    approved: bool = False,
) -> None:
    output = _first_tool_output(run)
    status, warnings, errors = _run_status_to_step(run, output)
    artifacts: list[dict[str, Any]] = []
    if isinstance(output, dict):
        artifacts = [a for a in (output.get("artifacts") or output.get("changed_artifacts") or []) if isinstance(a, dict)]
    if approved and run.get("status") == "completed" and status == "completed":
        warnings.append("Approved operation completed. Downstream evidence may now be stale until re-simulation.")
    _set_step(
        step,
        status,
        summary=_runtime_summary(run, output),
        warnings=warnings,
        errors=errors,
        artifacts=artifacts,
        tool_calls=_tool_call_from_run(run),
        data={"runtime_run": run, "output": output},
    )
    if step["id"] == "apply_cad_edit" and isinstance(output, dict):
        loop.setdefault("context", {})["applied_operation"] = output
        if output.get("stale_artifacts"):
            loop.setdefault("context", {})["stale_artifacts"] = output.get("stale_artifacts")


def _runtime_summary(run: dict[str, Any], output: Any) -> str:
    if isinstance(output, dict):
        msg = output.get("message") or output.get("summary") or output.get("status")
        if msg:
            return str(msg)
    return str(run.get("summary") or f"Runtime run {run.get('status')}.")


def _advance_inspect(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    warnings: list[str] = []
    artifacts: list[dict[str, Any]] = []
    names: set[str] = set()
    revalidation = None
    result_summary = None
    preprocessing = None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            revalidation = read_package_json(zf, "state/revalidation_status.json")
            result_summary = read_package_json(zf, "results/result_summary.json")
            preprocessing = read_package_json(zf, "simulation/preprocessing_summary.json")
            for p in ("manifest.json", "task/design_targets.yaml", "results/computed_metrics.json", "results/result_summary.json", "state/revalidation_status.json"):
                if p in names:
                    artifacts.append({"path": p, "label": Path(p).name})
    except Exception as exc:
        _set_step(step, "error", errors=[f"package inspection failed: {exc}"])
        return
    if result_summary is None:
        result_summary = _generate_cae_result_summary(settings, package_path)
        if result_summary is None:
            warnings.append("No results/result_summary.json found and dynamic result-summary generation is unavailable.")
    if preprocessing is None:
        preprocessing = _generate_cae_preprocessing_summary(settings, package_path)
        if preprocessing is None:
            warnings.append("No simulation/preprocessing_summary.json found and dynamic preprocessing summary is unavailable.")
    loop.setdefault("context", {})["evidence"] = {
        "member_count": len(names),
        "has_design_targets": "task/design_targets.yaml" in names,
        "has_computed_metrics": "results/computed_metrics.json" in names,
        "has_result_summary": result_summary is not None,
        "has_preprocessing_summary": preprocessing is not None,
        "revalidation_status": revalidation,
        "result_summary": result_summary,
        "preprocessing_summary": preprocessing,
    }
    status = "completed" if not warnings else "partial"
    _set_step(
        step,
        status,
        summary=f"Inspected {len(names)} package member(s).",
        warnings=warnings,
        artifacts=artifacts,
        data=loop["context"]["evidence"],
    )


def _advance_recommend(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    combined = _generate_cad_recommendations_with_verification(
        settings, package_path, strictness=loop.get("strictness", "default")
    )
    if combined is None:
        _set_step(step, "error", errors=["Recommendation/verification modules are unavailable."])
        return
    loop.setdefault("context", {})["recommendation_response"] = combined
    proposals = ((combined.get("recommendations") or {}).get("proposals") or [])
    if not proposals:
        _set_step(
            step,
            "skipped",
            summary="No CAD modification proposal is available from current evidence.",
            warnings=(combined.get("recommendations") or {}).get("warnings") or [],
            data=combined,
        )
        return
    selected = _select_proposal(combined, loop.get("selected_proposal_id"))
    loop.setdefault("context", {})["selected_proposal"] = selected
    _set_step(
        step,
        "completed",
        summary=f"Selected proposal {selected.get('proposal_id')}: {selected.get('feature_ref')} {selected.get('action_type')}.",
        warnings=(combined.get("recommendations") or {}).get("warnings") or [],
        data={"selected_proposal": selected, "proposal_count": len(proposals), "recommendations": combined.get("recommendations")},
    )


def _advance_verify(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    combined = loop.get("context", {}).get("recommendation_response")
    if not combined:
        _set_step(step, "skipped", summary="No recommendation response is available; run recommendation first.")
        return
    proposal = loop.get("context", {}).get("selected_proposal") or _select_proposal(combined, loop.get("selected_proposal_id"))
    verdict = _verdict_for(combined, proposal.get("proposal_id"))
    if not verdict:
        _set_step(step, "partial", summary="Proposal exists but no verification verdict was returned.", data={"proposal": proposal})
        return
    status = "completed" if verdict.get("verdict") in {"pass", "warn"} else "error"
    warnings = []
    if verdict.get("verdict") == "warn":
        warnings.append("Verification returned warnings; explicit user review is required before applying.")
    errors = []
    if verdict.get("verdict") == "fail":
        errors.append("Verification failed; the proposal is blocked from execution.")
    _set_step(
        step,
        status,
        summary=f"Verification verdict: {verdict.get('verdict')}.",
        warnings=warnings + [str(c.get("message")) for c in (verdict.get("warnings_from_checks") or []) if isinstance(c, dict) and c.get("message")],
        errors=errors + [str(c.get("message")) for c in (verdict.get("blockers") or []) if isinstance(c, dict) and c.get("message")],
        data={"proposal": proposal, "verdict": verdict, "claim_policy": combined.get("claim_policy")},
    )


def _advance_apply(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    if loop.get("context", {}).get("apply_rejected"):
        _set_step(step, "skipped", summary="CAD edit was previously rejected by the user.", warnings=["reason=user_rejected"])
        return
    proposal = loop.get("context", {}).get("selected_proposal")
    verdict = _verdict_for(loop.get("context", {}).get("recommendation_response") or {}, proposal.get("proposal_id") if proposal else None)
    if not proposal:
        _set_step(step, "skipped", summary="No proposal selected for application.")
        return
    if verdict and verdict.get("verdict") == "fail":
        _set_step(step, "skipped", summary="Verification failed; blocked from execution.", errors=["verification_failed"])
        return
    change = proposal.get("parameter_change") or {}
    if not change.get("name") or change.get("to") is None:
        _set_step(step, "skipped", summary="Selected proposal has no executable parameter_change.")
        return
    run = _run_runtime_tool(
        project_id=project_id,
        message="edit cad parameter",
        tool_input={
            "project_id": project_id,
            "featureId": proposal.get("feature_ref"),
            "parameterName": change.get("name"),
            "newValue": change.get("to"),
        },
    )
    _apply_run_outcome_to_step(loop, step, run)


def _advance_mark_stale(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    apply_step = _find_step(loop, "apply_cad_edit")
    if apply_step.get("status") == "skipped":
        _set_step(step, "skipped", summary="No CAD edit was applied; no new stale evidence was introduced.")
        return
    revalidation = _read_revalidation(package_path)
    stale_artifacts = []
    if isinstance(revalidation, dict):
        stale_artifacts = revalidation.get("affected_artifacts") or []
    stale_artifacts = stale_artifacts or loop.get("context", {}).get("stale_artifacts") or []
    if revalidation and revalidation.get("requires_revalidation"):
        status = "completed"
        summary = "Downstream geometry-dependent evidence is marked stale."
    elif stale_artifacts:
        status = "partial"
        summary = "Stale artifacts are known from the CAD edit output, but package revalidation state was not confirmed."
    else:
        status = "skipped"
        summary = "No stale marker was found. If no geometry changed, this is expected; otherwise revalidation status is missing."
    _set_step(
        step,
        status,
        summary=summary,
        artifacts=[{"path": p, "label": "stale"} for p in stale_artifacts],
        warnings=[] if status == "completed" else ["Stale propagation is incomplete or not applicable."],
        data={"revalidation_status": revalidation, "stale_artifacts": stale_artifacts},
    )


def _advance_prepare_solver(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    run = _run_runtime_tool(
        project_id=project_id,
        message="prepare solver run",
        tool_input={"project_id": project_id, "runId": "run_001"},
    )
    output = _first_tool_output(run)
    _apply_run_outcome_to_step(loop, step, run)
    if isinstance(output, dict):
        loop.setdefault("context", {})["solver_preflight"] = output
        if output.get("ready_to_run") is False and step.get("status") == "completed":
            step["status"] = "partial"
            step.setdefault("warnings", []).append("Solver is not ready; see preflight missing_items.")


def _advance_run_mesh_solver(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    preflight = loop.get("context", {}).get("solver_preflight") or {}
    if isinstance(preflight, dict) and preflight.get("ready_to_run"):
        run = _run_runtime_tool(
            project_id=project_id,
            message="execute solver run",
            tool_input={
                "project_id": project_id,
                "runId": preflight.get("run_id") or "run_001",
                "inputDeckPath": f"simulation/runs/{preflight.get('run_id') or 'run_001'}/solver_input.inp",
                "extractResults": True,
                "refreshSummary": True,
            },
        )
        _apply_run_outcome_to_step(loop, step, run)
        return
    missing = ((preflight.get("preflight") or {}).get("missing_items") if isinstance(preflight, dict) else None) or []
    # If solver is not ready, do not fake mesh/solver success. This v0 reports the
    # honest blocker and lets the user run mesh/setup tools separately.
    _set_step(
        step,
        "skipped",
        summary="Mesh/solver execution was not started because preflight is not ready.",
        warnings=[str(m) for m in missing] or ["Run prepare solver first or provide solver setup/input deck."],
        data={"preflight": preflight},
    )


def _advance_extract_results(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    frd = _find_first_member(package_path, "simulation/runs/", "/outputs/result.frd")
    if not frd:
        _set_step(step, "skipped", summary="No CalculiX FRD result file is available to extract.", warnings=["result.frd not found"])
        return
    run = _run_runtime_tool(
        project_id=project_id,
        message="extract solver results",
        tool_input={"project_id": project_id, "frdPath": frd, "overwrite": True, "refresh_result_summary": False},
    )
    _apply_run_outcome_to_step(loop, step, run)


def _advance_refresh_summary(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    run = _run_runtime_tool(
        project_id=project_id,
        message="refresh cae summary",
        tool_input={"project_id": project_id, "overwrite": True},
    )
    _apply_run_outcome_to_step(loop, step, run)


def _advance_compare_targets(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    before = loop.get("context", {}).get("baseline") or {}
    after = _read_metrics_snapshot(package_path, settings=settings, project_id=project_id)
    comparison = _compare_metric_snapshots(before, after)
    loop.setdefault("context", {})["after"] = after
    loop.setdefault("context", {})["metric_comparison"] = comparison
    target_summary = after.get("design_target_comparisons")
    status = "completed" if comparison.get("metrics") or target_summary else "partial"
    warnings = []
    if not comparison.get("metrics"):
        warnings.append("No before/after metric delta could be computed from available evidence.")
    _set_step(
        step,
        status,
        summary="Compared available metrics and design target status.",
        warnings=warnings,
        data={"before": before, "after": after, "comparison": comparison, "design_target_comparisons": target_summary},
    )


def _advance_generate_report(
    settings: Settings, project_id: str, package_path: Path, loop: dict[str, Any], step: dict[str, Any]
) -> None:
    report = _build_loop_report(loop)
    report_path = f"reports/copilot_loop/{loop['loop_id']}.md"
    tmp = project_dir(settings, project_id) / "copilot_loops" / f"{loop['loop_id']}.md"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(report["markdown"], encoding="utf-8")
    artifacts: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        artifacts.append(write_artifact_to_package(package_path, report_path, tmp, overwrite=True))
    except Exception as exc:
        warnings.append(f"Could not write loop report into package: {exc}")
    report["artifact_path"] = report_path if artifacts else None
    loop.setdefault("context", {})["report"] = report
    _set_step(
        step,
        "completed" if artifacts else "partial",
        summary="Generated closed-loop Copilot report.",
        warnings=warnings,
        artifacts=artifacts or [{"path": str(tmp), "label": "local report"}],
        data=report,
    )


def _select_proposal(combined: dict[str, Any], requested_id: str | None = None) -> dict[str, Any]:
    proposals = (combined.get("recommendations") or {}).get("proposals") or []
    verdicts = {v.get("proposal_id"): v for v in (combined.get("verification") or {}).get("verdicts") or []}
    if requested_id:
        for p in proposals:
            if p.get("proposal_id") == requested_id:
                return p
    for p in proposals:
        verdict = verdicts.get(p.get("proposal_id"), {})
        if verdict.get("verdict") == "pass":
            return p
    for p in proposals:
        verdict = verdicts.get(p.get("proposal_id"), {})
        if verdict.get("verdict") == "warn":
            return p
    return proposals[0]


def _verdict_for(combined: dict[str, Any], proposal_id: str | None) -> dict[str, Any] | None:
    if not proposal_id:
        return None
    for verdict in (combined.get("verification") or {}).get("verdicts") or []:
        if verdict.get("proposal_id") == proposal_id:
            return verdict
    return None


def _read_revalidation(package_path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            return read_package_json(zf, "state/revalidation_status.json")
    except Exception:
        return None


def _find_first_member(package_path: Path, prefix: str, suffix: str) -> str | None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            for name in sorted(zf.namelist()):
                if name.startswith(prefix) and name.endswith(suffix):
                    return name
    except Exception:
        return None
    return None


def _read_metrics_snapshot(
    package_path: Path,
    *,
    settings: Settings | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    result_summary = None
    computed = None
    targets = None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            result_summary = read_package_json(zf, "results/result_summary.json")
            computed = read_package_json(zf, "results/computed_metrics.json")
    except Exception:
        pass
    if isinstance(result_summary, dict):
        computed_values = result_summary.get("computed_values") or {}
        targets = result_summary.get("design_target_comparisons")
    else:
        computed_values = {}
    if not isinstance(targets, dict) and settings is not None and project_id is not None:
        try:
            from . import target_comparison

            targets = target_comparison.compare_package_targets(settings, project_id).get("comparison")
        except Exception:
            targets = None
    metrics: dict[str, Any] = {}

    def _put_metric(name: str, obj: Any) -> None:
        if isinstance(obj, dict) and isinstance(obj.get("value"), (int, float)):
            metrics[name] = {"value": obj.get("value"), "unit": obj.get("unit")}

    _put_metric("max_displacement", computed_values.get("max_displacement"))
    _put_metric("max_von_mises_stress", computed_values.get("max_von_mises_stress"))
    _put_metric("minimum_safety_factor", computed_values.get("minimum_safety_factor"))

    if isinstance(computed, dict):
        for lc in computed.get("load_cases") or []:
            if not isinstance(lc, dict):
                continue
            for key, value in (lc.get("metrics") or {}).items():
                _put_metric(str(key), value)

    return {
        "metrics": metrics,
        "design_target_comparisons": targets,
        "source": "results/result_summary.json/results/computed_metrics.json",
    }


def _compare_metric_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    before_metrics = before.get("metrics") or {}
    after_metrics = after.get("metrics") or {}
    for key in sorted(set(before_metrics) | set(after_metrics)):
        b = before_metrics.get(key) or {}
        a = after_metrics.get(key) or {}
        bv = b.get("value")
        av = a.get("value")
        delta = av - bv if isinstance(bv, (int, float)) and isinstance(av, (int, float)) else None
        direction = "unknown"
        if delta is not None:
            direction = "improved_or_regressed_requires_target_context"
            if key in {"max_von_mises_stress", "max_displacement"}:
                direction = "improved" if delta < 0 else "regressed" if delta > 0 else "unchanged"
            elif key in {"minimum_safety_factor"}:
                direction = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
            elif "mass" in key:
                direction = "improved" if delta < 0 else "regressed" if delta > 0 else "unchanged"
        rows.append({"metric": key, "before": bv, "after": av, "delta": delta, "unit": a.get("unit") or b.get("unit"), "direction": direction})
    return {"metrics": rows}


def _build_loop_report(loop: dict[str, Any]) -> dict[str, Any]:
    context = loop.get("context") or {}
    apply_step = next((s for s in loop.get("steps", []) if s.get("id") == "apply_cad_edit"), None)
    apply_status = apply_step.get("status") if apply_step else None
    apply_rejected = bool(context.get("apply_rejected"))

    lines = [
        f"# Closed-loop Copilot Report — {loop['loop_id']}",
        "",
        "## Claim boundary",
        "",
        "This report does not certify the design, does not advance engineering claims automatically, and must be reviewed by a qualified engineer. CAD proposals are hypotheses; computed metrics are evidence inputs only.",
        "",
        "> This report does not certify design safety, does not auto-advance engineering claims, and must be reviewed by a qualified engineer.",
        "",
        "## Loop summary",
        "",
        f"- Loop id: `{loop.get('loop_id')}`",
        f"- Project: `{loop.get('project_id')}`",
        f"- Package: `{loop.get('package_path')}`",
        f"- Strictness: `{loop.get('strictness') or 'default'}`",
        f"- Generated at: {now_iso()}",
        f"- Loop status: `{loop.get('status') or 'unknown'}`",
        f"- Apply decision: "
        + ("`rejected by user` (CAD edit was not executed)" if apply_rejected else f"`{apply_status or 'not_reached'}`"),
        "",
        "## Step status",
        "",
    ]
    for step in loop.get("steps", []):
        lines.append(f"- **{step.get('title')}**: `{step.get('status')}` — {step.get('summary') or ''}")
        for warning in step.get("warnings") or []:
            lines.append(f"  - Warning: {warning}")
        for error in step.get("errors") or []:
            lines.append(f"  - Error: {error}")

    proposal = context.get("selected_proposal")
    if proposal:
        change = proposal.get("parameter_change") or {}
        lines.extend([
            "",
            "## CAD modification proposal",
            "",
            f"- Feature: `{proposal.get('feature_ref')}`",
            f"- Action: `{proposal.get('action_type')}`",
            f"- Parameter change: `{change.get('name')}` {change.get('from')} → {change.get('to')}",
            f"- Rationale: {proposal.get('rationale') or 'n/a'}",
        ])

    if apply_rejected:
        lines.extend([
            "",
            "## Rejection notice",
            "",
            "The CAD parameter edit was rejected during the approval gate. No mutation was applied to the package, no downstream evidence was invalidated by this loop, and all subsequent geometry-dependent steps were skipped or operated on the unchanged baseline.",
        ])

    stale_artifacts = context.get("stale_artifacts") or []
    revalidation = (context.get("evidence") or {}).get("revalidation_status")
    if not stale_artifacts and isinstance(revalidation, dict):
        stale_artifacts = revalidation.get("affected_artifacts") or []
    if stale_artifacts:
        lines.extend([
            "",
            "## Stale downstream artifacts",
            "",
            "After the approved CAD edit, the following package members must be regenerated before they can be cited as evidence for the modified geometry:",
            "",
        ])
        for path in stale_artifacts:
            lines.append(f"- `{path}`")

    preflight = context.get("solver_preflight") or {}
    if preflight:
        lines.extend([
            "",
            "## Mesh / solver readiness",
            "",
            f"- Preflight ready_to_run: `{preflight.get('ready_to_run')}`",
        ])
        missing = ((preflight.get("preflight") or {}).get("missing_items")) or []
        for m in missing:
            lines.append(f"  - Missing: {m}")

    comparison = context.get("metric_comparison") or {}
    if comparison.get("metrics"):
        lines.extend(["", "## Before/after metrics", ""])
        lines.append("| metric | before | after | delta | direction |")
        lines.append("|---|---:|---:|---:|---|")
        for row in comparison["metrics"]:
            lines.append(
                f"| {row.get('metric')} | {row.get('before')} | {row.get('after')} | {row.get('delta')} | {row.get('direction')} |"
            )

    target_summary = (context.get("after") or {}).get("design_target_comparisons")
    if isinstance(target_summary, dict) and target_summary.get("items"):
        lines.extend(["", "## Design target comparison", ""])
        lines.append("| target | status | actual | expected |")
        lines.append("|---|---|---|---|")
        for item in target_summary.get("items") or []:
            if isinstance(item, dict):
                lines.append(
                    f"| `{item.get('target_id')}` | `{item.get('status')}` | {item.get('actual')} | {item.get('expected')} |"
                )

    lines.extend([
        "",
        "## Limitations",
        "",
        "- A proposal is a hypothesis, not evidence.",
        "- Solver success is not the same as engineering validation.",
        "- Verification checks are pre-execution heuristics, not a substitute for re-simulation.",
        "- Missing Gmsh/CalculiX tools are reported as skipped/error/partial; success is never faked.",
        "- Stale evidence is preserved in the package for audit but must not be cited for the new geometry.",
        "- Claim advancement requires a separate explicit evidence-backed workflow.",
        "",
    ])
    return {
        "schema_version": "0.1",
        "loop_id": loop["loop_id"],
        "generated_at": now_iso(),
        "claim_boundary": {
            "claims_advanced": False,
            "design_certified": False,
            "statement": "This report does not certify the design, does not advance engineering claims automatically, and must be reviewed by a qualified engineer.",
        },
        "apply_rejected": apply_rejected,
        "stale_artifacts": list(stale_artifacts),
        "markdown": "\n".join(lines),
    }
