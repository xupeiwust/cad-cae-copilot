from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

from .adapters import DEFAULT_STEP_TIMEOUT_SECONDS, LocalAgentAdapter, adapter_registry
from .context_memory import ContextMemoryManager
from .policy import evaluate_tool_call
from .prompts import build_system_layer, OPERATING_RULES
from .schema import (
    AgentPlan,
    AgentPlanStep,
    AgentWorkingState,
    AutopilotAgentAction,
    AutopilotErrorClass,
    AutopilotApproval,
    AutopilotObservation,
    AutopilotRunRequest,
    AutopilotRunState,
    AutopilotStep,
    now_iso,
)
from .store import AutopilotStore


# Per-run adapter step counter.  Key = "{effective_adapter_session_id}:{adapter_id}".
# Value = next step index for the in-flight run on that session+adapter.
# step_index==0 tells an adapter (e.g. Claude Code CLI) the first call of a run
# should open the session (--session-id); >0 means reconnect (--resume).  The
# counter is cleared when the run reaches a terminal state (see _checkpoint) so a
# later run on the same chat session starts a fresh sequence rather than
# inheriting the previous run's index.  Cross-run conversational continuity is
# preserved by the adapter itself (the CLI session id is derived from the chat
# session id, and Claude Code falls back to --resume if --session-id is "already
# in use").  Access is guarded by _STEP_COUNTER_LOCK because the step loop runs
# on background worker threads.
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
_STEP_COUNTER_LOCK = threading.Lock()
_SESSION_STEP_COUNTERS: dict[str, int] = {}


def _step_counter_key(session_id: str | None, adapter_id: str) -> str:
    return f"{session_id or '_none_'}:{adapter_id}"


def _session_step_index(session_id: str | None, adapter_id: str) -> int:
    key = _step_counter_key(session_id, adapter_id)
    with _STEP_COUNTER_LOCK:
        idx = _SESSION_STEP_COUNTERS.get(key, 0)
        _SESSION_STEP_COUNTERS[key] = idx + 1
        return idx


def _clear_step_counter(session_id: str | None, adapter_id: str) -> None:
    with _STEP_COUNTER_LOCK:
        _SESSION_STEP_COUNTERS.pop(_step_counter_key(session_id, adapter_id), None)


def clear_session_step_counters(session_id: str | None) -> None:
    """Drop every adapter step counter for a chat session (e.g. on session delete)."""
    prefix = f"{session_id or '_none_'}:"
    with _STEP_COUNTER_LOCK:
        for key in [key for key in _SESSION_STEP_COUNTERS if key.startswith(prefix)]:
            _SESSION_STEP_COUNTERS.pop(key, None)


def _effective_adapter_session_id(state: AutopilotRunState) -> str:
    """Stable session id passed to session-aware local adapters.

    UI chat sessions remain the stable key when present. Runs launched without a
    chat session still need a stable adapter conversation across approval/follow-
    up steps; use the run id instead of passing None, otherwise adapters such as
    Claude Code generate a fresh UUID per invocation and `--resume` cannot find
    step 0's conversation.
    """
    return state.session_id or f"run:{state.run_id}"


DEFAULT_PLAN_STEPS = [
    ("observe_context", "Observe context", "observe"),
    ("select_skill_or_tool", "Select skill/tool", "skill"),
    ("prepare_action", "Prepare action", "tool"),
    ("await_approval", "Await approval when needed", "approval"),
    ("execute_tool", "Execute", "tool"),
    ("repair_tool_input", "Repair tool input", "repair"),
    ("verify_result", "Verify", "verify"),
    ("summarize_result", "Summarize", "summarize"),
]

CAD_MUTATION_TOOLS = frozenset({
    "cad.execute_build123d",
    "cad.edit_parameter",
    "cad.replace_part",
    "cad.remove_part",
    "cad.refine",
    "aieng.apply_shape_ir_patch",
    "aieng.convert",
})

GEOMETRY_MUTATION_REPAIR_INSTRUCTION = (
    "The user requested a geometry change, but no CAD mutation tool has succeeded yet. "
    "Select a CAD mutation tool or ask the user for clarification."
)

_GEOMETRY_CREATE_TERMS = (
    "创建",
    "生成",
    "画",
    "建模",
    "create",
    "generate",
    "build",
    "draw",
)

_GEOMETRY_MODIFY_TERMS = (
    "修改",
    "改成",
    "加",
    "删除",
    "替换",
    "变成",
    "优化外形",
    "modify",
    "change",
    "add",
    "remove",
    "replace",
    "make it",
    "turn into",
)

SIMULATION_PLAN_STEPS = [
    ("observe_context", "Inspect CAD/CAE context", "observe"),
    ("select_skill_or_tool", "Select simulation workflow", "skill"),
    ("prepare_action", "Prepare CAE setup, preflight, or solver deck action", "tool"),
    ("await_approval", "Request approval before solver execution", "approval"),
    ("execute_tool", "Execute current CAE workflow step", "tool"),
    ("repair_tool_input", "Repair CAE tool input", "repair"),
    ("verify_result", "Preflight readiness or parse solver results", "verify"),
    ("summarize_result", "Summarize simulation evidence", "summarize"),
]


def _geometry_mutation_intent(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered for term in _GEOMETRY_MODIFY_TERMS):
        return "modify_geometry"
    if any(term in lowered for term in _GEOMETRY_CREATE_TERMS):
        return "create_geometry"
    return None


def _latest_geometry_mutation_intent(state: AutopilotRunState) -> str | None:
    messages = [state.message]
    for obs in state.observations:
        if obs.kind != "user_message":
            continue
        if obs.data.get("reply") or obs.data.get("queued") or obs.data.get("revision_request"):
            messages.append(obs.summary)
    for message in reversed(messages):
        intent = _geometry_mutation_intent(str(message))
        if intent:
            return intent
    return None


