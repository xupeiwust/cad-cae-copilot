"""Tests for stress_heatmap.py — GLB heatmap generation pipeline."""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.stress_heatmap import (
    _extract_surface_triangles,
    _parse_frd_vm_stress,
    _parse_inp_mesh,
    _thermal_color,
    generate_heatmap_glb,
)


# ── _thermal_color ─────────────────────────────────────────────────────────────

def test_thermal_color_blue_at_zero():
    r, g, b = _thermal_color(0.0)
    assert r == 0.0 and b == 1.0


def test_thermal_color_red_at_one():
    r, g, b = _thermal_color(1.0)
    assert r == 1.0 and b == 0.0


def test_thermal_color_clamps():
    assert _thermal_color(-1.0) == _thermal_color(0.0)
    assert _thermal_color(2.0) == _thermal_color(1.0)


def test_thermal_color_midpoint_green():
    r, g, b = _thermal_color(0.5)
    assert g == 1.0
    assert r < 0.1
    assert b < 0.1


# ── _parse_frd_vm_stress ───────────────────────────────────────────────────────

# CalculiX FRD uses i12 for node IDs and e12.5 for values (12-char fixed-width fields).
# Node ID 1 → "           1" (11 spaces + "1"), value 100.0 → " 1.00000E+02".
_MINIMAL_FRD_STRESS = b"""    -4 STRESS      6    1
    -5  SXX         1    4    1    1
    -5  SYY         1    4    2    2
    -5  SZZ         1    4    3    3
    -5  SXY         1    4    1    2
    -5  SXZ         1    4    1    3
    -5  SYZ         1    4    2    3
    -1           1 1.00000E+02 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
    -1           2 0.00000E+00 1.00000E+02 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00
   -3
"""


def test_frd_stress_parses_two_nodes():
    result = _parse_frd_vm_stress(_MINIMAL_FRD_STRESS)
    assert len(result) == 2


def test_frd_stress_uniaxial_von_mises():
    # SXX=100, all others 0: vm = sqrt(0.5*(100^2 + 0^2 + 100^2)) = 100
    result = _parse_frd_vm_stress(_MINIMAL_FRD_STRESS)
    assert abs(result[1] - 100.0) < 1e-3


def test_frd_stress_empty_bytes_returns_empty():
    assert _parse_frd_vm_stress(b"") == {}


def test_frd_stress_no_stress_block_returns_empty():
    frd = b"    -4 DISP        4    1\n    -5  D1\n   -3\n"
    # No STRESS block, no DISP data either
    assert _parse_frd_vm_stress(frd) == {}


def test_frd_stress_fallback_to_displacement():
    frd = b"""    -4 DISP        4    1
    -5  D1          1    2    1    0
    -5  D2          1    2    2    0
    -5  D3          1    2    3    0
    -5  ALL         1    2    0    0    1ALL
    -1           1 3.00000E+00 4.00000E+00 0.00000E+00 5.00000E+00
   -3
"""
    result = _parse_frd_vm_stress(frd)
    assert 1 in result
    # magnitude of (3, 4, 0) = 5.0
    assert abs(result[1] - 5.0) < 1e-3


def test_frd_stress_negative_values_no_spaces():
    # Stress data with consecutive negatives (no space between fields)
    # SXX=-50, SYY=-50, SZZ=0, rest 0 → vm = sqrt(0.5*(0+50^2+50^2)) = 50
    sxx = "-5.00000E+01"
    syy = "-5.00000E+01"
    szz = " 0.00000E+00"
    rest = " 0.00000E+00" * 3
    # Node ID must be 12-char right-aligned (CalculiX i12 format)
    node_line = f"    -1           1{sxx}{syy}{szz}{rest}\n".encode()
    frd = b"""    -4 STRESS      6    1
    -5  SXX
    -5  SYY
    -5  SZZ
    -5  SXY
    -5  SXZ
    -5  SYZ
""" + node_line + b"   -3\n"
    result = _parse_frd_vm_stress(frd)
    assert 1 in result
    expected = math.sqrt(0.5 * (0 + 50 ** 2 + 50 ** 2))
    assert abs(result[1] - expected) < 1e-2


# ── _parse_inp_mesh ────────────────────────────────────────────────────────────

_SIMPLE_TET_INP = """\
*NODE
  1, 0.0, 0.0, 0.0
  2, 1.0, 0.0, 0.0
  3, 0.0, 1.0, 0.0
  4, 0.0, 0.0, 1.0
*ELEMENT, TYPE=C3D4, ELSET=EALL
  1, 1, 2, 3, 4
*NSET, NSET=EALL
  1
"""


