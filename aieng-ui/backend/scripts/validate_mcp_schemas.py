#!/usr/bin/env python3
"""Validate MCP tool schemas for provider compatibility.

Providers such as OpenAI Codex and Kimi Code CLI require tool input schemas to
have ``type == "object"`` at the top level and reject ``oneOf`` / ``anyOf`` /
``allOf`` / ``enum`` / ``not`` at the root.  This script scans every registered
runtime tool and fails if any schema violates those rules.

Usage (from aieng-ui/backend/):
    python scripts/validate_mcp_schemas.py
    python scripts/validate_mcp_schemas.py --dump schemas.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _build_mcp_server():
    """Boot the runtime registry (registers all tools via create_app side-effect)."""
    from app import runtime as _rt
    from app.mcp_server import _build_mcp_server as _build

    return _build()


FORBIDDEN_TOP_LEVEL = {"oneOf", "anyOf", "allOf", "enum", "not"}


def validate_schema(tool_name: str, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        errors.append(f"{tool_name}: schema is not a dict")
        return errors
    if schema.get("type") != "object":
        errors.append(
            f"{tool_name}: top-level type is '{schema.get('type')}', expected 'object'"
        )
    forbidden = FORBIDDEN_TOP_LEVEL & set(schema.keys())
    if forbidden:
        errors.append(
            f"{tool_name}: forbidden top-level keys: {sorted(forbidden)}"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate MCP tool schemas")
    parser.add_argument(
        "--dump",
        metavar="PATH",
        help="Write all schemas to a JSON file after validation",
    )
    args = parser.parse_args(argv)

    mcp = _build_mcp_server()
    tools: dict[str, Any] = dict(mcp._tool_manager._tools)

    all_errors: list[str] = []
    schemas: dict[str, dict[str, Any]] = {}

    for name, tool in tools.items():
        params = tool.parameters
        schemas[name] = dict(params) if isinstance(params, dict) else {}
        all_errors.extend(validate_schema(name, params))

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(schemas, f, indent=2, ensure_ascii=False)
        print(f"Dumped {len(schemas)} schemas to {args.dump}")

    if all_errors:
        print(f"FAIL — {len(all_errors)} provider-incompatible schema(s) found:")
        for err in all_errors:
            print(f"  • {err}")
        return 1

    print(f"OK — {len(schemas)} MCP tool schema(s) are provider-compatible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
