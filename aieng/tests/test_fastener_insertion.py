from __future__ import annotations

import json
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from aieng import FORMAT_VERSION
from aieng.package import create_package, read_manifest
from aieng.standards.fastener_insertion import (
    FASTENER_INSERTION_REPORT_PATH,
    insert_fasteners_for_holes,
)


def _make_package(tmp_path: Path, *, known_stack: bool = True, with_axis: bool = True) -> Path:
    pkg = create_package("fastener_demo", tmp_path / "fastener_demo.aieng")
    feature_graph = {
        "format_version": FORMAT_VERSION,
        "features": [
            {
                "id": f"feat_hole_{idx:03d}",
                "type": "mounting_hole",
                "name": f"M6 clearance hole {idx}",
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
                "hole_metadata": _hole_metadata(idx, known_stack=known_stack, with_axis=with_axis),
            }
            for idx in range(1, 5)
        ],
    }
    with zipfile.ZipFile(pkg, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph, indent=2, sort_keys=True) + "\n")
    return pkg


def _hole_metadata(idx: int, *, known_stack: bool, with_axis: bool) -> dict:
    metadata = {
        "diameter_mm": 6.6,
        "depth_mm": 9.0,
        "hole_depth_kind": "through",
        "through": True,
        "mating_stack": (
            {"status": "known", "thickness_mm": 9.0, "source": "test_fixture"}
            if known_stack
            else {"status": "unknown", "reason": "test fixture omitted stack"}
        ),
    }
    if with_axis:
        metadata["axis"] = {
            "origin_mm": [float(idx * 20), 10.0, 0.0],
            "direction": [0.0, 0.0, 1.0],
            "origin_source": "test_fixture",
            "direction_source": "test_fixture",
        }
    return metadata


def _read_json(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def test_explicit_insertion_populates_four_m6_holes_with_screws_and_nuts(tmp_path):
    pkg = _make_package(tmp_path)

    report = insert_fasteners_for_holes(
        pkg,
        [f"feat_hole_{idx:03d}" for idx in range(1, 5)],
    )

    assert report["status"] == "ok"
    assert report["explicit_opt_in"] is True
    assert report["mutates_geometry"] is False
    assert report["inserted_count"] == 8
    assert report["blockers"] == []

    feature_graph = _read_json(pkg, "graph/feature_graph.json")
    standard_parts = [feature for feature in feature_graph["features"] if feature["type"] == "standard_part"]
    screws = [feature for feature in standard_parts if feature["canonical_type"] == "screw"]
    nuts = [feature for feature in standard_parts if feature["canonical_type"] == "nut"]
    assert len(screws) == 4
    assert len(nuts) == 4
    assert all(feature["standard_part"] is True for feature in standard_parts)
    assert all(feature["source_library"] == "aieng.standards" for feature in standard_parts)
    assert all(feature["designation"] == "M6" for feature in standard_parts)
    assert screws[0]["parameters"]["length_mm"] == 16.0
    assert screws[0]["parameters"]["placement"]["axis_direction"] == [0.0, 0.0, 1.0]

    written_report = _read_json(pkg, FASTENER_INSERTION_REPORT_PATH)
    assert written_report["inserted_count"] == 8
    manifest = read_manifest(pkg)
    assert manifest["resources"]["graph"]["fastener_insertion_report"] == FASTENER_INSERTION_REPORT_PATH

    schema = json.loads((Path("schemas") / "feature_graph.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(feature_graph))
    assert errors == []


def test_insertion_reports_blocker_without_adding_parts_when_stack_unknown(tmp_path):
    pkg = _make_package(tmp_path, known_stack=False)

    report = insert_fasteners_for_holes(pkg, ["feat_hole_001"])

    assert report["status"] == "blocked"
    assert report["inserted_count"] == 0
    assert report["blockers"][0]["code"] == "unknown_stack_thickness"
    feature_graph = _read_json(pkg, "graph/feature_graph.json")
    assert not any(feature["type"] == "standard_part" for feature in feature_graph["features"])


def test_insertion_reports_blocker_without_adding_parts_when_axis_unknown(tmp_path):
    pkg = _make_package(tmp_path, with_axis=False)

    report = insert_fasteners_for_holes(pkg, ["feat_hole_001"])

    assert report["status"] == "blocked"
    assert report["inserted_count"] == 0
    assert report["blockers"][0]["code"] == "insufficient_placement"
    feature_graph = _read_json(pkg, "graph/feature_graph.json")
    assert not any(feature["type"] == "standard_part" for feature in feature_graph["features"])
