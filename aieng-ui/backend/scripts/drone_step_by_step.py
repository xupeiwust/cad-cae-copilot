"""Step-by-step drone creation in user's FreeCAD GUI via XML-RPC."""

from __future__ import annotations

import time
import xmlrpc.client

proxy = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)


def step(name: str, code: str, delay: float = 2.0) -> dict:
    print(f"\n>>> {name}")
    result = proxy.execute(code)
    ok = result.get("success")
    if ok:
        print(f"    OK")
    else:
        print(f"    FAILED: {result.get('error_message')}")
    time.sleep(delay)
    return result


# Step 0: Clear any existing Quadcopter document
step("Clear existing document", """
import FreeCAD
for name in list(FreeCAD.listDocuments().keys()):
    if "Quadcopter" in name:
        FreeCAD.closeDocument(name)
_result_ = "cleared"
""", delay=0.5)

# Step 1: Create document + Hub centered at origin
step("Step 1/11: Create document and central hub", """
import FreeCAD
doc = FreeCAD.newDocument("Quadcopter")
hub = doc.addObject("Part::Box", "Hub")
hub.Length = 30
hub.Width = 30
hub.Height = 12
hub.Placement.Base = FreeCAD.Vector(-15, -15, 0)
doc.recompute()
_result_ = {"doc": doc.Name, "hub": hub.Name}
""")

# Step 2: Arm 1 (0 degrees, along +X)
step("Step 2/11: Arm 1 - forward (+X)", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
arm = doc.addObject("Part::Box", "Arm_0")
arm.Length = 120
arm.Width = 12
arm.Height = 12
arm.Placement.Base = FreeCAD.Vector(15, -6, 0)
doc.recompute()
_result_ = {"arm": arm.Name, "pos": str(arm.Placement.Base)}
""")

# Step 3: Arm 2 (90 degrees, along +Y)
step("Step 3/11: Arm 2 - right (+Y)", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
arm = doc.addObject("Part::Box", "Arm_90")
arm.Length = 120
arm.Width = 12
arm.Height = 12
arm.Placement.Base = FreeCAD.Vector(-6, 15, 0)
arm.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 90)
doc.recompute()
_result_ = {"arm": arm.Name, "pos": str(arm.Placement.Base)}
""")

# Step 4: Arm 3 (180 degrees, along -X)
step("Step 4/11: Arm 3 - rear (-X)", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
arm = doc.addObject("Part::Box", "Arm_180")
arm.Length = 120
arm.Width = 12
arm.Height = 12
arm.Placement.Base = FreeCAD.Vector(-135, -6, 0)
arm.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 180)
doc.recompute()
_result_ = {"arm": arm.Name, "pos": str(arm.Placement.Base)}
""")

# Step 5: Arm 4 (270 degrees, along -Y)
step("Step 5/11: Arm 4 - left (-Y)", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
arm = doc.addObject("Part::Box", "Arm_270")
arm.Length = 120
arm.Width = 12
arm.Height = 12
arm.Placement.Base = FreeCAD.Vector(-6, -135, 0)
arm.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 270)
doc.recompute()
_result_ = {"arm": arm.Name, "pos": str(arm.Placement.Base)}
""")

# Step 6: Fuse all parts into FrameBody
step("Step 6/11: Fuse hub and arms", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
fuse = doc.addObject("Part::MultiFuse", "FrameBody")
fuse.Shapes = [
    doc.getObject("Hub"),
    doc.getObject("Arm_0"),
    doc.getObject("Arm_90"),
    doc.getObject("Arm_180"),
    doc.getObject("Arm_270"),
]
doc.recompute()
_result_ = {"fuse": fuse.Name, "volume": fuse.Shape.Volume}
""")

# Step 7: Motor hole 1 (forward, +X end)
step("Step 7/11: Motor hole 1 - forward", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
hole = doc.addObject("Part::Cylinder", "Hole_0")
hole.Radius = 4
hole.Height = 14
hole.Placement.Base = FreeCAD.Vector(135, 0, -1)
doc.recompute()
cut = doc.addObject("Part::Cut", "Cut_0")
cut.Base = doc.getObject("FrameBody")
cut.Tool = hole
doc.recompute()
_result_ = {"cut": cut.Name}
""")

# Step 8: Motor hole 2 (right, +Y end)
step("Step 8/11: Motor hole 2 - right", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
hole = doc.addObject("Part::Cylinder", "Hole_90")
hole.Radius = 4
hole.Height = 14
hole.Placement.Base = FreeCAD.Vector(0, 135, -1)
doc.recompute()
cut = doc.addObject("Part::Cut", "Cut_90")
cut.Base = doc.getObject("Cut_0")
cut.Tool = hole
doc.recompute()
_result_ = {"cut": cut.Name}
""")

# Step 9: Motor hole 3 (rear, -X end)
step("Step 9/11: Motor hole 3 - rear", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
hole = doc.addObject("Part::Cylinder", "Hole_180")
hole.Radius = 4
hole.Height = 14
hole.Placement.Base = FreeCAD.Vector(-135, 0, -1)
doc.recompute()
cut = doc.addObject("Part::Cut", "Cut_180")
cut.Base = doc.getObject("Cut_90")
cut.Tool = hole
doc.recompute()
_result_ = {"cut": cut.Name}
""")

# Step 10: Motor hole 4 (left, -Y end)
step("Step 10/11: Motor hole 4 - left", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
hole = doc.addObject("Part::Cylinder", "Hole_270")
hole.Radius = 4
hole.Height = 14
hole.Placement.Base = FreeCAD.Vector(0, -135, -1)
doc.recompute()
cut = doc.addObject("Part::Cut", "Cut_270")
cut.Base = doc.getObject("Cut_180")
cut.Tool = hole
doc.recompute()
_result_ = {"cut": cut.Name}
""")

# Step 11: Final recompute and rename final body
step("Step 11/11: Finalize", """
import FreeCAD
doc = FreeCAD.getDocument("Quadcopter")
doc.recompute()
final = doc.getObject("Cut_270")
bbox = final.Shape.BoundBox
_result_ = {
    "final_name": final.Name,
    "volume_mm3": round(final.Shape.Volume, 2),
    "bbox": {
        "x": [round(bbox.XMin, 1), round(bbox.XMax, 1)],
        "y": [round(bbox.YMin, 1), round(bbox.YMax, 1)],
        "z": [round(bbox.ZMin, 1), round(bbox.ZMax, 1)],
    }
}
""")

print("\n" + "=" * 60)
print("Drone frame complete!")
print("=" * 60)
print("Check your FreeCAD GUI — use Ctrl+2 (Fit all) if needed.")
