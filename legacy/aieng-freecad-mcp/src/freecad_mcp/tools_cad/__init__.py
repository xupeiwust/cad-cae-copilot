"""Core CAD tools for FreeCAD via the unified MCP server.

These are intentionally a focused subset sufficient for agent-driven modeling
and CAE hand-off, with truth-telling (bbox/volume/mass deltas) on every
mutation. More tools can be added incrementally.
"""

from __future__ import annotations

import base64
from typing import Any

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.guards import GuardResult, check_operation_allowed
from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    persist_standard_result_to_aieng,
)
from freecad_mcp.bridge.executor import CadExecutor
from freecad_mcp.contracts import ToolExecutionError
from freecad_mcp.contracts.failure_mode import classify_exception
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, StandardToolResult, TraceBlock
from freecad_mcp.tools_cad.models import CadBaseRequest, CadToolResponse


def _changes_block(obj_expr: str = "obj", density_kg_m3: float | None = None) -> str:
    """Return a code snippet that computes mutation effects."""
    mass_block = ""
    if density_kg_m3 is not None:
        mass_block = f'"mass_kg": round(float(shape.Volume * 1e-9 * {density_kg_m3}), 6),'
    else:
        mass_block = '"mass_kg": round(float(shape.Volume * 1e-9 * 2700.0), 6),'
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
    "center_of_gravity_mm": [
        round(float(shape.CenterOfMass.x), 3),
        round(float(shape.CenterOfMass.y), 3),
        round(float(shape.CenterOfMass.z), 3),
    ],
}}
"""


# ------------------------------------------------------------------
# .aieng context helpers
# ------------------------------------------------------------------

def _guard_rejected_response(tool_name: str, guard: GuardResult) -> CadToolResponse:
    from freecad_mcp.contracts.failure_mode import FailureDetail, FailureMode
    return CadToolResponse(
        status="rejected",
        operation=tool_name,
        claim_policy=ClaimPolicy(),
        failure_mode=FailureDetail(mode=FailureMode.GUARD_REJECTED, message="; ".join(guard.reasons) if guard.reasons else "Guard rejected"),
        warnings=guard.warnings,
        unsupported=guard.unsupported,
        errors=guard.reasons,
    )


def _maybe_persist(
    package_path: str | None,
    persist_to_aieng: bool,
    response: CadToolResponse,
) -> dict[str, Any] | None:
    if not persist_to_aieng or not package_path:
        return None
    try:
        result = StandardToolResult(
            status=response.status,
            operation=response.operation,
            inputs=response.inputs,
            outputs=response.outputs,
            artifacts_written=response.artifacts_written,
            evidence=response.evidence,
            claim_policy=response.claim_policy,
            trace=response.trace,
            warnings=response.warnings,
            unsupported=response.unsupported,
            errors=response.errors,
        )
        return persist_standard_result_to_aieng(package_path, result)
    except PersistenceError as exc:
        return {"error": str(exc), "error_code": "PERSISTENCE_FAILED", "persisted": False}


def _apply_persistence(
    response: CadToolResponse,
    persist_meta: dict[str, Any] | None,
) -> CadToolResponse:
    if persist_meta is not None:
        response.persistence = persist_meta
    return response


async def _execute_export_step(
    executor: CadExecutor,
    file_path: str,
    doc_name: str | None = None,
    object_names: list[str] | None = None,
    input_fcstd: str | None = None,
) -> dict[str, Any]:
    """Export objects to STEP format and return the raw result dict."""
    objs = object_names if object_names else []
    if input_fcstd:
        doc_line = f"doc = FreeCAD.open({input_fcstd!r})"
    else:
        doc_line = f"doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})"
    code = f"""
import FreeCAD
import Part
{doc_line}
if doc is None:
    raise ValueError("Document not found")
objects = []
if {objs!r}:
    for n in {objs!r}:
        obj = doc.getObject(n)
        if obj is not None and hasattr(obj, "Shape"):
            objects.append(obj)
else:
    for obj in doc.Objects:
        if hasattr(obj, "Shape"):
            objects.append(obj)
if not objects:
    raise ValueError("No exportable objects found")
if len(objects) == 1:
    shape = objects[0].Shape
else:
    shape = Part.makeCompound([obj.Shape for obj in objects])
shape.exportStep({file_path!r})
_result_ = {{"file_path": {file_path!r}, "object_count": len(objects)}}
"""
    resp = await executor.execute_async(code)
    if not resp.get("success", True):
        error = resp.get("error", "Unknown FreeCAD STEP export error")
        raise ToolExecutionError(error)
    return resp["result"]


async def _execute_export_fcstd(
    executor: CadExecutor,
    file_path: str,
    doc_name: str | None = None,
    input_fcstd: str | None = None,
) -> dict[str, Any]:
    """Save a FreeCAD document to FCStd and return the raw result dict."""
    if input_fcstd:
        doc_line = f"doc = FreeCAD.open({input_fcstd!r})"
    else:
        doc_line = f"doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})"
    code = f"""
