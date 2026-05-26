"""Test cad_create_box code snippet directly via execute_python."""

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


def _changes_block(obj_expr: str = "obj", density_kg_m3: float | None = None) -> str:
    mass_block = ""
    if density_kg_m3 is not None:
        mass_block = f"mass = shape.Volume * 1e-9 * {density_kg_m3},"
    else:
        mass_block = "mass = shape.Volume * 1e-9 * 2700.0,"
    return f"""
shape = {obj_expr}.Shape
bbox = shape.BoundBox
changes = {{
    "bbox": {{
        "xmin": float(bbox.XMin),
        "xmax": float(bbox.XMax),
        "ymin": float(bbox.YMin),
        "ymax": float(bbox.YMax),
        "zmin": float(bbox.ZMin),
        "zmax": float(bbox.ZMax),
    }},
    "volume_mm3": round(float(shape.Volume), 3),
    {mass_block}
}}
"""


async def main() -> None:
    client = FreeCADMCPClient(
        freecad_mcp_root=FREECAD_MCP_ROOT,
        freecad_path=FREECAD_HOME / "bin",
        mode="embedded",
        python_executable=FREECAD_PYTHON,
    )
    await client.start()

    # create doc
    await client.call_tool("cad_create_document", {"name": "BoxDoc2"})

    code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if "BoxDoc2" is None else FreeCAD.getDocument("BoxDoc2")
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
box = doc.addObject("Part::Box", "TestBox")
box.Length = 10
box.Width = 20
box.Height = 30
doc.recompute()
{_changes_block('box')}
_result_ = {{"name": box.Name, "label": box.Label, "type_id": box.TypeId, "changes": changes}}
"""
    print("CODE:")
    print(code)
    print("---")

    r = await client.execute_python(code)
    print("execute_python result:")
    print(json.dumps(r.get("parsed"), indent=2)[:800])

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