def _is_successful_cad_mutation_observation(obs: AutopilotObservation) -> bool:
    if obs.kind != "tool_result":
        return False
    data = obs.data if isinstance(obs.data, dict) else {}
    if data.get("dry_run") is True:
        return False
    if data.get("tool_name") not in CAD_MUTATION_TOOLS:
        return False
    output = data.get("output")
    if isinstance(output, dict):
        status = str(output.get("status") or "").lower()
        if status in {"error", "failed", "failure"} or output.get("error"):
            return False
    return True


def _has_successful_cad_mutation(state: AutopilotRunState) -> bool:
    return any(_is_successful_cad_mutation_observation(obs) for obs in state.observations)


def _looks_like_simulation_objective(objective: str) -> bool:
    text = objective.lower()
    simulation_terms = (
        "simulate",
        "simulation",
        "solver",
        "calculix",
        "ccx",
        "fea",
        "fem",
        "stress",
        "displacement",
        "deflection",
        "load case",
        "run cae",
    )
    return any(term in text for term in simulation_terms)


def create_default_agent_plan(objective: str, *, plan_id: str | None = None) -> AgentPlan:
    template = SIMULATION_PLAN_STEPS if _looks_like_simulation_objective(objective) else DEFAULT_PLAN_STEPS
    steps = [
        AgentPlanStep(id=step_id, title=title, kind=kind)  # type: ignore[arg-type]
        for step_id, title, kind in template
    ]
    return AgentPlan(
        id=plan_id or uuid.uuid4().hex[:12],
        objective=objective,
        status="running",
        steps=steps,
        current_step_id="observe_context",
    )


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


