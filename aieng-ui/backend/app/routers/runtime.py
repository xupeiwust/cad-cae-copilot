"""Runtime tool/capability introspection and runtime-run lifecycle routes
(`/api/runtime/tools`, `/api/runtime/capabilities`, `/api/runtime/runs*`).

Extracted from ``app_factory.create_app`` (#9), verbatim. Helpers are imported
from their real source modules; the ``runtime`` and ``agent_workbench`` modules
are imported as modules (not their attributes) so test monkeypatches on them keep
applying. ``active_settings`` is passed in from create_app.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from .. import agent_workbench
from .. import runtime as _rt
from ..config import now_iso
from ..logging_utils import log_exception
from ..project_io import _CAE_RESULT_FIELDS, _TOOL_CAPABILITY_PROFILE, write_audit_log
from ..runtime_tool_registry import _resolve_ccx_cmd

LOGGER = logging.getLogger(__name__)


def register_runtime_routes(app: FastAPI, *, active_settings: Any) -> None:
    @app.get("/api/runtime/workflows")
    def list_runtime_workflows() -> list[dict[str, Any]]:
        return agent_workbench.list_workflows()

    @app.get("/api/runtime/tools")
    def list_runtime_tools() -> list[dict[str, Any]]:
        return _rt.registered_tools_info()

    @app.get("/api/runtime/capabilities")
    def get_runtime_capabilities() -> dict[str, Any]:
        """Machine-readable runtime capability profile.

        Distinguishes implemented capabilities from environment availability.
        Read-only. Does not execute tools or advance claims.
        """
        ccx_available: bool = _resolve_ccx_cmd() is not None
        registered: set[str] = set(_rt.registered_tool_names())
        tool_metadata = _rt.list_tools_for_mcp()

        tool_caps: list[dict[str, Any]] = []
        for _entry in _TOOL_CAPABILITY_PROFILE:
            _cap = dict(_entry)
            _binary = _cap.get("external_binary")
            if _binary == "ccx":
                _cap["available"] = ccx_available
            else:
                _cap["available"] = True
            # Cross-check implemented flag against the live tool registry
            _cap["registered"] = _cap["name"] in registered
            tool_caps.append(_cap)

        return {
            "schema_version": "0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "ccx_available": ccx_available,
            },
            "tools": tool_caps,
            "result_fields": {
                "supported": list(_CAE_RESULT_FIELDS.keys()),
                "produces_evidence": False,
                "advances_claims": False,
            },
            "local_execution_boundary": {
                "backend_requires_api_key": False,
                "project_data_local": True,
                "data_root": str(active_settings.data_root),
                "projects_root": str(active_settings.projects_root),
                "external_model_provider": "BYO MCP client or runtime-configured provider",
                "external_model_calls_may_occur_outside_backend": True,
                "managed_approval_enabled": os.environ.get("AIENG_MCP_MANAGED_APPROVAL") == "1",
                "approval_gated_tools": sorted(
                    entry["name"]
                    for entry in tool_metadata
                    if entry.get("requires_approval") is True
                ),
                "cad_execution": {
                    "runs_in_subprocess": True,
                    "wall_clock_timeout": True,
                    "posix_resource_limits_available": os.name == "posix",
                    "full_untrusted_code_sandbox": False,
                },
                "secret_redaction": {
                    "backend_logs": True,
                    "common_secret_keys": [
                        "api_key",
                        "token",
                        "secret",
                        "password",
                        "authorization",
                        "bearer",
                    ],
                },
                "docs": ["docs/cad_execution_boundary.md"],
            },
            "claim_policy": {
                "automatic_claim_advancement": False,
                "claim_advancement_requires_explicit_workflow": True,
            },
        }

    @app.get("/api/runtime/runs")
    def list_runtime_runs() -> list[dict[str, Any]]:
        runs = _rt.get_all_runs(limit=50)
        return [_rt.run_to_summary_dict(r) for r in runs]

    @app.post("/api/runtime/runs")
    def create_runtime_run(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        run = _rt.RunRecord(
            run_id=uuid.uuid4().hex[:12],
            message=str(data.get("message") or "").strip(),
            created_at=now_iso(),
            status="pending",
            project_id=data.get("project_id") or None,
            package_path=data.get("package_path") or None,
        )
        ctx: dict[str, Any] = {"project_id": run.project_id}
        if "tool_input" in data and isinstance(data["tool_input"], dict):
            ctx["tool_input"] = data["tool_input"]
        if data.get("workflow_id"):
            ctx["workflow_id"] = data.get("workflow_id")
        if "llm_config" in data and isinstance(data["llm_config"], dict):
            # Keep raw API keys out of run records.
            ctx["llm_config"] = {k: v for k, v in data["llm_config"].items() if k != "api_key"}
        if isinstance(data.get("steps"), list):
            _rt.execute_run_with_plan(run, data["steps"], ctx)
        elif data.get("workflow_id"):
            workflows = {wf["id"]: wf for wf in agent_workbench.list_workflows()}
            workflow = workflows.get(str(data["workflow_id"]))
            if workflow is None:
                workflow_id = str(data["workflow_id"])
                message = f"workflow not found: {workflow_id}"
                diagnostic = {
                    "code": "workflow_not_found",
                    "message": message,
                    "remediation": "Call /api/runtime/workflows to list available workflow ids, then retry with a valid workflow_id.",
                    "tool_name": None,
                }
                run.status = "failed"
                run.errors.append(message)
                run.tool_errors.append(
                    _rt.ToolError(
                        code="workflow_not_found",
                        message=message,
                        tool_name=None,
                        details=diagnostic,
                    )
                )
                _rt._emit(run, "run_failed", {"errors": run.errors, "diagnostics": [diagnostic]})
                _rt.store_run(run)
            else:
                _rt.execute_run_with_plan(run, workflow.get("steps") or [], ctx)
        else:
            _rt.execute_run(run, ctx)
        all_artifacts = [
            a for tr in run.tool_results for a in tr.artifacts
        ]
        audit_payload: dict[str, Any] = {
            "kind": "runtime_run",
            "run_id": run.run_id,
            "message": run.message,
            "project_id": run.project_id,
            "tools": [tc.name for tc in run.tool_calls],
            "status": run.status,
            "errors": run.errors,
            "created_at": run.created_at,
            "artifacts": all_artifacts,
        }
        if run.project_id:
            try:
                write_audit_log(active_settings, run.project_id, "runtime_run", audit_payload)
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to write runtime run audit log.",
                    subsystem="app_factory.audit.runtime_run",
                    context={"project_id": run.project_id, "run_id": run.run_id},
                )
        return _rt.run_to_dict(run)

    @app.get("/api/runtime/runs/{run_id}")
    def get_runtime_run(run_id: str) -> dict[str, Any]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _rt.run_to_dict(run)

    @app.get("/api/runtime/runs/{run_id}/events")
    def get_runtime_run_events(run_id: str) -> list[dict[str, Any]]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return [
            {
                "id": e.id,
                "run_id": e.run_id,
                "type": e.type,
                "timestamp": e.timestamp,
                "payload": e.payload,
            }
            for e in run.events
        ]

    @app.post("/api/runtime/runs/{run_id}/approve")
    def approve_runtime_run(run_id: str) -> dict[str, Any]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"run is not awaiting approval (current status: {run.status})",
            )
        run = _rt.resume_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found after resume")
        if run.project_id:
            try:
                write_audit_log(
                    active_settings,
                    run.project_id,
                    "runtime_run",
                    {
                        "kind": "runtime_run_approved",
                        "run_id": run.run_id,
                        "status": run.status,
                        "created_at": now_iso(),
                    },
                )
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to write runtime-approval audit log.",
                    subsystem="app_factory.audit.runtime_run_approved",
                    context={"project_id": run.project_id, "run_id": run.run_id},
                )
        return _rt.run_to_dict(run)

    @app.post("/api/runtime/runs/{run_id}/reject")
    def reject_runtime_run(run_id: str) -> dict[str, Any]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"run is not awaiting approval (current status: {run.status})",
            )
        run = _rt.reject_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found after reject")
        if run.project_id:
            try:
                write_audit_log(
                    active_settings,
                    run.project_id,
                    "runtime_run",
                    {
                        "kind": "runtime_run_rejected",
                        "run_id": run.run_id,
                        "status": run.status,
                        "created_at": now_iso(),
                    },
                )
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to write runtime-rejection audit log.",
                    subsystem="app_factory.audit.runtime_run_rejected",
                    context={"project_id": run.project_id, "run_id": run.run_id},
                )
        return _rt.run_to_dict(run)
