"""Tests for the agent setup doctor (#229)."""

import json

from app.mcp_doctor import format_report, run_doctor


def _ok_health(_url: str) -> dict:
    return {"status": "ok", "runtime_tool_count": 74, "cad_tool_count": 11}


def _boom(_url: str):
    raise ConnectionError("connection refused")


def test_all_green(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"aieng-workbench": {"command": "aieng-workbench-mcp"}}}),
        encoding="utf-8",
    )
    report = run_doctor(root=tmp_path, backend_url="http://127.0.0.1:8000", tool_count=74, http_get=_ok_health)
    assert report["overall"] == "ok"
    names = {c["name"]: c["status"] for c in report["checks"]}
    assert names == {"mcp_config": "ok", "backend": "ok", "tools": "ok"}


def test_missing_mcp_config_warns_with_fix(tmp_path) -> None:
    report = run_doctor(root=tmp_path, backend_url=None, tool_count=74, http_get=_ok_health)
    cfg = next(c for c in report["checks"] if c["name"] == "mcp_config")
    assert cfg["status"] == "warn"
    assert cfg["fix"] and ".mcp.json" in cfg["fix"]
    # no backend configured → skipped, not fail
    backend = next(c for c in report["checks"] if c["name"] == "backend")
    assert backend["status"] == "skipped"
    # overall is warn (a warn, no fail)
    assert report["overall"] == "warn"


def test_unreachable_backend_fails_with_fix(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text("aieng-workbench", encoding="utf-8")
    report = run_doctor(root=tmp_path, backend_url="http://127.0.0.1:8000", tool_count=74, http_get=_boom)
    backend = next(c for c in report["checks"] if c["name"] == "backend")
    assert backend["status"] == "fail"
    assert "uvicorn" in backend["fix"]
    assert report["overall"] == "fail"


def test_zero_tools_fails(tmp_path) -> None:
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "mcp.json").write_text("aieng-workbench", encoding="utf-8")
    report = run_doctor(root=tmp_path, backend_url=None, tool_count=0, http_get=_ok_health)
    tools = next(c for c in report["checks"] if c["name"] == "tools")
    assert tools["status"] == "fail"
    assert report["overall"] == "fail"


def test_detects_config_in_vscode_and_cursor(tmp_path) -> None:
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "mcp.json").write_text('{"aieng-workbench": {}}', encoding="utf-8")
    report = run_doctor(root=tmp_path, backend_url=None, tool_count=5, http_get=_ok_health)
    cfg = next(c for c in report["checks"] if c["name"] == "mcp_config")
    assert cfg["status"] == "ok"
    assert ".cursor/mcp.json" in cfg["detail"]


def test_format_report_is_ascii_and_includes_fixes(tmp_path) -> None:
    report = run_doctor(root=tmp_path, backend_url="http://x", tool_count=0, http_get=_boom)
    text = format_report(report)
    assert "aieng-workbench doctor: FAIL" in text
    assert "[FAIL]" in text
    assert "-> fix:" in text
    assert "backend" in text and "tools" in text
    # must be printable on a cp1252 (Windows) console — no unicode glyphs
    text.encode("cp1252")
