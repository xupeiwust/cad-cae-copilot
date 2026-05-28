from pathlib import Path

from app.agent_autopilot.engine import AutopilotEngine
from app.agent_autopilot.schema import AdapterInvocationResult, AutopilotAgentAction, AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
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
    assert any(obs.kind == "policy_block" for obs in state.observations)
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


def test_engine_bootstraps_project_context_before_real_adapter_step(tmp_path: Path) -> None:
    class CapturingAdapter:
        adapter_id = "spy"
        label = "Spy"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def invoke(self, *, prompt, action_schema, timeout_seconds=300):  # type: ignore[no-untyped-def]
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
            message="解释一下这个模型",
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
