from __future__ import annotations

import re
from typing import Any

from .schema import ContextSummary


def redact_context_summary_text(value: Any, *, limit: int = 360) -> str:
    text = str(value or "").strip()
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-[redacted]", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)\S+", r"\1[redacted]", text)
    if len(text) > limit:
        return f"{text[: limit - 3]}..."
    return text


def build_context_summary(
    *,
    project_id: str,
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    events: list[dict[str, Any]],
    run: Any | None = None,
) -> ContextSummary:
    first_user = next((msg for msg in messages if msg.get("role") == "user"), None)
    last_message = messages[-1] if messages else None
    working_state = getattr(run, "working_state", None)
    goal = (
        getattr(working_state, "objective", "")
        or getattr(run, "message", "")
        or (first_user or {}).get("content")
        or session.get("title")
        or ""
    )
    current_state = (
        f"Run {run.run_id} is {run.status}."
        if run is not None
        else (
            f"Last message from {last_message.get('role')}: {redact_context_summary_text(last_message.get('content'))}"
            if last_message
            else "No chat messages yet."
        )
    )
    completed_steps: list[str] = []
    pending_steps: list[str] = []
    risks: list[str] = []
    if run is not None and run.plan is not None:
        for step in run.plan.steps:
            label = redact_context_summary_text(step.title or step.id, limit=160)
            if step.summary:
                label = f"{label}: {redact_context_summary_text(step.summary, limit=220)}"
            if step.status in {"completed", "skipped"}:
                completed_steps.append(label)
            elif step.status == "failed":
                risks.append(f"Failed step: {label}")
            else:
                pending_steps.append(label)
    relevant_files: list[str] = []
    for event in events[-80:]:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        for key in ("artifact_paths", "paths", "files"):
            values = payload.get(key)
            if isinstance(values, list):
                relevant_files.extend(redact_context_summary_text(item, limit=220) for item in values if item)
    user_constraints = [
        redact_context_summary_text(msg.get("content"), limit=240)
        for msg in messages
        if msg.get("role") == "user"
    ][-6:]
    important_decisions = list(getattr(working_state, "accepted_assumptions", []) or [])[-8:]
    risks.extend(list(getattr(working_state, "current_blockers", []) or [])[-8:])
    if run is not None:
        risks.extend(redact_context_summary_text(err, limit=240) for err in run.errors[-4:])
        if run.pending_approval is not None:
            approval = run.pending_approval
            risks.append(
                "Pending approval: "
                f"{redact_context_summary_text(approval.tool_name, limit=120)} - "
                f"{redact_context_summary_text(approval.explanation, limit=220)}"
            )
    next_action = _recommended_next_action(run, working_state)
    return ContextSummary(
        session_id=str(session["id"]),
        project_id=project_id,
        goal=redact_context_summary_text(goal),
        current_state=redact_context_summary_text(current_state),
        important_decisions=[redact_context_summary_text(item, limit=240) for item in important_decisions],
        completed_steps=completed_steps[-12:],
        pending_steps=pending_steps[:12],
        user_constraints=user_constraints,
        relevant_files=sorted(set(relevant_files))[:16],
        risks=[redact_context_summary_text(item, limit=240) for item in risks],
        next_action=redact_context_summary_text(next_action),
    )


def _recommended_next_action(run: Any | None, working_state: Any | None) -> str:
    recommended = getattr(working_state, "recommended_next_action", None) if working_state is not None else None
    if recommended:
        return str(recommended)
    if run is None:
        return "Wait for the next user request."
    if run.pending_approval is not None:
        return f"Review approval for {run.pending_approval.tool_name}."
    if run.status not in {"completed", "failed", "cancelled"}:
        return "Continue the active run."
    return "Wait for the next user request."
