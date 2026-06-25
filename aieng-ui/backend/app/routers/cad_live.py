"""Live CAD generation, preview, activity-stream, and invoke-tool routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request

from ..legacy_app_symbols import sync_main_symbols
from ..logging_utils import log_exception

LOGGER = logging.getLogger("app.app_factory")


def _sync_main_symbols() -> None:
    sync_main_symbols(globals())


def register_cad_live_routes(
    app: FastAPI,
    *,
    active_settings: Any,
    app_context: Any,
) -> None:
    _sync_main_symbols()
    _resolve_api_key = app_context.resolve_api_key
    def _publish_project_live_change(
        *,
        project_id: str | None,
        source: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Notify browser clients that project metadata/artifacts may be stale."""
        if not project_id:
            return
        try:
            from .. import agent_activity

            status = result.get("status", "ok") if isinstance(result, dict) else "ok"
            preview_url = result.get("preview_url") if isinstance(result, dict) else None
            preview_format = result.get("preview_format") if isinstance(result, dict) else None
            agent_activity.publish({
                "type": "project_changed",
                "project_id": project_id,
                "source": source,
                "status": status,
                "preview_url": preview_url,
                "preview_format": preview_format,
            })
            if status == "ok" and preview_url:
                agent_activity.publish({
                    "type": "viewer_asset_changed",
                    "project_id": project_id,
                    "source": source,
                    "preview_url": preview_url,
                    "preview_format": preview_format,
                })
        except Exception:
            # Live UI sync must never make a successful backend write fail.
            log_exception(
                LOGGER,
                "Failed to publish project-changed activity update.",
                subsystem="app_factory.project_changed.publish",
                context={"project_id": project_id, "source": source, "status": status},
            )
            return

    def _agent_tool_failure_diagnostic(tool: str, result: dict[str, Any]) -> dict[str, Any]:
        """Normalize an invoke-tool failure for activity/timeline consumers."""
        raw_diagnostic = result.get("diagnostic")
        if isinstance(raw_diagnostic, dict):
            diagnostic = dict(raw_diagnostic)
        else:
            diagnostic = {}
        code = str(diagnostic.get("code") or result.get("code") or "tool_error")
        message = str(
            diagnostic.get("message")
            or result.get("message")
            or result.get("error")
            or f"{tool} failed."
        )
        remediation = diagnostic.get("remediation") or result.get("remediation")
        if not remediation:
            remediation = "Review the tool input and the returned error details before retrying."
        diagnostic.update({
            "code": code,
            "message": message,
            "remediation": str(remediation),
            "tool_name": str(diagnostic.get("tool_name") or tool),
        })
        return diagnostic

    def _agent_tool_failure_payload(tool: str, result: dict[str, Any]) -> dict[str, Any]:
        diagnostic = _agent_tool_failure_diagnostic(tool, result)
        return {
            "tool": tool,
            "error": diagnostic["message"],
            "code": diagnostic["code"],
            "message": diagnostic["message"],
            "remediation": diagnostic.get("remediation"),
            "diagnostic": diagnostic,
        }

    @app.post("/api/projects/{project_id}/generate-cad")
    def generate_cad_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Text-to-CAD: generate a 3D part from a natural-language description.

        Calls Claude to write build123d Python code, executes it in a
        subprocess, extracts topology and feature semantics, and writes
        geometry/generated.step, geometry/topology_map.json,
        graph/feature_graph.json, and geometry/source.py into the package.

        Body:
          description (str, required): natural-language part description.
          hints (dict, optional): {material?, dimensions_mm?, style?, symmetry?}
          write_files (bool, optional): write artifacts to package (default true).
          timeout (int, optional): subprocess timeout in seconds (default 60).
        """
        from .. import cad_generation

        data = payload or {}
        resolved_key = _resolve_api_key(data)
        if resolved_key:
            data = {**data, "api_key": resolved_key}
        if isinstance(data.get("llm_config"), dict):
            data = {**data, "llm_config": agent_engine.sanitize_llm_config(data.get("llm_config"))}
        result = cad_generation.run_cad_generation(
            active_settings, project_id, data
        )
        _publish_project_live_change(project_id=project_id, source="generate-cad", result=result)
        return result

    @app.post("/api/projects/{project_id}/generate-cad-stream")
    def generate_cad_stream_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ):
        """Text-to-CAD with streaming SSE progress events.

        Yields server-sent events: planning → coding → building → retrying →
        writing → done (with full result) | error.
        Body same as /generate-cad.
        """
        from fastapi.responses import StreamingResponse
        from .. import cad_generation

        data = payload or {}
        resolved_key = _resolve_api_key(data)
        if resolved_key:
            data = {**data, "api_key": resolved_key}
        if isinstance(data.get("llm_config"), dict):
            data = {**data, "llm_config": agent_engine.sanitize_llm_config(data.get("llm_config"))}

        def generate():
            yield from cad_generation.run_cad_generation_stream(
                active_settings, project_id, data
            )

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/projects/{project_id}/cad-preview")
    def get_cad_preview(project_id: str):
        """Stream GLB (preferred) or STL preview from the project's .aieng package."""
        from fastapi.responses import Response
        from .. import cad_generation

        content, fmt = cad_generation.serve_cad_preview(active_settings, project_id)
        media_type = "model/gltf-binary" if fmt == "glb" else "model/stl"
        return Response(content=content, media_type=media_type)

    # ── live agent activity (Phase 2: external agents drive the workbench) ────

    @app.get("/api/agent-activity/stream")
    async def agent_activity_stream(request: Request):
        """SSE stream of live agent activity for the React UI to subscribe to.

        When an external agent (Claude Code/Codex/Copilot) forwards a tool call
        through /api/agent/invoke-tool, the resulting activity events are fanned
        out here so the UI can render them live (e.g. the CAD build animation).
        """
        import asyncio as _asyncio
        import json as _json
        import queue as _queue
        from fastapi.responses import StreamingResponse
        from .. import agent_activity

        async def gen():
            q = agent_activity.subscribe()
            try:
                yield f"data: {_json.dumps({'type': 'connected'})}\n\n"
                last_keepalive = 0.0
                while True:
                    if await request.is_disconnected():
                        break

                    emitted = False
                    try:
                        event = q.get_nowait()
                        emitted = True
                        yield f"data: {_json.dumps(event)}\n\n"
                    except _queue.Empty:
                        pass

                    now = _asyncio.get_running_loop().time()
                    if not emitted and now - last_keepalive >= 15:
                        # SSE comment keeps the connection alive through proxies.
                        last_keepalive = now
                        yield ": keepalive\n\n"

                    await _asyncio.sleep(0.25)
            except _asyncio.CancelledError:
                raise
            finally:
                agent_activity.unsubscribe(q)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/agent/invoke-tool")
    def agent_invoke_tool(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        """Run a runtime tool on behalf of an external agent and publish activity.

        This is the bridge endpoint the MCP server forwards to when
        AIENG_BACKEND_URL is configured, so that the single backend process
        owns all state mutations AND emits the live UI events.

        Body: { "tool": "<tool.name>", "input": { ... } }
        """
        import time as _time
        from .. import agent_activity

        data = payload or {}
        tool = str(data.get("tool") or "").strip()
        inp = data.get("input") if isinstance(data.get("input"), dict) else {}
        if not tool:
            return {"status": "error", "code": "missing_tool", "message": "tool is required."}

        project_id = inp.get("project_id")
        call_id = f"call_{int(_time.time() * 1000)}"
        agent_activity.publish({
            "type": "tool_started",
            "call_id": call_id,
            "tool": tool,
            "project_id": project_id,
            # Surface the agent-written build123d code so the UI can show it live.
            "code_preview": (str(inp.get("code"))[:2000] if tool == "cad.execute_build123d" and inp.get("code") else None),
        })

        try:
            if tool == "cad.execute_build123d":
                from .. import cad_generation

                def _on_progress(evt: dict[str, Any]) -> None:
                    agent_activity.publish({
                        "type": "cad_build_progress",
                        "call_id": call_id,
                        "project_id": project_id,
                        **evt,
                    })

                if not project_id:
                    result = {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
                else:
                    result = cad_generation.execute_build123d_code(
                        active_settings, project_id, inp, on_progress=_on_progress
                    )
            else:
                result = _rt.invoke_tool(tool, inp)
                if not isinstance(result, dict):
                    result = {"status": "ok", "result": result}
        except KeyError:
            result = {"status": "error", "code": "tool_not_found", "message": f"tool not registered: {tool}"}
        except Exception as exc:  # noqa: BLE001
            result = {"status": "error", "code": "tool_exception", "message": f"{type(exc).__name__}: {exc}"}

        status = result.get("status", "ok") if isinstance(result, dict) else "ok"
        preview_url = result.get("preview_url") if isinstance(result, dict) else None
        preview_format = result.get("preview_format") if isinstance(result, dict) else None
        agent_activity.publish({
            "type": "tool_completed",
            "call_id": call_id,
            "tool": tool,
            "project_id": project_id,
            "status": status,
            "preview_url": preview_url,
            "preview_format": preview_format,
            "topology_summary": result.get("topology_summary") if isinstance(result, dict) else None,
            "message": result.get("message") if isinstance(result, dict) else None,
        })
        if isinstance(result, dict) and status == "error":
            agent_activity.publish({
                "type": "tool_failed",
                "call_id": call_id,
                "project_id": project_id,
                **_agent_tool_failure_payload(tool, result),
            })
        project_change_tools = {
            "cad.execute_build123d",
            "cad.refine",
            "cad.edit_parameter",
            "cad.set_reference_image",
            "aieng.convert",
            "aieng.generate_preview",
            "aieng.refresh_semantics",
            "aieng.update_validation_status",
            "aieng.write_completeness_report",
            "aieng.write_evidence_scaffold",
            "cae.apply_setup_patch",
            "cae.generate_solver_input",
            "cae.write_mesh_handoff",
            "cae.import_solver_evidence",
            "cae.extract_solver_results",
            "cae.extract_field_regions",
            "postprocess.generate_computed_metrics",
            "postprocess.refresh_cae_summary",
        }
        if project_id and status == "ok" and (preview_url or tool in project_change_tools):
            agent_activity.publish({
                "type": "project_changed",
                "call_id": call_id,
                "tool": tool,
                "project_id": project_id,
                "source": "agent.invoke_tool",
                "status": status,
                "preview_url": preview_url,
                "preview_format": preview_format,
            })
            if preview_url:
                agent_activity.publish({
                    "type": "viewer_asset_changed",
                    "call_id": call_id,
                    "tool": tool,
                    "project_id": project_id,
                    "source": "agent.invoke_tool",
                    "preview_url": preview_url,
                    "preview_format": preview_format,
                })
        return result

    @app.post("/api/projects/{project_id}/refine-cad")
    def refine_cad_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Iterative CAD refinement based on natural-language engineer feedback.

        Reads geometry/source.py from the package, sends existing code + feedback
        to Claude, re-executes, and updates all CAD artifacts.

        Body:
          feedback (str, required): what to change, e.g. "make it 20mm longer".
          write_files (bool, optional): write back to package (default true).
          timeout (int, optional): subprocess timeout in seconds (default 60).
        """
        from .. import cad_generation

        data = payload or {}
        resolved_key = _resolve_api_key(data)
        if resolved_key:
            data = {**data, "api_key": resolved_key}
        if isinstance(data.get("llm_config"), dict):
            data = {**data, "llm_config": agent_engine.sanitize_llm_config(data.get("llm_config"))}
        result = cad_generation.refine_cad_generation(
            active_settings, project_id, data
        )
        _publish_project_live_change(project_id=project_id, source="refine-cad", result=result)
        return result

    @app.get("/api/projects/{project_id}/health-check")
    def get_project_health_check(project_id: str) -> dict[str, Any]:
        """Read-only health check for a project's readiness for Copilot Loop.

        Does not mutate the package, run solvers, or advance claims.
        """
        from .. import project_health

        return project_health.run_project_health_check(active_settings, project_id)
