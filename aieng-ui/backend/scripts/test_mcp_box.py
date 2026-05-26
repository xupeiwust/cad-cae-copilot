"""Test cad_create_box directly."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.freecad_mcp_client import FreeCADMCPClient

WORKSPACE = BACKEND.parents[1]
FREECAD_MCP_ROOT = WORKSPACE / "aieng-freecad-mcp"
FREECAD_HOME = Path(r"D:\FreeCAD 1.1")
FREECAD_PYTHON = FREECAD_HOME / "bin" / "python.exe"


async def main() -> None:
    client = FreeCADMCPClient(
        freecad_mcp_root=FREECAD_MCP_ROOT,
        freecad_path=FREECAD_HOME / "bin",
        mode="embedded",
        python_executable=FREECAD_PYTHON,
    )
    await client.start()

    # create doc
    r1 = await client.call_tool("cad_create_document", {"name": "BoxDoc"})
    print("create_doc:", json.dumps(r1.get("parsed"), indent=2)[:300])

    # create box
    r2 = await client.call_tool(
        "cad_create_box",
        {"length": 10, "width": 20, "height": 30, "name": "TestBox", "doc_name": "BoxDoc"},
    )
    print("create_box texts:", r2.get("texts"))
    print("create_box is_error:", r2.get("is_error"))
    print("create_box parsed:", json.dumps(r2.get("parsed"), indent=2)[:800])

    # list objects
    r3 = await client.call_tool("cad_list_objects", {"doc_name": "BoxDoc"})
    print("list_objects:", json.dumps(r3.get("parsed"), indent=2)[:400])

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
