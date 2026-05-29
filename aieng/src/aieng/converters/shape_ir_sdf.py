"""Shape IR → implicit SDF source compiler.

Second compile target for Shape IR (the first is build123d / B-Rep). This emits
Python for the `fogleman/sdf` library (signed-distance functions meshed via
marching cubes), which is the right representation for irregular / organic /
lattice shapes that are awkward to author as constructive B-Rep.

Like the build123d compiler, this only WRITES source — it does not execute the
SDF runtime or mesh anything. The aieng workbench SDF runner (separate slice)
executes the generated source and produces mesh/GLB evidence.

Target API (fogleman/sdf): `sphere(r)`, `box((w,l,h))`, `rounded_box(size, r)`,
`capped_cylinder(a, b, r)`, `capsule(a, b, r)`, `ellipsoid((a,b,c))`; boolean
`|` / `&` / `-`; smooth `a.union(b, k=...)`; `.translate((x,y,z))`. `X`/`Y`/`Z`
are unit-vector constants.
"""
from __future__ import annotations

from typing import Any

from .shape_ir import (
    _blend_child_ids,
    _dims,
    _node_id,
    _node_kind,
    _number,
    _py,
    _shape_nodes,
    _slug,
    _bbox,
)


# Node kinds this compiler can represent as native SDF primitives. Kinds outside
# this set (loft / sweep / revolve) are better served by the build123d target and
# fall back to a bounding-box proxy here so the model still meshes.
_SDF_PRIMITIVES = {
    "sphere", "box", "bbox", "rounded_box", "cylinder", "tube",
    "capped_cylinder", "capsule", "ellipsoid",
}


def compile_shape_ir_to_sdf_source(payload: dict[str, Any]) -> str:
    """Compile Shape IR declarations into fogleman/sdf Python source.

    The script binds the final field to ``f`` (the SDF runner calls
    ``f.save(...)``). Node ``operation`` selects how each part combines with the
    accumulated field: ``union`` (default), ``subtract``, ``intersect``. An
    ``organic_blend`` node smooth-unions its referenced children (``k`` = blend
    radius).
    """
    nodes = _shape_nodes(payload)
    lines = [
        "from sdf import *",
        "",
        "# Generated from AIENG Shape IR (representation: implicit_sdf).",
        "# This compiler only writes source; it does not execute the SDF runtime.",
        "# Execute with the aieng SDF runner to mesh (marching cubes) -> STL/GLB.",
        "",
    ]

    blend_child_ids = _blend_child_ids(nodes)
    compiled_vars: dict[str, str] = {}
    placed: list[tuple[str, str]] = []  # (var, op) for top-level combination
    pending_blends: list[tuple[dict[str, Any], str, int]] = []

    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        var = f"f_{_slug(node_id)}"
        if _node_kind(node) == "organic_blend":
            # Defer only the assignment LINES until the children vars exist; the
            # placement (fold order) is recorded now to preserve IR source order.
            pending_blends.append((node, var, index))
        else:
            lines.extend(_compile_sdf_node(node, index, var))
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


def _compile_sdf_node(node: dict[str, Any], index: int, var: str) -> list[str]:
    node_id = _node_id(node, index)
    expr = _sdf_expression(node) or _sdf_bbox_expression(node)
    out = [f"# Shape IR node: {node_id}", f"{var} = {expr}"]
    out.extend(_sdf_transform(var, node))
    return out


def _compile_blend_node(
    node: dict[str, Any], index: int, var: str, compiled_vars: dict[str, str],
) -> list[str]:
    node_id = _node_id(node, index)
    refs = node.get("children", node.get("solids", node.get("inputs", [])))
    child_vars = [compiled_vars.get(str(ref)) for ref in refs] if isinstance(refs, list) else []
    child_vars = [v for v in child_vars if v]
    k = _number(node, "radius", "blend_radius", default=1.0)
    if not child_vars:
        # Nothing resolvable to blend — degrade to a bbox proxy so the model still meshes.
        expr = _sdf_bbox_expression(node)
        out = [f"# Shape IR node: {node_id} (organic_blend: no resolvable children, bbox proxy)", f"{var} = {expr}"]
        out.extend(_sdf_transform(var, node))
        return out
    head, *rest = child_vars
    if rest:
        expr = f"{head}.union({', '.join(rest)}, k={k})"
    else:
        expr = head
    out = [f"# Shape IR node: {node_id} (organic_blend, smooth k={k})", f"{var} = {expr}"]
    out.extend(_sdf_transform(var, node))
    return out


def _sdf_expression(node: dict[str, Any]) -> str | None:
    kind = _node_kind(node)
    params = dict(node.get("parameters") or {}) if isinstance(node.get("parameters"), dict) else {}
    d = {**params, **node}

    if kind == "sphere":
        r = _number(d, "radius", default=None)
        if r is not None:
            return f"sphere({r})"

    if kind in {"box", "bbox"}:
        dims = _dims(d)
        if dims is not None:
            return f"box(({dims[0]}, {dims[1]}, {dims[2]}))"

    if kind == "rounded_box":
        dims = _dims(d)
        radius = _number(d, "radius", "fillet_radius", default=0.0)
        if dims is not None:
            return f"rounded_box(({dims[0]}, {dims[1]}, {dims[2]}), {radius})"

    if kind in {"cylinder", "tube", "capped_cylinder"}:
        r = _number(d, "radius", default=None)
        h = _number(d, "height", "length", default=None)
        if r is not None and h is not None:
            return f"capped_cylinder(-Z * {h / 2}, Z * {h / 2}, {r})"

    if kind == "capsule":
        r = _number(d, "radius", default=None)
        length = _number(d, "length", "height", default=None)
        if r is not None and length is not None:
            return f"capsule(-Z * {length / 2}, Z * {length / 2}, {r})"

    if kind == "ellipsoid":
        dims = _dims(d)
        if dims is not None:
            return f"ellipsoid(({dims[0] / 2}, {dims[1] / 2}, {dims[2] / 2}))"

    return None


def _sdf_bbox_expression(node: dict[str, Any]) -> str:
    dims = _dims(node) or [10.0, 10.0, 10.0]
    return f"box(({dims[0]}, {dims[1]}, {dims[2]}))"


def _sdf_transform(var: str, node: dict[str, Any]) -> list[str]:
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
    if translation is None:
        return []
    return [f"{var} = {var}.translate({_py(translation)})"]


def _op(node: dict[str, Any]) -> str:
    op = str(node.get("operation") or node.get("op") or "union").lower()
    if op in {"subtract", "difference", "cut"}:
        return "subtract"
    if op in {"intersect", "intersection", "common"}:
        return "intersect"
    return "union"


def _combine_line(placed: list[tuple[str, str]]) -> str:
    if not placed:
        return "f = sphere(1)  # empty Shape IR — placeholder field"
    combined = placed[0][0]
    for var, op in placed[1:]:
        if op == "subtract":
            combined = f"({combined} - {var})"
        elif op == "intersect":
            combined = f"({combined} & {var})"
        else:
            combined = f"({combined} | {var})"
    return f"f = {combined}"
