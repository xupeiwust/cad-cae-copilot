"""Tests for the aieng.standards Shape IR generators.

Verifies that every generator returns a well-formed Shape IR node with the
required fields (id, name/label, parameters, metadata, and valid children
when applicable).
"""
from __future__ import annotations

import pytest

from aieng.standards import (
    angle_profile,
    blind_hole,
    channel_profile,
    counterbored_hole,
    countersunk_hole,
    deep_groove_ball_bearing,
    hex_bolt,
    hex_nut,
    i_beam_profile,
    rectangular_tube,
    round_tube,
    set_screw,
    socket_head_cap_screw,
    splined_shaft,
    stepped_shaft,
    tapped_hole,
    through_hole,
    thrust_ball_bearing,
    washer,
)
from aieng.standards.bearings import (
    DEEP_GROOVE_BALL_BEARING_PRESETS,
    THRUST_BALL_BEARING_PRESETS,
)
from aieng.standards.fasteners import (
    METRIC_BOLT_PRESETS,
    METRIC_NUT_PRESETS,
    METRIC_SET_SCREW_PRESETS,
    METRIC_SOCKET_HEAD_PRESETS,
    METRIC_WASHER_PRESETS,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _assert_is_shape_ir_node(node: dict) -> None:
    assert isinstance(node, dict)
    assert "id" in node
    assert "parameters" in node
    assert isinstance(node["parameters"], dict)
    assert "metadata" in node
    meta = node["metadata"]
    assert meta.get("standard_name")
    assert meta.get("standard_reference")
    assert meta.get("part_category")
    assert isinstance(meta.get("editable_parameters"), list)


def _assert_has_children(node: dict, min_count: int = 1) -> None:
    children = node.get("children", node.get("inputs", []))
    assert isinstance(children, list)
    assert len(children) >= min_count


# ── fasteners ──────────────────────────────────────────────────────────────

def test_hex_bolt():
    node = hex_bolt()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"
    assert node["parameters"]["diameter"] == 8.0


def test_hex_bolt_with_presets():
    for size, preset in METRIC_BOLT_PRESETS.items():
        node = hex_bolt(**preset)
        _assert_is_shape_ir_node(node)
        assert node["parameters"]["diameter"] == preset["diameter"]


def test_hex_nut():
    node = hex_nut()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "difference"


def test_hex_nut_with_presets():
    for size, preset in METRIC_NUT_PRESETS.items():
        node = hex_nut(**preset)
        _assert_is_shape_ir_node(node)


def test_washer():
    node = washer()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "difference"


def test_washer_with_presets():
    for size, preset in METRIC_WASHER_PRESETS.items():
        node = washer(**preset)
        _assert_is_shape_ir_node(node)


def test_socket_head_cap_screw():
    node = socket_head_cap_screw()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"


def test_socket_head_cap_screw_with_presets():
    for size, preset in METRIC_SOCKET_HEAD_PRESETS.items():
        node = socket_head_cap_screw(**preset)
        _assert_is_shape_ir_node(node)


def test_set_screw():
    node = set_screw()
    _assert_is_shape_ir_node(node)
    assert node["primitive"] == "cylinder"


def test_set_screw_with_presets():
    for size, preset in METRIC_SET_SCREW_PRESETS.items():
        node = set_screw(**preset)
        _assert_is_shape_ir_node(node)


# ── bearings ───────────────────────────────────────────────────────────────

def test_deep_groove_ball_bearing():
    node = deep_groove_ball_bearing()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"


def test_deep_groove_ball_bearing_presets():
    for size, preset in DEEP_GROOVE_BALL_BEARING_PRESETS.items():
        node = deep_groove_ball_bearing(**preset)
        _assert_is_shape_ir_node(node)
        assert node["parameters"]["bore"] == preset["bore"]


def test_thrust_ball_bearing():
    node = thrust_ball_bearing()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"


def test_thrust_ball_bearing_presets():
    for size, preset in THRUST_BALL_BEARING_PRESETS.items():
        node = thrust_ball_bearing(**preset)
        _assert_is_shape_ir_node(node)


# ── shafts ──────────────────────────────────────────────────────────────────

def test_stepped_shaft():
    node = stepped_shaft()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 3)
    assert node["operation"] == "union"


def test_stepped_shaft_with_keyway():
    node = stepped_shaft(keyway_width=6.0, keyway_depth=3.0)
    _assert_is_shape_ir_node(node)
    assert node["parameters"]["keyway_width"] == 6.0
    assert node["parameters"]["keyway_depth"] == 3.0


def test_splined_shaft():
    node = splined_shaft()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)  # body + at least one spline
    assert node["operation"] == "union"
    assert node["parameters"]["spline_count"] == 6


# ── profiles ───────────────────────────────────────────────────────────────

def test_angle_profile():
    node = angle_profile()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"


def test_channel_profile():
    node = channel_profile()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "difference"


def test_i_beam_profile():
    node = i_beam_profile()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 3)
    assert node["operation"] == "union"


def test_rectangular_tube():
    node = rectangular_tube()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "difference"


def test_round_tube():
    node = round_tube()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "difference"


# ── holes ────────────────────────────────────────────────────────────────────

def test_through_hole():
    node = through_hole()
    _assert_is_shape_ir_node(node)
    assert node["primitive"] == "cylinder"


def test_blind_hole():
    node = blind_hole()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"
    assert node["parameters"]["bottom_angle"] == 118.0


def test_countersunk_hole():
    node = countersunk_hole()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"


def test_counterbored_hole():
    node = counterbored_hole()
    _assert_is_shape_ir_node(node)
    _assert_has_children(node, 2)
    assert node["operation"] == "union"


def test_tapped_hole():
    node = tapped_hole()
    _assert_is_shape_ir_node(node)
    assert node["primitive"] == "cylinder"
    assert node["parameters"]["thread_pitch"] == 1.25


# ── integration: nodes can be assembled into a payload ───────────────────────

def test_assemble_payload():
    """Verify that generated nodes fit into a valid Shape IR payload."""
    parts = [
        hex_bolt(),
        hex_nut(),
        washer(),
        deep_groove_ball_bearing(),
        stepped_shaft(),
        angle_profile(),
        through_hole(),
    ]
    payload = {
        "format_version": "0.1",
        "model_id": "test_assembly",
        "representation": "brep_build123d",
        "parts": parts,
    }
    assert isinstance(payload["parts"], list)
    assert len(payload["parts"]) == 7
    for p in payload["parts"]:
        assert "id" in p
        assert "metadata" in p
