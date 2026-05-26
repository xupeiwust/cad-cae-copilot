"""Kimi directly drives FreeCAD via MCP — live CAD demo.

This script demonstrates the agent operating FreeCAD in real-time:
create documents, add primitives, perform boolean operations, add fillets,
inspect properties, and export artifacts.
"""

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


def _print_step(n: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"STEP {n}: {title}")
    print("="*60)


async def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    client = FreeCADMCPClient(
        freecad_mcp_root=FREECAD_MCP_ROOT,
        freecad_path=FREECAD_HOME / "bin",
        mode="embedded",
        python_executable=FREECAD_PYTHON,
    )
    await client.start()
    print("Kimi -> MCP -> FreeCAD 1.1  CONNECTED")

    # ── Step 1: Create document ─────────────────────────────────────────────
    _print_step(1, "Create new document 'BracketDemo'")
    r = await client.call_tool("cad_create_document", {"name": "BracketDemo"})
    print(f"  Document: {r.get('parsed', {}).get('name')}")

    # ── Step 2: Create base plate ───────────────────────────────────────────
    _print_step(2, "Create base plate (80 x 60 x 10 mm)")
    r = await client.call_tool(
        "cad_create_box",
        {"length": 80, "width": 60, "height": 10, "name": "BasePlate", "doc_name": "BracketDemo"},
    )
    p = r.get("parsed", {})
    print(f"  Object: {p.get('name')} ({p.get('type_id')})")
    ch = p.get("changes", {})
    print(f"  Volume: {ch.get('volume_mm3')} mm3  Mass: {ch.get('mass_kg')} kg")

    # ── Step 3: Create mounting hole (cylinder) ─────────────────────────────
    _print_step(3, "Create mounting hole cylinder (radius 5 mm)")
    r = await client.call_tool(
        "cad_create_cylinder",
        {"radius": 5, "height": 12, "name": "Hole", "doc_name": "BracketDemo"},
    )
    p = r.get("parsed", {})
    print(f"  Object: {p.get('name')} ({p.get('type_id')})")

    # ── Step 4: Position the hole in center ─────────────────────────────────
    _print_step(4, "Position hole at center of base plate (40, 30, 0)")
    r = await client.call_tool(
        "cad_set_placement",
        {"object_name": "Hole", "x": 40, "y": 30, "z": -1, "doc_name": "BracketDemo"},
    )
    print(f"  Placement set: {r.get('parsed', {}).get('status')}")

    # ── Step 5: Boolean cut (base plate - hole) ─────────────────────────────
    _print_step(5, "Boolean cut: BasePlate - Hole")
    r = await client.call_tool(
        "cad_boolean_cut",
        {"base": "BasePlate", "tool": "Hole", "name": "BracketWithHole", "doc_name": "BracketDemo"},
    )
    p = r.get("parsed", {})
    print(f"  Result: {p.get('name')} ({p.get('type_id')})")

    # ── Step 6: Add fillet to edges ─────────────────────────────────────────
    _print_step(6, "Add fillet (radius 2 mm) to BracketWithHole")
    r = await client.call_tool(
        "cad_fillet_edges",
        {"object_name": "BracketWithHole", "radius": 2, "doc_name": "BracketDemo"},
    )
    p = r.get("parsed", {})
    print(f"  Result: {p.get('name')} ({p.get('type_id')})")

    # ── Step 7: Inspect final object ────────────────────────────────────────
    _print_step(7, "Inspect final object")
    r = await client.call_tool(
        "cad_inspect_object",
        {"object_name": "Fillet", "doc_name": "BracketDemo", "include_shape": True},
    )
    p = r.get("parsed", {})
    print(f"  Name: {p.get('name')}")
    print(f"  Type: {p.get('type_id')}")
    bb = p.get("bounding_box", {})
    if bb:
        print(f"  Bounds: X[{bb.get('min', [0])[0]:.1f}, {bb.get('max', [0])[0]:.1f}]  Y[{bb.get('min', [0])[1]:.1f}, {bb.get('max', [0])[1]:.1f}]  Z[{bb.get('min', [0])[2]:.1f}, {bb.get('max', [0])[2]:.1f}]")

    # ── Step 8: Mass properties ─────────────────────────────────────────────
    _print_step(8, "Compute mass properties")
    r = await client.call_tool(
        "cad_get_mass_properties",
        {"object_name": "Fillet", "doc_name": "BracketDemo", "density_kg_m3": 2700},
    )
    p = r.get("parsed", {})
    print(f"  Volume: {p.get('volume_mm3')} mm3")
    print(f"  Mass:   {p.get('mass_kg')} kg")
    cg = p.get("center_of_gravity_mm", [])
    if cg:
        print(f"  Center of Gravity: ({cg[0]}, {cg[1]}, {cg[2]}) mm")

    # ── Step 9: List all objects ────────────────────────────────────────────
    _print_step(9, "List all objects in document")
    r = await client.call_tool("cad_list_objects", {"doc_name": "BracketDemo"})
    objs = r.get("parsed", {}).get("objects", [])
    print(f"  Total objects: {len(objs)}")
    for obj in objs:
        print(f"    - {obj.get('name')} ({obj.get('type_id')})")

    # ── Step 10: Export ─────────────────────────────────────────────────────
    _print_step(10, "Export final geometry")
    fcstd_out = OUTPUT / "bracket_demo.fcstd"
    step_out = OUTPUT / "bracket_demo.step"
    stl_out = OUTPUT / "bracket_demo.stl"

    r1 = await client.call_tool("cad_export_fcstd", {"file_path": str(fcstd_out), "doc_name": "BracketDemo"})
    print(f"  FCStd: {r1.get('parsed', {}).get('status')} -> {fcstd_out}")

    r2 = await client.call_tool("cad_export_step", {"file_path": str(step_out), "doc_name": "BracketDemo"})
    print(f"  STEP:  {r2.get('parsed', {}).get('status')} -> {step_out}")

    r3 = await client.call_tool("cad_export_stl", {"file_path": str(stl_out), "doc_name": "BracketDemo"})
    print(f"  STL:   {r3.get('parsed', {}).get('status')} -> {stl_out}")

    await client.close()

    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print(f"\nAll files saved to: {OUTPUT}")
    print(f"  - bracket_demo.fcstd  (open in FreeCAD GUI)")
    print(f"  - bracket_demo.step   (CAD exchange format)")
    print(f"  - bracket_demo.stl    (3D print ready)")
    print("\nOpen 'bracket_demo.fcstd' in FreeCAD to see the full bracket.")


if __name__ == "__main__":
    asyncio.run(main())
