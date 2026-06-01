from pathlib import Path

import pytest

from app.agent_autopilot.schema import AgentPlan, AgentPlanStep, AutopilotRunState
from app.agent_autopilot.store import AutopilotStore


def test_store_round_trips_run_state(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    state = AutopilotRunState(
        run_id="run1",
        status="running",
        message="make a bracket",
        adapter_id="fake",
    )
    store.save(state)
    loaded = store.load("run1")
    assert loaded.run_id == "run1"
    assert loaded.message == "make a bracket"
    assert loaded.working_state.objective == ""


def test_store_round_trips_run_state_plan(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    state = AutopilotRunState(
        run_id="run1",
        status="running",
        message="make a bracket",
        adapter_id="fake",
    )
    state.plan = AgentPlan(
        id="plan1",
        objective="make a bracket",
        status="running",
        steps=[AgentPlanStep(id="observe_context", title="Observe context")],
        current_step_id="observe_context",
    )

    store.save(state)
    loaded = store.load("run1")

    assert loaded.plan is not None
    assert loaded.plan.id == "plan1"
    assert loaded.plan.steps[0].id == "observe_context"


def test_store_round_trips_run_state_working_state(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    state = AutopilotRunState(
        run_id="run1",
        status="running",
        message="make a bracket",
        adapter_id="fake",
    )
    state.working_state.objective = "make a bracket"
    state.working_state.current_blockers = ["Awaiting approval."]
    state.working_state.latest_evidence = [{"tool_name": "cad.plan_build123d_skill"}]

    store.save(state)
    loaded = store.load("run1")

    assert loaded.working_state.objective == "make a bracket"
    assert loaded.working_state.current_blockers == ["Awaiting approval."]
    assert loaded.working_state.latest_evidence == [{"tool_name": "cad.plan_build123d_skill"}]


def test_store_retries_transient_windows_replace_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AutopilotStore(tmp_path / "runs")
    state = AutopilotRunState(
        run_id="run1",
        status="running",
        message="make a bracket",
        adapter_id="fake",
    )
    from app.agent_autopilot import store as store_module

    real_replace = store_module.os.replace
    calls = 0

    def flaky_replace(src: Path, dst: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("locked by reader")
        real_replace(src, dst)

    monkeypatch.setattr(store_module.os, "replace", flaky_replace)

    store.save(state)

    assert calls == 2
    assert store.load("run1").message == "make a bracket"


def test_store_reports_corrupt_run_file(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    (tmp_path / "runs" / "bad.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError):
        store.load("bad")
