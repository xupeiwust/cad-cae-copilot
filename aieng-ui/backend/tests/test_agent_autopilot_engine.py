from pathlib import Path

from app.agent_autopilot.engine import (
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    AutopilotEngine,
    create_default_agent_plan,
)
from app.agent_autopilot.schema import AdapterInvocationResult, AutopilotAgentAction, AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
    {"name": "cad.plan_build123d_skill", "description": "skill", "input_schema": {"type": "object"}},
    {"name": "cad.execute_build123d", "description": "cad", "input_schema": {"type": "object"}},
    {"name": "cae.apply_setup_patch", "description": "setup", "input_schema": {"type": "object"}},
    {"name": "cae.prepare_solver_run", "description": "preflight", "input_schema": {"type": "object"}},
    {"name": "cae.run_solver", "description": "solver", "input_schema": {"type": "object"}},
    {"name": "cae.extract_solver_results", "description": "metrics", "input_schema": {"type": "object"}},
    {"name": "cae.extract_field_regions", "description": "regions", "input_schema": {"type": "object"}},
    {"name": "postprocess.refresh_cae_summary", "description": "summary", "input_schema": {"type": "object"}},
]


def _engine(tmp_path: Path) -> AutopilotEngine:
    return AutopilotEngine(store=AutopilotStore(tmp_path / "runs"), runtime_tools=RUNTIME_TOOLS)


def test_engine_completes_on_final_action(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="hello",
            fake_actions=[
                {"action": {"type": "final", "message": "All set."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert state.final_message == "All set."
    assert state.plan is not None
    assert state.plan.objective == "hello"
    assert state.plan.status == "completed"
    assert state.plan.steps[0].status == "completed"
    assert state.plan.steps[-1].status == "completed"


def test_mutation_intent_guard_rejects_chinese_create_final_and_reselects_tool(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="创建一个无人机模型",
            project_id="p1",
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "Done without CAD."}, "done": True},
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    }
                },
            ],
        )
    )

    assert state.status == "awaiting_approval"
    assert state.pending_approval is not None
    assert state.pending_approval.tool_name == "cad.execute_build123d"
    assert [step.action.action.type for step in state.steps] == ["tool_call"]
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs
    assert guard_obs[-1].data["intent"] == "create_geometry"


def test_mutation_intent_guard_rejects_english_modify_final_and_allows_ask_user(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="Make it look more futuristic",
            project_id="p1",
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "Already done."}, "done": True},
                {"action": {"type": "ask_user", "question": "Which part should I change?"}},
            ],
        )
    )

    assert state.status == "blocked"
    assert [step.action.action.type for step in state.steps] == ["ask_user"]
    ask_obs = next(obs for obs in state.observations if obs.kind == "ask_user")
    assert ask_obs.data["question"] == "Which part should I change?"
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs[-1].data["intent"] == "modify_geometry"


def test_mutation_intent_guard_does_not_count_critique_as_mutation(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []
    runtime_tools = RUNTIME_TOOLS + [
        {"name": "cad.critique", "description": "critique", "input_schema": {"type": "object"}},
    ]
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=runtime_tools,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"status": "ok"},
    )

    state = engine.start(
        AutopilotRunRequest(
            message="add rotor guards to the drone",
            project_id="p1",
            dry_run=False,
            max_steps=3,
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "cad.critique", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "Critique only."}, "done": True},
                {"action": {"type": "ask_user", "question": "Should I proceed with a CAD edit?"}},
            ],
        )
    )

    assert state.status == "blocked"
    assert calls == [("cad.critique", {"project_id": "p1"})]
    assert [step.action.action.type for step in state.steps] == ["tool_call", "ask_user"]
    assert any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)
    assert state.final_message is None


def test_mutation_intent_guard_allows_readonly_explanation_final(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="解释当前模型有什么部件",
            project_id="p1",
            fake_actions=[
                {"action": {"type": "final", "message": "当前模型包含机身和支架。"}, "done": True},
            ],
        )
    )

    assert state.status == "completed"
    assert state.final_message == "当前模型包含机身和支架。"
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)


def test_mutation_intent_guard_allows_final_after_cad_mutation(tmp_path: Path) -> None:
    class CadThenFinalAdapter:
        adapter_id = "cad-final"
        label = "CAD then Final"

        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            action = (
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    },
                }
                if self.calls == 1
                else {"action": {"type": "final", "message": "Geometry updated."}, "done": True}
            )
            return AdapterInvocationResult(status="success", action=AutopilotAgentAction.model_validate(action))

    calls: list[tuple[str, dict]] = []
    adapter = CadThenFinalAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"cad-final": adapter},
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"named_parts": ["body"], "parts_added": ["body"]},
    )

    state = engine.start(
        AutopilotRunRequest(
            message="add a camera pod",
            project_id="p1",
            adapter_id="cad-final",
            dry_run=False,
        )
    )
    assert state.status == "awaiting_approval"

    resumed = engine.continue_run(state.run_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.final_message == "Geometry updated."
    assert calls == [
        ("aieng.agent_context", {"project_id": "p1"}),
        ("cad.execute_build123d", {"project_id": "p1", "code": "result = None"}),
    ]
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in resumed.observations)


