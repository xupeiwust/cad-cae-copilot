from pathlib import Path

import pytest

from app.agent_autopilot.schema import AutopilotRunState
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


def test_store_reports_corrupt_run_file(tmp_path: Path) -> None:
    store = AutopilotStore(tmp_path / "runs")
    (tmp_path / "runs" / "bad.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError):
        store.load("bad")
