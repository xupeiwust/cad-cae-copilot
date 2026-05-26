"""Lightweight executor that talks to FreeCAD via XML-RPC or direct import."""

from __future__ import annotations

import asyncio
import json
import os
import xmlrpc.client
from enum import Enum
from typing import Any, Protocol

from freecad_mcp.config import get_settings
from freecad_mcp.contracts import ToolExecutionError


class CadExecutor(Protocol):
    """Protocol satisfied by all FreeCAD executor backends.

    ``FreecadExecutor``, ``FreecadCmdExecutor``, and ``StubFreecadExecutor``
    all implement this interface, making them interchangeable at the patch
    and tool boundaries.
    """

    async def execute_async(self, code: str) -> dict[str, Any]: ...
    async def get_version_async(self) -> dict[str, Any]: ...


class FreecadMode(str, Enum):
    XMLRPC = "xmlrpc"
    SOCKET = "socket"
    EMBEDDED = "embedded"


class FreecadExecutor:
    """Synchronous executor with optional async wrapper."""

    def __init__(
        self,
        mode: FreecadMode | None = None,
        host: str = "localhost",
        xmlrpc_port: int = 9875,
        socket_port: int = 9876,
        timeout: float = 120.0,
        freecad_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.mode = mode or FreecadMode(settings.mode.value)
        self.host = host or settings.socket_host
        self.xmlrpc_port = xmlrpc_port or settings.xmlrpc_port
        self.socket_port = socket_port or settings.socket_port
        self.timeout = timeout
        self.freecad_path = freecad_path or settings.freecad_path
        self._proxy: xmlrpc.client.ServerProxy | None = None
        self._embedded_freecad: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        if self.mode == FreecadMode.XMLRPC:
            transport = xmlrpc.client.Transport()
            transport.timeout = self.timeout
            self._proxy = xmlrpc.client.ServerProxy(
                f"http://{self.host}:{self.xmlrpc_port}",
                allow_none=True,
                transport=transport,
            )
        elif self.mode == FreecadMode.EMBEDDED:
            self._connect_embedded()
        else:
            raise ToolExecutionError(f"Socket mode not yet implemented in lightweight executor. Use xmlrpc.")

    def disconnect(self) -> None:
        self._proxy = None
        self._embedded_freecad = None

    def _connect_embedded(self) -> None:
        freecad_path = self.freecad_path
        if not freecad_path:
            # Check configuration environment variables first
            freecad_path = os.environ.get("FREECAD_MCP_FREECAD_PATH") or os.environ.get("FREECAD_HOME")
        if not freecad_path:
            # Fallback to common platform paths (convenience only)
            candidates = [
                "/usr/lib/freecad/lib",
                "/usr/lib/freecad-daily/lib",
                "/Applications/FreeCAD.app/Contents/lib",
                "C:/Program Files/FreeCAD/bin",
            ]
            for cand in candidates:
                if os.path.isdir(cand):
                    freecad_path = cand
                    break
        if not freecad_path or not os.path.isdir(freecad_path):
            raise ToolExecutionError(
                "FreeCAD lib path not found. Set FREECAD_HOME, FREECAD_MCP_FREECAD_PATH, or install FreeCAD."
            )
        import sys

        if freecad_path not in sys.path:
            sys.path.insert(0, freecad_path)
        try:
            import FreeCAD  # type: ignore[import-not-found]
            self._embedded_freecad = FreeCAD
        except Exception as exc:
            raise ToolExecutionError(f"Failed to import FreeCAD in embedded mode: {exc}") from exc

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, code: str) -> dict[str, Any]:
        if self.mode == FreecadMode.XMLRPC and self._proxy is not None:
            return self._execute_xmlrpc(code)
        if self.mode == FreecadMode.EMBEDDED and self._embedded_freecad is not None:
            return self._execute_embedded(code)
        raise ToolExecutionError("FreeCAD executor is not connected.")

    def _execute_xmlrpc(self, code: str) -> dict[str, Any]:
        try:
            response = self._proxy.execute(code)  # type: ignore[union-attr]
        except Exception as exc:
            raise ToolExecutionError(f"FreeCAD XML-RPC call failed: {exc}") from exc
        if not isinstance(response, dict):
            raise ToolExecutionError("Unexpected FreeCAD XML-RPC response format.")
        if not response.get("success", False):
            error = (
                response.get("error_traceback")
                or response.get("error_message")
                or response.get("stderr")
                or "Unknown FreeCAD execution error."
            )
            raise ToolExecutionError(error)
        return response

    def _execute_embedded(self, code: str) -> dict[str, Any]:
        # Simple embedded execution using exec in FreeCAD context
        try:
            namespace: dict[str, Any] = {"FreeCAD": self._embedded_freecad}
            exec(code, namespace)  # noqa: S102
            result = namespace.get("_result_", {})
            return {"success": True, "result": result, "stdout": "", "stderr": ""}
        except Exception as exc:
            return {
                "success": False,
                "error_message": str(exc),
                "error_traceback": str(exc),
                "stdout": "",
                "stderr": "",
            }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_version(self) -> dict[str, Any]:
        code = """
import FreeCAD
_result_ = {
    "version": FreeCAD.Version()[0] + "." + FreeCAD.Version()[1] + "." + FreeCAD.Version()[2],
    "revision": FreeCAD.Version()[3],
    "python_version": FreeCAD.Version()[4],
    "gui_available": FreeCAD.GuiUp,
}
"""
        resp = self.execute(code)
        return resp.get("result", {})

    def get_active_document(self) -> dict[str, Any] | None:
        code = """
import FreeCAD
doc = FreeCAD.ActiveDocument
if doc is None:
    _result_ = None
else:
    _result_ = {
        "name": doc.Name,
        "label": doc.Label,
        "path": doc.FileName,
        "objects": [obj.Name for obj in doc.Objects],
    }
"""
        resp = self.execute(code)
        return resp.get("result")

    # ------------------------------------------------------------------
    # Async wrappers for FastMCP
    # ------------------------------------------------------------------

    async def execute_async(self, code: str) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute, code)

    async def get_version_async(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_version)
