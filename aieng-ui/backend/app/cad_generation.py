"""build123d text-to-CAD backend for aieng-ui.

Implements TextToCadBackend (from aieng.modeling.text_to_cad).
Calls Claude to generate build123d Python code, executes it in a
subprocess to produce a STEP file and topology_map.json, applies
heuristics to build feature_graph.json, then writes all artifacts
into the project's .aieng package.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import ensure_aieng_on_path

# ── build123d runner template ──────────────────────────────────────────────────
# Placeholder __AIENG_GENERATED_CODE__ is replaced (not .format()-substituted)
# so all { } inside this string are literal Python syntax.

_RUNNER_TEMPLATE = """\
import sys
import json
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
        data["surface_type"] = "other"
    return data


def _has_labeled_descendant(node):
    for c in (getattr(node, "children", None) or []):
        if (getattr(c, "label", "") or "") or _has_labeled_descendant(c):
            return True
    return False


def _collect_parts(shape):
    # Returns [(name_or_None, part_shape), ...]. A node carrying a build123d
    # `.label` becomes a named part (we don't descend into it). An UNLABELED
    # compound is split into its children only when a label exists somewhere below
    # — this recovers names nested by append mode (previous_result is itself a
    # Compound) while leaving unnamed unions (e.g. auto-wrapped ShapeLists) as a
    # single body, preserving prior behavior.
    out = []

    def _walk(node):
        label = (getattr(node, "label", "") or "")
        if label:
            out.append((label, node))
            return
        children = list(getattr(node, "children", None) or [])
        if children and _has_labeled_descendant(node):
            for c in children:
                _walk(c)
            return
        out.append((None, node))

    _walk(shape)
    return out


def _extract_topology(shape):
    entities = []
    face_counter = 0
    for pi, (name, part) in enumerate(_collect_parts(shape)):
        body_id = f"body_{pi + 1:03d}"
        body = {"id": body_id, "type": "solid", "bounding_box": _bbox_list(part.bounding_box())}
        if name:
            body["name"] = name
        entities.append(body)
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
_export("stl", result, out_stl)
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


