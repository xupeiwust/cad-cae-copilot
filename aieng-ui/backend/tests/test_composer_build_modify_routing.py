"""Backend command routing — /build and /modify are mutation-required.

When a run carries composer_intent.command == "build" / "modify", the engine:
  * injects a create/modify-geometry instruction into the run context, and
  * forces the geometry-mutation guard ON, so a bare `final` is rejected until a
    CAD mutation tool has succeeded — *regardless* of whether the free text
    contains create/modify trigger words.

/critique stays read-only (mutation guard suppressed), unrouted commands and
plain natural language keep the free-text heuristic, and a successful CAD
mutation (cad.execute_build123d etc.) lets the run finish. cad.critique and
other read-only tools do NOT satisfy the requirement.

Uses the deterministic fake adapter + a mocked tool_executor — no real
Claude/Codex/LLM and no build123d execution required.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_autopilot.engine import (
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    BUILD_COMMAND_INSTRUCTION,
    MODIFY_COMMAND_INSTRUCTION,
    AutopilotEngine,
    command_intent_label,
    command_mutation_intent,
    is_mutation_required_command,
)
from app.agent_autopilot.schema import (
    AdapterInvocationResult,
    AutopilotAgentAction,
    AutopilotRunRequest,
)
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
    {"name": "cad.execute_build123d", "description": "cad", "input_schema": {"type": "object"}},
    {"name": "cad.critique", "description": "critique", "input_schema": {"type": "object"}},
]


def _engine(tmp_path: Path, **kwargs) -> AutopilotEngine:
    return AutopilotEngine(store=AutopilotStore(tmp_path / "runs"), runtime_tools=RUNTIME_TOOLS, **kwargs)


def _intent(command: str, text: str) -> dict:
    return {
        "command": command,
        "commandRaw": f"/{command}",
        "text": text,
        "mentions": [],
        "errors": [],
    }


class _CadThenFinalAdapter:
    """Step 1: call cad.execute_build123d. Step 2+: return final."""

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


# --- Unit-level helper coverage ---------------------------------------------


def test_command_helpers_route_build_and_modify() -> None:
    build = SimpleNamespace(composer_intent={"command": "build"})
    assert command_intent_label(build) == "create_geometry"
    assert command_mutation_intent(build) == "create_geometry"
    assert is_mutation_required_command(build) is True

    modify = SimpleNamespace(composer_intent={"command": "modify"})
    assert command_intent_label(modify) == "modify_geometry"
    assert command_mutation_intent(modify) == "modify_geometry"
    assert is_mutation_required_command(modify) is True

    # /critique stays routed but read-only (not mutation-required).
    critique = SimpleNamespace(composer_intent={"command": "critique"})
    assert command_intent_label(critique) == "critique_geometry"
    assert command_mutation_intent(critique) is None
    assert is_mutation_required_command(critique) is False

    # Unrouted / unknown / natural language → no forced intent.
    for command in ("simulate", "totally-unknown"):
        obj = SimpleNamespace(composer_intent={"command": command})
        assert command_intent_label(obj) is None
        assert command_mutation_intent(obj) is None
        assert is_mutation_required_command(obj) is False
    assert command_mutation_intent(SimpleNamespace(composer_intent=None)) is None


# --- /build is mutation-required --------------------------------------------


def test_build_cannot_final_before_mutation(tmp_path: Path) -> None:
    # Free text has NO create trigger word — only the /build command forces the
    # mutation requirement.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="a quadcopter chassis",
            project_id="p1",
            composer_intent=_intent("build", "a quadcopter chassis"),
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

    # The premature final was rejected; the agent reselected a mutation tool.
    assert state.status == "awaiting_approval"
    assert state.pending_approval is not None
    assert state.pending_approval.tool_name == "cad.execute_build123d"
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs
    assert guard_obs[-1].data["intent"] == "create_geometry"
    # The /build instruction reached the run context.
    assert any(obs.summary == BUILD_COMMAND_INSTRUCTION for obs in state.observations)


def test_build_after_mutation_success_can_final(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []
    engine = _engine(
        tmp_path,
        adapters={"cad-final": _CadThenFinalAdapter()},
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"named_parts": ["body"]},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="a quadcopter chassis",
            project_id="p1",
            adapter_id="cad-final",
            dry_run=False,
            composer_intent=_intent("build", "a quadcopter chassis"),
        )
    )
    assert state.status == "awaiting_approval"
    resumed = engine.continue_run(state.run_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.final_message == "Geometry updated."
    assert ("cad.execute_build123d", {"project_id": "p1", "code": "result = None"}) in calls
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in resumed.observations)


# --- /modify is mutation-required -------------------------------------------


def test_modify_cannot_final_before_mutation(tmp_path: Path) -> None:
    # Free text has NO modify trigger word — only the /modify command forces it.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="the proportions look off",
            project_id="p1",
            composer_intent=_intent("modify", "the proportions look off"),
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "Looks fine."}, "done": True},
                {"action": {"type": "ask_user", "question": "Which part should I change?"}},
            ],
        )
    )

    # The premature final was rejected; ask_user (clarification) is allowed.
    assert state.status == "blocked"
    assert [step.action.action.type for step in state.steps] == ["ask_user"]
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs
    assert guard_obs[-1].data["intent"] == "modify_geometry"
    assert any(obs.summary == MODIFY_COMMAND_INSTRUCTION for obs in state.observations)


def test_modify_after_mutation_success_can_final(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []
    engine = _engine(
        tmp_path,
        adapters={"cad-final": _CadThenFinalAdapter()},
        tool_executor=lambda name, inp: calls.append((name, inp)) or {"named_parts": ["body"]},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="the proportions look off",
            project_id="p1",
            adapter_id="cad-final",
            dry_run=False,
            composer_intent=_intent("modify", "the proportions look off"),
        )
    )
    assert state.status == "awaiting_approval"
    resumed = engine.continue_run(state.run_id, approved=True)

    assert resumed.status == "completed"
    assert resumed.final_message == "Geometry updated."
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in resumed.observations)


def test_critique_does_not_satisfy_modify(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []
    engine = _engine(tmp_path, tool_executor=lambda name, inp: calls.append((name, inp)) or {"status": "ok"})
    state = engine.start(
        AutopilotRunRequest(
            message="the proportions look off",
            project_id="p1",
            dry_run=False,
            max_steps=3,
            composer_intent=_intent("modify", "the proportions look off"),
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "cad.critique", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "Critique only."}, "done": True},
                {"action": {"type": "ask_user", "question": "Should I proceed with a CAD edit?"}},
            ],
        )
    )

    # A read-only critique tool does NOT satisfy /modify's mutation requirement.
    assert state.status == "blocked"
    assert calls == [("cad.critique", {"project_id": "p1"})]
    assert any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)
    assert state.final_message is None


# --- /critique stays read-only ----------------------------------------------


def test_critique_does_not_require_mutation(tmp_path: Path) -> None:
    # Free text contains "add", which would trip the heuristic — but /critique is
    # read-only, so the final must still be allowed.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="should I add ribs?",
            project_id="p1",
            composer_intent=_intent("critique", "should I add ribs?"),
            fake_actions=[
                {"action": {"type": "final", "message": "No manufacturability issues."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)


# --- Backward compatibility: no command / unknown command -------------------


def test_no_command_natural_language_uses_heuristic(tmp_path: Path) -> None:
    # No composer_intent: free-text "create" trigger still gates the final.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="create a drone body",
            project_id="p1",
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "Done."}, "done": True},
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
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs and guard_obs[-1].data["intent"] == "create_geometry"


def test_unknown_command_is_backward_compatible(tmp_path: Path) -> None:
    # An unrouted/unknown command with neutral text behaves like plain natural
    # language: no forced mutation requirement, final allowed.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="what parts does this model have?",
            project_id="p1",
            composer_intent=_intent("totally-unknown", "what parts does this model have?"),
            fake_actions=[
                {"action": {"type": "final", "message": "It has a body and arms."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)


def test_chinese_build_command_roundtrip(tmp_path: Path) -> None:
    # Chinese command text + /build: routed as create_geometry, mutation-required.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="一个四轴飞行器机架",
            project_id="p1",
            composer_intent=_intent("build", "一个四轴飞行器机架"),
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "完成。"}, "done": True},
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
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs and guard_obs[-1].data["intent"] == "create_geometry"