def test_simulation_objective_uses_cae_plan_template() -> None:
    plan = create_default_agent_plan("Run the structural simulation and show stress results")
    titles_by_id = {step.id: step.title for step in plan.steps}

    assert list(titles_by_id) == [
        "observe_context",
        "select_skill_or_tool",
        "prepare_action",
        "await_approval",
        "execute_tool",
        "repair_tool_input",
        "verify_result",
        "summarize_result",
    ]
    assert titles_by_id["observe_context"] == "Inspect CAD/CAE context"
    assert titles_by_id["prepare_action"] == "Prepare CAE setup, preflight, or solver deck action"
    assert titles_by_id["await_approval"] == "Request approval before solver execution"
    assert titles_by_id["verify_result"] == "Preflight readiness or parse solver results"


def test_engine_blocks_then_recovers_when_agent_selects_legal_action(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="context please",
            project_id="p1",
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "unknown.tool", "input": {"project_id": "p1"}}},
                {"action": {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "Observed."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    policy_obs = next(obs for obs in state.observations if obs.kind == "policy_block")
    assert policy_obs.data["error_class"] == "policy_error"
    assert any(obs.kind == "tool_result" for obs in state.observations)


def test_engine_pauses_for_approval_required_action(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="make cad",
            project_id="p1",
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    }
                },
            ],
        )
    )
    assert state.status == "awaiting_approval"
    assert state.pending_approval is not None
    assert state.pending_approval.tool_name == "cad.execute_build123d"
    assert state.plan is not None
    approval_step = next(step for step in state.plan.steps if step.id == "await_approval")
    assert approval_step.status == "blocked"
    assert approval_step.tool_name == "cad.execute_build123d"
    assert state.plan.current_step_id == "await_approval"


def test_engine_approval_mode_controls_low_risk_tool_execution(tmp_path: Path) -> None:
    executed: list[str] = []

    strict_engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "strict-runs"),
        runtime_tools=RUNTIME_TOOLS,
        approval_mode="strict",
        tool_executor=lambda tool_name, _tool_input: executed.append(tool_name) or {"ok": True},
    )
    strict_state = strict_engine.start(
        AutopilotRunRequest(
            message="patch setup",
            project_id="p1",
            fake_actions=[{
                "action": {
                    "type": "tool_call",
                    "tool_name": "cae.apply_setup_patch",
                    "input": {"project_id": "p1", "patch": []},
                },
            }],
        )
    )
    assert strict_state.status == "awaiting_approval"
    assert strict_state.pending_approval is not None
    assert strict_state.pending_approval.tool_name == "cae.apply_setup_patch"
    assert executed == []

    manual_engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "manual-runs"),
        runtime_tools=RUNTIME_TOOLS,
        approval_mode="manual",
        tool_executor=lambda tool_name, _tool_input: executed.append(tool_name) or {"ok": True},
    )
    manual_state = manual_engine.start(
        AutopilotRunRequest(
            message="read context",
            project_id="p1",
            fake_actions=[{
                "action": {
                    "type": "tool_call",
                    "tool_name": "aieng.agent_context",
                    "input": {"project_id": "p1"},
                },
            }],
        )
    )
    assert manual_state.status == "awaiting_approval"
    assert manual_state.pending_approval is not None
    assert manual_state.pending_approval.tool_name == "aieng.agent_context"
    assert executed == []


def test_engine_emits_distinct_ask_user_event(tmp_path: Path) -> None:
    events = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        on_event=events.append,
    )

    state = engine.start(
        AutopilotRunRequest(
            message="make cad",
            fake_actions=[
                {"action": {"type": "ask_user", "question": "Which material should I use?"}},
            ],
        )
    )

    assert state.status == "blocked"
    ask_obs = next(obs for obs in state.observations if obs.kind == "ask_user")
    assert ask_obs.data["question"] == "Which material should I use?"
    ask_events = [event for event in events if event["type"] == "ask_user_requested"]
    assert ask_events
    assert ask_events[0]["content"] == "Which material should I use?"
    assert ask_events[0]["payload"]["kind"] == "ask_user"


def test_engine_emits_plan_lifecycle_events(tmp_path: Path) -> None:
    events = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        on_event=events.append,
    )

    state = engine.start(
        AutopilotRunRequest(
            message="make cad",
            project_id="p1",
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    }
                },
            ],
        )
    )

    assert state.status == "awaiting_approval"
    created = next(event for event in events if event["type"] == "agent_plan_created")
    assert created["event_id"] == f"{state.run_id}-plan-{state.plan.id}-created"  # type: ignore[union-attr]
    assert created["payload"]["plan"]["objective"] == "make cad"
    updates = [event for event in events if event["type"] == "agent_plan_step_updated"]
    assert any(event["payload"]["step"]["id"] == "observe_context" for event in updates)
    approval = next(event for event in updates if event["payload"]["step"]["id"] == "await_approval")
    assert approval["status"] == "blocked"
    assert "cad.execute_build123d" in approval["payload"]["step"]["tool_name"]


