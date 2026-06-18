from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng import FORMAT_VERSION
from aieng.package import create_package
from aieng.standards.fastener_insertion import insert_fasteners_for_holes
from aieng.standards.fastener_validation import (
    validate_inserted_fasteners,
    validate_inserted_fasteners_package,
)


def _make_package(tmp_path: Path) -> Path:
    pkg = create_package("fastener_validation_demo", tmp_path / "fastener_validation_demo.aieng")
    feature_graph = {
        "format_version": FORMAT_VERSION,
        "features": [
            {
                "id": f"feat_hole_{idx:03d}",
                "type": "mounting_hole",
                "name": f"M6 stack hole {idx}",
                "geometry_refs": {"faces": [f"face_hole_{idx:03d}"]},
                "parameters": {"diameter_mm": 6.6},
                "parameter_source": "mock",
                "parameter_confidence": "medium",
                "editable": True,
                "editability": "semantic_only",
                "writeback_strategy": "semantic_parameter_update_only",
                "editability_reason": "Test fixture semantic hole.",
                "intent": {"role": "mounting_or_passage_candidate"},
                "recognition": {"method": "test_fixture", "confidence": "medium"},
                "hole_metadata": {
                    "diameter_mm": 6.6,
                    "depth_mm": 9.0,
                    "hole_depth_kind": "through",
                    "through": True,
                    "axis": {
                        "origin_mm": [float(idx * 20), 10.0, 0.0],
                        "direction": [0.0, 0.0, 1.0],
                    },
                    "mating_stack": {
                        "status": "known",
                        "thickness_mm": 9.0,
                        "part_ids": ["plate_a", "plate_b"],
                    },
                },
            }
            for idx in range(1, 3)
        ],
    }
    with zipfile.ZipFile(pkg, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph, indent=2, sort_keys=True) + "\n")
    return pkg


def _read_feature_graph(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read("graph/feature_graph.json"))


def test_valid_inserted_fasteners_pass_and_emit_bolted_proxy_connections(tmp_path):
    pkg = _make_package(tmp_path)
    insert_fasteners_for_holes(pkg, ["feat_hole_001", "feat_hole_002"])

    report = validate_inserted_fasteners_package(pkg)

    assert report["status"] == "ok"
    assert report["mutates_geometry"] is False
    assert report["runs_solver"] is False
    assert report["validation_count"] == 4
    assert all(item["status"] == "pass" for item in report["validations"])
    assert len(report["bolted_proxy_connections"]) == 2
    first = report["bolted_proxy_connections"][0]
    assert first["type"] == "bolted_proxy"
    assert first["part_a"] == "plate_a"
    assert first["part_b"] == "plate_b"
    assert "no bolt preload" in first["limitations"][0]


def test_offset_inserted_fastener_is_reported_as_not_coaxial(tmp_path):
    pkg = _make_package(tmp_path)
    insert_fasteners_for_holes(pkg, ["feat_hole_001"])
    feature_graph = _read_feature_graph(pkg)
    screw = next(
        feature
        for feature in feature_graph["features"]
        if feature.get("type") == "standard_part" and feature.get("canonical_type") == "screw"
    )
    screw["parameters"]["placement"]["axis_origin_mm"] = [25.0, 10.0, 0.0]

    report = validate_inserted_fasteners(feature_graph, tolerance_mm=0.25)

    failed = next(item for item in report["validations"] if item["feature_id"] == screw["id"])
    assert failed["status"] == "fail"
    assert "fastener_not_coaxial" in failed["reasons"]
    assert report["warnings"]


def test_missing_evidence_returns_unknown_without_bolted_proxy():
    feature_graph = {
        "format_version": FORMAT_VERSION,
        "features": [
            {
                "id": "hole",
                "type": "mounting_hole",
                "name": "hole without metadata",
                "geometry_refs": {"faces": ["face_hole"]},
                "parameters": {"diameter_mm": 6.6},
                "recognition": {"method": "test", "confidence": "low"},
            },
            {
                "id": "inserted_screw",
                "type": "standard_part",
                "name": "semantic screw",
                "geometry_refs": {"faces": ["face_hole"]},
                "parameters": {"placement": {}},
                "relationships": [
                    {
                        "type": "inserted_for_hole",
                        "source_feature_id": "inserted_screw",
                        "target_feature_id": "hole",
                    }
                ],
                "canonical_type": "screw",
                "designation": "M6",
            },
        ],
    }

    report = validate_inserted_fasteners(feature_graph)

    assert report["status"] == "review"
    assert report["validations"][0]["status"] == "unknown"
    assert "missing_axis_evidence" in report["validations"][0]["reasons"]
    assert report["bolted_proxy_connections"] == []
