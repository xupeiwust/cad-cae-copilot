"""Backend command routing — /simulate is simulation planning / readiness (v1).

When a run carries composer_intent.command == "simulate", the engine:
  * injects a simulation planning/readiness instruction into the run context
    (biasing the agent toward CAE setup/preflight + read-only inspection tools,
    telling it to ask_user for missing material/load/constraint/mesh/solver/
    analysis_type, and to output a plan WITHOUT running the solver), and
  * suppresses the geometry-mutation guard, so a simulation-plan `final` is
    allowed without a CAD mutation even when the free text contains words like
    "add" (e.g. "add a 500N load").

It does NOT auto-run the solver, does NOT modify CAD, and does NOT bypass
approval. /build and /modify stay mutation-required; /critique and /explain stay
read-only. Uses the deterministic fake adapter — no real LLM / solver.
"""

from pathlib import Path
from types import SimpleNamespace

from app.agent_autopilot.engine import (
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    SIMULATE_COMMAND_INSTRUCTION,
    AutopilotEngine,
    command_intent_label,
    command_mutation_intent,
    is_mutation_required_command,
    is_read_only_command,
    is_simulation_command,
    mention_context_label,
    suppresses_mutation_guard,
)
from app.agent_autopilot.schema import AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
    {"name": "cae.prepare_solver_run", "description": "preflight", "input_schema": {"type": "object"}},
    {"name": "cae.run_solver", "description": "solver", "input_schema": {"type": "object"}},
    {"name": "cad.execute_build123d", "description": "cad", "input_schema": {"type": "object"}},
]


def _engine(tmp_path: Path, **kwargs) -> AutopilotEngine:
    return AutopilotEngine(store=AutopilotStore(tmp_path / "runs"), runtime_tools=RUNTIME_TOOLS, **kwargs)


def _intent(command: str, text: str, mentions: list[dict] | None = None) -> dict:
    return {
        "command": command,
        "commandRaw": f"/{command}",
        "text": text,
        "mentions": mentions or [],
        "errors": [],
    }


def _summaries(state) -> list[str]:
    return [str(o.summary) for o in state.observations]


# --- Unit-level helper coverage ---------------------------------------------


def test_simulate_command_helpers() -> None:
    sim = SimpleNamespace(composer_intent={"command": "simulate"})
    assert command_intent_label(sim) == "plan_simulation"
    assert is_simulation_command(sim) is True
    assert suppresses_mutation_guard(sim) is True
    # Not read-only and not mutation-required.
    assert is_read_only_command(sim) is False
    assert is_mutation_required_command(sim) is False
    assert command_mutation_intent(sim) is None

    # Other routed commands are unaffected.
    assert is_simulation_command(SimpleNamespace(composer_intent={"command": "explain"})) is False
    assert suppresses_mutation_guard(SimpleNamespace(composer_intent={"command": "explain"})) is True
    assert suppresses_mutation_guard(SimpleNamespace(composer_intent={"command": "modify"})) is False
    assert is_simulation_command(SimpleNamespace(composer_intent=None)) is False


# --- /simulate injects the planning instruction & suppresses the guard -------


def test_simulate_plan_final_without_mutation_is_allowed(tmp_path: Path) -> None:
    # Free text contains "add" — the heuristic would normally trip the guard, but
    # /simulate is a planning request so the plan final must still be allowed.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="add a 500N load on top and simulate the stress",
            project_id="p1",
            composer_intent=_intent("simulate", "add a 500N load on top and simulate the stress"),
            fake_actions=[
                {
                    "action": {
                        "type": "final",
                        "message": "Plan: setup -> mesh -> preflight -> deck -> solver -> post. Solver NOT run yet.",
                    },
                    "done": True,
                },
            ],
        )
    )
    assert state.status == "completed"
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))
    # The /simulate instruction reached the run context with the right metadata.
    instr = next(o for o in state.observations if o.summary == SIMULATE_COMMAND_INSTRUCTION)
    assert instr.data["intent_type"] == "plan_simulation"
    assert instr.data["simulation_planning"] is True
    assert instr.data["mutation_required"] is False
    assert instr.data["read_only"] is False


def test_simulate_can_ask_user_for_missing_inputs(tmp_path: Path) -> None:
    # Missing material/load/etc → the agent asks the user. This must not be
    # blocked by the mutation guard, and must not be treated as a failed run.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="simulate this part",
            project_id="p1",
            composer_intent=_intent("simulate", "simulate this part"),
            fake_actions=[
                {"action": {"type": "ask_user", "question": "Which material, load, and constraints should I use?"}},
            ],
        )
    )
    assert state.status == "blocked"  # waiting on the user, not a guard rejection
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))
    ask = next(o for o in state.observations if o.kind == "ask_user")
    assert "material" in ask.data["question"]


