"""Tests for domain-aware mate predicates (concentric / tangent / coincident / clearance)."""
from __future__ import annotations

import pytest

from aieng.converters.assembly_interface_resolution import (
    evaluate_mate_predicate,
    validate_connection_geometry,
)


def test_concentric_satisfied_when_coaxial() -> None:
    wa = {"axis": [0, 0, 1], "axis_point": [10, 10, 0], "radius": 6}
    wb = {"axis": [0, 0, 1], "axis_point": [10, 10, 20], "radius": 11}  # same axis line
    r = evaluate_mate_predicate("concentric", wa, wb)
    assert r["satisfied"] is True
    assert r["measured_mm"] == pytest.approx(0.0, abs=1e-3)


def test_concentric_violated_when_offset() -> None:
    wa = {"axis": [0, 0, 1], "axis_point": [10, 10, 0], "radius": 6}
    wb = {"axis": [0, 0, 1], "axis_point": [14, 10, 20], "radius": 11}  # 4mm axis offset
    r = evaluate_mate_predicate("concentric", wa, wb)
    assert r["satisfied"] is False
    assert r["measured_mm"] == pytest.approx(4.0, abs=1e-3)


def test_tangent_satisfied_when_pitch_circles_touch() -> None:
    wa = {"axis": [1, 0, 0], "axis_point": [0, 0, 0], "radius": 15}
    wb = {"axis": [1, 0, 0], "axis_point": [0, 40, 0], "radius": 25}  # axis distance 40 = r1+r2
    r = evaluate_mate_predicate("tangent", wa, wb)
    assert r["satisfied"] is True
    assert r["expected_mm"] == pytest.approx(40.0)
    assert r["measured_mm"] == pytest.approx(40.0, abs=1e-3)


def test_tangent_violated_gearbox_gap() -> None:
    # the exact gearbox case: shafts 50mm apart, r1+r2=40 -> 10mm gap, gears do NOT mesh
    wa = {"axis": [1, 0, 0], "axis_point": [0, 25, 0], "radius": 15}
    wb = {"axis": [1, 0, 0], "axis_point": [0, -25, 0], "radius": 25}
    r = evaluate_mate_predicate("tangent", wa, wb)
    assert r["satisfied"] is False
    assert r["measured_mm"] == pytest.approx(50.0, abs=1e-3)
    assert r["expected_mm"] == pytest.approx(40.0)


def test_coincident_faces_flush_vs_not() -> None:
    wa = {"normal": [0, 0, 1], "centroid": [0, 0, 5]}
    wb = {"normal": [0, 0, -1], "centroid": [0, 0, 5.2]}  # facing, 0.2mm gap
    assert evaluate_mate_predicate("coincident", wa, wb)["satisfied"] is True
    wc = {"normal": [0, 0, 1], "centroid": [0, 0, 5]}  # same direction, not mating
    assert evaluate_mate_predicate("coincident", wa, wc)["satisfied"] is False


def test_clearance_checks_expected_gap() -> None:
    wa, wb = {"centroid": [0, 0, 0]}, {"centroid": [0, 0, 10]}
    assert evaluate_mate_predicate("clearance", wa, wb, expected_clearance_mm=10)["satisfied"] is True
    assert evaluate_mate_predicate("clearance", wa, wb, expected_clearance_mm=5)["satisfied"] is False
    no_expected = evaluate_mate_predicate("clearance", wa, wb)
    assert no_expected["satisfied"] is None
    assert no_expected["measured_mm"] == pytest.approx(10.0)


def test_predicate_insufficient_geometry_is_none() -> None:
    # concentric without an axis -> honest None, never a guess
    r = evaluate_mate_predicate("concentric", {"centroid": [0, 0, 0]}, {"centroid": [1, 1, 1]})
    assert r["satisfied"] is None


def _cyl_iface(axis, axis_point, radius, bbox):
    return {
        "resolution_status": "resolved", "semantic_role": "contact_face", "transform_note": None,
        "world": {"bbox": bbox, "centroid": [(bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2, (bbox[2] + bbox[5]) / 2],
                  "normal": None, "axis": axis, "axis_point": axis_point, "radius": radius},
    }


def test_connection_geometry_applies_and_fails_on_violated_predicate() -> None:
    assembly = {
        "format": "aieng.assembly_ir",
        "parts": [{"id": "shaft"}, {"id": "housing"}],
        "connections": [{
            "id": "c1", "type": "rigid_tie", "part_a": "shaft", "part_b": "housing",
            "interface_a": "if_s", "interface_b": "if_h", "mate_predicate": "concentric",
        }],
    }
    # coaxial -> satisfied -> plausible
    res_ok = {"interfaces": {
        "if_s": _cyl_iface([0, 0, 1], [6, 6, 0], 6, [0, 0, 0, 12, 12, 40]),
        "if_h": _cyl_iface([0, 0, 1], [6, 6, 0], 11, [-5, -5, 0, 17, 17, 40]),
    }}
    c_ok = validate_connection_geometry(assembly, res_ok)["connections"][0]
    assert c_ok["mate_predicate"]["predicate"] == "concentric"
    assert c_ok["mate_predicate"]["satisfied"] is True
    assert c_ok["geometry_status"] == "plausible"

    # offset axis -> violated -> invalid
    res_bad = {"interfaces": {
        "if_s": _cyl_iface([0, 0, 1], [6, 6, 0], 6, [0, 0, 0, 12, 12, 40]),
        "if_h": _cyl_iface([0, 0, 1], [11, 6, 0], 11, [0, -5, 0, 22, 17, 40]),  # axis 5mm off
    }}
    c_bad = validate_connection_geometry(assembly, res_bad)["connections"][0]
    assert c_bad["mate_predicate"]["satisfied"] is False
    assert c_bad["geometry_status"] == "invalid"
    assert "mate_predicate_violated" in c_bad["reasons"]
