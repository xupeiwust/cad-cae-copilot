"""build123d text-to-CAD backend for aieng-ui.

Implements TextToCadBackend (from aieng.modeling.text_to_cad).
Calls Claude to generate build123d Python code, executes it in a
subprocess to produce a STEP file and topology_map.json, applies
heuristics to build feature_graph.json, then writes all artifacts
into the project's .aieng package.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from filelock import FileLock

from .config import ensure_aieng_on_path


# ── AGENTS.md resolution (single source of truth for build123d capabilities) ──

def _resolve_agents_md_path() -> Path | None:
    """Find AGENTS.md in the workspace or backend root."""
    backend_root = Path(__file__).resolve().parents[1]  # aieng-ui/backend
    workspace_root = backend_root.parents[1]  # workspace root
    candidates = [
        workspace_root / "AGENTS.md",
        backend_root / "AGENTS.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_agents_md() -> str | None:
    """Read AGENTS.md content, or None if not found / unreadable."""
    path = _resolve_agents_md_path()
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


# ── build123d runner template ──────────────────────────────────────────────────
# Placeholder __AIENG_GENERATED_CODE__ is replaced (not .format()-substituted)
# so all { } inside this string are literal Python syntax.

_RUNNER_TEMPLATE = """\
import sys
import json
import re
from pathlib import Path
import build123d as _aieng_build123d
from build123d import *

# Compatibility shim for agent-authored code. In build123d, `Compound([a, b])`
# can create a compound whose `.children` are empty, losing `.label` names that
# downstream MCP tools rely on. Prefer `Compound(children=[...])`, but preserve
# labels for the common positional-list form too. Patch the module before the
# generated code runs so a later `from build123d import *` in that code imports
# the shim as well.
_AIENG_ORIGINAL_COMPOUND = Compound


class Compound(_AIENG_ORIGINAL_COMPOUND):
    def __new__(cls, *args, **kwargs):
        if "children" not in kwargs and len(args) == 1:
            candidate = args[0]
            if isinstance(candidate, (list, tuple)) or type(candidate).__name__ == "ShapeList":
                return _AIENG_ORIGINAL_COMPOUND(children=list(candidate), **kwargs)
        return _AIENG_ORIGINAL_COMPOUND(*args, **kwargs)


_aieng_build123d.Compound = Compound


# ── bd_warehouse standard parts (ISO/DIN/ANSI fasteners, bearings, gears, …) ──
# Pre-bind the standard-parts modules so agent code can produce spec-compliant
# parts — e.g. ``fastener.SocketHeadCapScrew("M6-1", length=10)`` — instead of
# approximating with primitives, and so the geometry is semantically a screw/
# bearing/gear rather than an anonymous cylinder. Guarded per-module: a missing
# or broken submodule is skipped and never breaks a build. Agent code may also
# ``from bd_warehouse.fastener import SocketHeadCapScrew`` (the package is installed).
import importlib as _aieng_importlib
for _aieng_bdw_mod in ("fastener", "bearing", "gear", "thread", "pipe", "flange", "sprocket"):
    try:
        globals()[_aieng_bdw_mod] = _aieng_importlib.import_module("bd_warehouse." + _aieng_bdw_mod)
    except Exception:
        pass


def _aieng_designation_from_text(text):
    if not text:
        return None
    match = re.search(r"\\bM\\d+(?:[-xX]\\d+(?:\\.\\d+)?)?\\b", str(text))
    return match.group(0) if match else None


def _aieng_standard_part_canonical(module, class_name, label):
    class_text = str(class_name or "").lower()
    for needle, canonical in (
        ("washer", "washer"),
        ("nut", "nut"),
        ("screw", "screw"),
        ("bolt", "bolt"),
        ("bearing", "bearing"),
        ("gear", "gear"),
        ("thread", "thread"),
        ("flange", "flange"),
    ):
        if needle in class_text:
            return canonical
    text = f"{module} {class_name} {label}".lower()
    if "washer" in text:
        return "washer"
    if "nut" in text:
        return "nut"
    if "bolt" in text:
        return "bolt"
    if "screw" in text:
        return "screw"
    if ".fastener" in module or "fastener" in text:
        return "fastener"
    if ".bearing" in module or "bearing" in text:
        return "bearing"
    if ".gear" in module or "gear" in text:
        return "gear"
    if ".thread" in module or "thread" in text:
        return "thread"
    if ".flange" in module or "flange" in text:
        return "flange"
    return "unknown_standard_part"


def _aieng_standard_part_metadata(part, name):
    module = str(getattr(type(part), "__module__", "") or "")
    if not module.startswith("bd_warehouse."):
        return None
    class_name = str(getattr(type(part), "__name__", "") or "")
    object_label = str(getattr(part, "label", "") or "")
    label = object_label or str(name or "")
    designation = None
    for attr in (
        "screw_size", "thread_size", "bearing_size", "gear_size",
        "part_number", "size", "nominal_size", "fastener_type",
    ):
        try:
            value = getattr(part, attr)
        except Exception:
            continue
        if value not in (None, ""):
            designation = str(value)
            break
    if designation is None:
        designation = _aieng_designation_from_text(label)
    metadata = {
        "standard_part": True,
        "source_library": "bd_warehouse",
        "source_module": module,
        "source_class": class_name,
        "canonical_type": _aieng_standard_part_canonical(module, class_name, label),
        "object_label": object_label or None,
        "original_label": object_label or str(name or "") or None,
        "designation": designation,
        "detection_method": "bd_warehouse_type",
        "confidence": "high",
    }
    return {k: v for k, v in metadata.items() if v not in (None, "")}


# ── aieng high-level modelling helpers ──────────────────────────────────────
# Injected into the runner namespace so agent-authored code can produce smooth,
# designed forms with one call instead of stacking primitives. Each helper wraps
# the error-prone build123d boilerplate (BuildSketch/Plane/loft/sweep) that LLMs
# routinely get wrong, so the result is both more organic AND more reliable.
# Validated against build123d 0.10.0.

def _aieng_finish(part, label=None, color=None):
    if label is not None:
        part.label = label
    if color is not None:
        if isinstance(color, Color):
            part.color = color
        elif isinstance(color, (list, tuple)) and len(color) >= 3:
            part.color = Color(float(color[0]), float(color[1]), float(color[2]))
    return part


def lofted_stack(sections, label=None, color=None, ruled=False):
    \"\"\"Loft a smooth solid through cross-sections stacked along Z.

    Each section is a tuple, read by length:
      (z, radius)            -> circle
      (z, width, depth)      -> rounded rectangle (auto corner = 20% of min side)
      (z, width, depth, r)   -> rounded rectangle with corner radius r (r=0 -> sharp)
    Sections must be ordered by increasing z. Use for torsos, vehicle cabs,
    fuselages, helmet crowns -- anything tapered. Replaces stacked boxes.
    \"\"\"
    secs = list(sections)
    if len(secs) < 2:
        raise ValueError("lofted_stack needs >= 2 sections")
    with BuildPart() as _bp:
        for sec in secs:
            z = float(sec[0])
            with BuildSketch(Plane.XY.offset(z)):
                if len(sec) == 2:
                    Circle(float(sec[1]))
                elif len(sec) == 3:
                    w, d = float(sec[1]), float(sec[2])
                    cr = min(w, d) * 0.2
                    RectangleRounded(w, d, max(0.01, min(cr, min(w, d) / 2 - 0.01)))
                else:
                    w, d, cr = float(sec[1]), float(sec[2]), float(sec[3])
                    if cr > 0:
                        RectangleRounded(w, d, min(cr, min(w, d) / 2 - 0.01))
                    else:
                        Rectangle(w, d)
        loft(ruled=ruled)
    return _aieng_finish(_bp.part, label, color)


def rounded_box(length, width, height, radius, label=None, color=None, edges="all"):
    \"\"\"A box with filleted edges -- the default block for *designed* enclosures
    and bodies instead of a hard-edged Box. ``edges`` is "all" or "vertical".
    \"\"\"
    r = max(0.01, min(float(radius), min(length, width, height) / 2 - 0.01))
    with BuildPart() as _bp:
        Box(length, width, height)
        try:
            if edges == "vertical":
                fillet(_bp.edges().filter_by(Axis.Z), radius=r)
            else:
                fillet(_bp.edges(), radius=r)
        except Exception:
            fillet(_bp.edges().filter_by(Axis.Z), radius=min(r, min(length, width) / 2 - 0.01))
    return _aieng_finish(_bp.part, label, color)


def capsule(radius, length, axis="Z", label=None, color=None):
    \"\"\"A cylinder with hemispherical caps -- limbs, arms, legs, rounded pins.
    ``length`` is the cylindrical span; total length = length + 2*radius.
    ``axis`` in {"X","Y","Z"}.
    \"\"\"
    part = Cylinder(radius, length) + Sphere(radius).moved(Location((0, 0, length / 2))) \\
        + Sphere(radius).moved(Location((0, 0, -length / 2)))
    if isinstance(part, (list, tuple)) or type(part).__name__ == "ShapeList":
        part = Compound(children=list(part))
    a = str(axis).upper()
    if a == "X":
        part = part.rotate(Axis.Y, 90)
    elif a == "Y":
        part = part.rotate(Axis.X, 90)
    return _aieng_finish(part, label, color)


def tapered_cylinder(bottom_radius, top_radius, height, label=None, color=None):
    \"\"\"A truncated cone (different top/bottom radii) -- necks, nozzles, legs.\"\"\"
    return _aieng_finish(Cone(bottom_radius, top_radius, height), label, color)


def swept_tube(path_points, radius, label=None, color=None):
    \"\"\"Sweep a circular profile of ``radius`` along a smooth spline through
    ``path_points`` (list of (x,y,z)). Pipes, handles, exhausts, cable runs.
    \"\"\"
    pts = [tuple(float(c) for c in p) for p in path_points]
    if len(pts) < 2:
        raise ValueError("swept_tube needs >= 2 path points")
    with BuildPart() as _bp:
        with BuildLine() as _ln:
            if len(pts) == 2:
                Line(pts[0], pts[1])
            else:
                Spline(*pts)
        with BuildSketch(Plane(origin=_ln.line @ 0, z_dir=_ln.line % 0)):
            Circle(float(radius))
        sweep()
    return _aieng_finish(_bp.part, label, color)


def revolved_profile(profile_points, label=None, color=None, degrees=360):
    \"\"\"Revolve a 2D profile around the Z axis. ``profile_points`` is a list of
    (r, z) with r>=0 (distance from the Z axis); auto-closed to the axis.
    Bottles, vases, bell housings, wheels -- anything axisymmetric.
    \"\"\"
    pts = [(float(r), float(z)) for r, z in profile_points]
    if len(pts) < 2:
        raise ValueError("revolved_profile needs >= 2 points")
    if pts[0][0] != 0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] != 0:
        pts.append((0.0, pts[-1][1]))
    with BuildPart() as _bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*pts, close=True)
            make_face()
        revolve(axis=Axis.Z, revolution_arc=float(degrees))
    return _aieng_finish(_bp.part, label, color)


def organic_blend(solids, radius, label=None, color=None):
    \"\"\"Fuse solids and fillet the resulting edges so the join reads as one
    smooth body instead of glued primitives. Falls back to smaller radii (then
    no fillet) if the requested radius is geometrically infeasible.
    \"\"\"
    items = list(solids)
    if not items:
        raise ValueError("organic_blend needs >= 1 solid")
    fused = items[0]
    for s in items[1:]:
        fused = fused + s
    if isinstance(fused, (list, tuple)) or type(fused).__name__ == "ShapeList":
        fused = Compound(children=list(fused))
    for rr in (float(radius), float(radius) * 0.5, float(radius) * 0.25):
        try:
            fused = fillet(fused.edges(), radius=rr)
            break
        except Exception:
            continue
    return _aieng_finish(fused, label, color)


# ── domain primitives (common engineering / vehicle shapes) ──────────────────
# Higher-level than the generic helpers above: one call for a shape that would
# otherwise take a fragile hand-rolled sketch. Same _aieng_finish(label, color)
# contract; each returns a labelled, colourable Part.

def naca_airfoil(chord, thickness, span=None, label=None, color=None):
    \"\"\"A symmetric NACA-4-digit airfoil section extruded into a 3D wing solid.

    ``chord`` = chord length (mm) along X, ``thickness`` = max thickness (mm),
    ``span`` = extrusion length along Y (default = chord). Wings, fins, blades,
    struts. Profile follows the standard NACA00xx half-thickness polynomial.
    For a tapered/swept wing, build two and ``loft`` between them.
    \"\"\"
    c = float(chord)
    tf = float(thickness) / c
    sp = float(span) if span is not None else c
    n = 30
    xs = [i / n for i in range(n + 1)]

    def _yt(x):
        return 5 * tf * c * (
            0.2969 * x ** 0.5 - 0.1260 * x - 0.3516 * x ** 2
            + 0.2843 * x ** 3 - 0.1015 * x ** 4
        )

    upper = [(x * c, _yt(x)) for x in xs]
    lower = [(x * c, -_yt(x)) for x in reversed(xs[1:-1])]
    pts = upper + lower
    with BuildPart() as _bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*pts, close=True)
            make_face()
        extrude(amount=sp)
    return _aieng_finish(_bp.part, label, color)


def fuselage_profile(length, max_diameter, nose_frac=0.2, tail_frac=0.3, label=None, color=None):
    \"\"\"A revolved fuselage: rounded nose, constant mid-body, tapered tail.

    ``length`` axial span (mm) along Z, ``max_diameter`` the max body diameter;
    ``nose_frac`` / ``tail_frac`` are the fractions of length spent on the nose
    and tail tapers. Aircraft/rocket bodies, pods, bottles.
    \"\"\"
    L = float(length)
    R = float(max_diameter) / 2.0
    nose = max(0.0, float(nose_frac)) * L
    tail = max(0.0, float(tail_frac)) * L
    pts = []
    ns = 6
    for i in range(ns + 1):
        f = i / ns
        pts.append((max(0.001, R * (f ** 0.5)), f * nose))
    pts.append((R, max(nose, L - tail)))
    ts = 6
    for i in range(1, ts + 1):
        f = i / ts
        pts.append((max(0.001, R * (1 - f)), (L - tail) + f * tail))
    return revolved_profile(pts, label=label, color=color)


def wheel(rim_radius, tire_radius, width, label=None, color=None):
    \"\"\"A wheel disc (axis along Z) with a central axle bore.

    Outer radius = ``rim_radius`` + ``tire_radius``; ``width`` is the axial
    thickness. The bore is 30% of ``rim_radius``. Vehicle wheels, pulleys,
    rollers, gear blanks.
    \"\"\"
    rr = float(rim_radius)
    outer = rr + float(tire_radius)
    bore = max(0.001, rr * 0.3)
    with BuildPart() as _bp:
        Cylinder(outer, float(width))
        Cylinder(bore, float(width), mode=Mode.SUBTRACT)
    return _aieng_finish(_bp.part, label, color)


