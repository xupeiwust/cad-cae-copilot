"""Shape IR reference converter.

This converter makes an agent-authored intermediate shape description a first
class `.aieng` source.  It is deliberately conservative: it does not run a CAD
kernel, mesher, solver, optimizer, or geometry compiler.  Instead it records the
Shape IR, projects its declared parts into AI-readable topology/feature/object
resources, and preserves explicit provenance/coverage so downstream tools know
which claims are only semantic intent.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from aieng import FORMAT_VERSION

from .base import (
    CAPABILITY_LEVEL_NAMES,
    ConversionResult,
    ConverterCapabilityProfile,
    ConverterError,
    CoverageCategory,
    EmittedResource,
    SupportedLevel,
    UncertaintyNote,
    UnsupportedItem,
)


SHAPE_IR_SOURCE_PATH = "geometry/shape_ir.json"
BUILD123D_SOURCE_PATH = "geometry/source.py"
SHAPE_IR_SDF_SOURCE_PATH = "geometry/sdf_source.py"
SHAPE_IR_MANIFOLD_SOURCE_PATH = "geometry/manifold_source.py"
TOPOLOGY_MAP_PATH = "geometry/topology_map.json"
FEATURE_GRAPH_PATH = "graph/feature_graph.json"
OBJECT_REGISTRY_PATH = "objects/object_registry.json"

_FEATURE_TYPES = {
    "base_plate",
    "mounting_hole",
    "mounting_hole_pattern",
    "rib",
    "fillet",
    "chamfer",
    "boss",
    "flange",
    "interface_face",
    "unknown_feature",
}


class ShapeIRConverter:
    """Convert a lightweight Shape IR JSON file into semantic `.aieng` resources."""

    converter_id = "shape_ir_reference"
    source_system = "AIENG Shape IR"
    display_name = "AIENG Shape IR reference converter"
    converter_version = "0.1"

    def capability_profile(self) -> ConverterCapabilityProfile:
        levels = (
            SupportedLevel(level=0, name=CAPABILITY_LEVEL_NAMES[0]),
            SupportedLevel(
                level=1,
                name=CAPABILITY_LEVEL_NAMES[1],
                notes=(
                    "Topology is projected from Shape IR declarations, not parsed from exact B-Rep.",
                    "Face/edge/body IDs are stable for the Shape IR node IDs.",
                ),
            ),
            SupportedLevel(level=2, name=CAPABILITY_LEVEL_NAMES[2]),
            SupportedLevel(
                level=3,
                name=CAPABILITY_LEVEL_NAMES[3],
                notes=("Feature roles are Shape IR intent, not CAD-kernel feature recognition.",),
            ),
            SupportedLevel(
                level=4,
                name=CAPABILITY_LEVEL_NAMES[4],
                notes=("Parameters are semantic Shape IR parameters; no CAD write-back is implied.",),
            ),
        )
        return ConverterCapabilityProfile(
            converter_id=self.converter_id,
            source_system=self.source_system,
            supported_levels=levels,
            display_name=self.display_name,
            converter_version=self.converter_version,
            source_file_extensions=(".shape.json", ".shape_ir.json", ".json"),
            notes=(
                "Reference converter for agent-authored Shape IR.",
                "No CAD kernel, mesher, solver, optimizer, or geometry compiler is executed.",
            ),
        )

    def convert(
        self,
        source_path: Path,
        *,
        model_id: str,
        runtime_mode: str = "auto",
        options: Mapping[str, Any] | None = None,
    ) -> ConversionResult:
        _ = options
        if not source_path.exists():
            raise ConverterError(f"source file does not exist: {source_path}")
        if not source_path.is_file():
            raise ConverterError(f"source path is not a file: {source_path}")

        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConverterError(f"Shape IR source is not valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ConverterError("Shape IR source must be a JSON object")

        nodes = _shape_nodes(payload)
        if not nodes:
            raise ConverterError("Shape IR source must contain a non-empty 'parts' or 'components' array")

        source_bytes = source_path.read_bytes()
        sha = hashlib.sha256(source_bytes).hexdigest()

        topology_map = _build_topology_map(payload, nodes)
        feature_graph = _build_feature_graph(payload, nodes)
        object_registry = _build_object_registry(nodes, topology_map, feature_graph)
        compiled = compile_shape_ir(payload)
        representation = compiled["representation"]
        compiled_source_path = compiled["source_path"]  # geometry/source.py | geometry/sdf_source.py
        readme = _build_readme(payload, source_path, nodes)

        package_files: dict[str, bytes] = {
            SHAPE_IR_SOURCE_PATH: (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(),
            compiled_source_path: compiled["source"].encode(),
            TOPOLOGY_MAP_PATH: (json.dumps(topology_map, indent=2, sort_keys=True) + "\n").encode(),
            FEATURE_GRAPH_PATH: (json.dumps(feature_graph, indent=2, sort_keys=True) + "\n").encode(),
            OBJECT_REGISTRY_PATH: (json.dumps(object_registry, indent=2, sort_keys=True) + "\n").encode(),
            "README_FOR_AI.md": readme.encode(),
        }

        emitted = [
            EmittedResource(path=SHAPE_IR_SOURCE_PATH, kind="geometry", level=0),
            EmittedResource(
                path=compiled_source_path,
                kind="geometry",
                level=4,
                notes=(
                    f"Generated {compiled['runtime']} source ({representation}); "
                    "not executed by this converter.",
                ),
            ),
            EmittedResource(path=TOPOLOGY_MAP_PATH, kind="topology", level=1),
            EmittedResource(path=FEATURE_GRAPH_PATH, kind="feature_graph", level=3),
            EmittedResource(path=OBJECT_REGISTRY_PATH, kind="object_registry", level=2),
        ]

        has_parameters = any(isinstance(node.get("parameters"), dict) and node["parameters"] for node in nodes)
        declared_levels = (
            SupportedLevel(level=0, name=CAPABILITY_LEVEL_NAMES[0]),
            SupportedLevel(level=1, name=CAPABILITY_LEVEL_NAMES[1]),
            SupportedLevel(level=2, name=CAPABILITY_LEVEL_NAMES[2]),
            SupportedLevel(level=3, name=CAPABILITY_LEVEL_NAMES[3]),
            SupportedLevel(level=4, name=CAPABILITY_LEVEL_NAMES[4]),
        )
        achieved_levels = declared_levels if has_parameters else declared_levels[:-1]

        unsupported = [
            UnsupportedItem(
                category="geometry",
                status="missing",
                description=(
                    "Shape IR conversion records semantic topology intent only. "
                    "Compile the Shape IR through a CAD backend to produce exact STEP/B-Rep geometry."
                ),
            ),
            UnsupportedItem(
                category="mesh",
                status="missing",
                description="No mesh/GLB preview is generated by the Shape IR reference converter.",
            ),
            UnsupportedItem(
                category="writeback_strategy",
                status="unsupported",
                description="Round-trip CAD write-back is not emitted by the reference Shape IR converter.",
            ),
        ]

        uncertainty = [
            UncertaintyNote(
                scope="topology_extraction",
                description=(
                    "Topology entities are projected from Shape IR declarations; they are not "
                    "validated against B-Rep, mesh, or manufacturing geometry."
                ),
            )
        ]

        return ConversionResult(
            model_id=model_id,
            converter_id=self.converter_id,
            source_system=self.source_system,
            converter_version=self.converter_version,
            display_name=self.display_name,
            runtime_mode="offline",
            source_filename=source_path.name,
            source_byte_size=source_path.stat().st_size,
            source_content_sha256=sha,
            source_document_metadata={
                "shape_ir_format_version": str(payload.get("format_version", "")),
                "declared_model_id": str(payload.get("model_id", "")),
                "node_count": len(nodes),
                "representation": representation,
                "requested_representation": compiled["requested_representation"],
                "compile_runtime": compiled["runtime"],
                "representation_fallback": compiled["fallback"],
                "compiled_source_path": compiled_source_path,
                "build123d_source_emitted": representation == "brep_build123d",
            },
            declared_levels=declared_levels,
            achieved_levels=tuple(achieved_levels),
            emitted_resources=emitted,
            unsupported=unsupported,
            uncertainty=uncertainty,
            coverage_categories=_build_coverage_categories(nodes, has_parameters=has_parameters),
            package_files=package_files,
            notes=(
                f"Converted from Shape IR via {self.converter_id}.",
                "Generated build123d source.py, but did not execute a CAD kernel.",
                "No solver, mesher, optimizer, CAD edit, or CAD kernel compilation was executed.",
            ),
        )


def _shape_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("parts", payload.get("components", []))
    if not isinstance(raw, list):
        return []
    return [node for node in raw if isinstance(node, dict)]


# ── compile-target registry + dispatch ───────────────────────────────────────
# Shape IR is the source; each registered representation compiles to a different
# backend's source (a different evidence level): build123d/OCP -> exact B-Rep
# STEP; implicit_sdf -> fogleman/sdf marching-cubes mesh; manifold_mesh ->
# manifold3d CSG mesh. New targets (COMPAS-OCC NURBS, topology optimization)
# register here as plug-ins — no edits to the dispatcher.
_COMPILER_REGISTRY: dict[str, dict[str, Any]] = {}


def register_compiler(
    representation: str,
    *,
    compiler: Any,
    source_path: str,
    runtime: str,
    aliases: tuple[str, ...] = (),
) -> None:
    """Register a Shape IR compile target. ``compiler`` is ``payload -> source str``."""
    entry = {"compiler": compiler, "source_path": source_path, "runtime": runtime, "canonical": representation}
    _COMPILER_REGISTRY[representation] = entry
    for alias in aliases:
        _COMPILER_REGISTRY[alias] = dict(entry)  # canonical stays the registered name


def available_representations() -> list[str]:
    """Canonical representation names that have a registered compiler."""
    return sorted({entry["canonical"] for entry in _COMPILER_REGISTRY.values()})


def representation_runtime(representation: str) -> str:
    """The runtime that executes a representation's generated source
    ('build123d', 'sdf', 'manifold', ...). Unknown representations default to
    build123d. Lets callers route execution by runtime rather than name."""
    entry = _COMPILER_REGISTRY.get(str(representation).lower())
    return str(entry["runtime"]) if entry else "build123d"


def resolve_representation(payload_or_name: Any) -> dict[str, Any]:
    """Resolve a requested representation (or a Shape IR payload) to
    ``{representation, requested_representation, runtime, source_path, fallback}``
    WITHOUT compiling. Unknown requests resolve to build123d with fallback=True."""
    if isinstance(payload_or_name, dict):
        requested = shape_ir_representation(payload_or_name)
    else:
        requested = str(payload_or_name or "brep_build123d").lower()
    entry = _COMPILER_REGISTRY.get(requested)
    if entry is None:
        brep = _COMPILER_REGISTRY.get("brep_build123d", {})
        return {
            "representation": "brep_build123d",
            "requested_representation": requested,
            "runtime": str(brep.get("runtime", "build123d")),
            "source_path": str(brep.get("source_path", BUILD123D_SOURCE_PATH)),
            "fallback": True,
        }
    return {
        "representation": entry["canonical"],
        "requested_representation": requested,
        "runtime": entry["runtime"],
        "source_path": entry["source_path"],
        "fallback": False,
    }


def shape_ir_representation(payload: dict[str, Any]) -> str:
    """The requested compile target, lower-cased. Defaults to build123d B-Rep."""
    return str(payload.get("representation") or payload.get("target") or "brep_build123d").lower()


def compile_shape_ir(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch Shape IR to its representation's registered compiler.

    Returns ``{representation, requested_representation, source, source_path,
    runtime, fallback}``. Unknown representations fall back to build123d and set
    ``fallback=True`` so callers can record the substitution honestly.
    """
    requested = shape_ir_representation(payload)
    entry = _COMPILER_REGISTRY.get(requested)
    fallback = entry is None
    if entry is None:
        entry = _COMPILER_REGISTRY["brep_build123d"]
    return {
        "representation": entry["canonical"],
        "requested_representation": requested,
        "source": entry["compiler"](payload),
        "source_path": entry["source_path"],
        "runtime": entry["runtime"],
        "fallback": fallback,
    }


