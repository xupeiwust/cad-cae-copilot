from __future__ import annotations

import pytest

from app.cad_fidelity_benchmark import (
    SCORECARD_FORMAT,
    list_cad_fidelity_cases,
    score_cad_fidelity_case,
    score_cad_fidelity_suite,
)


def test_cad_fidelity_cases_define_v0_portfolio_with_provenance() -> None:
    cases = list_cad_fidelity_cases()

    assert len(cases) >= 8
    assert len({case["case_id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["prompt"]
        assert case["source_provenance"]
        assert case["failure_conditions"]
        assert case.get("required_named_parts") or case.get("required_feature_types")


def test_cad_fidelity_scores_semantically_good_flange() -> None:
    topology = {
        "entities": [
            {
                "id": "body_001",
                "type": "solid",
                "name": "flange",
                "bounding_box": [-50.0, -50.0, 0.0, 50.0, 50.0, 12.0],
            }
        ]
    }
    feature_graph = {
        "features": [
            {"id": "feat_body_001", "type": "named_part", "name": "flange"},
            {
                "id": "feat_holes",
                "type": "mounting_hole_pattern",
                "name": "M6 bolt circle",
                "parameters": {"count": 4, "hole_diameter_mm": 6.6},
            },
            {
                "id": "feat_bore",
                "type": "bore",
                "name": "Center bore",
                "parameters": {"bore_diameter_mm": 24.0},
            },
        ]
    }

    result = score_cad_fidelity_case(
        "flange_m6_four_hole_pattern",
        topology_map=topology,
        feature_graph=feature_graph,
    )

    assert result["format"] == SCORECARD_FORMAT
    assert result["status"] == "passed"
    assert result["score"]["earned"] == result["score"]["possible"]


def test_cad_fidelity_catches_exportable_but_semantically_bad_model() -> None:
    # A featureless block exports successfully, but it should fail the flange
    # fidelity case because it lacks named/semantic hole and bore features.
    topology = {
        "entities": [
            {
                "id": "body_001",
                "type": "solid",
                "name": "block",
                "bounding_box": [-50.0, -50.0, 0.0, 50.0, 50.0, 12.0],
            }
        ]
    }
    feature_graph = {"features": [{"id": "feat_body_001", "type": "named_part", "name": "block"}]}

    result = score_cad_fidelity_case(
        "flange_m6_four_hole_pattern",
        topology_map=topology,
        feature_graph=feature_graph,
    )

    assert result["status"] == "failed"
    failed = [check for check in result["checks"] if check["status"] == "fail"]
    assert {check["id"] for check in failed} >= {
        "named_part:flange",
        "feature_type:mounting_hole_pattern",
        "feature_type:bore",
    }


def test_cad_fidelity_suite_is_machine_readable_and_honest() -> None:
    report = score_cad_fidelity_suite(case_ids=["flange_m6_four_hole_pattern"])

    assert report["format"] == SCORECARD_FORMAT
    assert report["summary"]["case_count"] == 1
    assert "not certification" in report["honesty_boundary"]
    assert report["cases"][0]["failure_conditions"]


def test_cad_fidelity_unknown_case_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown CAD fidelity case_id"):
        score_cad_fidelity_case("missing_case")
