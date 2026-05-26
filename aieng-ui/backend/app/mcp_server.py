"""MCP server exposing the workbench runtime tool registry.

Lets external agents (Claude Code, Cursor, Cline, etc.) drive the workbench
via their own tool-calling harness — no need to reimplement the LLM loop.

Architecture:
    runtime._REGISTRY (single source of truth, registered by create_app)
        │
        ▼
    list_tools_for_mcp() → MCP tool definitions with JSON schemas
        │
        ▼
    FastMCP server → stdio (default) or HTTP (--http)

Usage:
    # stdio (Claude Code-style):
    python -m app.mcp_server

    # HTTP transport for debugging or multi-client:
    python -m app.mcp_server --http --port 8765

The server boots a FastAPI app instance just to trigger the existing
``create_app()`` tool registration; the FastAPI request handlers themselves
are never used. All tool invocations are dispatched through
``runtime.invoke_tool``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

logger = logging.getLogger(__name__)

# When set, tool calls are forwarded to the running FastAPI backend's
# /api/agent/invoke-tool endpoint instead of executing in-process. This is what
# lets the React UI render live agent activity (CAD build animation) — the
# single backend process owns state AND emits SSE events. Configure it in the
# Claude Code mcp.json env block: AIENG_BACKEND_URL=http://127.0.0.1:8000
_BACKEND_URL = (os.environ.get("AIENG_BACKEND_URL") or "").rstrip("/")


def _forward_to_backend(tool_name: str, args: dict[str, Any]) -> Any:
    """POST the tool call to the running backend; return its JSON result.

    Raises urllib.error.URLError if the backend is unreachable so the caller
    can decide whether to fall back to in-process execution.
    """
    url = f"{_BACKEND_URL}/api/agent/invoke-tool"
    body = json.dumps({"tool": tool_name, "input": args}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Generous timeout: a real solver run or build can take a while; the backend
    # streams progress to the UI meanwhile.
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _coerce_result(value: Any) -> str:
    """Serialise tool return value to a JSON string for MCP text content.

    MCP tools return text content blocks. Runtime handlers return arbitrary
    Python objects (mostly dicts); JSON is the lossless representation that
    survives the agent's parser.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception:
        return repr(value)


def _finalize_result(value: Any) -> Any:
    """Convert a tool result into MCP content.

    If the result dict carries a ``thumbnail_png_base64`` field (rendered by
    ``cad.execute_build123d`` so the agent can *see* the geometry), strip it from
    the JSON text and return ``[text, Image]`` so the MCP client renders the
    thumbnail as an actual image rather than an opaque base64 blob. Otherwise
    return the plain JSON string.
    """
    if isinstance(value, dict) and value.get("thumbnail_png_base64"):
        import base64

        b64 = value.get("thumbnail_png_base64")
        rest = {k: v for k, v in value.items() if k != "thumbnail_png_base64"}
        text = _coerce_result(rest)
        try:
            image = Image(data=base64.b64decode(b64), format="png")
            return [text, image]
        except Exception:
            return text
    return _coerce_result(value)


_SERVER_DESCRIPTION = """\
aieng Workbench — CAD/CAE co-pilot for mechanical engineering.

IMPORTANT: Call aieng.agent_readme first to receive the full capability guide.
Then call aieng.list_projects to discover available project IDs.

This server exposes real 3D CAD modeling (build123d / OpenCASCADE) and
structural FEA (CalculiX) tools. cad.execute_build123d runs your Python code
against build123d and produces actual STEP/STL/GLB geometry — no API key needed.

Quick start:
  1. aieng.agent_readme      → full guide (workflows, pointer syntax, approvals)
  2. aieng.list_projects     → discover project IDs
  3. aieng.agent_context { project_id }  → geometry state + suggested next steps

Sustainable modeling loop: cad.get_source (read state) → cad.execute_build123d
with mode=append (build onto `previous_result`; set `.label` on parts to name them)
→ read the returned thumbnail + named_parts/parts_added to verify, then repeat.
"""


