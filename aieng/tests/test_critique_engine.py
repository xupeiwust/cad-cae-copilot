"""Tests for the deterministic critique engine shared with cad.critique."""
from __future__ import annotations

from aieng.converters.critique_engine import critique_geometry, resolve_rule_pack_key


def _topo(*bodies):
    return {"entities": list(bodies)}


def _body(bid, name, bbox, *, body_type="solid"):
    return {"id": bid, "type": body_type, "name": name, "bounding_box": bbox}


def _feature_graph(*features):
    return {"features": list(features)}


def _named_part(name, body_id):
    return {"id": f"feat_{body_id}", "type": "named_part", "name": name,
            "geometry_refs": {"body": body_id}}


def _fillet_feature(radius_mm, *, feature_id="fillet_1", body_id="b1"):
    return {
        "id": feature_id,
        "type": "fillet",
        "name": "Fillet candidate",
        "parameters": {"radius_mm": radius_mm},
        "geometry_refs": {"body": body_id},
    }


def test_empty_model_skipped():
    result = critique_geometry(_topo(), _feature_graph())
    assert result["status"] == "ok"
    assert result["verdict"] == "skipped"
    assert result["findings"] == []


def test_no_engineering_features_in_auto_mode():
    topo = _topo(_body("b1", "arm_L", [0, 0, 0, 10, 10, 100]))
    fg = _feature_graph(_named_part("arm_L", "b1"))
    result = critique_geometry(topo, fg, mode="auto")
    assert result["status"] == "ok"
    assert result["verdict"] == "passes"
    assert result["summary"]["engineering_audit_run"] is False


def test_thin_wall_fails_audit():
    # back_plate is one of the labels that elevates a thin-wall finding to high severity.
    topo = _topo(_body("b1", "back_plate", [0, 0, 0, 100, 80, 1.5]))
    fg = _feature_graph(_named_part("back_plate", "b1"))
    result = critique_geometry(topo, fg, mode="engineering")
    assert result["status"] == "ok"
    assert result["verdict"] == "fails_audit"
    finding = next(f for f in result["findings"] if f["rule"] == "min_wall_thickness")
    assert finding["severity"] == "high"
    assert finding["category"] == "manufacturing_rule"
    assert "1.50mm" in finding["observation"]


def test_thin_rib_is_medium_severity():
    topo = _topo(_body("b1", "rib_main", [0, 0, 0, 50, 1.0, 25]))
    fg = _feature_graph(_named_part("rib_main", "b1"))
    result = critique_geometry(topo, fg, mode="engineering")
    assert result["status"] == "ok"
    assert result["verdict"] == "passes_with_warnings"
    assert result["findings"][0]["severity"] == "medium"


def test_floating_part_flagged_high():
    b1 = _body("b1", "base_plate", [0, 0, 0, 50, 50, 5])
    b2 = _body("b2", "floater", [500, 500, 500, 520, 520, 520])
    topo = _topo(b1, b2)
    fg = _feature_graph(_named_part("base_plate", "b1"), _named_part("floater", "b2"))
    result = critique_geometry(topo, fg, mode="engineering")
    assert result["status"] == "ok"
    assert result["verdict"] == "fails_audit"
    finding = next(f for f in result["findings"] if f["rule"] == "floating_component")
    assert finding["severity"] == "high"


def test_nonstandard_hole_is_low_severity():
    topo = _topo(_body("b1", "base_plate", [0, 0, 0, 50, 50, 5]))
    fg = _feature_graph(
        _named_part("base_plate", "b1"),
        {"id": "mh1", "type": "mounting_hole", "name": "hole_1",
         "parameters": {"hole_diameter_mm": 7.0}, "geometry_refs": {"body": "b1"}},
    )
    result = critique_geometry(topo, fg, mode="engineering")
    assert result["status"] == "ok"
    assert result["verdict"] == "passes_with_notes"
    finding = result["findings"][0]
    assert finding["rule"] == "standard_hole_size"
    assert finding["severity"] == "low"


def test_nonstandard_hole_detected_with_core_recognizer_diameter_field():
    """The core RuleBasedFeatureRecognizer emits hole diameter as `diameter_mm`
    (the runtime path uses `hole_diameter_mm`). The standard-hole DfM check must
    read either, so it fires on imported / CLI-recognized geometry too."""
    topo = _topo(_body("b1", "base_plate", [0, 0, 0, 50, 50, 5]))
    fg = _feature_graph(
        _named_part("base_plate", "b1"),
        {"id": "mh1", "type": "mounting_hole", "name": "hole_1",
         "parameters": {"diameter_mm": 7.3, "radius_mm": 3.65},
         "geometry_refs": {"faces": ["f_hole_1"]}},
    )
    result = critique_geometry(topo, fg, mode="engineering")
    finding = next(f for f in result["findings"] if f["rule"] == "standard_hole_size")
    assert finding["severity"] == "low"