def test_engine_emits_typed_phase_events(tmp_path: Path) -> None:
    events = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        on_event=events.append,
    )

    state = engine.start(
        AutopilotRunRequest(
            message="hello",
            fake_actions=[
                {"action": {"type": "final", "message": "All set."}, "done": True},
            ],
        )
    )

    assert state.status == "completed"
    phases = [event for event in events if event["type"] == "agent_phase_changed"]
    assert phases
    assert any(event["payload"]["phase"] == "prompt_prepared" for event in phases)
    assert all(event["payload"].get("adapter_id") for event in phases)


def test_engine_executes_auto_allowed_tool_when_not_dry_run(tmp_path: Path) -> None:
    calls = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"ok": True},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="context please",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "Observed."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert calls == [("aieng.agent_context", {"project_id": "p1"})]
    assert any(obs.data.get("dry_run") is False for obs in state.observations)


def test_engine_classifies_tool_runtime_errors(tmp_path: Path) -> None:
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda _name, _inp: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    state = engine.start(
        AutopilotRunRequest(
            message="context please",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "Observed."}, "done": True},
            ],
        )
    )

    tool_errors = [obs for obs in state.observations if obs.kind == "tool_error"]
    assert tool_errors
    assert tool_errors[-1].data["error_class"] == "tool_runtime_error"
    assert tool_errors[-1].data["recoverable"] is True


def test_engine_repairs_recoverable_tool_input_once(tmp_path: Path) -> None:
    class RepairAdapter:
        adapter_id = "repair"
        label = "Repair"

        def __init__(self) -> None:
            self.calls = 0
            self.prompts: list[str] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            self.prompts.append(prompt)
            action = (
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "aieng.agent_context",
                        "input": {"project_id": "p1", "bad": True},
                    }
                }
                if self.calls == 1
                else (
                    {
                        "action": {
                            "type": "tool_call",
                            "tool_name": "aieng.agent_context",
                            "input": {"project_id": "p1"},
                        }
                    }
                    if self.calls == 2
                    else {"action": {"type": "final", "message": "Recovered."}, "done": True}
                )
            )
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(action),
            )

    calls = []
    events = []
    adapter = RepairAdapter()

    def _execute(name: str, inp: dict) -> dict:
        calls.append((name, inp))
        if inp.get("bad"):
            raise RuntimeError("bad field should be removed")
        return {"ok": True}

    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"repair": adapter},
        tool_executor=_execute,
        on_event=events.append,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="load context",
            project_id="p1",
            adapter_id="repair",
            dry_run=False,
            max_steps=5,
        )
    )

    assert state.status == "completed"
    assert state.final_message == "Recovered."
    assert calls == [
        ("aieng.agent_context", {"project_id": "p1"}),
        ("aieng.agent_context", {"project_id": "p1", "bad": True}),
        ("aieng.agent_context", {"project_id": "p1"}),
    ]
    assert state.repair_attempts == {"aieng.agent_context:tool_runtime_error": 1}
    assert "tool_error" in adapter.prompts[1]
    assert "bad field should be removed" in adapter.prompts[1]
    repair_step = next(step for step in state.plan.steps if step.id == "repair_tool_input")  # type: ignore[union-attr]
    assert repair_step.status == "completed"
    assert any(event["payload"].get("phase") == "repair" for event in events if event["type"] == "agent_phase_changed")


def test_engine_fails_after_repair_attempts_are_exceeded(tmp_path: Path) -> None:
    class FailingAdapter:
        adapter_id = "repair"
        label = "Repair"

        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(
                    {
                        "action": {
                            "type": "tool_call",
                            "tool_name": "aieng.agent_context",
                            "input": {"project_id": "p1", "bad": self.calls},
                        }
                    }
                ),
            )

    calls = []

    def _execute(name: str, inp: dict) -> dict:
        calls.append((name, inp))
        raise RuntimeError("still broken")

    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"repair": FailingAdapter()},
        tool_executor=_execute,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="load context",
            project_id="p1",
            adapter_id="repair",
            dry_run=False,
            max_steps=5,
        )
    )

    assert state.status == "failed"
    assert len(calls) == 4
    assert calls[0] == ("aieng.agent_context", {"project_id": "p1"})
    assert state.repair_attempts == {"aieng.agent_context:tool_runtime_error": 3}
    assert state.errors == ["Repair attempts exceeded for aieng.agent_context: still broken"]
    repair_step = next(step for step in state.plan.steps if step.id == "repair_tool_input")  # type: ignore[union-attr]
    assert repair_step.status == "failed"


def test_engine_allows_agent_to_orchestrate_cad_skill_before_approval(tmp_path: Path) -> None:
    calls = []
    skill_output = {
        "status": "ready",
        "skill_name": "cad.plan_build123d_skill",
        "brief": "Mechanical flange: OD 40mm.",
        "assumptions": ["Defaulted thickness to 6mm."],
        "warnings": [],
        "proposed_tool": "cad.execute_build123d",
        "verification_targets": ["base_plate named part exists"],
        "execute_input": {
            "project_id": "p1",
            "code": "result = None",
            "mode": "replace",
            "model_kind": "mechanical",
        },
    }

    def _execute(name: str, inp: dict) -> dict:
        calls.append((name, inp))
        return skill_output

    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=_execute,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="建模一个40mm的法兰盘",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个40mm的法兰盘"},
                    }
                },
                {
                    "user_message": "CAD skill prepared a 40mm flange; approval is needed to write geometry.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    },
                },
            ],
        )
    )

    assert state.status == "awaiting_approval"
    assert calls == [
        ("cad.plan_build123d_skill", {"project_id": "p1", "message": "建模一个40mm的法兰盘"})
    ]
    assert state.pending_approval is not None
    assert state.pending_approval.tool_name == "cad.execute_build123d"
    assert state.pending_approval.skill_plan_brief == "Mechanical flange: OD 40mm."
    assert state.pending_approval.skill_plan_assumptions == ["Defaulted thickness to 6mm."]
    assert state.pending_approval.skill_plan_verification_targets == ["base_plate named part exists"]


