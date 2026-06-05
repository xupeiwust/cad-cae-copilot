"""Discovery / capability routes: workbench capabilities, benchmark scenarios &
runs, and local-agent probing (`/api/capabilities`, `/api/benchmarks`,
`/api/local-agents`).

Extracted from ``app_factory.create_app`` (#9), verbatim. These are thin
delegators: capabilities/benchmarks call ``agent_workbench`` with
``active_settings``; the local-agent endpoints lazily import their probes (as in
the original) and need no create_app state.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException

from .. import agent_workbench


def register_discovery_routes(app: FastAPI, *, active_settings: Any) -> None:
    @app.get("/api/capabilities")
    def list_capabilities() -> list[dict[str, Any]]:
        return agent_workbench.list_capabilities(active_settings)

    @app.post("/api/capabilities/preview")
    def preview_capability(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return agent_workbench.preview_capability(active_settings, payload or {})

    @app.get("/api/benchmarks/scenarios")
    def list_benchmark_scenarios() -> list[dict[str, Any]]:
        return agent_workbench.list_benchmark_scenarios(active_settings)

    @app.post("/api/benchmarks/runs")
    def create_benchmark_run(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return agent_workbench.run_benchmark_from_payload(active_settings, payload or {})

    @app.get("/api/benchmarks/runs/{run_id}")
    def get_benchmark_run(run_id: str) -> dict[str, Any]:
        run = agent_workbench.get_benchmark_run(active_settings, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="benchmark run not found")
        return run

    @app.get("/api/local-agents/capabilities")
    def get_local_agent_capabilities() -> dict[str, Any]:
        from ..agent_autopilot.adapters import probe_local_agent_capabilities

        adapters = probe_local_agent_capabilities()
        return {
            "adapters": adapters,
            "available": [item for item in adapters if item.get("status") == "available"],
        }

    @app.get("/api/local-agents/preflight")
    def get_local_agent_preflight(adapter: str | None = None) -> dict[str, Any]:
        from ..agent_autopilot.local_agent_preflight import local_agent_preflight

        return local_agent_preflight(adapter=adapter)
