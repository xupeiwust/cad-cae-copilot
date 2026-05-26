"""Stress heatmap GLB generator for CalculiX simulation results.

Reads simulation/mesh.inp and simulation/result.frd from an .aieng package
and returns a binary GLB file with per-node Von Mises stress coloring
(blue→cyan→green→yellow→red thermal colormap).
"""
from __future__ import annotations

import json
import math
import struct
from typing import Any


# ── FRD parsing ───────────────────────────────────────────────────────────────

def _parse_frd_vm_stress(frd_bytes: bytes) -> dict[int, float]:
    """Extract per-node Von Mises stress from a CalculiX FRD byte string.

    Uses fixed-width 12-char column parsing to handle consecutive negative
    values that lack separating spaces (e.g. '-1.23E-04-5.67E-04').
    Falls back to displacement magnitude if no STRESS block is found.
    Returns {node_id: value_mpa} or empty dict if no usable data.
    """
    lines = frd_bytes.decode("ascii", errors="replace").splitlines()

    best: dict[int, float] = {}
    in_block = False
    block_type = ""
    n_components = 0
    node_values: dict[int, list[float]] = {}

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("-4"):
            # Save previous block if it was stress
            if block_type == "STRESS" and node_values:
                best = _vm_from_components(node_values)
            in_block = True
            parts = stripped.split()
            block_type = parts[1].upper() if len(parts) > 1 else ""
            n_components = 0
            node_values = {}
            continue

        if not in_block:
            continue

        if stripped.startswith("-5"):
            n_components += 1
            continue

        if stripped.startswith("-3"):
            if block_type == "STRESS" and node_values:
                best = _vm_from_components(node_values)
            in_block = False
            continue

        if stripped.startswith("-1") and n_components > 0:
            # Locate "-1" in the original line to find field start
            idx = line.find("-1")
            if idx < 0:
                continue
            field_start = idx + 2
            try:
                node_id = int(line[field_start: field_start + 12])
                values: list[float] = []
                for k in range(n_components):
                    s = field_start + 12 + k * 12
                    e = s + 12
                    if e <= len(line):
                        values.append(float(line[s:e]))
                if values:
                    node_values[node_id] = values
            except (ValueError, IndexError):
                pass

    if in_block and block_type == "STRESS" and node_values:
        best = _vm_from_components(node_values)

    # If we got stress data return it; otherwise try the last displacement block
    if best:
        return best

    # Fallback: try DISP block (return displacement magnitude)
    in_block = False
    block_type = ""
    n_components = 0
    node_values = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-4"):
            in_block = True
            parts = stripped.split()
            block_type = parts[1].upper() if len(parts) > 1 else ""
            n_components = 0
            node_values = {}
            continue
        if not in_block:
            continue
        if stripped.startswith("-5"):
            n_components += 1
            continue
        if stripped.startswith("-3"):
            in_block = False
            continue
        if stripped.startswith("-1") and block_type == "DISP" and n_components >= 3:
            idx = line.find("-1")
            if idx < 0:
                continue
            field_start = idx + 2
            try:
                node_id = int(line[field_start: field_start + 12])
                values = []
                for k in range(3):  # D1, D2, D3 only
                    s = field_start + 12 + k * 12
                    e = s + 12
                    if e <= len(line):
                        values.append(float(line[s:e]))
                if len(values) == 3:
                    node_values[node_id] = values
            except (ValueError, IndexError):
                pass

    if node_values:
        return {nid: math.sqrt(sum(v * v for v in comps)) for nid, comps in node_values.items()}

    return {}


def _vm_from_components(node_values: dict[int, list[float]]) -> dict[int, float]:
    """Compute Von Mises stress from [SXX, SYY, SZZ, SXY, SXZ, SYZ] per node."""
    result: dict[int, float] = {}
    for nid, comps in node_values.items():
        if len(comps) < 6:
            continue
        sxx, syy, szz, sxy, sxz, syz = comps[:6]
        vm = math.sqrt(max(0.0, 0.5 * (
            (sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
            + 6.0 * (sxy ** 2 + sxz ** 2 + syz ** 2)
        )))
        result[nid] = vm
    return result


# ── INP mesh parsing ──────────────────────────────────────────────────────────

def _parse_inp_mesh(
    inp_text: str,
) -> tuple[dict[int, tuple[float, float, float]], list[tuple[int, int, int, int]]]:
    """Parse node coordinates and C3D4/C3D10 elements from a Gmsh .inp file.

    Returns:
        nodes:  {node_id: (x, y, z)}
        tets:   list of (n1, n2, n3, n4) — corner nodes only, 1-indexed
    """
    nodes: dict[int, tuple[float, float, float]] = {}
    tets: list[tuple[int, int, int, int]] = []

    in_node = False
    in_tet = False

    for raw_line in inp_text.splitlines():
        line = raw_line.strip()
        upper = line.upper()

        if upper.startswith("*NODE"):
            in_node = True
            in_tet = False
            continue

        if upper.startswith("*ELEMENT"):
            in_node = False
            in_tet = "C3D4" in upper or "C3D10" in upper
            continue

        if line.startswith("*"):
            in_node = False
            in_tet = False
            continue

        if not line or line.startswith("**"):
            continue

        if in_node:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                try:
                    nid = int(parts[0])
                    nodes[nid] = (float(parts[1]), float(parts[2]), float(parts[3]))
                except ValueError:
                    pass

        elif in_tet:
            parts = [p.strip() for p in line.split(",")]
            # Element line: elem_id, n1, n2, n3, n4[, midnodes...]
            if len(parts) >= 5:
                try:
                    tets.append((int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])))
                except ValueError:
                    pass

    return nodes, tets


