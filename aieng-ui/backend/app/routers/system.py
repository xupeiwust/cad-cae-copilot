"""System / infrastructure routes: health, environment, runtime status,
error metrics, and runtime-config read/write/test.

Extracted from ``app_factory.create_app`` (#9). Behavior is unchanged: the
handlers are the same closures, moved verbatim. ``runtime_status`` /
``runtime_config_snapshot`` / ``persist_runtime_config`` are resolved through the
``app.main`` module at request time so existing monkeypatch points keep working.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from fastapi import Body, FastAPI

from ..config import APP_ROOT
from ..logging_utils import error_metrics_snapshot
from .. import runtime as _rt


def register_system_routes(
    app: FastAPI,
    *,
    active_settings: Any,
    server_started_at: str,
) -> None:
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        tool_names = _rt.registered_tool_names()
        cad_tool_names = [name for name in tool_names if name.startswith("cad.")]
        return {
            "status": "ok",
            "pid": os.getpid(),
            "started_at": server_started_at,
            "python_executable": sys.executable,
            "app_root": str(APP_ROOT),
            "runtime_tool_count": len(tool_names),
            "cad_tool_count": len(cad_tool_names),
            # Content hash of the registered tool set: lets an operator detect a
            # long-lived MCP server serving a stale registry (#29).
            "registry_hash": _rt.registry_identity()["registry_hash"],
            "backend_log_path": app.state.backend_log_path,
            "error_metrics": error_metrics_snapshot(limit=20),
        }

    @app.get("/api/environment")
    def environment() -> dict[str, Any]:
        """Return environment topology so agents can discover ports, paths, and formats."""
        tool_names = _rt.registered_tool_names()
        cad_tool_names = [name for name in tool_names if name.startswith("cad.")]
        cae_tool_names = [name for name in tool_names if name.startswith("cae.")]
        return {
            "ui_url": "http://localhost:5173",
            "api_url": "http://localhost:8000",
            "data_root": str(active_settings.data_root),
            "projects_root": str(active_settings.projects_root),
            "aieng_root": str(active_settings.aieng_root),
            "app_root": str(APP_ROOT),
            "platform_root": str(active_settings.platform_root),
            "conda_env": "aieng311",
            "python_executable": sys.executable,
            "supported_preview_formats": ["glb", "stl"],
            "cad_tool_count": len(cad_tool_names),
            "cae_tool_count": len(cae_tool_names),
            "total_tool_count": len(tool_names),
            "sample_tools": tool_names[:10],
        }

    @app.get("/api/runtime")
    def runtime() -> dict[str, Any]:
        from .. import main as _main  # noqa: PLC0415 — request-time for monkeypatch compat

        return _main.runtime_status(active_settings)

    @app.get("/api/diagnostics/error-metrics")
    def get_error_metrics() -> dict[str, Any]:
        return {
            "backend_log_path": app.state.backend_log_path,
            **error_metrics_snapshot(),
        }

    @app.get("/api/runtime-config")
    def get_runtime_config() -> dict[str, Any]:
        from .. import main as _main  # noqa: PLC0415

        return _main.runtime_config_snapshot(active_settings)

    @app.put("/api/runtime-config")
    def update_runtime_config(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        from .. import main as _main  # noqa: PLC0415

        return _main.persist_runtime_config(active_settings, payload or {})

    @app.post("/api/runtime-config/test")
    def test_runtime_config(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        from .. import main as _main  # noqa: PLC0415

        return _main.runtime_config_snapshot(active_settings, payload or {})
