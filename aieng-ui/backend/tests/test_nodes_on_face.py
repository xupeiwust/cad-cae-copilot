"""Tests for the improved _nodes_on_face in simulation_runner.py.

Covers:
- Axis-aligned planes via normal vector (top/bottom/side faces)
- Non-axis-aligned planes (45° chamfer, arbitrary incline)
- Cylinder path (unchanged)
- Fallback to thin-dimension when no normal stored
- Edge cases (empty bbox, zero normal magnitude)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.simulation_runner import _nodes_on_face


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nodes_dict(*coords):
    """Build {node_id: (x, y, z)} from positional (x, y, z) tuples."""
    return {i: c for i, c in enumerate(coords)}


# ── Axis-aligned faces via normal vector ──────────────────────────────────────

def test_top_face_normal_up():
    """Normal [0,0,1] — top face at z=10."""
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, 9.9, 10.0, 10.0, 10.1],
        "normal": [0.0, 0.0, 1.0],
        "center": [5.0, 5.0, 10.0],
    }
    nodes = _nodes_dict(
        (2.0, 3.0, 10.0),   # on top face ✓
        (5.0, 5.0, 10.0),   # on top face ✓
        (2.0, 3.0,  5.0),   # inside body ✗
        (2.0, 3.0,  0.0),   # bottom face ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 in result
    assert 2 not in result
    assert 3 not in result


def test_bottom_face_normal_down():
    """Normal [0,0,-1] — bottom face at z=0."""
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, -0.1, 10.0, 10.0, 0.1],
        "normal": [0.0, 0.0, -1.0],
        "center": [5.0, 5.0, 0.0],
    }
    nodes = _nodes_dict(
        (5.0, 5.0, 0.0),    # on bottom face ✓
        (5.0, 5.0, 5.0),    # mid-body ✗
        (5.0, 5.0, 10.0),   # top face ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 not in result
    assert 2 not in result


def test_side_face_normal_x():
    """Normal [1,0,0] — right face at x=10."""
    face = {
        "surface_type": "plane",
        "bounding_box": [9.9, 0.0, 0.0, 10.1, 5.0, 10.0],
        "normal": [1.0, 0.0, 0.0],
        "center": [10.0, 2.5, 5.0],
    }
    nodes = _nodes_dict(
        (10.0, 1.0, 2.0),   # on right face ✓
        (10.0, 4.0, 8.0),   # on right face ✓
        (0.0,  1.0, 2.0),   # left face ✗
        (5.0,  1.0, 2.0),   # interior ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 in result
    assert 2 not in result
    assert 3 not in result


# ── Non-axis-aligned faces (new capability) ───────────────────────────────────

def test_45_degree_chamfer():
    """45° chamfer: normal [1/√2, 0, 1/√2].

    Plane passes through point (5, 0, 5) with normal [0.707, 0, 0.707].
    Plane equation: 0.707*x + 0.707*z = 7.07  →  x + z = 10
    Nodes with x + z = 10 lie on the chamfer.
    """
    s = 1.0 / math.sqrt(2)
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, 0.0, 10.0, 5.0, 10.0],
        "normal": [s, 0.0, s],
        "center": [5.0, 2.5, 5.0],  # 5 + 5 = 10 ✓ lies on plane
    }
    nodes = _nodes_dict(
        (3.0, 1.0, 7.0),    # 3+7=10 — on chamfer ✓
        (8.0, 2.0, 2.0),    # 8+2=10 — on chamfer ✓
        (0.0, 1.0, 0.0),    # 0+0=0 ≠ 10 — not on chamfer ✗
        (5.0, 2.0, 5.0),    # 5+5=10 — on chamfer ✓
        (5.0, 2.0, 2.0),    # 5+2=7 ≠ 10 — interior ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result, "node (3,1,7) should be on 45° chamfer"
    assert 1 in result, "node (8,2,2) should be on 45° chamfer"
    assert 2 not in result, "node (0,1,0) should NOT be on chamfer"
    assert 3 in result, "node (5,2,5) should be on 45° chamfer"
    assert 4 not in result, "node (5,2,2) should NOT be on chamfer"


def test_inclined_face_30_degrees():
    """Inclined face at 30° from vertical: normal [0.5, 0, 0.866].

    Plane passes through (5, 0, 5): d = 0.5*5 + 0.866*5 = 6.83
    """
    cos30 = math.cos(math.radians(30))
    sin30 = math.sin(math.radians(30))
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, 0.0, 10.0, 5.0, 10.0],
        "normal": [sin30, 0.0, cos30],
        "center": [5.0, 2.5, 5.0],
    }
    d = sin30 * 5.0 + cos30 * 5.0

    on_face = []
    off_face = []
    for nid, (x, y, z) in {
        0: (3.0, 1.0, (d - sin30 * 3.0) / cos30),  # on plane by construction
        1: (0.0, 0.0, 0.0),                          # far from plane
    }.items():
        plane_dist = abs(sin30 * x + cos30 * z - d)
        if plane_dist < 0.1:
            on_face.append(nid)
        else:
            off_face.append(nid)

    # Verify our test vectors are correct
    assert 0 in on_face
    assert 1 in off_face

    # Now test via _nodes_on_face
    result = set(_nodes_on_face({
        0: (3.0, 1.0, (d - sin30 * 3.0) / cos30),
        1: (0.0, 0.0, 0.0),
    }, face))
    assert 0 in result
    assert 1 not in result


def test_non_unit_normal_is_normalized():
    """A stored normal with magnitude != 1 must still work (function normalises it)."""
    face = {
        "surface_type": "plane",
        "bounding_box": [-0.1, -0.1, 9.9, 10.1, 10.1, 10.1],
        "normal": [0.0, 0.0, 5.0],   # magnitude = 5, not 1
        "center": [5.0, 5.0, 10.0],
    }
    nodes = _nodes_dict(
        (3.0, 4.0, 10.0),  # on top face ✓
        (3.0, 4.0,  5.0),  # mid ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 not in result


# ── Cylinder (unchanged behaviour) ───────────────────────────────────────────

def test_cylinder_nodes():
    """Cylindrical hole: radius 2, centred at (5,5), z 0..10."""
    face = {
        "surface_type": "cylinder",
        "bounding_box": [3.0, 3.0, 0.0, 7.0, 7.0, 10.0],
        "radius": 2.0,
    }
    nodes = _nodes_dict(
        (7.0, 5.0, 5.0),   # on cylinder surface (r=2) ✓
        (3.0, 5.0, 5.0),   # on cylinder surface ✓
        (5.0, 5.0, 5.0),   # centre — inside hole ✗
        (5.0, 5.0, 0.0),   # on axis, bottom — inside hole ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 in result
    assert 2 not in result


# ── Fallback: thin-dimension (no normal stored) ───────────────────────────────

def test_fallback_no_normal():
    """When no normal is stored, the thin-dimension heuristic must still work."""
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, 9.9, 10.0, 10.0, 10.1],
        # no "normal" key
    }
    nodes = _nodes_dict(
        (2.0, 3.0, 10.0),  # on top face ✓
        (2.0, 3.0,  5.0),  # mid-body ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 not in result


def test_fallback_none_normal():
    """Explicit None for normal should trigger fallback."""
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, 9.9, 10.0, 10.0, 10.1],
        "normal": None,
    }
    nodes = _nodes_dict(
        (2.0, 3.0, 10.0),  # on top face ✓
        (2.0, 3.0,  5.0),  # mid-body ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 not in result


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_bbox():
    assert _nodes_on_face({0: (1.0, 2.0, 3.0)}, {"bounding_box": []}) == []


def test_short_bbox():
    assert _nodes_on_face({0: (1.0, 2.0, 3.0)}, {"bounding_box": [0, 0, 0]}) == []


def test_zero_normal_falls_back_to_thin_dim():
    """Zero normal vector magnitude should not crash — falls through to fallback."""
    face = {
        "surface_type": "plane",
        "bounding_box": [0.0, 0.0, 9.9, 10.0, 10.0, 10.1],
        "normal": [0.0, 0.0, 0.0],
    }
    nodes = _nodes_dict((5.0, 5.0, 10.0))
    # Should not raise regardless of which path it takes
    result = _nodes_on_face(nodes, face)
    assert isinstance(result, list)


def test_bbox_filter_excludes_distant_nodes():
    """Normal-vector path must still reject nodes outside the face's AABB."""
    s = 1.0 / math.sqrt(2)
    face = {
        "surface_type": "plane",
        # Small chamfer: x ∈ [8,10], z ∈ [8,10]
        "bounding_box": [8.0, 0.0, 8.0, 10.0, 5.0, 10.0],
        "normal": [s, 0.0, s],
        "center": [9.0, 2.5, 9.0],
    }
    # A node on the infinite plane x+z=18 but far outside the face's AABB
    nodes = _nodes_dict(
        (9.0, 1.0, 9.0),    # inside AABB and on plane ✓
        (0.0, 1.0, 18.0),   # on plane but outside AABB ✗  (x=0 < 8)
    )
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result
    assert 1 not in result


