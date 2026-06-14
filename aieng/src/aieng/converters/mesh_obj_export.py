"""Neutral triangle-mesh (Wavefront OBJ) export for topology-optimization results.

The 3D smooth-mesh topology-optimization writeback emits a ``smooth_mesh_proxy``
Shape IR node (marching-cubes vertices + triangle faces). This module serializes
that mesh to a standalone **OBJ** file so the result is *file-ready* for
downstream mesh tools — notably the AMRTO/PYTOCAD mesh→NURBS reconstruction spike
(#149), whose first concrete enabler is exactly "a neutral mesh exporter for the
``smooth_mesh_proxy``" (it is the cheapest in-repo slice toward #204).

Honesty boundary: this is a mesh preview / reconstruction *input* — lossy,
mesh-derived, **not production CAD**.

Pure and dependency-free (no numpy / OCC); ``vertices`` / ``faces`` may be Python
lists or numpy arrays.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

TOPOLOGY_RESULT_MESH_OBJ_PATH = "geometry/topology_result_mesh.obj"

# Shape IR surface-mesh node kinds — mirrors shape_ir._SURFACE_MESH_KINDS.
_SURFACE_MESH_KINDS = {"surface_mesh", "smooth_mesh_proxy", "mesh_proxy", "triangle_mesh"}

_OBJ_HEADER = (
    "# aieng topology-optimization result mesh\n"
    "# reconstructed / mesh-derived / lossy — NOT production CAD"
)


def mesh_to_obj(vertices: Any, faces: Any, *, object_name: str = "topology_result") -> str:
    """Serialize a triangle (or polygon) mesh to Wavefront OBJ text.

    ``vertices`` is an iterable of ``(x, y, z)``; ``faces`` an iterable of
    vertex-index tuples (**0-based**; OBJ output is 1-based). Faces with fewer
    than 3 indices are skipped; n-gons are written as-is (OBJ supports them).
    Pure; no dependencies.
    """
    lines: list[str] = [_OBJ_HEADER, f"o {object_name}"]
    for v in vertices:
        lines.append(f"v {float(v[0]):.6f} {float(v[1]):.6f} {float(v[2]):.6f}")
    for f in faces:
        idx = [int(i) + 1 for i in f]
        if len(idx) >= 3:
            lines.append("f " + " ".join(str(i) for i in idx))
    return "\n".join(lines) + "\n"


def find_surface_mesh_node(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first Shape IR node carrying a renderable surface mesh, or None.

    Shape IR nodes live under ``parts`` (or legacy ``components``); a usable node
    has a surface-mesh ``type`` and non-empty ``vertices`` + ``faces``.
    """
    if not isinstance(payload, dict):
        return None
    nodes = payload.get("parts")
    if not isinstance(nodes, list):
        nodes = payload.get("components") if isinstance(payload.get("components"), list) else []
    for node in nodes:
        if (
            isinstance(node, dict)
            and node.get("type") in _SURFACE_MESH_KINDS
            and node.get("vertices")
            and node.get("faces")
        ):
            return node
    return None


def topology_result_mesh_obj(payload: dict[str, Any]) -> str | None:
    """OBJ text for the surface-mesh node in a Shape IR payload, or None if absent."""
    node = find_surface_mesh_node(payload)
    if node is None:
        return None
    return mesh_to_obj(node["vertices"], node["faces"], object_name=str(node.get("id") or "topology_result"))


def write_topology_result_mesh_obj(package_path: str | Path) -> dict[str, Any]:
    """Write ``geometry/topology_result_mesh.obj`` into a package from its Shape IR
    surface-mesh node (replacing any existing member).

    Returns ``{ok, obj_path, vertex_count, face_count}`` on success, or
    ``{ok: False, reason}`` when there is no Shape IR / no surface-mesh node /
    a read/write error. The OBJ is reconstructed/lossy mesh, not production CAD.
    """
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if "geometry/shape_ir.json" not in zf.namelist():
                return {"ok": False, "reason": "no_shape_ir"}
            payload = json.loads(zf.read("geometry/shape_ir.json").decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"read_failed: {type(exc).__name__}: {exc}"}

    node = find_surface_mesh_node(payload)
    if node is None:
        return {"ok": False, "reason": "no_surface_mesh_node"}

    data = mesh_to_obj(
        node["vertices"], node["faces"], object_name=str(node.get("id") or "topology_result")
    ).encode("utf-8")
    tmp = package_path.with_suffix(".objexport.tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != TOPOLOGY_RESULT_MESH_OBJ_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(TOPOLOGY_RESULT_MESH_OBJ_PATH, data)
        tmp.replace(package_path)
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return {"ok": False, "reason": f"write_failed: {type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "obj_path": TOPOLOGY_RESULT_MESH_OBJ_PATH,
        "vertex_count": len(node["vertices"]),
        "face_count": len(node["faces"]),
    }