import FreeCAD
{doc_line}
if doc is None:
    raise ValueError("Document not found")
doc.saveAs({file_path!r})
_result_ = {{"file_path": {file_path!r}, "document": doc.Name}}
"""
    resp = await executor.execute_async(code)
    if not resp.get("success", True):
        error = resp.get("error", "Unknown FreeCAD FCStd export error")
        raise ToolExecutionError(error)
    return resp["result"]


async def _execute_set_parameter(
    executor: CadExecutor,
    object_name: str,
    parameter_name: str,
    value: Any,
    doc_name: str | None = None,
    input_fcstd: str | None = None,
) -> dict[str, Any]:
    """Execute a parameter change in FreeCAD and return the raw result dict.

    This is the shared internal helper used by both ``cad_set_parameter``
    and the patch bridge. It builds the Python code string and calls the
    executor, keeping unsafe code generation in one place.
    """
    if input_fcstd:
        doc_line = f"doc = FreeCAD.open({input_fcstd!r})"
    else:
        doc_line = f"doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})"

    code = f"""
import FreeCAD
{doc_line}
if doc is None:
    raise ValueError("Document not found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if not hasattr(obj, {parameter_name!r}):
    raise ValueError(f"Parameter not found: {parameter_name!r}")
old_value = getattr(obj, {parameter_name!r})
# Coerce FreeCAD Quantity/App::Property to plain Python value for JSON serialization
try:
    if hasattr(old_value, "Value"):
        old_value = old_value.Value
except Exception:
    pass
setattr(obj, {parameter_name!r}, {value!r})
doc.recompute()
_result_ = {{
    "object_name": obj.Name,
    "parameter_name": {parameter_name!r},
    "old_value": old_value,
    "new_value": {value!r},
}}
"""
    resp = await executor.execute_async(code)
    if not resp.get("success", True):
        error = resp.get("error", "Unknown FreeCAD execution error")
        raise ToolExecutionError(error)
    return resp["result"]


def register_cad_tools(mcp: Any, executor: CadExecutor) -> None:
    """Register core CAD tools with the FastMCP server."""

    # ------------------------------------------------------------------
    # Meta / version
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_get_version(
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Get FreeCAD version and runtime info."""
        tool_name = "cad_get_version"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            result = await executor.get_version_async()
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            failure = classify_exception(exc)
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                failure_mode=failure,
                errors=[failure.message],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_create_document(name: str = "Unnamed", label: str | None = None) -> dict[str, Any]:
        """Create a new FreeCAD document."""
        code = f"""
import FreeCAD
doc = FreeCAD.newDocument({name!r})
if {label!r}:
    doc.Label = {label!r}
_result_ = {{"name": doc.Name, "label": doc.Label, "path": doc.FileName}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_save_document(doc_name: str | None = None, path: str | None = None) -> dict[str, Any]:
        """Save a FreeCAD document. If path is omitted, saves to existing FileName."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
if {path!r}:
    doc.saveAs({path!r})
else:
    doc.save()
_result_ = {{"name": doc.Name, "path": doc.FileName}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_close_document(doc_name: str | None = None, save_changes: bool = False) -> dict[str, Any]:
        """Close a FreeCAD document."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
if {save_changes}:
    doc.save()
name = doc.Name
FreeCAD.closeDocument(name)
_result_ = {{"closed": name}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_list_documents(
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """List all open FreeCAD documents."""
        tool_name = "cad_list_documents"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = """
import FreeCAD
_result_ = [
    {"name": d.Name, "label": d.Label, "path": d.FileName}
    for d in FreeCAD.listDocuments().values()
]
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                outputs={"documents": result},
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                documents=result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Object management
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_list_objects(
        doc_name: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """List all objects in a document."""
        tool_name = "cad_list_objects"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
_result_ = []
for obj in doc.Objects:
    info = {{"name": obj.Name, "label": obj.Label, "type_id": obj.TypeId}}
    if hasattr(obj, "ViewObject") and obj.ViewObject:
        info["visibility"] = obj.ViewObject.Visibility
    _result_.append(info)
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"doc_name": doc_name},
                outputs={"objects": result},
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                objects=result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"doc_name": doc_name},
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_inspect_object(
        object_name: str,
        doc_name: str | None = None,
        include_shape: bool = True,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Get detailed info about a FreeCAD object."""
        tool_name = "cad_inspect_object"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
info = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
}}
if {include_shape} and hasattr(obj, "Shape") and obj.Shape.isValid():
    shape = obj.Shape
    bbox = shape.BoundBox
    info["shape"] = {{
        "volume_mm3": round(float(shape.Volume), 3),
        "bbox": {{
            "xmin": float(bbox.XMin), "xmax": float(bbox.XMax),
            "ymin": float(bbox.YMin), "ymax": float(bbox.YMax),
            "zmin": float(bbox.ZMin), "zmax": float(bbox.ZMax),
        }},
        "center_of_gravity_mm": [
            round(float(shape.CenterOfMass.x), 3),
            round(float(shape.CenterOfMass.y), 3),
            round(float(shape.CenterOfMass.z), 3),
        ],
        "solid_count": len(shape.Solids),
        "face_count": len(shape.Faces),
        "edge_count": len(shape.Edges),
    }}
_result_ = info
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"object_name": object_name, "doc_name": doc_name, "include_shape": include_shape},
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"object_name": object_name, "doc_name": doc_name, "include_shape": include_shape},
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_delete_object(object_name: str, doc_name: str | None = None) -> dict[str, Any]:
        """Delete an object from a document."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
doc.removeObject(obj.Name)
doc.recompute()
_result_ = {{"deleted": {object_name!r}}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_set_placement(
        object_name: str,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        rotation: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set object position and rotation."""
        rot = rotation if rotation else [0, 0, 0]
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
obj.Placement.Base = FreeCAD.Vector({x}, {y}, {z})
if hasattr(obj, "Placement") and {rot!r}:
    obj.Placement.Rotation = FreeCAD.Rotation(*{rot!r})
doc.recompute()
{_changes_block('obj')}
_result_ = {{"name": obj.Name, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_create_box(
        length: float = 10.0,
        width: float = 10.0,
        height: float = 10.0,
        name: str = "Box",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part::Box primitive."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
box = doc.addObject("Part::Box", {name!r})
box.Length = {length}
box.Width = {width}
box.Height = {height}
doc.recompute()
{_changes_block('box')}
_result_ = {{"name": box.Name, "label": box.Label, "type_id": box.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_create_cylinder(
        radius: float = 5.0,
        height: float = 10.0,
        angle: float = 360.0,
        name: str = "Cylinder",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part::Cylinder primitive."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
cyl = doc.addObject("Part::Cylinder", {name!r})
cyl.Radius = {radius}
cyl.Height = {height}
cyl.Angle = {angle}
doc.recompute()
{_changes_block('cyl')}
_result_ = {{"name": cyl.Name, "label": cyl.Label, "type_id": cyl.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_create_sphere(
        radius: float = 5.0,
        name: str = "Sphere",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part::Sphere primitive."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
sph = doc.addObject("Part::Sphere", {name!r})
sph.Radius = {radius}
doc.recompute()
{_changes_block('sph')}
_result_ = {{"name": sph.Name, "label": sph.Label, "type_id": sph.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_create_cone(
        radius1: float = 5.0,
        radius2: float = 0.0,
        height: float = 10.0,
        name: str = "Cone",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part::Cone primitive."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
cone = doc.addObject("Part::Cone", {name!r})
cone.Radius1 = {radius1}
cone.Radius2 = {radius2}
cone.Height = {height}
doc.recompute()
{_changes_block('cone')}
_result_ = {{"name": cone.Name, "label": cone.Label, "type_id": cone.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # PartDesign
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_create_partdesign_body(
        name: str | None = None, doc_name: str | None = None
    ) -> dict[str, Any]:
        """Create a PartDesign::Body container."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
body_name = {name!r} or "Body"
body = doc.addObject("PartDesign::Body", body_name)
doc.recompute()
_result_ = {{"name": body.Name, "label": body.Label, "type_id": body.TypeId}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_create_sketch(
        body_name: str | None = None,
        plane: str = "XY_Plane",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Sketch attached to a PartDesign Body or standalone."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
sketch_name = {name!r} or "Sketch"
if {body_name!r}:
    body = doc.getObject({body_name!r})
    if body is None:
        raise ValueError(f"Body not found: {body_name!r}")
    sketch = body.newObject("Sketcher::SketchObject", sketch_name)
    plane = {plane!r}
    if plane in ["XY_Plane", "XZ_Plane", "YZ_Plane"]:
        plane_obj = body.Origin.getObject(plane)
        if hasattr(sketch, "AttachmentSupport"):
            sketch.AttachmentSupport = [(plane_obj, "")]
        else:
            sketch.Support = (plane_obj, [""])
        sketch.MapMode = "FlatFace"
else:
    sketch = doc.addObject("Sketcher::SketchObject", sketch_name)
    if {plane!r} == "XZ_Plane":
        sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(FreeCAD.Vector(1,0,0), 90))
    elif {plane!r} == "YZ_Plane":
        sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(FreeCAD.Vector(0,1,0), 90))
doc.recompute()
_result_ = {{"name": sketch.Name, "label": sketch.Label, "type_id": sketch.TypeId}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_pad_sketch(
        sketch_name: str,
        length: float,
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Pad (extrusion) from a sketch inside a PartDesign Body."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pad operation")
pad_name = {name!r} or "Pad"
pad = body.newObject("PartDesign::Pad", pad_name)
pad.Profile = sketch
pad.Length = {length}
pad.Symmetric = {symmetric}
pad.Reversed = {reversed}
doc.recompute()
{_changes_block('pad')}
_result_ = {{"name": pad.Name, "label": pad.Label, "type_id": pad.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_pocket_sketch(
        sketch_name: str,
        length: float,
        pocket_type: str = "Length",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Pocket (cut extrusion) from a sketch inside a PartDesign Body."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pocket operation")
pocket_name = {name!r} or "Pocket"
pocket = body.newObject("PartDesign::Pocket", pocket_name)
pocket.Profile = sketch
pocket.Length = {length}
pocket.Type = {pocket_type!r}
doc.recompute()
{_changes_block('pocket')}
_result_ = {{"name": pocket.Name, "label": pocket.Label, "type_id": pocket.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_fillet_edges(
        object_name: str,
        radius: float,
        edges: list[str] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add fillet (rounded edges) to an object."""
        edges_param = edges if edges else None
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break
selected_edges = {edges_param!r}
fillet_name = {name!r} or "Fillet"
if body:
    fillet = body.newObject("PartDesign::Fillet", fillet_name)
    fillet.Base = (obj, selected_edges if selected_edges else obj.Shape.Edges)
    fillet.Radius = {radius}
else:
    fillet = doc.addObject("Part::Fillet", fillet_name)
    fillet.Base = obj
    if selected_edges:
        edge_list = [(int(e.replace("Edge", "")), {radius}, {radius}) for e in selected_edges]
    else:
        edge_list = [(i+1, {radius}, {radius}) for i in range(len(obj.Shape.Edges))]
    fillet.Edges = edge_list
doc.recompute()
{_changes_block('fillet')}
_result_ = {{"name": fillet.Name, "label": fillet.Label, "type_id": fillet.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_chamfer_edges(
        object_name: str,
        size: float,
        edges: list[str] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add chamfer (beveled edges) to an object."""
        edges_param = edges if edges else None
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break
selected_edges = {edges_param!r}
chamfer_name = {name!r} or "Chamfer"
if body:
    chamfer = body.newObject("PartDesign::Chamfer", chamfer_name)
    chamfer.Base = (obj, selected_edges if selected_edges else obj.Shape.Edges)
    chamfer.Size = {size}
else:
    chamfer = doc.addObject("Part::Chamfer", chamfer_name)
    chamfer.Base = obj
    if selected_edges:
        edge_list = [(int(e.replace("Edge", "")), {size}, {size}) for e in selected_edges]
    else:
        edge_list = [(i+1, {size}, {size}) for i in range(len(obj.Shape.Edges))]
    chamfer.Edges = edge_list
doc.recompute()
{_changes_block('chamfer')}
_result_ = {{"name": chamfer.Name, "label": chamfer.Label, "type_id": chamfer.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Boolean operations
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_boolean_fuse(
        objects: list[str],
        name: str = "Fuse",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Fuse (union) multiple objects."""
        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
objs = [doc.getObject(n) for n in {objects!r}]
if None in objs:
    raise ValueError("One or more objects not found")
shape = objs[0].Shape
for o in objs[1:]:
    shape = shape.fuse(o.Shape)
fuse = doc.addObject("Part::Feature", {name!r})
fuse.Shape = shape
doc.recompute()
{_changes_block('fuse')}
_result_ = {{"name": fuse.Name, "label": fuse.Label, "type_id": fuse.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_boolean_cut(
        base: str,
        tool: str,
        name: str = "Cut",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Cut one object from another."""
        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
base_obj = doc.getObject({base!r})
tool_obj = doc.getObject({tool!r})
if base_obj is None or tool_obj is None:
    raise ValueError("Base or tool object not found")
shape = base_obj.Shape.cut(tool_obj.Shape)
cut = doc.addObject("Part::Feature", {name!r})
cut.Shape = shape
doc.recompute()
{_changes_block('cut')}
_result_ = {{"name": cut.Name, "label": cut.Label, "type_id": cut.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_boolean_common(
        objects: list[str],
        name: str = "Common",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Intersect (common) multiple objects."""
        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
objs = [doc.getObject(n) for n in {objects!r}]
if None in objs:
    raise ValueError("One or more objects not found")
shape = objs[0].Shape
for o in objs[1:]:
    shape = shape.common(o.Shape)
common = doc.addObject("Part::Feature", {name!r})
common.Shape = shape
doc.recompute()
{_changes_block('common')}
_result_ = {{"name": common.Name, "label": common.Label, "type_id": common.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_export_step(
        file_path: str,
        doc_name: str | None = None,
        object_names: list[str] | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Export objects to STEP format."""
        tool_name = "cad_export_step"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            result = await _execute_export_step(executor, file_path, doc_name, object_names)
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"file_path": file_path, "doc_name": doc_name, "object_names": object_names},
                outputs=result,
                artifacts_written=[file_path],
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"file_path": file_path, "doc_name": doc_name, "object_names": object_names},
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_export_stl(
        file_path: str,
        doc_name: str | None = None,
        object_names: list[str] | None = None,
        mesh_tolerance: float = 0.1,
    ) -> dict[str, Any]:
        """Export objects to STL format (3D printing)."""
        objs = object_names if object_names else []
        code = f"""
import FreeCAD
import Mesh
import MeshPart
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
objects = []
if {objs!r}:
    for n in {objs!r}:
        obj = doc.getObject(n)
        if obj is not None and hasattr(obj, "Shape"):
            objects.append(obj)
else:
    for obj in doc.Objects:
        if hasattr(obj, "Shape"):
            objects.append(obj)
if not objects:
    raise ValueError("No exportable objects found")
meshes = []
for obj in objects:
    mesh = MeshPart.meshFromShape(obj.Shape, LinearDeflection={mesh_tolerance})
    meshes.append(mesh)
if len(meshes) == 1:
    final_mesh = meshes[0]
else:
    final_mesh = Mesh.Mesh()
    for m in meshes:
        final_mesh.addMesh(m)
final_mesh.write({file_path!r})
_result_ = {{"file_path": {file_path!r}, "object_count": len(objects)}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_import_step(file_path: str, doc_name: str | None = None) -> dict[str, Any]:
        """Import a STEP file into FreeCAD."""
        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
Part.insert({file_path!r}, doc.Name)
doc.recompute()
imported = [obj.Name for obj in doc.Objects if obj.Name not in [o.Name for o in doc.Objects[:-1]]]
_result_ = {{"file_path": {file_path!r}, "imported_objects": imported}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Mass properties
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_get_mass_properties(
        doc_name: str | None = None,
        object_name: str | None = None,
        density_kg_m3: float = 2700.0,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Get mass properties (volume, mass, center of gravity) for an object."""
        tool_name = "cad_get_mass_properties"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
if {object_name!r}:
    obj = doc.getObject({object_name!r})
else:
    obj = None
    for o in doc.Objects:
        if hasattr(o, "Shape") and o.Shape.isValid():
            obj = o
            break
if obj is None or not hasattr(obj, "Shape"):
    raise ValueError("No valid object found")
shape = obj.Shape
volume = shape.Volume
mass = volume * 1e-9 * {density_kg_m3}
cog = shape.CenterOfMass
_result_ = {{
    "volume_mm3": round(volume, 3),
    "mass_kg": round(mass, 6),
    "center_of_gravity_mm": [round(float(cog.x), 3), round(float(cog.y), 3), round(float(cog.z), 3)],
    "density_kg_m3": {density_kg_m3},
    "object_name": obj.Name,
}}
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"doc_name": doc_name, "object_name": object_name, "density_kg_m3": density_kg_m3},
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"doc_name": doc_name, "object_name": object_name, "density_kg_m3": density_kg_m3},
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    # ------------------------------------------------------------------
    # View / Screenshot
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_get_screenshot(
        view_angle: str = "Isometric",
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Capture a screenshot of the FreeCAD 3D view.

        Requires GUI mode. Returns base64-encoded PNG if successful.
        """
        code = f"""
import FreeCAD
import base64
if not FreeCAD.GuiUp:
    raise RuntimeError("Screenshot requires FreeCAD GUI mode. Headless is not supported.")
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
FreeCAD.setActiveDocument(doc.Name)
gui_doc = FreeCAD.Gui.getDocument(doc.Name)
view = gui_doc.ActiveView
angle = {view_angle!r}
if angle == "Isometric":
    view.viewIsometric()
elif angle == "Front":
    view.viewFront()
elif angle == "Back":
    view.viewBack()
elif angle == "Top":
    view.viewTop()
elif angle == "Bottom":
    view.viewBottom()
elif angle == "Left":
    view.viewLeft()
elif angle == "Right":
    view.viewRight()
elif angle == "FitAll":
    view.fitAll()
img_path = FreeCAD.getUserAppDataDir() + "tmp_mcp_screenshot.png"
view.saveImage(img_path, {width}, {height})
with open(img_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
_result_ = {{"success": True, "format": "png", "width": {width}, "height": {height}, "data": b64}}
"""
        try:
            resp = await executor.execute_async(code)
            return resp["result"]
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def cad_set_view_angle(
        view_angle: str = "Isometric",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the 3D view angle."""
        code = f"""
import FreeCAD
if not FreeCAD.GuiUp:
    raise RuntimeError("View control requires FreeCAD GUI mode.")
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
FreeCAD.setActiveDocument(doc.Name)
gui_doc = FreeCAD.Gui.getDocument(doc.Name)
view = gui_doc.ActiveView
angle = {view_angle!r}
if angle == "Isometric":
    view.viewIsometric()
elif angle == "Front":
    view.viewFront()
elif angle == "Back":
    view.viewBack()
elif angle == "Top":
    view.viewTop()
elif angle == "Bottom":
    view.viewBottom()
elif angle == "Left":
    view.viewLeft()
elif angle == "Right":
    view.viewRight()
elif angle == "FitAll":
    view.fitAll()
_result_ = {{"success": True, "angle": angle}}
"""
        try:
            resp = await executor.execute_async(code)
            return resp["result"]
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Sketch geometry
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_add_sketch_line(
        sketch_name: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        construction: bool = False,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a line to a sketch."""
        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
idx = sketch.addGeometry(Part.LineSegment(FreeCAD.Vector({x1}, {y1}, 0), FreeCAD.Vector({x2}, {y2}, 0)), {construction})
doc.recompute()
_result_ = {{"geometry_index": idx, "geometry_count": sketch.GeometryCount}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_add_sketch_arc(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        start_angle: float,
        end_angle: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add an arc to a sketch."""
        code = f"""
import FreeCAD
import Part
import math
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
center = FreeCAD.Vector({center_x}, {center_y}, 0)
arc = Part.ArcOfCircle(Part.Circle(center, FreeCAD.Vector(0,0,1), {radius}), math.radians({start_angle}), math.radians({end_angle}))
idx = sketch.addGeometry(arc, False)
doc.recompute()
_result_ = {{"geometry_index": idx, "geometry_count": sketch.GeometryCount}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_add_sketch_circle(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a circle to a sketch."""
        code = f"""
import FreeCAD
import Part
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
idx = sketch.addGeometry(Part.Circle(FreeCAD.Vector({center_x}, {center_y}, 0), FreeCAD.Vector(0,0,1), {radius}), False)
doc.recompute()
_result_ = {{"geometry_index": idx, "geometry_count": sketch.GeometryCount}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_add_sketch_rectangle(
        sketch_name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a rectangle to a sketch."""
        code = f"""
import FreeCAD
import Part
import Sketcher
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")
x0, y0, w, h = {x}, {y}, {width}, {height}
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x0, y0, 0), FreeCAD.Vector(x0+w, y0, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x0+w, y0, 0), FreeCAD.Vector(x0+w, y0+h, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x0+w, y0+h, 0), FreeCAD.Vector(x0, y0+h, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x0, y0+h, 0), FreeCAD.Vector(x0, y0, 0)), False)
n = sketch.GeometryCount - 4
sketch.addConstraint(Sketcher.Constraint("Coincident", n, 2, n+1, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", n+1, 2, n+2, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", n+2, 2, n+3, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", n+3, 2, n, 1))
doc.recompute()
_result_ = {{"geometry_count": sketch.GeometryCount, "constraint_count": sketch.ConstraintCount}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Patterns & Mirror
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_linear_pattern(
        feature_name: str,
        direction: str = "X",
        length: float = 50.0,
        occurrences: int = 3,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a linear pattern of a PartDesign feature."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")
pattern_name = {name!r} or "LinearPattern"
pattern = body.newObject("PartDesign::LinearPattern", pattern_name)
pattern.Originals = [feature]
pattern.Length = {length}
pattern.Occurrences = {occurrences}
dir_name = {direction!r}
pattern.Direction = (body.Origin.getObject(f"{{dir_name}}_Axis"), [""])
doc.recompute()
{_changes_block('pattern')}
_result_ = {{"name": pattern.Name, "label": pattern.Label, "type_id": pattern.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_polar_pattern(
        feature_name: str,
        axis: str = "Z",
        angle: float = 360.0,
        occurrences: int = 6,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a polar (circular) pattern of a PartDesign feature."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")
pattern_name = {name!r} or "PolarPattern"
pattern = body.newObject("PartDesign::PolarPattern", pattern_name)
pattern.Originals = [feature]
pattern.Angle = {angle}
pattern.Occurrences = {occurrences}
axis_name = {axis!r}
pattern.Axis = (body.Origin.getObject(f"{{axis_name}}_Axis"), [""])
doc.recompute()
{_changes_block('pattern')}
_result_ = {{"name": pattern.Name, "label": pattern.Label, "type_id": pattern.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_mirror_feature(
        feature_name: str,
        plane: str = "XY",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Mirror a PartDesign feature across a plane."""
        plane_map = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}
        plane_ref = plane_map.get(plane, "XY_Plane")
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")
mirror_name = {name!r} or "Mirrored"
mirror = body.newObject("PartDesign::Mirrored", mirror_name)
mirror.Originals = [feature]
mirror.MirrorPlane = (body.Origin.getObject({plane_ref!r}), [""])
doc.recompute()
{_changes_block('mirror')}
_result_ = {{"name": mirror.Name, "label": mirror.Label, "type_id": mirror.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Loft & Sweep
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_loft_sketches(
        sketch_names: list[str],
        solid: bool = True,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a loft through multiple sketches inside a PartDesign Body."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketches = [doc.getObject(n) for n in {sketch_names!r}]
if None in sketches:
    raise ValueError("One or more sketches not found")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketches[0] in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body")
loft_name = {name!r} or "Loft"
loft = body.newObject("PartDesign::AdditiveLoft", loft_name)
loft.Sections = sketches
loft.Solid = {solid}
doc.recompute()
{_changes_block('loft')}
_result_ = {{"name": loft.Name, "label": loft.Label, "type_id": loft.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_sweep_sketch(
        profile_sketch: str,
        spine_sketch: str,
        solid: bool = True,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Sweep a profile sketch along a spine sketch inside a PartDesign Body."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
profile = doc.getObject({profile_sketch!r})
spine = doc.getObject({spine_sketch!r})
if profile is None or spine is None:
    raise ValueError("Profile or spine sketch not found")
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and profile in obj.Group:
            body = obj
            break
if body is None:
    raise ValueError("Profile must be inside a PartDesign Body")
sweep_name = {name!r} or "Sweep"
sweep = body.newObject("PartDesign::AdditivePipe", sweep_name)
sweep.Section = profile
spine_edge = spine.Shape.Edges[0] if spine.Shape.Edges else None
if spine_edge is None:
    raise ValueError("Spine sketch has no edges")
sweep.Spine = (spine, ["Edge1"])
sweep.Solid = {solid}
doc.recompute()
{_changes_block('sweep')}
_result_ = {{"name": sweep.Name, "label": sweep.Label, "type_id": sweep.TypeId, "changes": changes}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Spreadsheet (parametric design)
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_create_spreadsheet(
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Spreadsheet for parametric design."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")
sheet_name = {name!r} or "Spreadsheet"
sheet = doc.addObject("Spreadsheet::Sheet", sheet_name)
doc.recompute()
_result_ = {{"name": sheet.Name, "label": sheet.Label, "type_id": sheet.TypeId}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_set_spreadsheet_cell(
        spreadsheet_name: str,
        cell: str,
        value: str | int | float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set a spreadsheet cell value (number, string, or formula starting with '=')."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")
val = {value!r}
if isinstance(val, str) and val.startswith("="):
    sheet.set({cell!r}, val)
else:
    sheet.set({cell!r}, val)
doc.recompute()
_result_ = {{"cell": {cell!r}, "value": val, "computed": sheet.get({cell!r})}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_get_spreadsheet_value(
        spreadsheet_name: str,
        cell: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get the computed value of a spreadsheet cell."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")
_result_ = {{"cell": {cell!r}, "value": sheet.get({cell!r}), "display": sheet.getContents({cell!r})}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    # ------------------------------------------------------------------
    # Display & Workbench
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_set_object_color(
        object_name: str,
        r: int = 200,
        g: int = 200,
        b: int = 200,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set object color (RGB 0-255). Requires GUI mode."""
        code = f"""
import FreeCAD
if not FreeCAD.GuiUp:
    raise RuntimeError("Color setting requires FreeCAD GUI mode.")
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
gui_doc = FreeCAD.Gui.getDocument(doc.Name)
gui_obj = gui_doc.getObject(obj.Name)
if gui_obj and hasattr(gui_obj, "ShapeColor"):
    gui_obj.ShapeColor = ({r}/255.0, {g}/255.0, {b}/255.0)
_result_ = {{"object": obj.Name, "color": [{r}, {g}, {b}]}}
"""
        try:
            resp = await executor.execute_async(code)
            return resp["result"]
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def cad_set_display_mode(
        object_name: str,
        mode: str = "Shaded",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set object display mode: Shaded, Wireframe, Points, Flat Lines."""
        code = f"""
import FreeCAD
if not FreeCAD.GuiUp:
    raise RuntimeError("Display mode requires FreeCAD GUI mode.")
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
gui_doc = FreeCAD.Gui.getDocument(doc.Name)
gui_obj = gui_doc.getObject(obj.Name)
if gui_obj and hasattr(gui_obj, "DisplayMode"):
    gui_obj.DisplayMode = {mode!r}
_result_ = {{"object": obj.Name, "display_mode": {mode!r}}}
"""
        try:
            resp = await executor.execute_async(code)
            return resp["result"]
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def cad_set_object_visibility(
        object_name: str,
        visible: bool = True,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Show or hide an object."""
        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if FreeCAD.GuiUp and hasattr(obj, "ViewObject") and obj.ViewObject:
    obj.ViewObject.Visibility = {visible}
_result_ = {{"object": obj.Name, "visible": {visible}}}
"""
        resp = await executor.execute_async(code)
        return resp["result"]

    @mcp.tool()
    async def cad_activate_workbench(workbench_name: str) -> dict[str, Any]:
        """Activate a FreeCAD workbench.

        Common workbenches: PartWorkbench, PartDesignWorkbench, SketcherWorkbench,
        DraftWorkbench, MeshWorkbench, SpreadsheetWorkbench, FemWorkbench.
        """
        code = f"""
import FreeCAD
import FreeCADGui
if FreeCAD.GuiUp:
    FreeCADGui.activateWorkbench({workbench_name!r})
    _result_ = {{"success": True, "workbench": {workbench_name!r}}}
else:
    _result_ = {{"success": False, "error": "GUI not available"}}
"""
        try:
            resp = await executor.execute_async(code)
            return resp["result"]
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Parameters & Recompute
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_list_parameters(
        doc_name: str | None = None,
        object_name: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """List all editable parameters of a FreeCAD document or object."""
        tool_name = "cad_list_parameters"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
target_obj = None
if {object_name!r}:
    target_obj = doc.getObject({object_name!r})
    if target_obj is None:
        raise ValueError(f"Object not found: {object_name!r}")
objects = [target_obj] if target_obj else doc.Objects
param_types = [
    "App::PropertyFloat", "App::PropertyLength", "App::PropertyAngle",
    "App::PropertyInteger", "App::PropertyString", "App::PropertyBool",
    "App::PropertyQuantity", "App::PropertyFloatConstraint",
    "App::PropertyIntegerConstraint", "App::PropertyPercent",
]
params = []
for obj in objects:
    obj_params = {{"object_name": obj.Name, "object_label": obj.Label, "parameters": []}}
    for prop in obj.PropertiesList:
        if obj.getTypeIdOfProperty(prop) in param_types:
            try:
                val = getattr(obj, prop)
                obj_params["parameters"].append({{
                    "name": prop,
                    "value": val,
                    "type": obj.getTypeIdOfProperty(prop),
                }})
            except Exception:
                pass
    if obj_params["parameters"]:
        params.append(obj_params)
_result_ = {{"parameters": params}}
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"doc_name": doc_name, "object_name": object_name},
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"doc_name": doc_name, "object_name": object_name},
                claim_policy=ClaimPolicy(),
                errors=[f"{{type(exc).__name__}}: {{exc}}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_get_parameter(
        object_name: str,
        parameter_name: str,
        doc_name: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Get the current value of a single parameter on a FreeCAD object."""
        tool_name = "cad_get_parameter"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if not hasattr(obj, {parameter_name!r}):
    raise ValueError(f"Parameter not found: {parameter_name!r}")
val = getattr(obj, {parameter_name!r})
ptype = obj.getTypeIdOfProperty({parameter_name!r}) if {parameter_name!r} in obj.PropertiesList else "unknown"
_result_ = {{
    "object_name": obj.Name,
    "parameter_name": {parameter_name!r},
    "value": val,
    "type": ptype,
}}
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"object_name": object_name, "parameter_name": parameter_name, "doc_name": doc_name},
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"object_name": object_name, "parameter_name": parameter_name, "doc_name": doc_name},
                claim_policy=ClaimPolicy(),
                errors=[f"{{type(exc).__name__}}: {{exc}}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_set_parameter(
        object_name: str,
        parameter_name: str,
        value: Any,
        doc_name: str | None = None,
        input_fcstd: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Set a parameter value on a FreeCAD object and recompute.

        This is a CAD modification operation. In .aieng-enhanced mode,
        semantic-only features and protected regions are rejected.
        """
        tool_name = "cad_set_parameter"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id or object_name, is_modification=True)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            result = await _execute_set_parameter(executor, object_name, parameter_name, value, doc_name, input_fcstd)
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"object_name": object_name, "parameter_name": parameter_name, "value": value, "doc_name": doc_name, "input_fcstd": input_fcstd},
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"object_name": object_name, "parameter_name": parameter_name, "value": value, "doc_name": doc_name, "input_fcstd": input_fcstd},
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_recompute_document(
        doc_name: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Recompute a FreeCAD document and report success or failure."""
        tool_name = "cad_recompute_document"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("Document not found")
try:
    doc.recompute()
    failed_features = [obj.Name for obj in doc.Objects if hasattr(obj, "isValid") and not obj.isValid()]
    _result_ = {{"success": True, "document": doc.Name, "failed_features": failed_features}}
except Exception as e:
    _result_ = {{"success": False, "error": str(e), "document": doc.Name}}
"""
        try:
            resp = await executor.execute_async(code)
            result = resp["result"]
            status = "success" if result.get("success") else "failed"
            response = CadToolResponse(
                status=status,
                operation=tool_name,
                inputs={"doc_name": doc_name},
                outputs=result,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"doc_name": doc_name},
                claim_policy=ClaimPolicy(),
                errors=[f"{{type(exc).__name__}}: {{exc}}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cad_export_fcstd(
        file_path: str,
        doc_name: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Save a FreeCAD document to an FCStd file."""
        tool_name = "cad_export_fcstd"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CadToolResponse(
                status="rejected",
                operation=tool_name,
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            result = await _execute_export_fcstd(executor, file_path, doc_name)
            response = CadToolResponse(
                status="success",
                operation=tool_name,
                inputs={"file_path": file_path, "doc_name": doc_name},
                outputs=result,
                artifacts_written=[file_path],
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                **result,
            )
        except Exception as exc:
            response = CadToolResponse(
                status="failed",
                operation=tool_name,
                inputs={"file_path": file_path, "doc_name": doc_name},
                claim_policy=ClaimPolicy(),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Python execution
    # ------------------------------------------------------------------

    @mcp.tool()
    async def cad_execute_python(code: str, doc_name: str | None = None) -> dict[str, Any]:
        """Execute arbitrary Python code inside FreeCAD."""
        if doc_name:
            code = f"""
import FreeCAD
doc = FreeCAD.getDocument({doc_name!r})
FreeCAD.setActiveDocument(doc.Name)
""" + code
        resp = await executor.execute_async(code)
        return {
            "success": resp.get("success", False),
            "result": resp.get("result"),
            "stdout": resp.get("stdout", ""),
            "stderr": resp.get("stderr", ""),
            "error": resp.get("error_message") or resp.get("error_traceback"),
        }
