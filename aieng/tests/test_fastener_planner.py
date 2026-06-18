from __future__ import annotations

from aieng.standards.fastener_planner import (
    plan_fastener_for_hole,
    plan_fasteners_for_features,
)


def test_m6_clearance_hole_matches_metric_fastener():
    result = plan_fastener_for_hole(
        {
            "diameter_mm": 6.6,
            "depth_mm": 8.0,
            "hole_depth_kind": "through",
            "through": True,
            "mating_stack": {"status": "unknown"},
        }
    )

    assert result["status"] == "matched"
    assert result["mode"] == "clearance"
    assert result["mutates_geometry"] is False
    spec = result["fastener_spec"]
    assert spec["designation"] == "M6"
    assert spec["part_type"] == "hex_bolt"
    assert spec["nominal_thread_diameter_mm"] == 6.0
    assert spec["clearance_hole_diameter_mm"] == 6.6
    assert spec["suggested_length_mm"] == 10.0
    assert spec["nut_requirement"] == "unknown_through_clearance_hole"


def test_counterbored_hole_selects_socket_head_style():
    result = plan_fastener_for_hole(
        {
            "diameter_mm": 6.6,
            "hole_depth_kind": "through",
            "counterbore": {"diameter_mm": 11.0, "depth_mm": 6.0},
        }
    )

    assert result["status"] == "matched"
    assert result["mode"] == "counterbore"
    spec = result["fastener_spec"]
    assert spec["part_type"] == "socket_head_cap_screw"
    assert spec["head_style"] == "socket_head"
    assert spec["counterbore"] == {"diameter_mm": 11.0, "depth_mm": 6.0}


def test_countersunk_hole_selects_flat_head_style():
    result = plan_fastener_for_hole(
        {
            "diameter_mm": 4.5,
            "hole_depth_kind": "through",
            "countersink": {"angle_deg": 90.0, "diameter_mm": 8.0},
        }
    )

    assert result["status"] == "matched"
    assert result["mode"] == "countersunk"
    spec = result["fastener_spec"]
    assert spec["designation"] == "M4"
    assert spec["part_type"] == "flat_head_socket_screw"
    assert spec["head_style"] == "countersunk"


def test_threaded_hole_requires_explicit_thread_evidence():
    result = plan_fastener_for_hole(
        {
            "diameter_mm": 6.0,
            "thread": {"designation": "M6", "pitch_mm": 1.0},
        }
    )

    assert result["status"] == "matched"
    assert result["mode"] == "threaded"
    spec = result["fastener_spec"]
    assert spec["designation"] == "M6"
    assert spec["threaded_hole"] is True
    assert spec["thread_pitch_mm"] == 1.0
    assert spec["nut_requirement"] == "not_required_threaded_hole"


def test_thread_like_clearance_diameter_without_thread_evidence_does_not_invent_threaded_match():
    result = plan_fastener_for_hole({"diameter_mm": 6.0})

    assert result["status"] == "no_match"
    assert "fastener_spec" not in result
    assert "outside the supported metric clearance-hole catalog" in result["reasons"][0]


def test_out_of_catalog_hole_returns_no_match():
    result = plan_fastener_for_hole({"diameter_mm": 7.3})

    assert result["status"] == "no_match"
    assert result["observed"] == {"diameter_mm": 7.3}
    assert "fastener_spec" not in result


def test_ambiguous_catalog_match_returns_candidates_without_spec():
    catalog = {
        "M6A": {"thread_diameter": 6.0, "clearance_hole": 6.6},
        "M6B": {"thread_diameter": 6.0, "clearance_hole": 6.6},
    }

    result = plan_fastener_for_hole({"diameter_mm": 6.6}, catalog=catalog)

    assert result["status"] == "ambiguous"
    assert "fastener_spec" not in result
    assert [candidate["designation"] for candidate in result["candidates"]] == ["M6A", "M6B"]


def test_plan_fasteners_for_features_only_consumes_features_with_hole_metadata():
    features = [
        {"id": "base", "type": "base_plate"},
        {"id": "hole", "type": "mounting_hole", "hole_metadata": {"diameter_mm": 6.6}},
    ]

    plans = plan_fasteners_for_features(features)

    assert len(plans) == 1
    assert plans[0]["feature_id"] == "hole"
    assert plans[0]["feature_type"] == "mounting_hole"
    assert plans[0]["status"] == "matched"
