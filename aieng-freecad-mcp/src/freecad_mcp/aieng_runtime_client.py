"""Synchronous REST client for the aieng-ui runtime API.

Wraps the aieng-ui runtime endpoints so that MCP tools can trigger runs,
poll status, and approve/reject gated operations without embedding any
FreeCAD or package logic here.

Configure via env var:
    AIENG_RUNTIME_BASE_URL=http://localhost:8000  (default)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class AiengRuntimeError(Exception):
    """Raised when the runtime API returns an error or is unreachable."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class AiengRuntimeClient:
    """Synchronous HTTP client for the aieng-ui runtime REST API.

    Args:
        base_url: Base URL of the aieng-ui backend. Falls back to
                  ``AIENG_RUNTIME_BASE_URL`` env var, then
                  ``http://localhost:8000``.
        timeout:  Per-request timeout in seconds.
    """

    DEFAULT_URL = "http://localhost:8000"

    def __init__(self, base_url: str | None = None, timeout: int = 30) -> None:
        self.base_url = (
            base_url
            or os.environ.get("AIENG_RUNTIME_BASE_URL", self.DEFAULT_URL)
        ).rstrip("/")
        self.timeout = timeout

    # ── internal ──────────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                detail: dict[str, Any] = json.loads(exc.read().decode())
            except Exception:
                detail = {"detail": exc.reason}
            raise AiengRuntimeError(
                f"HTTP {exc.code} from {method} {path}",
                status_code=exc.code,
                response=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise AiengRuntimeError(
                f"Connection error reaching {url}: {exc.reason}"
            ) from exc

    # ── public API ────────────────────────────────────────────────────────────

    def list_tools(self) -> list[dict[str, Any]]:
        """Return all tools registered in the aieng-ui runtime."""
        result = self._request("GET", "/api/runtime/tools")
        return result if isinstance(result, list) else []

    def start_run(
        self,
        message: str,
        project_id: str | None = None,
        tool_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a runtime run and return the initial run record.

        Args:
            message:    Natural-language instruction routed by the runtime planner.
            project_id: Optional project ID; lets the runtime resolve file paths
                        from the project's ``metadata.json``.
            tool_input: Optional structured parameters merged into each plan step's
                        input. Useful for passing explicit ``inputPath``,
                        ``outputPath``, ``loadCaseId``, etc.
        """
        body: dict[str, Any] = {"message": message}
        if project_id:
            body["project_id"] = project_id
        if tool_input:
            body["tool_input"] = tool_input
        return self._request("POST", "/api/runtime/runs", body=body)

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Return a run record by ID."""
        return self._request("GET", f"/api/runtime/runs/{run_id}")

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return the ordered event timeline for a run."""
        result = self._request("GET", f"/api/runtime/runs/{run_id}/events")
        return result if isinstance(result, list) else []

    def approve_run(self, run_id: str) -> dict[str, Any]:
        """Resume an awaiting-approval run by approving the pending tool."""
        return self._request("POST", f"/api/runtime/runs/{run_id}/approve")

    def reject_run(self, run_id: str) -> dict[str, Any]:
        """Cancel an awaiting-approval run without executing the pending tool."""
        return self._request("POST", f"/api/runtime/runs/{run_id}/reject")

    def get_cae_artifacts(self, project_id: str) -> dict[str, Any]:
        """Return CAE artifact detection payload for a project.

        Args:
            project_id: Project ID whose .aieng package will be scanned.
        """
        return self._request("GET", f"/api/projects/{project_id}/cae-artifacts")

    def get_cae_result_summary(self, project_id: str) -> dict[str, Any]:
        """Return CAE/post-processing result summary for a project.

        This is a thin wrapper over the aieng-ui endpoint. The summary is
        generated from artifact presence only; no solver is executed and no
        numerical VTU/FRD fields are parsed.

        Args:
            project_id: Project ID to inspect.
        """
        return self._request("GET", f"/api/projects/{project_id}/cae-result-summary")

    def get_cae_preprocessing_summary(self, project_id: str) -> dict[str, Any]:
        """Return CAE pre-processing readiness summary for a project.

        Reports which setup artifacts are present (materials, loads, BCs, mesh,
        solver settings) and whether the package is ready for solver execution.
        Read-only; no solver is executed.

        Args:
            project_id: Project ID to inspect.
        """
        return self._request("GET", f"/api/projects/{project_id}/cae-preprocessing-summary")

    def get_cae_simulation_run_summary(self, project_id: str) -> dict[str, Any]:
        """Return simulation run metadata summary for a project.

        Reports run count, latest run state (solved/converged/failed), solver
        software, and warnings. Read-only; no solver is executed and no
        VTU/FRD numerical fields are parsed.

        Args:
            project_id: Project ID to inspect.
        """
        return self._request("GET", f"/api/projects/{project_id}/cae-simulation-run-summary")

    def wait_for_run(
        self,
        run_id: str,
        timeout_seconds: float = 60,
        poll_interval: float = 2,
    ) -> dict[str, Any]:
        """Poll until the run reaches a terminal or approval-required state.

        Terminal statuses: ``completed``, ``failed``, ``rejected``, ``cancelled``.
        Also returns on ``awaiting_approval`` without auto-approving the run.

        Raises:
            AiengRuntimeError: If ``timeout_seconds`` is exceeded.
        """
        deadline = time.monotonic() + timeout_seconds
        while True:
            run = self.get_run(run_id)
            status = run.get("status", "")
            if status in (
                "completed",
                "failed",
                "rejected",
                "cancelled",
                "awaiting_approval",
            ):
                return run
            if time.monotonic() >= deadline:
                raise AiengRuntimeError(
                    f"Timed out after {timeout_seconds}s waiting for run {run_id!r}; "
                    f"last status: {status!r}"
                )
            time.sleep(poll_interval)
