"""Kimi directly drives FreeCAD via MCP — live CAD demo (simplified)."""

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
OUTPUT = Path.home() / "Desktop" / "aieng_mcp_test"


async def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    client = FreeCADMCPClient(
        freecad_mcp_root=FREECAD_MCP_ROOT,
        freecad_path=FREECAD_HOME / "bin",
        mode="embedded",
        python_executable=FREECAD_PYTHON,
    )
    await client.start()
    print("Kimi -> MCP -> FreeCAD 1.1  CONNECTED\n")

    # ── Create document ─────────────────────────────────────────────────────
    print("[1] Creating document 'Demo'")
    r = await client.call_tool("cad_create_document", {"name": "Demo"})
    print(f"    OK: {r.get('parsed', {}).get('name')}")

    # ── Create box ──────────────────────────────────────────────────────────
    print("[2] Creating box (50 x 30 x 20)")
    r = await client.call_tool(
        "cad_create_box",
        {"length": 50, "width": 30, "height": 20, "name": "Box", "doc_name": "Demo"},
    )
    p = r.get("parsed", {})
    print(f"    OK: {p.get('name')} ({p.get('type_id')})")
    print(f"    Volume: {p.get('changes', {}).get('volume_mm3')} mm3")

    # ── Create cylinder ─────────────────────────────────────────────────────
    print("[3] Creating cylinder (radius 8, height 25)")
    r = await client.call_tool(
        "cad_create_cylinder",
        {"radius": 8, "height": 25, "name": "Cylinder", "doc_name": "Demo"},
    )
    p = r.get("parsed", {})
    print(f"    OK: {p.get('name')} ({p.get('type_id')})")

    # ── Create sphere ───────────────────────────────────────────────────────
    print("[4] Creating sphere (radius 12)")
    r = await client.call_tool(
        "cad_create_sphere",
        {"radius": 12, "name": "Sphere", "doc_name": "Demo"},
    )
    p = r.get("parsed", {})
    print(f"    OK: {p.get('name')} ({p.get('type_id')})")

    # ── List objects ────────────────────────────────────────────────────────
    print("[5] Listing all objects")
    r = await client.call_tool("cad_list_objects", {"doc_name": "Demo"})
    objs = r.get("parsed", {}).get("objects", [])
    print(f"    Found {len(objs)} objects:")
    for obj in objs:
        print(f"      - {obj.get('name')} ({obj.get('type_id')})")

    # ── Mass properties ─────────────────────────────────────────────────────
    print("[6] Mass properties for Box")
    r = await client.call_tool(
        "cad_get_mass_properties",
        {"object_name": "Box", "doc_name": "Demo", "density_kg_m3": 2700},
    )
    p = r.get("parsed", {})
    print(f"    Volume: {p.get('volume_mm3')} mm3")
    print(f"    Mass:   {p.get('mass_kg')} kg")

    # ── Export ──────────────────────────────────────────────────────────────
    fcstd = OUTPUT / "demo_assembly.fcstd"
    step = OUTPUT / "demo_assembly.step"

    print(f"[7] Exporting FCStd -> {fcstd}")
    r = await client.call_tool("cad_export_fcstd", {"file_path": str(fcstd), "doc_name": "Demo"})
    print(f"    Status: {r.get('parsed', {}).get('status')}")

    print(f"[8] Exporting STEP -> {step}")
    r = await client.call_tool("cad_export_step", {"file_path": str(step), "doc_name": "Demo"})
    print(f"    Status: {r.get('parsed', {}).get('status')}")

    await client.close()

    print("\n" + "="*60)
    print("Done! Files saved to:")
    print(f"  {fcstd}")
    print(f"  {step}")
    print("="*60)
    print("Open demo_assembly.fcstd in FreeCAD to see Box + Cylinder + Sphere.")


if __name__ == "__main__":
    asyncio.run(main())