def render_mesh_thumbnail(stl_bytes: bytes, size: int = 420) -> str | None:
    """Render an STL mesh to a base64-encoded PNG thumbnail (headless).

    Gives an agent driving CAD a visual feedback loop — it can see roughly what
    the geometry looks like instead of judging from face counts and a bounding box
    alone. Uses matplotlib's 3D toolkit (Agg backend) because trimesh's GL-based
    `save_image` requires pyglet/OpenGL, which is unavailable headless on Windows.

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
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        verts = np.asarray(triangles).reshape((-1, 3))

        # Simple Lambert shading so the form reads clearly (not photorealism).
        normals = np.asarray(normals, dtype=float)
        light = np.array([0.3, 0.4, 0.85])
        light = light / np.linalg.norm(light)
        intensity = np.clip(normals @ light, 0.18, 1.0)
        base_color = np.array([0.40, 0.55, 0.85])
        facecolors = np.clip(intensity[:, None] * base_color, 0.0, 1.0)

        fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
        ax = fig.add_subplot(111, projection="3d")
        coll = Poly3DCollection(
            triangles, facecolors=facecolors, edgecolors=(0, 0, 0, 0.10), linewidths=0.15
        )
        ax.add_collection3d(coll)

        mins = verts.min(axis=0)
        maxs = verts.max(axis=0)
        center = (mins + maxs) / 2
        span = float((maxs - mins).max()) / 2 or 1.0
        ax.set_xlim(center[0] - span, center[0] + span)
        ax.set_ylim(center[1] - span, center[1] + span)
        ax.set_zlim(center[2] - span, center[2] + span)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=25, azim=-50)
        ax.set_axis_off()
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return _render_mesh_thumbnail_basic(triangles, size)


def _topology_to_feature_graph(topo: dict[str, Any]) -> dict[str, Any]:
    """Heuristic: derive a feature_graph.json from extracted topology."""
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
        features.append({
            "id": f"feat_{body['id']}",
            "type": "named_part",
            "name": body["name"],
            "geometry_refs": {"body": body["id"], "faces": body_faces},
            "parameters": {},
            "intent": {"role": "named_component"},
        })

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

    return {"features": features}


def _named_parts_from_feature_graph(feature_graph: dict[str, Any]) -> list[str]:
    """Extract the ordered list of named-part labels from a feature graph."""
    return [
        f["name"]
        for f in (feature_graph or {}).get("features", [])
        if f.get("type") == "named_part" and f.get("name")
    ]


def _available_named_parts_from_topology(topology_map: dict[str, Any]) -> list[str]:
    """Return all named solid/body labels in topology order."""
    return [
        str(entity["name"])
        for entity in (topology_map or {}).get("entities", [])
        if entity.get("type") == "solid" and entity.get("name")
    ]


# ── Claude API call ────────────────────────────────────────────────────────────

def call_claude_for_build123d_code(
    description: str,
    hints: dict[str, Any] | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """Call Claude to generate build123d Python code. Returns the code string."""
    import anthropic

    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not resolved_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not set — cannot call Claude for CAD generation",
        )

    ensure_aieng_on_path()
    from aieng.modeling.text_to_cad import (
        BUILD123D_SYSTEM_PROMPT,
        TextToCadHints,
        build_build123d_user_prompt,
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

    resolved_model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    resolved_base_url = os.environ.get("ANTHROPIC_BASE_URL")
    client = anthropic.Anthropic(
        api_key=resolved_key,
        **({"base_url": resolved_base_url} if resolved_base_url else {}),
    )
    response = client.messages.create(
        model=resolved_model,
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": BUILD123D_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
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

    pkg_path.parent.mkdir(parents=True, exist_ok=True)

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
        )

        warnings: list[str] = []
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                step_bytes, stl_bytes, glb_bytes, topo = _execute_build123d_code(
                    generated_code, timeout=timeout
                )
                feature_graph = _topology_to_feature_graph(topo)
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

    project = get_project(settings, project_id)

    backend = Build123dBackend(settings)
    if not backend.can_generate():
        raise HTTPException(
            status_code=503,
            detail="build123d is not installed — cannot generate CAD geometry",
        )

    result = backend.generate(description, hints=hints, timeout=timeout, api_key=api_key)

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
    if mode == "append":
        existing_pkg = project.get("aieng_file")
        pkg = resolve_project_path(settings, project_id, existing_pkg) if existing_pkg else None
        prior_source: str | None = None
        if pkg is not None and pkg.exists():
            try:
                with zipfile.ZipFile(pkg, "r") as zf:
                    names = zf.namelist()
                    if "geometry/source.py" in names:
                        prior_source = zf.read("geometry/source.py").decode("utf-8")
                    if "graph/feature_graph.json" in names:
                        prior_fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                        prior_named_parts = _named_parts_from_feature_graph(prior_fg)
            except Exception:
                prior_source = None
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
        code = (
            prior_source
            + "\n\n# --- aieng append: previous step exposed as `previous_result` ---\n"
            + "previous_result = result.part if hasattr(result, 'part') else result\n"
            + "# --- new code (must reassign `result`) ---\n"
            + code
        )

    # Drain the streaming executor; forward heartbeats to on_progress so a
    # subscribed UI sees the build advance in real time.
    last_error: str | None = None
    result_evt: dict[str, Any] | None = None
    for evt in _execute_build123d_code_streaming(code, timeout=timeout):
        kind = evt.get("kind")
        if kind == "heartbeat":
            _emit({"phase": "building", "elapsed_s": evt.get("elapsed_s", 0)})
        elif kind == "error":
            last_error = str(evt.get("error") or "build123d execution failed")
        elif kind == "result":
            result_evt = evt

    if result_evt is None:
        return {
            "status": "error",
            "code": "execution_failed",
            "message": last_error or "build123d produced no result",
        }

    step_bytes = result_evt["step_bytes"]
    stl_bytes = result_evt["stl_bytes"]
    glb_bytes = result_evt["glb_bytes"]
    topo = result_evt["topo"]
    feature_graph = _topology_to_feature_graph(topo)
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
            generated_code=code,
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
            project["updated_at"] = _now_iso()
            _save_project2(settings, project)
        except Exception:
            pass

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
        "named_parts": named_parts,
        "parts_added": parts_added,
        "topology_summary": {
            "face_count": face_count,
            "feature_count": feature_count,
            "bounding_box": solid.get("bounding_box") if solid else None,
        },
        "feature_graph": feature_graph,
        "written_artifacts": written,
        "write_files": write_files,
        "preview_url": f"/api/projects/{project_id}/cad-preview",
        "preview_format": "glb" if glb_bytes else "stl",
    }

    # Visual feedback loop: render a thumbnail so an agent can see the geometry,
    # not just face/bbox numbers. Opt out with {"thumbnail": false}.
    if payload.get("thumbnail", True):
        thumb = render_mesh_thumbnail(stl_bytes or b"")
        if thumb:
            result["thumbnail_png_base64"] = thumb

    return result


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
            description=description, hints=hints, api_key=api_key,
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
    feature_graph = _topology_to_feature_graph(topo)
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
            "feature_graph": feature_graph,
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
) -> str:
    """Call Claude to refine existing build123d code based on engineer feedback."""
    import anthropic

    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not resolved_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not set — cannot call Claude for CAD refinement",
        )

    ensure_aieng_on_path()
    from aieng.modeling.text_to_cad import BUILD123D_SYSTEM_PROMPT, build_build123d_refine_prompt

    user_prompt = build_build123d_refine_prompt(existing_code, feedback)

    resolved_model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    resolved_base_url = os.environ.get("ANTHROPIC_BASE_URL")
    client = anthropic.Anthropic(
        api_key=resolved_key,
        **({"base_url": resolved_base_url} if resolved_base_url else {}),
    )
    response = client.messages.create(
        model=resolved_model,
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": BUILD123D_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
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

    refined_code = call_claude_for_build123d_refinement(existing_code, feedback, api_key=api_key)

    try:
        step_bytes, stl_bytes, glb_bytes, topo = _execute_build123d_code(refined_code, timeout=timeout)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Refined CAD execution failed: {exc}")

    feature_graph = _topology_to_feature_graph(topo)
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
        "feature_graph": feature_graph,
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
                named_parts = [
                    f["name"]
                    for f in fg.get("features", [])
                    if f.get("type") == "named_part" and f.get("name")
                ]
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
