"""Agent planning, run, connection, and agentic approval routes.

Extracted from ``app_factory.create_app`` (#9). The long-lived autopilot store
and event publishing helpers still live in ``app_factory`` because project/chat
cleanup paths reuse them; this router receives those pieces as explicit
callbacks.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from fastapi import Body, FastAPI, HTTPException

from .. import agent_engine, agent_workbench
from .. import runtime as _rt
from ..agent_autopilot.agentic_approval import (
    PermissionBroker,
    build_approval_name_set,
    format_decision,
    requires_approval as _agentic_requires_approval,
    resolve_registry_name as _agentic_resolve_name,
)
from ..config import now_iso
from ..logging_utils import log_exception
from ..project_io import write_audit_log

LOGGER = logging.getLogger(__name__)


def _agent_plan_response_from_run(state: Any) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "project_id": state.project_id,
        "session_id": state.session_id,
        "plan": state.plan.model_dump() if state.plan is not None else None,
        "run_status": state.status,
        "updated_at": state.updated_at,
    }


def register_agent_routes(
    app: FastAPI,
    *,
    active_settings: Any,
    resolve_api_key: Callable[[dict[str, Any] | None], str | None],
    llm_config_from_payload: Callable[..., dict[str, Any]],
    build_agent_response: Callable[[dict[str, Any]], dict[str, Any]],
    autopilot_store: Callable[[], Any],
    autopilot_run_response: Callable[[Any], dict[str, Any]],
    publish_agent_event: Callable[[dict[str, Any]], None],
) -> None:
    @app.post("/api/llm/test")
    def test_llm_provider_endpoint(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        llm_config = agent_engine.sanitize_llm_config(data.get("llm_config"))
        if not llm_config:
            raise HTTPException(status_code=400, detail="llm_config is required")
        api_key = resolve_api_key(data)
        verify = bool(data.get("verify_connection", False))
        return agent_engine.test_llm_provider(
            active_settings, llm_config, api_key=api_key, verify_connection=verify
        )

    @app.post("/api/agent/plan")
    def create_agent_plan(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return build_agent_response(payload or {})

    @app.post("/api/agent/runs")
    def create_agent_run(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        agent_plan = data.get("plan") if isinstance(data.get("plan"), dict) else build_agent_response(data)
        steps = agent_plan.get("steps") if isinstance(agent_plan.get("steps"), list) else []
        message = str(agent_plan.get("message") or data.get("message") or "agent run").strip()
        project_id = agent_plan.get("project_id") or data.get("project_id") or None
        run = _rt.RunRecord(
            run_id=uuid.uuid4().hex[:12],
            message=message,
            created_at=now_iso(),
            status="pending",
            project_id=str(project_id) if project_id else None,
        )
        ctx: dict[str, Any] = {
            "project_id": run.project_id,
            "workflow_id": "agent_chat",
            "agent_plan": {
                "mode": agent_plan.get("mode"),
                "warnings": agent_plan.get("warnings") or [],
                "errors": agent_plan.get("errors") or [],
                "selected_geometry": agent_plan.get("selected_geometry"),
            },
        }
        if isinstance(data.get("llm_config"), dict):
            ctx["llm_config"] = llm_config_from_payload(data)
        _rt.execute_run_with_plan(run, steps, ctx)
        if run.project_id:
            try:
                write_audit_log(
                    active_settings,
                    run.project_id,
                    "agent_run",
                    {
                        "kind": "agent_run",
                        "run_id": run.run_id,
                        "message": run.message,
                        "agent_plan": agent_plan,
                        "status": run.status,
                        "errors": run.errors,
                        "created_at": run.created_at,
                    },
                )
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to write agent run audit log.",
                    subsystem="app_factory.audit.agent_run",
                    context={"project_id": run.project_id, "run_id": run.run_id},
                )
        return {
            "agent": agent_plan,
            "run": _rt.run_to_dict(run),
        }

    @app.get("/api/agent/autopilot/runs/{run_id}")
    def get_agent_autopilot_run(run_id: str) -> dict[str, Any]:
        store = autopilot_store()
        try:
            return autopilot_run_response(store.load(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/agent/autopilot/runs/{run_id}/plan")
    def get_agent_autopilot_run_plan(run_id: str) -> dict[str, Any]:
        store = autopilot_store()
        try:
            return _agent_plan_response_from_run(store.load(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # The agentic-session adapter drives the workbench MCP tools directly.
    # Gated mutations pause here so the agentic path keeps the same approval
    # semantics as browser-originated actions.
    agentic_permission_broker = PermissionBroker()

    def _agentic_approval_names() -> set[str]:
        return build_approval_name_set(_rt.list_tools_for_mcp())

    @app.post("/api/agent/agentic/permission")
    def create_agentic_permission(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        """Called by the MCP permission bridge for agentic-session approvals."""
        data = payload or {}
        tool_name = str(data.get("tool_name") or "").strip()
        if not tool_name:
            raise HTTPException(status_code=400, detail="tool_name is required")
        tool_input = data.get("input") if isinstance(data.get("input"), dict) else {}
        run_id = data.get("run_id") or None
        if not _agentic_requires_approval(tool_name, _agentic_approval_names()):
            return {
                "status": "resolved",
                "decision": format_decision(allowed=True, tool_input=tool_input),
            }
        entry = agentic_permission_broker.create(
            run_id=run_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )
        dotted = _agentic_resolve_name(tool_name, _rt.list_tools_for_mcp())
        approval_payload = {
            "id": entry.permission_id,
            "agentic_permission_id": entry.permission_id,
            "tool_name": dotted,
            "input": tool_input,
            "level": "mutation",
            "explanation": f"The agent wants to run {dotted}. Approve to let it proceed.",
            "code_preview": tool_input.get("code") if isinstance(tool_input.get("code"), str) else None,
            "target_project_id": data.get("project_id"),
        }
        publish_agent_event(
            {
                "event_id": f"{run_id or 'agentic'}-approval-{entry.permission_id}",
                "type": "approval_requested",
                "run_id": run_id,
                "project_id": data.get("project_id"),
                "session_id": data.get("session_id"),
                "status": "awaiting_approval",
                "content": approval_payload["explanation"],
                "payload": approval_payload,
            }
        )
        return {"status": "pending", "permission_id": entry.permission_id}

    @app.get("/api/agent/agentic/permission/{permission_id}")
    def get_agentic_permission(permission_id: str, wait: float = 0.0) -> dict[str, Any]:
        # Optional long-poll: clamp to a sane ceiling so bridge polling stays
        # readable while approvals still resolve quickly.
        if wait and wait > 0:
            entry = agentic_permission_broker.wait(permission_id, min(float(wait), 30.0))
        else:
            entry = agentic_permission_broker.get(permission_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="unknown permission_id")
        if entry.status == "pending":
            return {"status": "pending", "permission_id": permission_id}
        return {"status": "resolved", "decision": agentic_permission_broker.decision_for(entry)}

    @app.post("/api/agent/agentic/permission/{permission_id}/resolve")
    def resolve_agentic_permission(
        permission_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """UI approve/deny for an agentic-session gated tool."""
        data = payload or {}
        approved = bool(data.get("approved", False))
        message = data.get("message")
        updated_input = data.get("updated_input") if isinstance(data.get("updated_input"), dict) else None
        entry = agentic_permission_broker.resolve(
            permission_id,
            approved=approved,
            message=message,
            updated_input=updated_input,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="unknown permission_id")
        publish_agent_event(
            {
                "event_id": f"{entry.run_id or 'agentic'}-approval-resolved-{permission_id}",
                "type": "approval_resolved",
                "run_id": entry.run_id,
                "project_id": data.get("project_id"),
                "session_id": data.get("session_id"),
                "status": "running" if approved else "blocked",
                "content": ("Approved." if approved else "Denied.") + f" ({entry.tool_name})",
                "payload": {
                    "agentic_permission_id": permission_id,
                    "approved": approved,
                    "tool_name": entry.tool_name,
                },
            }
        )
        return {
            "status": "resolved",
            "approved": approved,
            "decision": agentic_permission_broker.decision_for(entry),
        }

    @app.get("/api/agent/connections")
    def list_agent_connections() -> list[dict[str, Any]]:
        return agent_workbench.list_chat_connections(active_settings)
