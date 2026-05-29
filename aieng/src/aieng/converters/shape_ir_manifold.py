"""Shape IR → manifold3d (mesh CSG) source compiler.

Third compile target for Shape IR. Emits Python for `manifold3d` — a fast,
guaranteed-manifold mesh boolean kernel. Where SDF excels at smooth/organic
fields, Manifold excels at robust hard-edged constructive solid geometry on
meshes, and supports native rotation. Like the other compilers this only WRITES
source; the workbench Manifold runner executes it and meshes via trimesh.

Target API (manifold3d): `Manifold.sphere(r)`, `Manifold.cube((x,y,z), center)`,
`Manifold.cylinder(h, r_low, r_high, segments, center)`; booleans `+` (union),
`-` (difference), `^` (intersection); `.translate((x,y,z))`, `.rotate((rx,ry,rz))`
(degrees), `.scale((x,y,z))`. The final solid is bound to `result`.
"""
from __future__ import annotations

from typing import Any

from .shape_ir import (
    _bbox,
    _blend_child_ids,
    _dims,
    _node_id,
    _node_kind,
    _number,
    _py,
    _shape_nodes,
    _slug,
)


def compile_shape_ir_to_manifold_source(payload: dict[str, Any]) -> str:
    """Compile Shape IR declarations into manifold3d Python source.

    Binds the final solid to ``result`` (a Manifold). Node ``operation`` selects
    how each part combines: ``union`` (default, ``+``), ``subtract`` (``-``),
    ``intersect`` (``^``). Manifold has no smooth blend, so ``organic_blend`` is a
    plain union of its children (use the implicit_sdf target for smooth fillets).
    """
    nodes = _shape_nodes(payload)
    lines = [
        "from manifold3d import Manifold",
        "",
        "# Generated from AIENG Shape IR (representation: manifold_mesh).",
        "# This compiler only writes source; it does not execute the manifold runtime.",
        "# Execute with the aieng Manifold runner to mesh -> STL/GLB.",
        "",
    ]

    blend_child_ids = _blend_child_ids(nodes)
    compiled_vars: dict[str, str] = {}
    placed: list[tuple[str, str]] = []
    pending_blends: list[tuple[dict[str, Any], str, int]] = []

    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        var = f"m_{_slug(node_id)}"
        if _node_kind(node) == "organic_blend":
            pending_blends.append((node, var, index))
        else:
            lines.extend(_compile_manifold_node(node, index, var))
            lines.append("")
            compiled_vars[node_id] = var
        if node_id not in blend_child_ids or bool(node.get("emit", False)):
            placed.append((var, _op(node)))

    for node, var, index in pending_blends:
        lines.extend(_compile_blend_node(node, index, var, compiled_vars))
        lines.append("")
        compiled_vars[_node_id(node, index)] = var

    lines.append(_combine_line(placed))
    lines.append("")
    return "\n".join(lines)


def _compile_manifold_node(node: dict[str, Any], index: int, var: str) -> list[str]:
    node_id = _node_id(node, index)
    expr = _manifold_expression(node) or _manifold_bbox_expression(node)
    out = [f"# Shape IR node: {node_id}", f"{var} = {expr}"]
    out.extend(_manifold_transform(var, node))
    return out


def _compile_blend_node(
    node: dict[str, Any], index: int, var: str, compiled_vars: dict[str, str],
) -> list[str]:
    node_id = _node_id(node, index)
    refs = node.get("children", node.get("solids", node.get("inputs", [])))
    child_vars = [compiled_vars.get(str(ref)) for ref in refs] if isinstance(refs, list) else []
    child_vars = [v for v in child_vars if v]
    if not child_vars:
        expr = _manifold_bbox_expression(node)
        out = [f"# Shape IR node: {node_id} (organic_blend: no resolvable children, bbox proxy)", f"{var} = {expr}"]
        out.extend(_manifold_transform(var, node))
        return out
    expr = " + ".join(child_vars)  # manifold has no smooth blend -> plain union
    out = [
        f"# Shape IR node: {node_id} (organic_blend -> plain union; manifold has no smooth k)",
        f"{var} = {expr}",
    ]
    out.extend(_manifold_transform(var, node))
    return out