def _compile_sdf(payload: dict[str, Any]) -> str:
    from .shape_ir_sdf import compile_shape_ir_to_sdf_source
    return compile_shape_ir_to_sdf_source(payload)


def _compile_manifold(payload: dict[str, Any]) -> str:
    from .shape_ir_manifold import compile_shape_ir_to_manifold_source
    return compile_shape_ir_to_manifold_source(payload)


def _compile_nurbs(payload: dict[str, Any]) -> str:
    from .shape_ir_nurbs import compile_shape_ir_to_nurbs_source
    return compile_shape_ir_to_nurbs_source(payload)


def compile_shape_ir_to_build123d_source(payload: dict[str, Any]) -> str:
    """Compile Shape IR declarations into build123d source without executing it.

    The generated script is intended for the workbench build123d runner, which
    injects high-level helpers such as `lofted_stack`, `capsule`, and
    `swept_tube`.  Primitive fallback code is still normal build123d Python.
    """
    nodes = _shape_nodes(payload)
    lines = [
        "from build123d import *",
        "",
        "# Generated from AIENG Shape IR.",
        "# This converter only writes source; it does not execute build123d.",
        "# Execute with the aieng workbench runner to inject helpers like lofted_stack/capsule.",
        "",
        "parts = []",
        "",
    ]

    compiled_vars: dict[str, str] = {}
    pending_blends: list[tuple[int, dict[str, Any], str]] = []
    blend_child_ids = _blend_child_ids(nodes)

    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        var_name = f"part_{_slug(node_id)}"
        if _node_kind(node) == "organic_blend":
            pending_blends.append((index, node, var_name))
            continue
        lines.extend(_compile_node(node, index, var_name))
        if node_id not in blend_child_ids or bool(node.get("emit", False)):
            lines.append(f"parts.append({var_name})")
        lines.append("")
        compiled_vars[node_id] = var_name

    for index, node, var_name in pending_blends:
        lines.extend(_compile_node(node, index, var_name, compiled_vars=compiled_vars))
        lines.append(f"parts.append({var_name})")
        lines.append("")
        compiled_vars[_node_id(node, index)] = var_name

    lines.extend([
        "if len(parts) == 1:",
        "    result = parts[0]",
        "else:",
        "    result = Compound(children=parts)",
        "",
    ])
    return "\n".join(lines)