def test_m6_clearance_hole_is_not_flagged_as_nonstandard_drill():
    topo = _topo(_body("b1", "base_plate", [0, 0, 0, 50, 50, 5]))
    fg = _feature_graph(
        _named_part("base_plate", "b1"),
        {"id": "mh1", "type": "mounting_hole", "name": "M6 clearance hole",
         "parameters": {"hole_diameter_mm": 6.6},
         "geometry_refs": {"body": "b1", "faces": ["f_hole_1"]}},
    )
    result = critique_geometry(topo, fg, mode="engineering", process="cnc")
    assert result["status"] == "ok"
    assert not any(f["rule"] == "standard_hole_size" for f in result["findings"])
    assert 6.6 in result["rules_applied"]["standard_clearance_hole_diameters_mm"]


def test_small_corner_radius_flagged_for_casting_rule_pack():
    topo = _topo(_body("b1", "base_plate", [0, 0, 0, 80, 60, 6]))
    fg = _feature_graph(
        _named_part("base_plate", "b1"),
        _fillet_feature(1.0, body_id="b1"),
    )
    result = critique_geometry(topo, fg, mode="engineering", process="casting")
    finding = next(f for f in result["findings"] if f["rule"] == "min_corner_radius")
    assert finding["severity"] == "medium"
    assert finding["category"] == "manufacturing_rule"
    assert "1.00mm" in finding["observation"]
    assert "casting_aluminium minimum is 3.0mm" in finding["observation"]
    assert finding["thresholds"]["min_corner_radius_mm"] == 3.0


def test_corner_radius_rule_ignores_unmeasured_edge_breaks():
    topo = _topo(_body("b1", "base_plate", [0, 0, 0, 80, 60, 6]))
    fg = _feature_graph(
        _named_part("base_plate", "b1"),
        {"id": "ch1", "type": "chamfer", "name": "Chamfer", "parameters": {}},
    )
    result = critique_geometry(topo, fg, mode="engineering", process="casting")
    assert not any(f["rule"] == "min_corner_radius" for f in result["findings"])


def test_casting_flags_explicit_low_draft_angle():
    topo = _topo(_body("b1", "cast_housing", [0, 0, 0, 80, 60, 40]))
    fg = _feature_graph(
        _named_part("cast_housing", "b1"),
        {
            "id": "draft_1",
            "type": "taper",
            "name": "Side wall draft",
            "parameters": {"draft_angle_deg": 0.25},
            "geometry_refs": {"body": "b1"},
        },
    )
    result = critique_geometry(topo, fg, mode="engineering", process="casting")
    finding = next(f for f in result["findings"] if f["rule"] == "min_draft_angle")
    assert finding["severity"] == "medium"
    assert finding["category"] == "manufacturing_rule"
    assert "0.25deg" in finding["observation"]
    assert finding["thresholds"]["min_draft_angle_deg"] == 1.0
    assert result["rules_applied"]["min_draft_angle_deg"] == 1.0


def test_draft_angle_rule_requires_process_threshold_and_explicit_metadata():
    topo = _topo(_body("b1", "housing", [0, 0, 0, 80, 60, 40]))
    explicit_low_draft = _feature_graph(
        _named_part("housing", "b1"),
        {
            "id": "draft_1",
            "type": "taper",
            "name": "Side wall draft",
            "parameters": {"draft_angle_deg": 0.25},
            "geometry_refs": {"body": "b1"},
        },
    )
    missing_draft_metadata = _feature_graph(
        _named_part("housing", "b1"),
        {
            "id": "draft_2",
            "type": "taper",
            "name": "Side wall draft",
            "parameters": {},
            "geometry_refs": {"body": "b1"},
        },
    )
    cnc = critique_geometry(topo, explicit_low_draft, mode="engineering", process="cnc")
    casting_missing = critique_geometry(topo, missing_draft_metadata, mode="engineering", process="casting")
    assert cnc["rules_applied"]["min_draft_angle_deg"] is None
    assert not any(f["rule"] == "min_draft_angle" for f in cnc["findings"])
    assert not any(f["rule"] == "min_draft_angle" for f in casting_missing["findings"])


def test_fdm_flags_explicit_unsupported_overhang_from_vertical():
    topo = _topo(_body("b1", "printed_bracket", [0, 0, 0, 80, 60, 40]))
    fg = _feature_graph(
        _named_part("printed_bracket", "b1"),
        {
            "id": "overhang_1",
            "type": "overhang",
            "name": "Cantilever lip",
            "parameters": {"overhang_angle_from_vertical_deg": 62.0},
            "geometry_refs": {"body": "b1"},
        },
    )
    result = critique_geometry(topo, fg, mode="engineering", process="fdm")
    finding = next(f for f in result["findings"] if f["rule"] == "max_unsupported_overhang")
    assert finding["severity"] == "medium"
    assert finding["category"] == "manufacturing_rule"
    assert "62.00deg from vertical" in finding["observation"]
    assert finding["thresholds"]["max_unsupported_overhang_from_vertical_deg"] == 45.0
    assert result["rules_applied"]["max_unsupported_overhang_from_vertical_deg"] == 45.0


