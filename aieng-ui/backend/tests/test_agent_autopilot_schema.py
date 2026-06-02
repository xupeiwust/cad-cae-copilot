import pytest
from pydantic import ValidationError

from app.agent_autopilot.schema import AgentNextAction, AgentPlan, AgentPlanStep, AgentWorkingState, AutopilotAgentAction, AutopilotRunRequest, AutopilotRunState, ContextSummary, SkillToolOutput, map_autopilot_action_to_next_action


def test_agent_action_accepts_supported_action_types() -> None:
    for action in [
        {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {"project_id": "p1"}},
        {"type": "ask_user", "question": "Which face should be fixed?"},
        {"type": "final", "message": "Done."},
        {"type": "pause", "reason": "Adapter unavailable."},
    ]:
        parsed = AutopilotAgentAction.model_validate({"action": action})
        assert parsed.action.type == action["type"]


def test_agent_action_rejects_unknown_type_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AutopilotAgentAction.model_validate({"action": {"type": "shell", "command": "dir"}})
    with pytest.raises(ValidationError):
        AutopilotAgentAction.model_validate(
            {
                "action": {"type": "tool_call", "tool_name": "aieng.agent_context", "input": {}},
                "direct_file_write": True,
            }
        )


def test_agent_action_json_schema_serializes() -> None:
    schema = AutopilotAgentAction.json_schema_for_adapter()
    assert schema["type"] == "object"
    assert "action" in schema["properties"]


def test_agent_next_action_mapper_matches_autopilot_actions() -> None:
    tool = map_autopilot_action_to_next_action(
        AutopilotAgentAction.model_validate(
            {"action": {"type": "tool_call", "tool_name": "cad.get_source", "input": {"project_id": "p1"}}}
        ).action,
        target_step_id="step-1",
    )
    ask = map_autopilot_action_to_next_action(
        AutopilotAgentAction.model_validate({"action": {"type": "ask_user", "question": "Which material?"}}).action
    )
    final = map_autopilot_action_to_next_action(
        AutopilotAgentAction.model_validate({"action": {"type": "final", "message": "Done."}}).action,
        done=True,
    )
    pause = map_autopilot_action_to_next_action(
        AutopilotAgentAction.model_validate({"action": {"type": "pause", "reason": "Awaiting approval."}}).action
    )
    chat = map_autopilot_action_to_next_action(
        AutopilotAgentAction.model_validate({"action": {"type": "chat", "message": "Checking context."}}).action
    )

    assert tool.type == "execute_step"
    assert tool.target_step_id == "step-1"
    assert tool.payload["tool_name"] == "cad.get_source"
    assert ask.type == "ask_user"
    assert ask.payload["question"] == "Which material?"
    assert final.type == "finish_task"
    assert pause.type == "wait_for_user"
    assert chat.type == "answer_user"


def test_agent_next_action_contract_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        AgentNextAction.model_validate({"type": "wander", "reason": "invalid", "payload": {}})


def test_autopilot_request_accepts_llm_config() -> None:
    request = AutopilotRunRequest.model_validate(
        {
            "message": "explain the model",
            "adapter_id": "llm-api",
            "llm_config": {"provider": "openai-compatible", "model": "demo"},
        }
    )
    assert request.adapter_id == "llm-api"
    assert request.llm_config["model"] == "demo"


def test_autopilot_request_accepts_transient_top_level_api_key() -> None:
    request = AutopilotRunRequest.model_validate(
        {
            "message": "explain the model",
            "adapter_id": "llm-api",
            "llm_config": {"provider": "anthropic", "model": "kimi-for-coding"},
            "api_key": "sk-test",
        }
    )

    assert request.api_key == "sk-test"
    assert "api_key" not in request.model_dump()


def test_agent_plan_accepts_empty_defaults() -> None:
    plan = AgentPlan()

    assert plan.id
    assert plan.objective == ""
    assert plan.status == "pending"
    assert plan.steps == []
    assert plan.current_step_id is None
    assert plan.created_at
    assert plan.updated_at


def test_agent_plan_round_trips_through_pydantic() -> None:
    plan = AgentPlan(
        id="plan1",
        objective="Make a flange",
        status="running",
        current_step_id="step1",
        steps=[
            AgentPlanStep(
                id="step1",
                title="Plan CAD skill",
                kind="skill",
                status="completed",
                skill_name="cad.plan_build123d_skill",
                summary="Prepared deterministic flange plan.",
                evidence={"matched_terms": ["flange"]},
            ),
            AgentPlanStep(
                id="step2",
                title="Await approval",
                kind="approval",
                status="running",
                tool_name="cad.execute_build123d",
            ),
        ],
    )

    restored = AgentPlan.model_validate(plan.model_dump())

    assert restored == plan
    assert restored.steps[0].evidence["matched_terms"] == ["flange"]


def test_old_run_payload_without_plan_still_validates() -> None:
    payload = {
        "run_id": "run1",
        "status": "running",
        "message": "make a bracket",
        "adapter_id": "fake",
    }

    state = AutopilotRunState.model_validate(payload)

    assert state.run_id == "run1"
    assert state.steps == []
    assert state.working_state.objective == ""


def test_agent_working_state_round_trips_through_pydantic() -> None:
    working_state = AgentWorkingState(
        objective="Make a flange",
        current_mode="autopilot",
        accepted_assumptions=["Default thickness is 8mm."],
        open_questions=["Which finish?"],
        latest_evidence=[{"tool_name": "cad.plan_build123d_skill", "brief": "40mm flange"}],
        current_blockers=["Awaiting approval."],
        last_successful_tool="cad.plan_build123d_skill",
        recommended_next_action="Request approval for cad.execute_build123d.",
    )

    restored = AgentWorkingState.model_validate(working_state.model_dump())

    assert restored == working_state
    assert restored.latest_evidence[0]["tool_name"] == "cad.plan_build123d_skill"


def test_context_summary_contract_defaults_and_round_trip() -> None:
    summary = ContextSummary(
        session_id="session-1",
        project_id="project-1",
        goal="Make the Web Chat Agent stateful",
        current_state="Plan model compatibility has been documented.",
        completed_steps=["WCA-P1-001"],
        pending_steps=["WCA-P1-002"],
        relevant_files=["aieng-ui/docs/web-chat-agent-stateful-task.md"],
        risks=["Do not rename existing AgentPlan fields in place."],
        next_action="Implement AgentSession extension fields.",
    )

    restored = ContextSummary.model_validate(summary.model_dump())

    assert restored == summary
    assert restored.schema_version == 1
    assert restored.important_decisions == []
    assert restored.updated_at


def test_context_summary_rejects_extra_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        ContextSummary.model_validate(
            {
                "session_id": "session-1",
                "project_id": "project-1",
                "api_key": "sk-test",
            }
        )


def test_skill_tool_output_contract_defaults() -> None:
    output = SkillToolOutput(status="unsupported", skill_name="cad.plan_build123d_skill")

    assert output.intent == ""
    assert output.assumptions == []
    assert output.warnings == []
    assert output.proposed_tool is None
    assert output.proposed_input == {}
    assert output.verification_targets == []
