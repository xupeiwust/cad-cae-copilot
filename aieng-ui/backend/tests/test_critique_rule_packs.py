"""Tests for process-aware DfM rule packs in cad.critique / critique_engine."""

from __future__ import annotations

import pytest

from aieng.converters.critique_engine import critique_geometry, get_rule_pack, resolve_rule_pack_key


def _thin_wall_topology() -> dict:
    return {
        "entities": [
            {"id": "body_001", "type": "solid", "bounding_box": [0, 0, 0, 50, 50, 1.5]},
        ]
    }


def _thin_wall_feature_graph() -> dict:
    return {
        "features": [
            {
                "id": "f_wall",
                "type": "named_part",
                "name": "front_wall",
                "geometry_refs": {"body": "body_001"},
            }
        ]
    }


def _hole_feature_graph(diameter: float) -> dict:
    return {
        "features": [
            {
                "id": "f_wall",
                "type": "named_part",
                "name": "front_wall",
                "geometry_refs": {"body": "body_001"},
            },
            {
                "id": "f_hole",
                "type": "mounting_hole",
                "name": "mount_hole",
                "parameters": {"hole_diameter_mm": diameter},
                "geometry_refs": {"body": "body_001"},
            },
        ]
    }


def test_get_rule_pack_defaults_to_cnc() -> None:
    pack = get_rule_pack("unknown")
    assert pack.name == "cnc_aluminium"


def test_process_aliases_resolve_to_explicit_rule_packs() -> None:
    assert resolve_rule_pack_key("machining") == "cnc"
    assert get_rule_pack("cnc-aluminum").name == "cnc_aluminium"
    assert resolve_rule_pack_key("additive manufacturing") == "fdm"
    assert get_rule_pack("3d printing").name == "fdm"
    assert resolve_rule_pack_key("resin") == "sla"
    assert resolve_rule_pack_key("die casting") == "casting"
    assert get_rule_pack("casting").name == "casting_aluminium"


def test_cnc_flags_thin_wall() -> None:
    result = critique_geometry(
        _thin_wall_topology(),
        _thin_wall_feature_graph(),
        mode="engineering",
        process="cnc",
    )
    assert result["process"] == "cnc_aluminium"
    assert result["rules_applied"]["min_wall_mm"] == 3.0
    findings = [f for f in result["findings"] if f["rule"] == "min_wall_thickness"]
    assert findings
    assert findings[0]["rule_pack"] == "cnc_aluminium"
    assert "3.0" in findings[0]["observation"]


def test_fdm_passes_same_wall() -> None:
    result = critique_geometry(
        _thin_wall_topology(),
        _thin_wall_feature_graph(),
        mode="engineering",
        process="fdm",
    )
    assert result["process"] == "fdm"
    assert result["rules_applied"]["min_wall_mm"] == 1.2
    findings = [f for f in result["findings"] if f["rule"] == "min_wall_thickness"]
    assert not findings


def test_sheet_metal_intermediate_threshold() -> None:
    result = critique_geometry(
        _thin_wall_topology(),
        _thin_wall_feature_graph(),
        mode="engineering",
        process="sheet_metal",
    )
    assert result["rules_applied"]["min_wall_mm"] == 2.0
    # 1.5mm is below the 2.0mm sheet-metal threshold, so it should still flag.
    findings = [f for f in result["findings"] if f["rule"] == "min_wall_thickness"]
    assert findings
    assert "sheet_metal" in findings[0]["observation"]


def test_casting_rule_pack_uses_casting_threshold_not_cnc_fallback() -> None:
    topology = {
        "entities": [
            {"id": "body_001", "type": "solid", "bounding_box": [0, 0, 0, 50, 50, 3.5]},
        ]
    }
    result = critique_geometry(
        topology,
        _thin_wall_feature_graph(),
        mode="engineering",
        process="casting",
    )
    assert result["process"] == "casting_aluminium"
    assert result["rules_applied"]["requested_process"] == "casting"
    assert result["rules_applied"]["process_key"] == "casting"
    assert result["rules_applied"]["min_wall_mm"] == 4.0
    findings = [f for f in result["findings"] if f["rule"] == "min_wall_thickness"]
    assert findings
    assert "casting_aluminium minimum is 4.0mm" in findings[0]["observation"]


def test_cnc_checks_standard_hole_size() -> None:
    result = critique_geometry(
        _thin_wall_topology(),
        _hole_feature_graph(7.2),
        mode="engineering",
        process="cnc",
    )
    findings = [f for f in result["findings"] if f["rule"] == "standard_hole_size"]
    assert findings
    assert findings[0]["rule_pack"] == "cnc_aluminium"


def test_fdm_skips_standard_hole_check() -> None:
    result = critique_geometry(
        _thin_wall_topology(),
        _hole_feature_graph(7.2),
        mode="engineering",
        process="fdm",
    )
    assert result["rules_applied"]["check_standard_holes"] is False
    findings = [f for f in result["findings"] if f["rule"] == "standard_hole_size"]
    assert not findings


def test_explicit_override_trumps_rule_pack() -> None:
    result = critique_geometry(
        _thin_wall_topology(),
        _thin_wall_feature_graph(),
        mode="engineering",
        process="fdm",
        min_wall_mm=5.0,
    )
    assert result["rules_applied"]["min_wall_mm"] == 5.0
    findings = [f for f in result["findings"] if f["rule"] == "min_wall_thickness"]
    assert findings
