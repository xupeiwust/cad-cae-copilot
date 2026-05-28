from __future__ import annotations

import uuid
from typing import Any, Callable

from .adapters import LocalAgentAdapter, adapter_registry
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

    def start(self, request: AutopilotRunRequest) -> AutopilotRunState:
        adapters = adapter_registry(request.fake_actions)
        adapters.update({k: v for k, v in self.adapters.items() if k not in adapters})
        adapter = adapters.get(request.adapter_id)
        if adapter is None:
            state = self._new_state(request)
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {request.adapter_id}")
            self.store.save(state)
            return state
        state = self._new_state(request)
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
        self._step_loop(state, adapter, request.max_steps)
        self.store.save(state)
        return state

    def _new_state(self, request: AutopilotRunRequest) -> AutopilotRunState:
        return AutopilotRunState(
            run_id=uuid.uuid4().hex[:12],
            status="running",
            message=request.message,
            project_id=request.project_id,
            adapter_id=request.adapter_id,
            mode=request.mode,
            dry_run=request.dry_run,
            selected_geometry=request.selected_geometry,
        )

    def _step_loop(self, state: AutopilotRunState, adapter: LocalAgentAdapter, max_steps: int) -> None:
        for _ in range(max_steps):
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
                timeout_seconds=120,
            )
            if result.status != "success" or result.action is None:
                state.status = "failed"
                state.errors.append(result.diagnostic or "Local agent adapter failed.")
                state.observations.append(_observation("tool_error", state.errors[-1], result.model_dump()))
                return
            action = result.action
            step = AutopilotStep(index=len(state.steps), adapter_id=state.adapter_id, action=action)
            state.steps.append(step)
            state.updated_at = now_iso()

            if action.action.type == "final":
                state.status = "completed"
                state.final_message = action.action.message
                state.observations.append(_observation("final", action.action.message))
                return
            if action.action.type == "ask_user":
                state.status = "blocked"
                state.observations.append(_observation("user_message", action.action.question))
                return
            if action.action.type == "pause":
                state.status = "blocked"
                state.observations.append(_observation("policy_block", action.action.reason))
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
                return
            if not self._execute_allowed_tool(state, tool_call.tool_name, tool_call.input, policy.model_dump()):
                return
        state.status = "failed"
        state.errors.append(f"Autopilot exceeded max step count ({max_steps}).")

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
            return True
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
        if tool_name == "cae.apply_setup_patch":
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
                continue
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

    def continue_run(self, run_id: str, *, approved: bool, max_steps: int = 6) -> AutopilotRunState:
        state = self.store.load(run_id)
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
            return state
        adapter = self.adapters.get(state.adapter_id)
        if adapter is None:
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {state.adapter_id}")
        else:
            self._step_loop(state, adapter, max_steps)
        state.updated_at = now_iso()
        self.store.save(state)
        return state

    def cancel_run(self, run_id: str) -> AutopilotRunState:
        state = self.store.load(run_id)
        state.status = "cancelled"
        state.pending_approval = None
        state.updated_at = now_iso()
        state.observations.append(_observation("user_message", "Autopilot run cancelled."))
        self.store.save(state)
        return state