def test_engine_updates_working_state_from_skill_plan(tmp_path: Path) -> None:
    skill_output = {
        "status": "ready",
        "skill_name": "cad.plan_build123d_skill",
        "intent": "make a flange",
        "brief": "Mechanical flange: OD 40mm.",
        "assumptions": ["Defaulted thickness to 6mm."],
        "proposed_tool": "cad.execute_build123d",
        "proposed_input": {"project_id": "p1", "code": "result = None"},
    }

    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda _name, _inp: skill_output,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="建模一个40mm的法兰盘",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个40mm的法兰盘"},
                    }
                },
                {"action": {"type": "ask_user", "question": "Proceed to CAD execution?"}},
            ],
        )
    )

    assert state.status == "blocked"
    assert state.working_state.objective == "建模一个40mm的法兰盘"
    assert state.working_state.current_mode == "autopilot"
    assert state.working_state.last_successful_tool == "cad.plan_build123d_skill"
    assert state.working_state.recommended_next_action == "Review skill plan, then call cad.execute_build123d if it matches the user intent."
    assert state.working_state.latest_evidence[-1]["brief"] == "Mechanical flange: OD 40mm."


def test_engine_persists_approved_skill_assumptions_in_next_prompt(tmp_path: Path) -> None:
    class SkillThenCadAdapter:
        adapter_id = "skill-cad"
        label = "Skill CAD"

        def __init__(self) -> None:
            self.calls = 0
            self.prompts: list[str] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            self.prompts.append(prompt)
            if self.calls == 1:
                action = {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个40mm的法兰盘"},
                    }
                }
            elif self.calls == 2:
                action = {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    },
                    "user_message": "Approval required for CAD write.",
                }
            else:
                action = {"action": {"type": "final", "message": "Built."}, "done": True}
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(action),
            )

    skill_output = {
        "status": "ready",
        "skill_name": "cad.plan_build123d_skill",
        "brief": "Mechanical flange: OD 40mm.",
        "assumptions": ["Defaulted thickness to 6mm."],
        "proposed_tool": "cad.execute_build123d",
        "proposed_input": {"project_id": "p1", "code": "result = None"},
    }

    def _execute(name: str, inp: dict) -> dict:
        if name == "cad.plan_build123d_skill":
            return skill_output
        return {"named_parts": ["base_plate"], "parts_added": ["base_plate"]}

    adapter = SkillThenCadAdapter()
    store = AutopilotStore(tmp_path / "runs")
    engine = AutopilotEngine(
        store=store,
        runtime_tools=RUNTIME_TOOLS,
        adapters={"skill-cad": adapter},
        tool_executor=_execute,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="建模一个40mm的法兰盘",
            project_id="p1",
            adapter_id="skill-cad",
            dry_run=False,
        )
    )

    assert state.status == "awaiting_approval"
    resumed = engine.continue_run(state.run_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.working_state.accepted_assumptions == ["Defaulted thickness to 6mm."]
    assert len(adapter.prompts) == 3
    assert '"resume_summary"' in adapter.prompts[2]
    assert '"working_memory"' in adapter.prompts[2]
    assert '"accepted_assumptions":["Defaulted thickness to 6mm."]' in adapter.prompts[2]


def test_engine_does_not_accept_assumptions_when_approval_rejected(tmp_path: Path) -> None:
    skill_output = {
        "status": "ready",
        "skill_name": "cad.plan_build123d_skill",
        "brief": "Mechanical flange: OD 40mm.",
        "assumptions": ["Defaulted thickness to 6mm."],
        "proposed_tool": "cad.execute_build123d",
        "proposed_input": {"project_id": "p1", "code": "result = None"},
    }

    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda _name, _inp: skill_output,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="建模一个40mm的法兰盘",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个40mm的法兰盘"},
                    }
                },
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    },
                },
            ],
        )
    )
    rejected = engine.continue_run(state.run_id, approved=False)

    assert rejected.status == "blocked"
    assert rejected.working_state.accepted_assumptions == []
    assert rejected.working_state.current_blockers == ["User rejected approval for cad.execute_build123d."]


