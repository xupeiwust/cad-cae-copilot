"""Shape IR → NURBS B-Rep (build123d + OCP) source compiler.

Fourth compile target for Shape IR. Produces smooth NURBS B-spline surfaces as
exact OpenCASCADE B-Rep — the "NURBS / B-Rep surfaces" capability — *without* a
new dependency or runner: it emits build123d source that builds the surfaces via
the already-installed OCP kernel and binds ``result``, so the existing build123d
runner exports STEP/STL/GLB and extracts REAL per-face B-Rep topology (each NURBS
patch is its own pickable face). That's the analytic-face advantage over the mesh
backends (SDF/Manifold), which only yield one region face.

NURBS-surface nodes (``nurbs_surface`` / ``bspline_surface`` / ``surface`` /
``patch``) carry a ``control_net`` (a 2-D grid of ``[x, y, z]`` points); the
surface is fitted with ``GeomAPI_PointsToBSplineSurface``. Any other node kind
falls back to the build123d primitive compiler, so a model may mix NURBS patches
with primitives/lofts.
"""
from __future__ import annotations

from typing import Any

from .shape_ir import (
    _color,
    _compile_node,
    _node_id,
    _node_kind,
    _py,
    _shape_nodes,
    _slug,
    _transform_lines,
)

_NURBS_KINDS = {"nurbs_surface", "bspline_surface", "surface", "patch", "nurbs", "nurbs_patch"}

# Emitted into the generated source; runs in the build123d runner (OCP present).
_NURBS_HELPER = '''\
def _nurbs_face(control_net, label=None, color=None):
    """Fit a NURBS B-spline surface through a grid of control points and return
    a build123d Face wrapping the OCP B-Rep face."""
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.gp import gp_Pnt
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    rows = len(control_net)
    cols = len(control_net[0])
    arr = TColgp_Array2OfPnt(1, rows, 1, cols)
    for i in range(rows):
        for j in range(cols):
            p = control_net[i][j]
            arr.SetValue(i + 1, j + 1, gp_Pnt(float(p[0]), float(p[1]), float(p[2])))
    surface = GeomAPI_PointsToBSplineSurface(arr).Surface()
    topo_face = BRepBuilderAPI_MakeFace(surface, 1e-6).Face()
    face = Face(topo_face)
    if label:
        face.label = label
    if color is not None:
        face.color = Color(*color)
    return face'''


def compile_shape_ir_to_nurbs_source(payload: dict[str, Any]) -> str:
    """Compile Shape IR into build123d source that builds NURBS B-Rep surfaces.

    Binds ``result`` (a build123d Face/Compound). Executed by the build123d
    runner — no separate runtime.
    """
    nodes = _shape_nodes(payload)
    lines = [
        "from build123d import *",
        "",
        "# Generated from AIENG Shape IR (representation: nurbs_brep).",
        "# NURBS B-Rep surfaces built via OCP; executed by the build123d runner",
        "# (exact STEP + per-face B-Rep topology). Only writes source; does not run.",
        "",
        _NURBS_HELPER,
        "",
        "parts = []",
        "",
    ]
    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        var = f"part_{_slug(node_id)}"
        if _node_kind(node) in _NURBS_KINDS:
            lines.extend(_compile_nurbs_node(node, index, var))
        else:
            # Reuse the build123d primitive compiler so NURBS patches can mix
            # with primitives / lofts in one model.
            lines.extend(_compile_node(node, index, var, compiled_vars={}))
        lines.append(f"parts.append({var})")
        lines.append("")
    lines.extend([
        "if len(parts) == 1:",
        "    result = parts[0]",
        "else:",
        "    result = Compound(children=parts)",
        "",
    ])
    return "\n".join(lines)


def _compile_nurbs_node(node: dict[str, Any], index: int, var: str) -> list[str]:
    node_id = _node_id(node, index)
    label = str(node.get("label") or node.get("name") or node_id)
    color = _color(node)
    control_net = (
        node.get("control_net")
        or node.get("control_points")
        or node.get("points")
        or node.get("net")
    )
    lines = [f"# Shape IR NURBS node: {node_id}"]
    if (
        isinstance(control_net, list) and len(control_net) >= 2
        and isinstance(control_net[0], list) and len(control_net[0]) >= 2
    ):
        lines.append(f"{var} = _nurbs_face({_py(control_net)}, label={_py(label)}, color={_py(color)})")
    else:
        # No usable control net -> bbox proxy so the model still builds.
        lines.append("# (no valid control_net grid; bbox proxy)")
        lines.append(f"{var} = _aieng_finish(Box(10, 10, 1), label={_py(label)}, color={_py(color)})")
    lines.extend(_transform_lines(var, node))
    return lines
