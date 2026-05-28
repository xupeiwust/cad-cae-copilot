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
    """Push a lightweight notification so the UI knows to refresh the full run state."""
    try:
        from .. import agent_activity
    except Exception:
        return
    agent_activity.publish({
        "type": "autopilot_update",
        "project_id": state.project_id,
        "run_id": state.run_id,
        "status": state.status,
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
    ) -> None:
        self.store = store
        self.runtime_tools = runtime_tools
        self.adapters = adapters or adapter_registry()
        self.agent_context = agent_context or {}
        self.tool_executor = tool_executor

    def start(self, request: AutopilotRunRequest, *, run_id: str | None = None) -> AutopilotRunState:
        adapters = adapter_registry(request.fake_actions)
        adapters.update({k: v for k, v in self.adapters.items() if k not in adapters})
        adapter = adapters.get(request.adapter_id)
        if adapter is None:
            state = self._new_state(request, run_id=run_id)
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {request.adapter_id}")
            self.store.save(state)
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
        _publish_autopilot_update(state)
        return state

    def _new_state(self, request: AutopilotRunRequest, *, run_id: str | None = None) -> AutopilotRunState:
        return AutopilotRunState(
            run_id=run_id or uuid.uuid4().hex[:12],
            status="running",
            message=request.message,
            project_id=request.project_id,
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
        _publish_autopilot_update(state)

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
            state.observations.append(
                _observation(
                    "agent_activity",
                    f"Invoking {adapter.adapter_id} for the next action.",
                    {"adapter_id": adapter.adapter_id, "step_index": len(state.steps)},
                )
            )
            self._checkpoint(state)
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
            if result.status != "success" or result.action is None:
                state.status = "failed"
                state.errors.append(result.diagnostic or "Local agent adapter failed.")
                state.observations.append(_observation("tool_error", state.errors[-1], result.model_dump()))
                self._checkpoint(state)
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

            if action.action.type == "final":
                state.status = "completed"
                state.final_message = action.action.message
                state.observations.append(_observation("final", action.action.message))
                self._checkpoint(state)
                return
            if action.action.type == "ask_user":
                state.status = "blocked"
                state.observations.append(_observation("user_message", action.action.question))
                self._checkpoint(state)
                return
            if action.action.type == "chat":
                state.status = "chatting"
                state.observations.append(_observation("user_message", action.action.message))
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
                approval = AutopilotApproval(
                    id=uuid.uuid4().hex[:12],
                    tool_name=tool_call.tool_name,
                    input=tool_call.input,
                    level=policy.level,
                    explanation=policy.explanation,
                )
                state.status = "awaiting_approval"
                state.pending_approval = approval
                state.observations.append(
                    _observation("approval_required", policy.explanation, approval.model_dump())
                )
                self._checkpoint(state)
                return
            if not self._execute_allowed_tool(state, tool_call.tool_name, tool_call.input, policy.model_dump()):
                return
        state.status = "failed"
        state.errors.append(f"Autopilot exceeded max step count ({max_steps}).")
        self._checkpoint(state)

    def _execute_allowed_tool(
        self,
        state: AutopilotRunState,
        tool_name: str,
        tool_input: dict[str, Any],
        policy_data: dict[str, Any],
    ) -> bool:
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
            self._checkpoint(state)
            return True
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
        self._checkpoint(state)
        self._execute_followups(state, tool_name, tool_input)
        return True

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
            self._checkpoint(state)

    def continue_run(
        self,
        run_id: str,
        *,
        approved: bool,
        max_steps: int = 6,
        user_message: str | None = None,
    ) -> AutopilotRunState:
        state = self.store.load(run_id)
        # Handle chatting mode: append user message and resume the step loop.
        if state.status == "chatting" and user_message:
            state.status = "running"
            state.observations.append(_observation("user_message", user_message))
            self.store.save(state)
            adapter = self.adapters.get(state.adapter_id)
            if adapter is not None:
                self._step_loop(state, adapter, max_steps)
            state.updated_at = now_iso()
            self.store.save(state)
            _publish_autopilot_update(state)
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
            state.updated_at = now_iso()
            self.store.save(state)
            _publish_autopilot_update(state)
            return state
        state.status = "running"
        state.observations.append(
            _observation("user_message", f"User approved {approval.tool_name}.", approval.model_dump())
        )
        if not self._execute_allowed_tool(
            state,
            approval.tool_name,
            approval.input,
            {"level": approval.level, "requires_approval": True, "explanation": approval.explanation},
        ):
            self.store.save(state)
            _publish_autopilot_update(state)
            return state
        adapter = self.adapters.get(state.adapter_id)
        if adapter is None:
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {state.adapter_id}")
        else:
            self._step_loop(state, adapter, max_steps)
        state.updated_at = now_iso()
        self.store.save(state)
        _publish_autopilot_update(state)
        return state

    def cancel_run(self, run_id: str) -> AutopilotRunState:
        state = self.store.load(run_id)
        state.status = "cancelled"
        state.pending_approval = None
        state.updated_at = now_iso()
        state.observations.append(_observation("user_message", "Autopilot run cancelled."))
        self.store.save(state)
        _publish_autopilot_update(state)
        return state