def test_overhang_rule_requires_fdm_threshold_and_unambiguous_metadata():
    topo = _topo(_body("b1", "printed_bracket", [0, 0, 0, 80, 60, 40]))
    explicit_overhang = _feature_graph(
        _named_part("printed_bracket", "b1"),
        {
            "id": "overhang_1",
            "type": "overhang",
            "name": "Cantilever lip",
            "parameters": {"overhang_angle_from_vertical_deg": 62.0},
            "geometry_refs": {"body": "b1"},
        },
    )
    ambiguous_overhang = _feature_graph(
        _named_part("printed_bracket", "b1"),
        {
            "id": "overhang_2",
            "type": "overhang",
            "name": "Cantilever lip",
            "parameters": {"overhang_angle_deg": 62.0},
            "geometry_refs": {"body": "b1"},
        },
    )
    cnc = critique_geometry(topo, explicit_overhang, mode="engineering", process="cnc")
    fdm_ambiguous = critique_geometry(topo, ambiguous_overhang, mode="engineering", process="fdm")
    assert cnc["rules_applied"]["max_unsupported_overhang_from_vertical_deg"] is None
    assert not any(f["rule"] == "max_unsupported_overhang" for f in cnc["findings"])
    assert not any(f["rule"] == "max_unsupported_overhang" for f in fdm_ambiguous["findings"])


def test_tapped_hole_at_tap_drill_diameter_is_not_flagged_nonstandard():
    """A hole recognized as a thread (tap-drill diameter) is intentionally a
    non-standard *final* diameter — flagging it 'non-standard hole' is a false
    positive, so the standard-hole check must skip threaded holes."""
    topo = _topo(_body("b1", "base_plate", [0, 0, 0, 50, 50, 5]))
    fg = _feature_graph(
        _named_part("base_plate", "b1"),
        # 6.8mm == M8 coarse tap-drill: non-standard as a final drill size.
        {"id": "mh1", "type": "mounting_hole", "name": "hole_1",
         "parameters": {"diameter_mm": 6.8, "radius_mm": 3.4},
         "geometry_refs": {"faces": ["f_hole_1"]}},
        {"id": "th1", "type": "thread", "name": "Thread candidate (M8)",
         "parameters": {"nominal_size": "M8"}, "geometry_refs": {"faces": ["f_hole_1"]}},
    )
    result = critique_geometry(topo, fg, mode="engineering")
    assert not any(f["rule"] == "standard_hole_size" for f in result["findings"])


def test_bracket_without_mounting_warns():
    topo = _topo(_body("b1", "bracket", [0, 0, 0, 50, 50, 5]))
    fg = _feature_graph(_named_part("bracket", "b1"))
    result = critique_geometry(topo, fg, mode="engineering")
    assert result["status"] == "ok"
    assert result["verdict"] == "passes_with_warnings"
    assert any(f["rule"] == "missing_mounting_interface" for f in result["findings"])


def test_passes_when_thick_enough():
    # A non-plate/non-bracket part in forced engineering mode has no blocking
    # findings and no advisory warnings.
    topo = _topo(_body("b1", "arm_L", [0, 0, 0, 10, 10, 100]))
    fg = _feature_graph(_named_part("arm_L", "b1"))
    result = critique_geometry(topo, fg, mode="engineering")
    assert result["status"] == "ok"
    assert result["verdict"] == "passes"
    assert result["findings"] == []


def test_custom_min_wall_respected():
    topo = _topo(_body("b1", "arm_L", [0, 0, 0, 10, 10, 2.0]))
    fg = _feature_graph(_named_part("arm_L", "b1"))
    result = critique_geometry(topo, fg, mode="engineering", min_wall_mm=1.5)
    assert result["status"] == "ok"
    assert result["verdict"] == "passes"


def test_rules_applied_returned():
    result = critique_geometry(_topo(), _feature_graph())
    assert result["rules_applied"]["min_wall_mm"] == 3.0
    assert result["rules_applied"]["min_corner_radius_mm"] == 2.0
    assert 3.0 in result["rules_applied"]["standard_hole_diameters_mm"]


def test_sheet_metal_aliases_resolve_to_sheet_metal_rule_pack():
    assert resolve_rule_pack_key("brake forming") == "sheet_metal"
    assert resolve_rule_pack_key("sheetmetal") == "sheet_metal"
    result = critique_geometry(_topo(), _feature_graph(), process="laser cut sheet")
    assert result["rules_applied"]["process_key"] == "sheet_metal"
    assert result["rules_applied"]["process"] == "sheet_metal"
