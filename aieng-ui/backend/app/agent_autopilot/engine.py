from __future__ import annotations

import uuid
from typing import Any, Callable

from .adapters import DEFAULT_STEP_TIMEOUT_SECONDS, LocalAgentAdapter, adapter_registry
from .policy import evaluate_tool_call
from .prompts import build_action_prompt
from .schema import (
    AutopilotAgentAction,
    AutopilotApproval,
    AutopilotObservation,
    AutopilotRunRequest,
    AutopilotRunState,
    AutopilotStep,
    now_iso,
)
from .store import AutopilotStore


def _publish_autopilot_update(state: AutopilotRunState) -> None:
    """Push the current run state over the shared UI SSE stream."""
    try:
        from .. import agent_activity
    except Exception:
        return
    agent_activity.publish({
        "type": "autopilot_update",
        "project_id": state.project_id,
        "session_id": state.session_id,
        "run_id": state.run_id,
        "status": state.status,
        "run": state.model_dump(),
    })


def _observation(kind: str, summary: str, data: dict[str, Any] | None = None) -> AutopilotObservation:
    return AutopilotObservation(
        id=uuid.uuid4().hex[:12],
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        data=data or {},
    )


class AutopilotEngine:
    def __init__(
        self,
        *,
        store: AutopilotStore,
        runtime_tools: list[dict[str, Any]],
        adapters: dict[str, LocalAgentAdapter] | None = None,
        agent_context: dict[str, Any] | None = None,
        tool_executor: Callable[[str, dict[str, Any]], Any] | None = None,
        on_state_update: Callable[[AutopilotRunState], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.store = store
        self.runtime_tools = runtime_tools
        self.adapters = adapters or adapter_registry()
        self.agent_context = agent_context or {}
        self.tool_executor = tool_executor
        self.on_state_update = on_state_update
        self.on_event = on_event

    def start(self, request: AutopilotRunRequest, *, run_id: str | None = None) -> AutopilotRunState:
        adapters = adapter_registry(request.fake_actions)
        adapters.update({k: v for k, v in self.adapters.items() if k not in adapters})
        adapter = adapters.get(request.adapter_id)
        if adapter is None:
            state = self._new_state(request, run_id=run_id)
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {request.adapter_id}")
            self.store.save(state)
            self._publish_state(state)
            return state
        state = self._new_state(request, run_id=run_id)
        state.observations.append(
            _observation(
                "context",
                "Autopilot run started.",
                {
                    "project_id": request.project_id,
                    "selected_geometry": request.selected_geometry,
                    "tool_count": len(self.runtime_tools),
                },
            )
        )
        if not request.fake_actions:
            self._bootstrap_project_context(state)
        self._step_loop(state, adapter, request.max_steps)
        self.store.save(state)
        self._publish_state(state)
        return state

    def _new_state(self, request: AutopilotRunRequest, *, run_id: str | None = None) -> AutopilotRunState:
        return AutopilotRunState(
            run_id=run_id or uuid.uuid4().hex[:12],
            status="running",
            message=request.message,
            project_id=request.project_id,
            session_id=request.session_id,
            adapter_id=request.adapter_id,
            mode=request.mode,
            dry_run=request.dry_run,
            selected_geometry=request.selected_geometry,
            llm_config=request.llm_config,
        )

    def _registered_tool_names(self) -> set[str]:
        return {str(tool.get("name")) for tool in self.runtime_tools if tool.get("name")}

    def _checkpoint(self, state: AutopilotRunState) -> None:
        state.updated_at = now_iso()
        self.store.save(state)
        self._publish_state(state)

    def _publish_state(self, state: AutopilotRunState) -> None:
        if self.on_state_update is not None:
            try:
                self.on_state_update(state)
            except Exception:
                pass
        _publish_autopilot_update(state)

    def _emit_event(
        self,
        state: AutopilotRunState,
        event_type: str,
        *,
        status: str | None = None,
        content: str | None = None,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> None:
        event = {
            "event_id": event_id or f"{state.run_id}-{len(state.observations)}-{event_type}-{uuid.uuid4().hex[:8]}",
            "type": event_type,
            "project_id": state.project_id,
            "session_id": state.session_id,
            "run_id": state.run_id,
            "status": status,
            "content": content,
            "payload": payload or {},
            "created_at": now_iso(),
        }
        if self.on_event is not None:
            try:
                self.on_event(event)
                return
            except Exception:
                pass
        try:
            from .. import agent_activity

            agent_activity.publish(event)
        except Exception:
            pass

    def _cancel_if_requested(self, state: AutopilotRunState) -> bool:
        if not self.store.is_cancel_requested(state.run_id):
            return False
        state.status = "cancelled"
        state.pending_approval = None
        state.observations.append(_observation("user_message", "Autopilot run cancelled."))
        self.store.clear_cancel(state.run_id)
        self._emit_event(state, "run_cancelled", status="cancelled", content="Autopilot run cancelled.")
        self._checkpoint(state)
        return True

    def _bootstrap_project_context(self, state: AutopilotRunState) -> None:
        if state.dry_run or self.tool_executor is None or not state.project_id:
            return
        if "aieng.agent_context" not in self._registered_tool_names():
            return
        state.observations.append(
            _observation(
                "agent_activity",
                "Loading project context with aieng.agent_context.",
                {"tool_name": "aieng.agent_context", "input": {"project_id": state.project_id}},
            )
        )
        self._checkpoint(state)
        try:
            output = self.tool_executor("aieng.agent_context", {"project_id": state.project_id})
        except Exception as exc:
            state.observations.append(
                _observation(
                    "tool_error",
                    f"Initial aieng.agent_context failed: {exc}",
                    {"tool_name": "aieng.agent_context", "input": {"project_id": state.project_id}},
                )
            )
            return
        state.observations.append(
            _observation(
                "tool_result",
                "Loaded initial project context with aieng.agent_context.",
                {
                    "dry_run": False,
                    "tool_name": "aieng.agent_context",
                    "input": {"project_id": state.project_id},
                    "policy": {
                        "level": "auto_read",
                        "requires_approval": False,
                        "explanation": "Read-only project context is safe to load before the first agent step.",
                    },
                    "output": output if isinstance(output, dict) else {"value": output},
                },
            )
        )
        self._checkpoint(state)

    def _step_loop(self, state: AutopilotRunState, adapter: LocalAgentAdapter, max_steps: int) -> None:
        for _ in range(max_steps):
            if self._cancel_if_requested(state):
                return
            if state.queued_user_messages:
                queued = list(state.queued_user_messages)
                state.queued_user_messages.clear()
                for message in queued:
                    state.observations.append(_observation("user_message", f"Queued follow-up: {message}", {"queued": True}))
                self._checkpoint(state)
            state.observations.append(
                _observation(
                    "agent_activity",
                    f"Invoking {adapter.adapter_id} for the next action.",
                    {"adapter_id": adapter.adapter_id, "step_index": len(state.steps)},
                )
            )
            self._checkpoint(state)
            self._emit_event(
                state,
                "run_status_changed",
                status=state.status,
                content=f"Invoking {adapter.adapter_id} for the next action.",
                payload={"adapter_id": adapter.adapter_id, "step_index": len(state.steps)},
            )
            prompt = build_action_prompt(
                objective=state.message,
                project_id=state.project_id,
                selected_geometry=state.selected_geometry,
                agent_context=self.agent_context,
                runtime_tools=self.runtime_tools,
                observations=[obs.model_dump() for obs in state.observations],
            )
            result = adapter.invoke(
                prompt=prompt,
                action_schema=AutopilotAgentAction.json_schema_for_adapter(),
                timeout_seconds=DEFAULT_STEP_TIMEOUT_SECONDS,
            )
            if self._cancel_if_requested(state):
                return
            if result.status != "success" or result.action is None:
                state.status = "failed"
                state.errors.append(result.diagnostic or "Local agent adapter failed.")
                state.observations.append(_observation("tool_error", state.errors[-1], result.model_dump()))
                self._checkpoint(state)
                self._emit_event(state, "tool_failed", status="failed", content=state.errors[-1], payload=result.model_dump())
                return
            action = result.action
            step = AutopilotStep(index=len(state.steps), adapter_id=state.adapter_id, action=action)
            state.steps.append(step)
            state.updated_at = now_iso()
            state.observations.append(
                _observation(
                    "agent_activity",
                    f"{adapter.adapter_id} selected {action.action.type}.",
                    {"adapter_id": adapter.adapter_id, "action_type": action.action.type},
                )
            )
            if action.thought_summary:
                self._emit_event(
                    state,
                    "agent_message",
                    status=state.status,
                    content=action.thought_summary,
                    payload={"kind": "thought_summary"},
                )
            if action.user_message:
                self._emit_event(
                    state,
                    "agent_message",
                    status=state.status,
                    content=action.user_message,
                    payload={"kind": "user_message"},
                )

            if action.action.type == "final":
                state.status = "completed"
                state.final_message = action.action.message
                state.observations.append(_observation("final", action.action.message))
                self._emit_event(state, "agent_message", status="completed", content=action.action.message, payload={"kind": "final"})
                self._emit_event(state, "run_status_changed", status="completed", content="Autopilot run completed.")
                self._checkpoint(state)
                return
            if action.action.type == "ask_user":
                state.status = "blocked"
                state.observations.append(_observation("user_message", action.action.question))
                self._emit_event(state, "agent_message", status="blocked", content=action.action.question, payload={"kind": "ask_user"})
                self._checkpoint(state)
                return
            if action.action.type == "chat":
                state.status = "chatting"
                state.observations.append(_observation("user_message", action.action.message))
                self._emit_event(state, "agent_message", status="chatting", content=action.action.message, payload={"kind": "chat"})
                self._checkpoint(state)
                return
            if action.action.type == "pause":
                state.status = "blocked"
                state.observations.append(_observation("policy_block", action.action.reason))
                self._checkpoint(state)
                return
            tool_call = action.action
            policy = evaluate_tool_call(
                tool_name=tool_call.tool_name,
                tool_input=tool_call.input,
                active_project_id=state.project_id,
                registered_tools=self.runtime_tools,
                mode=state.mode,
            )
            state.steps[-1].policy = policy.model_dump()
            if not policy.allowed:
                state.observations.append(
                    _observation(
                        "policy_block",
                        policy.explanation,
                        {"tool_name": tool_call.tool_name, "level": policy.level},
                    )
                )
                self._checkpoint(state)
                continue
            if policy.requires_approval:
                approval_payload = self._approval_payload(
                    tool_name=tool_call.tool_name,
                    tool_input=tool_call.input,
                    level=policy.level,
                    explanation=policy.explanation,
                    state=state,
                )
                approval = AutopilotApproval(
                    id=uuid.uuid4().hex[:12],
                    tool_name=tool_call.tool_name,
                    input=tool_call.input,
                    level=policy.level,
                    explanation=policy.explanation,
                    **approval_payload,
                )
                state.status = "awaiting_approval"
                state.pending_approval = approval
                state.observations.append(
                    _observation("approval_required", policy.explanation, approval.model_dump())
                )
                self._emit_event(
                    state,
                    "approval_requested",
                    status="awaiting_approval",
                    content=policy.explanation,
                    payload=approval.model_dump(),
                    event_id=f"{state.run_id}-approval-{approval.id}",
                )
                self._checkpoint(state)
                return
            if not self._execute_allowed_tool(state, tool_call.tool_name, tool_call.input, policy.model_dump()):
                return
        state.status = "failed"
        state.errors.append(f"Autopilot exceeded max step count ({max_steps}).")
        self._emit_event(state, "run_status_changed", status="failed", content=state.errors[-1])
        self._checkpoint(state)

    def _approval_payload(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        level: str,
        explanation: str,
        state: AutopilotRunState,
    ) -> dict[str, str | None]:
        code = tool_input.get("code")
        project_id = tool_input.get("project_id") or state.project_id
        mutates = tool_name.startswith("cad.") or tool_name.startswith("cae.") or tool_name == "aieng.convert"
        side_effect = "Will update project geometry/artifacts." if mutates else "Will run the selected workbench tool."
        if tool_name == "cae.run_solver":
            side_effect = "Will run the external solver and write result artifacts."
        return {
            "side_effect_summary": side_effect,
            "risk_summary": explanation or f"Policy level: {level}",
            "target_project_id": str(project_id) if project_id else None,
            "code_preview": str(code)[:8000] if isinstance(code, str) else None,
            "artifact_preview": None,
            "recommended_action": "Approve if the target project, code, and side effects match your intent.",
        }

    def _execute_allowed_tool(
        self,
        state: AutopilotRunState,
        tool_name: str,
        tool_input: dict[str, Any],
        policy_data: dict[str, Any],
    ) -> bool:
        if self._cancel_if_requested(state):
            return False
        if state.dry_run or self.tool_executor is None:
            state.observations.append(
                _observation(
                    "tool_result",
                    f"Dry-run accepted tool call: {tool_name}",
                    {
                        "dry_run": True,
                        "tool_name": tool_name,
                        "input": tool_input,
                        "policy": policy_data,
                    },
                )
            )
            self._checkpoint(state)
            return True
        state.observations.append(
            _observation(
                "agent_activity",
                f"Executing workbench tool: {tool_name}",
                {"tool_name": tool_name, "input": tool_input, "policy": policy_data},
            )
        )
        self._emit_event(
            state,
            "tool_started",
            status="running",
            content=f"Executing workbench tool: {tool_name}",
            payload={"tool_name": tool_name, "input": tool_input, "policy": policy_data},
        )
        self._checkpoint(state)
        try:
            output = self.tool_executor(tool_name, tool_input)
        except Exception as exc:
            state.observations.append(
                _observation(
                    "tool_error",
                    f"Tool {tool_name} failed: {exc}",
                    {
                        "tool_name": tool_name,
                        "input": tool_input,
                        "policy": policy_data,
                    },
                )
            )
            self._emit_event(
                state,
                "tool_failed",
                status="failed",
                content=f"Tool {tool_name} failed: {exc}",
                payload={"tool_name": tool_name, "input": tool_input, "policy": policy_data, "error": str(exc)},
            )
            self._checkpoint(state)
            return True
        if self._cancel_if_requested(state):
            return False
        state.observations.append(
            _observation(
                "tool_result",
                f"Executed tool call: {tool_name}",
                {
                    "dry_run": False,
                    "tool_name": tool_name,
                    "input": tool_input,
                    "policy": policy_data,
                    "output": output if isinstance(output, dict) else {"value": output},
                },
            )
        )
        output_payload = output if isinstance(output, dict) else {"value": output}
        self._emit_event(
            state,
            "tool_completed",
            status="done",
            content=f"Executed tool call: {tool_name}",
            payload={"tool_name": tool_name, "input": tool_input, "policy": policy_data, **output_payload},
        )
        artifact_payload = self._artifact_payload(output_payload)
        if artifact_payload:
            self._emit_event(
                state,
                "artifact_ready",
                status="done",
                content=artifact_payload.get("summary"),
                payload={"tool_name": tool_name, **artifact_payload},
            )
        self._checkpoint(state)
        self._execute_followups(state, tool_name, tool_input)
        return True

    def _artifact_payload(self, output: dict[str, Any]) -> dict[str, Any] | None:
        keys = {"preview_url", "preview_format", "artifact_paths", "written_artifacts", "named_parts", "parts_added", "geometry_report", "solver_run_id", "result_summary"}
        if not any(key in output for key in keys):
            return None
        named_parts = output.get("named_parts") if isinstance(output.get("named_parts"), list) else []
        parts_added = output.get("parts_added") if isinstance(output.get("parts_added"), list) else []
        artifact_paths = []
        for key in ("artifact_paths", "written_artifacts"):
            value = output.get(key)
            if isinstance(value, list):
                artifact_paths.extend(item for item in value if isinstance(item, str))
        summary = "Artifact ready"
        if parts_added:
            summary = f"CAD updated: {len(parts_added)} part(s) added."
        elif named_parts:
            summary = f"CAD ready: {len(named_parts)} named part(s)."
        elif artifact_paths:
            summary = f"{len(artifact_paths)} artifact(s) ready."
        return {
            "summary": summary,
            "preview_url": output.get("preview_url"),
            "preview_format": output.get("preview_format"),
            "artifact_paths": artifact_paths,
            "named_parts": named_parts,
            "parts_added": parts_added,
            "geometry_report": output.get("geometry_report"),
            "solver_run_id": output.get("solver_run_id") or output.get("run_id"),
            "result_summary": output.get("result_summary"),
        }

    def _execute_followups(
        self,
        state: AutopilotRunState,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        if state.dry_run or self.tool_executor is None:
            return
        project_id = tool_input.get("project_id") or state.project_id
        if not project_id:
            return
        followups: list[tuple[str, dict[str, Any]]] = []
        if tool_name == "cad.execute_build123d":
            # CAD critique is deterministic/read-only and keeps later agent prompts
            # compact by surfacing only blocking manufacturability objections.
            followups.append(("cad.critique", {"project_id": project_id, "mode": "auto"}))
        elif tool_name == "cae.apply_setup_patch":
            followups.append(("cae.prepare_solver_run", {"project_id": project_id}))
        elif tool_name == "cae.run_solver":
            run_id = tool_input.get("runId") or tool_input.get("run_id")
            base = {"project_id": project_id, **({"runId": run_id} if run_id else {})}
            followups.extend(
                [
                    ("cae.extract_solver_results", dict(base)),
                    ("cae.extract_field_regions", {"project_id": project_id, "field": "stress"}),
                    ("postprocess.refresh_cae_summary", {"project_id": project_id}),
                ]
            )
        if not followups:
            return
        registered = {str(tool.get("name")) for tool in self.runtime_tools if tool.get("name")}
        for followup_name, followup_input in followups:
            if self._cancel_if_requested(state):
                return
            if followup_name not in registered:
                state.observations.append(
                    _observation(
                        "tool_error",
                        f"Skipped Autopilot follow-up; tool is not registered: {followup_name}",
                        {"tool_name": followup_name, "input": followup_input},
                    )
                )
                self._checkpoint(state)
                continue
            state.observations.append(
                _observation(
                    "agent_activity",
                    f"Executing Autopilot follow-up: {followup_name}",
                    {"tool_name": followup_name, "input": followup_input, "followup_for": tool_name},
                )
            )
            self._emit_event(
                state,
                "tool_started",
                status="running",
                content=f"Executing Autopilot follow-up: {followup_name}",
                payload={"tool_name": followup_name, "input": followup_input, "followup_for": tool_name},
            )
            self._checkpoint(state)
            try:
                output = self.tool_executor(followup_name, followup_input)
            except Exception as exc:
                state.observations.append(
                    _observation(
                        "tool_error",
                        f"Autopilot follow-up {followup_name} failed: {exc}",
                        {"tool_name": followup_name, "input": followup_input},
                    )
                )
                self._emit_event(
                    state,
                    "tool_failed",
                    status="failed",
                    content=f"Autopilot follow-up {followup_name} failed: {exc}",
                    payload={"tool_name": followup_name, "input": followup_input, "error": str(exc)},
                )
                self._checkpoint(state)
                continue
            state.observations.append(
                _observation(
                    "tool_result",
                    f"Executed Autopilot follow-up: {followup_name}",
                    {
                        "dry_run": False,
                        "tool_name": followup_name,
                        "input": followup_input,
                        "followup_for": tool_name,
                        "output": output if isinstance(output, dict) else {"value": output},
                    },
                )
            )
            output_payload = output if isinstance(output, dict) else {"value": output}
            self._emit_event(
                state,
                "tool_completed",
                status="done",
                content=f"Executed Autopilot follow-up: {followup_name}",
                payload={"tool_name": followup_name, "input": followup_input, "followup_for": tool_name, **output_payload},
            )
            self._checkpoint(state)

    def continue_run(
        self,
        run_id: str,
        *,
        approved: bool,
        max_steps: int = 10,
        user_message: str | None = None,
    ) -> AutopilotRunState:
        state = self.store.load(run_id)
        if user_message and state.status != "awaiting_approval":
            return self.reply_to_run(run_id, user_message, max_steps=max_steps)
        if user_message and state.status == "awaiting_approval":
            state.observations.append(_observation("user_message", f"Revision request: {user_message}", {"revision_request": True}))
            state.pending_approval = None
            state.status = "running"
            self._emit_event(
                state,
                "approval_resolved",
                status="running",
                content="User asked the agent to revise the pending action.",
                payload={"approved": False, "revision_request": user_message},
            )
            self._checkpoint(state)
            adapter = self.adapters.get(state.adapter_id)
            if adapter is not None:
                self._step_loop(state, adapter, max_steps)
            return state

        if state.status != "awaiting_approval" or state.pending_approval is None:
            return state
        approval = state.pending_approval
        state.pending_approval = None
        if not approved:
            state.status = "blocked"
            state.errors.append(f"User rejected approval for {approval.tool_name}.")
            state.observations.append(
                _observation(
                    "user_message",
                    f"User rejected approval for {approval.tool_name}.",
                    approval.model_dump(),
                )
            )
            self._emit_event(
                state,
                "approval_resolved",
                status="blocked",
                content=f"User rejected approval for {approval.tool_name}.",
                payload={"approved": False, **approval.model_dump()},
            )
            state.updated_at = now_iso()
            self.store.save(state)
            self._publish_state(state)
            return state
        state.status = "running"
        state.observations.append(
            _observation("user_message", f"User approved {approval.tool_name}.", approval.model_dump())
        )
        self._emit_event(
            state,
            "approval_resolved",
            status="running",
            content=f"User approved {approval.tool_name}.",
            payload={"approved": True, **approval.model_dump()},
        )
        if not self._execute_allowed_tool(
            state,
            approval.tool_name,
            approval.input,
            {"level": approval.level, "requires_approval": True, "explanation": approval.explanation},
        ):
            self.store.save(state)
            self._publish_state(state)
            return state
        adapter = self.adapters.get(state.adapter_id)
        if adapter is None:
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {state.adapter_id}")
        else:
            self._step_loop(state, adapter, max_steps)
        state.updated_at = now_iso()
        self.store.save(state)
        self._publish_state(state)
        return state

    def reply_to_run(self, run_id: str, message: str, *, max_steps: int = 10) -> AutopilotRunState:
        state = self.store.load(run_id)
        if state.status in {"completed", "failed", "cancelled"}:
            return state
        if state.status == "awaiting_approval":
            state.pending_approval = None
            state.observations.append(_observation("user_message", f"Revision request: {message}", {"revision_request": True}))
            self._emit_event(
                state,
                "approval_resolved",
                status="running",
                content="User asked the agent to revise the pending action.",
                payload={"approved": False, "revision_request": message},
            )
        else:
            state.observations.append(_observation("user_message", message, {"reply": True}))
        state.status = "running"
        self._emit_event(state, "agent_message", status="running", content=message, payload={"role": "user", "kind": "reply"})
        self._checkpoint(state)
        adapter = self.adapters.get(state.adapter_id)
        if adapter is None:
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {state.adapter_id}")
        else:
            self._step_loop(state, adapter, max_steps)
        state.updated_at = now_iso()
        self.store.save(state)
        self._publish_state(state)
        return state

    def follow_up_run(self, run_id: str, message: str) -> AutopilotRunState:
        state = self.store.load(run_id)
        if state.status in {"completed", "failed", "cancelled"}:
            return state
        if state.status in {"running", "awaiting_approval"}:
            state.queued_user_messages.append(message)
            state.observations.append(_observation("user_message", f"Queued follow-up: {message}", {"queued": True}))
            self._emit_event(
                state,
                "run_status_changed",
                status="queued",
                content="Follow-up queued for the next agent step.",
                payload={"message": message},
            )
            self._checkpoint(state)
            return state
        return self.reply_to_run(run_id, message)

    def cancel_run(self, run_id: str) -> AutopilotRunState:
        state = self.store.load(run_id)
        self.store.request_cancel(run_id)
        state.status = "cancelled"
        state.pending_approval = None
        state.updated_at = now_iso()
        state.observations.append(_observation("user_message", "Autopilot run cancelled."))
        self._emit_event(state, "run_cancelled", status="cancelled", content="Autopilot run cancelled.")
        self.store.save(state)
        self._publish_state(state)
        return state