def test_end_to_end_smoke_40mm_flange_skill_approval_execute_critique(tmp_path: Path) -> None:
    class FlangeAdapter:
        adapter_id = "flange"
        label = "Flange"

        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                action = {
                    "thought_summary": "Need deterministic CAD skill planning before CAD write.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个40mm的法兰盘"},
                    },
                }
            elif self.calls == 2:
                action = {
                    "thought_summary": "Skill produced a flange plan; request approval for geometry write.",
                    "user_message": "CAD skill planned a 40mm flange with default 6mm thickness; approval required to write geometry.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "mode": "replace", "model_kind": "mechanical", "code": "result = None"},
                    },
                }
            else:
                action = {
                    "thought_summary": "CAD executed and critique follow-up returned clean.",
                    "action": {"type": "final", "message": "40mm flange built and checked."},
                    "done": True,
                }
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(action),
            )

    calls: list[tuple[str, dict]] = []

    def _execute(name: str, inp: dict) -> dict:
        calls.append((name, inp))
        if name == "aieng.agent_context":
            return {"schema_version": "0.1", "project_id": "p1", "project": {"name": "Smoke"}}
        if name == "cad.plan_build123d_skill":
            return {
                "status": "ready",
                "skill_name": "cad.plan_build123d_skill",
                "intent": "建模一个40mm的法兰盘",
                "brief": "40mm flange with four M6 holes.",
                "assumptions": ["Defaulted thickness to 6mm."],
                "proposed_tool": "cad.execute_build123d",
                "proposed_input": {"project_id": "p1", "mode": "replace", "model_kind": "mechanical", "code": "result = None"},
                "verification_targets": ["base_plate named part exists", "mounting_hole_pattern exists"],
            }
        if name == "cad.execute_build123d":
            return {
                "named_parts": ["base_plate", "mounting_hole_pattern"],
                "parts_added": ["base_plate", "mounting_hole_pattern"],
                "mode": "replace",
                "used_base": False,
                "geometry_report": {"overall_proportions": {"x": 1.0, "y": 1.0, "z": 0.15}},
            }
        if name == "cad.critique":
            return {"status": "ok", "verdict": "pass", "findings": [], "fail_first_objections": []}
        raise AssertionError(f"unexpected tool {name}")

    runtime_tools = RUNTIME_TOOLS + [
        {"name": "cad.critique", "description": "critique", "input_schema": {"type": "object"}},
    ]
    adapter = FlangeAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=runtime_tools,
        adapters={"flange": adapter},
        tool_executor=_execute,
    )

    state = engine.start(
        AutopilotRunRequest(
            message="建模一个40mm的法兰盘",
            project_id="p1",
            adapter_id="flange",
            dry_run=False,
        )
    )

    assert state.status == "awaiting_approval"
    assert state.pending_approval is not None
    assert state.pending_approval.skill_plan_brief == "40mm flange with four M6 holes."
    resumed = engine.continue_run(state.run_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.final_message == "40mm flange built and checked."
    assert [name for name, _inp in calls] == [
        "aieng.agent_context",
        "cad.plan_build123d_skill",
        "cad.execute_build123d",
        "cad.critique",
    ]
    assert resumed.working_state.accepted_assumptions == ["Defaulted thickness to 6mm."]
    assert resumed.working_state.last_successful_tool == "cad.critique"
    assert any(obs.kind == "tool_result" and obs.data.get("tool_name") == "cad.critique" for obs in resumed.observations)


def test_end_to_end_smoke_unsupported_cad_skill_falls_back_to_authored_build(tmp_path: Path) -> None:
    class UnsupportedAdapter:
        adapter_id = "unsupported"
        label = "Unsupported"

        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                action = {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个复杂机器人外壳"},
                    }
                }
            elif self.calls == 2:
                action = {
                    "thought_summary": "No deterministic skill matched; inspect source before authoring fallback CAD.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.get_source",
                        "input": {"project_id": "p1"},
                    },
                }
            elif self.calls == 3:
                action = {
                    "thought_summary": "Fallback path will author build123d directly and still requires approval.",
                    "user_message": "No deterministic CAD skill matched this robot shell, so I will use a direct build123d fallback; approval is still required before writing geometry.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "mode": "replace", "model_kind": "organic", "code": "result = None"},
                    },
                }
            else:
                action = {"action": {"type": "final", "message": "Fallback CAD path completed."}, "done": True}
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(action),
            )

    calls: list[tuple[str, dict]] = []

    def _execute(name: str, inp: dict) -> dict:
        calls.append((name, inp))
        if name == "aieng.agent_context":
            return {"schema_version": "0.1", "project_id": "p1", "project": {"name": "Robot"}}
        if name == "cad.plan_build123d_skill":
            return {
                "status": "unsupported",
                "skill_name": "cad.plan_build123d_skill",
                "intent": "建模一个复杂机器人外壳",
                "brief": "No deterministic template matched.",
                "match_confidence": 0.12,
                "matched_terms": [],
                "rejection_reason": "complex_robot_shell_not_supported",
                "fallback_recommendation": "Use direct build123d industrial-design fallback with user approval.",
            }
        if name == "cad.get_source":
            return {"named_parts": [], "has_base": False, "source": ""}
        if name == "cad.execute_build123d":
            return {"named_parts": ["robot_shell"], "parts_added": ["robot_shell"], "mode": "replace", "used_base": False}
        raise AssertionError(f"unexpected tool {name}")

    runtime_tools = RUNTIME_TOOLS + [
        {"name": "cad.get_source", "description": "source", "input_schema": {"type": "object"}},
    ]
    adapter = UnsupportedAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=runtime_tools,
        adapters={"unsupported": adapter},
        tool_executor=_execute,
    )

    state = engine.start(
        AutopilotRunRequest(
            message="建模一个复杂机器人外壳",
            project_id="p1",
            adapter_id="unsupported",
            dry_run=False,
            max_steps=5,
        )
    )

    assert state.status == "awaiting_approval"
    assert [name for name, _inp in calls] == [
        "aieng.agent_context",
        "cad.plan_build123d_skill",
        "cad.get_source",
    ]
    skill_obs = next(obs for obs in state.observations if obs.kind == "tool_result" and obs.data.get("tool_name") == "cad.plan_build123d_skill")
    assert skill_obs.data["output"]["status"] == "unsupported"
    assert "direct build123d" in skill_obs.data["output"]["fallback_recommendation"]
    assert state.pending_approval is not None
    assert state.pending_approval.tool_name == "cad.execute_build123d"

    resumed = engine.continue_run(state.run_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.final_message == "Fallback CAD path completed."
    assert [name for name, _inp in calls] == [
        "aieng.agent_context",
        "cad.plan_build123d_skill",
        "cad.get_source",
        "cad.execute_build123d",
    ]


def test_engine_includes_working_state_in_adapter_prompt(tmp_path: Path) -> None:
    class CapturingAdapter:
        adapter_id = "spy"
        label = "Spy"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.prompts.append(prompt)
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(
                    {"action": {"type": "final", "message": "Done."}, "done": True}
                ),
            )

    adapter = CapturingAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"spy": adapter},
        tool_executor=lambda _name, _inp: {"ok": True},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="Explain current blockers",
            project_id="p1",
            adapter_id="spy",
            dry_run=False,
        )
    )

    assert state.status == "completed"
    assert adapter.prompts
    assert '"working_state"' in adapter.prompts[0]
    assert '"objective":"Explain current blockers"' in adapter.prompts[0]


