from __future__ import annotations

import tomllib
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_exposes_branded_mcp_entrypoints() -> None:
    project = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "aieng-workbench-mcp"
    assert project["scripts"]["aieng-workbench-mcp"] == "aieng_workbench_mcp.__main__:main"
    assert project["scripts"]["aieng-workbench-mcp-smoke"] == "aieng_workbench_mcp.smoke:main"

    dependencies = set(project["dependencies"])
    cad_extra = set(project["optional-dependencies"]["cad"])
    assert "aieng-format>=0.1.0a2" in dependencies
    assert "build123d>=0.10.0" not in dependencies
    assert "build123d>=0.10.0" in cad_extra


def test_python_module_entrypoint_uses_existing_mcp_server_main() -> None:
    from app.mcp_server import main as server_main
    from aieng_workbench_mcp.__main__ import main as branded_main

    assert branded_main is server_main


def test_cli_runtime_options_configure_headless_modes(monkeypatch, tmp_path: Path) -> None:
    from app import mcp_server as ms

    old_backend_url = ms._BACKEND_URL
    try:
        ms._apply_cli_runtime_options(
            backend_url="",
            approval_mode="block",
            data_dir=str(tmp_path),
            require_guides=False,
        )
        assert ms._BACKEND_URL == ""
        assert "AIENG_BACKEND_URL" not in ms.os.environ
        assert ms.os.environ["AIENG_MCP_BLOCK_APPROVAL_TOOLS"] == "1"
        assert "AIENG_MCP_MANAGED_APPROVAL" not in ms.os.environ
        assert ms.os.environ["AIENG_MCP_REQUIRE_GUIDES"] == "0"
        assert Path(ms.os.environ["AIENG_PLATFORM_DATA"]) == tmp_path.resolve()

        ms._apply_cli_runtime_options(
            backend_url="http://127.0.0.1:8000/",
            approval_mode="managed",
            data_dir=None,
            require_guides=True,
        )
        assert ms._BACKEND_URL == "http://127.0.0.1:8000"
        assert ms.os.environ["AIENG_BACKEND_URL"] == "http://127.0.0.1:8000"
        assert ms.os.environ["AIENG_MCP_MANAGED_APPROVAL"] == "1"
        assert "AIENG_MCP_BLOCK_APPROVAL_TOOLS" not in ms.os.environ
        assert ms.os.environ["AIENG_MCP_REQUIRE_GUIDES"] == "1"
    finally:
        ms._BACKEND_URL = old_backend_url


def test_packaged_mcp_smoke_stubbed_cad(tmp_path: Path) -> None:
    from aieng_workbench_mcp.smoke import run_smoke

    result = run_smoke(data_dir=tmp_path, real_cad=False)

    assert result["status"] == "ok"
    assert result["mode"] == "stubbed-cad"
    assert result["approval_block_code"] == "approval_blocked"
    assert "smoke_base_plate" in result["cad_named_parts"]
