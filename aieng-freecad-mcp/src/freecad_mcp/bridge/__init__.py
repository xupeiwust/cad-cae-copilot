"""Minimal FreeCAD execution bridge for the unified MCP server.

Supports XML-RPC (primary), socket (JSON-RPC), embedded, and FreeCADCmd
subprocess modes.  For most use cases, XML-RPC is recommended; for
environments with ABI mismatch, FreeCADCmd subprocess is preferred.
"""

from freecad_mcp.bridge.executor import FreecadExecutor, FreecadMode
from freecad_mcp.bridge.freecad_cmd import FreecadCmdExecutor

__all__ = ["FreecadExecutor", "FreecadMode", "FreecadCmdExecutor"]
