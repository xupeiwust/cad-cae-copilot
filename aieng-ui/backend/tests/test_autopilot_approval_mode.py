"""Regression: session approval_mode must survive autopilot run lifecycle rebuilds.

Bug B-3 (audit): `continue` / `reply` / `follow-up` rebuilt the AutopilotEngine
without passing `approval_mode`, so a `strict`/`manual` session silently fell back
to the engine default (`balanced`) after the first approval/reply — letting tools
that should have been gated auto-run. These tests capture the `approval_mode` each
rebuild path hands to the engine and assert it matches the session.
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent_autopilot import engine as engine_module
from app.main import Settings, create_app, default_project, save_project


def _make_runtime_settings(tmp_path: Path) -> Settings:
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )


def _wait_for_status(
    client: TestClient,
    run_id: str,
    statuses: set[str],
    timeout_s: float = 5.0,
) -> dict:
    deadline = time.time() + timeout_s
    last: dict | None = None
    while time.time() < deadline:
        resp = client.get(f"/api/agent/autopilot/runs/{run_id}")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}; last={last}")


@pytest.mark.parametrize("approval_mode", ["strict", "manual"])
def test_run_lifecycle_endpoints_preserve_session_approval_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    approval_mode: str,
) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("approval-mode"))
    client = TestClient(create_app(settings))

    # 1. Session configured with a non-default approval mode.
    session_id = client.post(
        f"/api/projects/{project['id']}/chat-sessions", json={"title": "Gate"}
    ).json()["id"]
    patched = client.patch(
        f"/api/projects/{project['id']}/chat-sessions/{session_id}",
        json={"approval_mode": approval_mode},
    )
    assert patched.status_code == 200
    assert patched.json()["approval_mode"] == approval_mode

    # 2. Create a run that parks in a non-terminal state (ask_user -> blocked),
    #    so the continue/reply guards (which only early-return on terminal status)
    #    actually proceed to rebuild the engine. Uses the fake adapter — no CAD/LLM.
    run_resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "inspect the active project",
            "project_id": project["id"],
            "session_id": session_id,
            "adapter_id": "fake",
            "fake_actions": [
                {"action": {"type": "ask_user", "question": "Which face?"}, "done": False}
            ],
        },
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]
    _wait_for_status(client, run_id, {"blocked"})

    # Sanity: run creation must not have clobbered the session approval mode.
    sessions = client.get(f"/api/projects/{project['id']}/chat-sessions").json()
    this_session = next(s for s in sessions if s["id"] == session_id)
    assert this_session["approval_mode"] == approval_mode

    # 3. Replace the engine with a capturing stub so every rebuild records the
    #    approval_mode it received. The endpoints `from ... import AutopilotEngine`
    #    inside their bodies, so patching the module attribute is picked up.
    captured: list[str | None] = []
    real_store_load = None

    class CapturingEngine:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs.get("approval_mode"))  # type: ignore[arg-type]
            self._store = kwargs.get("store")

        def _state(self, run_id: str) -> object:
            # Return a real persisted run state so the endpoints' post-call
            # handling (audit write / model_dump) works unchanged.
            return self._store.load(run_id)  # type: ignore[union-attr]

        def continue_run(self, run_id: str, approved: bool = True, user_message: object = None) -> object:
            return self._state(run_id)

        def reply_to_run(self, run_id: str, message: str, **_: object) -> object:
            return self._state(run_id)

        def follow_up_run(self, run_id: str, message: str, **_: object) -> object:
            return self._state(run_id)

    monkeypatch.setattr(engine_module, "AutopilotEngine", CapturingEngine)

    # 4a. continue path
    captured.clear()
    cont = client.post(
        f"/api/agent/autopilot/runs/{run_id}/continue", json={"approved": True}
    )
    assert cont.status_code == 200
    assert captured == [approval_mode], f"continue rebuilt engine with {captured!r}"

    # 4b. reply path
    captured.clear()
    rep = client.post(
        f"/api/agent/autopilot/runs/{run_id}/reply", json={"message": "the top face"}
    )
    assert rep.status_code == 200
    assert captured == [approval_mode], f"reply rebuilt engine with {captured!r}"

    # 4c. follow-up path (runs synchronously, returns the run state)
    captured.clear()
    fup = client.post(
        f"/api/agent/autopilot/runs/{run_id}/follow-up", json={"message": "also add a rib"}
    )
    assert fup.status_code == 200
    assert captured == [approval_mode], f"follow-up rebuilt engine with {captured!r}"