def ribbed_plate(length, width, thickness, rib_count=2, rib_height=None, label=None, color=None):
    \"\"\"A flat plate with parallel stiffening ribs on top, running along length.

    ``rib_count`` evenly-spaced ribs across the width; ``rib_height`` defaults to
    3x ``thickness``; rib thickness is ~0.8x plate ``thickness``. Brackets, base
    plates, structural panels. The plate bottom sits at Z=0.
    \"\"\"
    L = float(length)
    W = float(width)
    t = float(thickness)
    n = max(1, int(rib_count))
    rh = float(rib_height) if rib_height is not None else t * 3.0
    rt = max(1.0, t * 0.8)
    ys = [(-W / 2 + W * (i + 0.5) / n) for i in range(n)]
    with BuildPart() as _bp:
        Box(L, W, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(*[(0, y, t) for y in ys]):
            Box(L, rt, rh, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return _aieng_finish(_bp.part, label, color)


# ---- aieng generated code ----
__AIENG_GENERATED_CODE__
# ---- end generated code ----

# normalise: BuildPart context → Part
if hasattr(result, "part"):
    result = result.part

# normalise: build123d's `+` can yield a ShapeList (e.g. Solid + Cylinder) which
# has no single `.wrapped` and fails to export. Wrap any list-like result in a
# Compound so the exporters always receive a single shape.
if isinstance(result, (list, tuple)) or type(result).__name__ == "ShapeList":
    _items = list(result)
    if len(_items) == 1:
        result = _items[0]
    elif _items:
        result = Compound(children=_items)


def _bbox_list(bb):
    return [
        round(bb.min.X, 4), round(bb.min.Y, 4), round(bb.min.Z, 4),
        round(bb.max.X, 4), round(bb.max.Y, 4), round(bb.max.Z, 4),
    ]


def _face_entity(face, fid, body_id):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder

    fbb = face.bounding_box()
    data = {
        "id": fid,
        "type": "face",
        "area": round(face.area, 4),
        "bounding_box": _bbox_list(fbb),
        "center": [
            round((fbb.min.X + fbb.max.X) / 2, 4),
            round((fbb.min.Y + fbb.max.Y) / 2, 4),
            round((fbb.min.Z + fbb.max.Z) / 2, 4),
        ],
        "body_id": body_id,
    }
    adaptor = BRepAdaptor_Surface(face.wrapped)
    surf_type = adaptor.GetType()
    surf_name = str(surf_type).lower()
    if surf_type == GeomAbs_Plane:
        data["surface_type"] = "plane"
        try:
            n = face.normal_at(0.5, 0.5)
            data["normal"] = [round(n.X, 6), round(n.Y, 6), round(n.Z, 6)]
        except Exception:
            data["normal"] = [0.0, 0.0, 1.0]
    elif surf_type == GeomAbs_Cylinder:
        data["surface_type"] = "cylinder"
        data["radius"] = round(adaptor.Cylinder().Radius(), 4)
    else:
        # Free-form face (loft / sweep / sphere / spline) from the high-level
        # helpers. Still record a PROXY normal + true face centre so the face is
        # usable for face-picking and approximate CAE binding — downstream code
        # only had a plane/cylinder path and fell back to a broken axis-aligned
        # heuristic when neither was present. The proxy is the surface normal at
        # the UV midpoint; `freeform: true` flags that it is an approximation.
        if "bspline" in surf_name:
            data["surface_type"] = "bspline"
        elif "bezier" in surf_name:
            data["surface_type"] = "bezier"
        elif "sphere" in surf_name:
            data["surface_type"] = "sphere"
        elif "cone" in surf_name:
            data["surface_type"] = "cone"
        elif "torus" in surf_name:
            data["surface_type"] = "torus"
        elif "revolution" in surf_name:
            data["surface_type"] = "surface_of_revolution"
        elif "extrusion" in surf_name:
            data["surface_type"] = "surface_of_extrusion"
        else:
            data["surface_type"] = "freeform"
        data["freeform"] = True
        try:
            data["uv_bounds"] = [
                round(float(adaptor.FirstUParameter()), 6),
                round(float(adaptor.LastUParameter()), 6),
                round(float(adaptor.FirstVParameter()), 6),
                round(float(adaptor.LastVParameter()), 6),
            ]
        except Exception:
            pass
        try:
            n = face.normal_at(0.5, 0.5)
            data["normal"] = [round(n.X, 6), round(n.Y, 6), round(n.Z, 6)]
            data["proxy_normal"] = data["normal"]
        except Exception:
            pass
        try:
            c = face.center()
            data["center"] = [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)]
        except Exception:
            pass
    return data


def _has_labeled_descendant(node):
    for c in (getattr(node, "children", None) or []):
        if (getattr(c, "label", "") or "") or _has_labeled_descendant(c):
            return True
    return False


def _collect_parts(shape, include_assemblies=False):
    # Returns [(name_or_None, part_shape, is_assembly), ...]. A labelled leaf is
    # a named part. A labelled Compound that also has labelled descendants is an
    # assembly label: include it when topology asks for assemblies, then keep
    # descending so child labels remain referenceable. Mesh export leaves those
    # parents out to avoid duplicate triangles/z-fighting in thumbnails.
    out = []

    def _walk(node):
        label = (getattr(node, "label", "") or "")
        children = list(getattr(node, "children", None) or [])
        labeled_descendants = bool(children) and _has_labeled_descendant(node)
        if label:
            is_assembly = labeled_descendants
            if include_assemblies or not is_assembly:
                out.append((label, node, is_assembly))
            if is_assembly:
                for c in children:
                    _walk(c)
            return
        if labeled_descendants:
            for c in children:
                _walk(c)
            return
        out.append((None, node, False))

    _walk(shape)
    return out


def _extract_topology(shape):
    entities = []
    face_counter = 0
    for pi, (name, part, is_assembly) in enumerate(_collect_parts(shape, include_assemblies=True)):
        body_id = f"body_{pi + 1:03d}"
        body = {"id": body_id, "type": "solid", "bounding_box": _bbox_list(part.bounding_box())}
        if name:
            body["name"] = name
        standard_part = _aieng_standard_part_metadata(part, name)
        if standard_part:
            body.update(standard_part)
            body["standard_part_metadata"] = dict(standard_part)
        if is_assembly:
            body["assembly"] = True
        entities.append(body)
        if is_assembly:
            continue
        for face in part.faces():
            face_counter += 1
            entities.append(_face_entity(face, f"face_{face_counter:03d}", body_id))
    return {"format_version": "0.1", "entities": entities}



out_step = Path(sys.argv[1])
out_topo = Path(sys.argv[2])
out_stl = Path(sys.argv[3])
out_glb = Path(sys.argv[4])


def _export(kind, obj, path, **kwargs):
    # build123d <0.9 exposed export_* as Shape methods; 0.9+ moved them to
    # module-level free functions. Support both so the runner is version-robust.
    method = getattr(obj, "export_" + kind, None)
    if callable(method):
        return method(str(path), **kwargs)
    import build123d as _b123d
    fn = getattr(_b123d, "export_" + kind, None)
    if fn is None:
        raise RuntimeError("build123d has no export_" + kind)
    return fn(obj, str(path), **kwargs)


_export("step", result, out_step)

# Per-body STL export — concatenate into the combined STL while recording each
# body's triangle range + color, so the thumbnail renderer can colorize parts.
# Falls back to whole-result STL if any per-body export fails (mesh_meta empty).
import struct as _aieng_struct
import tempfile as _aieng_tempfile

_aieng_collected = _collect_parts(result)
_aieng_mesh_meta = {"bodies": []}
_aieng_combined_tris: list[bytes] = []
_aieng_combined_count = 0
_aieng_use_combined = True

def _aieng_extract_color(part):
    # Accept build123d Color, tuple/list, or anything exposing .r/.g/.b in 0..1.
    try:
        c = getattr(part, "color", None)
        if c is None:
            return None
        if isinstance(c, (tuple, list)) and len(c) >= 3:
            return [float(c[0]), float(c[1]), float(c[2])]
        if hasattr(c, "to_tuple"):
            t = c.to_tuple()
            return [float(t[0]), float(t[1]), float(t[2])]
        if hasattr(c, "r") and hasattr(c, "g") and hasattr(c, "b"):
            return [float(c.r), float(c.g), float(c.b)]
        # Last resort: iterable of floats
        t = tuple(c)
        return [float(t[0]), float(t[1]), float(t[2])]
    except Exception:
        return None

with _aieng_tempfile.TemporaryDirectory() as _aieng_td:
    for _aieng_bi, (_aieng_pname, _aieng_ppart, _aieng_is_assembly) in enumerate(_aieng_collected):
        _aieng_body_id = f"body_{_aieng_bi + 1:03d}"
        _aieng_col = _aieng_extract_color(_aieng_ppart)
        _aieng_tris = 0
        try:
            _aieng_bstl = Path(_aieng_td) / (_aieng_body_id + ".stl")
            _export("stl", _aieng_ppart, _aieng_bstl)
            _aieng_raw = _aieng_bstl.read_bytes()
            if len(_aieng_raw) >= 84:
                _aieng_tris = _aieng_struct.unpack("<I", _aieng_raw[80:84])[0]
                _aieng_combined_tris.append(_aieng_raw[84:84 + _aieng_tris * 50])
                _aieng_combined_count += _aieng_tris
        except Exception as _aieng_ee:
            print(f"[runner] per-body STL export failed for {_aieng_body_id}: {_aieng_ee}", file=sys.stderr)
            _aieng_use_combined = False
        _aieng_mesh_meta["bodies"].append({
            "body_id": _aieng_body_id,
            "name": _aieng_pname,
            "color": _aieng_col,
            "triangle_count": _aieng_tris,
        })

if _aieng_use_combined and _aieng_combined_count > 0:
    _aieng_hdr = b"aieng-stl".ljust(80, b" ")
    out_stl.write_bytes(_aieng_hdr + _aieng_struct.pack("<I", _aieng_combined_count) + b"".join(_aieng_combined_tris))
else:
    # Per-body path failed for at least one part — write whole-result STL and
    # invalidate mesh_meta so the renderer falls back to default coloring.
    _export("stl", result, out_stl)
    _aieng_mesh_meta = {"bodies": []}

(out_stl.with_name("mesh_meta.json")).write_text(json.dumps(_aieng_mesh_meta, indent=2))

try:
    _export("gltf", result, out_glb, binary=True)
except Exception as _e:
    print(f"[runner] GLB export failed: {_e}", file=sys.stderr)
topo = _extract_topology(result)
out_topo.write_text(json.dumps(topo, indent=2))
"""


# ── helpers ────────────────────────────────────────────────────────────────────

_EXPORT_CALL_RE = re.compile(
    r"^\s*(export_step|export_stl|export_gltf|result\.export_|\.export_step|\.export_stl|\.export_gltf)",
    re.MULTILINE,
)


def _coerce_code(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:python)?\s*\n?", "", stripped, flags=re.MULTILINE)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _check_code_contract(code: str) -> str | None:
    """Return an error message if the code violates the runner contract, else None.

    Checks:
    - Code must assign to ``result`` (the model variable the runner exports).
    - Code must NOT contain export calls (the runner adds them; duplicates cause errors).
    """
    if not re.search(r"\bresult\s*=", code):
        return (
            "Code contract violation: the script must assign the final model to a "
            "variable named `result` (e.g. `result = Box(100, 50, 10)`)."
        )
    if _EXPORT_CALL_RE.search(code):
        return (
            "Code contract violation: the script must NOT include export calls "
            "(export_step, export_stl, export_gltf). "
            "The runner adds them automatically."
        )
    return None


def _load_stl_triangles(stl_bytes: bytes) -> tuple[Any, Any] | tuple[None, None]:
    """Best-effort STL loader returning (triangles, normals) as numpy arrays.

    Prefers trimesh when installed, but falls back to a tiny local ASCII/binary
    STL parser so thumbnail rendering still works in minimal environments.
    """
    import struct

    import numpy as np

    try:
        import io
        import trimesh

        mesh = trimesh.load(io.BytesIO(stl_bytes), file_type="stl", force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            return None, None
        verts = np.asarray(mesh.vertices)
        triangles = verts[np.asarray(mesh.faces)]
        normals = np.asarray(mesh.face_normals)
        return triangles, normals
    except Exception:
        pass

    stripped = stl_bytes.lstrip()
    if stripped[:5].lower() == b"solid" and b"facet" in stripped:
        text = stl_bytes.decode("utf-8", errors="ignore")
        vertex_matches = re.findall(
            r"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",
            text,
        )
        if len(vertex_matches) >= 3 and len(vertex_matches) % 3 == 0:
            verts = np.asarray([[float(x), float(y), float(z)] for x, y, z in vertex_matches], dtype=float)
            triangles = verts.reshape((-1, 3, 3))
            edge1 = triangles[:, 1] - triangles[:, 0]
            edge2 = triangles[:, 2] - triangles[:, 0]
            normals = np.cross(edge1, edge2)
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            normals = normals / np.where(norms == 0, 1.0, norms)
            return triangles, normals

    if len(stl_bytes) >= 84:
        tri_count = struct.unpack("<I", stl_bytes[80:84])[0]
        expected = 84 + tri_count * 50
        if tri_count > 0 and expected <= len(stl_bytes):
            triangles: list[list[list[float]]] = []
            normals: list[list[float]] = []
            offset = 84
            for _ in range(tri_count):
                nx, ny, nz = struct.unpack("<3f", stl_bytes[offset:offset + 12])
                offset += 12
                tri = []
                for _ in range(3):
                    vx, vy, vz = struct.unpack("<3f", stl_bytes[offset:offset + 12])
                    offset += 12
                    tri.append([vx, vy, vz])
                offset += 2  # attribute byte count
                triangles.append(tri)
                normals.append([nx, ny, nz])
            if triangles:
                return np.asarray(triangles, dtype=float), np.asarray(normals, dtype=float)

    return None, None


def _encode_rgb_png(width: int, height: int, pixels: bytes) -> bytes:
    import struct
    import zlib

    def _chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    scanlines = b"".join(
        b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3]
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(scanlines, 9))
        + _chunk(b"IEND", b"")
    )


def _render_mesh_thumbnail_basic(triangles: Any, size: int) -> str | None:
    """Dependency-free orthographic fallback that returns a valid PNG."""
    try:
        import base64

        import numpy as np

        tris = np.asarray(triangles, dtype=float)
        if tris.size == 0:
            return None
        pts = tris[:, :, :2].reshape((-1, 2))
        mins = pts.min(axis=0)
        maxs = pts.max(axis=0)
        span = float((maxs - mins).max()) or 1.0
        margin = max(8, size // 24)

        def project(point: Any) -> tuple[int, int]:
            x = (float(point[0]) - float(mins[0])) / span
            y = (float(point[1]) - float(mins[1])) / span
            px = int(margin + x * (size - 2 * margin))
            py = int(size - margin - y * (size - 2 * margin))
            return max(0, min(size - 1, px)), max(0, min(size - 1, py))

        bg = [246, 249, 252]
        fill = [92, 128, 196]
        edge = [27, 43, 74]
        pixels = bytearray(bg * size * size)

        def set_px(x: int, y: int, color: list[int]) -> None:
            if 0 <= x < size and 0 <= y < size:
                idx = (y * size + x) * 3
                pixels[idx : idx + 3] = bytes(color)

        def draw_line(a: tuple[int, int], b: tuple[int, int], color: list[int]) -> None:
            x0, y0 = a
            x1, y1 = b
            dx = abs(x1 - x0)
            dy = -abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                set_px(x0, y0, color)
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x0 += sx
                if e2 <= dx:
                    err += dx
                    y0 += sy

        for tri in tris:
            p0, p1, p2 = [project(p) for p in tri]
            min_x = max(0, min(p0[0], p1[0], p2[0]))
            max_x = min(size - 1, max(p0[0], p1[0], p2[0]))
            min_y = max(0, min(p0[1], p1[1], p2[1]))
            max_y = min(size - 1, max(p0[1], p1[1], p2[1]))
            denom = ((p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])) or 1
            for y in range(min_y, max_y + 1):
                for x in range(min_x, max_x + 1):
                    a = ((p1[1] - p2[1]) * (x - p2[0]) + (p2[0] - p1[0]) * (y - p2[1])) / denom
                    b = ((p2[1] - p0[1]) * (x - p2[0]) + (p0[0] - p2[0]) * (y - p2[1])) / denom
                    c = 1 - a - b
                    if a >= 0 and b >= 0 and c >= 0:
                        set_px(x, y, fill)
            draw_line(p0, p1, edge)
            draw_line(p1, p2, edge)
            draw_line(p2, p0, edge)

        return base64.b64encode(_encode_rgb_png(size, size, bytes(pixels))).decode("ascii")
    except Exception:
        return None


# Four review views: front, side, top, iso. Tiled into a 2x2 contact sheet so the
# agent can judge silhouette + alignment + proportion at once, not just the iso.
# (elev, azim, label) — matplotlib 3D convention.
_REVIEW_VIEWS: tuple[tuple[float, float, str], ...] = (
    (10.0, -90.0, "front"),
    (10.0, 0.0, "side"),
    (89.0, -90.0, "top"),
    (25.0, -50.0, "iso"),
)

# Distinct mid-saturation palette for parts that didn't set an explicit .color.
# Mid-value tones so Lambert shading still reads; ordered for high contrast
# between adjacent parts.
_DEFAULT_PART_PALETTE: tuple[tuple[float, float, float], ...] = (
    (0.40, 0.55, 0.85),  # blue
    (0.85, 0.40, 0.35),  # red
    (0.40, 0.75, 0.50),  # green
    (0.90, 0.70, 0.30),  # amber
    (0.60, 0.45, 0.75),  # purple
    (0.45, 0.75, 0.80),  # teal
    (0.85, 0.55, 0.70),  # pink
    (0.65, 0.65, 0.65),  # neutral grey
)


def _build_face_colors_from_mesh_meta(mesh_meta: Any) -> Any:
    """Expand per-body colors from mesh_meta into a per-triangle RGB array.

    Bodies that supplied an explicit `.color` use that RGB; bodies without a
    color get a cycling palette entry so part boundaries are still visible.
    Returns None when mesh_meta is missing or invalid — caller then falls back
    to the default uniform tint inside render_mesh_thumbnail.
    """
    if not isinstance(mesh_meta, dict):
        return None
    bodies = mesh_meta.get("bodies")
    if not isinstance(bodies, list) or not bodies:
        return None
    try:
        import numpy as np

        rows: list[list[float]] = []
        palette_idx = 0
        for body in bodies:
            tris = int(body.get("triangle_count", 0) or 0)
            if tris <= 0:
                continue
            raw_color = body.get("color")
            if (
                isinstance(raw_color, (list, tuple))
                and len(raw_color) >= 3
                and all(isinstance(x, (int, float)) for x in raw_color[:3])
            ):
                color = [float(raw_color[0]), float(raw_color[1]), float(raw_color[2])]
            else:
                color = list(_DEFAULT_PART_PALETTE[palette_idx % len(_DEFAULT_PART_PALETTE)])
                palette_idx += 1
            rows.extend([color] * tris)
        if not rows:
            return None
        return np.asarray(rows, dtype=float)
    except Exception:
        return None


def render_mesh_thumbnail(
    stl_bytes: bytes,
    size: int = 480,
    face_colors: Any = None,
    reference_image_bytes: bytes | None = None,
) -> str | None:
    """Render an STL mesh as a multi-view contact sheet PNG (base64, headless).

    Gives an agent driving CAD a visual feedback loop with four review angles
    (front / side / top / iso) so silhouette and alignment can be judged at once.
    When ``reference_image_bytes`` is supplied, the contact sheet expands to a
    2x3 layout with the reference image in the rightmost column spanning both
    rows — the agent compares its build against the reference at every iteration.

    Uses matplotlib's 3D toolkit (Agg backend) because trimesh's GL-based
    ``save_image`` requires pyglet/OpenGL, which is unavailable headless on Windows.

    Args:
        stl_bytes: binary STL data.
        size: final contact-sheet edge length in pixels.
        face_colors: optional per-triangle RGB array, shape ``(n_triangles, 3)``,
            values in 0..1. When None, all triangles share a default blue and a
            simple Lambert shading is applied. When provided, the colors are
            modulated by the same Lambert term so part boundaries stay readable.
        reference_image_bytes: optional encoded image (PNG/JPEG) to display in
            the rightmost column for side-by-side comparison. Decoded via PIL.

    Returns None on any failure — a thumbnail is best-effort and must never break
    the build.
    """
    if not stl_bytes:
        return None
    triangles, normals = _load_stl_triangles(stl_bytes)
    if triangles is None or normals is None or len(triangles) == 0:
        return None
    try:
        import base64
        import io

        import numpy as np
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        verts = np.asarray(triangles).reshape((-1, 3))

        # Lambert shading so form reads clearly (not photorealism). When the
        # caller supplied per-face colors, modulate them with the same intensity
        # term; otherwise fall back to a default blue tint.
        normals_arr = np.asarray(normals, dtype=float)
        light = np.array([0.3, 0.4, 0.85])
        light = light / np.linalg.norm(light)
        intensity = np.clip(normals_arr @ light, 0.25, 1.0)

        if face_colors is not None:
            colors_arr = np.asarray(face_colors, dtype=float)
            if colors_arr.shape == (len(triangles), 3):
                facecolors = np.clip(intensity[:, None] * colors_arr, 0.0, 1.0)
            else:
                # Length mismatch: fall back to default rather than crash.
                base_color = np.array([0.40, 0.55, 0.85])
                facecolors = np.clip(intensity[:, None] * base_color, 0.0, 1.0)
        else:
            base_color = np.array([0.40, 0.55, 0.85])
            facecolors = np.clip(intensity[:, None] * base_color, 0.0, 1.0)

        mins = verts.min(axis=0)
        maxs = verts.max(axis=0)
        center = (mins + maxs) / 2
        span = float((maxs - mins).max()) / 2 or 1.0

        # Try to decode the reference image first; if it fails, fall back to the
        # plain 2x2 layout rather than crashing the build.
        ref_image = None
        if reference_image_bytes:
            try:
                from PIL import Image

                ref_image = np.asarray(Image.open(io.BytesIO(reference_image_bytes)).convert("RGB"))
            except Exception:
                ref_image = None

        has_ref = ref_image is not None

        # Layout: 2x2 without reference, 2x3 with reference (last column = ref).
        # Wider figure when reference is present so each tile keeps roughly its
        # original size instead of squeezing.
        if has_ref:
            fig_w, fig_h = (size * 1.5) / 100, size / 100
            gs = GridSpec(2, 3, figure=plt.figure(figsize=(fig_w, fig_h), dpi=100))
            fig = plt.gcf()
        else:
            fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
            gs = GridSpec(2, 2, figure=fig)

        for i, (elev, azim, label) in enumerate(_REVIEW_VIEWS):
            row, col = divmod(i, 2)
            ax = fig.add_subplot(gs[row, col], projection="3d")
            # Use a fresh Poly3DCollection per axis — sharing one across multiple
            # 3D axes causes matplotlib to render only on the last one.
            coll = Poly3DCollection(
                triangles,
                facecolors=facecolors,
                edgecolors=(0, 0, 0, 0.08),
                linewidths=0.12,
            )
            ax.add_collection3d(coll)
            ax.set_xlim(center[0] - span, center[0] + span)
            ax.set_ylim(center[1] - span, center[1] + span)
            ax.set_zlim(center[2] - span, center[2] + span)
            ax.set_box_aspect((1, 1, 1))
            ax.view_init(elev=elev, azim=azim)
            ax.set_axis_off()
            # Tile label in the top-left corner — agent uses it to map findings
            # to a specific view ("right shoulder misaligned in front view").
            ax.text2D(
                0.03, 0.95, label,
                transform=ax.transAxes,
                fontsize=9,
                color=(0.15, 0.20, 0.35),
                family="monospace",
                weight="bold",
            )

        if has_ref:
            ax_ref = fig.add_subplot(gs[:, 2])
            ax_ref.imshow(ref_image)
            ax_ref.set_axis_off()
            ax_ref.text(
                0.03, 0.97, "reference",
                transform=ax_ref.transAxes,
                fontsize=10,
                color=(0.6, 0.15, 0.15),  # red so it pops vs the blue view labels
                family="monospace",
                weight="bold",
                verticalalignment="top",
            )

        fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return _render_mesh_thumbnail_basic(triangles, size)


# Canonical engineering labels (from feature_graph.schema.json) — their presence
# signals a mechanical part where bolt-pattern / base-plate heuristics are wanted.
_ENGINEERING_LABEL_HINTS: tuple[str, ...] = (
    "base_plate", "back_plate", "mount_plate", "mounting_hole", "rib", "boss",
    "flange", "interface_face", "load_interface", "wall", "cover", "lid",
    "shell", "bracket", "housing", "manifold", "fixture", "frame", "mount",
    "chassis", "plate", "bearing", "bolt", "gusset",
)

# Organic/industrial-design helper calls in the source — their presence signals
# a character/vehicle/product where the mechanical heuristics misfire (they tag
# limb cylinders as "mounting_hole_pattern" and the bottom face as "base_plate").
_ORGANIC_HELPER_HINTS: tuple[str, ...] = (
    "lofted_stack(", "capsule(", "swept_tube(", "revolved_profile(",
    "organic_blend(", "tapered_cylinder(",
    "naca_airfoil(", "fuselage_profile(", "wheel(",
)


def _infer_model_kind(named_solids: list[dict[str, Any]], source_code: str | None) -> str:
    """Decide whether a model is 'organic' or 'mechanical' for heuristic gating.

    Mechanical wins if any named part uses a canonical engineering label.
    Otherwise, using the organic helper functions (loft/capsule/sweep/…) marks
    the model organic. Default when neither signal fires: mechanical (preserves
    prior behaviour for plain primitive parts).
    """
    names = " ".join(str(b.get("name") or "").lower() for b in named_solids)
    if any(h in names for h in _ENGINEERING_LABEL_HINTS):
        return "mechanical"
    if source_code and any(h in source_code for h in _ORGANIC_HELPER_HINTS):
        return "organic"
    return "mechanical"


_STANDARD_PART_CANONICAL_TYPES = {
    "fastener",
    "bearing",
    "gear",
    "thread",
    "flange",
    "washer",
    "nut",
    "screw",
    "bolt",
    "unknown_standard_part",
}

_STANDARD_PART_METADATA_FIELDS = (
    "standard_part",
    "source_library",
    "source_module",
    "source_class",
    "canonical_type",
    "designation",
    "original_label",
    "object_label",
    "detection_method",
    "confidence",
)

_STANDARD_PART_SOURCE_HINTS = (
    "bd_warehouse",
    "fastener.",
    "bearing.",
    "gear.",
    "thread.",
    "flange.",
)


def _canonical_standard_type_from_text(text: str) -> str | None:
    lower = text.lower()
    checks = (
        ("washer", "washer"),
        ("nut", "nut"),
        ("bolt", "bolt"),
        ("screw", "screw"),
        ("fastener", "fastener"),
        ("bearing", "bearing"),
        ("gear", "gear"),
        ("thread", "thread"),
        ("flange", "flange"),
    )
    for needle, canonical in checks:
        if needle in lower:
            return canonical
    return None


def _designation_from_text(text: str) -> str | None:
    match = re.search(r"\bM\d+(?:[-xX]\d+(?:\.\d+)?)?\b", text)
    return match.group(0) if match else None


def _clean_standard_part_metadata(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for key in _STANDARD_PART_METADATA_FIELDS:
        value = raw.get(key)
        if key == "standard_part" and value is False:
            continue
        if value in (None, ""):
            continue
        out[key] = value
    if not out and not raw.get("standard_part"):
        return None
    canonical = str(out.get("canonical_type") or "unknown_standard_part")
    if canonical not in _STANDARD_PART_CANONICAL_TYPES:
        canonical = "unknown_standard_part"
    out["standard_part"] = True
    out["canonical_type"] = canonical
    out.setdefault("detection_method", "topology_metadata")
    out.setdefault("confidence", "medium")
    return out


def _standard_part_metadata_for_body(
    body: dict[str, Any],
    source_code: str | None,
) -> dict[str, Any] | None:
    raw: dict[str, Any] = {}
    nested = body.get("standard_part_metadata")
    if isinstance(nested, dict):
        raw.update(nested)
    for field in _STANDARD_PART_METADATA_FIELDS:
        if field in body:
            raw[field] = body[field]
    from_topology = _clean_standard_part_metadata(raw)
    if from_topology:
        return from_topology

    name = str(body.get("name") or "")
    source_text = source_code or ""
    source_lower = source_text.lower()
    source_known = any(hint in source_lower for hint in _STANDARD_PART_SOURCE_HINTS)
    canonical = _canonical_standard_type_from_text(name)
    if canonical is None and source_known:
        canonical = _canonical_standard_type_from_text(source_text) or "unknown_standard_part"
    if canonical is None:
        return None
    metadata = {
        "standard_part": True,
        "canonical_type": canonical,
        "designation": _designation_from_text(f"{name} {source_text}"),
        "original_label": name,
        "object_label": name,
        "detection_method": "source_and_label_heuristic" if source_known else "label_heuristic",
        "confidence": "medium" if source_known else "low",
    }
    if source_known:
        metadata["source_library"] = "bd_warehouse"
    return {k: v for k, v in metadata.items() if v not in (None, "")}


def _standard_part_bom_summary(features: list[dict[str, Any]]) -> dict[str, Any] | None:
    items: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}
    for feat in features:
        if feat.get("type") != "standard_part" or not feat.get("standard_part"):
            continue
        canonical = str(feat.get("canonical_type") or "unknown_standard_part")
        by_type[canonical] = by_type.get(canonical, 0) + 1
        item = {
            "feature_id": feat.get("id"),
            "name": feat.get("name"),
            "canonical_type": canonical,
        }
        for key in ("designation", "source_library", "confidence"):
            if feat.get(key):
                item[key] = feat[key]
        items.append(item)
    if not items:
        return None
    return {
        "count": len(items),
        "by_canonical_type": by_type,
        "items": items,
        "source": "feature_graph_standard_part_detection",
        "limitations": "Best-effort semantic recognition; not a supplier BOM or validation claim.",
    }


def _is_named_part_feature(feature: dict[str, Any]) -> bool:
    return feature.get("type") in {"named_part", "standard_part"} and bool(feature.get("name"))


def _topology_to_feature_graph(
    topo: dict[str, Any],
    source_code: str | None = None,
    model_kind: str = "auto",
) -> dict[str, Any]:
    """Heuristic: derive a feature_graph.json from extracted topology.

    When ``source_code`` is provided (the build123d script that produced this
    topology), scan it for UPPER_SNAKE_CASE named constants and attach them as
    editable parameters to the matching features. This is what makes
    ``cad.edit_parameter`` a fast text-replacement instead of an LLM round-trip.

    ``model_kind`` gates the mechanical heuristics (bolt patterns, base plate):
    ``"mechanical"`` runs them, ``"organic"`` skips them, ``"auto"`` (default)
    infers from labels + helper usage. On a character/vehicle the bolt-pattern
    heuristic otherwise mislabels limb cylinders as "mounting_hole_pattern" and
    the bottom face as a "base_plate" — noise that pollutes the feature graph.
    """
    entities = topo.get("entities", [])
    faces = [e for e in entities if e.get("type") == "face"]
    solid = next((e for e in entities if e.get("type") == "solid"), None)
    bbox = solid.get("bounding_box", [0] * 6) if solid else [0] * 6

    features: list[dict[str, Any]] = []
    feat_counter = 0

    # named parts — surface agent-supplied build123d labels as first-class features
    # so later calls can reference them (e.g. "enlarge motor_pod_FL"). The feature
    # id is derived from the body id so it stays stable across rebuilds.
    named_solids = [
        e for e in entities if e.get("type") == "solid" and e.get("name")
    ]
    for body in named_solids:
        body_faces = [f["id"] for f in faces if f.get("body_id") == body["id"]]
        standard_part = _standard_part_metadata_for_body(body, source_code)
        feature = {
            "id": f"feat_{body['id']}",
            "type": "standard_part" if standard_part else "named_part",
            "name": body["name"],
            "geometry_refs": {"body": body["id"], "faces": body_faces},
            "parameters": {},
            "intent": {"role": "standard_part" if standard_part else "named_component"},
        }
        if standard_part:
            feature.update(standard_part)
            feature["recognition"] = {
                "method": standard_part.get("detection_method", "topology_metadata"),
                "confidence": standard_part.get("confidence", "medium"),
            }
            feature["intent"] = {
                "role": "standard_part",
                "canonical_type": standard_part.get("canonical_type", "unknown_standard_part"),
            }
        features.append(feature)

    resolved_kind = model_kind if model_kind in ("organic", "mechanical") else _infer_model_kind(named_solids, source_code)
    run_mechanical_heuristics = resolved_kind != "organic"

    if run_mechanical_heuristics:
        # bolt pattern detection — group cylinders by radius (±8% tolerance)
        cylinders = [f for f in faces if f.get("surface_type") == "cylinder" and f.get("radius")]
        radius_groups: dict[float, list[str]] = {}
        for face in cylinders:
            r = float(face["radius"])
            matched = next(
                (kr for kr in radius_groups if abs(r - kr) / max(r, kr) < 0.08),
                None,
            )
            if matched is None:
                radius_groups[r] = [face["id"]]
            else:
                radius_groups[matched].append(face["id"])

        for radius, face_ids in radius_groups.items():
            if len(face_ids) >= 2:
                feat_counter += 1
                ftype = "mounting_hole_pattern" if len(face_ids) >= 4 else "mounting_hole"
                features.append({
                    "id": f"feat_{feat_counter:03d}",
                    "type": ftype,
                    "name": f"Hole pattern r={radius:.1f}mm ({len(face_ids)} holes)",
                    "geometry_refs": {"faces": face_ids},
                    "parameters": {"hole_diameter_mm": round(radius * 2, 2), "count": len(face_ids)},
                    "intent": {"role": "mounting_candidate"},
                })

        # base plate — largest planar face in the bottom 20% of Z range.
        # Skip the heuristic entirely for degenerate Z extents (flat shells / no
        # Z thickness) so we never advertise a 0 mm-thick "base plate" feature.
        planes = [f for f in faces if f.get("surface_type") == "plane"]
        z_range = bbox[5] - bbox[2]
        bottom_planes: list[dict[str, Any]] = []
        if z_range > 1e-6:
            z_threshold = bbox[2] + z_range * 0.2
            bottom_planes = [
                f for f in planes
                if f.get("normal") and f["normal"][2] < -0.8
                and (f.get("center", [0, 0, 0])[2]) <= z_threshold
            ]
        if bottom_planes:
            base = max(bottom_planes, key=lambda f: f.get("area", 0.0))
            bb = base.get("bounding_box", [0] * 6)
            feat_counter += 1
            features.append({
                "id": f"feat_{feat_counter:03d}",
                "type": "base_plate",
                "name": "Base face",
                "geometry_refs": {"faces": [base["id"]]},
                "parameters": {
                    "length_mm": round(bb[3] - bb[0], 2),
                    "width_mm": round(bb[4] - bb[1], 2),
                    "thickness_mm": round(z_range, 2),
                },
                "intent": {"role": "structural_base"},
            })

    feature_graph = {"format_version": "0.1.0", "features": features, "model_kind": resolved_kind}
    standard_part_summary = _standard_part_bom_summary(features)
    if standard_part_summary:
        feature_graph["metadata"] = {"standard_parts": standard_part_summary}
    if source_code:
        feature_graph = _enrich_feature_graph_with_source_params(source_code, feature_graph)
    return feature_graph


def _named_parts_from_feature_graph(feature_graph: dict[str, Any]) -> list[str]:
    """Extract the ordered list of named-part labels from a feature graph."""
    return [
        f["name"]
        for f in (feature_graph or {}).get("features", [])
        if _is_named_part_feature(f)
    ]


def _slim_feature_graph_for_response(feature_graph: dict[str, Any]) -> dict[str, Any]:
    """Return a token-lean copy of the feature graph for tool responses.

    The full graph (with every per-feature BREP face id) is persisted to
    ``graph/feature_graph.json`` and is reachable via aieng.agent_context /
    aieng.inspect_package. Echoing all of those face ids back on *every* build is
    the dominant token cost of a cad.execute_build123d response, and the agent
    never needs the raw face lists to decide the next step. This keeps what the
    agent actually uses — feature id/type/name, editable ``parameters``, intent,
    and the ``body`` ref — and collapses each ``geometry_refs.faces`` array to a
    ``face_count``. Does not mutate the input.
    """
    if not isinstance(feature_graph, dict):
        return feature_graph
    slim: dict[str, Any] = {k: v for k, v in feature_graph.items() if k != "features"}
    slim_features: list[Any] = []
    for feat in feature_graph.get("features", []) or []:
        if not isinstance(feat, dict):
            slim_features.append(feat)
            continue
        new_feat = {k: v for k, v in feat.items() if k != "geometry_refs"}
        refs = feat.get("geometry_refs")
        if isinstance(refs, dict):
            slim_refs = {k: v for k, v in refs.items() if k != "faces"}
            faces = refs.get("faces")
            if isinstance(faces, list):
                slim_refs["face_count"] = len(faces)
            new_feat["geometry_refs"] = slim_refs
        slim_features.append(new_feat)
    slim["features"] = slim_features
    return slim


def _available_named_parts_from_topology(topology_map: dict[str, Any]) -> list[str]:
    """Return all named solid/body labels in topology order."""
    return [
        str(entity["name"])
        for entity in (topology_map or {}).get("entities", [])
        if entity.get("type") == "solid" and entity.get("name")
    ]


# ── quantitative geometry report ───────────────────────────────────────────────
# The agent judges form badly from a blurry thumbnail but reasons well over
# numbers. This report converts "does it look right?" into deterministic signals
# the agent can self-correct against: part proportions, symmetry residuals, and
# a contact/gap matrix. Returned alongside the thumbnail on every build.

# Name-token pairs that signal a left/right mirror partner. Checked longest-first
# so `_fl`/`_fr` win over `_l`/`_r`.
_MIRROR_TOKEN_PAIRS: tuple[tuple[str, str], ...] = (
    ("_fl", "_fr"), ("_bl", "_br"),
    ("_lf", "_rf"), ("_lb", "_rb"),
    ("left", "right"),
    ("_l", "_r"),
)


def _mirror_partner_name(name: str) -> str | None:
    """Return the expected mirror-partner name for a part, or None.

    e.g. motor_pod_FL → motor_pod_FR, left_arm → right_arm.
    Direction-agnostic: maps either side to the other.
    """
    low = name.lower()
    for a, b in _MIRROR_TOKEN_PAIRS:
        if low.endswith(a):
            return name[: len(name) - len(a)] + b
        if low.endswith(b):
            return name[: len(name) - len(b)] + a
        # also handle mid-name "left"/"right"
        if a == "left" and "left" in low:
            return low.replace("left", "right")
        if a == "left" and "right" in low:
            return low.replace("right", "left")
    return None


def _bbox_metrics(bb: list[float]) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    """Return (center, size, max_dim) for a 6-element bbox."""
    center = ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)
    size = (bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
    return center, size, max(size)


def _compute_geometry_report(topology_map: dict[str, Any], max_parts: int = 14) -> dict[str, Any]:
    """Produce a deterministic, agent-readable geometry report from topology.

    Sections:
      overall_bbox / overall_proportions  — model size + normalized H:W:D
      parts            — per-named-part dims, max-dim, ratio to largest part
      symmetry         — for detected left/right name pairs, size + mirror residual
      gaps             — each part's nearest-neighbour gap (touching vs floating)
    Every number is in millimetres unless noted. Designed to be small enough to
    travel in the MCP text response so the agent can cite specifics like
    "arm_len/torso_len = 0.42, too short".
    """
    entities = (topology_map or {}).get("entities", [])
    solids = [
        e for e in entities
        if e.get("type") == "solid" and isinstance(e.get("bounding_box"), list)
        and len(e["bounding_box"]) == 6
    ]
    if not solids:
        return {"available": False, "reason": "no solids with bounding boxes in topology"}

    # Overall bbox (union of all solids)
    xs = [s["bounding_box"] for s in solids]
    ov = [
        min(b[0] for b in xs), min(b[1] for b in xs), min(b[2] for b in xs),
        max(b[3] for b in xs), max(b[4] for b in xs), max(b[5] for b in xs),
    ]
    ov_center, ov_size, ov_max = _bbox_metrics(ov)
    ov_max = ov_max or 1.0

    def _r(x: float, n: int = 2) -> float:
        return round(float(x), n)

    report: dict[str, Any] = {
        "available": True,
        "units": "mm",
        "part_count": len(solids),
        "overall_bbox": [_r(v) for v in ov],
        "overall_size": {"x": _r(ov_size[0]), "y": _r(ov_size[1]), "z": _r(ov_size[2])},
        "overall_proportions": {
            "x": _r(ov_size[0] / ov_max, 3),
            "y": _r(ov_size[1] / ov_max, 3),
            "z": _r(ov_size[2] / ov_max, 3),
            "note": "normalized so the largest overall dimension = 1.0",
        },
    }

    # Per-part metrics
    part_recs: list[dict[str, Any]] = []
    named: list[tuple[str, tuple[float, float, float], tuple[float, float, float], float]] = []
    largest_part_dim = max(_bbox_metrics(s["bounding_box"])[2] for s in solids) or 1.0
    for s in solids:
        name = s.get("name") or s.get("id")
        c, sz, mx = _bbox_metrics(s["bounding_box"])
        named.append((name, c, sz, mx))
        part_recs.append({
            "name": name,
            "size": {"x": _r(sz[0]), "y": _r(sz[1]), "z": _r(sz[2])},
            "max_dim": _r(mx),
            "ratio_to_largest": _r(mx / largest_part_dim, 3),
        })
    report["parts"] = part_recs[:max_parts]
    if len(part_recs) > max_parts:
        report["parts_truncated"] = len(part_recs) - max_parts

    # Symmetry: match left/right name pairs, report size + mirror residuals.
    name_to_idx = {n.lower(): i for i, (n, *_rest) in enumerate(named)}
    symmetry: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for name, c, sz, _mx in named:
        partner = _mirror_partner_name(name)
        if not partner:
            continue
        pidx = name_to_idx.get(partner.lower())
        if pidx is None:
            symmetry.append({
                "part": name,
                "expected_partner": partner,
                "status": "missing_partner",
                "note": "mirror partner not found — symmetry likely broken",
            })
            continue
        key = tuple(sorted((name.lower(), partner.lower())))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        _pn, pc, psz, _pmx = named[pidx]
        # Size residual — mirror parts should be the same size.
        size_res = max(abs(sz[0] - psz[0]), abs(sz[1] - psz[1]), abs(sz[2] - psz[2]))
        # Mirror axis = the axis along which the two centers are most separated
        # (the symmetry plane is normal to it). Robust to a skewed global center
        # because it only looks at the pair. For a true mirror, the OTHER two
        # axes should align — that misalignment is the residual.
        seps = [abs(c[ax] - pc[ax]) for ax in range(3)]
        mirror_ax = max(range(3), key=lambda ax: seps[ax])
        align_res = max(seps[o] for o in range(3) if o != mirror_ax)
        symmetry.append({
            "pair": [name, named[pidx][0]],
            "size_residual_mm": _r(size_res),
            "mirror_axis": "xyz"[mirror_ax],
            "mirror_separation_mm": _r(seps[mirror_ax]),
            "align_residual_mm": _r(align_res),
            "ok": bool(
                size_res < max(1.0, largest_part_dim * 0.02)
                and align_res < max(1.0, ov_max * 0.02)
            ),
        })
    if symmetry:
        report["symmetry"] = symmetry

    # Gap matrix: each part's nearest-neighbour approximate gap. Negative ⇒
    # overlapping/touching (good for an assembly); large positive ⇒ floating.
    if len(named) >= 2:
        gap_recs: list[dict[str, Any]] = []
        mean_size = sum(m for *_x, m in named) / len(named)
        gap_threshold = max(mean_size, 50.0)
        for i, (name, c1, _s1, m1) in enumerate(named):
            min_gap = float("inf")
            nearest = None
            for j, (n2, c2, _s2, m2) in enumerate(named):
                if i == j:
                    continue
                dist = ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5
                gap = dist - (m1 + m2) / 2.0
                if gap < min_gap:
                    min_gap = gap
                    nearest = n2
            status = "touching" if min_gap <= 0 else ("floating" if min_gap > gap_threshold else "near")
            gap_recs.append({
                "part": name,
                "nearest": nearest,
                "gap_mm": _r(min_gap),
                "status": status,
            })
        report["gaps"] = gap_recs[:max_parts]
        if len(gap_recs) > max_parts:
            report["gaps_truncated"] = len(gap_recs) - max_parts
        floating = [g["part"] for g in gap_recs if g["status"] == "floating"]
        # Always-present contact summary over ALL parts (not just the truncated
        # gaps list above) so the agent can confirm "everything touches / N
        # floating" even on large models where the per-part gaps are clipped.
        report["gaps_summary"] = {
            "touching": sum(1 for g in gap_recs if g["status"] == "touching"),
            "near": sum(1 for g in gap_recs if g["status"] == "near"),
            "floating": len(floating),
            "total": len(gap_recs),
        }
        if floating:
            report["floating_parts"] = floating

    return report


# Response detail and exact build123d execution cache helpers.

def _normalize_response_detail(value: Any) -> str:
    detail = str(value or "full").strip().lower()
    return detail if detail in {"compact", "full"} else "full"


def _should_render_thumbnail(payload_or_flag: Any, response_detail: str) -> bool:
    if isinstance(payload_or_flag, dict) and "thumbnail" in payload_or_flag:
        return bool(payload_or_flag.get("thumbnail"))
    if isinstance(payload_or_flag, bool):
        return payload_or_flag
    return response_detail != "compact"


def _geometry_report_summary(report: dict[str, Any]) -> str:
    if not report or not report.get("available"):
        reason = report.get("reason", "no report") if isinstance(report, dict) else "no report"
        return f"geometry unavailable: {reason}"
    size = report.get("overall_size") if isinstance(report.get("overall_size"), dict) else {}
    proportions = report.get("overall_proportions") if isinstance(report.get("overall_proportions"), dict) else {}
    gaps = report.get("gaps_summary") if isinstance(report.get("gaps_summary"), dict) else {}
    symmetry = report.get("symmetry") if isinstance(report.get("symmetry"), list) else []
    symmetry_issues = sum(
        1
        for item in symmetry
        if item.get("ok") is False or item.get("status") == "missing_partner"
    )
    return (
        "geometry: "
        f"{report.get('part_count', 0)} part(s), "
        f"size={size.get('x', '?')}x{size.get('y', '?')}x{size.get('z', '?')} mm, "
        f"proportions={proportions.get('x', '?')}/{proportions.get('y', '?')}/{proportions.get('z', '?')}, "
        f"floating={gaps.get('floating', 0)}, "
        f"symmetry_issues={symmetry_issues}"
    )


def _geometry_report_for_response(report: dict[str, Any], response_detail: str) -> dict[str, Any] | str:
    if response_detail == "compact":
        return _geometry_report_summary(report)
    return report


_BUILD123D_CACHE_FORMAT_VERSION = "1"
def _parse_cache_env(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (ValueError, KeyError):
        return default


_BUILD123D_CACHE_MAX_ENTRIES = _parse_cache_env("AIENG_CACHE_MAX_ENTRIES", 64)
_BUILD123D_CACHE_MAX_BYTES = _parse_cache_env("AIENG_CACHE_MAX_BYTES", 512 * 1024 * 1024)
# Grace seconds added to FileLock timeout so followers can wait through the
# build + post-build work (feature graph, geometry report, cache write/prune)
# that the lock holder performs after _execute_build123d_code returns.
_BUILD123D_CACHE_LOCK_GRACE_SECONDS = 30


def _package_version(name: str) -> str:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return "not-installed"
    except Exception:
        return "unknown"


def _build123d_cache_versions() -> dict[str, str]:
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "build123d": _package_version("build123d"),
        "ocp": _package_version("ocp"),
        "cadquery-ocp": _package_version("cadquery-ocp"),
    }


_STEP_LABELS_SURVIVE_ROUNDTRIP: bool | None = None


def _step_roundtrip_preserves_labels() -> bool:
    """Check whether build123d preserves part labels through STEP export/import.

    Cached per-process so the probe runs at most once. Returns ``False`` when
    build123d is unavailable or the roundtrip drops the label.
    """
    global _STEP_LABELS_SURVIVE_ROUNDTRIP
    if _STEP_LABELS_SURVIVE_ROUNDTRIP is not None:
        return _STEP_LABELS_SURVIVE_ROUNDTRIP
    try:
        import build123d as b3d
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "probe.step"
            part = b3d.Box(10, 10, 10)
            part.label = "aieng_probe_label"
            b3d.export_step(part, str(path))
            imported = b3d.import_step(str(path))
            _STEP_LABELS_SURVIVE_ROUNDTRIP = getattr(imported, "label", "") == "aieng_probe_label"
    except Exception:
        _STEP_LABELS_SURVIVE_ROUNDTRIP = False
    return _STEP_LABELS_SURVIVE_ROUNDTRIP


def _build123d_cache_key(*, code: str, mode: str, model_kind: str) -> tuple[str, dict[str, Any]]:
    material = {
        "cache_format_version": _BUILD123D_CACHE_FORMAT_VERSION,
        "executor": "build123d_streaming",
        "mode": mode,
        "model_kind": model_kind,
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "versions": _build123d_cache_versions(),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), material


def _build123d_cache_root(settings: Any) -> Path:
    return Path(settings.data_root) / "cache" / "build123d"


def _cache_entry_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _prune_build123d_cache(root: Path) -> None:
    try:
        entries = [p for p in root.iterdir() if p.is_dir() and not p.name.endswith(".tmp")]
    except OSError:
        return
    if not entries:
        return
    sized = [(p, _cache_entry_size(p)) for p in entries]
    total = sum(size for _p, size in sized)
    if len(sized) <= _BUILD123D_CACHE_MAX_ENTRIES and total <= _BUILD123D_CACHE_MAX_BYTES:
        return

    def _mtime(path: Path) -> float:
        marker = path / ".complete"
        try:
            return marker.stat().st_mtime if marker.exists() else path.stat().st_mtime
        except OSError:
            return 0.0

    for entry, size in sorted(sized, key=lambda item: _mtime(item[0])):
        if len(sized) <= _BUILD123D_CACHE_MAX_ENTRIES and total <= _BUILD123D_CACHE_MAX_BYTES:
            break
        shutil.rmtree(entry, ignore_errors=True)
        total -= size
        sized = [(p, s) for p, s in sized if p != entry]


_CACHE_REQUIRED_FILES = {
    "metadata.json",
    "generated.step",
    "preview.stl",
    "topology_map.json",
    "feature_graph.json",
    "geometry_report.json",
}


def _read_build123d_cache(settings: Any, cache_key: str) -> dict[str, Any] | None:
    """Read a cached build123d result, validating integrity.

    Verifies that all required artifact files exist and that the metadata
    cache_key and cache_format_version match. Incomplete or corrupt entries
    are treated as misses and removed so they do not poison future lookups.
    """
    entry = _build123d_cache_root(settings) / cache_key
    if not (entry / ".complete").exists():
        return None
    try:
        # Integrity: every required file must be present and readable.
        missing = [name for name in _CACHE_REQUIRED_FILES if not (entry / name).is_file()]
        if missing:
            shutil.rmtree(entry, ignore_errors=True)
            return None

        meta = json.loads((entry / "metadata.json").read_text(encoding="utf-8"))
        if meta.get("cache_key") != cache_key:
            shutil.rmtree(entry, ignore_errors=True)
            return None
        if meta.get("cache_format_version") != _BUILD123D_CACHE_FORMAT_VERSION:
            shutil.rmtree(entry, ignore_errors=True)
            return None

        return {
            "step_bytes": (entry / "generated.step").read_bytes(),
            "stl_bytes": (entry / "preview.stl").read_bytes(),
            "glb_bytes": (entry / "preview.glb").read_bytes() if (entry / "preview.glb").exists() else b"",
            "topology_map": json.loads((entry / "topology_map.json").read_text(encoding="utf-8")),
            "feature_graph": json.loads((entry / "feature_graph.json").read_text(encoding="utf-8")),
            "geometry_report": json.loads((entry / "geometry_report.json").read_text(encoding="utf-8")),
            "mesh_meta": (
                json.loads((entry / "mesh_meta.json").read_text(encoding="utf-8"))
                if (entry / "mesh_meta.json").exists()
                else None
            ),
        }
    except Exception:
        shutil.rmtree(entry, ignore_errors=True)
        return None


def _write_build123d_cache(
    settings: Any,
    cache_key: str,
    key_material: dict[str, Any],
    *,
    step_bytes: bytes,
    stl_bytes: bytes,
    glb_bytes: bytes,
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
    geometry_report: dict[str, Any],
    mesh_meta: Any,
    _already_locked: bool = False,
) -> None:
    """Write a build123d result to the cache with per-key locking and atomic promotion.

    Uses filelock so concurrent identical requests serialize writes. Writes to a
    temporary directory first, then renames atomically so readers never observe
    partial artifacts.

    Pass ``_already_locked=True`` when the caller already holds the per-key lock
    (e.g. inside ``_execute_build123d_cached``) to avoid reentrant-deadlock.
    """
    if not step_bytes:
        return
    root = _build123d_cache_root(settings)
    entry = root / cache_key

    def _do_write() -> None:
        if (entry / ".complete").exists():
            return
        # Atomic write: build in a temp sibling directory, then rename.
        tmp_entry = root / (cache_key + ".tmp")
        shutil.rmtree(tmp_entry, ignore_errors=True)
        tmp_entry.mkdir(parents=True, exist_ok=True)

        metadata = {
            "cache_key": cache_key,
            "cache_format_version": _BUILD123D_CACHE_FORMAT_VERSION,
            "created_at": time.time(),
            "key_material": key_material,
        }
        (tmp_entry / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        (tmp_entry / "generated.step").write_bytes(step_bytes)
        (tmp_entry / "preview.stl").write_bytes(stl_bytes or b"")
        if glb_bytes:
            (tmp_entry / "preview.glb").write_bytes(glb_bytes)
        (tmp_entry / "topology_map.json").write_text(json.dumps(topology_map, indent=2), encoding="utf-8")
        (tmp_entry / "feature_graph.json").write_text(json.dumps(feature_graph, indent=2), encoding="utf-8")
        (tmp_entry / "geometry_report.json").write_text(json.dumps(geometry_report, indent=2), encoding="utf-8")
        if mesh_meta is not None:
            (tmp_entry / "mesh_meta.json").write_text(json.dumps(mesh_meta, indent=2), encoding="utf-8")
        (tmp_entry / ".complete").write_text("ok", encoding="utf-8")

        os.replace(str(tmp_entry), str(entry))
        _prune_build123d_cache(root)

    try:
        if _already_locked:
            _do_write()
        else:
            lock_path = str(entry) + ".lock"
            with FileLock(lock_path, timeout=30):
                _do_write()
    except Exception:
        # Only clean up the temp directory; do NOT delete a finalized entry
        # that may have been valid before this write attempt.
        shutil.rmtree(root / (cache_key + ".tmp"), ignore_errors=True)


def _execute_build123d_cached(
    settings: Any,
    code: str,
    *,
    mode: str = "replace",
    model_kind: str = "auto",
    timeout: int = 60,
) -> dict[str, Any]:
    """Execute build123d code with exact-content caching (shared by all mutation paths).

    Checks the content-addressed cache first; on a miss, runs the non-streaming
    executor, computes the feature graph and geometry report, writes the result
    to cache, and returns everything the caller needs.

    Returns a dict with keys:
      step_bytes, stl_bytes, glb_bytes, topo, feature_graph, geometry_report,
      mesh_meta, cache_hit
    """
    cache_key, cache_key_material = _build123d_cache_key(
        code=code, mode=mode, model_kind=model_kind,
    )
    cached = _read_build123d_cache(settings, cache_key)
    if cached is not None:
        topo = cached["topology_map"]
        mesh_meta = topo.pop("_mesh_meta", None) if isinstance(topo, dict) else None
        # Restore mesh_meta from cache if it was stored separately.
        if mesh_meta is None and cached.get("mesh_meta") is not None:
            mesh_meta = cached["mesh_meta"]
        return {
            "step_bytes": cached["step_bytes"],
            "stl_bytes": cached["stl_bytes"],
            "glb_bytes": cached["glb_bytes"],
            "topo": topo,
            "feature_graph": cached["feature_graph"],
            "geometry_report": cached.get("geometry_report") or _compute_geometry_report(topo),
            "mesh_meta": mesh_meta,
            "cache_hit": True,
        }

    # Double-checked locking: acquire per-key lock and re-check cache so only
    # one thread pays the build123d execution cost for a given cache key.
    root = _build123d_cache_root(settings)
    entry = root / cache_key
    lock_path = str(entry) + ".lock"
    with FileLock(lock_path, timeout=timeout + _BUILD123D_CACHE_LOCK_GRACE_SECONDS):
        cached = _read_build123d_cache(settings, cache_key)
        if cached is not None:
            topo = cached["topology_map"]
            mesh_meta = topo.pop("_mesh_meta", None) if isinstance(topo, dict) else None
            if mesh_meta is None and cached.get("mesh_meta") is not None:
                mesh_meta = cached["mesh_meta"]
            return {
                "step_bytes": cached["step_bytes"],
                "stl_bytes": cached["stl_bytes"],
                "glb_bytes": cached["glb_bytes"],
                "topo": topo,
                "feature_graph": cached["feature_graph"],
                "geometry_report": cached.get("geometry_report") or _compute_geometry_report(topo),
                "mesh_meta": mesh_meta,
                "cache_hit": True,
            }

        step_bytes, stl_bytes, glb_bytes, topo = _execute_build123d_code(code, timeout=timeout)
        mesh_meta = topo.pop("_mesh_meta", None) if isinstance(topo, dict) else None
        feature_graph = _topology_to_feature_graph(
            topo, source_code=code, model_kind=model_kind,
        )
        geometry_report = _compute_geometry_report(topo)
        _write_build123d_cache(
            settings,
            cache_key,
            cache_key_material,
            step_bytes=step_bytes,
            stl_bytes=stl_bytes or b"",
            glb_bytes=glb_bytes or b"",
            topology_map=topo,
            feature_graph=feature_graph,
            geometry_report=geometry_report,
            mesh_meta=mesh_meta,
            _already_locked=True,
        )
    return {
        "step_bytes": step_bytes,
        "stl_bytes": stl_bytes,
        "glb_bytes": glb_bytes,
        "topo": topo,
        "feature_graph": feature_graph,
        "geometry_report": geometry_report,
        "mesh_meta": mesh_meta,
        "cache_hit": False,
    }


def _finish_execute_build123d_response(
    *,
    settings: Any,
    project_id: str,
    project: dict[str, Any],
    payload: dict[str, Any],
    code: str,
    mode: str,
    used_base: bool,
    prior_named_parts: list[str],
    step_bytes: bytes,
    stl_bytes: bytes,
    glb_bytes: bytes,
    topo: dict[str, Any],
    feature_graph: dict[str, Any],
    mesh_meta: Any,
    geometry_report_full: dict[str, Any],
    write_files: bool,
    response_detail: str,
    cache_hit: bool,
    emit: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    from .project_io import resolve_project_path

    face_count = sum(1 for e in topo.get("entities", []) if e.get("type") == "face")
    feature_count = len(feature_graph.get("features", []))
    written: list[str] = []
    if write_files and step_bytes:
        emit({"phase": "writing"})
        existing_pkg = project.get("aieng_file")
        pkg_path = resolve_project_path(settings, project_id, existing_pkg) if existing_pkg else None
        if pkg_path is None:
            from .main import project_dir, save_project as _save_project

            pkg_name = f"{project_id}.aieng"
            pkg_path = project_dir(settings, project_id) / pkg_name
            project["aieng_file"] = pkg_name
            _save_project(settings, project)

        _write_cad_artifacts(
            pkg_path=pkg_path,
            step_bytes=step_bytes,
            stl_bytes=stl_bytes or b"",
            topology_map=topo,
            feature_graph=feature_graph,
            generated_code=code,
            glb_bytes=glb_bytes,
        )
        _clear_revalidation_status(pkg_path)

        try:
            from .main import save_project as _save_project2, now_iso as _now_iso

            project["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
            req_name = str(payload.get("name") or "").strip()
            if req_name:
                project["name"] = req_name
            project["updated_at"] = _now_iso()
            _save_project2(settings, project)
        except Exception:
            pass

        _publish_preview_to_viewer(settings, project_id, project, glb_bytes, stl_bytes)
        written = [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ]
        if glb_bytes:
            written.append("geometry/preview.glb")

    solid = next((e for e in topo.get("entities", []) if e.get("type") == "solid"), None)
    named_parts = _named_parts_from_feature_graph(feature_graph)
    result: dict[str, Any] = {
        "status": "ok",
        "schema_version": "0.1",
        "project_id": project_id,
        "backend": "build123d",
        "mode": mode,
        "used_base": used_base,
        "cache_hit": cache_hit,
        "response_detail": response_detail,
        "named_parts": named_parts,
        "parts_added": [p for p in named_parts if p not in prior_named_parts],
        "topology_summary": {
            "face_count": face_count,
            "feature_count": feature_count,
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": _slim_feature_graph_for_response(feature_graph),
        "geometry_report": _geometry_report_for_response(geometry_report_full, response_detail),
        "geometry_report_summary": _geometry_report_summary(geometry_report_full),
        "written_artifacts": written,
        "write_files": write_files,
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if glb_bytes else "stl",
    }
    if _should_render_thumbnail(payload, response_detail):
        face_colors = _build_face_colors_from_mesh_meta(mesh_meta)
        ref_aieng_file = project.get("aieng_file")
        ref_pkg = resolve_project_path(settings, project_id, ref_aieng_file) if ref_aieng_file else None
        thumb = render_mesh_thumbnail(
            stl_bytes or b"",
            face_colors=face_colors,
            reference_image_bytes=_read_reference_image_bytes(ref_pkg),
        )
        if thumb:
            result["thumbnail_png_base64"] = thumb
    return result


# Geometry regression diff: a parametric edit or rebuild is supposed to change
# one thing. Compare before/after topology by named part so collateral changes
# are visible instead of silently shipping.
def _solids_by_name(topology_map: dict[str, Any]) -> dict[str, list[float]]:
    """Map each named solid to its bounding box. Unnamed solids fall back to id
    so they still participate in the diff."""
    out: dict[str, list[float]] = {}
    for e in (topology_map or {}).get("entities", []):
        if e.get("type") != "solid":
            continue
        bb = e.get("bounding_box")
        if not isinstance(bb, list) or len(bb) != 6:
            continue
        key = e.get("name") or e.get("id")
        if key:
            out[str(key)] = bb
    return out


def _diff_topology(
    before: dict[str, Any],
    after: dict[str, Any],
    expected_parts: set[str] | None = None,
    eps_mm: float = 0.05,
) -> dict[str, Any]:
    """Diff two topology maps by named part.

    Reports, per named part: bbox size delta (per axis), center shift, and
    whether it changed beyond ``eps_mm``. Parts present only before/after are
    listed as removed/added.

    ``expected_parts`` is the set of part names the caller intended to affect
    (e.g. the edited feature's part, or all parts for a global constant). Any
    changed part NOT in that set is flagged as `collateral` — a likely
    regression. When ``expected_parts`` is None, no collateral judgment is made.
    """
    a = _solids_by_name(before)
    b = _solids_by_name(after)

    def _r(x: float) -> float:
        return round(float(x), 2)

    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))

    changed: list[dict[str, Any]] = []
    unchanged: list[str] = []
    for name in sorted(set(a) & set(b)):
        ba, bb = a[name], b[name]
        _ca, sa, _ma = _bbox_metrics(ba)
        _cb, sb, _mb = _bbox_metrics(bb)
        size_delta = (sb[0] - sa[0], sb[1] - sa[1], sb[2] - sa[2])
        center_shift = (
            (bb[0] + bb[3]) / 2 - (ba[0] + ba[3]) / 2,
            (bb[1] + bb[4]) / 2 - (ba[1] + ba[4]) / 2,
            (bb[2] + bb[5]) / 2 - (ba[2] + ba[5]) / 2,
        )
        max_change = max(abs(v) for v in (*size_delta, *center_shift))
        if max_change <= eps_mm:
            unchanged.append(name)
            continue
        rec: dict[str, Any] = {
            "part": name,
            "size_delta_mm": {"x": _r(size_delta[0]), "y": _r(size_delta[1]), "z": _r(size_delta[2])},
            "center_shift_mm": {"x": _r(center_shift[0]), "y": _r(center_shift[1]), "z": _r(center_shift[2])},
            "max_change_mm": _r(max_change),
        }
        if expected_parts is not None:
            rec["expected"] = name in expected_parts
        changed.append(rec)

    collateral = (
        [c["part"] for c in changed if c.get("expected") is False]
        if expected_parts is not None else []
    )

    summary: dict[str, Any]
    if not changed and not added and not removed:
        verdict = "identical"
        headline = "No geometry changed (parameter had no effect — wrong constant or no-op value?)."
    elif collateral:
        verdict = "collateral_change"
        headline = (
            f"WARNING: {len(collateral)} unrelated part(s) also changed: "
            f"{', '.join(collateral)}. The edit likely affected geometry it "
            "shouldn't have — verify the constant isn't shared across parts."
        )
    elif added or removed:
        verdict = "topology_changed"
        headline = (
            f"Part set changed (added: {added or '—'}, removed: {removed or '—'}). "
            "A dimensional edit normally preserves the part set; review if unexpected."
        )
    else:
        verdict = "clean"
        headline = (
            f"{len(changed)} part(s) changed as expected; "
            f"{len(unchanged)} unchanged."
        )

    return {
        "verdict": verdict,
        "headline": headline,
        "changed": changed,
        "added": added,
        "removed": removed,
        "unchanged_count": len(unchanged),
        "collateral_parts": collateral,
    }


# ── parametric editing: extract editable parameters from source.py ─────────────

_PARAM_CONSTANT_RE = re.compile(r"^([ \t]*)([A-Z][A-Z0-9_]*)[ \t]*=[ \t]*([0-9]+\.?[0-9]*)([ \t]*(?:#.*)?)$")


def _infer_param_name(const_name: str) -> str:
    """Infer a human-friendly parameter name from a UPPER_SNAKE_CASE constant."""
    lower = const_name.lower()
    # Dimensional suffixes take priority
    for suffix, unit in [
        ("_radius_mm", "radius_mm"),
        ("_diameter_mm", "diameter_mm"),
        ("_height_mm", "height_mm"),
        ("_length_mm", "length_mm"),
        ("_width_mm", "width_mm"),
        ("_depth_mm", "depth_mm"),
        ("_thickness_mm", "thickness_mm"),
        ("_offset_mm", "offset_mm"),
        ("_angle_deg", "angle_deg"),
        ("_radius", "radius_mm"),
        ("_diameter", "diameter_mm"),
        ("_height", "height_mm"),
        ("_length", "length_mm"),
        ("_width", "width_mm"),
        ("_depth", "depth_mm"),
        ("_thickness", "thickness_mm"),
        ("_offset", "offset_mm"),
        ("_angle", "angle_deg"),
    ]:
        if lower.endswith(suffix):
            return unit
    # Content-based inference
    if "radius" in lower:
        return "radius_mm"
    if "diameter" in lower:
        return "diameter_mm"
    if "height" in lower:
        return "height_mm"
    if "length" in lower:
        return "length_mm"
    if "width" in lower:
        return "width_mm"
    if "depth" in lower:
        return "depth_mm"
    if "thickness" in lower:
        return "thickness_mm"
    if "fillet" in lower:
        return "fillet_radius_mm"
    if "offset" in lower:
        return "offset_mm"
    if "angle" in lower:
        return "angle_deg"
    return lower + "_mm"


def _match_constant_to_feature(const_name: str, feature_name: str) -> bool:
    """Determine whether a named constant likely belongs to a given feature.

    Matching rules (all case-insensitive):
    1. The constant's first word appears in the feature name.
       e.g. MOTOR_POD_RADIUS → motor_pod_FL (motor matches).
    2. The feature's first word appears in the constant name.
       e.g. BODY_LENGTH → body (body matches).
    3. Global / shared prefixes.
       e.g. FILLET_RADIUS, GLOBAL_WALL, DEFAULT_…
    4. The constant contains the feature name verbatim.
       e.g. FUSELAGE_LENGTH → fuselage
    """
    c_parts = const_name.lower().split("_")
    f_parts = feature_name.lower().replace("-", "_").split("_")
    c0 = c_parts[0]
    f0 = f_parts[0]

    if c0 in f_parts:
        return True
    if f0 in c_parts:
        return True
    if c0 in ("global", "default", "fillet", "chamfer"):
        return True
    if feature_name.lower() in const_name.lower():
        return True
    return False


def _enrich_feature_graph_with_source_params(
    source_code: str,
    feature_graph: dict[str, Any],
) -> dict[str, Any]:
    """Scan source.py for UPPER_SNAKE_CASE constants and attach them as editable
    parameters to the feature-graph features they likely belong to.

    This is what makes ``cad.edit_parameter`` work: the feature graph now carries
    ``parameters`` entries with ``cad_parameter_name`` pointing back to a named
    constant in source.py, so editing can be a deterministic text replacement
    instead of an LLM round-trip.
    """
    # 1. Extract all named constants (UPPER_SNAKE_CASE = number).
    constants: dict[str, float] = {}
    for line in source_code.splitlines():
        m = _PARAM_CONSTANT_RE.match(line)
        if m:
            name = m.group(2)
            try:
                val = float(m.group(3))
                constants[name] = val
            except ValueError:
                pass

    if not constants:
        return feature_graph

    features = feature_graph.get("features", [])

    def _param_entry(cval: float, cname: str) -> dict[str, Any]:
        return {
            "current_value": cval,
            "cad_parameter_name": cname,
            "type": "number",
            "min_value": max(0.01, cval * 0.05),
            "max_value": max(cval * 5.0, 1000.0),
        }

    def _attach(feature: dict[str, Any], params: dict[str, Any]) -> None:
        existing = feature.get("parameters") or {}
        if isinstance(existing, dict):
            # Source-derived params win over topology-derived heuristics because
            # they are the ground truth the user can actually edit.
            existing.update(params)
            feature["parameters"] = existing
        elif isinstance(existing, list):
            for k, v in params.items():
                existing.append({"name": k, **v})

    # Global / shared constants get their own feature regardless of part matching.
    global_consts = {
        k: v
        for k, v in constants.items()
        if k.split("_")[0].lower() in ("global", "default", "fillet", "chamfer", "wall")
    }

    attached: set[str] = set(global_consts)

    # 2. Attach matched constants to the feature whose name they relate to.
    for feature in features:
        fname = feature.get("name", "")
        if not fname:
            continue
        matched: dict[str, Any] = {}
        for cname, cval in constants.items():
            if cname in global_consts or not _match_constant_to_feature(cname, fname):
                continue
            pname = _infer_param_name(cname)
            if pname in matched:
                # Same inferred name from two constants — key the 2nd by its
                # constant name so both stay addressable instead of dropping one.
                pname = cname.lower()
            matched[pname] = _param_entry(cval, cname)
            attached.add(cname)
        if matched:
            _attach(feature, matched)

    # 3. Surface global constants as a synthetic "global_params" feature so
    #    agents can edit shared dims (wall thickness, default fillet).
    if global_consts and not any(f.get("type") == "global_params" for f in features):
        gparams: dict[str, Any] = {}
        for k, v in global_consts.items():
            pname = _infer_param_name(k)
            if pname in gparams:
                pname = k.lower()
            gparams[pname] = _param_entry(v, k)
        features.insert(0, {
            "id": "feat_global_params",
            "type": "global_params",
            "name": "Global Parameters",
            "parameters": gparams,
            "intent": {"role": "shared_dimensions"},
        })

    # 3b. Fallback so EVERY declared constant is editable. Constants that matched
    #     no part name and aren't global would otherwise be unreachable by
    #     cad.edit_parameter. If there's exactly one named part, they belong to
    #     it (and collateral detection still works); otherwise collect them in a
    #     generic model_params bucket.
    leftover = {k: v for k, v in constants.items() if k not in attached}
    if leftover:
        named_parts = [f for f in features if _is_named_part_feature(f)]
        params: dict[str, Any] = {}
        for k, v in leftover.items():
            pname = _infer_param_name(k)
            if pname in params:
                pname = k.lower()
            params[pname] = _param_entry(v, k)
        if len(named_parts) == 1:
            _attach(named_parts[0], params)
        elif not any(f.get("type") == "model_params" for f in features):
            features.insert(0, {
                "id": "feat_model_params",
                "type": "model_params",
                "name": "Model Parameters",
                "parameters": params,
                "intent": {"role": "unscoped_dimensions"},
            })

    # 4. Detect advanced modelling features from source code patterns
    #    (loft, revolve, sweep, fillet, mirror) so the feature graph reflects
    #    industrial-design intent, not just primitive counts.
    _source_lower = source_code.lower()
    _adv_counter = 0

    def _add_adv_feature(ftype: str, name: str, params: dict[str, Any], intent_role: str) -> None:
        nonlocal _adv_counter
        _adv_counter += 1
        features.append({
            "id": f"feat_{ftype}_{_adv_counter:03d}",
            "type": ftype,
            "name": name,
            "parameters": params,
            "intent": {"role": intent_role},
        })

    # Loft — count BuildSketch pairs with loft() between them
    loft_count = _source_lower.count("loft(")
    if loft_count > 0:
        _add_adv_feature(
            "loft",
            f"Loft ({loft_count} operation{'s' if loft_count > 1 else ''})",
            {},
            "tapered_body",
        )

    # Revolve
    revolve_count = _source_lower.count("revolve(")
    if revolve_count > 0:
        _add_adv_feature(
            "revolve",
            f"Revolve ({revolve_count} operation{'s' if revolve_count > 1 else ''})",
            {},
            "axisymmetric_body",
        )

    # Sweep
    sweep_count = _source_lower.count("sweep(")
    if sweep_count > 0:
        _add_adv_feature(
            "sweep",
            f"Sweep ({sweep_count} operation{'s' if sweep_count > 1 else ''})",
            {},
            "path_extrusion",
        )

    # Fillet — extract radii so they become editable if declared as constants
    _fillet_radii: list[float] = []
    for _fm in re.finditer(
        r'fillet\s*\([^)]*radius\s*=\s*([0-9]+\.?[0-9]*)',
        source_code,
        re.IGNORECASE,
    ):
        try:
            _fillet_radii.append(float(_fm.group(1)))
        except ValueError:
            pass
    if _fillet_radii:
        _add_adv_feature(
            "fillet",
            f"Fillet ({len(_fillet_radii)} operation{'s' if len(_fillet_radii) > 1 else ''}, "
            f"r={min(_fillet_radii):.1f}–{max(_fillet_radii):.1f}mm)",
            {"fillet_radius_mm": round(sum(_fillet_radii) / len(_fillet_radii), 2)},
            "edge_rounding",
        )

    # Mirror
    mirror_count = _source_lower.count("mirror(")
    if mirror_count > 0:
        _add_adv_feature(
            "mirror",
            f"Mirror symmetry ({mirror_count} operation{'s' if mirror_count > 1 else ''})",
            {},
            "symmetric_copy",
        )

    return feature_graph


# ── LLM API calls ──────────────────────────────────────────────────────────────

def _merge_llm_config(
    llm_config: dict[str, Any] | None,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    config = dict(llm_config or {})
    if not config:
        config = {
            "provider": "anthropic",
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL") or None,
        }
    if model:
        config["model"] = model
    if api_key:
        config["api_key"] = api_key
    return config


def _generate_llm_text(
    settings: Any,
    *,
    llm_config: dict[str, Any] | None,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    from . import agent_engine

    provider = agent_engine._build_provider(
        settings,
        _merge_llm_config(llm_config, api_key=api_key, model=model),
    )
    try:
        return provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False,
        )
    except TypeError:
        # Test doubles and older local providers may not expose json_mode yet.
        return provider.generate(system_prompt=system_prompt, user_prompt=user_prompt)


def call_claude_for_build123d_code(
    description: str,
    hints: dict[str, Any] | None = None,
    api_key: str | None = None,
    model: str | None = None,
    settings: Any | None = None,
    llm_config: dict[str, Any] | None = None,
) -> str:
    """Call the configured LLM to generate build123d Python code."""
    if settings is None:
        raise HTTPException(status_code=503, detail="LLM settings are required for CAD generation")

    ensure_aieng_on_path()
    from aieng.modeling.text_to_cad import (
        BUILD123D_SYSTEM_PROMPT,
        TextToCadHints,
        build_build123d_user_prompt,
        build_system_prompt,
    )

    hint_obj: TextToCadHints | None = None
    if hints:
        hint_obj = TextToCadHints(
            material=hints.get("material"),
            dimensions_mm=hints.get("dimensions_mm"),
            style=hints.get("style"),
            symmetry=hints.get("symmetry"),
        )

    user_prompt = build_build123d_user_prompt(description, hint_obj)

    # Inject AGENTS.md as the single source of truth for build123d capabilities.
    # Falls back to the base prompt if AGENTS.md is missing or unreadable.
    agents_md = _load_agents_md()
    system_prompt = build_system_prompt(agents_md)

    raw = _generate_llm_text(
        settings,
        llm_config=llm_config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        model=model,
    )
    return _coerce_code(raw)


# ── build123d subprocess execution ────────────────────────────────────────────

def _execute_build123d_code(
    code: str,
    timeout: int = 60,
) -> tuple[bytes, bytes, bytes, dict[str, Any]]:
    """Execute build123d code in a subprocess (blocking).

    Returns ``(step_bytes, stl_bytes, glb_bytes, topology_map)``.
    Used by the non-streaming code path; the streaming variant
    ``_execute_build123d_code_streaming`` runs a near-identical subprocess but
    yields periodic heartbeats so the SSE client sees progress during a long
    build123d invocation.
    """
    runner_script = _RUNNER_TEMPLATE.replace("__AIENG_GENERATED_CODE__", code)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        runner_path = tmp / "runner.py"
        runner_path.write_text(runner_script, encoding="utf-8")
        out_step = tmp / "result.step"
        out_topo = tmp / "topology.json"
        out_stl = tmp / "result.stl"
        out_glb = tmp / "result.glb"

        proc = subprocess.run(
            [sys.executable, str(runner_path), str(out_step), str(out_topo), str(out_stl), str(out_glb)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if proc.returncode != 0:
            stderr_excerpt = proc.stderr[-2000:] if proc.stderr else "(no stderr)"
            raise RuntimeError(
                f"build123d execution failed (exit {proc.returncode}):\n{stderr_excerpt}"
            )

        step_bytes = out_step.read_bytes() if out_step.exists() else b""
        stl_bytes = out_stl.read_bytes() if out_stl.exists() else b""
        glb_bytes = out_glb.read_bytes() if out_glb.exists() else b""
        topo: dict[str, Any] = (
            json.loads(out_topo.read_text(encoding="utf-8"))
            if out_topo.exists()
            else {}
        )
        # mesh_meta.json is best-effort: when present, it carries per-body color
        # and triangle counts for the thumbnail renderer. Stash it under a "_"-
        # prefixed key inside topo so it travels through the existing return
        # tuple without breaking any caller that unpacks 4 values.
        mesh_meta_path = out_stl.with_name("mesh_meta.json")
        if mesh_meta_path.exists():
            try:
                topo["_mesh_meta"] = json.loads(mesh_meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return step_bytes, stl_bytes, glb_bytes, topo


def _execute_build123d_code_streaming(
    code: str,
    timeout: int = 60,
    heartbeat_interval_s: float = 2.0,
) -> Iterator[dict[str, Any]]:
    """Execute build123d code as a subprocess, yielding heartbeat dicts while it runs.

    Yields:
      ``{"kind": "heartbeat", "elapsed_s": int}`` every ``heartbeat_interval_s``
      until completion. The final yield is exactly one of:
        - ``{"kind": "result", "step_bytes": bytes, "stl_bytes": bytes, "glb_bytes": bytes, "topo": dict}``
        - ``{"kind": "error", "error": str}``

    The subprocess is always reaped before the generator returns, even when the
    caller stops consuming early (e.g. client disconnect).
    """
    runner_script = _RUNNER_TEMPLATE.replace("__AIENG_GENERATED_CODE__", code)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        runner_path = tmp / "runner.py"
        runner_path.write_text(runner_script, encoding="utf-8")
        out_step = tmp / "result.step"
        out_topo = tmp / "topology.json"
        out_stl = tmp / "result.stl"
        out_glb = tmp / "result.glb"

        proc = subprocess.Popen(
            [
                sys.executable,
                str(runner_path),
                str(out_step),
                str(out_topo),
                str(out_stl),
                str(out_glb),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        start = time.monotonic()
        timed_out = False
        # Emit an initial heartbeat immediately so the UI's building stage gets a
        # progress event even when the build finishes in under heartbeat_interval_s.
        yield {"kind": "heartbeat", "elapsed_s": 0}
        try:
            while proc.poll() is None:
                elapsed = time.monotonic() - start
                if elapsed > timeout:
                    proc.kill()
                    timed_out = True
                    break
                yield {"kind": "heartbeat", "elapsed_s": int(elapsed)}
                time.sleep(heartbeat_interval_s)

            stdout, stderr = proc.communicate()
            if timed_out:
                yield {
                    "kind": "error",
                    "error": f"build123d execution timed out after {timeout}s",
                }
                return
            if proc.returncode != 0:
                stderr_excerpt = stderr[-2000:] if stderr else "(no stderr)"
                yield {
                    "kind": "error",
                    "error": (
                        f"build123d execution failed (exit {proc.returncode}):\n"
                        f"{stderr_excerpt}"
                    ),
                }
                return

            step_bytes = out_step.read_bytes() if out_step.exists() else b""
            stl_bytes = out_stl.read_bytes() if out_stl.exists() else b""
            glb_bytes = out_glb.read_bytes() if out_glb.exists() else b""
            topo: dict[str, Any] = (
                json.loads(out_topo.read_text(encoding="utf-8"))
                if out_topo.exists()
                else {}
            )
            mesh_meta_path = out_stl.with_name("mesh_meta.json")
            if mesh_meta_path.exists():
                try:
                    topo["_mesh_meta"] = json.loads(mesh_meta_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            yield {
                "kind": "result",
                "step_bytes": step_bytes,
                "stl_bytes": stl_bytes,
                "glb_bytes": glb_bytes,
                "topo": topo,
            }
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass


# ── package write ──────────────────────────────────────────────────────────────

def _write_cad_artifacts(
    pkg_path: Path,
    step_bytes: bytes,
    stl_bytes: bytes,
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
    generated_code: str,
    glb_bytes: bytes | None = None,
) -> None:
    artifacts: dict[str, bytes] = {
        "geometry/generated.step": step_bytes,
        "geometry/preview.stl": stl_bytes,
        "geometry/topology_map.json": json.dumps(topology_map, indent=2).encode(),
        "graph/feature_graph.json": json.dumps(feature_graph, indent=2).encode(),
        "geometry/source.py": generated_code.encode(),
    }
    if glb_bytes:
        artifacts["geometry/preview.glb"] = glb_bytes

    # Regenerate the symbolic B-Rep graph from the FRESH topology. Without this,
    # the zip-rewrite below copies a previously-persisted graph/brep_graph.json
    # forward unchanged (it isn't in `artifacts`), so after an incremental edit
    # the viewer's pick/highlight reads a stale, partial face list (e.g. only the
    # parts that existed at the first explicit build). Primitives for the newly
    # added parts then have no matching face and fall back to the nearest stale
    # face — selecting a face on the wrong part. Rebuilding here keeps the graph
    # consistent with the geometry on every execute/edit/replace/remove. If the
    # rebuild fails, DROP the stale artifacts so the serving path rebuilds them
    # on demand from topology instead of trusting an outdated file.
    drop: set[str] = set()
    try:
        from .brep_graph import (
            BREP_DIGEST_MEMBER,
            BREP_GRAPH_MEMBER,
            ENTITY_INDEX_MEMBER,
            build_brep_graph_from_topology,
        )

        _bg = build_brep_graph_from_topology(topology_map, feature_graph=feature_graph)
        artifacts[BREP_GRAPH_MEMBER] = json.dumps(_bg["brep_graph"], indent=2, ensure_ascii=False).encode()
        artifacts[ENTITY_INDEX_MEMBER] = json.dumps(_bg["entity_index"], indent=2, ensure_ascii=False).encode()
        artifacts[BREP_DIGEST_MEMBER] = _bg["digest"].encode("utf-8")
    except Exception as _bg_err:  # noqa: BLE001
        print(f"[cad] brep_graph regen failed, invalidating stale copy: {_bg_err}", file=sys.stderr)
        drop = {"graph/brep_graph.json", "graph/entity_index.json", "ai/brep_digest.md"}

    pkg_path.parent.mkdir(parents=True, exist_ok=True)

    if pkg_path.exists():
        tmp = pkg_path.with_suffix(".tmp.aieng")
        try:
            with (
                zipfile.ZipFile(pkg_path, "r") as src,
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
            ):
                for item in src.infolist():
                    if item.filename not in artifacts and item.filename not in drop:
                        dst.writestr(item, src.read(item.filename))
                for name, data in artifacts.items():
                    dst.writestr(name, data)
            tmp.replace(pkg_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    else:
        with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
            for name, data in artifacts.items():
                zf.writestr(name, data)


# Project names default to a UI placeholder ("STEP workbench project"); without
# auto-naming, list_projects shows a wall of identical rows (the discoverability
# pain). Agent builds derive a recognizable name from their part labels instead.
_PLACEHOLDER_PROJECT_NAMES = {"", "untitled project", "step workbench project"}


def _is_placeholder_project_name(name: Any) -> bool:
    return str(name or "").strip().lower() in _PLACEHOLDER_PROJECT_NAMES


def _derive_project_name(named_parts: list[str], limit: int = 3) -> str | None:
    """Derive a human-recognizable name from part labels.

    Groups by the token before the first underscore — parts in an assembly share a
    prefix (``optimus_torso`` / ``bee_torso`` -> "Optimus + Bee"); labels without
    an underscore are used whole. Returns None when nothing usable is present.
    """
    parts = [str(p) for p in (named_parts or []) if str(p).strip()]
    if not parts:
        return None
    prefixes: list[str] = []
    for p in parts:
        token = p.split("_", 1)[0].strip()
        if token and token not in prefixes:
            prefixes.append(token)
    # Clean assembly case: a few shared prefixes (optimus_*/bee_* -> "Optimus + Bee").
    # When labels are flat with no shared scheme, prefix-joining is noisy, so fall
    # back to a plain count — agents should pass an explicit `name` for these.
    if 1 <= len(prefixes) <= limit:
        return " + ".join(t[:1].upper() + t[1:] for t in prefixes)
    return f"{len(parts)}-part model"


def _named_parts_from_package(pkg_path: Path) -> list[str]:
    """Read named-part labels from a package's feature graph (fallback topology)."""
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = set(zf.namelist())
            if "graph/feature_graph.json" in names:
                parts = _named_parts_from_feature_graph(json.loads(zf.read("graph/feature_graph.json")))
                if parts:
                    return parts
            if "geometry/topology_map.json" in names:
                return _available_named_parts_from_topology(json.loads(zf.read("geometry/topology_map.json")))
    except Exception:
        pass
    return []


def _publish_preview_to_viewer(
    settings: Any,
    project_id: str,
    project: dict[str, Any],
    glb_bytes: bytes | None,
    stl_bytes: bytes | None,
) -> None:
    """Copy the freshly-built preview to ``viewer/model.{glb,stl}`` and point the
    project's ``web_asset`` at it.

    The frontend's primary viewer URL (``projectViewerUrl``) resolves to
    ``/assets/projects/{id}/{web_asset}`` — so without a populated ``web_asset``
    an agent-built model never appears in the UI viewer even though the package
    holds a valid preview. Mirrors the ``aieng.generate_preview`` publish step so
    every agent build (execute / edit / replace / remove) shows up immediately.
    Best-effort: never raises into the build.
    """
    try:
        from .main import project_dir as _project_dir, save_project as _save_project
        from .project_io import project_relpath as _project_relpath

        data, fmt = (glb_bytes, "glb") if glb_bytes else (stl_bytes, "stl")
        if not data:
            return
        viewer_root = _project_dir(settings, project_id) / "viewer"
        viewer_root.mkdir(parents=True, exist_ok=True)
        asset_path = viewer_root / f"model.{fmt}"
        asset_path.write_bytes(data)
        project["web_asset"] = _project_relpath(settings, project_id, asset_path)
        project["web_asset_format"] = fmt
        # Discoverability: stash the named parts on project metadata and auto-name
        # placeholder projects from their parts, so list_projects / part search are
        # meaningful. Best-effort — never blocks publishing the preview.
        try:
            from .project_io import resolve_project_path as _resolve_path
            pkg_path = _resolve_path(settings, project_id, project.get("aieng_file"))
            if pkg_path and pkg_path.exists():
                parts = _named_parts_from_package(pkg_path)
                if parts:
                    project["named_parts"] = parts
                    project["part_count"] = len(parts)
                    if _is_placeholder_project_name(project.get("name")):
                        derived = _derive_project_name(parts)
                        if derived:
                            project["name"] = derived
        except Exception:
            pass
        _save_project(settings, project)
        # Notify the live UI that a new preview is available.  This matches the
        # publish step in /api/agent/invoke-tool so that Autopilot-driven builds
        # (which bypass that endpoint and call runtime.invoke_tool directly) still
        # trigger the viewer refresh.
        try:
            from . import agent_activity

            preview_url = f"/api/projects/{project_id}/cad-preview"
            agent_activity.publish({
                "type": "project_changed",
                "project_id": project_id,
                "source": "cad_generation.preview_published",
                "status": "ok",
                "preview_url": preview_url,
                "preview_format": fmt,
            })
            agent_activity.publish({
                "type": "viewer_asset_changed",
                "project_id": project_id,
                "source": "cad_generation.preview_published",
                "preview_url": preview_url,
                "preview_format": fmt,
            })
        except Exception:
            pass
    except Exception:
        pass


def _clear_revalidation_status(pkg_path: Path) -> None:
    """Remove state/revalidation_status.json from the package.

    Called after a successful CAD build so that aieng.agent_context no longer
    shows stale EDIT IMPACT warnings that belonged to the previous geometry.
    Silently skips if the file is absent or the package can't be rewritten.
    """
    member = "state/revalidation_status.json"
    if not pkg_path.exists():
        return
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            if member not in zf.namelist():
                return
        tmp = pkg_path.with_suffix(".tmp.aieng")
        try:
            with (
                zipfile.ZipFile(pkg_path, "r") as src,
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
            ):
                for item in src.infolist():
                    if item.filename != member:
                        dst.writestr(item, src.read(item.filename))
            tmp.replace(pkg_path)
        except Exception:
            tmp.unlink(missing_ok=True)
    except Exception:
        pass


def _build_executed_object_registry(
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
) -> dict[str, Any]:
    """Object registry indexed against REAL executed topology/feature entities.

    The Shape IR converter emits a registry keyed by its projected slug ids
    (``body_<slug>`` / ``feat_<slug>``). Once the generated source is executed
    those ids no longer exist (the real extractor uses ``body_001`` / ``feat_*``),
    so the projected registry dangles. This rebuilds it from the executed
    artifacts.
    """
    fmt = str(topology_map.get("format_version") or "0.1")
    objects: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for entity in topology_map.get("entities", []) or []:
        eid = entity.get("id")
        if not eid:
            continue
        objects.append({
            "id": eid,
            "kind": "topology_entity",
            "type": str(entity.get("type", "")),
            "name": str(entity.get("name") or eid),
            "defined_in": "geometry/topology_map.json",
            "referenced_by": ["geometry/topology_map.json", "graph/feature_graph.json"],
            "roles": ["executed_geometry"],
            "status": "compiled_and_executed",
        })
    for feature in feature_graph.get("features", []) or []:
        fid = feature.get("id")
        if not fid:
            continue
        objects.append({
            "id": fid,
            "kind": "feature",
            "type": str(feature.get("type", "")),
            "name": str(feature.get("name") or fid),
            "defined_in": "graph/feature_graph.json",
            "referenced_by": ["graph/feature_graph.json"],
            "roles": ["executed_feature"],
            "status": "compiled_and_executed",
        })
        refs = feature.get("geometry_refs") or {}
        for entity_id in (refs.get("entities") or refs.get("faces") or []):
            relationships.append({
                "from": fid,
                "to": entity_id,
                "type": "references_topology",
                "source_file": "graph/feature_graph.json",
            })
    return {
        "format": "aieng.object_registry",
        "format_version": fmt,
        "source_files": ["geometry/source.py", "geometry/topology_map.json", "graph/feature_graph.json"],
        "objects": objects,
        "relationships": relationships,
        "notes": [
            "Rebuilt from executed build123d geometry after Shape IR compilation.",
            "Supersedes the converter's projected (pre-execution) registry.",
        ],
    }


# Canonical mapping representation -> representation_kind (mirrors
# shape_ir_verification._REPR_KIND so the manifest agrees with verification).
_REPRESENTATION_KIND = {
    "brep_build123d": "brep",
    "nurbs_brep": "nurbs_brep",
    "manifold_mesh": "mesh",
    "implicit_sdf": "implicit_field",
}
# Geometry artifacts a compile/recompile may produce (manifest lists those present).
_GEOMETRY_ARTIFACTS = (
    "geometry/source.py",
    "geometry/manifold_source.py",
    "geometry/sdf_source.py",
    "geometry/generated.step",
    "geometry/preview.glb",
    "geometry/preview.stl",
    "geometry/topology_map.json",
    "geometry/mesh_topology_map.json",
)
# Real-geometry artifacts: at least one must exist for executed:true to be honest.
_REAL_GEOMETRY_ARTIFACTS = ("geometry/generated.step", "geometry/preview.glb", "geometry/preview.stl")


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_geometry_execution_record(
    names: set[str],
    shape_ir: dict[str, Any] | None,
    topology_map: dict[str, Any] | list | None,
    *,
    representation: str,
    requested_runtime: str,
    actual_runtime: str,
    executed: bool,
    geometry_kind: str,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    executed_at: str | None = None,
) -> dict[str, Any]:
    """Build the normalized ``geometry_execution`` record — the backend source of
    truth for what geometry was generated, by which runtime/representation, and
    which artifacts exist. Honesty guards: ``executed`` is only true when a real
    geometry artifact is present, and ``geometry_kind`` is forced to ``none`` when
    not executed (never report mesh/brep without geometry)."""
    repr_kind = _REPRESENTATION_KIND.get(str(representation), "unknown")
    artifacts = [a for a in _GEOMETRY_ARTIFACTS if a in names]
    has_real = any(a in names for a in _REAL_GEOMETRY_ARTIFACTS)
    executed = bool(executed and has_real)
    gk = str(geometry_kind) if executed else "none"

    nodes = []
    if isinstance(shape_ir, dict):
        nodes = shape_ir.get("parts") or shape_ir.get("components") or []
    node_ids = [str(n.get("id") or n.get("name")) for n in nodes if isinstance(n, dict) and (n.get("id") or n.get("name"))]
    ents = []
    if isinstance(topology_map, dict):
        ents = topology_map.get("entities") or []
    elif isinstance(topology_map, list):
        ents = topology_map
    mapped = sorted({str(e.get("source_ir_node")) for e in ents
                     if isinstance(e, dict) and e.get("source_ir_node")})

    return {
        "executed": executed,
        "requested_runtime": str(requested_runtime),
        "actual_runtime": str(actual_runtime),
        "backend": str(actual_runtime),          # back-compat: verification reads .backend
        "representation": str(representation),    # back-compat
        "representation_kind": repr_kind,         # brep | nurbs_brep | mesh | implicit_field | unknown
        "geometry_kind": gk,                      # brep | mesh | none
        "real_geometry": executed,
        "source_shape_ir": "geometry/shape_ir.json",
        "source_ir_node_coverage": {
            "mapped": len(mapped), "total": len(node_ids),
            "mapped_node_ids": mapped, "node_ids": node_ids,
        },
        "artifacts": artifacts,
        "fallback": {"used": bool(fallback_used), "reason": fallback_reason},
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "executed_at_utc": executed_at or _utc_now_iso(),
    }


def write_geometry_execution_manifest(
    pkg_path: Path,
    *,
    representation: str,
    requested_runtime: str,
    actual_runtime: str,
    executed: bool,
    geometry_kind: str,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> None:
    """Create-or-update ``provenance/conversion_manifest.json`` with a normalized
    ``geometry_execution`` record (reads shape_ir + topology from the package for
    coverage/artifacts). Used by the failure/skip paths and any recompile that did
    not go through ``reconcile_shape_ir_provenance``. Best-effort; never raises."""
    if not Path(pkg_path).exists():
        return
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = set(zf.namelist())
            shape_ir = {}
            topo: dict[str, Any] | list = {}
            if "geometry/shape_ir.json" in names:
                try:
                    shape_ir = json.loads(zf.read("geometry/shape_ir.json"))
                except Exception:
                    shape_ir = {}
            for tm in ("geometry/topology_map.json", "geometry/mesh_topology_map.json"):
                if tm in names:
                    try:
                        topo = json.loads(zf.read(tm))
                        break
                    except Exception:
                        pass
            manifest: dict[str, Any] = {}
            if "provenance/conversion_manifest.json" in names:
                try:
                    manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
                except Exception:
                    manifest = {}
        if not isinstance(manifest, dict):
            manifest = {}
        manifest.setdefault("format", "aieng.conversion_manifest")
        manifest.setdefault("converter", "shape_ir_recompile")
        manifest["geometry_execution"] = build_geometry_execution_record(
            names, shape_ir, topo, representation=representation,
            requested_runtime=requested_runtime, actual_runtime=actual_runtime,
            executed=executed, geometry_kind=geometry_kind, fallback_used=fallback_used,
            fallback_reason=fallback_reason, warnings=warnings, errors=errors)
        _replace_member(pkg_path, "provenance/conversion_manifest.json",
                        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    except Exception as exc:  # noqa: BLE001 - manifest write is best-effort
        print(f"[shape_ir] geometry_execution manifest write failed: {exc}", file=sys.stderr)


def reconcile_shape_ir_provenance(
    pkg_path: Path,
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
    *,
    executed_at: str | None = None,
    representation: str = "brep_build123d",
    backend: str = "build123d",
    geometry_kind: str = "brep",
    requested_runtime: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> None:
    """Reconcile a Shape-IR package's provenance after its source was executed.

    Executing the converter-generated ``source.py`` overwrites topology_map.json /
    feature_graph.json with REAL build123d geometry, but the converter's
    ``objects/object_registry.json`` and ``provenance/conversion_manifest.json``
    still describe the PROJECTED (pre-execution) entities — leaving dangling ids
    and a manifest that claims geometry is projected-only. This:

      1. rebuilds the object registry against the executed entities, and
      2. stamps the conversion manifest with a ``geometry_execution`` record so
         the package honestly reflects that real geometry now exists.

    Best-effort and idempotent-ish: skips silently if the package or members are
    absent, never raises into the caller.
    """
    if not pkg_path.exists():
        return
    if executed_at is None:
        executed_at = _utc_now_iso()
    try:
        registry = _build_executed_object_registry(topology_map, feature_graph)
        replacements: dict[str, bytes] = {
            "objects/object_registry.json": (json.dumps(registry, indent=2, sort_keys=True) + "\n").encode(),
        }
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = set(zf.namelist())
            shape_ir: dict[str, Any] = {}
            if "geometry/shape_ir.json" in names:
                try:
                    shape_ir = json.loads(zf.read("geometry/shape_ir.json"))
                except Exception:
                    shape_ir = {}
            manifest: dict[str, Any] = {}
            if "provenance/conversion_manifest.json" in names:
                try:
                    manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
                except Exception:
                    manifest = {}
        # Create-or-update the conversion manifest with the normalized
        # geometry_execution record (the source of truth verification/registry read).
        if not isinstance(manifest, dict):
            manifest = {}
        manifest.setdefault("format", "aieng.conversion_manifest")
        manifest.setdefault("converter", "shape_ir_recompile")
        manifest["geometry_execution"] = build_geometry_execution_record(
            names, shape_ir, topology_map, representation=representation,
            requested_runtime=requested_runtime or backend, actual_runtime=backend,
            executed=True, geometry_kind=geometry_kind, fallback_used=fallback_used,
            fallback_reason=fallback_reason, warnings=warnings, errors=errors,
            executed_at=executed_at)
        replacements["provenance/conversion_manifest.json"] = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode()
        tmp = pkg_path.with_suffix(".tmp.aieng")
        try:
            with (
                zipfile.ZipFile(pkg_path, "r") as src,
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
            ):
                for item in src.infolist():
                    if item.filename not in replacements:
                        dst.writestr(item, src.read(item.filename))
                for name, data in replacements.items():
                    dst.writestr(name, data)
            tmp.replace(pkg_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    except Exception as exc:  # noqa: BLE001 - provenance reconcile is best-effort
        print(f"[shape_ir] provenance reconcile failed: {exc}", file=sys.stderr)


# ── implicit SDF runner (Shape IR representation: implicit_sdf) ──────────────
# Executes fogleman/sdf source (binds `f`), meshes via marching cubes, exports
# STL + GLB, and projects a region-level mesh topology. Runs in the backend's
# interpreter (aieng311, where `sdf` + scikit-image are installed); under any
# interpreter without `sdf` the subprocess fails and the caller reports honestly.
_SDF_RUNNER_TEMPLATE = r'''
import sys, json

out_stl = sys.argv[1]
out_glb = sys.argv[2]
out_topo = sys.argv[3]
samples = int(sys.argv[4]) if len(sys.argv) > 4 else 2 ** 18

# --- user SDF source (must bind `f`) ---
__AIENG_SDF_CODE__
# --- end user source ---

if "f" not in globals() or globals()["f"] is None:
    raise RuntimeError("SDF source must bind a variable named `f`")

f.save(out_stl, samples=samples)

import trimesh
mesh = trimesh.load(out_stl, file_type="stl", force="mesh")
mesh.export(out_glb, file_type="glb")

b = mesh.bounds
bbox = [float(b[0][0]), float(b[0][1]), float(b[0][2]),
        float(b[1][0]), float(b[1][1]), float(b[1][2])]
body = {
    "id": "body_001", "type": "solid", "name": "sdf_body",
    "bounding_box": bbox, "area": float(mesh.area),
    "triangle_count": int(len(mesh.faces)), "face_ids": ["face_001"],
}
try:
    if mesh.is_volume:
        body["volume"] = float(mesh.volume)
except Exception:
    pass
topo = {
    "format_version": "0.1",
    "metadata": {
        "extractor": "SDFRunner", "extraction_backend": "sdf",
        "extraction_mode": "marching_cubes_mesh", "representation": "implicit_sdf",
        "real_step_parsing": False,
        "limitations": [
            "Mesh from SDF marching cubes; faces are region-level, not analytic B-Rep faces.",
            "Booleans fuse into one field, so individual Shape IR part identity is not preserved.",
        ],
    },
    "entities": [
        body,
        {"id": "face_001", "type": "face", "body_id": "body_001",
         "surface_type": "freeform", "freeform": True, "name": "sdf_surface",
         "bounding_box": bbox, "area": float(mesh.area)},
    ],
}
with open(out_topo, "w") as fh:
    json.dump(topo, fh, indent=2)
'''


def _execute_sdf_code(
    code: str, timeout: int = 120, samples: int = 2 ** 18,
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Run SDF source in a subprocess; return (stl_bytes, glb_bytes, topology_map).

    Raises RuntimeError on failure (including a missing `sdf` runtime, which
    surfaces as a non-zero exit) so the caller can report it honestly.
    """
    runner = _SDF_RUNNER_TEMPLATE.replace("__AIENG_SDF_CODE__", code)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        runner_path = tmp / "sdf_runner.py"
        runner_path.write_text(runner, encoding="utf-8")
        out_stl, out_glb, out_topo = tmp / "result.stl", tmp / "result.glb", tmp / "topology.json"
        try:
            proc = subprocess.run(
                [sys.executable, str(runner_path), str(out_stl), str(out_glb), str(out_topo), str(samples)],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"SDF execution timed out after {timeout}s") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"SDF execution failed (exit {proc.returncode}):\n{(proc.stderr or '(no stderr)')[-2000:]}"
            )
        stl_bytes = out_stl.read_bytes() if out_stl.exists() else b""
        glb_bytes = out_glb.read_bytes() if out_glb.exists() else b""
        topo: dict[str, Any] = json.loads(out_topo.read_text(encoding="utf-8")) if out_topo.exists() else {}
        return stl_bytes, glb_bytes, topo


def _mesh_feature_graph(topology_map: dict[str, Any]) -> dict[str, Any]:
    """Minimal feature graph for a mesh body (one named_part per solid).

    Backend-agnostic: representation/recognizer are read from the topology
    metadata the runner wrote (SDF or Manifold), so the same builder serves both.
    """
    meta = topology_map.get("metadata", {}) or {}
    representation = str(meta.get("representation") or "mesh")
    recognizer = str(meta.get("extractor") or "MeshRunner")
    features: list[dict[str, Any]] = []
    for entity in topology_map.get("entities", []) or []:
        if entity.get("type") != "solid":
            continue
        bid = entity["id"]
        features.append({
            "id": f"feat_{bid}",
            "type": "named_part",
            "name": entity.get("name") or bid,
            "geometry_refs": {
                "entities": [bid, *(entity.get("face_ids") or [])],
                "faces": list(entity.get("face_ids") or []),
            },
            "parameters": {},
            "intent": {"role": "mesh_body"},
            "recognition": {"method": representation, "confidence": "low"},
        })
    return {
        "format_version": "0.1",
        "features": features,
        "metadata": {
            "recognizer": recognizer,
            "representation": representation,
            "model_kind": "organic",
            "limitations": [
                "Single fused mesh body; individual Shape IR part identity is not preserved.",
            ],
        },
    }


def _write_mesh_artifacts(
    pkg_path: Path,
    stl_bytes: bytes,
    glb_bytes: bytes,
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
) -> None:
    """Write executed mesh artifacts into the package (no STEP / build123d
    source.py — mesh backends are mesh-only). Regenerates the brep graph from the
    mesh topology so face pick/highlight still resolves (region-level). Shared by
    the SDF and Manifold runners."""
    artifacts: dict[str, bytes] = {
        "geometry/preview.stl": stl_bytes,
        "geometry/topology_map.json": json.dumps(topology_map, indent=2).encode(),
        "graph/feature_graph.json": json.dumps(feature_graph, indent=2).encode(),
    }
    if glb_bytes:
        artifacts["geometry/preview.glb"] = glb_bytes
    try:
        from .brep_graph import (
            BREP_DIGEST_MEMBER,
            BREP_GRAPH_MEMBER,
            ENTITY_INDEX_MEMBER,
            build_brep_graph_from_topology,
        )
        _bg = build_brep_graph_from_topology(topology_map, feature_graph=feature_graph)
        artifacts[BREP_GRAPH_MEMBER] = json.dumps(_bg["brep_graph"], indent=2, ensure_ascii=False).encode()
        artifacts[ENTITY_INDEX_MEMBER] = json.dumps(_bg["entity_index"], indent=2, ensure_ascii=False).encode()
        artifacts[BREP_DIGEST_MEMBER] = _bg["digest"].encode("utf-8")
    except Exception as _bg_err:  # noqa: BLE001
        print(f"[sdf] brep_graph regen failed: {_bg_err}", file=sys.stderr)

    if not pkg_path.exists():
        return
    tmp = pkg_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(pkg_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in artifacts:
                    dst.writestr(item, src.read(item.filename))
            for name, data in artifacts.items():
                dst.writestr(name, data)
        tmp.replace(pkg_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── manifold mesh runner (Shape IR representation: manifold_mesh) ────────────
# Executes manifold3d source (binds `result`), converts the manifold to a
# trimesh, exports STL + GLB, and projects a region-level mesh topology. Runs in
# the backend interpreter (aieng311, where `manifold3d` + trimesh are installed).
_MANIFOLD_RUNNER_TEMPLATE = r'''
import sys, json

out_stl = sys.argv[1]
out_glb = sys.argv[2]
out_topo = sys.argv[3]

# --- user manifold source (must bind `result`) ---
__AIENG_MANIFOLD_CODE__
# --- end user source ---

if "result" not in globals() or globals()["result"] is None:
    raise RuntimeError("manifold source must bind a variable named `result`")

import numpy as np
import trimesh
mesh = result.to_mesh()
verts = np.asarray(mesh.vert_properties)[:, :3]
faces = np.asarray(mesh.tri_verts).reshape(-1, 3)
tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
tm.export(out_stl)
tm.export(out_glb)

b = tm.bounds
bbox = [float(b[0][0]), float(b[0][1]), float(b[0][2]),
        float(b[1][0]), float(b[1][1]), float(b[1][2])]
body = {
    "id": "body_001", "type": "solid", "name": "manifold_body",
    "bounding_box": bbox, "area": float(tm.area),
    "triangle_count": int(len(tm.faces)), "face_ids": ["face_001"],
}
try:
    if tm.is_volume:
        body["volume"] = float(tm.volume)
except Exception:
    pass
topo = {
    "format_version": "0.1",
    "metadata": {
        "extractor": "ManifoldRunner", "extraction_backend": "manifold",
        "extraction_mode": "manifold_csg_mesh", "representation": "manifold_mesh",
        "real_step_parsing": False,
        "limitations": [
            "Mesh from manifold3d CSG; faces are region-level, not analytic B-Rep faces.",
            "Booleans fuse into one solid, so individual Shape IR part identity is not preserved.",
        ],
    },
    "entities": [
        body,
        {"id": "face_001", "type": "face", "body_id": "body_001",
         "surface_type": "mesh_region", "freeform": True, "name": "manifold_surface",
         "bounding_box": bbox, "area": float(tm.area)},
    ],
}
with open(out_topo, "w") as fh:
    json.dump(topo, fh, indent=2)
'''


def _execute_manifold_code(
    code: str, timeout: int = 120,
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Run manifold3d source in a subprocess; return (stl_bytes, glb_bytes, topology_map).

    Raises RuntimeError on failure (including a missing `manifold3d` runtime).
    """
    runner = _MANIFOLD_RUNNER_TEMPLATE.replace("__AIENG_MANIFOLD_CODE__", code)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        runner_path = tmp / "manifold_runner.py"
        runner_path.write_text(runner, encoding="utf-8")
        out_stl, out_glb, out_topo = tmp / "result.stl", tmp / "result.glb", tmp / "topology.json"
        try:
            proc = subprocess.run(
                [sys.executable, str(runner_path), str(out_stl), str(out_glb), str(out_topo)],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Manifold execution timed out after {timeout}s") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"Manifold execution failed (exit {proc.returncode}):\n{(proc.stderr or '(no stderr)')[-2000:]}"
            )
        stl_bytes = out_stl.read_bytes() if out_stl.exists() else b""
        glb_bytes = out_glb.read_bytes() if out_glb.exists() else b""
        topo: dict[str, Any] = json.loads(out_topo.read_text(encoding="utf-8")) if out_topo.exists() else {}
        return stl_bytes, glb_bytes, topo


def _replace_member(pkg_path: Path, name: str, data: bytes) -> None:
    """Atomically write/replace a single member in a .aieng zip."""
    if not pkg_path.exists():
        return
    tmp = pkg_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(pkg_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != name:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(name, data)
        tmp.replace(pkg_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def recompile_shape_ir_package(package_path: Path, *, timeout: int = 120, use_cache: bool = True) -> dict[str, Any]:
    """Recompile + re-execute a package whose geometry/shape_ir.json changed.

    Routes by the representation's runtime (build123d / sdf / manifold), writes
    the compiled source + regenerated artifacts, reconciles provenance, and
    refreshes shape_ir_verification + object_registry. Returns a summary. Reused
    by the Shape IR patch apply path so an edit re-runs the full pipeline.

    Args:
        package_path: Path to the .aieng package file.
        timeout: Subprocess timeout in seconds.
        use_cache: When ``True`` (default), check the ``GeometryCache`` before
            recompiling. Cache hits skip compilation and return the cached summary.
    """
    from aieng.converters.shape_ir import compile_shape_ir
    from aieng.converters.shape_ir_object_registry import write_shape_ir_object_registry
    from aieng.converters.shape_ir_verification import write_shape_ir_verification

    package_path = Path(package_path)
    with zipfile.ZipFile(package_path, "r") as zf:
        payload = json.loads(zf.read("geometry/shape_ir.json").decode("utf-8"))

    # ── GeometryCache integration ───────────────────────────────────────────
    if use_cache:
        try:
            from aieng.cache.geometry_cache import GeometryCache, compute_shape_ir_hash
            from aieng.cache.metrics import get_default_metrics

            cache = GeometryCache()
            metrics = get_default_metrics()
            h = compute_shape_ir_hash(payload)
            cached = cache.get(h)
            if cached is not None and _cached_geometry_has_real_artifacts(cached):
                metrics.record_hit()
                # Re-write cached artifacts into the package so the package stays consistent
                _write_cached_artifacts_to_package(package_path, cached)
                representation = str(cached.metadata.get("representation", "brep_build123d"))
                runtime = str(cached.metadata.get("runtime", "build123d"))
                geometry_kind = str(cached.metadata.get("geometry_kind", "brep"))
                topo = cached.topology_map or cached.metadata.get("topology_map")
                feature_graph = cached.feature_graph or cached.metadata.get("feature_graph")
                if isinstance(topo, dict) and isinstance(feature_graph, dict):
                    reconcile_shape_ir_provenance(
                        package_path,
                        topo,
                        feature_graph,
                        representation=representation,
                        backend=runtime,
                        geometry_kind=geometry_kind,
                        requested_runtime=runtime,
                    )
                else:
                    # Older cache entries may not carry semantic maps. Still
                    # restore an honest normalized execution record from the
                    # binary artifacts that were written back into the package.
                    write_geometry_execution_manifest(
                        package_path,
                        representation=representation,
                        requested_runtime=runtime,
                        actual_runtime=runtime,
                        executed=True,
                        geometry_kind=geometry_kind,
                    )
                for refresh in (write_shape_ir_verification, write_shape_ir_object_registry):
                    try:
                        refresh(package_path)
                    except Exception:  # noqa: BLE001 - cache restore remains best-effort
                        pass
                return {
                    "representation": representation,
                    "runtime": runtime,
                    "executed": True,
                    "geometry_kind": geometry_kind,
                    "cached": True,
                    "cache_hit": True,
                    "source_path": cached.metadata.get("source_path", "geometry/source.py"),
                }
            metrics.record_miss()
        except Exception:
            # Cache failure is non-fatal; fall through to normal compilation
            pass

    compiled = compile_shape_ir(payload, use_cache=use_cache)
    representation, runtime, source = compiled["representation"], compiled["runtime"], compiled["source"]
    _replace_member(package_path, compiled["source_path"], source.encode())

    # The compiler may fall back to build123d for an unknown/failed representation.
    fallback_used = bool(compiled.get("fallback"))
    fallback_reason = (f"requested representation '{payload.get('representation')}' fell back to "
                       f"{representation}") if fallback_used else None
    summary: dict[str, Any] = {"representation": representation, "runtime": runtime, "executed": False}
    try:
        if runtime == "build123d":
            step, stl, glb, topo = _execute_build123d_code(source, timeout=timeout)
            if isinstance(topo, dict):
                topo.pop("_mesh_meta", None)
            fg = _topology_to_feature_graph(topo, source_code=source, model_kind=str(payload.get("model_kind") or "auto"))
            _write_cad_artifacts(package_path, step_bytes=step, stl_bytes=stl, topology_map=topo,
                                 feature_graph=fg, generated_code=source, glb_bytes=glb)
            # ── Write to GeometryCache ──────────────────────────────────────────
            if use_cache:
                try:
                    from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
                    from aieng.cache.metrics import get_default_metrics

                    cache = GeometryCache()
                    metrics = get_default_metrics()
                    h = compute_shape_ir_hash(payload)
                    cg = CachedGeometry(
                        shape_ir_hash=h,
                        metadata={
                            "representation": representation,
                            "runtime": runtime,
                            "source": source,
                            "source_path": compiled["source_path"],
                            "geometry_kind": "brep",
                            "step_bytes": step,
                            "stl_bytes": stl,
                            "glb_bytes": glb,
                            "topology_map": topo,
                            "feature_graph": fg,
                        },
                    )
                    cg.topology_map = topo
                    cg.feature_graph = fg
                    cache.set(h, cg)
                    metrics.record_set()
                except Exception:
                    pass
            reconcile_shape_ir_provenance(package_path, topo, fg, representation=representation,
                                          backend="build123d", geometry_kind="brep",
                                          requested_runtime=runtime, fallback_used=fallback_used,
                                          fallback_reason=fallback_reason)
            summary.update(executed=True, geometry_kind="brep")
        elif runtime in ("sdf", "manifold"):
            runner = _execute_sdf_code if runtime == "sdf" else _execute_manifold_code
            stl, glb, topo = runner(source, timeout=timeout)
            fg = _mesh_feature_graph(topo)
            _write_mesh_artifacts(package_path, stl, glb, topo, fg)
            # ── Write to GeometryCache ──────────────────────────────────────────
            if use_cache:
                try:
                    from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
                    from aieng.cache.metrics import get_default_metrics

                    cache = GeometryCache()
                    metrics = get_default_metrics()
                    h = compute_shape_ir_hash(payload)
                    cg = CachedGeometry(
                        shape_ir_hash=h,
                        metadata={
                            "representation": representation,
                            "runtime": runtime,
                            "source": source,
                            "source_path": compiled["source_path"],
                            "geometry_kind": "mesh",
                            "stl_bytes": stl,
                            "glb_bytes": glb,
                            "topology_map": topo,
                            "feature_graph": fg,
                        },
                    )
                    cg.topology_map = topo
                    cg.feature_graph = fg
                    cache.set(h, cg)
                    metrics.record_set()
                except Exception:
                    pass
            reconcile_shape_ir_provenance(package_path, topo, fg, representation=representation,
                                          backend=runtime, geometry_kind="mesh",
                                          requested_runtime=runtime, fallback_used=fallback_used,
                                          fallback_reason=fallback_reason)
            summary.update(executed=True, geometry_kind="mesh")
            # Mesh outputs get a solver-neutral region graph + analytic plane fits for
            # planar_candidate regions (observational mesh analysis; not B-Rep).
            try:
                from aieng.converters.mesh_region_segmentation import write_mesh_region_graph
                rg = write_mesh_region_graph(package_path)
                summary["mesh_region_count"] = len(rg.get("regions") or [])
                from aieng.converters.mesh_surface_fitting import write_mesh_surface_fit
                sf = write_mesh_surface_fit(package_path)
                summary["mesh_plane_fit_count"] = len(sf.get("surfaces") or [])
                # Freeform/NURBS surface fitting evidence v0 (evidence-only; no B-Rep/STEP).
                from aieng.converters.mesh_freeform_surface_fitting import write_freeform_surface_fit
                ff = write_freeform_surface_fit(package_path)
                summary["mesh_freeform_fit_count"] = len(ff.get("surfaces") or [])
                # Freeform readiness scoring v0 (advisory; does NOT generate B-Rep faces/STEP).
                from aieng.converters.mesh_freeform_surface_readiness import write_freeform_readiness
                fr = write_freeform_readiness(package_path)
                summary["mesh_freeform_readiness"] = fr.get("status")
                # Freeform B-Rep FACE candidate generation v0 (candidate-only; no stitch/solid/STEP).
                from aieng.converters.mesh_freeform_brep_face_generation import write_freeform_brep_faces
                fbf = write_freeform_brep_faces(package_path)
                summary["mesh_freeform_face_candidate_count"] = (fbf.get("summary") or {}).get("generated_face_count", 0)
                # Freeform face TRIMMING readiness v0 (diagnostic-only; no trimming/stitch/STEP).
                from aieng.converters.mesh_freeform_face_trimming_readiness import write_freeform_trimming_readiness
                ftr = write_freeform_trimming_readiness(package_path)
                summary["mesh_freeform_trimming_readiness"] = ftr.get("status")
                from aieng.converters.mesh_reconstruction_readiness import write_mesh_reconstruction_readiness
                rr = write_mesh_reconstruction_readiness(package_path)
                summary["reconstruction_next_action"] = (rr.get("readiness") or {}).get("recommended_next_action")
                # Partial B-Rep PLANNING: accepted fits -> face candidates (no stitching/solid/STEP).
                from aieng.converters.mesh_brep_reconstruction import write_partial_brep_plan
                bp = write_partial_brep_plan(package_path)
                summary["brep_face_candidate_count"] = (bp.get("summary") or {}).get("candidate_face_count", 0)
                # Generate + validate real OCC faces from the candidates (no stitch/solid/STEP).
                from aieng.converters.mesh_brep_face_generation import write_brep_faces
                gf = write_brep_faces(package_path)
                summary["brep_generated_face_count"] = (gf.get("summary") or {}).get("generated_face_count", 0)
                # Stitching readiness + edge matching (plan only; no sewing/shell/STEP).
                from aieng.converters.mesh_brep_stitching import write_brep_stitching_plan
                sp = write_brep_stitching_plan(package_path)
                summary["brep_matched_edge_pairs"] = (sp.get("summary") or {}).get("matched_edge_pair_count", 0)
                # Conservative mesh-to-CAD continuation: sew candidate faces, create/export
                # STEP only if OCC validates a closed solid, then roundtrip-verify.
                from aieng.converters.mesh_brep_solidification import reconstruct_brep_step
                br = reconstruct_brep_step(package_path)
                summary["brep_shell_type"] = ((br.get("sewing") or {}).get("summary") or {}).get("shell_type")
                summary["brep_step_exported"] = bool((br.get("step_export") or {}).get("step_exported"))
                summary["brep_roundtrip_status"] = (br.get("roundtrip_verification") or {}).get("status")
                # Mesh-to-CAD reconstruction STATUS AGGREGATOR v0 (diagnostic summary only).
                from aieng.converters.mesh_to_cad_reconstruction_status import write_mesh_to_cad_reconstruction_status
                rs = write_mesh_to_cad_reconstruction_status(package_path)
                summary["mesh_to_cad_status"] = rs.get("status")
                summary["mesh_to_cad_next_action"] = rs.get("recommended_next_action")
                # Mesh region SEGMENTATION QUALITY + re-segmentation hints v0 (advisory only).
                from aieng.converters.mesh_segmentation_quality import write_segmentation_quality
                sq, sh = write_segmentation_quality(package_path)
                summary["mesh_segmentation_quality"] = sq.get("status")
                summary["mesh_segmentation_quality_score"] = (sq.get("summary") or {}).get("overall_quality_score")
                summary["mesh_resegmentation_next_action"] = sh.get("recommended_next_action")
            except Exception:  # noqa: BLE001 - mesh analysis is best-effort
                pass
        else:
            summary["skipped"] = True
            # Honest record: representation emitted source but no runner is wired.
            write_geometry_execution_manifest(
                package_path, representation=representation, requested_runtime=runtime,
                actual_runtime=runtime, executed=False, geometry_kind="none",
                fallback_used=fallback_used, fallback_reason=fallback_reason,
                warnings=[f"runtime '{runtime}' is not wired; no executed geometry produced"])
    except Exception as exc:  # noqa: BLE001 - report, don't raise into the patch flow
        summary["error"] = f"{type(exc).__name__}: {exc}"
        # Honest record: execution failed, so no real geometry exists.
        write_geometry_execution_manifest(
            package_path, representation=representation, requested_runtime=runtime,
            actual_runtime=runtime, executed=False, geometry_kind="none",
            fallback_used=fallback_used, fallback_reason=fallback_reason,
            errors=[summary["error"]])
    # Refresh diagnostics from the (re)generated package regardless of outcome.
    for refresh in (write_shape_ir_verification, write_shape_ir_object_registry):
        try:
            refresh(package_path)
        except Exception:  # noqa: BLE001
            pass
    # Optional Assembly IR v0: if the package carries assembly/assembly_ir.json, refresh its
    # registry / connection graph / validation / CAE draft. Gated on presence — single-part
    # packages are untouched. Best-effort; never raises, never runs a solver.
    try:
        from aieng.converters.assembly_ir import process_assembly_package
        asm = process_assembly_package(package_path)
        if asm.get("assembly_present"):
            summary["assembly_validation_status"] = asm.get("validation_status")
            summary["assembly_part_count"] = asm.get("part_count")
            # Resolve interfaces against part topology + validate connection geometry.
            from aieng.converters.assembly_interface_resolution import (
                resolve_and_validate_assembly_geometry,
            )
            geo = resolve_and_validate_assembly_geometry(package_path)
            if geo.get("assembly_present"):
                summary["assembly_geometry_summary"] = geo.get("geometry_summary")
                summary["assembly_cae_model_status"] = geo.get("assembly_cae_model_status")
                summary["assembly_solver_deck_status"] = geo.get("solver_deck_status")
                summary["assembly_solver_execution_status"] = geo.get("solver_execution_status")
                summary["assembly_result_mapping_status"] = geo.get("assembly_result_mapping_status")
    except Exception:  # noqa: BLE001 - assembly processing is best-effort
        pass
    # Optional design study v0: if the package carries analysis/design_study_problem.json,
    # validate the problem + any candidate patches (contract + validation ONLY — never applies a
    # patch, never recompiles geometry, never runs CAE). Gated on presence; best-effort.
    try:
        from aieng.converters.design_study import process_design_study_package
        ds = process_design_study_package(package_path)
        if ds.get("design_study_present"):
            summary["design_study_problem_status"] = ds.get("problem_status")
            summary["design_study_candidate_count"] = ds.get("candidate_count")
    except Exception:  # noqa: BLE001 - design-study processing is best-effort
        pass
    return summary


def make_candidate_recompiler(baseline_package_path: Path) -> Any:
    """Build a recompiler for design-study candidate execution that compiles a candidate's
    DERIVED Shape IR in a THROWAWAY copy of the baseline package — the baseline is never touched.

    The returned callable matches the contract expected by
    ``design_study_execution.execute_design_study_candidate``:
    ``(candidate_shape_ir: dict, context: dict) -> dict``.
    """
    baseline_package_path = Path(baseline_package_path)

    def _recompiler(candidate_shape_ir: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        sid = context.get("candidate_id", "candidate")
        tmp = baseline_package_path.with_suffix(f".dscand_{sid}.tmp.aieng")
        try:
            # throwaway copy with geometry/shape_ir.json swapped for the candidate's derived IR
            with (
                zipfile.ZipFile(baseline_package_path, "r") as src,
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
            ):
                for item in src.infolist():
                    if item.filename != "geometry/shape_ir.json":
                        dst.writestr(item, src.read(item.filename))
                dst.writestr("geometry/shape_ir.json",
                             json.dumps(candidate_shape_ir).encode())
            summary = recompile_shape_ir_package(tmp)
            ge, verification, metrics = {}, None, {}
            with zipfile.ZipFile(tmp, "r") as zf:
                names = set(zf.namelist())
                if "provenance/conversion_manifest.json" in names:
                    ge = (json.loads(zf.read("provenance/conversion_manifest.json"))
                          .get("geometry_execution") or {})
                if "diagnostics/shape_ir_verification.json" in names:
                    verification = json.loads(zf.read("diagnostics/shape_ir_verification.json"))
            executed = bool(ge.get("executed"))
            metrics = {"executed": executed, "geometry_kind": ge.get("geometry_kind"),
                       "representation_kind": ge.get("representation_kind"),
                       "artifacts": ge.get("artifacts")}
            return {
                "compile_status": "compile_succeeded" if executed else "compile_failed",
                "geometry_execution": ge or None,
                "verification": verification,
                "metrics": metrics,
                "errors": list(ge.get("errors") or []) + ([summary["error"]] if summary.get("error") else []),
                "warnings": list(ge.get("warnings") or []),
            }
        except Exception as exc:  # noqa: BLE001
            return {"compile_status": "compile_failed", "errors": [f"{type(exc).__name__}: {exc}"]}
        finally:
            tmp.unlink(missing_ok=True)

    return _recompiler


# ── backend class ─────────────────────────────────────────────────────────────

class Build123dBackend:
    def __init__(self, settings: Any) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "build123d"

    def can_generate(self) -> bool:
        try:
            import build123d  # noqa: F401
            return True
        except ImportError:
            return False

    def generate(
        self,
        description: str,
        hints: dict[str, Any] | None = None,
        timeout: int = 60,
        max_retries: int = 2,
        api_key: str | None = None,
        llm_config: dict[str, Any] | None = None,
    ) -> Any:
        """Non-streaming text-to-CAD with internal LLM-fix retry loop.

        The streaming endpoint (``run_cad_generation_stream``) implements the
        same retry strategy inline so it can yield SSE heartbeats during each
        subprocess. Both paths must stay behaviour-compatible.
        """
        ensure_aieng_on_path()
        from aieng.modeling.text_to_cad import TextToCadResult

        generated_code = call_claude_for_build123d_code(
            description=description,
            hints=hints,
            api_key=api_key,
            settings=self._settings,
            llm_config=llm_config,
        )

        warnings: list[str] = []
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                step_bytes, stl_bytes, glb_bytes, topo = _execute_build123d_code(
                    generated_code, timeout=timeout
                )
                feature_graph = _topology_to_feature_graph(topo, source_code=generated_code)
                face_count = sum(
                    1 for e in topo.get("entities", []) if e.get("type") == "face"
                )
                if attempt > 0:
                    warnings.append(
                        f"Auto-fixed after {attempt} retry(s). Last error: {last_error}"
                    )
                return TextToCadResult(
                    backend=self.name,
                    description=description,
                    generated_code=generated_code,
                    step_bytes=step_bytes,
                    stl_bytes=stl_bytes,
                    glb_bytes=glb_bytes or None,
                    topology_map=topo,
                    feature_graph=feature_graph,
                    warnings=warnings,
                    metadata={
                        "face_count": face_count,
                        "feature_count": len(feature_graph.get("features", [])),
                        "retries_used": attempt,
                    },
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < max_retries:
                    warnings.append(
                        f"Attempt {attempt + 1} failed: {last_error[:300]}... Asking LLM to fix."
                    )
                    generated_code = call_claude_for_build123d_refinement(
                        existing_code=generated_code,
                        feedback=(
                            f"The build123d code failed to execute with this error:\n\n"
                            f"{last_error}\n\n"
                            f"Please fix the code so it runs successfully. "
                            f"Pay special attention to fillet radii (use max_fillet() or smaller values), "
                            f"boolean operation order, and edge selection validity."
                        ),
                        api_key=api_key,
                        settings=self._settings,
                        llm_config=llm_config,
                    )
                else:
                    break

        return TextToCadResult(
            backend=self.name,
            description=description,
            generated_code=generated_code,
            step_bytes=None,
            stl_bytes=None,
            topology_map={},
            feature_graph={"features": []},
            warnings=warnings,
            metadata={"retries_used": max_retries},
            error=last_error,
        )


# ── orchestration ─────────────────────────────────────────────────────────────

def run_cad_generation(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate a 3D CAD model from a natural-language description.

    Writes geometry/generated.step, geometry/topology_map.json,
    graph/feature_graph.json, and geometry/source.py into the .aieng package.
    """
    from .project_io import get_project, resolve_project_path

    description = str(payload.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="description is required")

    hints: dict[str, Any] = payload.get("hints") or {}
    write_files = bool(payload.get("write_files", True))
    timeout = int(payload.get("timeout", 60))
    api_key = payload.get("api_key")
    llm_config = payload.get("llm_config") if isinstance(payload.get("llm_config"), dict) else None

    project = get_project(settings, project_id)

    backend = Build123dBackend(settings)
    if not backend.can_generate():
        raise HTTPException(
            status_code=503,
            detail="build123d is not installed — cannot generate CAD geometry",
        )

    result = backend.generate(
        description,
        hints=hints,
        timeout=timeout,
        api_key=api_key,
        llm_config=llm_config,
    )

    if result.error:
        raise HTTPException(status_code=422, detail=f"CAD generation failed: {result.error}")

    written: list[str] = []
    if write_files and result.step_bytes:
        existing_pkg = project.get("aieng_file")
        if existing_pkg:
            pkg_path = resolve_project_path(settings, project_id, existing_pkg)
        else:
            pkg_path = None

        if pkg_path is None:
            from .main import project_dir, save_project
            pkg_name = f"{project_id}.aieng"
            pkg_path = project_dir(settings, project_id) / pkg_name
            project["aieng_file"] = pkg_name
            save_project(settings, project)

        _write_cad_artifacts(
            pkg_path=pkg_path,
            step_bytes=result.step_bytes or b"",
            stl_bytes=result.stl_bytes or b"",
            topology_map=result.topology_map,
            feature_graph=result.feature_graph,
            generated_code=result.generated_code,
            glb_bytes=result.glb_bytes,
        )
        written = [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ]
        if result.glb_bytes:
            written.append("geometry/preview.glb")

    solid = next(
        (e for e in result.topology_map.get("entities", []) if e.get("type") == "solid"),
        None,
    )

    return {
        "schema_version": "0.1",
        "project_id": project_id,
        "description": description,
        "backend": result.backend,
        "generated_code": result.generated_code,
        "topology_summary": {
            "face_count": result.metadata.get("face_count", 0),
            "feature_count": result.metadata.get("feature_count", 0),
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": result.feature_graph,
        "written_artifacts": written,
        "write_files": write_files,
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if result.glb_bytes else "stl",
        "warnings": result.warnings,
    }


# ── caller-supplied code execution (no LLM) ──────────────────────────────────

def execute_build123d_code(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
    on_progress: "Callable[[dict[str, Any]], None] | None" = None,
) -> dict[str, Any]:
    """Execute caller-supplied build123d code — no LLM involved.

    This is the entry point an external agent (Claude Code, Codex, Copilot)
    uses to drive CAD modelling without our backend needing an API key: the
    agent writes the build123d source itself and we run it deterministically,
    writing geometry/source.py, generated.step, preview.stl/.glb,
    topology_map.json, and feature_graph.json into the .aieng package.

    Payload:
        code (str, required): the full build123d script. The script must build
            a result object exposing ``export_step`` / ``export_stl`` /
            ``export_gltf`` — i.e. the same contract the LLM-generated code
            obeys. The variable bound to the model must be named ``result``.
        write_files (bool, optional): write artifacts to the package (default true).
        timeout (int, optional): subprocess timeout in seconds (default 60).
        name (str, optional): a human-recognizable project name (e.g. "Optimus +
            Bumblebee"). When given it is set on the project; otherwise a
            placeholder-named project is auto-named from its part labels.

    Args:
        on_progress: optional callback invoked with progress dicts as the build
            runs — used by the live-UI bridge to stream build heartbeats to
            subscribers. Shapes:
              {"phase": "building", "elapsed_s": int}
              {"phase": "writing"}
            Never raises into the caller; exceptions in the callback are
            swallowed so a slow UI can't break the build.

    Returns a dict mirroring run_cad_generation()'s shape (topology_summary,
    feature_graph, preview_url, written_artifacts) plus ``status``.
    """
    from .project_io import get_project, resolve_project_path

    def _emit(evt: dict[str, Any]) -> None:
        if on_progress is None:
            return
        try:
            on_progress(evt)
        except Exception:
            pass

    code = str(payload.get("code") or "").strip()
    if not code:
        return {"status": "error", "code": "missing_code", "message": "code is required (build123d source)."}

    write_files = bool(payload.get("write_files", True))
    timeout = int(payload.get("timeout", 60))
    response_detail = _normalize_response_detail(payload.get("response_detail"))
    model_kind = str(payload.get("model_kind", "auto"))

    code = _coerce_code(code)
    contract_error = _check_code_contract(code)
    if contract_error:
        return {"status": "error", "code": "contract_violation", "message": contract_error}

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    backend = Build123dBackend(settings)
    if not backend.can_generate():
        return {
            "status": "error",
            "code": "build123d_unavailable",
            "message": "build123d is not installed in the backend Python — cannot execute CAD code.",
        }

    # Incremental modeling: in "append" mode, run the previously-stored source
    # first, expose its result as `previous_result`, then run the new code on top.
    # The combined script is what we store, so successive appends accumulate.
    mode = str(payload.get("mode") or "replace").lower()
    used_base = False
    prior_named_parts: list[str] = []
    storage_code = code  # what we persist in geometry/source.py
    execution_code = code  # what we actually run
    prior_step_path: str | None = None
    append_step_cache = bool(payload.get("append_step_cache", False))
    if mode == "append":
        existing_pkg = project.get("aieng_file")
        pkg = resolve_project_path(settings, project_id, existing_pkg) if existing_pkg else None
        prior_source: str | None = None
        prior_step_bytes: bytes | None = None
        if pkg is not None and pkg.exists():
            try:
                with zipfile.ZipFile(pkg, "r") as zf:
                    names = zf.namelist()
                    if "geometry/source.py" in names:
                        prior_source = zf.read("geometry/source.py").decode("utf-8")
                    if "graph/feature_graph.json" in names:
                        prior_fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                        prior_named_parts = _named_parts_from_feature_graph(prior_fg)
                    if "geometry/generated.step" in names:
                        prior_step_bytes = zf.read("geometry/generated.step")
            except Exception:
                prior_source = None
                prior_step_bytes = None
        if not prior_source:
            return {
                "status": "error",
                "code": "append_without_base",
                "message": (
                    "mode=append requires an existing model with geometry/source.py. "
                    "Run once with mode=replace (the default) first."
                ),
            }
        used_base = True
        storage_code = (
            prior_source
            + "\n\n# --- aieng append: previous step exposed as `previous_result` ---\n"
            + "previous_result = result.part if hasattr(result, 'part') else result\n"
            + "# --- new code (must reassign `result`) ---\n"
            + code
        )
        # Prefix-reuse optimization: import prior STEP instead of re-executing
        # the full accumulated script. Only when labels survive roundtrip.
        if append_step_cache and prior_step_bytes and _step_roundtrip_preserves_labels():
            try:
                import tempfile as _tmpf
                prior_step_path = _tmpf.NamedTemporaryFile(suffix=".step", delete=False).name
                Path(prior_step_path).write_bytes(prior_step_bytes)
                execution_code = (
                    "previous_result = _aieng_build123d.import_step("
                    + repr(prior_step_path)
                    + ")\n"
                    + "if hasattr(previous_result, 'part'):\n"
                    + "    previous_result = previous_result.part\n"
                    + "if isinstance(previous_result, (list, tuple)) or type(previous_result).__name__ == 'ShapeList':\n"
                    + "    _items = list(previous_result)\n"
                    + "    if len(_items) == 1:\n"
                    + "        previous_result = _items[0]\n"
                    + "    elif _items:\n"
                    + "        previous_result = Compound(children=_items)\n"
                    + "# --- aieng append: new code (must reassign `result`) ---\n"
                    + code
                )
            except Exception:
                execution_code = storage_code
                prior_step_path = None
        else:
            execution_code = storage_code

    if mode == "append" and execution_code != storage_code and prior_step_bytes is not None:
        # Custom cache key for prefix-reuse: stable across temp-file paths.
        prior_step_hash = hashlib.sha256(prior_step_bytes).hexdigest()
        new_code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        cache_key_material = {
            "cache_format_version": _BUILD123D_CACHE_FORMAT_VERSION,
            "executor": "build123d_streaming",
            "mode": mode,
            "model_kind": model_kind,
            "prior_step_sha256": prior_step_hash,
            "new_code_sha256": new_code_hash,
            "prefix_reuse": True,
            "versions": _build123d_cache_versions(),
        }
        encoded = json.dumps(cache_key_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        cache_key = hashlib.sha256(encoded).hexdigest()
    else:
        cache_key, cache_key_material = _build123d_cache_key(code=execution_code, mode=mode, model_kind=model_kind)

    cached = _read_build123d_cache(settings, cache_key)
    if cached is not None:
        try:
            return _finish_execute_build123d_response(
                settings=settings,
                project_id=project_id,
                project=project,
                payload=payload,
                code=storage_code,
                mode=mode,
                used_base=used_base,
                prior_named_parts=prior_named_parts,
                step_bytes=cached["step_bytes"],
                stl_bytes=cached["stl_bytes"],
                glb_bytes=cached["glb_bytes"],
                topo=cached["topology_map"],
                feature_graph=cached["feature_graph"],
                mesh_meta=cached.get("mesh_meta"),
                geometry_report_full=cached.get("geometry_report") or _compute_geometry_report(cached["topology_map"]),
                write_files=write_files,
                response_detail=response_detail,
                cache_hit=True,
                emit=_emit,
            )
        finally:
            if prior_step_path:
                try:
                    os.unlink(prior_step_path)
                except Exception:
                    pass

    # Drain the streaming executor; forward heartbeats to on_progress so a
    # subscribed UI sees the build advance in real time.
    last_error: str | None = None
    result_evt: dict[str, Any] | None = None
    for evt in _execute_build123d_code_streaming(execution_code, timeout=timeout):
        kind = evt.get("kind")
        if kind == "heartbeat":
            _emit({"phase": "building", "elapsed_s": evt.get("elapsed_s", 0)})
        elif kind == "error":
            last_error = str(evt.get("error") or "build123d execution failed")
        elif kind == "result":
            result_evt = evt

    if result_evt is None:
        try:
            return {
                "status": "error",
                "code": "execution_failed",
                "message": last_error or "build123d produced no result",
            }
        finally:
            if prior_step_path:
                try:
                    os.unlink(prior_step_path)
                except Exception:
                    pass

    step_bytes = result_evt["step_bytes"]
    stl_bytes = result_evt["stl_bytes"]
    glb_bytes = result_evt["glb_bytes"]
    topo = result_evt["topo"]
    # _mesh_meta is transient (used only for thumbnail coloring) — pop it so it
    # doesn't get written to topology_map.json on disk.
    mesh_meta = topo.pop("_mesh_meta", None) if isinstance(topo, dict) else None
    feature_graph = _topology_to_feature_graph(
        topo, source_code=storage_code, model_kind=model_kind,
    )
    geometry_report_full = _compute_geometry_report(topo)
    _write_build123d_cache(
        settings,
        cache_key,
        cache_key_material,
        step_bytes=step_bytes,
        stl_bytes=stl_bytes or b"",
        glb_bytes=glb_bytes or b"",
        topology_map=topo,
        feature_graph=feature_graph,
        geometry_report=geometry_report_full,
        mesh_meta=mesh_meta,
    )
    face_count = sum(1 for e in topo.get("entities", []) if e.get("type") == "face")
    feature_count = len(feature_graph.get("features", []))

    written: list[str] = []
    if write_files and step_bytes:
        _emit({"phase": "writing"})
        existing_pkg = project.get("aieng_file")
        pkg_path = resolve_project_path(settings, project_id, existing_pkg) if existing_pkg else None
        if pkg_path is None:
            from .main import project_dir, save_project as _save_project
            pkg_name = f"{project_id}.aieng"
            pkg_path = project_dir(settings, project_id) / pkg_name
            project["aieng_file"] = pkg_name
            _save_project(settings, project)

        _write_cad_artifacts(
            pkg_path=pkg_path,
            step_bytes=step_bytes,
            stl_bytes=stl_bytes or b"",
            topology_map=topo,
            feature_graph=feature_graph,
            generated_code=storage_code,
            glb_bytes=glb_bytes,
        )
        # Clear stale-artifact warnings: a fresh build invalidates any previous
        # EDIT IMPACT state, so aieng.agent_context won't show false positives.
        _clear_revalidation_status(pkg_path)

        # Mark the project as having viewable geometry and bump updated_at so the
        # UI project list reflects the new model (not stuck at status "empty").
        try:
            from .main import save_project as _save_project2, now_iso as _now_iso
            project["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
            # An explicit caller-supplied name wins; otherwise _publish_preview_to_viewer
            # auto-derives one for placeholder-named projects from the part labels.
            req_name = str(payload.get("name") or "").strip()
            if req_name:
                project["name"] = req_name
            project["updated_at"] = _now_iso()
            _save_project2(settings, project)
        except Exception:
            pass

        # Publish the preview to viewer/model.* + set web_asset so the UI viewer
        # actually loads it (the frontend resolves /assets/projects/{id}/{web_asset}).
        _publish_preview_to_viewer(settings, project_id, project, glb_bytes, stl_bytes)

        written = [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ]
        if glb_bytes:
            written.append("geometry/preview.glb")

    solid = next((e for e in topo.get("entities", []) if e.get("type") == "solid"), None)

    # Named-part summary so the agent gets text-side feedback even if its client
    # drops the thumbnail image block. parts_added is what this step introduced:
    # in append mode, current minus the prior step's parts; in replace, all of them.
    named_parts = _named_parts_from_feature_graph(feature_graph)
    parts_added = [p for p in named_parts if p not in prior_named_parts]

    result: dict[str, Any] = {
        "status": "ok",
        "schema_version": "0.1",
        "project_id": project_id,
        "backend": "build123d",
        "mode": mode,
        "used_base": used_base,
        "cache_hit": False,
        "response_detail": response_detail,
        "named_parts": named_parts,
        "parts_added": parts_added,
        "topology_summary": {
            "face_count": face_count,
            "feature_count": feature_count,
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": _slim_feature_graph_for_response(feature_graph),
        "geometry_report": _geometry_report_for_response(geometry_report_full, response_detail),
        "geometry_report_summary": _geometry_report_summary(geometry_report_full),
        "written_artifacts": written,
        "write_files": write_files,
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if glb_bytes else "stl",
    }

    # Visual feedback loop: render a 4-view contact sheet so an agent can judge
    # silhouette and alignment, not just face/bbox numbers. When per-body
    # mesh_meta is available, colorize each part by its build123d `.color` so
    # parts can be distinguished visually. When a reference image is attached
    # to the project, tile it next to the views for side-by-side comparison.
    # Opt out with {"thumbnail": false}; compact mode defaults thumbnails off.
    if _should_render_thumbnail(payload, response_detail):
        face_colors = _build_face_colors_from_mesh_meta(mesh_meta)
        # Resolve the project package via `project.get("aieng_file")` — after a
        # write_files run, that pointer is up-to-date; before any build it
        # already points at the package set by cad.set_reference_image.
        ref_aieng_file = project.get("aieng_file")
        ref_pkg = (
            resolve_project_path(settings, project_id, ref_aieng_file)
            if ref_aieng_file else None
        )
        ref_bytes = _read_reference_image_bytes(ref_pkg)
        thumb = render_mesh_thumbnail(
            stl_bytes or b"",
            face_colors=face_colors,
            reference_image_bytes=ref_bytes,
        )
        if thumb:
            result["thumbnail_png_base64"] = thumb

    try:
        return result
    finally:
        if prior_step_path:
            try:
                os.unlink(prior_step_path)
            except Exception:
                pass


# ── streaming variant ───────────────────────────────────────────────────────────

def _sse(event: dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def run_cad_generation_stream(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> Any:
    """Streaming variant of run_cad_generation — yields SSE-formatted progress events.

    Events: planning → coding → building → retrying → writing → done (with full result) | error.
    The generator runs the orchestration inline so each step is flushed to the
    client as soon as it happens (no list collector / no end-of-run dump).
    """
    from .project_io import get_project, resolve_project_path

    description = str(payload.get("description") or "").strip()
    if not description:
        yield _sse({"step": "error", "message": "description is required"})
        return

    hints: dict[str, Any] = payload.get("hints") or {}
    write_files = bool(payload.get("write_files", True))
    timeout = int(payload.get("timeout", 60))
    max_retries = int(payload.get("max_retries", 2))
    api_key = payload.get("api_key")
    llm_config = payload.get("llm_config") if isinstance(payload.get("llm_config"), dict) else None

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        yield _sse({"step": "error", "message": f"Project not found: {exc}"})
        return

    backend = Build123dBackend(settings)
    if not backend.can_generate():
        yield _sse({
            "step": "error",
            "message": "build123d is not installed — cannot generate CAD geometry",
        })
        return

    # Stage 1: ask the LLM for build123d code.
    yield _sse({"step": "planning", "message": "AI is analyzing the design description…"})
    try:
        generated_code = call_claude_for_build123d_code(
            description=description,
            hints=hints,
            api_key=api_key,
            settings=settings,
            llm_config=llm_config,
        )
    except HTTPException as exc:
        yield _sse({"step": "error", "message": str(exc.detail)})
        return
    except Exception as exc:
        yield _sse({"step": "error", "message": f"LLM call failed: {exc}"})
        return

    yield _sse({
        "step": "coding",
        "message": f"Code generated ({len(generated_code)} chars) — building geometry…",
        "code_preview": generated_code[:600],
    })

    # Stage 2: run build123d, retrying with LLM feedback on failure.
    warnings: list[str] = []
    last_error: str | None = None
    step_bytes: bytes | None = None
    stl_bytes: bytes | None = None
    glb_bytes: bytes | None = None
    topo: dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        attempt_error: str | None = None
        attempt_result: dict[str, Any] | None = None
        for evt in _execute_build123d_code_streaming(generated_code, timeout=timeout):
            kind = evt.get("kind")
            if kind == "heartbeat":
                elapsed_s = evt.get("elapsed_s", 0)
                if attempt == 0:
                    msg = f"build123d is executing… ({elapsed_s}s elapsed)"
                else:
                    msg = (
                        f"build123d is executing the AI fix… "
                        f"({elapsed_s}s, attempt {attempt + 1}/{max_retries + 1})"
                    )
                yield _sse({
                    "step": "building",
                    "message": msg,
                    "elapsed_s": elapsed_s,
                    "attempt": attempt,
                })
            elif kind == "error":
                attempt_error = str(evt.get("error") or "build123d failed")
            elif kind == "result":
                attempt_result = evt

        if attempt_result is not None:
            step_bytes = attempt_result["step_bytes"]
            stl_bytes = attempt_result["stl_bytes"]
            glb_bytes = attempt_result["glb_bytes"]
            topo = attempt_result["topo"]
            if attempt > 0:
                warnings.append(
                    f"Auto-fixed after {attempt} retry(s). Last error: {last_error}"
                )
            break
        else:
            last_error = attempt_error or "build123d failed without a specific error"
            if attempt < max_retries:
                yield _sse({
                    "step": "retrying",
                    "message": (
                        f"Build failed — asking AI to fix "
                        f"(attempt {attempt + 1}/{max_retries})…"
                    ),
                    "error_preview": last_error[:400],
                })
                warnings.append(
                    f"Attempt {attempt + 1} failed: {last_error[:300]}... Asking LLM to fix."
                )
                try:
                    generated_code = call_claude_for_build123d_refinement(
                        existing_code=generated_code,
                        feedback=(
                            "The build123d code failed to execute with this error:\n\n"
                            f"{last_error}\n\n"
                            "Please fix the code so it runs successfully. "
                            "Pay special attention to fillet radii (use max_fillet() "
                            "or smaller values), boolean operation order, and edge "
                            "selection validity."
                        ),
                        api_key=api_key,
                        settings=settings,
                        llm_config=llm_config,
                    )
                    yield _sse({
                        "step": "coding",
                        "message": "AI returned a fix — rebuilding…",
                        "code_preview": generated_code[:600],
                    })
                except Exception as fix_exc:
                    yield _sse({
                        "step": "error",
                        "message": f"Refinement LLM call failed: {fix_exc}",
                        "generated_code": generated_code,
                    })
                    return
            else:
                yield _sse({
                    "step": "error",
                    "message": f"CAD generation failed after {max_retries} retries",
                    "error": last_error,
                    "generated_code": generated_code,
                })
                return

    # At this point step_bytes is set (or we returned above).
    feature_graph = _topology_to_feature_graph(topo, source_code=generated_code)
    face_count = sum(1 for e in topo.get("entities", []) if e.get("type") == "face")

    # Stage 3: write artifacts.
    written: list[str] = []
    if write_files and step_bytes:
        existing_pkg = project.get("aieng_file")
        if existing_pkg:
            pkg_path = resolve_project_path(settings, project_id, existing_pkg)
        else:
            pkg_path = None

        if pkg_path is None:
            from .main import project_dir, save_project
            pkg_name = f"{project_id}.aieng"
            pkg_path = project_dir(settings, project_id) / pkg_name
            project["aieng_file"] = pkg_name
            save_project(settings, project)

        yield _sse({"step": "writing", "message": "Writing artifacts to package…"})

        _write_cad_artifacts(
            pkg_path=pkg_path,
            step_bytes=step_bytes,
            stl_bytes=stl_bytes or b"",
            topology_map=topo,
            feature_graph=feature_graph,
            generated_code=generated_code,
            glb_bytes=glb_bytes,
        )
        written = [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ]
        if glb_bytes:
            written.append("geometry/preview.glb")

    solid = next(
        (e for e in topo.get("entities", []) if e.get("type") == "solid"),
        None,
    )

    yield _sse({
        "step": "done",
        "message": f"CAD complete — {face_count} faces",
        "result": {
            "schema_version": "0.1",
            "project_id": project_id,
            "description": description,
            "backend": backend.name,
            "generated_code": generated_code,
            "topology_summary": {
                "face_count": face_count,
                "feature_count": len(feature_graph.get("features", [])),
                "bounding_box": solid.get("bounding_box") if solid else None,
            },
            "feature_graph": _slim_feature_graph_for_response(feature_graph),
            "geometry_report": _compute_geometry_report(topo),
            "written_artifacts": written,
            "write_files": write_files,
            "preview_url": f"/api/projects/{project_id}/cad-preview",
            "preview_format": "glb" if glb_bytes else "stl",
            "warnings": warnings,
        },
    })


# ── iterative refinement ──────────────────────────────────────────────────────

def call_claude_for_build123d_refinement(
    existing_code: str,
    feedback: str,
    api_key: str | None = None,
    model: str | None = None,
    settings: Any | None = None,
    llm_config: dict[str, Any] | None = None,
) -> str:
    """Call the configured LLM to refine existing build123d code."""
    if settings is None:
        raise HTTPException(status_code=503, detail="LLM settings are required for CAD refinement")

    ensure_aieng_on_path()
    from aieng.modeling.text_to_cad import (
        BUILD123D_SYSTEM_PROMPT,
        build_build123d_refine_prompt,
        build_system_prompt,
    )

    user_prompt = build_build123d_refine_prompt(existing_code, feedback)

    # Inject AGENTS.md as the single source of truth for build123d capabilities.
    agents_md = _load_agents_md()
    system_prompt = build_system_prompt(agents_md)

    raw = _generate_llm_text(
        settings,
        llm_config=llm_config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_key=api_key,
        model=model,
    )
    return _coerce_code(raw)


def refine_cad_generation(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Refine an existing CAD model based on natural-language engineer feedback.

    Reads geometry/source.py from the package, sends existing code + feedback
    to Claude, re-executes the refined code, and updates all CAD artifacts.
    """
    from .project_io import get_project, resolve_project_path

    feedback = str(payload.get("feedback") or "").strip()
    if not feedback:
        raise HTTPException(status_code=400, detail="feedback is required")

    write_files = bool(payload.get("write_files", True))
    timeout = int(payload.get("timeout", 60))
    api_key = payload.get("api_key")
    llm_config = payload.get("llm_config") if isinstance(payload.get("llm_config"), dict) else None

    project = get_project(settings, project_id)
    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        raise HTTPException(status_code=404, detail=".aieng package not found")

    existing_code: str | None = None
    prior_named_parts: list[str] = []
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if "geometry/source.py" in zf.namelist():
                existing_code = zf.read("geometry/source.py").decode()
            if "graph/feature_graph.json" in zf.namelist():
                prior_fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                prior_named_parts = _named_parts_from_feature_graph(prior_fg)
    except Exception:
        pass

    if not existing_code:
        raise HTTPException(status_code=404, detail="No CAD source code found — generate a model first")

    backend = Build123dBackend(settings)
    if not backend.can_generate():
        raise HTTPException(status_code=503, detail="build123d is not installed")

    refined_code = call_claude_for_build123d_refinement(
        existing_code,
        feedback,
        api_key=api_key,
        settings=settings,
        llm_config=llm_config,
    )

    try:
        step_bytes, stl_bytes, glb_bytes, topo = _execute_build123d_code(refined_code, timeout=timeout)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Refined CAD execution failed: {exc}")

    feature_graph = _topology_to_feature_graph(topo, source_code=refined_code)
    named_parts = _named_parts_from_feature_graph(feature_graph)
    parts_added = [part for part in named_parts if part not in prior_named_parts]

    written: list[str] = []
    if write_files:
        _write_cad_artifacts(
            pkg_path=package_path,
            step_bytes=step_bytes,
            stl_bytes=stl_bytes,
            topology_map=topo,
            feature_graph=feature_graph,
            generated_code=refined_code,
            glb_bytes=glb_bytes or None,
        )
        written = [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ]
        if glb_bytes:
            written.append("geometry/preview.glb")

        # Mark existing CAE mapping as stale since geometry changed
        _mark_cae_mapping_stale(package_path)
        written.append("simulation/cae_mapping.json")

    solid = next(
        (e for e in topo.get("entities", []) if e.get("type") == "solid"),
        None,
    )
    face_count = sum(1 for e in topo.get("entities", []) if e.get("type") == "face")

    return {
        "status": "ok",
        "schema_version": "0.1",
        "project_id": project_id,
        "mode": "refine",
        "feedback": feedback,
        "backend": "build123d",
        "refined_code": refined_code,
        "named_parts": named_parts,
        "parts_added": parts_added,
        "topology_summary": {
            "face_count": face_count,
            "feature_count": len(feature_graph.get("features", [])),
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": _slim_feature_graph_for_response(feature_graph),
        "written_artifacts": written,
        "write_files": write_files,
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if glb_bytes else "stl",
        "warnings": [],
    }


def get_named_part_bbox(
    settings: Any,
    project_id: str,
    part_name: str,
) -> dict[str, Any]:
    """Return bbox + center for a named solid from geometry/topology_map.json."""
    from .project_io import get_project, resolve_project_path

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        return {"status": "error", "code": "package_not_found", "message": ".aieng package not found"}

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if "geometry/topology_map.json" not in zf.namelist():
                return {
                    "status": "error",
                    "code": "topology_missing",
                    "message": "geometry/topology_map.json not found in package",
                    "available_parts": [],
                }
            topology_map = json.loads(zf.read("geometry/topology_map.json").decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "code": "topology_read_failed", "message": f"{exc}"}

    available_parts = _available_named_parts_from_topology(topology_map)
    entities = topology_map.get("entities", []) if isinstance(topology_map, dict) else []
    target = next(
        (
            entity
            for entity in entities
            if entity.get("type") == "solid" and entity.get("name") == part_name
        ),
        None,
    )
    if target is None:
        return {
            "status": "error",
            "message": f"part '{part_name}' not found",
            "available_parts": available_parts,
        }

    bbox = target.get("bounding_box")
    if not isinstance(bbox, list) or len(bbox) != 6:
        return {
            "status": "error",
            "code": "bbox_missing",
            "message": f"part '{part_name}' does not have a valid bounding_box",
            "available_parts": available_parts,
        }

    center = [
        round((float(bbox[0]) + float(bbox[3])) / 2, 4),
        round((float(bbox[1]) + float(bbox[4])) / 2, 4),
        round((float(bbox[2]) + float(bbox[5])) / 2, 4),
    ]
    return {
        "status": "ok",
        "project_id": project_id,
        "part_name": part_name,
        "bounding_box": bbox,
        "center": center,
        "available_parts": available_parts,
    }


# ── Stale mapping marker ──────────────────────────────────────────────────────

def _mark_cae_mapping_stale(pkg_path: Path) -> None:
    """If the package contains a cae_mapping.json, mark it stale atomically."""
    if not pkg_path.exists():
        return
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            if "simulation/cae_mapping.json" not in zf.namelist():
                return
            raw = zf.read("simulation/cae_mapping.json")
    except Exception:
        return

    try:
        data = json.loads(raw)
    except Exception:
        return

    data["stale"] = True
    data["stale_reason"] = "CAD geometry changed since mapping was created — re-run AI preprocessing"
    from datetime import datetime, timezone
    data["stale_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    tmp = pkg_path.with_suffix(".tmp.aieng")
    try:
        with zipfile.ZipFile(pkg_path, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename == "simulation/cae_mapping.json":
                    dst.writestr(item, json.dumps(data, indent=2).encode())
                else:
                    dst.writestr(item, src.read(item.filename))
        tmp.replace(pkg_path)
    except Exception:
        tmp.unlink(missing_ok=True)


# ── CAD source readback ──────────────────────────────────────────────────────

def _read_reference_image_bytes(pkg_path: Path | None) -> bytes | None:
    """Read geometry/reference.png from a project package, if present.

    Returns the raw PNG bytes for rendering. None when no package, no
    reference set, or any read error — best-effort, never blocks the build.
    """
    if pkg_path is None or not pkg_path.exists():
        return None
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            if "geometry/reference.png" in zf.namelist():
                return zf.read("geometry/reference.png")
    except Exception:
        return None
    return None


def set_reference_image(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Attach a reference image to a project for side-by-side thumbnails.

    The image (from URL or local path) is decoded, downscaled to fit within
    800x800 to keep the package small, re-encoded as PNG, and stored as
    geometry/reference.png plus geometry/reference.json metadata in the
    project's .aieng package. Subsequent cad.execute_build123d thumbnails
    will tile the reference in a rightmost column for visual comparison.

    Payload keys (one of image_url / image_path is required):
        image_url:   HTTP(S) URL to fetch (timeout 15s)
        image_path:  local file path
        description: optional caption stored in reference.json
    """
    from .project_io import get_project, resolve_project_path

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    image_url = payload.get("image_url")
    image_path_str = payload.get("image_path")
    description = (payload.get("description") or "").strip()

    if not image_url and not image_path_str:
        return {
            "status": "error",
            "code": "missing_input",
            "message": "Provide either image_url (HTTP/HTTPS) or image_path (local file).",
        }

    # Fetch raw image bytes
    raw_bytes: bytes
    source_descriptor: str
    try:
        if image_url:
            import urllib.request

            # Identifying UA — Wikimedia and others reject generic urllib UAs.
            req = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": (
                        "aieng-workbench/1.0 (CAD reference fetch; "
                        "https://github.com/armpro24-blip/cad-cae-copilot)"
                    ),
                    "Accept": "image/*",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_bytes = resp.read()
            source_descriptor = f"url:{image_url}"
        else:
            p = Path(image_path_str)
            if not p.exists():
                return {
                    "status": "error",
                    "code": "file_not_found",
                    "message": f"Local file not found: {image_path_str}",
                }
            raw_bytes = p.read_bytes()
            source_descriptor = f"path:{p.name}"
    except Exception as exc:
        return {
            "status": "error",
            "code": "fetch_failed",
            "message": f"Could not load reference image: {exc}",
        }

    # Decode, downscale, re-encode as PNG so the package stays compact
    try:
        from PIL import Image
        import io as _io

        img = Image.open(_io.BytesIO(raw_bytes)).convert("RGB")
        max_dim = 800
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()
        width, height = img.size
    except Exception as exc:
        return {
            "status": "error",
            "code": "invalid_image",
            "message": f"Image decode/resize failed: {exc}",
        }

    # Resolve / create the package
    existing_pkg = project.get("aieng_file")
    pkg_path = resolve_project_path(settings, project_id, existing_pkg) if existing_pkg else None
    if pkg_path is None:
        from .main import project_dir, save_project as _save_project

        pkg_name = f"{project_id}.aieng"
        pkg_path = project_dir(settings, project_id) / pkg_name
        project["aieng_file"] = pkg_name
        _save_project(settings, project)
    pkg_path.parent.mkdir(parents=True, exist_ok=True)

    reference_meta = {
        "source": source_descriptor,
        "description": description,
        "width": width,
        "height": height,
        "byte_size": len(png_bytes),
    }
    artifacts: dict[str, bytes] = {
        "geometry/reference.png": png_bytes,
        "geometry/reference.json": json.dumps(reference_meta, indent=2).encode(),
    }

    # Merge into existing zip if present; otherwise create a minimal package
    if pkg_path.exists():
        tmp = pkg_path.with_suffix(".tmp.aieng")
        try:
            with (
                zipfile.ZipFile(pkg_path, "r") as src,
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
            ):
                for item in src.infolist():
                    if item.filename not in artifacts:
                        dst.writestr(item, src.read(item.filename))
                for name, data in artifacts.items():
                    dst.writestr(name, data)
            tmp.replace(pkg_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    else:
        with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
            for name, data in artifacts.items():
                zf.writestr(name, data)

    return {
        "status": "ok",
        "project_id": project_id,
        "source": source_descriptor,
        "description": description,
        "width": width,
        "height": height,
        "byte_size_kb": round(len(png_bytes) / 1024, 1),
        "message": (
            "Reference image attached. Future cad.execute_build123d thumbnails "
            "will include it in a right-hand column for side-by-side comparison."
        ),
    }


# ── reference image search (Wikimedia Commons) ───────────────────────────────

_WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
_REFERENCE_SEARCH_UA = (
    "aieng-workbench/1.0 (CAD reference search; "
    "https://github.com/armpro24-blip/cad-cae-copilot)"
)


def _search_wikimedia_images(
    query: str, *, limit: int = 10, thumb_width: int = 1024
) -> list[dict[str, Any]]:
    """Query Wikimedia Commons for File-namespace images matching ``query``.

    Returns candidates ranked by Wikimedia's search relevance, each as
    ``{title, url, width, height, mime, page_url}``. SVG and result rows
    without a usable raster URL are filtered out (set_reference_image needs
    raster bytes that PIL can decode). Raises on network/parse failure so the
    caller can shape the error response.
    """
    import urllib.parse
    import urllib.request

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",  # File: namespace
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": str(thumb_width),
    }
    url = f"{_WIKIMEDIA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _REFERENCE_SEARCH_UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    pages = ((data.get("query") or {}).get("pages") or {})
    # generator=search annotates each page with `index` = search rank (1-based).
    ranked = sorted(pages.values(), key=lambda p: p.get("index", 1_000_000))
    candidates: list[dict[str, Any]] = []
    for page in ranked:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = str(info.get("mime") or "")
        if not mime.startswith("image/") or mime == "image/svg+xml":
            continue
        # Prefer the scaled thumb (smaller download); fall back to the full url.
        img_url = info.get("thumburl") or info.get("url")
        if not img_url:
            continue
        candidates.append(
            {
                "title": page.get("title"),
                "url": img_url,
                "width": info.get("thumbwidth") or info.get("width"),
                "height": info.get("thumbheight") or info.get("height"),
                "mime": mime,
                "page_url": info.get("descriptionurl"),
            }
        )
    return candidates


def search_reference_image(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Search Wikimedia Commons for a reference image and attach the best match.

    A convenience wrapper around :func:`set_reference_image`: it resolves a
    free-text query (e.g. ``"Boeing 747 side view"``) to a real image URL from
    Wikimedia Commons, then delegates to ``set_reference_image`` to fetch,
    downscale, and store it. The matched ``page_url`` is returned so the user
    can verify the source and its license before relying on it. Degrades
    gracefully: when nothing usable is found it returns ``status="no_results"``
    and the caller proceeds without a reference instead of failing the build.

    Payload keys:
        query:       required free-text search string.
        source:      optional; only "wikimedia" is supported (default).
        description: optional caption override stored with the reference.
    """
    query = (payload.get("query") or "").strip()
    if not query:
        return {
            "status": "error",
            "code": "missing_query",
            "message": "query is required (e.g. 'Boeing 747 side view').",
        }

    source = str(payload.get("source") or "wikimedia").strip().lower()
    if source != "wikimedia":
        return {
            "status": "error",
            "code": "unsupported_source",
            "message": (
                f"Unsupported reference source '{source}'. "
                "Only 'wikimedia' is supported."
            ),
        }

    try:
        candidates = _search_wikimedia_images(query)
    except Exception as exc:
        return {
            "status": "error",
            "code": "search_failed",
            "message": f"Wikimedia search failed: {exc}",
        }

    if not candidates:
        return {
            "status": "no_results",
            "project_id": project_id,
            "query": query,
            "source": source,
            "message": (
                f"No usable Wikimedia Commons image found for '{query}'. "
                "Proceed without a reference, or attach one manually with "
                "cad.set_reference_image."
            ),
        }

    # Try candidates in rank order; the first that set_reference_image can
    # actually fetch + decode wins (guards against dead thumbs / odd formats).
    last_error: str | None = None
    caption = (payload.get("description") or "").strip() or f"{query} (Wikimedia Commons)"
    for cand in candidates:
        attached = set_reference_image(
            settings,
            project_id,
            {"image_url": cand["url"], "description": caption},
        )
        if attached.get("status") == "ok":
            return {
                "status": "ok",
                "project_id": project_id,
                "query": query,
                "source": source,
                "attached": True,
                "matched_url": cand["url"],
                "page_url": cand.get("page_url"),
                "title": cand.get("title"),
                "width": attached.get("width"),
                "height": attached.get("height"),
                "byte_size_kb": attached.get("byte_size_kb"),
                "candidates_considered": len(candidates),
                "message": (
                    f"Attached a Wikimedia Commons reference for '{query}'. "
                    "Verify the source/license at page_url. Future "
                    "cad.execute_build123d thumbnails will tile it for "
                    "side-by-side comparison."
                ),
            }
        last_error = attached.get("message")

    return {
        "status": "error",
        "code": "attach_failed",
        "project_id": project_id,
        "query": query,
        "source": source,
        "message": (
            f"Found {len(candidates)} candidate(s) but none could be "
            f"fetched/decoded. Last error: {last_error}"
        ),
    }


# ── critique: deterministic engineering audit ────────────────────────────────

# Canonical labels (from aieng/schemas/feature_graph.schema.json type enum)
# that imply the part is a structural body whose wall thickness must respect
# manufacturing minimums. Substring match against the user-supplied `.label`.
_THIN_PART_LABELS: tuple[str, ...] = (
    "wall", "rib", "cover", "lid", "back_plate", "base_plate",
    "plate", "shell", "flange",
)

# Drill sizes commonly stocked — flag through-holes that aren't ~these.
_STANDARD_HOLE_DIAMETERS_MM: tuple[float, ...] = (
    1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0,
    12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 27.0, 30.0,
)


def critique(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Run a deterministic engineering critique against the project's geometry.

    Inspects the named features in graph/feature_graph.json plus the bounding
    boxes in geometry/topology_map.json and checks them against the
    manufacturing rules derived from aieng/schemas/constraints.schema.json
    (min wall thickness, standard hole sizes). Returns structured findings
    with severity, category, the affected feature/body id, what was observed,
    and a suggested fix.

    Payload (all optional):
        mode: "auto" (default) | "engineering" | "geometry"
            - auto: runs geometry sanity + engineering audit when the model has
              labelled engineering features (rib/base_plate/...).
            - engineering: forces the manufacturing audit even on un-canonical
              labels.
            - geometry: only basic sanity checks (component counts, sizes).
        min_wall_mm: float, default 3.0 (CNC aluminium minimum).
        min_corner_radius_mm: float, default 2.0.

    Use this AFTER cad.execute_build123d to validate engineering parts before
    user review or simulation handoff.
    """
    from .project_io import get_project, resolve_project_path

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg_path is None or not pkg_path.exists():
        return {
            "status": "error",
            "code": "no_package",
            "message": "No .aieng package; build a model with cad.execute_build123d first.",
        }

    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = zf.namelist()
            topo: dict[str, Any] = (
                json.loads(zf.read("geometry/topology_map.json").decode("utf-8"))
                if "geometry/topology_map.json" in names else {}
            )
            fg: dict[str, Any] = (
                json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                if "graph/feature_graph.json" in names else {}
            )
    except Exception as exc:
        return {"status": "error", "code": "read_failed", "message": f"{exc}"}

    mode = str(payload.get("mode", "auto"))
    min_wall = float(payload.get("min_wall_mm", 3.0))
    min_corner_radius = float(payload.get("min_corner_radius_mm", 2.0))

    findings: list[dict[str, Any]] = []
    finding_counter = 0

    def add(severity: str, category: str, rule: str, feature: str,
            feature_id: str | None, observation: str, fix: str) -> None:
        nonlocal finding_counter
        finding_counter += 1
        findings.append({
            "id": f"find_{finding_counter:03d}",
            "severity": severity,
            "category": category,
            "rule": rule,
            "feature": feature,
            "feature_id": feature_id,
            "observation": observation,
            "suggested_fix": fix,
        })

    # ── geometry sanity (always runs) ──
    entities = topo.get("entities", [])
    bodies = {e["id"]: e for e in entities if e.get("type") == "solid"}
    body_count = len(bodies)

    # 1) Empty model
    if body_count == 0:
        return {
            "status": "ok",
            "project_id": project_id,
            "mode": mode,
            "verdict": "skipped",
            "message": "No solids in the topology map; nothing to critique.",
            "findings": [],
        }

    # 2) Floating geometry — a body whose nearest-neighbor gap is wildly
    # larger than the typical part size is likely detached. Uses approximate
    # bbox-gap (center distance minus half-sizes) rather than distance to
    # centroid, so tall/elongated models (e.g. a humanoid) don't false-flag
    # legitimate distant parts that are still connected through neighbors.
    if body_count >= 2:
        body_data: list[tuple[str, dict[str, Any], tuple[float, float, float], float]] = []
        for body_id, b in bodies.items():
            bb = b.get("bounding_box") or []
            if len(bb) < 6:
                continue
            center = ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)
            size = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
            body_data.append((body_id, b, center, size))

        if len(body_data) >= 2:
            mean_size = sum(d[3] for d in body_data) / len(body_data)
            # A gap larger than ~one typical part is suspicious. Floor at 50mm
            # so tiny-model false positives don't dominate.
            gap_threshold = max(mean_size, 50.0)

            for body_id, b, c1, s1 in body_data:
                # Approximate gap to the closest other body
                min_gap = float("inf")
                for other_id, _, c2, s2 in body_data:
                    if other_id == body_id:
                        continue
                    center_dist = (
                        (c1[0] - c2[0]) ** 2
                        + (c1[1] - c2[1]) ** 2
                        + (c1[2] - c2[2]) ** 2
                    ) ** 0.5
                    gap = center_dist - (s1 + s2) / 2.0
                    if gap < min_gap:
                        min_gap = gap

                if min_gap > gap_threshold:
                    add(
                        "high", "geometry", "floating_component",
                        b.get("name", body_id), body_id,
                        f"{b.get('name', body_id)}: nearest other part is "
                        f"~{min_gap:.0f}mm away (typical part size {mean_size:.0f}mm) "
                        "— this part is disconnected from the rest of the model.",
                        "Check the Location() / .moved() coordinates for this part; "
                        "it may be a typo that placed it far from the body.",
                    )

    # ── engineering audit ──
    # Run when:
    #   - mode == "engineering" (forced), OR
    #   - mode == "auto" AND at least one named feature has a canonical
    #     engineering label (rib / base_plate / mounting_hole / ...).
    features = fg.get("features", [])
    named_features = [f for f in features if _is_named_part_feature(f)]

    def _has_canonical_label(feat: dict[str, Any]) -> bool:
        name = (feat.get("name") or "").lower()
        canonical = (
            "base_plate", "back_plate", "mount_plate",
            "mounting_hole", "rib", "boss", "flange",
            "interface_face", "load_interface",
            "wall", "cover", "lid", "shell",
        )
        return any(c in name for c in canonical)

    engineering_eligible = (
        mode == "engineering"
        or (mode == "auto" and any(_has_canonical_label(f) for f in named_features))
    )

    if engineering_eligible:
        # 3) Wall / rib / plate thickness check
        for feat in named_features:
            name = feat.get("name") or ""
            name_lower = name.lower()
            if not any(t in name_lower for t in _THIN_PART_LABELS):
                continue
            geo = feat.get("geometry_refs") or {}
            body_id = geo.get("body") if isinstance(geo, dict) else None
            body = bodies.get(body_id) if body_id else None
            if not body:
                continue
            bb = body.get("bounding_box") or []
            if len(bb) < 6:
                continue
            dims = (bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
            positive = [d for d in dims if d > 0]
            if not positive:
                continue
            thinnest = min(positive)
            if thinnest < min_wall:
                # Walls/shells are higher-stakes than ribs (load-bearing)
                severity = "high" if any(t in name_lower for t in ("wall", "shell", "back_plate")) else "medium"
                add(
                    severity, "manufacturing_rule", "min_wall_thickness",
                    name, body_id,
                    f"{name}: thinnest dimension is {thinnest:.2f}mm; CNC minimum is {min_wall:.1f}mm.",
                    f"Increase the thinnest dimension of {name} to at least {min_wall:.1f}mm "
                    f"(or downgrade target process to sheet metal / FDM and lower min_wall_mm).",
                )

        # 4) Mounting hole feature checks: standard size, count sanity
        for feat in features:
            if feat.get("type") not in ("mounting_hole", "mounting_hole_pattern"):
                continue
            params = feat.get("parameters") or {}
            diameter = params.get("hole_diameter_mm")
            if isinstance(diameter, (int, float)):
                nearest = min(_STANDARD_HOLE_DIAMETERS_MM, key=lambda d: abs(d - float(diameter)))
                # 0.3mm slop tolerates measurement rounding (e.g. 9.85→10) but
                # flags actual non-standard picks (9.5, 7, 11) so the agent
                # can choose a stocked drill.
                if abs(float(diameter) - nearest) > 0.3:
                    add(
                        "low", "manufacturing_rule", "standard_hole_size",
                        feat.get("name", "<unnamed>"),
                        (feat.get("geometry_refs", {}) or {}).get("body") if isinstance(feat.get("geometry_refs"), dict) else None,
                        f"{feat.get('name', '<unnamed>')}: hole diameter {float(diameter):.2f}mm is "
                        f"non-standard; closest standard drill is {nearest:.1f}mm.",
                        f"Round the hole diameter to {nearest:.1f}mm to use an off-the-shelf drill.",
                    )

        # 5) No mounting interface at all on a part that's labelled like a bracket
        looks_like_bracket = any(
            "bracket" in (b.get("name") or "").lower()
            or "plate" in (b.get("name") or "").lower()
            for b in bodies.values()
        )
        has_mounting = any(
            f.get("type") in ("mounting_hole", "mounting_hole_pattern") for f in features
        )
        if looks_like_bracket and not has_mounting:
            add(
                "medium", "engineering", "missing_mounting_interface",
                "(model)", None,
                "Model contains a plate / bracket part but no mounting holes were detected.",
                "Add at least one Hole() / cboreHole() / cskHole() to expose a mounting interface, "
                "or label the holes you have so the topology heuristic picks them up.",
            )

    # ── verdict ──
    severity_counts = {
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "medium": sum(1 for f in findings if f["severity"] == "medium"),
        "low": sum(1 for f in findings if f["severity"] == "low"),
    }
    if severity_counts["high"] > 0:
        verdict = "fails_audit"
    elif severity_counts["medium"] > 0:
        verdict = "passes_with_warnings"
    elif severity_counts["low"] > 0:
        verdict = "passes_with_notes"
    else:
        verdict = "passes"

    # The "fail-first" view: the highest-severity findings restated as
    # blocking objections, so an agent driving the critique can act on the
    # top issues without sorting the full list.
    fail_first = [
        f"{f['feature']}: {f['observation']}"
        for f in findings
        if f["severity"] in ("high", "medium")
    ][:5]

    return {
        "status": "ok",
        "project_id": project_id,
        "mode": mode,
        "verdict": verdict,
        "summary": {
            "findings_count": len(findings),
            "by_severity": severity_counts,
            "named_part_count": len(named_features),
            "engineering_audit_run": engineering_eligible,
        },
        "fail_first_objections": fail_first,
        "findings": findings,
        "rules_applied": {
            "min_wall_mm": min_wall,
            "min_corner_radius_mm": min_corner_radius,
            "standard_hole_diameters_mm": list(_STANDARD_HOLE_DIAMETERS_MM),
        },
        "rule_source": "aieng/schemas/constraints.schema.json (manufacturing_rule type)",
    }


# ── design review: critique + structure + concrete fix targets (read-only) ───

# Extra dimension keywords per critique rule, unioned with the finding's feature
# name to bind it to a concrete editable parameter. critique itself only knows
# the body id; design_review resolves the parameter the agent would actually edit.
_REVIEW_RULE_KEYWORDS: dict[str, str] = {
    "min_wall_thickness": "wall thickness",
    "standard_hole_size": "hole diameter",
    "min_corner_radius": "fillet corner radius",
}

_REVIEW_VERDICT_RANK = {
    "skipped": 0,
    "passes": 1,
    "passes_with_notes": 2,
    "passes_with_warnings": 3,
    "fails_audit": 4,
}


def _verdict_from_counts(counts: dict[str, int]) -> str:
    if counts.get("high", 0) > 0:
        return "fails_audit"
    if counts.get("medium", 0) > 0:
        return "passes_with_warnings"
    if counts.get("low", 0) > 0:
        return "passes_with_notes"
    return "passes"


def _symmetry_findings(geometry_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Structural findings critique does NOT produce: broken / missing mirror pairs.

    Pure. Reads the `symmetry` list from a geometry_report and turns each
    non-ok pair (`ok == False`) and each `missing_partner` row into a medium
    finding shaped like critique's findings (so they merge seamlessly).
    """
    out: list[dict[str, Any]] = []
    symmetry = geometry_report.get("symmetry") if isinstance(geometry_report, dict) else None
    if not isinstance(symmetry, list):
        return out
    counter = 0
    for item in symmetry:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "missing_partner":
            counter += 1
            part = item.get("part", "<part>")
            expected = item.get("expected_partner", "?")
            out.append({
                "id": f"sym_{counter:03d}",
                "severity": "medium",
                "category": "structure",
                "rule": "broken_symmetry",
                "feature": str(part),
                "feature_id": None,
                "observation": (
                    f"{part}: expected mirror partner '{expected}' not found — "
                    "left/right symmetry is likely broken."
                ),
                "suggested_fix": (
                    f"Add the mirrored counterpart of {part} (e.g. "
                    f"mirror({part}, about=Plane.YZ)) or fix its label."
                ),
            })
        elif item.get("ok") is False:
            counter += 1
            pair = item.get("pair") or []
            pair_label = " / ".join(str(p) for p in pair) if pair else "<pair>"
            residual = item.get("align_residual_mm")
            axis = item.get("mirror_axis", "?")
            residual_txt = f"{residual}mm" if residual is not None else "non-zero"
            out.append({
                "id": f"sym_{counter:03d}",
                "severity": "medium",
                "category": "structure",
                "rule": "broken_symmetry",
                "feature": pair_label,
                "feature_id": None,
                "observation": (
                    f"{pair_label}: mirror pair is not symmetric across {axis} "
                    f"(alignment residual {residual_txt}) — likely a coordinate typo."
                ),
                "suggested_fix": (
                    f"Re-derive one side by mirroring the other "
                    f"(mirror(part, about=Plane.{str(axis).upper()}Z)) so the pair matches."
                ),
            })
    return out


def _bind_finding_to_parameter(
    finding: dict[str, Any], index: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """Resolve the concrete editable parameter a finding points at, or None.

    Reuses parameter_binding's token-overlap matcher (and its honesty rules:
    no index → unverified, no overlap → not found, tie → ambiguous). The slot
    query unions the finding's feature name with rule-specific dimension words.
    """
    from .agent_autopilot.parameter_binding import bind_parameter_slots

    keywords = _REVIEW_RULE_KEYWORDS.get(str(finding.get("rule") or ""), "")
    query = f"{finding.get('feature') or ''} {keywords}".strip()
    if not query:
        return None
    binding = bind_parameter_slots([{"name": query, "value": None, "unit": None}], index)[0]
    known = binding.get("known")
    if known is True:
        return {
            "known": True,
            "feature_id": binding["feature_id"],
            "parameter_name": binding["parameter_name"],
            "cad_parameter_name": binding["cad_parameter_name"],
            "current_value": binding["current_value"],
            "min_value": binding["min_value"],
            "max_value": binding["max_value"],
            "match_score": binding["match_score"],
        }
    if binding.get("candidates"):
        return {"known": False, "reason": binding.get("reason"), "candidates": binding["candidates"]}
    # No overlap / no index: stay quiet rather than emit a noisy "not found" per
    # finding — the absence of a target already says "no fast parametric fix".
    return None


def design_review(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Read-only self-review: critique + structural checks + concrete fix targets.

    Synthesizes existing deterministic signals into one prioritized, actionable
    report so an agent can self-correct before presenting a result, instead of
    only fixing what the user explicitly points out. It:

      1. runs ``critique`` (manufacturing rules, floating components, ...),
      2. adds the symmetry checks critique lacks (from ``geometry_report``),
      3. binds each fixable finding to the concrete ``cad.edit_parameter``
         target the agent would edit (featureId / parameterName / range).

    It changes NOTHING: it never calls ``cad.edit_parameter`` /
    ``cad.execute_build123d``. Applying a fix still goes through the normal
    approved modeling-plan path. ``response_detail: "compact"`` returns the prioritized
    actions + summary only; ``"full"`` (default) also returns every finding.

    Payload (all optional): ``mode`` / ``min_wall_mm`` / ``min_corner_radius_mm``
    (forwarded to critique), ``response_detail`` ("compact" | "full").
    """
    from .project_io import get_project, resolve_project_path

    detail = _normalize_response_detail(payload.get("response_detail"))

    crit = critique(settings, project_id, payload)
    if crit.get("status") != "ok":
        return crit

    # Load topology + feature graph once for the structural + parameter signals.
    geometry_report: dict[str, Any] = {}
    parameter_index: list[dict[str, Any]] | None = None
    try:
        project = get_project(settings, project_id)
        pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
        if pkg_path is not None and pkg_path.exists():
            with zipfile.ZipFile(pkg_path, "r") as zf:
                names = zf.namelist()
                if "geometry/topology_map.json" in names:
                    topo = json.loads(zf.read("geometry/topology_map.json").decode("utf-8"))
                    geometry_report = _compute_geometry_report(topo)
                if "graph/feature_graph.json" in names:
                    from .agent_autopilot.parameter_binding import build_parameter_index

                    fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                    parameter_index = build_parameter_index(fg)
    except Exception:
        # Critique already succeeded; degrade to critique-only findings rather
        # than fail the whole review on a structural-signal read error.
        geometry_report = {}

    findings = list(crit.get("findings") or []) + _symmetry_findings(geometry_report)

    # Bind fix targets and build the prioritized, actionable subset.
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    actions: list[dict[str, Any]] = []
    for finding in findings:
        target = _bind_finding_to_parameter(finding, parameter_index)
        if target is not None:
            finding["parameter_target"] = target
            if target.get("known") is True:
                actions.append({
                    "finding_id": finding.get("id"),
                    "severity": finding.get("severity"),
                    "category": finding.get("category"),
                    "observation": finding.get("observation"),
                    "suggested_fix": finding.get("suggested_fix"),
                    "parameter_target": target,
                })
    actions.sort(key=lambda a: severity_rank.get(a.get("severity"), 9))

    severity_counts = {
        sev: sum(1 for f in findings if f.get("severity") == sev)
        for sev in ("high", "medium", "low")
    }
    verdict = _verdict_from_counts(severity_counts)
    floating_parts = geometry_report.get("floating_parts") or []
    broken_symmetry = [
        f["feature"] for f in findings if f.get("rule") == "broken_symmetry"
    ]

    if actions:
        recommendation = (
            f"{len(actions)} finding(s) map to a fast cad.edit_parameter fix; "
            "start with the highest-severity targets, then re-run cad.design_review. "
            "Issues without a parameter target need a geometry edit "
            "(cad.execute_build123d / replace_part)."
        )
    elif findings:
        recommendation = (
            "No finding maps to a single editable parameter — address them with a "
            "geometry edit (cad.execute_build123d / cad.replace_part) and re-review."
        )
    else:
        recommendation = "No issues found. Geometry passes the deterministic review."

    result: dict[str, Any] = {
        "status": "ok",
        "project_id": project_id,
        "verdict": verdict,
        "critique_verdict": crit.get("verdict"),
        "summary": {
            "findings_count": len(findings),
            "by_severity": severity_counts,
            "actionable_count": len(actions),
            "floating_parts": floating_parts,
            "broken_symmetry": broken_symmetry,
        },
        "actions": actions,
        "recommendation": recommendation,
        "message": (
            "Read-only review — nothing was changed. Apply any fix through the "
            "modeling-plan-approved cad.edit_parameter (parameter targets) or "
            "cad.execute_build123d / cad.replace_part path."
        ),
    }
    if detail != "compact":
        result["findings"] = findings
    return result


def read_cad_source(settings: Any, project_id: str) -> dict[str, Any]:
    """Return the accumulated build123d source plus a structured state summary.

    Read-only. Lets an agent decide replace vs append, see which named parts
    already exist, and avoid re-adding prior logic. Shape:
        {status, project_id, mode, source, named_parts, has_base}
    ``has_base`` is True when a source exists (i.e. append is possible).
    """
    from .project_io import get_project, resolve_project_path

    empty = {
        "status": "ok",
        "project_id": project_id,
        "mode": "build123d",
        "source": None,
        "named_parts": [],
        "has_base": False,
    }
    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    pkg = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg is None or not pkg.exists():
        return empty

    source: str | None = None
    named_parts: list[str] = []
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = zf.namelist()
            if "geometry/source.py" in names:
                source = zf.read("geometry/source.py").decode("utf-8")
            if "graph/feature_graph.json" in names:
                fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                named_parts = _named_parts_from_feature_graph(fg)
    except Exception as exc:
        return {"status": "error", "code": "read_failed", "message": f"{exc}"}

    return {
        "status": "ok",
        "project_id": project_id,
        "mode": "build123d",
        "source": source,
        "named_parts": named_parts,
        "has_base": bool(source),
    }


# ── CAD preview (serve STL from package) ─────────────────────────────────────

def serve_cad_preview(settings: Any, project_id: str) -> tuple[bytes, str]:
    """Extract the best available CAD preview from the .aieng package.

    Returns (content, format) where format is 'glb' or 'stl'.
    GLB is preferred for richer rendering; STL is the fallback.
    """
    from .project_io import get_project, resolve_project_path

    project = get_project(settings, project_id)
    pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))

    if pkg_path is None or not pkg_path.exists():
        raise HTTPException(status_code=404, detail="Package not found")

    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = zf.namelist()
            if "geometry/preview.glb" in names:
                return zf.read("geometry/preview.glb"), "glb"
            if "geometry/preview.stl" in names:
                return zf.read("geometry/preview.stl"), "stl"
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=404, detail="No CAD preview in package — generate a model first")


# ── parametric edit: fast text replacement in source.py ────────────────────────

def edit_build123d_parameter(
    settings: Any,
    project_id: str,
    feature_id: str,
    parameter_name: str,
    new_value: Any,
    timeout: int = 120,
    response_detail: str = "full",
    thumbnail: bool | None = None,
) -> dict[str, Any]:
    """Apply a parametric edit by replacing a named constant in source.py.

    Workflow:
        1. Validate the edit contract against graph/feature_graph.json.
        2. Read geometry/source.py from the .aieng package.
        3. Locate the UPPER_SNAKE_CASE constant and replace its value.
        4. Re-execute build123d with the modified source.
        5. Write new geometry/topology/feature_graph back into the package.
        6. Return a thumbnail so the caller can visually verify the change.

    This is deterministic and fast (sub-second to a few seconds) because it
    bypasses the LLM entirely — only a text substitution + rebuild.
    """
    from .project_io import (
        _validate_cad_parameter_edit_contract,
        get_project,
        resolve_project_path,
    )
    response_detail = _normalize_response_detail(response_detail)

    # 1. Load project & package
    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg_path is None or not pkg_path.exists():
        return {
            "status": "error",
            "code": "package_not_found",
            "message": ".aieng package not found — generate a model first",
        }

    # 2. Validate contract (reads feature_graph.json, checks min/max bounds)
    try:
        contract = _validate_cad_parameter_edit_contract(
            pkg_path, feature_id, parameter_name, new_value
        )
    except ValueError as exc:
        return {"status": "error", "code": "invalid_contract", "message": str(exc)}

    param_info = contract["parameter"]
    cad_parameter_name = param_info.get("cad_parameter_name") or parameter_name
    previous_value = param_info.get("current_value")

    # 3. Read source.py + reference image + the BEFORE topology (for regression diff)
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = zf.namelist()
            source_code = zf.read("geometry/source.py").decode("utf-8")
            ref_bytes = (
                zf.read("geometry/reference.png")
                if "geometry/reference.png" in names
                else None
            )
            before_topo: dict[str, Any] = (
                json.loads(zf.read("geometry/topology_map.json").decode("utf-8"))
                if "geometry/topology_map.json" in names
                else {}
            )
    except Exception as exc:
        return {
            "status": "error",
            "code": "read_failed",
            "message": f"Failed to read source.py from package: {exc}",
        }

    # 4. Text replacement: find `CONSTANT_NAME = value` and swap the numeric part.
    #    We preserve indentation and any inline comment.
    pattern = rf'^([ \t]*)({re.escape(cad_parameter_name)})([ \t]*=[ \t]*)([0-9]+\.?[0-9]*)(.*)$'
    modified_lines: list[str] = []
    found = False

    for line in source_code.splitlines():
        m = re.match(pattern, line)
        if m:
            indent = m.group(1)
            name = m.group(2)
            eq = m.group(3)
            tail = m.group(5)
            modified_lines.append(f"{indent}{name}{eq}{new_value}{tail}")
            found = True
        else:
            modified_lines.append(line)

    if not found:
        return {
            "status": "error",
            "code": "parameter_not_found_in_source",
            "message": (
                f"Named constant '{cad_parameter_name}' not found in source.py. "
                f"Ensure the CAD code declares parameters as UPPER_SNAKE_CASE constants "
                f"(e.g. {cad_parameter_name} = {previous_value})."
            ),
            "previous_value": previous_value,
        }

    modified_source = "\n".join(modified_lines)

    # 5. Re-execute build123d with the modified source
    backend = Build123dBackend(settings)
    if not backend.can_generate():
        return {
            "status": "error",
            "code": "build123d_unavailable",
            "message": "build123d is not installed — cannot re-execute CAD code.",
        }

    try:
        cached_result = _execute_build123d_cached(
            settings,
            modified_source,
            mode="replace",
            model_kind=contract.get("model_kind", "auto"),
            timeout=timeout,
        )
    except Exception as exc:
        # If the edit breaks the model, return the error but preserve the
        # previous state (do NOT write the broken source back into the package).
        return {
            "status": "error",
            "code": "execution_failed",
            "message": (
                f"Parameter edit caused build failure — the value {new_value} may be "
                f"geometrically invalid for this feature. Error: {exc}"
            ),
            "previous_value": previous_value,
            "new_value": new_value,
            "cad_parameter_name": cad_parameter_name,
        }

    step_bytes = cached_result["step_bytes"]
    stl_bytes = cached_result["stl_bytes"]
    glb_bytes = cached_result["glb_bytes"]
    topo = cached_result["topo"]
    feature_graph = cached_result["feature_graph"]
    geometry_report_full = cached_result["geometry_report"]
    mesh_meta = cached_result.get("mesh_meta")
    cache_hit = cached_result["cache_hit"]

    # 6b. Geometry regression diff — confirm the edit changed only what it should.
    # The set of parts we EXPECT to move: for a named_part feature, just that
    # part; for a shared/global constant, any part is fair game (no collateral
    # judgment); otherwise we can't attribute it to one part, so skip the verdict.
    edited_feature = contract.get("feature") or {}
    before_names = set(_solids_by_name(before_topo))
    if edited_feature.get("type") == "global_params":
        expected_parts: set[str] | None = None
    elif edited_feature.get("name") in before_names:
        expected_parts = {edited_feature["name"]}
    else:
        expected_parts = None
    regression_diff = _diff_topology(before_topo, topo, expected_parts=expected_parts)

    # 7. Write artifacts back into the package atomically
    _write_cad_artifacts(
        pkg_path=pkg_path,
        step_bytes=step_bytes,
        stl_bytes=stl_bytes or b"",
        topology_map=topo,
        feature_graph=feature_graph,
        generated_code=modified_source,
        glb_bytes=glb_bytes,
    )
    _clear_revalidation_status(pkg_path)

    # 8. Mark project as updated
    try:
        from .main import save_project as _save_project, now_iso as _now_iso
        project["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
        project["updated_at"] = _now_iso()
        _save_project(settings, project)
    except Exception:
        pass
    _publish_preview_to_viewer(settings, project_id, project, glb_bytes, stl_bytes)

    # 9. Render thumbnail so the caller can verify visually
    # mesh_meta was already extracted from topo by _execute_build123d_cached.
    thumb = None
    if _should_render_thumbnail(thumbnail, response_detail):
        face_colors = _build_face_colors_from_mesh_meta(mesh_meta)
        thumb = render_mesh_thumbnail(
            stl_bytes or b"",
            face_colors=face_colors,
            reference_image_bytes=ref_bytes,
        )

    solid = next(
        (e for e in topo.get("entities", []) if e.get("type") == "solid"), None
    )
    # geometry_report_full already computed by _execute_build123d_cached.

    result = {
        "status": "ok",
        "schema_version": "0.1",
        "project_id": project_id,
        "response_detail": response_detail,
        "feature_id": feature_id,
        "parameter_name": parameter_name,
        "cad_parameter_name": cad_parameter_name,
        "new_value": new_value,
        "previous_value": previous_value,
        "topology_summary": {
            "face_count": sum(
                1 for e in topo.get("entities", []) if e.get("type") == "face"
            ),
            "feature_count": len(feature_graph.get("features", [])),
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": _slim_feature_graph_for_response(feature_graph),
        "geometry_report": _geometry_report_for_response(geometry_report_full, response_detail),
        "geometry_report_summary": _geometry_report_summary(geometry_report_full),
        "regression_diff": regression_diff,
        "written_artifacts": [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ] + (["geometry/preview.glb"] if glb_bytes else []),
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if glb_bytes else "stl",
        "thumbnail_png_base64": thumb,
    }
    if not thumb:
        result.pop("thumbnail_png_base64", None)
    return result


# ── part-level edits: remove / replace a named part (F2) ──────────────────────
# append-mode can only ADD geometry; to refine a character/product the agent
# also needs to drop or swap a single part by label without resubmitting the
# whole script. Both operations transform source.py so it stays self-consistent
# (the stored script still rebuilds the current model), then re-execute + diff.

# Snippet appended after the prior source to drop the named child(ren). Robust to
# a single-body result (no children) — it treats the whole result as one part.
_REMOVE_PART_SNIPPET = """

# --- aieng remove_part: drop '{label}' ---
_aieng_prev = result.part if hasattr(result, 'part') else result
_aieng_children = list(getattr(_aieng_prev, 'children', None) or [])
if not _aieng_children:
    _aieng_children = [_aieng_prev]
_aieng_kept = [c for c in _aieng_children if (getattr(c, 'label', '') or '') != '{label}']
result = Compound(children=_aieng_kept)
"""

# Snippet that drops the old child(ren) then appends the caller's replacement
# code (which must reassign `result` to the new part and set its `.label`).
_REPLACE_PART_HEAD = """

# --- aieng replace_part: swap '{label}' ---
_aieng_prev = result.part if hasattr(result, 'part') else result
_aieng_children = list(getattr(_aieng_prev, 'children', None) or [])
if not _aieng_children:
    _aieng_children = [_aieng_prev]
_aieng_kept = [c for c in _aieng_children if (getattr(c, 'label', '') or '') != '{label}']
# --- replacement code (reassigns `result` to the new part) ---
"""

_REPLACE_PART_TAIL = """
# --- aieng replace_part: recombine ---
_aieng_repl = result.part if hasattr(result, 'part') else result
result = Compound(children=_aieng_kept + [_aieng_repl])
"""


def _rebuild_after_part_edit(
    settings: Any,
    project_id: str,
    project: dict[str, Any],
    pkg_path: Path,
    new_source: str,
    before_topo: dict[str, Any],
    *,
    action: str,
    label: str,
    expected_parts: set[str] | None,
    ref_bytes: bytes | None,
    timeout: int,
    response_detail: str = "full",
    thumbnail: bool | None = None,
) -> dict[str, Any]:
    """Execute ``new_source``, write artifacts, and assemble the response with a
    regression diff. Shared by remove_part / replace_part."""
    # Preserve the original model_kind so cache key + heuristics stay consistent.
    model_kind = "auto"
    with zipfile.ZipFile(pkg_path, "r") as zf:
        if "graph/feature_graph.json" in zf.namelist():
            fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
            model_kind = fg.get("model_kind", "auto")

    try:
        cached_result = _execute_build123d_cached(
            settings,
            new_source,
            mode="replace",
            model_kind=model_kind,
            timeout=timeout,
        )
    except Exception as exc:
        return {
            "status": "error",
            "code": "execution_failed",
            "message": f"{action} for '{label}' failed to rebuild: {exc}",
            "label": label,
        }

    step_bytes = cached_result["step_bytes"]
    stl_bytes = cached_result["stl_bytes"]
    glb_bytes = cached_result["glb_bytes"]
    topo = cached_result["topo"]
    feature_graph = cached_result["feature_graph"]
    regression_diff = _diff_topology(before_topo, topo, expected_parts=expected_parts)

    _write_cad_artifacts(
        pkg_path=pkg_path,
        step_bytes=step_bytes,
        stl_bytes=stl_bytes or b"",
        topology_map=topo,
        feature_graph=feature_graph,
        generated_code=new_source,
        glb_bytes=glb_bytes,
    )
    _clear_revalidation_status(pkg_path)

    try:
        from .main import save_project as _save_project, now_iso as _now_iso
        project["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
        project["updated_at"] = _now_iso()
        _save_project(settings, project)
    except Exception:
        pass
    _publish_preview_to_viewer(settings, project_id, project, glb_bytes, stl_bytes)

    response_detail = _normalize_response_detail(response_detail)
    # mesh_meta was already extracted from topo by _execute_build123d_cached.
    mesh_meta = cached_result.get("mesh_meta")
    thumb = None
    if _should_render_thumbnail(thumbnail, response_detail):
        thumb = render_mesh_thumbnail(
            stl_bytes or b"",
            face_colors=_build_face_colors_from_mesh_meta(mesh_meta),
            reference_image_bytes=ref_bytes,
        )
    solid = next((e for e in topo.get("entities", []) if e.get("type") == "solid"), None)
    named_parts = _named_parts_from_feature_graph(feature_graph)
    # geometry_report_full already computed by _execute_build123d_cached.
    geometry_report_full = cached_result.get("geometry_report") or _compute_geometry_report(topo)

    result = {
        "status": "ok",
        "schema_version": "0.1",
        "project_id": project_id,
        "response_detail": response_detail,
        "action": action,
        "label": label,
        "named_parts": named_parts,
        "topology_summary": {
            "face_count": sum(1 for e in topo.get("entities", []) if e.get("type") == "face"),
            "feature_count": len(feature_graph.get("features", [])),
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": _slim_feature_graph_for_response(feature_graph),
        "geometry_report": _geometry_report_for_response(geometry_report_full, response_detail),
        "geometry_report_summary": _geometry_report_summary(geometry_report_full),
        "regression_diff": regression_diff,
        "written_artifacts": [
            "geometry/generated.step",
            "geometry/preview.stl",
            "geometry/topology_map.json",
            "graph/feature_graph.json",
            "geometry/source.py",
        ] + (["geometry/preview.glb"] if glb_bytes else []),
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if glb_bytes else "stl",
        "thumbnail_png_base64": thumb,
    }
    if not thumb:
        result.pop("thumbnail_png_base64", None)
    return result


def _read_source_and_state(
    settings: Any, project_id: str,
) -> tuple[dict[str, Any], Path, str, dict[str, Any], bytes | None] | dict[str, Any]:
    """Resolve project + package and read source.py / topology / reference image.
    Returns (project, pkg_path, source, before_topo, ref_bytes) or an error dict."""
    from .project_io import get_project, resolve_project_path

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}
    pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg_path is None or not pkg_path.exists():
        return {"status": "error", "code": "package_not_found", "message": ".aieng package not found — build a model first"}
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = zf.namelist()
            if "geometry/source.py" not in names:
                return {"status": "error", "code": "no_source", "message": "No geometry/source.py — generate a model first"}
            source = zf.read("geometry/source.py").decode("utf-8")
            ref_bytes = zf.read("geometry/reference.png") if "geometry/reference.png" in names else None
            before_topo = (
                json.loads(zf.read("geometry/topology_map.json").decode("utf-8"))
                if "geometry/topology_map.json" in names else {}
            )
    except Exception as exc:
        return {"status": "error", "code": "read_failed", "message": f"{exc}"}
    return project, pkg_path, source, before_topo, ref_bytes


def remove_build123d_part(
    settings: Any,
    project_id: str,
    label: str,
    timeout: int = 120,
    response_detail: str = "full",
    thumbnail: bool | None = None,
) -> dict[str, Any]:
    """Remove a named part from the model by its build123d ``.label``.

    Appends a filter step to source.py (keeping the script self-consistent) and
    re-executes. The regression diff lists the dropped part under ``removed``.
    """
    label = str(label or "").strip()
    if not label:
        return {"status": "error", "code": "missing_label", "message": "label is required"}

    state = _read_source_and_state(settings, project_id)
    if isinstance(state, dict):
        return state
    project, pkg_path, source, before_topo, ref_bytes = state

    if label not in _solids_by_name(before_topo):
        return {
            "status": "error",
            "code": "part_not_found",
            "message": f"No named part '{label}' in the current model.",
            "available_parts": sorted(_solids_by_name(before_topo)),
        }

    new_source = source + _REMOVE_PART_SNIPPET.format(label=label)
    return _rebuild_after_part_edit(
        settings, project_id, project, pkg_path, new_source, before_topo,
        action="remove_part", label=label, expected_parts={label},
        ref_bytes=ref_bytes, timeout=timeout,
        response_detail=response_detail,
        thumbnail=thumbnail,
    )


def replace_build123d_part(
    settings: Any,
    project_id: str,
    label: str,
    code: str,
    timeout: int = 120,
    response_detail: str = "full",
    thumbnail: bool | None = None,
) -> dict[str, Any]:
    """Replace a named part by its ``.label`` with caller-supplied build123d code.

    The replacement ``code`` must reassign ``result`` to the new part and set its
    ``.label`` (normally back to the same name). The old part is dropped and the
    new one combined in; everything else is preserved. The regression diff should
    show ``clean`` (only ``label`` changed) when the swap is well-scoped.
    """
    label = str(label or "").strip()
    code = _coerce_code(str(code or ""))
    if not label:
        return {"status": "error", "code": "missing_label", "message": "label is required"}
    if not code:
        return {"status": "error", "code": "missing_code", "message": "code (replacement build123d) is required"}
    if not re.search(r"\bresult\s*=", code):
        return {
            "status": "error",
            "code": "contract_violation",
            "message": "Replacement code must assign the new part to `result` (and set result.label).",
        }
    if _EXPORT_CALL_RE.search(code):
        return {"status": "error", "code": "contract_violation", "message": "Replacement code must not include export calls."}

    state = _read_source_and_state(settings, project_id)
    if isinstance(state, dict):
        return state
    project, pkg_path, source, before_topo, ref_bytes = state

    if label not in _solids_by_name(before_topo):
        return {
            "status": "error",
            "code": "part_not_found",
            "message": f"No named part '{label}' in the current model.",
            "available_parts": sorted(_solids_by_name(before_topo)),
        }

    new_source = (
        source
        + _REPLACE_PART_HEAD.format(label=label)
        + code
        + _REPLACE_PART_TAIL
    )
    # Both the old and new part carry `label`, so the diff's expected set is {label}.
    return _rebuild_after_part_edit(
        settings, project_id, project, pkg_path, new_source, before_topo,
        action="replace_part", label=label, expected_parts={label},
        ref_bytes=ref_bytes, timeout=timeout,
        response_detail=response_detail,
        thumbnail=thumbnail,
    )


def _write_cached_artifacts_to_package(
    package_path: Path,
    cached: "aieng.cache.geometry_cache.CachedGeometry",
) -> None:
    """Write cached geometry artifacts back into an .aieng package.

    Used by ``recompile_shape_ir_package`` on cache hit so the package stays
    consistent even when compilation is skipped.
    """
    import zipfile

    meta = cached.metadata
    # Re-write source.py if available
    source = meta.get("source")
    source_path = meta.get("source_path", "geometry/source.py")
    if source:
        _replace_member(package_path, source_path, source.encode("utf-8"))

    # Re-write binary artifacts
    step_bytes = meta.get("step_bytes")
    if step_bytes:
        _replace_member(package_path, "geometry/generated.step", step_bytes)
    stl_bytes = meta.get("stl_bytes")
    if stl_bytes:
        _replace_member(package_path, "geometry/preview.stl", stl_bytes)
    glb_bytes = meta.get("glb_bytes")
    if glb_bytes:
        _replace_member(package_path, "geometry/preview.glb", glb_bytes)

    # Re-write topology_map.json and feature_graph.json
    topo = cached.topology_map or meta.get("topology_map")
    if topo:
        _replace_member(
            package_path,
            "geometry/topology_map.json",
            (json.dumps(topo, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    fg = cached.feature_graph or meta.get("feature_graph")
    if fg:
        _replace_member(
            package_path,
            "graph/feature_graph.json",
            (json.dumps(fg, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )


def _cached_geometry_has_real_artifacts(
    cached: "aieng.cache.geometry_cache.CachedGeometry",
) -> bool:
    """Return whether a cache entry can replace geometry execution.

    ``compile_shape_ir`` also uses ``GeometryCache`` for source-only entries.
    Those entries may skip source generation, but they must never make
    ``recompile_shape_ir_package`` skip the runtime that produces real geometry.
    """
    meta = cached.metadata
    if not meta.get("source"):
        return False
    return any(
        bool(value)
        for value in (
            meta.get("step_bytes"),
            meta.get("stl_bytes"),
            meta.get("glb_bytes"),
            cached.step_path,
            cached.stl_path,
            cached.glb_path,
        )
    )
