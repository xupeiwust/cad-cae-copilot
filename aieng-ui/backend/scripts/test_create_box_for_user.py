"""Create a box and save FCStd + STEP to user's Desktop for visual inspection."""

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

OUTPUT_DIR = Path.home() / "Desktop" / "aieng_mcp_test"


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fcstd_path = OUTPUT_DIR / "test_box.fcstd"
    step_path = OUTPUT_DIR / "test_box.step"

    print(f"Connecting to FreeCAD via MCP (embedded mode)...")
    client = FreeCADMCPClient(
        freecad_mcp_root=FREECAD_MCP_ROOT,
        freecad_path=FREECAD_HOME / "bin",
        mode="embedded",
        python_executable=FREECAD_PYTHON,
    )
    await client.start()
    print("Connected.")

    # Create document
    print("Creating document...")
    r1 = await client.call_tool("cad_create_document", {"name": "TestBoxDoc"})
    print(f"  Doc: {json.dumps(r1.get('parsed'), indent=2)[:200]}")

    # Create box
    print("Creating box (50x30x20)...")
    r2 = await client.call_tool(
        "cad_create_box",
        {"length": 50, "width": 30, "height": 20, "name": "TestBox", "doc_name": "TestBoxDoc"},
    )
    print(f"  Box: {json.dumps(r2.get('parsed'), indent=2)[:300]}")

    # Export FCStd
    print(f"Exporting FCStd to {fcstd_path}...")
    r3 = await client.call_tool("cad_export_fcstd", {"file_path": str(fcstd_path), "doc_name": "TestBoxDoc"})
    print(f"  FCStd export: {r3.get('parsed', {}).get('status', 'unknown')}")

    # Export STEP
    print(f"Exporting STEP to {step_path}...")
    r4 = await client.call_tool("cad_export_step", {"file_path": str(step_path), "doc_name": "TestBoxDoc"})
    print(f"  STEP export: {r4.get('parsed', {}).get('status', 'unknown')}")

    await client.close()
    print("Done.")
    print("")
    print("=" * 60)
    print(f"Files saved to: {OUTPUT_DIR}")
    print(f"  - {fcstd_path.name}")
    print(f"  - {step_path.name}")
    print("=" * 60)
    print("")
    print("Please open 'test_box.fcstd' in your FreeCAD GUI to verify.")


if __name__ == "__main__":
    asyncio.run(main())