def _blend_child_ids(nodes: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for node in nodes:
        if _node_kind(node) != "organic_blend":
            continue
        refs = node.get("children", node.get("solids", node.get("inputs", [])))
        if isinstance(refs, list):
            ids.update(str(ref) for ref in refs)
    return ids


def _compile_node(
    node: dict[str, Any],
    index: int,
    var_name: str,
    *,
    compiled_vars: dict[str, str] | None = None,
) -> list[str]:
    node_id = _node_id(node, index)
    label = str(node.get("label") or node.get("id") or node.get("name") or node_id)
    kind = _node_kind(node)
    params = dict(node.get("parameters") or {}) if isinstance(node.get("parameters"), dict) else {}
    merged = {**params, **node}
    color = _color(node)

    if kind in _DENSITY_VOXEL_KINDS:
        return _compile_density_voxels_b123d(node, node_id, var_name, label, color)

    transform = _transform_lines(var_name, node)

    expr = _build_expression(kind, merged, label, color, compiled_vars=compiled_vars or {})
    if expr is None:
        expr = _bbox_expression(node, label, color)

    lines = [
        f"# Shape IR node: {node_id}",
        f"{var_name} = {expr}",
    ]
    lines.extend(transform)
    return lines


def _compile_density_voxels_b123d(
    node: dict[str, Any],
    node_id: str,
    var_name: str,
    label: str,
    color: list[float] | None,
) -> list[str]:
    """build123d source for a density-field node: a Compound of extruded voxel boxes.

    The cells are grouped under one labelled Compound so the topology carries a
    single named part (the optimized body) rather than hundreds of anonymous solids.
    """
    cells, (sx, sy, sz) = density_voxel_cells(node)
    slug = _slug(node_id)
    lines = [
        f"# Shape IR node: {node_id} (density_voxels -> {len(cells)} solid cells, extruded {sz})",
        f"_cells_{slug} = {_py(cells)}",
        f"_boxes_{slug} = [_aieng_finish(Box({sx}, {sy}, {sz})).moved(Location((c[0], c[1], c[2]))) "
        f"for c in _cells_{slug}]",
        f"if _boxes_{slug}:",
        f"    {var_name} = Compound(children=_boxes_{slug})",
        f"else:",
        f"    {var_name} = _aieng_finish(Box(0.001, 0.001, 0.001))",
        f"{var_name}.label = {_py(label)}",
    ]
    if color is not None:
        lines.append(f"{var_name}.color = Color(*{_py(color)})")
    return lines


def _node_kind(node: dict[str, Any]) -> str:
    return str(
        node.get("operation")
        or node.get("primitive")
        or node.get("shape")
        or node.get("type")
        or node.get("kind")
        or node.get("surface_type")
        or "bbox"
    ).lower()


# Node kinds that carry a thresholded density field (topology-optimization
# writeback). Each compiler expands the solid cells into extruded voxel boxes.
_DENSITY_VOXEL_KINDS = {"density_voxels", "optimized_topology", "voxel_field"}


def density_voxel_cells(node: dict[str, Any]) -> tuple[list[list[float]], tuple[float, float, float]]:
    """Expand a density-field node into solid voxel cell centres + cell size.

    The 2D density grid (``density[j][i]``: rows = y, cols = x) is thresholded;
    every cell at/above ``threshold`` becomes a box centred in the XY plane and
    extruded along Z by ``thickness`` (default = the larger in-plane cell edge).
    Cells are placed relative to ``origin``. Returns ``(centres, (sx, sy, sz))``
    where each centre is ``[cx, cy, cz]`` — the position is baked in, so callers
    must NOT additionally apply the node transform.
    """
    density = node.get("density") or node.get("density_grid") or []
    if isinstance(density, dict):
        density = density.get("values") or []
    threshold = float(node.get("threshold", 0.5))
    cell = node.get("cell_size") or [1.0, 1.0]
    sx = float(cell[0])
    sy = float(cell[1] if len(cell) > 1 else cell[0])
    sz = float(node.get("thickness", node.get("depth", max(sx, sy))))
    origin = node.get("origin") or [0.0, 0.0, 0.0]
    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    cells: list[list[float]] = []
    for j, row in enumerate(density):
        for i, value in enumerate(row):
            try:
                solid = float(value) >= threshold
            except (TypeError, ValueError):
                solid = False
            if solid:
                cells.append([
                    round(ox + (i + 0.5) * sx, 6),
                    round(oy + (j + 0.5) * sy, 6),
                    round(oz + sz / 2.0, 6),
                ])
    return cells, (sx, sy, sz)


def _build_expression(
    kind: str,
    data: dict[str, Any],
    label: str,
    color: list[float] | None,
    *,
    compiled_vars: dict[str, str],
) -> str | None:
    color_kw = f", color={_py(color)}" if color is not None else ""
    label_kw = f"label={_py(label)}"

    if kind in {"lofted_stack", "loft", "freeform", "bspline"}:
        sections = data.get("sections")
        if isinstance(sections, list) and len(sections) >= 2:
            return f"lofted_stack({_py(sections)}, {label_kw}{color_kw})"

    if kind in {"rounded_box", "box", "bbox"}:
        dims = _dims(data)
        if dims is None:
            return None
        radius = _number(data, "radius", "fillet_radius", default=0.0)
        if kind == "rounded_box" or radius > 0:
            return f"rounded_box({dims[0]}, {dims[1]}, {dims[2]}, {radius}, {label_kw}{color_kw})"
        return f"_aieng_finish(Box({dims[0]}, {dims[1]}, {dims[2]}), {label_kw}{color_kw})"

    if kind == "capsule":
        radius = _number(data, "radius", default=None)
        length = _number(data, "length", "height", default=None)
        if radius is not None and length is not None:
            axis = str(data.get("axis") or "Z").upper()
            return f"capsule({radius}, {length}, axis={_py(axis)}, {label_kw}{color_kw})"

    if kind in {"cylinder", "tube"}:
        radius = _number(data, "radius", default=None)
        height = _number(data, "height", "length", default=None)
        if radius is not None and height is not None:
            return f"_aieng_finish(Cylinder({radius}, {height}), {label_kw}{color_kw})"

    if kind in {"tapered_cylinder", "cone"}:
        bottom = _number(data, "bottom_radius", "r_bot", "radius_bottom", default=None)
        top = _number(data, "top_radius", "r_top", "radius_top", default=None)
        height = _number(data, "height", "length", default=None)
        if bottom is not None and top is not None and height is not None:
            return f"tapered_cylinder({bottom}, {top}, {height}, {label_kw}{color_kw})"

    if kind == "sphere":
        radius = _number(data, "radius", default=None)
        if radius is not None:
            return f"_aieng_finish(Sphere({radius}), {label_kw}{color_kw})"

    if kind in {"swept_tube", "sweep"}:
        path_points = data.get("path_points", data.get("path"))
        radius = _number(data, "radius", default=None)
        if isinstance(path_points, list) and radius is not None:
            return f"swept_tube({_py(path_points)}, {radius}, {label_kw}{color_kw})"

    if kind in {"revolved_profile", "revolve"}:
        profile_points = data.get("profile_points", data.get("profile"))
        if isinstance(profile_points, list):
            return f"revolved_profile({_py(profile_points)}, {label_kw}{color_kw})"

    if kind == "organic_blend":
        refs = data.get("children", data.get("solids", data.get("inputs", [])))
        if isinstance(refs, list):
            var_refs = [compiled_vars.get(str(ref)) for ref in refs]
            var_refs = [ref for ref in var_refs if ref]
            radius = _number(data, "radius", "blend_radius", default=1.0)
            if var_refs:
                return f"organic_blend([{', '.join(var_refs)}], {radius}, {label_kw}{color_kw})"

    return None


def _bbox_expression(node: dict[str, Any], label: str, color: list[float] | None) -> str:
    dims = _dims(node) or [10.0, 10.0, 10.0]
    color_kw = f", color={_py(color)}" if color is not None else ""
    return f"_aieng_finish(Box({dims[0]}, {dims[1]}, {dims[2]}), label={_py(label)}{color_kw})"


def _transform_lines(var_name: str, node: dict[str, Any]) -> list[str]:
    # Resolve translation: explicit location/position/translate, else bbox centre.
    translation: tuple[float, float, float] | None = None
    loc = node.get("location", node.get("position", node.get("translate")))
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

    rotation: tuple[float, float, float] | None = None
    rotation_val = node.get("rotation")
    if isinstance(rotation_val, list) and len(rotation_val) == 3:
        try:
            rotation = tuple(float(v) for v in rotation_val)
        except (TypeError, ValueError):
            rotation = None

    if translation is None and rotation is None:
        return []
    # Emit ONE Location: build123d applies the Euler rotation about the part
    # origin FIRST, then the translation — i.e. orient-in-place, then place.
    # Two separate .moved() calls (translate, then rotate about (0,0,0)) would
    # orbit an already-translated part around the world origin instead.
    t = translation if translation is not None else (0.0, 0.0, 0.0)
    if rotation is not None:
        return [f"{var_name} = {var_name}.moved(Location({_py(t)}, {_py(rotation)}))"]
    return [f"{var_name} = {var_name}.moved(Location({_py(t)}))"]


def _dims(data: dict[str, Any]) -> list[float] | None:
    for key in ("dimensions", "dims", "size"):
        value = data.get(key)
        if isinstance(value, list) and len(value) == 3:
            try:
                return [float(value[0]), float(value[1]), float(value[2])]
            except (TypeError, ValueError):
                return None
    length = _number(data, "length", "l", default=None)
    width = _number(data, "width", "w", default=None)
    height = _number(data, "height", "h", default=None)
    if length is not None and width is not None and height is not None:
        return [length, width, height]
    bbox = _bbox(data)
    if bbox is not None:
        return [abs(bbox[3] - bbox[0]), abs(bbox[4] - bbox[1]), abs(bbox[5] - bbox[2])]
    return None


def _number(data: dict[str, Any], *keys: str, default: float | None = 0.0) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _color(node: dict[str, Any]) -> list[float] | None:
    value = node.get("color")
    if not isinstance(value, list) or len(value) < 3:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def _py(value: Any) -> str:
    return repr(value)


def _build_topology_map(payload: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    face_ids_by_node: dict[str, str] = {}

    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        body_id = f"body_{_slug(node_id)}"
        face_id = f"face_{_slug(node_id)}"
        face_ids_by_node[node_id] = face_id

        body: dict[str, Any] = {
            "id": body_id,
            "type": str(node.get("topology_type") or node.get("entity_type") or "solid"),
            "name": str(node.get("name") or node_id),
            "source_ir_node": node_id,
            "face_ids": [face_id],
        }
        bbox = _bbox(node)
        if bbox is not None:
            body["bounding_box"] = bbox
        entities.append(body)

        face: dict[str, Any] = {
            "id": face_id,
            "type": "face",
            "body_id": body_id,
            "surface_type": str(node.get("surface_type") or node.get("kind") or "freeform"),
            "name": str(node.get("name") or node_id),
            "source_ir_node": node_id,
        }
        if bbox is not None:
            face["bounding_box"] = bbox
        if node.get("area") is not None:
            face["area"] = node["area"]
        else:
            face["area"] = _bbox_area_proxy(bbox)
        if isinstance(node.get("normal"), list) and len(node["normal"]) == 3:
            face["normal"] = node["normal"]
        if bool(node.get("freeform", False)) or face["surface_type"] in {"freeform", "bspline", "bezier", "subdivision_proxy"}:
            face["freeform"] = True
            if isinstance(node.get("proxy_normal"), list) and len(node["proxy_normal"]) == 3:
                face["proxy_normal"] = node["proxy_normal"]
            if isinstance(node.get("uv_bounds"), list) and len(node["uv_bounds"]) == 4:
                face["uv_bounds"] = node["uv_bounds"]
            if isinstance(node.get("curvature_sample"), dict):
                face["curvature_sample"] = node["curvature_sample"]
        entities.append(face)

    adjacency = payload.get("adjacency", [])
    if isinstance(adjacency, list):
        adjacent_faces: dict[str, set[str]] = {face_id: set() for face_id in face_ids_by_node.values()}
        for relation in adjacency:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source", ""))
            target = str(relation.get("target", ""))
            source_face = face_ids_by_node.get(source)
            target_face = face_ids_by_node.get(target)
            if source_face and target_face:
                adjacent_faces[source_face].add(target_face)
                adjacent_faces[target_face].add(source_face)
        for entity in entities:
            if entity.get("type") == "face":
                adj = sorted(adjacent_faces.get(str(entity.get("id")), set()))
                if adj:
                    entity["adjacent_entity_ids"] = adj

    return {
        "format_version": FORMAT_VERSION,
        "metadata": {
            "extractor": "ShapeIRConverter",
            "extraction_backend": "shape_ir",
            "extraction_mode": "projected_from_shape_ir",
            "representation": shape_ir_representation(payload),
            "real_step_parsing": False,
            "source_geometry": SHAPE_IR_SOURCE_PATH,
            "adjacency_evidence": "shape_ir_declared",
            "limitations": [
                "Projected semantic topology only; no CAD kernel or mesh geometry was executed.",
                "IDs are stable for Shape IR node IDs, not persistent CAD-kernel names.",
            ],
            "declared_model_id": payload.get("model_id"),
        },
        "entities": entities,
    }


def _build_feature_graph(payload: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        feature_type = str(node.get("feature_type") or node.get("role") or "unknown_feature")
        if feature_type not in _FEATURE_TYPES:
            feature_type = "unknown_feature"
        params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
        feature = {
            "id": f"feat_{_slug(node_id)}",
            "type": feature_type,
            "name": str(node.get("name") or node_id),
            "geometry_refs": {
                "entities": [f"body_{_slug(node_id)}", f"face_{_slug(node_id)}"],
                "faces": [f"face_{_slug(node_id)}"],
            },
            "parameters": params,
            "parameter_source": "converter_extracted",
            "editable": bool(params),
            "editability": "proposal_allowed" if params else "semantic_only",
            "writeback_strategy": "semantic_parameter_update_only" if params else "none",
            "editability_reason": (
                "Shape IR parameters can be edited semantically; exact CAD regeneration "
                "requires a Shape IR compiler/backend."
            ),
            "parameter_confidence": "medium" if params else "low",
            "intent": {
                "role": str(node.get("role") or node.get("kind") or "shape_ir_component"),
                "source_ir_node": node_id,
            },
            "recognition": {
                "method": "shape_ir_declared",
                "confidence": "medium",
            },
        }
        features.append(feature)

    relationships = payload.get("adjacency", [])
    if isinstance(relationships, list):
        for relation in relationships:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source", ""))
            target = str(relation.get("target", ""))
            if not source or not target:
                continue
            source_feature = f"feat_{_slug(source)}"
            target_feature = f"feat_{_slug(target)}"
            for feature in features:
                if feature["id"] == source_feature:
                    feature.setdefault("relationships", []).append({
                        "type": str(relation.get("type") or "adjacent_to"),
                        "source_feature_id": source_feature,
                        "target_feature_id": target_feature,
                    })

    return {
        "format_version": FORMAT_VERSION,
        "features": features,
        "metadata": {
            "recognizer": "ShapeIRConverter",
            "source_geometry": SHAPE_IR_SOURCE_PATH,
            "representation": shape_ir_representation(payload),
            "model_kind": str(payload.get("model_kind") or "organic"),
            "limitations": [
                "Feature semantics are declared by Shape IR, not inferred from exact geometry.",
            ],
        },
    }


def _build_object_registry(
    nodes: list[dict[str, Any]],
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
) -> dict[str, Any]:
    objects: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for entity in topology_map["entities"]:
        entity_id = entity["id"]
        objects.append({
            "id": entity_id,
            "kind": "topology_entity",
            "type": str(entity.get("type", "")),
            "name": str(entity.get("name") or entity_id),
            "defined_in": TOPOLOGY_MAP_PATH,
            "referenced_by": [TOPOLOGY_MAP_PATH, FEATURE_GRAPH_PATH],
            "roles": ["shape_ir_topology"],
            "status": "projected_from_shape_ir",
        })

    for feature in feature_graph["features"]:
        feature_id = feature["id"]
        objects.append({
            "id": feature_id,
            "kind": "feature",
            "type": str(feature.get("type", "")),
            "name": str(feature.get("name") or feature_id),
            "defined_in": FEATURE_GRAPH_PATH,
            "referenced_by": [FEATURE_GRAPH_PATH],
            "roles": ["shape_ir_feature"],
            "status": "declared_by_shape_ir",
        })
        for entity_id in feature.get("geometry_refs", {}).get("entities", []):
            relationships.append({
                "from": feature_id,
                "to": entity_id,
                "type": "references_topology",
                "source_file": FEATURE_GRAPH_PATH,
            })

    return {
        "format": "aieng.object_registry",
        "format_version": FORMAT_VERSION,
        "source_files": [SHAPE_IR_SOURCE_PATH, TOPOLOGY_MAP_PATH, FEATURE_GRAPH_PATH],
        "objects": objects,
        "relationships": relationships,
        "notes": [
            "Generated index from Shape IR; not the source of truth.",
            "Shape IR, topology_map, and feature_graph resources remain authoritative.",
        ],
    }


def _build_coverage_categories(nodes: list[dict[str, Any]], *, has_parameters: bool) -> list[CoverageCategory]:
    return [
        CoverageCategory(
            category="geometry",
            status="inferred",
            resources_emitted=(SHAPE_IR_SOURCE_PATH,),
            inferred_items=("semantic shape declarations",),
            missing_items=("exact B-Rep STEP geometry", "mesh preview"),
            notes="Shape IR records modeling intent; compile it to produce exact geometry.",
        ),
        CoverageCategory(
            category="topology",
            status="inferred",
            resources_emitted=(TOPOLOGY_MAP_PATH,),
            inferred_items=("body and face entities projected from Shape IR nodes",),
            notes="Topology IDs are semantic/provisional until a CAD backend confirms geometry.",
        ),
        CoverageCategory(
            category="object_registry",
            status="complete",
            resources_emitted=(OBJECT_REGISTRY_PATH,),
            notes=f"{len(nodes)} Shape IR node(s) indexed.",
        ),
        CoverageCategory(
            category="features",
            status="partial",
            resources_emitted=(FEATURE_GRAPH_PATH,),
            inferred_items=("feature roles declared by Shape IR",),
            notes="Feature candidates require engineer/CAD-kernel review before engineering claims.",
        ),
        CoverageCategory(
            category="editability_metadata",
            status="partial" if has_parameters else "missing",
            resources_emitted=(FEATURE_GRAPH_PATH,) if has_parameters else (),
            notes=(
                "Shape IR parameters are semantic-only until a compiler write-back contract is implemented."
                if has_parameters else
                "No Shape IR parameters were provided."
            ),
        ),
        CoverageCategory(
            category="writeback_metadata",
            status="unsupported",
            missing_items=("Shape IR compiler write-back contract",),
            notes="The reference converter does not emit L5 round-trip writeback metadata.",
        ),
    ]


def _build_readme(payload: dict[str, Any], source_path: Path, nodes: list[dict[str, Any]]) -> str:
    model_name = str(payload.get("model_id") or source_path.stem)
    lines = [
        f"# Shape IR conversion: {model_name}",
        "",
        f"- Source: `{source_path.name}`",
        f"- Nodes: {len(nodes)}",
        "- Conversion mode: semantic Shape IR projection only.",
        "- No CAD kernel, mesher, solver, optimizer, or CAD edit was executed.",
        "- Exact STEP/B-Rep geometry is not present unless another backend adds it later.",
        "",
        "## Shape IR nodes",
    ]
    for index, node in enumerate(nodes, start=1):
        node_id = _node_id(node, index)
        lines.append(f"- `{node_id}`: {node.get('name', node_id)}")
    lines.append("")
    return "\n".join(lines)


def _node_id(node: dict[str, Any], index: int) -> str:
    raw = node.get("id") or node.get("name") or f"node_{index:03d}"
    return str(raw)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_").lower()
    return cleaned or "node"


def _bbox(node: dict[str, Any]) -> list[float] | None:
    bbox = node.get("bounding_box", node.get("bbox"))
    if not isinstance(bbox, list) or len(bbox) != 6:
        return None
    try:
        return [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None


def _bbox_area_proxy(bbox: list[float] | None) -> float:
    if bbox is None:
        return 0.0
    dx = abs(bbox[3] - bbox[0])
    dy = abs(bbox[4] - bbox[1])
    dz = abs(bbox[5] - bbox[2])
    faces = sorted((dx * dy, dx * dz, dy * dz), reverse=True)
    return float(faces[0]) if faces else 0.0


# ── built-in compile targets (registered at import) ──────────────────────────
register_compiler(
    "brep_build123d",
    compiler=compile_shape_ir_to_build123d_source,
    source_path=BUILD123D_SOURCE_PATH,
    runtime="build123d",
    aliases=("build123d", "brep", "ocp", "auto", ""),
)
register_compiler(
    "implicit_sdf",
    compiler=_compile_sdf,
    source_path=SHAPE_IR_SDF_SOURCE_PATH,
    runtime="sdf",
)
register_compiler(
    "manifold_mesh",
    compiler=_compile_manifold,
    source_path=SHAPE_IR_MANIFOLD_SOURCE_PATH,
    runtime="manifold",
)
register_compiler(
    # NURBS B-Rep surfaces built via OCP; emits build123d source and reuses the
    # build123d runtime (exact STEP + per-face B-Rep topology), so source_path is
    # geometry/source.py.
    "nurbs_brep",
    compiler=_compile_nurbs,
    source_path=BUILD123D_SOURCE_PATH,
    runtime="build123d",
    aliases=("nurbs", "nurbs_ocp", "bspline_brep"),
)
