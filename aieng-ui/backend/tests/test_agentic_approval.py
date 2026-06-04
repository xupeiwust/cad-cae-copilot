"""Phase 2 coverage for the agentic-session approval bridge (Approach A).

Pure-logic tests + an API roundtrip through the permission endpoints. No live
agent or MCP subprocess required. See
``aieng-ui/docs/web-chat-agentic-parity-plan.md``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_autopilot.agentic_approval import (
    PermissionBroker,
    build_approval_name_set,
    format_decision,
    requires_approval,
    resolve_registry_name,
    strip_mcp_prefix,
)
from app.main import Settings, create_app


TOOL_DEFS = [
    {"name": "cad.execute_build123d", "requires_approval": True},
    {"name": "cae.run_solver", "requires_approval": True},
    {"name": "cad.get_source", "requires_approval": False},
    {"name": "aieng.list_projects"},  # missing flag → not gated
]


# --- name normalization ---------------------------------------------------

def test_strip_mcp_prefix_workbench_and_generic():
    assert strip_mcp_prefix("mcp__aieng-workbench__cad_execute_build123d") == "cad_execute_build123d"
    assert strip_mcp_prefix("mcp__other-server__do_thing") == "do_thing"
    assert strip_mcp_prefix("cad_execute_build123d") == "cad_execute_build123d"


# --- gated classification (single source: registry requires_approval) -----

def test_gated_set_covers_both_forms():
    names = build_approval_name_set(TOOL_DEFS)
    assert "cad.execute_build123d" in names
    assert "cad_execute_build123d" in names
    assert "cae.run_solver" in names and "cae_run_solver" in names
    assert "cad.get_source" not in names


def test_requires_approval_matches_all_presentations():
    names = build_approval_name_set(TOOL_DEFS)
    assert requires_approval("cad.execute_build123d", names)
    assert requires_approval("cad_execute_build123d", names)
    assert requires_approval("mcp__aieng-workbench__cad_execute_build123d", names)
    # non-gated / unknown must not require approval
    assert not requires_approval("cad.get_source", names)
    assert not requires_approval("aieng.list_projects", names)
    assert not requires_approval("totally_unknown_tool", names)


def test_resolve_registry_name_returns_dotted():
    assert resolve_registry_name("cad_execute_build123d", TOOL_DEFS) == "cad.execute_build123d"
    assert resolve_registry_name("mcp__aieng-workbench__cae_run_solver", TOOL_DEFS) == "cae.run_solver"


# --- decision contract ----------------------------------------------------

def test_format_decision_allow_and_deny():
    allow = format_decision(allowed=True, tool_input={"a": 1})
    assert allow == {"behavior": "allow", "updatedInput": {"a": 1}}
    deny = format_decision(allowed=False, message="nope")
    assert deny == {"behavior": "deny", "message": "nope"}


# --- broker rendezvous ----------------------------------------------------

def test_broker_create_resolve_allow():
    broker = PermissionBroker()
    entry = broker.create(run_id="r1", tool_name="cad.execute_build123d", tool_input={"code": "x"})
    assert broker.get(entry.permission_id).status == "pending"
    broker.resolve(entry.permission_id, approved=True)
    decision = broker.decision_for(broker.get(entry.permission_id))
    assert decision["behavior"] == "allow"
    assert decision["updatedInput"] == {"code": "x"}


def test_broker_resolve_deny_with_message():
    broker = PermissionBroker()
    entry = broker.create(run_id=None, tool_name="cae.run_solver", tool_input={})
    broker.resolve(entry.permission_id, approved=False, message="not now")
    decision = broker.decision_for(broker.get(entry.permission_id))
    assert decision == {"behavior": "deny", "message": "not now"}


def test_broker_resolve_unknown_returns_none():
    broker = PermissionBroker()
    assert broker.resolve("nope", approved=True) is None


def test_broker_wait_returns_immediately_when_already_resolved():
    broker = PermissionBroker()
    entry = broker.create(run_id=None, tool_name="cae.run_solver", tool_input={})
    broker.resolve(entry.permission_id, approved=True)
    # Already resolved → wait should not block even with a large timeout.
    got = broker.wait(entry.permission_id, timeout=30)
    assert got is not None and got.status == "allowed"


def test_broker_wait_unblocks_on_resolve_from_another_thread():
    import threading as _t
    import time as _time
    broker = PermissionBroker()
    entry = broker.create(run_id=None, tool_name="cad.execute_build123d", tool_input={})

    def _resolve_soon():
        _time.sleep(0.05)
        broker.resolve(entry.permission_id, approved=False, message="no")

    _t.Thread(target=_resolve_soon).start()
    got = broker.wait(entry.permission_id, timeout=5)
    assert got is not None and got.status == "denied"


def test_broker_updated_input_overrides():
    broker = PermissionBroker()
    entry = broker.create(run_id=None, tool_name="cad.edit_parameter", tool_input={"v": 1})
    broker.resolve(entry.permission_id, approved=True, updated_input={"v": 2})
    assert broker.decision_for(broker.get(entry.permission_id))["updatedInput"] == {"v": 2}


# --- API roundtrip --------------------------------------------------------

def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )
    return TestClient(create_app(settings))


def test_api_non_gated_tool_auto_allows(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.post("/api/agent/agentic/permission", json={"tool_name": "cad.get_source", "input": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["decision"]["behavior"] == "allow"


def test_api_gated_tool_pending_then_approve(tmp_path: Path):
    client = _client(tmp_path)
    created = client.post(
        "/api/agent/agentic/permission",
        json={"tool_name": "cad.execute_build123d", "input": {"code": "result = Box(1,1,1)"}, "run_id": "r1"},
    ).json()
    assert created["status"] == "pending"
    pid = created["permission_id"]
    # poll before resolution → still pending
    assert client.get(f"/api/agent/agentic/permission/{pid}").json()["status"] == "pending"
    # user approves
    resolved = client.post(f"/api/agent/agentic/permission/{pid}/resolve", json={"approved": True}).json()
    assert resolved["approved"] is True
    assert resolved["decision"]["behavior"] == "allow"
    # subsequent poll returns the resolved decision
    polled = client.get(f"/api/agent/agentic/permission/{pid}").json()
    assert polled["status"] == "resolved" and polled["decision"]["behavior"] == "allow"


def test_api_gated_tool_deny(tmp_path: Path):
    client = _client(tmp_path)
    pid = client.post(
        "/api/agent/agentic/permission",
        json={"tool_name": "cae.run_solver", "input": {}, "run_id": "r2"},
    ).json()["permission_id"]
    resolved = client.post(
        f"/api/agent/agentic/permission/{pid}/resolve",
        json={"approved": False, "message": "review first"},
    ).json()
    assert resolved["decision"] == {"behavior": "deny", "message": "review first"}


def test_api_unknown_permission_id_404(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/api/agent/agentic/permission/nope").status_code == 404
    assert client.post("/api/agent/agentic/permission/nope/resolve", json={"approved": True}).status_code == 404