def _build_mcp_server(name: str = "aieng-workbench") -> FastMCP:
    """Instantiate FastMCP and register every runtime tool from the workbench.

    Side effect: triggers ``create_app()`` so the runtime tool registry is
    populated before we read it. The FastAPI app is otherwise discarded.
    """
    # Import lazily so module-load doesn't pay for FastAPI when only the
    # registry shape is needed (e.g. in tests that don't need a server).
    from .app_factory import create_app
    from . import runtime as _rt

    create_app()  # populates runtime._REGISTRY
    tool_defs = _rt.list_tools_for_mcp()

    mcp = FastMCP(name, instructions=_SERVER_DESCRIPTION)

    # Onboarding tools first — agents see these at the top of the tool list
    # and are more likely to call them before attempting other operations.
    _ONBOARDING_FIRST = ("aieng.agent_readme", "aieng.list_projects", "aieng.agent_context")
    tool_defs = sorted(
        tool_defs,
        key=lambda t: (0 if t["name"] in _ONBOARDING_FIRST else 1, t["name"]),
    )

    for tool_def in tool_defs:
        tool_name = tool_def["name"]
        description = tool_def.get("description") or tool_name
        if tool_def.get("requires_approval"):
            description = (
                f"[APPROVAL REQUIRED] {description}\n\n"
                "This tool performs an action with side effects (e.g. solver "
                "execution or CAD modification). The MCP client should prompt "
                "the human before invoking it."
            )
        input_schema = tool_def.get("input_schema") or {
            "type": "object",
            "additionalProperties": True,
        }

        def _make_handler(name_: str):
            def _handler(**kwargs: Any) -> Any:
                args = dict(kwargs)
                # Prefer forwarding to the running backend so the UI sees live
                # activity; fall back to in-process execution if it's down.
                if _BACKEND_URL:
                    try:
                        result = _forward_to_backend(name_, args)
                        return _finalize_result(result)
                    except urllib.error.URLError as exc:
                        logger.warning(
                            "backend forward failed for %s (%s); running in-process",
                            name_, exc,
                        )
                    except Exception as exc:  # pragma: no cover
                        logger.warning("backend forward error for %s: %s; running in-process", name_, exc)
                try:
                    result = _rt.invoke_tool(name_, args)
                except KeyError as exc:
                    return _coerce_result({"status": "error", "code": "tool_not_found", "message": str(exc)})
                except Exception as exc:  # pragma: no cover - propagated to client
                    logger.exception("tool %s raised", name_)
                    return _coerce_result({"status": "error", "code": "tool_exception", "message": f"{type(exc).__name__}: {exc}"})
                return _finalize_result(result)
            _handler.__name__ = name_.replace(".", "_")
            _handler.__doc__ = description
            return _handler

        mcp.add_tool(
            _make_handler(tool_name),
            name=tool_name,
            description=description,
            structured_output=False,
            annotations=None,
        )
        # FastMCP versions vary in how they accept JSON Schema overrides;
        # write the schema directly into the registered Tool so MCP clients
        # see the curated shape rather than the inferred ``**kwargs`` blob.
        tool_obj = mcp._tool_manager._tools.get(tool_name)  # type: ignore[attr-defined]
        if tool_obj is not None:
            tool_obj.parameters = input_schema

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.mcp_server", description=__doc__.splitlines()[0])
    parser.add_argument("--http", action="store_true", help="Run over HTTP (SSE) instead of stdio.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (only with --http).")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port (only with --http).")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Server log level. stdio transport requires WARNING+ so logs don't corrupt the framed protocol.",
    )
    args = parser.parse_args(argv)

    # IMPORTANT: stdio is the wire — any stray print to stdout corrupts the
    # JSON-RPC frames. Route logging to stderr, which Claude Code surfaces
    # under the MCP server's status panel.
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        stream=sys.stderr,
        format="[mcp-server] %(levelname)s %(name)s: %(message)s",
    )

    mcp = _build_mcp_server()
    logger.info("registered %d tools", len(mcp._tool_manager._tools))  # type: ignore[attr-defined]

    if args.http:
        # FastMCP's SSE app provides /sse + /messages.
        import uvicorn

        logger.warning("MCP server listening on http://%s:%d (SSE)", args.host, args.port)
        uvicorn.run(mcp.sse_app(), host=args.host, port=args.port, log_level=args.log_level.lower())
    else:
        # Default: stdio transport. FastMCP's blocking entry point.
        mcp.run("stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