def test_local_and_llm_adapters_follow_equivalent_skill_policy_path(tmp_path: Path) -> None:
    class ScriptedAdapter:
        def __init__(self, adapter_id: str) -> None:
            self.adapter_id = adapter_id
            self.label = adapter_id
            self.calls = 0
            self.prompts: list[str] = []
            self.supports_session_continuation = adapter_id == "local-fake"

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            self.prompts.append(prompt)
            action = (
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.plan_build123d_skill",
                        "input": {"project_id": "p1", "message": "建模一个40mm的法兰盘"},
                    }
                }
                if self.calls == 1
                else {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    },
                    "user_message": "CAD skill prepared geometry; approval is needed.",
                }
            )
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(action),
            )

    def run(adapter_id: str):
        calls: list[tuple[str, dict]] = []
        adapter = ScriptedAdapter(adapter_id)
        engine = AutopilotEngine(
            store=AutopilotStore(tmp_path / adapter_id / "runs"),
            runtime_tools=RUNTIME_TOOLS,
            adapters={adapter_id: adapter},
            tool_executor=lambda name, inp: calls.append((name, inp)) or {
                "status": "ready",
                "skill_name": "cad.plan_build123d_skill",
                "proposed_tool": "cad.execute_build123d",
                "proposed_input": {"project_id": "p1", "code": "result = None"},
            },
        )
        state = engine.start(
            AutopilotRunRequest(
                message="建模一个40mm的法兰盘",
                project_id="p1",
                adapter_id=adapter_id,
                dry_run=False,
            )
        )
        return state, calls, adapter

    local_state, local_calls, local_adapter = run("local-fake")
    llm_state, llm_calls, llm_adapter = run("llm-api")

    assert local_state.status == llm_state.status == "awaiting_approval"
    assert local_calls == llm_calls == [
        ("aieng.agent_context", {"project_id": "p1"}),
        ("cad.plan_build123d_skill", {"project_id": "p1", "message": "建模一个40mm的法兰盘"})
    ]
    assert [step.action.action.type for step in local_state.steps] == [step.action.action.type for step in llm_state.steps]
    assert [step.policy for step in local_state.steps] == [step.policy for step in llm_state.steps]
    assert [obs.kind for obs in local_state.observations] == [obs.kind for obs in llm_state.observations]
    assert local_state.pending_approval is not None
    assert llm_state.pending_approval is not None
    assert local_state.pending_approval.tool_name == llm_state.pending_approval.tool_name == "cad.execute_build123d"
    assert len(local_adapter.prompts) == len(llm_adapter.prompts) == 2
    assert '"resume_summary"' in local_adapter.prompts[1]
    assert '"resume_summary"' in llm_adapter.prompts[1]
    assert '"working_memory"' in local_adapter.prompts[1]
    assert '"working_memory"' in llm_adapter.prompts[1]


def test_engine_bootstraps_project_context_before_real_adapter_step(tmp_path: Path) -> None:
    class CapturingAdapter:
        adapter_id = "spy"
        label = "Spy"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.prompts.append(prompt)
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(
                    {"action": {"type": "final", "message": "Model explained."}, "done": True}
                ),
            )

    calls = []
    adapter = CapturingAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"spy": adapter},
        tool_executor=lambda name, inp: calls.append((name, inp)) or {
            "schema_version": "0.1",
            "project_id": inp["project_id"],
            "project": {"name": "Schenkel"},
            "agent_brief": {"part_summary": "A plate with holes."},
        },
    )
    state = engine.start(
        AutopilotRunRequest(
            message="Explain this model",
            project_id="p1",
            adapter_id="spy",
            dry_run=False,
        )
    )
    assert state.status == "completed"
    assert calls == [("aieng.agent_context", {"project_id": "p1"})]
    assert "Loaded initial project context" in adapter.prompts[0]


