"""Backend command routing v1 — /critique only.

When a run carries composer_intent.command == "critique", the engine:
  * injects a read-only critique/inspection instruction into the run context,
  * suppresses the geometry-mutation guard (so a final is allowed even if the
    free text contains words like "add"), and
  * still accepts read-only tool calls such as cad.critique.

Other commands and plain natural language are unchanged: the mutation guard
still fires for create/modify intent. Uses the deterministic fake adapter — no
real Claude/Codex/LLM and no CAD execution required for the routing assertions.
"""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent_autopilot.engine import (
    CRITIQUE_COMMAND_INSTRUCTION,
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    command_intent_label,
    get_composer_command,
    is_critique_command,
)
from app.main import Settings, create_app, default_project, save_project


def _make_runtime_settings(tmp_path: Path) -> Settings:
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )


def _wait_for_status(client: TestClient, run_id: str, statuses: set[str], timeout_s: float = 6.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict | None = None
    while time.time() < deadline:
        resp = client.get(f"/api/agent/autopilot/runs/{run_id}")
        if resp.status_code == 200:  # tolerate transient mid-write reads
            last = resp.json()
            if last.get("status") in statuses:
                return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}; last={last}")


def _summaries(run: dict) -> list[str]:
    return [str(o.get("summary", "")) for o in run.get("observations", [])]


_CRITIQUE_INTENT = {
    "command": "critique",
    "commandRaw": "/critique",
    "text": "check if I should add ribs",
    "mentions": [],
    "errors": [],
}


def test_composer_command_helpers() -> None:
    crit = SimpleNamespace(composer_intent={"command": "critique"})
    assert get_composer_command(crit) == "critique"
    assert is_critique_command(crit) is True
    assert command_intent_label(crit) == "critique_geometry"

    mod = SimpleNamespace(composer_intent={"command": "modify"})
    assert get_composer_command(mod) == "modify"
    assert is_critique_command(mod) is False
    assert command_intent_label(mod) is None  # not routed in v1

    # Robust to missing / malformed metadata.
    assert get_composer_command(SimpleNamespace(composer_intent=None)) is None
    assert get_composer_command(SimpleNamespace(composer_intent="oops")) is None
    assert get_composer_command(SimpleNamespace(composer_intent={})) is None
    assert get_composer_command(SimpleNamespace()) is None


def test_critique_run_is_read_only_and_completes(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("critique-route"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            # Note: text contains "add" — the mutation guard would normally trip,
            # but /critique is read-only so the final must still be allowed.
            "message": "/critique check if I should add ribs",
            "project_id": project["id"],
            "adapter_id": "fake",
            "composer_intent": _CRITIQUE_INTENT,
            "fake_actions": [
                {"action": {"type": "final", "message": "No manufacturability issues found."}, "done": True}
            ],
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    final = _wait_for_status(client, run_id, {"completed", "failed"})
    assert final["status"] == "completed"  # final allowed despite "add" in text
    assert final["composer_intent"]["command"] == "critique"

    summaries = _summaries(final)
    # Criterion 1: prompt/context carries the read-only critique instruction.
    assert any(CRITIQUE_COMMAND_INSTRUCTION in s for s in summaries)
    # Criterion 3: the geometry mutation guard was NOT triggered.
    assert not any(GEOMETRY_MUTATION_REPAIR_INSTRUCTION in s for s in summaries)


def test_critique_accepts_cad_critique_tool(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("critique-tool"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "/critique review manufacturability",
            "project_id": project["id"],
            "adapter_id": "fake",
            "composer_intent": {**_CRITIQUE_INTENT, "text": "review manufacturability"},
            "fake_actions": [
                {"action": {"type": "tool_call", "tool_name": "cad.critique", "input": {"project_id": project["id"]}}, "done": False},
                {"action": {"type": "final", "message": "Critique complete."}, "done": True},
            ],
        },
    )
    assert resp.status_code == 200
    final = _wait_for_status(client, resp.json()["run_id"], {"completed", "failed"})
    assert final["status"] == "completed"
    # The read-only cad.critique tool action was accepted and recorded as a step.
    tool_names = [s.get("action", {}).get("action", {}).get("tool_name") for s in final.get("steps", [])]
    assert "cad.critique" in tool_names


@pytest.mark.parametrize(
    "composer_intent",
    [None, {"command": "modify", "commandRaw": "/modify", "text": "add rotor guards", "mentions": [], "errors": []}],
    ids=["natural_language", "modify_command"],
)
def test_mutation_guard_still_fires_for_non_critique(tmp_path: Path, composer_intent: dict | None) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("guard-intact"))
    client = TestClient(create_app(settings))

    body = {
        "message": "add rotor guards",
        "project_id": project["id"],
        "adapter_id": "fake",
        "max_steps": 3,  # bound the loop; the final keeps getting rejected
        "fake_actions": [{"action": {"type": "final", "message": "done"}, "done": True}],
    }
    if composer_intent is not None:
        body["composer_intent"] = composer_intent

    resp = client.post("/api/agent/autopilot/runs", json=body)
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    # The mutation guard must reject the premature final at least once — proving
    # /modify and plain natural language are unchanged (guard not removed).
    deadline = time.time() + 6.0
    guarded = False
    while time.time() < deadline:
        run = client.get(f"/api/agent/autopilot/runs/{run_id}").json()
        if any(GEOMETRY_MUTATION_REPAIR_INSTRUCTION in s for s in _summaries(run)):
            guarded = True
            break
        time.sleep(0.05)
    assert guarded, "expected the geometry mutation guard to fire for non-critique intent"