def test_simulate_after_readonly_preflight_is_allowed(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []
    engine = _engine(tmp_path, tool_executor=lambda name, inp: calls.append((name, inp)) or {"status": "ready"})
    state = engine.start(
        AutopilotRunRequest(
            message="simulate the bracket under load",
            project_id="p1",
            dry_run=False,
            composer_intent=_intent("simulate", "simulate the bracket under load"),
            fake_actions=[
                {"action": {"type": "tool_call", "tool_name": "cae.prepare_solver_run", "input": {"project_id": "p1"}}},
                {"action": {"type": "final", "message": "Readiness checked. Plan ready; solver not run."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert ("cae.prepare_solver_run", {"project_id": "p1"}) in calls
    # The solver was never auto-invoked.
    assert not any(name == "cae.run_solver" for name, _ in calls)
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))


def test_simulate_scopes_plan_to_mentioned_part(tmp_path: Path) -> None:
    part = {"kind": "part", "raw": "@part:bracket", "value": "bracket"}
    obj = SimpleNamespace(composer_intent=_intent("simulate", "simulate it", [part]))
    label = mention_context_label(obj)
    assert label is not None
    assert "bracket" in label
    assert "Scope the simulation" in label
    assert "do not run the solver" in label


def test_chinese_simulate_command_roundtrip(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="仿真这个支架在载荷下的应力",
            project_id="p1",
            composer_intent=_intent("simulate", "仿真这个支架在载荷下的应力"),
            fake_actions=[
                {"action": {"type": "final", "message": "计划已生成；求解器尚未运行。"}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert any(o.summary == SIMULATE_COMMAND_INSTRUCTION for o in state.observations)
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))


# --- Regression: other commands unaffected by adding /simulate --------------


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
    guard = [o for o in state.observations if o.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard and guard[-1].data["intent"] == "create_geometry"


def test_modify_still_requires_mutation(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="the proportions look off",
            project_id="p1",
            composer_intent=_intent("modify", "the proportions look off"),
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "Looks fine."}, "done": True},
                {"action": {"type": "ask_user", "question": "Which part?"}},
            ],
        )
    )
    assert state.status == "blocked"
    guard = [o for o in state.observations if o.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard and guard[-1].data["intent"] == "modify_geometry"


def test_no_command_natural_language_unchanged(tmp_path: Path) -> None:
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
    guard = [o for o in state.observations if o.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard and guard[-1].data["intent"] == "create_geometry"


# --- v1.5: deterministic readiness report injection -------------------------


def _readiness_obs(state):
    return next(
        (o for o in state.observations if isinstance(o.data, dict) and o.data.get("simulation_readiness")),
        None,
    )


def test_simulate_injects_readiness_report_when_setup_incomplete(tmp_path: Path) -> None:
    # No CAE context → setup not_found, required inputs missing, agent must ask.
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
    )
    state = engine.start(
        AutopilotRunRequest(
            message="simulate the bracket",
            project_id="p1",
            composer_intent=_intent("simulate", "simulate the bracket"),
            fake_actions=[
                {"action": {"type": "ask_user", "question": "Which material/loads/constraints?"}},
            ],
        )
    )
    obs = _readiness_obs(state)
    assert obs is not None
    report = obs.data["simulation_readiness"]
    assert report["setup_source"] == "not_found"
    assert set(report["missing_required_inputs"]) == {"material", "loads", "constraints"}
    assert report["solver_executed"] is False
    assert "Missing REQUIRED inputs" in obs.summary
    # Asking the user is allowed and not blocked by the mutation guard.
    assert state.status == "blocked"
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))


def test_simulate_readiness_complete_setup_allows_plan_final(tmp_path: Path) -> None:
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        agent_context={
            "cae": {
                "present": True,
                "materials": ["steel"],
                "loads": [{"type": "force"}],
                "boundary_conditions": [{"type": "fixed"}],
            }
        },
    )
    state = engine.start(
        AutopilotRunRequest(
            message="simulate the bracket under load",
            project_id="p1",
            composer_intent=_intent("simulate", "simulate the bracket under load"),
            fake_actions=[
                {"action": {"type": "final", "message": "Plan ready; solver not run."}, "done": True},
            ],
        )
    )
    obs = _readiness_obs(state)
    assert obs is not None
    report = obs.data["simulation_readiness"]
    assert report["setup_source"] == "cae_setup"
    assert report["missing_required_inputs"] == []
    assert report["ready_for_solver"] is True
    assert report["solver_executed"] is False
    assert state.status == "completed"


def test_simulate_readiness_marks_unknown_mentioned_part(tmp_path: Path) -> None:
    part = {"kind": "part", "raw": "@part:ghost", "value": "ghost"}
    engine = AutopilotEngine(
        store=AutopilotStore(tmp_path / "runs"),
        runtime_tools=RUNTIME_TOOLS,
        agent_context={"cad": {"named_parts": ["bracket", "rib"]}},
    )
    state = engine.start(
        AutopilotRunRequest(
            message="simulate @part:ghost",
            project_id="p1",
            composer_intent=_intent("simulate", "simulate @part:ghost", [part]),
            fake_actions=[
                {"action": {"type": "ask_user", "question": "That part does not exist — which part?"}},
            ],
        )
    )
    report = _readiness_obs(state).data["simulation_readiness"]
    targets = {t["value"]: t["known"] for t in report["targets"]["parts"]}
    assert targets["ghost"] is False  # not in known named_parts


def test_non_simulate_command_gets_no_readiness_report(tmp_path: Path) -> None:
    engine = AutopilotEngine(store=AutopilotStore(tmp_path / "runs"), runtime_tools=RUNTIME_TOOLS)
    state = engine.start(
        AutopilotRunRequest(
            message="explain the model",
            project_id="p1",
            composer_intent=_intent("explain", "explain the model"),
            fake_actions=[{"action": {"type": "final", "message": "It is a bracket."}, "done": True}],
        )
    )
    assert _readiness_obs(state) is None
