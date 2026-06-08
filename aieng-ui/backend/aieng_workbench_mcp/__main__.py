"""Run the AIENG Workbench MCP server as ``python -m aieng_workbench_mcp``."""

from __future__ import annotations

from app.mcp_server import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
