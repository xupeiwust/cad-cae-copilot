"""Test MCP connection to FreeCAD GUI via xmlrpc mode."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SRC = str(Path(r"c:\Users\RL_Carla\Desktop\workspace_aieng\aieng-freecad-mcp") / "src")


async def main() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env["FREECAD_MCP_MODE"] = "xmlrpc"
    env["FREECAD_MCP_TRANSPORT"] = "stdio"
    env["FREECAD_MCP_HOST"] = "localhost"
    env["FREECAD_MCP_XMLRPC_PORT"] = "9875"

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "freecad_mcp.server"],
        env=env,
    )

    print("Starting aieng-freecad-mcp in xmlrpc mode...")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP session initialized via xmlrpc!")

            # Test cad_get_version
            print("\nCalling cad_get_version...")
            result = await session.call_tool("cad_get_version", {})
            texts = [item.text for item in result.content if hasattr(item, "text")]
            if texts:
                try:
                    parsed = json.loads(texts[0])
                    print(f"FreeCAD version: {parsed.get('outputs', {}).get('version')}")
                except json.JSONDecodeError:
                    print("Raw:", texts[0][:300])

            # Test cad_create_document
            print("\nCalling cad_create_document...")
            result = await session.call_tool("cad_create_document", {"name": "DroneTest"})
            texts = [item.text for item in result.content if hasattr(item, "text")]
            if texts:
                try:
                    parsed = json.loads(texts[0])
                    print(f"Document: {parsed.get('name')}")
                except json.JSONDecodeError:
                    print("Raw:", texts[0][:300])

            # Test cad_create_box
            print("\nCalling cad_create_box...")
            result = await session.call_tool(
                "cad_create_box",
                {"length": 50, "width": 30, "height": 20, "name": "TestBox", "doc_name": "DroneTest"},
            )
            texts = [item.text for item in result.content if hasattr(item, "text")]
            if texts:
                try:
                    parsed = json.loads(texts[0])
                    print(f"Box: {parsed.get('name')} ({parsed.get('type_id')})")
                except json.JSONDecodeError:
                    print("Raw:", texts[0][:300])

            print("\nConnection test PASSED. Ready for drone creation.")


if __name__ == "__main__":
    asyncio.run(main())
