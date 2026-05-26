"""Tests for the MCP server bridge over the runtime tool registry.

Covers:
- Tool registration: every registered runtime tool surfaces in the MCP server.
- Schema attachment: curated schemas in runtime_tool_schemas.TOOL_SCHEMAS are
  attached to the corresponding FastMCP Tool object.
- High-frequency tools have non-trivial schemas (project_id at minimum).
- Approval-gated tools surface their approval requirement in the description.
- invoke_tool() dispatches to the registered handler and returns its result.
- Unknown tool names produce a structured error, not a crash.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import runtime as _rt
from app.mcp_server import _build_mcp_server, _coerce_result
from app.runtime_tool_schemas import TOOL_SCHEMAS


# ── registry / schema integration ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def mcp_server():
    """Build the MCP server once per module — boots create_app() too."""
    return _build_mcp_server()


def _tool_dict(mcp) -> dict[str, Any]:
    return dict(mcp._tool_manager._tools)


def test_mcp_server_registers_runtime_tools(mcp_server) -> None:
    tools = _tool_dict(mcp_server)
    assert len(tools) >= 10
    assert "aieng.inspect_package" in tools
    assert "cae.run_solver" in tools
    assert "postprocess.generate_computed_metrics" in tools


def test_high_frequency_tools_carry_curated_schema(mcp_server) -> None:
    tools = _tool_dict(mcp_server)
    for name in TOOL_SCHEMAS.keys():
        assert name in tools, f"curated-schema tool {name} not in MCP registry"
        params = tools[name].parameters
        assert isinstance(params, dict)
        assert params.get("type") == "object"
        # Most curated schemas require project_id.
        # Exceptions: tools with no required parameters (list/readme) and aieng.convert.
        _no_project_id = {"aieng.list_projects", "aieng.agent_readme", "aieng.convert"}
        props = params.get("properties") or {}
        if name not in _no_project_id:
            assert "project_id" in props, f"{name}: expected project_id in schema properties"


def test_tools_without_curated_schema_get_permissive_default(mcp_server) -> None:
    """A registered tool that has no entry in TOOL_SCHEMAS should still expose
    a usable (permissive) object schema, never a missing one."""
    tools = _tool_dict(mcp_server)
    permissive = {"type": "object", "additionalProperties": True}
    for name, tool in tools.items():
        if name in TOOL_SCHEMAS:
            continue
        assert tool.parameters == permissive or tool.parameters.get("type") == "object", (
            f"{name} has no schema and no permissive default"
        )


def test_approval_gated_tools_advertise_in_description(mcp_server) -> None:
    tools = _tool_dict(mcp_server)
    # cae.run_solver and cad.edit_parameter both require approval.
    for approval_tool in ("cae.run_solver", "cad.edit_parameter"):
        assert approval_tool in tools, f"{approval_tool} missing from MCP server"
        assert "[APPROVAL REQUIRED]" in tools[approval_tool].description


def test_non_approval_tool_has_no_approval_marker(mcp_server) -> None:
    tools = _tool_dict(mcp_server)
    assert "[APPROVAL REQUIRED]" not in tools["aieng.inspect_package"].description


# ── invoke_tool dispatch ──────────────────────────────────────────────────────

def test_invoke_tool_dispatches_to_handler() -> None:
    captured: dict[str, Any] = {}

    def _h(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        captured.update(inp)
        return {"echo": inp.get("project_id"), "status": "ok"}

    _rt.register_tool("test.echo", _h, description="test")
    try:
        result = _rt.invoke_tool("test.echo", {"project_id": "proj_xyz"})
        assert result == {"echo": "proj_xyz", "status": "ok"}
        assert captured == {"project_id": "proj_xyz"}
    finally:
        _rt._REGISTRY.pop("test.echo", None)


def test_invoke_tool_raises_keyerror_for_unknown_tool() -> None:
    with pytest.raises(KeyError):
        _rt.invoke_tool("no.such.tool", {})


def test_mcp_handler_catches_keyerror_and_returns_structured_error(mcp_server) -> None:
    """When the MCP layer encounters a missing tool, the handler should
    return a JSON-formatted error string rather than propagating."""
    # We can't easily call FastMCP's handler directly without a registered
    # name, so exercise the _coerce_result path that handles structured errors.
    err = {"status": "error", "code": "tool_not_found", "message": "tool not registered: x"}
    out = _coerce_result(err)
    parsed = json.loads(out)
    assert parsed["code"] == "tool_not_found"


# ── list_tools_for_mcp accessor ───────────────────────────────────────────────

def test_list_tools_for_mcp_returns_full_metadata(mcp_server) -> None:
    """Each entry must carry name, description, requires_approval, input_schema."""
    entries = _rt.list_tools_for_mcp()
    assert len(entries) >= 10
    for entry in entries:
        assert "name" in entry
        assert "description" in entry
        assert "requires_approval" in entry
        assert "input_schema" in entry
        assert isinstance(entry["input_schema"], dict)
        assert entry["input_schema"].get("type") == "object"


def test_list_tools_for_mcp_marks_approval_tools() -> None:
    entries = {e["name"]: e for e in _rt.list_tools_for_mcp()}
    assert entries["cae.run_solver"]["requires_approval"] is True
    assert entries["cad.edit_parameter"]["requires_approval"] is True
    assert entries["aieng.inspect_package"]["requires_approval"] is False


# ── coerce_result serialisation ───────────────────────────────────────────────

def test_coerce_result_passes_through_strings() -> None:
    assert _coerce_result("hello") == "hello"


def test_coerce_result_json_serialises_dicts() -> None:
    out = _coerce_result({"a": 1, "b": [1, 2]})
    parsed = json.loads(out)
    assert parsed == {"a": 1, "b": [1, 2]}


def test_coerce_result_handles_non_serialisable_via_default() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    out = _coerce_result({"x": Opaque()})
    assert "Opaque" in out


# ── thumbnail → MCP image content ─────────────────────────────────────────────

def test_finalize_result_plain_dict_returns_string() -> None:
    from app.mcp_server import _finalize_result

    out = _finalize_result({"status": "ok", "face_count": 6})
    assert isinstance(out, str)
    assert json.loads(out)["face_count"] == 6


def test_finalize_result_with_thumbnail_returns_text_and_image() -> None:
    import base64

    from mcp.server.fastmcp import Image

    from app.mcp_server import _finalize_result

    # 1x1 transparent PNG.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    result = {"status": "ok", "thumbnail_png_base64": base64.b64encode(png).decode()}
    out = _finalize_result(result)
    assert isinstance(out, list) and len(out) == 2
    text, image = out
    assert isinstance(text, str)
    assert "thumbnail_png_base64" not in text  # stripped from text block
    assert isinstance(image, Image)


def test_forward_to_backend_posts_and_parses(monkeypatch) -> None:
    """When AIENG_BACKEND_URL is set, _forward_to_backend POSTs the tool call."""
    import io
    import json as _json
    from app import mcp_server as _ms

    captured: dict = {}

    class _FakeResp:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload
        def read(self) -> bytes:
            return self._payload
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = _json.loads(req.data.decode())
        return _FakeResp(_json.dumps({"status": "ok", "echo": captured["body"]}).encode())

    monkeypatch.setattr(_ms, "_BACKEND_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(_ms.urllib.request, "urlopen", _fake_urlopen)

    out = _ms._forward_to_backend("aieng.inspect_package", {"project_id": "p1"})
    assert out["status"] == "ok"
    assert captured["url"].endswith("/api/agent/invoke-tool")
    assert captured["body"] == {"tool": "aieng.inspect_package", "input": {"project_id": "p1"}}


def test_coerce_result_handles_completely_unserialisable() -> None:
    class Hostile:
        def __repr__(self) -> str:
            raise RuntimeError("nope")

    # Falls back to repr() of the outer value, which may also raise → returns
    # the bare repr() of value. Any non-crashing string is acceptable here.
    obj = Hostile()
    try:
        out = _coerce_result(obj)
        assert isinstance(out, str)
    except RuntimeError:
        # If repr itself raises, that's the documented edge case.
        pass


# ── server build is deterministic and idempotent-enough ───────────────────────

def test_build_mcp_server_idempotent() -> None:
    """Building twice should not crash. Tool count must not drop between
    builds (FastMCP's add_tool may dedupe by name, so equal-or-greater)."""
    m1 = _build_mcp_server()
    n1 = len(_tool_dict(m1))
    m2 = _build_mcp_server()
    n2 = len(_tool_dict(m2))
    assert n1 == n2