def _classified_error_data(
    error_class: AutopilotErrorClass,
    *,
    tool_name: str | None = None,
    tool_input: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    error: str | None = None,
    recoverable: bool | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if recoverable is None:
        recoverable = error_class in {"schema_error", "tool_runtime_error", "cad_build_error", "timeout", "missing_context"}
    return {
        "error_class": error_class,
        "recoverable": recoverable,
        **({"tool_name": tool_name} if tool_name else {}),
        **({"input": tool_input} if tool_input is not None else {}),
        **({"policy": policy} if policy is not None else {}),
        **({"error": error} if error else {}),
        **extra,
    }


def _classify_exception(tool_name: str | None, exc: Exception) -> AutopilotErrorClass:
    text = f"{type(exc).__name__}: {exc}".lower()
    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        return "timeout"
    if tool_name == "cad.execute_build123d" or "build123d" in text or "cad build" in text:
        return "cad_build_error"
    if "project_id" in text or "missing" in text:
        return "missing_context"
    return "tool_runtime_error"


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
        approval_mode: str = "balanced",
    ) -> None:
        self.store = store
        self.runtime_tools = runtime_tools
        self.adapters = adapters or adapter_registry()
        self.agent_context = agent_context or {}
        self.tool_executor = tool_executor
        self.on_state_update = on_state_update
        self.on_event = on_event
        self.approval_mode = approval_mode if approval_mode in {"balanced", "strict", "manual"} else "balanced"
        self._system_layer = build_system_layer(
            runtime_tools=self.runtime_tools,
            rules=OPERATING_RULES,
        )
        self.memory = ContextMemoryManager(system_content=self._system_layer)
        self._memory_run_id: str | None = None

    def _reset_memory(self, run_id: str) -> None:
        self.memory = ContextMemoryManager(system_content=self._system_layer)
        self._memory_run_id = run_id

    def _ensure_memory_for_state(self, state: AutopilotRunState) -> None:
        """Bind the prompt memory to the current run.

        Engines are short-lived in the API path, but tests and direct callers may
        reuse one instance. Keeping the memory keyed by run prevents observations
        from one local-agent turn from leaking into the next.
        """
        if self._memory_run_id == state.run_id:
            return
        self._reset_memory(state.run_id)
        if state.observations:
            self.memory.add_observations([obs.model_dump() for obs in state.observations])

    def start(self, request: AutopilotRunRequest, *, run_id: str | None = None) -> AutopilotRunState:
        adapters = adapter_registry(request.fake_actions)
        adapters.update({k: v for k, v in self.adapters.items() if k not in adapters})
        adapter = adapters.get(request.adapter_id)
        if adapter is None:
            state = self._new_state(request, run_id=run_id)
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {request.adapter_id}")
            self._finish_plan(state, "failed", state.errors[-1])
            self.store.save(state)
            self._publish_state(state)
            return state
        state = self._new_state(request, run_id=run_id)
        self._reset_memory(state.run_id)
        self._emit_plan_created(state)
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
        self._set_plan_step(state, "observe_context", "completed", summary="Initial run context is ready.")
        self._step_loop(state, adapter, request.max_steps)
        self.store.save(state)
        self._publish_state(state)
        return state

    def _new_state(self, request: AutopilotRunRequest, *, run_id: str | None = None) -> AutopilotRunState:
        resolved_run_id = run_id or uuid.uuid4().hex[:12]
        return AutopilotRunState(
            run_id=resolved_run_id,
            status="running",
            message=request.message,
            project_id=request.project_id,
            session_id=request.session_id,
            adapter_id=request.adapter_id,
            mode=request.mode,
            dry_run=request.dry_run,
            selected_geometry=request.selected_geometry,
            llm_config={str(k): v for k, v in request.llm_config.items() if k != "api_key"},
            plan=self._new_plan(request, run_id=resolved_run_id),
            working_state=AgentWorkingState(objective=request.message, current_mode=request.mode),
        )

    def _new_plan(self, request: AutopilotRunRequest, *, run_id: str) -> AgentPlan:
        return create_default_agent_plan(request.message, plan_id=f"{run_id}-plan")

    def _set_plan_step(
        self,
        state: AutopilotRunState,
        step_id: str,
        status: str,
        *,
        summary: str | None = None,
        evidence: dict[str, Any] | None = None,
        tool_name: str | None = None,
        skill_name: str | None = None,
        current: bool | None = None,
    ) -> None:
        if state.plan is None:
            return
        for step in state.plan.steps:
            if step.id != step_id:
                continue
            previous_status = step.status
            step.status = status  # type: ignore[assignment]
            if summary is not None:
                step.summary = summary
            if evidence is not None:
                step.evidence.update(evidence)
            if tool_name is not None:
                step.tool_name = tool_name
            if skill_name is not None:
                step.skill_name = skill_name
            if current is True or (current is None and status == "running"):
                state.plan.current_step_id = step_id
            state.plan.updated_at = now_iso()
            if state.plan.status not in {"failed", "cancelled"}:
                if status in {"blocked", "failed"}:
                    state.plan.status = status  # type: ignore[assignment]
                elif state.status == "running":
                    state.plan.status = "running"
            if previous_status != step.status:
                self._emit_plan_step_updated(state, step)
            return

    def _plan_step_status(self, state: AutopilotRunState, step_id: str) -> str | None:
        if state.plan is None:
            return None
        for step in state.plan.steps:
            if step.id == step_id:
                return step.status
        return None

    def _current_plan_step_payload(self, state: AutopilotRunState) -> dict[str, Any] | None:
        if state.plan is None or not state.plan.current_step_id:
            return None
        for step in state.plan.steps:
            if step.id == state.plan.current_step_id:
                return step.model_dump()
        return None

    def _finish_plan(self, state: AutopilotRunState, status: str, summary: str) -> None:
        if state.plan is None:
            return
        state.plan.status = status  # type: ignore[assignment]
        step_status = "completed" if status == "completed" else "failed" if status == "failed" else "blocked"
        self._set_plan_step(state, "summarize_result", step_status, summary=summary, current=True)

    def _add_working_evidence(self, state: AutopilotRunState, evidence: dict[str, Any]) -> None:
        compact = {key: value for key, value in evidence.items() if value is not None}
        state.working_state.latest_evidence.append(compact)
        state.working_state.latest_evidence = state.working_state.latest_evidence[-8:]
        state.working_state.updated_at = now_iso()

    def _update_working_state_for_tool_result(
        self,
        state: AutopilotRunState,
        tool_name: str,
        tool_input: dict[str, Any],
        output: dict[str, Any],
        *,
        followup_for: str | None = None,
    ) -> None:
        state.working_state.objective = state.working_state.objective or state.message
        state.working_state.current_mode = state.mode
        state.working_state.last_successful_tool = tool_name
        evidence: dict[str, Any] = {
            "tool_name": tool_name,
            "followup_for": followup_for,
            "summary": output.get("summary") or output.get("brief") or output.get("verdict") or output.get("status"),
        }
        if isinstance(output.get("named_parts"), list):
            evidence["named_parts"] = output.get("named_parts")
        if isinstance(output.get("parts_added"), list):
            evidence["parts_added"] = output.get("parts_added")
        if output.get("skill_name") == "cad.plan_build123d_skill":
            evidence["intent"] = output.get("intent")
            evidence["brief"] = output.get("brief")
            evidence["assumptions"] = output.get("assumptions")
            proposed_tool = output.get("proposed_tool") or output.get("next_tool")
            if proposed_tool:
                state.working_state.recommended_next_action = f"Review skill plan, then call {proposed_tool} if it matches the user intent."
            if output.get("status") in {"unsupported", "needs_clarification", "error"}:
                blocker = output.get("rejection_reason") or output.get("fallback_recommendation") or output.get("brief")
                if blocker:
                    state.working_state.current_blockers = [str(blocker)]
            else:
                state.working_state.current_blockers = []
        elif tool_name == "cad.critique":
            objections = output.get("fail_first_objections") if isinstance(output.get("fail_first_objections"), list) else []
            findings = output.get("findings") if isinstance(output.get("findings"), list) else []
            blockers = [str(item) for item in objections[:5]]
            if not blockers:
                blockers = [
                    str(item.get("observation") or item.get("suggested_fix") or item)
                    for item in findings[:5]
                    if isinstance(item, dict)
                ]
            state.working_state.current_blockers = blockers
            state.working_state.recommended_next_action = "Address CAD critique blockers before finalizing." if blockers else "No critique blockers found."
        else:
            if state.working_state.current_blockers and tool_name != "aieng.agent_context":
                state.working_state.current_blockers = []
            state.working_state.recommended_next_action = f"Use {tool_name} result to decide the next agent action."
        self._add_working_evidence(state, evidence)

    def _record_working_blocker(self, state: AutopilotRunState, blocker: str, *, next_action: str | None = None) -> None:
        if blocker:
            state.working_state.current_blockers = [blocker]
        if next_action:
            state.working_state.recommended_next_action = next_action
        state.working_state.updated_at = now_iso()

    def _accept_working_assumptions(self, state: AutopilotRunState, assumptions: list[str]) -> None:
        if not assumptions:
            return
        seen = set(state.working_state.accepted_assumptions)
        for assumption in assumptions:
            text = str(assumption).strip()
            if text and text not in seen:
                state.working_state.accepted_assumptions.append(text)
                seen.add(text)
        state.working_state.updated_at = now_iso()

    def _registered_tool_names(self) -> set[str]:
        return {str(tool.get("name")) for tool in self.runtime_tools if tool.get("name")}

    def _checkpoint(self, state: AutopilotRunState) -> None:
        state.updated_at = now_iso()
        self.store.save(state)
        # A run that reached a terminal state no longer needs its step counter;
        # dropping it here (the unified write-through path) bounds memory and lets
        # the next run on this chat session start a fresh adapter step sequence.
        # Non-terminal states (running/awaiting_approval/blocked/chatting) keep the
        # counter so a resumed run continues its index correctly.
        if state.status in _TERMINAL_RUN_STATUSES:
            _clear_step_counter(_effective_adapter_session_id(state), state.adapter_id)
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

    def _emit_plan_created(self, state: AutopilotRunState) -> None:
        if state.plan is None:
            return
        self._emit_event(
            state,
            "agent_plan_created",
            status=state.plan.status,
            content=state.plan.objective,
            payload={"plan": state.plan.model_dump()},
            event_id=f"{state.run_id}-plan-{state.plan.id}-created",
        )

    def _emit_plan_step_updated(self, state: AutopilotRunState, step: AgentPlanStep) -> None:
        if state.plan is None:
            return
        event_version = step.updated_at if hasattr(step, "updated_at") else state.plan.updated_at
        event_version = str(event_version).replace(":", "").replace("+", "_")
        self._emit_event(
            state,
            "agent_plan_step_updated",
            status=step.status,
            content=step.summary or step.title,
            payload={"plan_id": state.plan.id, "current_step_id": state.plan.current_step_id, "step": step.model_dump()},
            event_id=f"{state.run_id}-plan-{state.plan.id}-step-{step.id}-{step.status}-{event_version}",
        )

    def _emit_phase_changed(
        self,
        state: AutopilotRunState,
        phase: str,
        message: str,
        *,
        adapter_id: str | None = None,
        plan_step_id: str | None = None,
        elapsed_seconds: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        phase_payload = {
            "phase": phase,
            "adapter_id": adapter_id or state.adapter_id,
            "plan_step_id": plan_step_id or (state.plan.current_step_id if state.plan else None),
            "elapsed_seconds": elapsed_seconds,
            "progress_event": True,
            **(payload or {}),
        }
        self._emit_event(
            state,
            "agent_phase_changed",
            status=state.status,
            content=message,
            payload=phase_payload,
            event_id=f"{state.run_id}-phase-{phase}-{plan_step_id or phase_payload.get('plan_step_id') or 'run'}-{len(state.observations)}",
        )

    def _cancel_if_requested(self, state: AutopilotRunState) -> bool:
        if not self.store.is_cancel_requested(state.run_id):
            return False
        try:
            persisted = self.store.load(state.run_id)
        except Exception:
            persisted = None
        if persisted is not None and persisted.status == "cancelled":
            # A user/API cancellation already emitted and persisted the terminal
            # event. Mirror that state into this in-flight worker so its final
            # save does not resurrect the run, but do not emit run_cancelled a
            # second time.
            state.status = persisted.status
            state.pending_approval = persisted.pending_approval
            state.observations = list(persisted.observations)
            state.plan = persisted.plan
            state.final_message = persisted.final_message
            state.errors = list(persisted.errors)
            state.updated_at = persisted.updated_at
            self.store.clear_cancel(state.run_id)
            return True
        state.status = "cancelled"
        state.pending_approval = None
        state.observations.append(_observation("user_message", "Autopilot run cancelled."))
        self._finish_plan(state, "cancelled", "Autopilot run cancelled.")
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
        self._emit_phase_changed(
            state,
            "context_bootstrap",
            "Loading project context with aieng.agent_context.",
            plan_step_id="observe_context",
        )
        self._checkpoint(state)
        try:
            output = self.tool_executor("aieng.agent_context", {"project_id": state.project_id})
        except Exception as exc:
            state.observations.append(
                _observation(
                    "tool_error",
                    f"Initial aieng.agent_context failed: {exc}",
                    _classified_error_data(
                        _classify_exception("aieng.agent_context", exc),
                        tool_name="aieng.agent_context",
                        tool_input={"project_id": state.project_id},
                        error=str(exc),
                    ),
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
        output_payload = output if isinstance(output, dict) else {"value": output}
        self._update_working_state_for_tool_result(
            state,
            "aieng.agent_context",
            {"project_id": state.project_id},
            output_payload,
        )
        self._checkpoint(state)
        # Sync bootstrapped observations into the memory manager so that
        # the first adapter step already has compacted context.
        self.memory.add_observations([obs.model_dump() for obs in state.observations])

    def _step_loop(self, state: AutopilotRunState, adapter: LocalAgentAdapter, max_steps: int) -> None:
        self._ensure_memory_for_state(state)
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
            self._set_plan_step(
                state,
                "select_skill_or_tool",
                "running",
                summary=f"Invoking {adapter.adapter_id} for the next structured action.",
                evidence={"adapter_id": adapter.adapter_id, "step_index": len(state.steps)},
            )
            self._checkpoint(state)
            self._emit_event(
                state,
                "run_status_changed",
                status=state.status,
                content=f"Invoking {adapter.adapter_id} for the next action.",
                payload={"adapter_id": adapter.adapter_id, "step_index": len(state.steps)},
            )
            # Sync any new observations added since the last step into the
            # memory manager so that compression and budget tracking stay current.
            new_obs = state.observations[self.memory.seen_count :]
            self.memory.add_observations([obs.model_dump() for obs in new_obs])

            # Adapters differ only in transport/invocation mechanics. The
            # autopilot core always emits the same context model so Local Agent
            # and LLM API runs follow identical reasoning state transitions.
            if len(state.steps) > 0:
                prompt = self.memory.build_resume_prompt(
                    objective=state.message,
                    project_id=state.project_id,
                    selected_geometry=state.selected_geometry,
                    agent_context=self.agent_context,
                    working_state=state.working_state.model_dump(),
                    current_plan_step=self._current_plan_step_payload(state),
                    latest_observation=new_obs[-1] if new_obs else None,
                    pending_approval=state.pending_approval.model_dump() if state.pending_approval else None,
                )
                prompt_kind = "resume"
            else:
                prompt = self.memory.build_full_prompt(
                    objective=state.message,
                    project_id=state.project_id,
                    selected_geometry=state.selected_geometry,
                    agent_context=self.agent_context,
                    working_state=state.working_state.model_dump(),
                )
                prompt_kind = "full"

            memory_stats = self.memory.get_memory_stats()
            prompt_tokens = max(1, len(prompt) // 4)
            self._emit_event(
                state,
                "run_status_changed",
                status=state.status,
                content=(
                    f"Prepared {prompt_kind} prompt for {adapter.adapter_id}: "
                    f"{memory_stats['working_count']} working observations, "
                    f"~{prompt_tokens} prompt tokens."
                ),
                payload={
                    "adapter_id": adapter.adapter_id,
                    "phase": "prompt_prepared",
                    "prompt_kind": prompt_kind,
                    "prompt_tokens_estimate": prompt_tokens,
                    "memory": memory_stats,
                },
            )
            self._emit_phase_changed(
                state,
                "prompt_prepared",
                f"Prepared {prompt_kind} prompt for {adapter.adapter_id}.",
                adapter_id=adapter.adapter_id,
                plan_step_id="select_skill_or_tool",
                payload={
                    "prompt_kind": prompt_kind,
                    "prompt_tokens_estimate": prompt_tokens,
                    "memory": memory_stats,
                },
            )

            # Progress reporting during the potentially-long adapter call.
            # A background thread emits honest keep-alive observations because
            # CLI JSON modes do not stream tokens. Adapter callbacks provide the
            # real process milestones; the heartbeat only says that we are still
            # waiting for the local CLI to finish.
            invoke_done = threading.Event()
            invoke_started_at = time.perf_counter()
            last_progress_at = time.perf_counter()

            def _on_adapter_progress(evt: dict[str, Any]) -> None:
                nonlocal last_progress_at
                last_progress_at = time.perf_counter()
                phase = evt.get("phase", "working")
                message = evt.get("message", f"{adapter.adapter_id} {phase}...")
                state.observations.append(
                    _observation(
                        "agent_activity",
                        message,
                        {"adapter_id": adapter.adapter_id, "phase": phase, "progress_event": True},
                    )
                )
                # Emit the event over SSE so the UI updates immediately, but do
                # NOT call _checkpoint here — store.save() is not thread-safe on
                # Windows and the main thread will checkpoint after invoke returns.
                self._emit_event(
                    state,
                    "run_status_changed",
                    status=state.status,
                    content=message,
                    payload={"adapter_id": adapter.adapter_id, "phase": phase, "progress_event": True},
                    event_id=f"{state.run_id}-progress-{len(state.steps)}-{phase}",
                )
                self._emit_phase_changed(
                    state,
                    "waiting_for_model" if phase == "waiting_for_cli" else str(phase),
                    str(message),
                    adapter_id=adapter.adapter_id,
                    plan_step_id="select_skill_or_tool",
                    payload={**evt, "progress_event": True},
                )

            def _heartbeat() -> None:
                """Emit a lightweight keep-alive while a non-streaming CLI runs."""
                while not invoke_done.is_set():
                    invoke_done.wait(timeout=12)
                    if invoke_done.is_set():
                        break
                    quiet_for = time.perf_counter() - last_progress_at
                    if quiet_for < 10:
                        continue
                    elapsed = int(time.perf_counter() - invoke_started_at)
                    _on_adapter_progress({
                        "phase": "waiting_for_model",
                        "message": (
                            f"Waiting for {adapter.adapter_id} model output "
                            f"({elapsed}s elapsed; streaming is unavailable for this adapter call)."
                        ),
                    })

            heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
            heartbeat_thread.start()

            result = adapter.invoke(
                prompt=prompt,
                action_schema=AutopilotAgentAction.json_schema_for_adapter(),
                timeout_seconds=DEFAULT_STEP_TIMEOUT_SECONDS,
                on_progress=_on_adapter_progress,
                session_id=_effective_adapter_session_id(state),
                step_index=_session_step_index(_effective_adapter_session_id(state), state.adapter_id),
            )

            invoke_done.set()
            heartbeat_thread.join(timeout=1)
            if self._cancel_if_requested(state):
                return
            if result.status != "success" or result.action is None:
                state.status = "failed"
                state.errors.append(result.diagnostic or "Local agent adapter failed.")
                self._set_plan_step(state, "select_skill_or_tool", "failed", summary=state.errors[-1])
                self._finish_plan(state, "failed", state.errors[-1])
                adapter_error_class: AutopilotErrorClass = "timeout" if result.status == "timeout" else "tool_runtime_error"
                state.observations.append(
                    _observation(
                        "tool_error",
                        state.errors[-1],
                        _classified_error_data(
                            adapter_error_class,
                            error=state.errors[-1],
                            adapter_id=adapter.adapter_id,
                            adapter_status=result.status,
                            raw=result.model_dump(),
                        ),
                    )
                )
                self._checkpoint(state)
                self._emit_event(state, "tool_failed", status="failed", content=state.errors[-1], payload=result.model_dump())
                return
            action = result.action
            mutation_intent = _latest_geometry_mutation_intent(state)
            if (
                action.action.type == "final"
                and mutation_intent
                and not _has_successful_cad_mutation(state)
            ):
                state.observations.append(
                    _observation(
                        "tool_error",
                        GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
                        _classified_error_data(
                            "missing_context",
                            error=GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
                            adapter_id=adapter.adapter_id,
                            action_type="final",
                            intent=mutation_intent,
                            recoverable=True,
                        ),
                    )
                )
                self._record_working_blocker(
                    state,
                    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
                    next_action="Select cad.execute_build123d/cad.edit_parameter/cad.replace_part/cad.remove_part, or ask the user for clarification.",
                )
                self._set_plan_step(
                    state,
                    "repair_tool_input",
                    "running",
                    summary=GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
                    evidence={"intent": mutation_intent, "rejected_action_type": "final"},
                    current=True,
                )
                self._emit_event(
                    state,
                    "tool_failed",
                    status="running",
                    content=GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
                    payload={
                        "kind": "mutation_intent_guard",
                        "intent": mutation_intent,
                        "adapter_id": adapter.adapter_id,
                    },
                )
                self._checkpoint(state)
                continue
            step = AutopilotStep(index=len(state.steps), adapter_id=state.adapter_id, action=action)
            state.steps.append(step)
            state.updated_at = now_iso()
            self._set_plan_step(
                state,
                "select_skill_or_tool",
                "completed",
                summary=f"{adapter.adapter_id} selected {action.action.type}.",
                evidence={"action_type": action.action.type},
                current=False,
            )
            self._set_plan_step(
                state,
                "prepare_action",
                "completed",
                summary=f"Prepared {action.action.type} action.",
                evidence={"action_type": action.action.type},
                current=True,
            )
            state.observations.append(
                _observation(
                    "agent_activity",
                    f"{adapter.adapter_id} selected {action.action.type}.",
                    {"adapter_id": adapter.adapter_id, "action_type": action.action.type},
                )
            )
            if action.thought_summary:
                state.observations.append(
                    _observation(
                        "agent_thought",
                        action.thought_summary,
                        {"step_index": len(state.steps), "adapter_id": state.adapter_id},
                    )
                )
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
                if self._plan_step_status(state, "execute_tool") == "pending":
                    self._set_plan_step(state, "execute_tool", "skipped", summary="No tool execution was needed for the final answer.", current=False)
                if self._plan_step_status(state, "verify_result") == "pending":
                    self._set_plan_step(state, "verify_result", "skipped", summary="No verification was needed for the final answer.", current=False)
                self._finish_plan(state, "completed", action.action.message)
                self._emit_event(state, "agent_message", status="completed", content=action.action.message, payload={"kind": "final"})
                self._emit_event(state, "run_status_changed", status="completed", content="Autopilot run completed.")
                self._checkpoint(state)
                return
            if action.action.type == "ask_user":
                state.status = "blocked"
                state.observations.append(_observation("ask_user", action.action.question, {"question": action.action.question}))
                self._finish_plan(state, "blocked", action.action.question)
                self._emit_event(
                    state,
                    "ask_user_requested",
                    status="blocked",
                    content=action.action.question,
                    payload={"kind": "ask_user", "question": action.action.question},
                )
                self._checkpoint(state)
                return
            if action.action.type == "chat":
                state.status = "chatting"
                state.observations.append(_observation("user_message", action.action.message))
                self._set_plan_step(state, "summarize_result", "blocked", summary=action.action.message, current=True)
                self._emit_event(state, "agent_message", status="chatting", content=action.action.message, payload={"kind": "chat"})
                self._checkpoint(state)
                return
            if action.action.type == "pause":
                state.status = "blocked"
                state.observations.append(_observation("policy_block", action.action.reason))
                self._finish_plan(state, "blocked", action.action.reason)
                self._checkpoint(state)
                return
            tool_call = action.action
            policy = evaluate_tool_call(
                tool_name=tool_call.tool_name,
                tool_input=tool_call.input,
                active_project_id=state.project_id,
                registered_tools=self.runtime_tools,
                mode=state.mode,
                approval_mode=self.approval_mode,  # type: ignore[arg-type]
            )
            state.steps[-1].policy = policy.model_dump()
            if not policy.allowed:
                self._set_plan_step(
                    state,
                    "prepare_action",
                    "blocked",
                    summary=policy.explanation,
                    evidence={"tool_name": tool_call.tool_name, "level": policy.level},
                    tool_name=tool_call.tool_name,
                )
                state.observations.append(
                    _observation(
                        "policy_block",
                        policy.explanation,
                        _classified_error_data(
                            "policy_error",
                            tool_name=tool_call.tool_name,
                            tool_input=tool_call.input,
                            error=policy.explanation,
                            level=policy.level,
                            recoverable=False,
                        ),
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
                self._set_plan_step(
                    state,
                    "await_approval",
                    "blocked",
                    summary=policy.explanation,
                    evidence={"approval_id": approval.id, "level": policy.level},
                    tool_name=tool_call.tool_name,
                    current=True,
                )
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
            self._set_plan_step(state, "await_approval", "skipped", summary="Policy allowed the tool without approval.", current=False)
            if not self._execute_allowed_tool(state, tool_call.tool_name, tool_call.input, policy.model_dump()):
                return
        state.status = "failed"
        state.errors.append(f"Autopilot exceeded max step count ({max_steps}).")
        self._finish_plan(state, "failed", state.errors[-1])
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
    ) -> dict[str, Any]:
        code = tool_input.get("code")
        project_id = tool_input.get("project_id") or state.project_id
        mutates = tool_name.startswith("cad.") or tool_name.startswith("cae.") or tool_name == "aieng.convert"
        side_effect = "Will update project geometry/artifacts." if mutates else "Will run the selected workbench tool."
        if tool_name == "cae.run_solver":
            side_effect = "Will run the external solver and write result artifacts."
        skill_plan = self._latest_skill_plan_for_tool(state, tool_name)
        payload: dict[str, Any] = {
            "side_effect_summary": side_effect,
            "risk_summary": explanation or f"Policy level: {level}",
            "target_project_id": str(project_id) if project_id else None,
            "code_preview": str(code)[:8000] if isinstance(code, str) else None,
            "artifact_preview": None,
            "recommended_action": "Approve if the target project, code, and side effects match your intent.",
        }
        if skill_plan:
            payload.update(skill_plan)
        return payload

    def _latest_skill_plan_for_tool(self, state: AutopilotRunState, tool_name: str) -> dict[str, Any] | None:
        for obs in reversed(state.observations):
            if obs.kind != "tool_result":
                continue
            output = obs.data.get("output") if isinstance(obs.data, dict) else None
            if not isinstance(output, dict) or output.get("skill_name") != "cad.plan_build123d_skill":
                continue
            proposed_tool = output.get("proposed_tool") or output.get("next_tool")
            if proposed_tool != tool_name:
                continue
            assumptions = output.get("assumptions") if isinstance(output.get("assumptions"), list) else []
            warnings = output.get("warnings") if isinstance(output.get("warnings"), list) else []
            verification_targets = output.get("verification_targets") or output.get("validation_targets")
            if not isinstance(verification_targets, list):
                verification_targets = []
            return {
                "skill_plan_brief": output.get("brief") if isinstance(output.get("brief"), str) else None,
                "skill_plan_assumptions": [str(item) for item in assumptions],
                "skill_plan_warnings": [str(item) for item in warnings],
                "skill_plan_verification_targets": [str(item) for item in verification_targets],
            }
        return None

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
            self._set_plan_step(
                state,
                "execute_tool",
                "completed",
                summary=f"Dry-run accepted tool call: {tool_name}",
                evidence={"dry_run": True, "tool_name": tool_name},
                tool_name=tool_name,
            )
            self._set_plan_step(state, "verify_result", "skipped", summary="Dry-run did not execute artifacts to verify.", current=False)
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
        self._set_plan_step(
            state,
            "execute_tool",
            "running",
            summary=f"Executing workbench tool: {tool_name}",
            evidence={"tool_name": tool_name},
            tool_name=tool_name,
        )
        self._emit_event(
            state,
            "tool_started",
            status="running",
            content=f"Executing workbench tool: {tool_name}",
            payload={"tool_name": tool_name, "input": tool_input, "policy": policy_data},
        )
        self._emit_phase_changed(
            state,
            "tool_execution",
            f"Executing workbench tool: {tool_name}",
            plan_step_id="execute_tool",
            payload={"tool_name": tool_name},
        )
        self._checkpoint(state)
        try:
            output = self.tool_executor(tool_name, tool_input)
        except Exception as exc:
            error_class = _classify_exception(tool_name, exc)
            repair_allowed = self._record_repair_attempt(state, tool_name, error_class, str(exc))
            self._set_plan_step(
                state,
                "execute_tool",
                "failed" if not repair_allowed else "blocked",
                summary=f"Tool {tool_name} failed: {exc}",
                evidence={"tool_name": tool_name, "error": str(exc)},
                tool_name=tool_name,
            )
            state.observations.append(
                _observation(
                    "tool_error",
                    f"Tool {tool_name} failed: {exc}",
                    _classified_error_data(
                        error_class,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        policy=policy_data,
                        error=str(exc),
                    ),
                )
            )
            self._record_working_blocker(
                state,
                f"Tool {tool_name} failed: {exc}",
                next_action="Repair the failed tool input and retry within the bounded repair loop." if repair_allowed else "Stop and report the failed tool execution.",
            )
            self._emit_event(
                state,
                "tool_failed",
                status="failed",
                content=f"Tool {tool_name} failed: {exc}",
                payload={"tool_name": tool_name, "input": tool_input, "policy": policy_data, "error": str(exc)},
            )
            self._checkpoint(state)
            if repair_allowed:
                return True
            state.status = "failed"
            state.errors.append(f"Repair attempts exceeded for {tool_name}: {exc}")
            self._finish_plan(state, "failed", state.errors[-1])
            self._checkpoint(state)
            return False
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
        self._set_plan_step(
            state,
            "execute_tool",
            "completed",
            summary=f"Executed tool call: {tool_name}",
            evidence={"tool_name": tool_name},
            tool_name=tool_name,
        )
        if self._plan_step_status(state, "repair_tool_input") == "running":
            self._set_plan_step(
                state,
                "repair_tool_input",
                "completed",
                summary=f"Recovered by executing corrected input for {tool_name}.",
                evidence={"tool_name": tool_name},
                tool_name=tool_name,
                current=False,
            )
        output_payload = output if isinstance(output, dict) else {"value": output}
        self._update_working_state_for_tool_result(state, tool_name, tool_input, output_payload)
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

    def _record_repair_attempt(
        self,
        state: AutopilotRunState,
        tool_name: str,
        error_class: AutopilotErrorClass,
        error: str,
        *,
        max_attempts: int = 2,
    ) -> bool:
        recoverable = error_class in {"schema_error", "tool_runtime_error", "cad_build_error", "timeout", "missing_context"}
        if not recoverable:
            return False
        key = f"{tool_name}:{error_class}"
        attempt = state.repair_attempts.get(key, 0) + 1
        state.repair_attempts[key] = attempt
        if attempt > max_attempts:
            if self._plan_step_status(state, "repair_tool_input") == "running":
                self._set_plan_step(
                    state,
                    "repair_tool_input",
                    "failed",
                    summary=f"Repair attempts exceeded for {tool_name}.",
                    evidence={"tool_name": tool_name, "error_class": error_class, "error": error, "attempt": attempt, "max_attempts": max_attempts},
                    tool_name=tool_name,
                    current=False,
                )
            return False
        self._set_plan_step(
            state,
            "repair_tool_input",
            "running",
            summary=f"Repair attempt {attempt}/{max_attempts} for {tool_name}.",
            evidence={"tool_name": tool_name, "error_class": error_class, "error": error},
            tool_name=tool_name,
        )
        self._emit_phase_changed(
            state,
            "repair",
            f"Repair attempt {attempt}/{max_attempts} for {tool_name}.",
            plan_step_id="repair_tool_input",
            payload={"tool_name": tool_name, "error_class": error_class, "attempt": attempt, "max_attempts": max_attempts},
        )
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
            self._set_plan_step(state, "verify_result", "skipped", summary="No automatic verification follow-up was registered.", current=False)
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
                        _classified_error_data(
                            "missing_context",
                            tool_name=followup_name,
                            tool_input=followup_input,
                            error="tool is not registered",
                        ),
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
            self._set_plan_step(
                state,
                "verify_result",
                "running",
                summary=f"Executing Autopilot follow-up: {followup_name}",
                evidence={"tool_name": followup_name, "followup_for": tool_name},
                tool_name=followup_name,
            )
            self._emit_event(
                state,
                "tool_started",
                status="running",
                content=f"Executing Autopilot follow-up: {followup_name}",
                payload={"tool_name": followup_name, "input": followup_input, "followup_for": tool_name},
            )
            self._emit_phase_changed(
                state,
                "verification",
                f"Executing Autopilot follow-up: {followup_name}",
                plan_step_id="verify_result",
                payload={"tool_name": followup_name, "followup_for": tool_name},
            )
            self._checkpoint(state)
            try:
                output = self.tool_executor(followup_name, followup_input)
            except Exception as exc:
                error_class = _classify_exception(followup_name, exc)
                self._set_plan_step(
                    state,
                    "verify_result",
                    "failed",
                    summary=f"Autopilot follow-up {followup_name} failed: {exc}",
                    evidence={"tool_name": followup_name, "error": str(exc)},
                    tool_name=followup_name,
                )
                state.observations.append(
                    _observation(
                        "tool_error",
                        f"Autopilot follow-up {followup_name} failed: {exc}",
                        _classified_error_data(
                            error_class,
                            tool_name=followup_name,
                            tool_input=followup_input,
                            error=str(exc),
                            followup_for=tool_name,
                        ),
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
            self._update_working_state_for_tool_result(
                state,
                followup_name,
                followup_input,
                output_payload,
                followup_for=tool_name,
            )
            self._emit_event(
                state,
                "tool_completed",
                status="done",
                content=f"Executed Autopilot follow-up: {followup_name}",
                payload={"tool_name": followup_name, "input": followup_input, "followup_for": tool_name, **output_payload},
            )
            self._set_plan_step(
                state,
                "verify_result",
                "completed",
                summary=f"Executed Autopilot follow-up: {followup_name}",
                evidence={"tool_name": followup_name, "followup_for": tool_name},
                tool_name=followup_name,
            )
            self._checkpoint(state)

    def continue_run(
        self,
        run_id: str,
        *,
        approved: bool,
        max_steps: int = 30,
        user_message: str | None = None,
    ) -> AutopilotRunState:
        state = self.store.load(run_id)
        if user_message and state.status != "awaiting_approval":
            return self.reply_to_run(run_id, user_message, max_steps=max_steps)
        if user_message and state.status == "awaiting_approval":
            state.observations.append(_observation("user_message", f"Revision request: {user_message}", {"revision_request": True}))
            self._record_working_blocker(
                state,
                f"User requested revision: {user_message}",
                next_action="Revise the pending tool input according to the user request.",
            )
            state.pending_approval = None
            state.status = "running"
            self._set_plan_step(state, "await_approval", "blocked", summary="User requested a revision instead of approving.", current=True)
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
            self._record_working_blocker(
                state,
                state.errors[-1],
                next_action="Ask for clarification or propose a safer revised action.",
            )
            self._set_plan_step(state, "await_approval", "blocked", summary=state.errors[-1], tool_name=approval.tool_name, current=True)
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
        self._add_working_evidence(
            state,
            {"event": "approval_accepted", "tool_name": approval.tool_name, "approval_id": approval.id},
        )
        self._accept_working_assumptions(state, approval.skill_plan_assumptions)
        state.working_state.current_blockers = []
        state.working_state.recommended_next_action = f"Execute approved tool {approval.tool_name}."
        self._set_plan_step(
            state,
            "await_approval",
            "completed",
            summary=f"User approved {approval.tool_name}.",
            evidence={"approval_id": approval.id},
            tool_name=approval.tool_name,
            current=False,
        )
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
            self._finish_plan(state, "failed", state.errors[-1])
        else:
            self._step_loop(state, adapter, max_steps)
        state.updated_at = now_iso()
        self.store.save(state)
        self._publish_state(state)
        return state

    def reply_to_run(self, run_id: str, message: str, *, max_steps: int = 30) -> AutopilotRunState:
        state = self.store.load(run_id)
        if state.status in {"completed", "failed", "cancelled"}:
            return state
        if state.status == "awaiting_approval":
            state.pending_approval = None
            state.observations.append(_observation("user_message", f"Revision request: {message}", {"revision_request": True}))
            self._record_working_blocker(
                state,
                f"User requested revision: {message}",
                next_action="Revise the pending action according to the user request.",
            )
            self._emit_event(
                state,
                "approval_resolved",
                status="running",
                content="User asked the agent to revise the pending action.",
                payload={"approved": False, "revision_request": message},
            )
        else:
            state.observations.append(_observation("user_message", message, {"reply": True}))
            state.working_state.recommended_next_action = f"Address user follow-up: {message[:240]}"
            state.working_state.updated_at = now_iso()
        state.status = "running"
        self._emit_event(state, "agent_message", status="running", content=message, payload={"role": "user", "kind": "reply"})
        self._checkpoint(state)
        adapter = self.adapters.get(state.adapter_id)
        if adapter is None:
            state.status = "failed"
            state.errors.append(f"Unknown local agent adapter: {state.adapter_id}")
            self._finish_plan(state, "failed", state.errors[-1])
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
            state.working_state.recommended_next_action = f"Address queued user follow-up: {message[:240]}"
            state.working_state.updated_at = now_iso()
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
        if state.status in {"completed", "failed", "cancelled"}:
            self.store.clear_cancel(run_id)
            return state
        self.store.request_cancel(run_id)
        state.status = "cancelled"
        state.pending_approval = None
        state.updated_at = now_iso()
        state.observations.append(_observation("user_message", "Autopilot run cancelled."))
        self._finish_plan(state, "cancelled", "Autopilot run cancelled.")
        self._emit_event(state, "run_cancelled", status="cancelled", content="Autopilot run cancelled.")
        # Route through _checkpoint so the terminal (cancelled) step counter is cleared.
        self._checkpoint(state)
        return state
