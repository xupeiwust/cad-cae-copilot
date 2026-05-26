"""Unified FreeCAD MCP Server entry point.

Provides a single FastMCP endpoint exposing both CAD modeling tools and
CAE simulation tools. The server manages:

- FreeCAD bridge lifecycle (XML-RPC / embedded)
- CAE facade and backend selection (surrogate or real FreeCAD FEM)
- Tool registration for both domains
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.bridge.executor import FreecadExecutor, FreecadMode
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.toolset import FreecadFemCaeToolset, SurrogateStaticCaeToolset
from freecad_mcp.aieng_runtime_client import AiengRuntimeClient
from freecad_mcp.config import TransportType, get_settings
from freecad_mcp.tools_aieng import register_aieng_tools
from freecad_mcp.tools_cad import register_cad_tools
from freecad_mcp.tools_cae.server import register_cae_tools
from freecad_mcp.tools_runtime import register_runtime_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state managed by lifespan
_executor: FreecadExecutor | None = None
_facade: CAEFacade | None = None


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Manage FreeCAD bridge and CAE facade lifecycle."""
    global _executor, _facade
    settings = get_settings()

    # Initialize FreeCAD executor (used by CAD tools)
    logger.info("Initializing FreeCAD executor...")
    _executor = FreecadExecutor(
        mode=FreecadMode(settings.mode.value),
        host=settings.socket_host,
        xmlrpc_port=settings.xmlrpc_port,
        socket_port=settings.socket_port,
        timeout=settings.timeout_ms / 1000.0,
        freecad_path=settings.freecad_path,
    )
    try:
        _executor.connect()
        version = _executor.get_version()
        logger.info(
            "FreeCAD connected: %s (GUI: %s)",
            version.get("version", "unknown"),
            version.get("gui_available", "unknown"),
        )
    except Exception as exc:
        logger.warning("Could not connect to FreeCAD at startup: %s", exc)
        # Continue; some backends (surrogate) don't need live FreeCAD

    # Initialize CAE facade
    freecad_connected = False
    try:
        _executor.get_version()
        freecad_connected = True
    except Exception:
        pass

    if freecad_connected and settings.solver_backend != "surrogate":
        toolset = FreecadFemCaeToolset(
            host=settings.socket_host,
            port=settings.xmlrpc_port,
            timeout_seconds=settings.timeout_ms / 1000.0,
            ccx_binary=settings.ccx_binary,
            gmsh_binary=settings.gmsh_binary,
        )
        logger.info("CAE backend: FreeCAD FEM (real solver)")
    else:
        if freecad_connected:
            logger.warning(
                "FreeCAD is connected but solver_backend='%s' — using surrogate. "
                "Unset FREECAD_MCP_SOLVER_BACKEND or set to 'freecad_fem' for real FEM.",
                settings.solver_backend,
            )
        else:
            logger.warning(
                "FreeCAD not connected — falling back to surrogate static backend. "
                "Real FEM requires FreeCAD + Gmsh + CalculiX."
            )
        toolset = SurrogateStaticCaeToolset()
        logger.info("CAE backend: surrogate static")

    _facade = CAEFacade(toolset)

    # Register tools now that runtime objects are initialized
    register_cad_tools(_server, _executor)
    register_cae_tools(_server, _facade)
    register_aieng_tools(_server, _executor, _facade)
    # Register runtime bridge tools (no FreeCAD needed; delegates to aieng-ui REST API)
    register_runtime_tools(_server, AiengRuntimeClient())

    try:
        yield
    finally:
        logger.info("Shutting down FreeCAD MCP server...")
        if _executor:
            _executor.disconnect()
            _executor = None
        _facade = None


def create_server() -> FastMCP:
    """Create and configure the unified FastMCP server."""
    settings = get_settings()
    mcp = FastMCP(name="freecad-mcp", lifespan=lifespan)

    return mcp


def _apply_cli_to_env(args: argparse.Namespace) -> None:
    import os

    if args.mode:
        os.environ["FREECAD_MCP_MODE"] = args.mode
    if args.host:
        os.environ["FREECAD_MCP_SOCKET_HOST"] = args.host
    if args.port:
        os.environ["FREECAD_MCP_XMLRPC_PORT"] = str(args.port)
    if args.transport:
        os.environ["FREECAD_MCP_TRANSPORT"] = args.transport
    if args.http_port:
        os.environ["FREECAD_MCP_HTTP_PORT"] = str(args.http_port)
    if args.solver:
        os.environ["FREECAD_MCP_SOLVER_BACKEND"] = args.solver
    if args.log_level:
        os.environ["FREECAD_MCP_LOG_LEVEL"] = args.log_level


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="freecad-mcp",
        description="Unified FreeCAD MCP Server (CAD + CAE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  FREECAD_MCP_MODE            Connection mode: xmlrpc, socket, or embedded (default: xmlrpc)
  FREECAD_MCP_SOCKET_HOST     Host for FreeCAD connection (default: localhost)
  FREECAD_MCP_XMLRPC_PORT     XML-RPC port (default: 9875)
  FREECAD_MCP_TRANSPORT       MCP transport: stdio or http (default: stdio)
  FREECAD_MCP_HTTP_PORT       HTTP port (default: 8000)
  FREECAD_MCP_SOLVER_BACKEND  CAE backend: surrogate or freecad_fem (default: surrogate)
  FREECAD_MCP_CCX_BINARY      Path to CalculiX binary (optional)
  FREECAD_MCP_GMSH_BINARY     Path to Gmsh binary (optional)

Examples:
  freecad-mcp                                    # stdio, surrogate CAE
  FREECAD_MCP_SOLVER_BACKEND=freecad_fem freecad-mcp  # real FEM backend
  freecad-mcp --transport http --http-port 8080  # HTTP transport
""",
    )
    parser.add_argument("--mode", choices=["xmlrpc", "socket", "embedded"], help="FreeCAD connection mode")
    parser.add_argument("--host", help="FreeCAD host")
    parser.add_argument("--port", type=int, help="FreeCAD XML-RPC port")
    parser.add_argument("--transport", choices=["stdio", "http"], help="MCP transport")
    parser.add_argument("--http-port", type=int, help="HTTP transport port")
    parser.add_argument("--solver", choices=["surrogate", "freecad_fem"], help="CAE solver backend")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    parser.add_argument("--check", action="store_true", help="Test FreeCAD connection and exit")
    args = parser.parse_args()

    _apply_cli_to_env(args)
    settings = get_settings()
    logging.getLogger().setLevel(settings.log_level.upper())

    if args.check:
        _test_connection()
        return

    mcp = create_server()

    if settings.transport == TransportType.HTTP:
        logger.info("Starting HTTP transport on port %d", settings.http_port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=settings.http_port)  # type: ignore[call-arg]
    else:
        logger.info("Starting stdio transport")
        mcp.run()


def _test_connection() -> None:
    settings = get_settings()
    executor = FreecadExecutor(
        mode=FreecadMode(settings.mode.value),
        host=settings.socket_host,
        xmlrpc_port=settings.xmlrpc_port,
    )
    try:
        executor.connect()
        version = executor.get_version()
        print("✓ Connection successful!")
        print(f"  FreeCAD version: {version.get('version', 'unknown')}")
        print(f"  GUI available: {version.get('gui_available', 'unknown')}")
        sys.exit(0)
    except Exception as exc:
        print(f"✗ Connection failed: {exc}")
        sys.exit(1)
    finally:
        executor.disconnect()


if __name__ == "__main__":
    main()
