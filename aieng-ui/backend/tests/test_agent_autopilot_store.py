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
    loaded_plan = store.load_plan("run1")
    assert loaded_plan is not None
    assert loaded_plan.id == "plan1"


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


def test_store_lists_and_deletes_runs_by_project_or_session(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    keep = AutopilotRunState(run_id="keep", status="running", message="keep", adapter_id="fake", project_id="p1", session_id="s1")
    remove_session = AutopilotRunState(run_id="remove-session", status="running", message="remove", adapter_id="fake", project_id="p1", session_id="s2")
    remove_project = AutopilotRunState(run_id="remove-project", status="running", message="remove", adapter_id="fake", project_id="p2", session_id="s3")
    for state in (keep, remove_session, remove_project):
        store.save(state)
        store.request_cancel(state.run_id)

    assert {state.run_id for state in store.list_runs(project_id="p1")} == {"keep", "remove-session"}
    assert {state.run_id for state in store.list_runs(session_id="s2")} == {"remove-session"}
    assert store.delete_runs(session_id="s2") == 1
    assert store.delete_run("remove-session") is False
    assert {state.run_id for state in store.list_runs(project_id="p1")} == {"keep"}
    assert store.delete_runs(project_id="p2") == 1
    assert [state.run_id for state in store.list_runs()] == ["keep"]
    assert store.is_cancel_requested("keep") is True


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


def test_store_caches_list_runs_and_invalidates_on_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AutopilotStore(tmp_path / "runs")
    state = AutopilotRunState(
        run_id="run1",
        status="running",
        message="make a bracket",
        adapter_id="fake",
        project_id="p1",
        session_id="s1",
    )
    store.save(state)

    # Count how many times Path.read_text is called inside list_runs.
    read_calls = 0
    real_read_text = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_calls
        read_calls += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    # First list_runs should hit disk.
    runs1 = store.list_runs()
    assert len(runs1) == 1
    reads_after_first = read_calls
    assert reads_after_first > 0

    # Second list_runs should be served from cache.
    runs2 = store.list_runs()
    assert len(runs2) == 1
    assert read_calls == reads_after_first

    # save() must invalidate the cache.
    state2 = AutopilotRunState(
        run_id="run2",
        status="running",
        message="make a gear",
        adapter_id="fake",
        project_id="p1",
        session_id="s1",
    )
    store.save(state2)

    # After save, list_runs should see the new run (cache invalidated).
    runs3 = store.list_runs()
    assert len(runs3) == 2
    assert read_calls > reads_after_first


def test_store_caches_list_runs_with_filters(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    store.save(AutopilotRunState(run_id="a", status="running", message="a", adapter_id="fake", project_id="p1", session_id="s1"))
    store.save(AutopilotRunState(run_id="b", status="running", message="b", adapter_id="fake", project_id="p1", session_id="s2"))
    store.save(AutopilotRunState(run_id="c", status="running", message="c", adapter_id="fake", project_id="p2", session_id="s1"))

    # Each filter combination gets its own cache slot.
    assert len(store.list_runs(project_id="p1")) == 2
    assert len(store.list_runs(session_id="s1")) == 2
    assert len(store.list_runs(project_id="p1", session_id="s1")) == 1
    assert len(store.list_runs()) == 3


def test_filtered_list_runs_warms_full_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AutopilotStore(tmp_path / "runs")
    store.save(AutopilotRunState(run_id="a", status="running", message="a", adapter_id="fake", project_id="p1"))
    store.save(AutopilotRunState(run_id="b", status="running", message="b", adapter_id="fake", project_id="p2"))

    read_calls = 0
    real_read_text = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_calls
        read_calls += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    assert [state.run_id for state in store.list_runs(project_id="p1")] == ["a"]
    reads_after_filtered = read_calls
    assert reads_after_filtered == 2

    assert [state.run_id for state in store.list_runs()] == ["a", "b"]
    assert read_calls == reads_after_filtered


def test_store_invalidate_cache_on_delete_run(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    store.save(AutopilotRunState(run_id="run1", status="running", message="a", adapter_id="fake"))

    # Warm cache.
    assert len(store.list_runs()) == 1
    assert len(store._list_runs_cache) == 1

    store.delete_run("run1")
    assert len(store._list_runs_cache) == 0
    assert len(store.list_runs()) == 0


def test_list_runs_returns_copy_not_cached_reference(tmp_path: Path) -> None:
    """Mutating the returned list (or dropping items) must not corrupt the cache.

    Cancellation paths iterate list_runs() and mutate each state; the cached
    list must not be aliased by the returned one.
    """
    store = AutopilotStore(tmp_path / "runs")
    store.save(AutopilotRunState(run_id="r1", status="running", message="a", adapter_id="fake"))
    store.save(AutopilotRunState(run_id="r2", status="running", message="b", adapter_id="fake"))

    first = store.list_runs()
    assert len(first) == 2
    # Caller mutates the returned container (e.g. filters it down).
    first.clear()

    # The cache must be unaffected — a fresh list still sees both runs.
    second = store.list_runs()
    assert len(second) == 2
    # And the two returned lists are distinct objects.
    assert first is not second