def test_engine_continue_executes_approved_pending_tool(tmp_path: Path) -> None:
    calls = []
    store = AutopilotStore(tmp_path / "runs")
    engine = AutopilotEngine(
        store=store,
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"ok": True},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="make cad",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    }
                },
            ],
        )
    )
    resumed = engine.continue_run(state.run_id, approved=True)
    assert resumed.status == "completed"
    assert calls == [("cad.execute_build123d", {"project_id": "p1", "code": "result = None"})]
    assert resumed.plan is not None
    approval_step = next(step for step in resumed.plan.steps if step.id == "await_approval")
    execute_step = next(step for step in resumed.plan.steps if step.id == "execute_tool")
    assert approval_step.status == "completed"
    assert execute_step.status == "completed"


def test_engine_rejects_pending_approval_without_execution(tmp_path: Path) -> None:
    calls = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"ok": True},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="make cad",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    }
                },
            ],
        )
    )
    rejected = engine.continue_run(state.run_id, approved=False)
    assert rejected.status == "blocked"
    assert not calls


def test_cad_generation_runs_readonly_critique_followup_when_registered(tmp_path: Path) -> None:
    calls = []
    runtime_tools = RUNTIME_TOOLS + [
        {"name": "cad.critique", "description": "critique", "input_schema": {"type": "object"}},
    ]
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=runtime_tools,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"status": "ok"},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="make cad",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "code": "result = None"},
                    }
                },
            ],
        )
    )
    resumed = engine.continue_run(state.run_id, approved=True)
    assert resumed.status == "completed"
    assert calls == [
        ("cad.execute_build123d", {"project_id": "p1", "code": "result = None"}),
        ("cad.critique", {"project_id": "p1", "mode": "auto"}),
    ]


def test_cad_generation_slice_feeds_topology_observation_after_approval(tmp_path: Path) -> None:
    calls = []

    def _execute(name: str, inp: dict) -> dict:
        calls.append((name, inp))
        return {
            "named_parts": ["vertical_leg", "horizontal_leg", "bolt_hole_A"],
            "parts_added": ["vertical_leg", "horizontal_leg", "bolt_hole_A"],
            "mode": inp.get("mode", "replace"),
            "used_base": False,
        }

    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=_execute,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="create a bracket",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {"project_id": "p1", "mode": "replace", "code": "from build123d import *\nresult = Box(1,1,1)"},
                    },
                    "user_message": "Approval required before writing CAD.",
                },
            ],
        )
    )
    resumed = engine.continue_run(state.run_id, approved=True)
    assert calls[0][0] == "cad.execute_build123d"
    tool_obs = [obs for obs in resumed.observations if obs.kind == "tool_result"]
    assert any("vertical_leg" in str(obs.data.get("output")) for obs in tool_obs)


def test_preprocessing_slice_runs_preflight_after_setup_patch(tmp_path: Path) -> None:
    calls = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"ok": True},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="fix selected face and apply load",
            project_id="p1",
            dry_run=False,
            selected_geometry={"pointers": ["@face:f_left"]},
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cae.apply_setup_patch",
                        "input": {"project_id": "p1", "patch": {"op": "merge_object"}},
                    }
                },
                {"action": {"type": "final", "message": "Preflight complete."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert calls[:2] == [
        ("cae.apply_setup_patch", {"project_id": "p1", "patch": {"op": "merge_object"}}),
        ("cae.prepare_solver_run", {"project_id": "p1"}),
    ]


def test_solver_slice_runs_postprocess_followups_after_approval(tmp_path: Path) -> None:
    calls = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"ok": True, "tool": name},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="run solver",
            project_id="p1",
            dry_run=False,
            fake_actions=[
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cae.run_solver",
                        "input": {"project_id": "p1", "runId": "load_case_001"},
                    }
                },
            ],
        )
    )
    resumed = engine.continue_run(state.run_id, approved=True)
    assert resumed.status == "completed"
    assert [name for name, _inp in calls] == [
        "cae.run_solver",
        "cae.extract_solver_results",
        "cae.extract_field_regions",
        "postprocess.refresh_cae_summary",
    ]


def test_reply_to_chatting_run_resumes_without_approval(tmp_path: Path) -> None:
    class ChatThenFinalAdapter:
        adapter_id = "chatty"
        label = "Chatty"

        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            action = (
                {"action": {"type": "chat", "message": "What size bracket do you need?"}}
                if self.calls == 1
                else {"action": {"type": "final", "message": "Follow-up received."}, "done": True}
            )
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(action),
            )

    adapter = ChatThenFinalAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"chatty": adapter},
    )
    state = engine.start(AutopilotRunRequest(message="make a bracket", adapter_id="chatty"))
    assert state.status == "chatting"

    resumed = engine.reply_to_run(state.run_id, "120mm wide")
    assert resumed.status == "completed"
    assert resumed.final_message == "Follow-up received."
    assert any(obs.data.get("reply") is True for obs in resumed.observations)


