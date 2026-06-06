"""Natural-language intent planning, action execution, and observation routes.

Extracted from ``app_factory.create_app`` (#9), verbatim. ``active_settings`` is
passed explicitly; domain modules are resolved at request time to preserve the
legacy import and monkeypatch behavior.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from .. import agent_workbench
from .. import runtime as _rt
from ..config import now_iso
from ..logging_utils import log_exception
from ..project_io import write_audit_log

LOGGER = logging.getLogger(__name__)

_READINESS_RELEVANT_TOOLS = {
    "engineering_template.save_draft",
    "engineering_template.adopt_targets",
    "engineering_template.generate_cad_fixture",
    "cae.prepare_solver_run",
}


def register_intent_planner_routes(app: FastAPI, *, active_settings: Any) -> None:
    def _structural_preflight_snapshot(project_id: str | None) -> dict[str, Any] | None:
        if not project_id:
            return None
        try:
            from .. import structural_adapter

            return structural_adapter.prepare_structural_run_preview(
                active_settings, str(project_id), None
            )
        except HTTPException:
            return None
        except Exception:
            log_exception(
                LOGGER,
                "Failed to build structural preflight snapshot for intent planning.",
                subsystem="app_factory.intent.structural_preflight",
                context={"project_id": project_id},
            )
            return None

    def _build_intent_plan(data: dict[str, Any]) -> dict[str, Any]:
        from .. import intent_planner

        message = str(data.get("message") or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        project_id = data.get("project_id") or None
        structural_preflight = _structural_preflight_snapshot(project_id)
        agent_context_snapshot = None
        if project_id:
            from .. import agent_context

            agent_context_snapshot = agent_context.build_agent_context(
                active_settings, str(project_id)
            )
        return intent_planner.plan_from_request(
            message=message,
            project_id=str(project_id) if project_id else None,
            runtime_tools=_rt.registered_tools_info(),
            capabilities=agent_workbench.list_capabilities(active_settings),
            structural_preflight=structural_preflight,
            agent_context=agent_context_snapshot,
        )

    @app.post("/api/intent-planner/plan")
    def create_intent_plan(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return _build_intent_plan(payload or {})

    @app.post("/api/intent-planner/actions/{action_id}/execute")
    def execute_intent_action(
        action_id: str, payload: dict[str, Any] = Body(default=None)
    ) -> dict[str, Any]:
        from .. import agent_observation, cad_observation, intent_planner

        data = payload or {}
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else None
        if plan is None:
            plan = _build_intent_plan(data)
        action = intent_planner.find_action(plan, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail=f"action not found in plan: {action_id}")
        tool_name = str(action.get("tool_name") or "")
        if tool_name not in set(_rt.registered_tool_names()):
            raise HTTPException(
                status_code=400,
                detail=f"action references unregistered tool: {tool_name}",
            )
        tool_args = action.get("tool_args") if isinstance(action.get("tool_args"), dict) else {}
        project_id = plan.get("project_id") or tool_args.get("project_id")
        step = {
            "id": action.get("id") or uuid.uuid4().hex[:10],
            "kind": "tool",
            "tool_name": tool_name,
            "name": tool_name,
            "description": action.get("description") or tool_name,
            "input": tool_args,
            "status": "pending",
            "approval_required": bool(action.get("requires_approval")),
        }
        run = _rt.RunRecord(
            run_id=uuid.uuid4().hex[:12],
            message=str(plan.get("message") or "intent action").strip() or "intent action",
            created_at=now_iso(),
            status="pending",
            project_id=str(project_id) if project_id else None,
        )
        ctx: dict[str, Any] = {
            "project_id": run.project_id,
            "workflow_id": "intent_planner",
            "intent_plan_id": plan.get("plan_id"),
            "intent_action_id": action.get("id"),
            "intent_action_mode": action.get("mode"),
        }
        preflight_before = _structural_preflight_snapshot(str(project_id) if project_id else None)
        _rt.execute_run_with_plan(run, [step], ctx)
        run_dict = _rt.run_to_dict(run)
        # Only re-evaluate readiness when the action could plausibly affect
        # it — saves a package read for pure inspection/preview steps.
        preflight_after = (
            _structural_preflight_snapshot(str(project_id) if project_id else None)
            if tool_name in _READINESS_RELEVANT_TOOLS and run.status == "completed"
            else preflight_before
        )
        cad_obs = (
            cad_observation.observe_cad_state(
                active_settings, str(project_id) if project_id else None,
            )
            if cad_observation.is_cad_related_action(action)
            else None
        )
        observation = agent_observation.build_observation(
            plan=plan,
            action=action,
            run=run_dict,
            structural_preflight_before=preflight_before,
            structural_preflight_after=preflight_after,
            cad_observation=cad_obs,
        )
        if run.project_id:
            try:
                write_audit_log(
                    active_settings,
                    run.project_id,
                    "intent_action",
                    {
                        "kind": "intent_action",
                        "run_id": run.run_id,
                        "plan_id": plan.get("plan_id"),
                        "action_id": action.get("id"),
                        "mode": action.get("mode"),
                        "tool_name": tool_name,
                        "status": run.status,
                        "errors": run.errors,
                        "created_at": run.created_at,
                        "observation_status": observation.get("status"),
                        "cad_observation_status": cad_obs.get("status") if cad_obs else None,
                    },
                )
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to write intent action audit log.",
                    subsystem="app_factory.audit.intent_action",
                    context={
                        "project_id": run.project_id,
                        "run_id": run.run_id,
                        "tool_name": tool_name,
                    },
                )
        return {
            "plan_id": plan.get("plan_id"),
            "action": action,
            "run": run_dict,
            "observation": observation,
        }

    @app.post("/api/intent-planner/observe")
    def observe_intent_action(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        """Recompute the observation for an already-submitted intent action.

        The frontend calls this after the existing approve/reject endpoints
        run so the observation reflects the live (post-approval) state of
        the run. The endpoint never executes a tool and never mutates the
        package.
        """
        from .. import agent_observation, cad_observation, intent_planner

        data = payload or {}
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else None
        if plan is None:
            raise HTTPException(status_code=400, detail="plan is required")
        action_id = str(data.get("action_id") or "").strip()
        if not action_id:
            raise HTTPException(status_code=400, detail="action_id is required")
        run_id = str(data.get("run_id") or "").strip()
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required")
        action = intent_planner.find_action(plan, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail=f"action not found in plan: {action_id}")
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        run_dict = _rt.run_to_dict(run)
        project_id = plan.get("project_id") or run.project_id
        tool_name = str(action.get("tool_name") or "")
        # We do not have the pre-execution snapshot any more; re-evaluate the
        # post-execution snapshot and present it as ``after`` only when it is
        # relevant. The delta is honestly reported with ``before=None`` so the
        # UI can show "after" readiness without inventing a delta.
        preflight_after = (
            _structural_preflight_snapshot(str(project_id) if project_id else None)
            if tool_name in _READINESS_RELEVANT_TOOLS and run.status == "completed"
            else None
        )
        cad_obs = (
            cad_observation.observe_cad_state(
                active_settings, str(project_id) if project_id else None,
            )
            if cad_observation.is_cad_related_action(action)
            else None
        )
        observation = agent_observation.build_observation(
            plan=plan,
            action=action,
            run=run_dict,
            structural_preflight_before=None,
            structural_preflight_after=preflight_after,
            cad_observation=cad_obs,
        )
        return {
            "plan_id": plan.get("plan_id"),
            "action": action,
            "run": run_dict,
            "observation": observation,
        }