def test_inp_mesh_nodes_parsed():
    nodes, tets = _parse_inp_mesh(_SIMPLE_TET_INP)
    assert len(nodes) == 4
    assert nodes[1] == (0.0, 0.0, 0.0)
    assert nodes[4] == (0.0, 0.0, 1.0)


def test_inp_mesh_tet_parsed():
    nodes, tets = _parse_inp_mesh(_SIMPLE_TET_INP)
    assert len(tets) == 1
    assert tets[0] == (1, 2, 3, 4)


def test_inp_mesh_empty_returns_empty():
    nodes, tets = _parse_inp_mesh("")
    assert nodes == {}
    assert tets == []


def test_inp_mesh_c3d10_first_four_nodes():
    inp = """\
*NODE
  1, 0.0, 0.0, 0.0
  2, 1.0, 0.0, 0.0
  3, 0.0, 1.0, 0.0
  4, 0.0, 0.0, 1.0
  5, 0.5, 0.0, 0.0
  6, 0.5, 0.5, 0.0
  7, 0.0, 0.5, 0.0
  8, 0.0, 0.0, 0.5
  9, 0.5, 0.0, 0.5
 10, 0.0, 0.5, 0.5
*ELEMENT, TYPE=C3D10, ELSET=EALL
  1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
"""
    nodes, tets = _parse_inp_mesh(inp)
    assert tets[0] == (1, 2, 3, 4)


# ── _extract_surface_triangles ─────────────────────────────────────────────────

def test_single_tet_has_four_surface_faces():
    tets = [(1, 2, 3, 4)]
    faces = _extract_surface_triangles(tets)
    assert len(faces) == 4


def test_two_adjacent_tets_share_internal_face():
    # Two tets sharing face (1,2,3): face (1,2,3) appears twice → internal
    tets = [(1, 2, 3, 4), (1, 2, 3, 5)]
    faces = _extract_surface_triangles(tets)
    # Each tet has 4 faces, shared face removed: 4+4-2 = 6 surface faces
    assert len(faces) == 6
    # The shared face must not be in the surface
    shared = tuple(sorted((1, 2, 3)))
    assert shared not in faces


def test_empty_tets_returns_empty():
    assert _extract_surface_triangles([]) == []


# ── generate_heatmap_glb ───────────────────────────────────────────────────────

def _make_simple_inputs():
    """Build minimal FRD + INP byte strings for a single-tet mesh."""
    inp = _SIMPLE_TET_INP
    # FRD with uniaxial stress on all 4 nodes (different magnitudes for colormap)
    stress_lines = [
        b"    -4 STRESS      6    1\n",
        b"    -5  SXX\n    -5  SYY\n    -5  SZZ\n    -5  SXY\n    -5  SXZ\n    -5  SYZ\n",
    ]
    for nid, sxx in [(1, 100.0), (2, 200.0), (3, 150.0), (4, 50.0)]:
        line = f"    -1{nid:12d}{sxx:12.5E}" + " 0.00000E+00" * 5 + "\n"
        stress_lines.append(line.encode())
    stress_lines.append(b"   -3\n")
    frd = b"".join(stress_lines)
    return inp, frd


def test_generate_heatmap_returns_tuple():
    inp, frd = _make_simple_inputs()
    result = generate_heatmap_glb(inp, frd)
    assert result is not None
    glb, min_mpa, max_mpa = result
    assert isinstance(glb, bytes)
    assert isinstance(min_mpa, float)
    assert isinstance(max_mpa, float)


def test_generate_heatmap_stress_range():
    inp, frd = _make_simple_inputs()
    _, min_mpa, max_mpa = generate_heatmap_glb(inp, frd)
    # Inputs have SXX values 50, 100, 150, 200 → vm range is 50–200 (approx)
    assert min_mpa < max_mpa
    assert min_mpa >= 0.0


def test_generate_heatmap_valid_glb_header():
    inp, frd = _make_simple_inputs()
    glb, _, _ = generate_heatmap_glb(inp, frd)
    magic, version, total = struct.unpack_from("<III", glb, 0)
    assert magic == 0x46546C67  # 'glTF'
    assert version == 2
    assert total == len(glb)


def test_generate_heatmap_none_on_empty_frd():
    assert generate_heatmap_glb(_SIMPLE_TET_INP, b"") is None


def test_generate_heatmap_none_on_empty_inp():
    _, frd = _make_simple_inputs()
    assert generate_heatmap_glb("", frd) is None