def _extract_surface_triangles(
    tets: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int]]:
    """Return triangular faces that appear in exactly one tetrahedron (surface faces)."""
    from collections import Counter

    face_count: Counter[tuple[int, int, int]] = Counter()

    for n1, n2, n3, n4 in tets:
        for face in (
            tuple(sorted((n1, n2, n3))),
            tuple(sorted((n1, n2, n4))),
            tuple(sorted((n1, n3, n4))),
            tuple(sorted((n2, n3, n4))),
        ):
            face_count[face] += 1  # type: ignore[arg-type]

    return [face for face, cnt in face_count.items() if cnt == 1]  # type: ignore[return-value]


# ── Colormap ──────────────────────────────────────────────────────────────────

def _thermal_color(t: float) -> tuple[float, float, float]:
    """Map t ∈ [0, 1] to blue→cyan→green→yellow→red."""
    t = max(0.0, min(1.0, t))
    if t < 0.25:
        s = t / 0.25
        return (0.0, s, 1.0)
    if t < 0.5:
        s = (t - 0.25) / 0.25
        return (0.0, 1.0, 1.0 - s)
    if t < 0.75:
        s = (t - 0.5) / 0.25
        return (s, 1.0, 0.0)
    s = (t - 0.75) / 0.25
    return (1.0, 1.0 - s, 0.0)


# ── GLB builder ───────────────────────────────────────────────────────────────

def _build_glb(
    positions: list[tuple[float, float, float]],
    colors: list[tuple[float, float, float]],
    indices: list[int],
) -> bytes:
    """Build a binary GLB (glTF 2.0) file with POSITION and COLOR_0 attributes."""
    n_verts = len(positions)
    n_idx = len(indices)

    # Binary buffer: POSITION (float32 xyz) | COLOR_0 (float32 rgba) | INDICES (uint32)
    pos_bytes = struct.pack(f"{n_verts * 3}f", *[c for p in positions for c in p])
    col_bytes = struct.pack(f"{n_verts * 4}f", *[c for rgb in colors for c in (*rgb, 1.0)])
    idx_bytes = struct.pack(f"{n_idx}I", *indices)

    pos_len = len(pos_bytes)  # already multiple of 4
    col_len = len(col_bytes)
    idx_len = len(idx_bytes)
    bin_data = pos_bytes + col_bytes + idx_bytes

    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]

    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "aieng-stress-heatmap"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "COLOR_0": 1}, "indices": 2, "mode": 4}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": n_verts, "type": "VEC3",
             "min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]},
            {"bufferView": 1, "componentType": 5126, "count": n_verts, "type": "VEC4"},
            {"bufferView": 2, "componentType": 5125, "count": n_idx, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0,                    "byteLength": pos_len, "target": 34962},
            {"buffer": 0, "byteOffset": pos_len,              "byteLength": col_len, "target": 34962},
            {"buffer": 0, "byteOffset": pos_len + col_len,    "byteLength": idx_len, "target": 34963},
        ],
        "buffers": [{"byteLength": len(bin_data)}],
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    # Pad JSON chunk to 4-byte boundary with spaces (per GLB spec)
    rem = len(json_bytes) % 4
    if rem:
        json_bytes += b" " * (4 - rem)

    json_chunk = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes   # JSON
    bin_chunk  = struct.pack("<II", len(bin_data),   0x004E4942) + bin_data      # BIN\0
    total_len  = 12 + len(json_chunk) + len(bin_chunk)
    header     = struct.pack("<III", 0x46546C67, 2, total_len)                   # glTF magic

    return header + json_chunk + bin_chunk


# ── Public API ────────────────────────────────────────────────────────────────

def generate_heatmap_glb(
    inp_text: str, frd_bytes: bytes
) -> tuple[bytes, float, float] | None:
    """Build a colored surface GLB from CalculiX mesh and FRD results.

    Returns (glb_bytes, min_vm_mpa, max_vm_mpa) on success, None if insufficient
    data (no stress values found or mesh has no recognisable tetrahedra).
    """
    vm_stress = _parse_frd_vm_stress(frd_bytes)
    if not vm_stress:
        return None

    nodes, tets = _parse_inp_mesh(inp_text)
    if not nodes or not tets:
        return None

    surface_faces = _extract_surface_triangles(tets)
    if not surface_faces:
        return None

    surf_node_ids = sorted({n for face in surface_faces for n in face})
    node_index = {nid: idx for idx, nid in enumerate(surf_node_ids)}

    stress_values = [vm_stress.get(n, 0.0) for n in surf_node_ids]
    min_vm = min(stress_values)
    max_vm = max(stress_values)
    stress_range = max_vm - min_vm if max_vm > min_vm else 1.0

    positions: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float]] = []
    for nid, vm in zip(surf_node_ids, stress_values):
        positions.append(nodes.get(nid, (0.0, 0.0, 0.0)))
        colors.append(_thermal_color((vm - min_vm) / stress_range))

    flat_indices = [node_index[n] for face in surface_faces for n in face]

    return _build_glb(positions, colors, flat_indices), min_vm, max_vm
