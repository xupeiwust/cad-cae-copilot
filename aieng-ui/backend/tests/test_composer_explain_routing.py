"""Backend command routing — /explain is a read-only explanation request.

When a run carries composer_intent.command == "explain", the engine:
  * injects a read-only explanation instruction into the run context (biasing the
    agent toward read-only context/source/topology tools), and
  * suppresses the geometry-mutation guard, so a `final` is allowed after a
    read-only inspection (or a clear "nothing to explain" answer) even if the
    free text contains words like "add"/"change".

/build and /modify stay mutation-required; /critique stays read-only critique;
unrouted commands and plain natural language keep the free-text heuristic.

Uses the deterministic fake adapter + a mocked tool_executor — no real
Claude/Codex/LLM and no build123d execution required.
"""

from pathlib import Path
from types import SimpleNamespace

from app.agent_autopilot.engine import (
    EXPLAIN_COMMAND_INSTRUCTION,
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    AutopilotEngine,
    command_intent_label,
    command_mutation_intent,
    is_mutation_required_command,
    is_read_only_command,
)
from app.agent_autopilot.schema import AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
    {"name": "cad.get_source", "description": "source", "input_schema": {"type": "object"}},
    {"name": "cad.execute_build123d", "description": "cad", "input_schema": {"type": "object"}},
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


# --- Unit-level helper coverage ---------------------------------------------


def test_explain_command_helpers() -> None:
    explain = SimpleNamespace(composer_intent={"command": "explain"})
    assert command_intent_label(explain) == "explain_project"
    assert command_mutation_intent(explain) is None  # read-only → no forced mutation
    assert is_mutation_required_command(explain) is False
    assert is_read_only_command(explain) is True

    # /critique is also read-only; /build and /modify are not.
    assert is_read_only_command(SimpleNamespace(composer_intent={"command": "critique"})) is True
    assert is_read_only_command(SimpleNamespace(composer_intent={"command": "build"})) is False
    assert is_read_only_command(SimpleNamespace(composer_intent={"command": "modify"})) is False
    # Unrouted / missing metadata.
    assert is_read_only_command(SimpleNamespace(composer_intent={"command": "simulate"})) is False
    assert is_read_only_command(SimpleNamespace(composer_intent=None)) is False


# --- /explain is read-only, never mutation-gated ----------------------------


def test_explain_final_without_mutation_is_allowed(tmp_path: Path) -> None:
    # Free text contains "add" — the heuristic would normally trip the guard, but
    # /explain is read-only so the final must still be allowed.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="why did you add ribs to this bracket?",
            project_id="p1",
            composer_intent=_intent("explain", "why did you add ribs to this bracket?"),
            fake_actions=[
                {"action": {"type": "final", "message": "The ribs stiffen the base plate."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert state.final_message == "The ribs stiffen the base plate."
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)
    # The /explain instruction reached the run context.
    assert any(obs.summary == EXPLAIN_COMMAND_INSTRUCTION for obs in state.observations)
    instruction_obs = next(obs for obs in state.observations if obs.summary == EXPLAIN_COMMAND_INSTRUCTION)
    assert instruction_obs.data["intent_type"] == "explain_project"
    assert instruction_obs.data["read_only"] is True
    assert instruction_obs.data["mutation_required"] is False


def test_explain_after_readonly_context_tool_is_allowed(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []
    engine = _engine(tmp_path, tool_executor=lambda name, inp: calls.append((name, inp)) or {"status": "ok"})
    state = engine.start(
        AutopilotRunRequest(
            message="explain the current model",
            project_id="p1",
            dry_run=False,
            composer_intent=_intent("explain", "explain the current model"),
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "cad.get_source", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "It is a 2-arm bracket."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert ("cad.get_source", {"project_id": "p1"}) in calls
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)


def test_explain_nothing_to_explain_final_is_allowed(tmp_path: Path) -> None:
    # No CAD available → a clear "nothing to explain" final is allowed.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="explain this project",
            project_id="p1",
            composer_intent=_intent("explain", "explain this project"),
            fake_actions=[
                {"action": {"type": "final", "message": "There is no CAD model in this project yet."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)


def test_chinese_explain_command_roundtrip(tmp_path: Path) -> None:
    # Chinese command text + /explain: routed read-only, final allowed.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="解释一下当前模型有哪些部件",
            project_id="p1",
            composer_intent=_intent("explain", "解释一下当前模型有哪些部件"),
            fake_actions=[
                {"action": {"type": "final", "message": "当前模型包含机身和支架。"}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert any(obs.summary == EXPLAIN_COMMAND_INSTRUCTION for obs in state.observations)
    assert not any(obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for obs in state.observations)


# --- Other commands are unaffected by adding /explain -----------------------


def test_build_still_requires_mutation(tmp_path: Path) -> None:
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
    assert state.status == "awaiting_approval"
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs and guard_obs[-1].data["intent"] == "create_geometry"


def test_modify_still_requires_mutation(tmp_path: Path) -> None:
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
    assert state.status == "blocked"
    guard_obs = [obs for obs in state.observations if obs.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs and guard_obs[-1].data["intent"] == "modify_geometry"


def test_critique_remains_read_only(tmp_path: Path) -> None:
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


def test_no_command_natural_language_unchanged(tmp_path: Path) -> None:
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