def test_follow_up_running_run_is_queued(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    state = engine.start(
        AutopilotRunRequest(
            message="wait",
            fake_actions=[{"action": {"type": "pause", "reason": "Need more context."}}],
        )
    )
    state.status = "running"
    engine.store.save(state)

    queued = engine.follow_up_run(state.run_id, "also add ribs")
    assert queued.status == "running"
    assert queued.queued_user_messages == ["also add ribs"]
    assert any(obs.data.get("queued") is True for obs in queued.observations)


def test_cancel_marker_stops_before_next_adapter_step(tmp_path: Path) -> None:
    class FinalAdapter:
        adapter_id = "finalizer"
        label = "Finalizer"

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate(
                    {"action": {"type": "final", "message": "Should not run."}, "done": True}
                ),
            )

    store = AutopilotStore(tmp_path / "runs")
    engine = AutopilotEngine(store=store, runtime_tools=RUNTIME_TOOLS, adapters={"finalizer": FinalAdapter()})
    state = engine.start(AutopilotRunRequest(message="x", adapter_id="finalizer", max_steps=1))
    state.status = "running"
    store.save(state)
    store.request_cancel(state.run_id)

    engine._step_loop(state, FinalAdapter(), 1)  # exercise the cooperative check directly
    assert state.status == "cancelled"


def test_cancel_run_emits_single_cancel_event_when_worker_also_sees_marker(tmp_path: Path) -> None:
    events: list[dict] = []
    store = AutopilotStore(tmp_path / "runs")
    engine = AutopilotEngine(store=store, runtime_tools=RUNTIME_TOOLS, on_event=events.append)
    state = engine.start(
        AutopilotRunRequest(
            message="wait",
            project_id="p1",
            fake_actions=[{"action": {"type": "pause", "reason": "waiting"}}],
        )
    )

    cancelled = engine.cancel_run(state.run_id)
    assert cancelled.status == "cancelled"
    assert [event["type"] for event in events].count("run_cancelled") == 1

    # Simulate an already-running worker reaching its cooperative cancel check
    # after the API endpoint has persisted cancellation.
    in_flight = state
    assert engine._cancel_if_requested(in_flight) is True
    assert in_flight.status == "cancelled"
    assert [event["type"] for event in events].count("run_cancelled") == 1


def test_adapter_failure_does_not_emit_run_cancelled(tmp_path: Path) -> None:
    class FailingAdapter:
        adapter_id = "failing"
        label = "Failing"

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            return AdapterInvocationResult(status="error", diagnostic="adapter exploded")

    events: list[dict] = []
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"failing": FailingAdapter()},
        on_event=events.append,
    )

    state = engine.start(AutopilotRunRequest(message="hello", project_id="p1", adapter_id="failing"))

    assert state.status == "failed"
    assert any(event["type"] == "tool_failed" for event in events)
    assert not any(event["type"] == "run_cancelled" for event in events)


def test_no_chat_session_run_uses_stable_adapter_session_id_across_steps(tmp_path: Path) -> None:
    class CapturingAdapter:
        adapter_id = "capture"
        label = "Capture"

        def __init__(self) -> None:
            self.calls = 0
            self.session_ids: list[str | None] = []
            self.step_indices: list[int] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            self.session_ids.append(kwargs.get("session_id"))
            self.step_indices.append(kwargs.get("step_index"))
            action = (
                {
                    "action": {
                        "type": "tool_call",
                        "tool_name": "aieng.agent_context",
                        "input": {"project_id": "p1"},
                    }
                }
                if self.calls == 1
                else {"action": {"type": "final", "message": "Observed."}, "done": True}
            )
            return AdapterInvocationResult(status="success", action=AutopilotAgentAction.model_validate(action))

    adapter = CapturingAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"capture": adapter},
        tool_executor=lambda _name, _inp: {"ok": True},
    )

    state = engine.start(
        AutopilotRunRequest(
            message="inspect the model",
            project_id="p1",
            adapter_id="capture",
            dry_run=False,
        )
    )

    assert state.status == "completed"
    assert adapter.session_ids == [f"run:{state.run_id}", f"run:{state.run_id}"]
    assert adapter.step_indices == [0, 1]


def test_chat_session_adapter_session_id_unchanged(tmp_path: Path) -> None:
    class CapturingAdapter:
        adapter_id = "capture"
        label = "Capture"

        def __init__(self) -> None:
            self.session_ids: list[str | None] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300, **kwargs):  # type: ignore[no-untyped-def]
            self.session_ids.append(kwargs.get("session_id"))
            return AdapterInvocationResult(
                status="success",
                action=AutopilotAgentAction.model_validate({"action": {"type": "final", "message": "Done."}, "done": True}),
            )

    adapter = CapturingAdapter()
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        adapters={"capture": adapter},
    )

    state = engine.start(
        AutopilotRunRequest(
            message="explain the model",
            project_id="p1",
            session_id="chat-session-123",
            adapter_id="capture",
        )
    )

    assert state.status == "completed"
    assert adapter.session_ids == ["chat-session-123"]