def _manifold_expression(node: dict[str, Any]) -> str | None:
    kind = _node_kind(node)
    params = dict(node.get("parameters") or {}) if isinstance(node.get("parameters"), dict) else {}
    d = {**params, **node}

    if kind == "sphere":
        r = _number(d, "radius", default=None)
        if r is not None:
            return f"Manifold.sphere({r})"

    if kind in {"box", "bbox", "rounded_box"}:
        dims = _dims(d)
        if dims is not None:
            # manifold has no native rounded cube; rounded_box falls back to a cube.
            return f"Manifold.cube(({dims[0]}, {dims[1]}, {dims[2]}), True)"

    if kind in {"cylinder", "tube", "capsule"}:
        r = _number(d, "radius", default=None)
        h = _number(d, "height", "length", default=None)
        if r is not None and h is not None:
            # capsule approximated as a cylinder (no spherical caps in this MVP).
            return f"Manifold.cylinder({h}, {r}, {r}, 0, True)"

    if kind in {"tapered_cylinder", "cone"}:
        rb = _number(d, "bottom_radius", "r_bot", "radius_bottom", default=None)
        rt = _number(d, "top_radius", "r_top", "radius_top", default=None)
        h = _number(d, "height", "length", default=None)
        if rb is not None and rt is not None and h is not None:
            return f"Manifold.cylinder({h}, {rb}, {rt}, 0, True)"

    if kind == "ellipsoid":
        dims = _dims(d)
        if dims is not None:
            return f"Manifold.sphere(1.0).scale(({dims[0] / 2}, {dims[1] / 2}, {dims[2] / 2}))"

    return None


def _manifold_bbox_expression(node: dict[str, Any]) -> str:
    dims = _dims(node) or [10.0, 10.0, 10.0]
    return f"Manifold.cube(({dims[0]}, {dims[1]}, {dims[2]}), True)"


def _manifold_transform(var: str, node: dict[str, Any]) -> list[str]:
    out: list[str] = []
    # Rotate first (about origin), then translate — orient-in-place, then place.
    rotation_val = node.get("rotation")
    if isinstance(rotation_val, list) and len(rotation_val) == 3:
        try:
            rot = tuple(float(v) for v in rotation_val)
            out.append(f"{var} = {var}.rotate({_py(rot)})")
        except (TypeError, ValueError):
            pass
    loc = node.get("location", node.get("position", node.get("translate")))
    translation: tuple[float, float, float] | None = None
    if isinstance(loc, list) and len(loc) == 3:
        try:
            translation = tuple(float(v) for v in loc)
        except (TypeError, ValueError):
            translation = None
    elif (bbox := _bbox(node)) is not None:
        cx = (bbox[0] + bbox[3]) / 2
        cy = (bbox[1] + bbox[4]) / 2
        cz = (bbox[2] + bbox[5]) / 2
        if any(abs(v) > 1e-9 for v in (cx, cy, cz)):
            translation = (cx, cy, cz)
    if translation is not None:
        out.append(f"{var} = {var}.translate({_py(translation)})")
    return out


def _op(node: dict[str, Any]) -> str:
    op = str(node.get("operation") or node.get("op") or "union").lower()
    if op in {"subtract", "difference", "cut"}:
        return "subtract"
    if op in {"intersect", "intersection", "common"}:
        return "intersect"
    return "union"


def _combine_line(placed: list[tuple[str, str]]) -> str:
    if not placed:
        return "result = Manifold.sphere(1.0)  # empty Shape IR — placeholder solid"
    combined = placed[0][0]
    for var, op in placed[1:]:
        if op == "subtract":
            combined = f"({combined} - {var})"
        elif op == "intersect":
            combined = f"({combined} ^ {var})"
        else:
            combined = f"({combined} + {var})"
    return f"result = {combined}"
