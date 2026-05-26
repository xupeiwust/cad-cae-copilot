"""FreeCAD Unified MCP Server.

Exposes CAD modeling and CAE simulation tools through a single MCP endpoint.
"""

__all__ = ["create_server", "CAEFacade", "register_cae_tools"]

from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.tools_cae.server import register_cae_tools
from freecad_mcp.server import create_server
