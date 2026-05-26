"""Debug script: probe FreeCAD state through MCP."""

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

    # Probe 1: list all documents
    print("=== Probe 1: list documents ===")
    r1 = await client.call_tool("cad_list_documents", {})
    print(json.dumps(r1.get("parsed"), indent=2, ensure_ascii=False)[:800])

    # Probe 2: create document and re-list
    print("\n=== Probe 2: create document ===")
    r2 = await client.call_tool("cad_create_document", {"name": "DebugDoc"})
    print(json.dumps(r2.get("parsed"), indent=2, ensure_ascii=False)[:400])

    print("\n=== Probe 3: list documents again ===")
    r3 = await client.call_tool("cad_list_documents", {})
    print(json.dumps(r3.get("parsed"), indent=2, ensure_ascii=False)[:800])

    # Probe 4: execute python to inspect state
    print("\n=== Probe 4: inspect FreeCAD state ===")
    r4 = await client.execute_python("""
import FreeCAD
_result_ = {
    "documents": [d.Name for d in FreeCAD.listDocuments().values()],
    "active_doc": FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None,
}
""")
    print(json.dumps(r4.get("parsed"), indent=2, ensure_ascii=False)[:800])

    # Probe 5: create box via python
    print("\n=== Probe 5: create box via execute_python ===")
    r5 = await client.execute_python("""
import FreeCAD
import Part
doc = FreeCAD.getDocument("DebugDoc")
box = doc.addObject("Part::Box", "MyBox")
box.Length = 10
box.Width = 20
box.Height = 30
doc.recompute()
_result_ = {"objects": [obj.Name for obj in doc.Objects]}
""")
    print(json.dumps(r5.get("parsed"), indent=2, ensure_ascii=False)[:800])

    # Probe 6: list objects in DebugDoc
    print("\n=== Probe 6: list objects in DebugDoc ===")
    r6 = await client.call_tool("cad_list_objects", {"doc_name": "DebugDoc"})
    print(json.dumps(r6.get("parsed"), indent=2, ensure_ascii=False)[:800])

    await client.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
