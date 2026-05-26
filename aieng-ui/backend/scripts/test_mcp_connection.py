"""Quick smoke test: connect to aieng-freecad-mcp and exercise a few CAD tools.

This demonstrates that the Kimi agent itself can operate FreeCAD directly
through the MCP stdio transport — a powerful debugging and exploration mode.

Run with the workspace Python (3.14) — the MCP server subprocess will use
FreeCAD's bundled Python (3.11) where FreeCAD.pyd can be imported.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure app package is importable
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.freecad_mcp_client import FreeCADMCPClient

WORKSPACE = BACKEND.parents[1]
FREECAD_MCP_ROOT = WORKSPACE / "aieng-freecad-mcp"
FREECAD_HOME = Path(r"D:\FreeCAD 1.1")
FREECAD_PYTHON = FREECAD_HOME / "bin" / "python.exe"


async def main() -> None:
    print("=" * 60)
    print("MCP Smoke Test -- Connecting Kimi -> aieng-freecad-mcp -> FreeCAD")
    print("=" * 60)

    client = FreeCADMCPClient(
        freecad_mcp_root=FREECAD_MCP_ROOT,
        freecad_path=FREECAD_HOME / "bin",
        mode="embedded",
        python_executable=FREECAD_PYTHON,
    )

    print(f"\n[1] Starting MCP server (python={FREECAD_PYTHON}) ...")
    await client.start()
    print("[1] OK -- MCP session initialized")

    # ── 2. Get FreeCAD version ──────────────────────────────────────────────
    print("\n[2] Calling cad_get_version ...")
    version_resp = await client.call_tool("cad_get_version", {})
    print(f"[2] Raw response: {json.dumps(version_resp.get('parsed'), indent=2, ensure_ascii=False)[:500]}")

    # ── 3. Create a document ────────────────────────────────────────────────
    print("\n[3] Calling cad_create_document ...")
    doc_resp = await client.call_tool("cad_create_document", {"name": "McpSmokeTest"})
    print(f"[3] Raw response: {json.dumps(doc_resp.get('parsed'), indent=2, ensure_ascii=False)[:500]}")

    # ── 4. Create a box ─────────────────────────────────────────────────────
    print("\n[4] Calling cad_create_box (50×30×20 mm) ...")
    box_resp = await client.call_tool(
        "cad_create_box",
        {"length": 50, "width": 30, "height": 20, "name": "SmokeBox", "doc_name": "McpSmokeTest"},
    )
    print(f"[4] full resp texts: {box_resp.get('texts', [])[:2]}")
    print(f"[4] is_error: {box_resp.get('is_error')}")
    box_parsed = box_resp.get("parsed") or {}
    print(f"[4] parsed: {json.dumps(box_parsed, indent=2, ensure_ascii=False)[:500]}")

    # ── 5. List objects ─────────────────────────────────────────────────────
    print("\n[5] Calling cad_list_objects ...")
    list_resp = await client.call_tool("cad_list_objects", {})
    list_parsed = list_resp.get("parsed") or {}
    objects = list_parsed.get("objects", [])
    print(f"[5] full list resp: {json.dumps(list_parsed, indent=2, ensure_ascii=False)[:500]}")
    print(f"[5] Found {len(objects)} object(s):")
    for obj in objects:
        print(f"    - {obj.get('name')} ({obj.get('type')})")

    # ── 6. Get mass properties ──────────────────────────────────────────────
    if objects:
        print("\n[6] Calling cad_get_mass_properties ...")
        mass_resp = await client.call_tool(
            "cad_get_mass_properties",
            {"object_name": objects[-1]["name"], "density_kg_m3": 2700},
        )
        mass_parsed = mass_resp.get("parsed") or {}
        print(f"[6] Volume={mass_parsed.get('volume_mm3')} mm3  Mass={mass_parsed.get('mass_kg')} kg")

    # ── 7. Export STEP to temp ──────────────────────────────────────────────
    import tempfile

    tmp_step = Path(tempfile.gettempdir()) / "mcp_smoke_test.step"
    print(f"\n[7] Calling cad_export_step -> {tmp_step} ...")
    export_resp = await client.call_tool("cad_export_step", {"file_path": str(tmp_step)})
    print(f"[7] full export resp: {json.dumps(export_resp.get('parsed'), indent=2, ensure_ascii=False)[:500]}")
    export_parsed = export_resp.get("parsed") or {}
    print(f"[7] success={export_parsed.get('success')}  file_exists={tmp_step.exists()}")
    if tmp_step.exists():
        tmp_step.unlink(missing_ok=True)

    print("\n[8] Closing MCP session ...")
    await client.close()
    print("[8] Done.")
    print("=" * 60)
    print("Smoke test PASSED -- Kimi can directly drive FreeCAD via MCP")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