# ── Free-form faces (loft/sweep/sphere) — proxy normal + wider tolerance ──────

def test_freeform_face_with_proxy_normal_selects_band():
    """A free-form face carries a proxy normal + freeform flag; the wider tol
    captures a usable band of surface nodes near the tangent plane instead of
    falling through to the (broken-for-curved) thin-bbox heuristic."""
    s = math.sqrt(0.5)
    # proxy normal (-s,0,s) through centre (5,0,5) ⇒ tangent plane z = x
    face = {
        "surface_type": "other",
        "freeform": True,
        "normal": [-s, 0.0, s],
        "center": [5.0, 0.0, 5.0],
        "bounding_box": [-1.0, -1.0, -1.0, 11.0, 1.0, 11.0],
    }
    # nodes on/near the tangent plane z = x (within the widened band)
    nodes = _nodes_dict(
        (5.0, 0.0, 5.0),    # on plane, inside aabb ✓
        (3.0, 0.0, 3.0),    # on plane ✓
        (7.0, 0.0, 7.0),    # on plane ✓
        (0.0, 0.0, 10.0),   # off plane (z−x=10) ✗
    )
    result = set(_nodes_on_face(nodes, face))
    assert {0, 1, 2}.issubset(result)
    assert 3 not in result


def test_freeform_face_without_normal_uses_fallback():
    """Legacy 'other' faces (no stored normal) still hit the thin-bbox fallback
    rather than crashing."""
    face = {"surface_type": "other", "bounding_box": [0.0, 0.0, 0.0, 10.0, 10.0, 0.1]}
    nodes = _nodes_dict((5.0, 5.0, 0.0), (5.0, 5.0, 50.0))
    result = set(_nodes_on_face(nodes, face))
    assert 0 in result and 1 not in result
