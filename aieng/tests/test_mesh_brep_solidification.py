"""Tests for conservative mesh-derived B-Rep sewing, solid STEP export, and roundtrip.

Only a closed OCC-valid solid may write geometry/reconstructed.step. Partial and failed
cases must leave STEP absent and explain why in diagnostics.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("OCP")

from aieng.converters.mesh_brep_face_generation import PARTIAL_BREP_FACES_PATH
from aieng.converters.mesh_brep_reconstruction import PARTIAL_BREP_SURFACES_PATH
from aieng.converters.mesh_brep_solidification import (  # noqa: E402
    MESH_BREP_ROUNDTRIP_PATH,
    MESH_BREP_SEWING_PATH,
    MESH_BREP_STEP_EXPORT_PATH,
    RECONSTRUCTED_STEP_PATH,
    RECONSTRUCTED_TOPOLOGY_PATH,
    reconstruct_brep_step,
)
from aieng.converters.mesh_brep_stitching import (  # noqa: E402
    MESH_BREP_STITCHING_PLAN_PATH,
    MESH_BREP_STITCHING_READINESS_PATH,
    plan_brep_stitching,
)

_PROV = {
    "source_mesh_artifact": "geometry/shape_ir.json#optimized_blk",
    "source_ir_node": "blk",
    "design_space_node": "blk",
    "runtime": "manifold",
}
_CV = {
    0: [0, 0, 0],
    1: [1, 0, 0],
    2: [1, 1, 0],
    3: [0, 1, 0],
    4: [0, 0, 1],
    5: [1, 0, 1],
    6: [1, 1, 1],
    7: [0, 1, 1],
}
_CUBE_FACES = {
    0: [0, 1, 2, 3],
    1: [4, 5, 6, 7],
    2: [0, 1, 5, 4],
    3: [3, 2, 6, 7],
    4: [1, 2, 6, 5],
    5: [0, 3, 7, 4],
}
_CUBE_ADJ_PAIRS = [
    (0, 2),
    (0, 3),
    (0, 4),
    (0, 5),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (2, 4),
    (2, 5),
    (3, 4),
    (3, 5),
]


def _loop(ids: list[int]) -> list[list[float]]:
    return [list(_CV[i]) for i in ids]


def _faces_doc(region_ids: list[int]) -> dict:
    return {
        "format": "aieng.partial_brep_faces",
        "faces": [
            {
                "face_id": f"face_cand_{i:03d}",
                "source_region_id": f"region_{i:03d}",
                "source_surface_id": f"surface_{i:03d}",
                "face_type": "plane",
                "status": "generated",
                "fit_confidence": "high",
                "geometry_validation": {"valid": True, "area": 1.0},
            }
            for i in region_ids
        ],
        "provenance": _PROV,
    }


def _surfaces_doc(region_ids: list[int]) -> dict:
    return {
        "format": "aieng.partial_brep_surfaces",
        "face_candidates": [
            {
                "face_candidate_id": f"face_cand_{i:03d}",
                "source_region_id": f"region_{i:03d}",
                "source_surface_id": f"surface_{i:03d}",
                "surface_type": "plane",
                "fit_confidence": "high",
                "boundary": {"loop_world": _loop(_CUBE_FACES[i])},
            }
            for i in region_ids
        ],
        "provenance": _PROV,
    }


def _region_graph(region_ids: list[int], pairs: list[tuple[int, int]]) -> dict:
    return {
        "regions": [{"region_id": f"region_{i:03d}", "area": 1.0} for i in region_ids],
        "adjacency": [
            {"region_a": f"region_{a:03d}", "region_b": f"region_{b:03d}", "shared_boundary_edges": 1}
            for a, b in pairs
        ],
        "provenance": _PROV,
    }


def _write_pkg(tmp_path: Path, region_ids: list[int], graph_region_ids: list[int] | None = None) -> Path:
    faces = _faces_doc(region_ids)
    surfaces = _surfaces_doc(region_ids)
    graph_ids = graph_region_ids or region_ids
    region_graph = _region_graph(graph_ids, _CUBE_ADJ_PAIRS)
    plan, readiness = plan_brep_stitching(faces, surfaces, region_graph)
    pkg = tmp_path / "case.aieng"
    manifest = {
        "format": "aieng.conversion_manifest",
        "geometry_execution": {
            "executed": True,
            "geometry_kind": "mesh",
            "representation_kind": "mesh",
            "actual_runtime": "manifold",
        },
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": [{"id": "blk"}]}))
        zf.writestr("graph/mesh_region_graph.json", json.dumps(region_graph))
        zf.writestr(PARTIAL_BREP_FACES_PATH, json.dumps(faces))
        zf.writestr(PARTIAL_BREP_SURFACES_PATH, json.dumps(surfaces))
        zf.writestr(MESH_BREP_STITCHING_PLAN_PATH, json.dumps(plan))
        zf.writestr(MESH_BREP_STITCHING_READINESS_PATH, json.dumps(readiness))
        zf.writestr("provenance/conversion_manifest.json", json.dumps(manifest))
    return pkg


def _replace_member(pkg: Path, name: str, payload: dict) -> None:
    tmp = pkg.with_suffix(".tmp.aieng")
    with zipfile.ZipFile(pkg, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename != name:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(name, json.dumps(payload))
    tmp.replace(pkg)


def test_cube_closed_shell_becomes_valid_solid_step_and_roundtrips(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, list(range(6)))
    result = reconstruct_brep_step(pkg)
    assert result["sewing"]["summary"]["shell_type"] == "closed_shell"
    assert result["sewing"]["summary"]["free_edge_count"] == 0
    assert result["step_export"]["solid_created"] is True
    assert result["step_export"]["step_exported"] is True
    assert result["roundtrip_verification"]["status"] in {"passed", "warning"}
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert RECONSTRUCTED_STEP_PATH in names
        assert RECONSTRUCTED_TOPOLOGY_PATH in names
        assert "geometry/topology_map.json" in names
        topo = json.loads(zf.read("geometry/topology_map.json"))
        assert len([e for e in topo["entities"] if e["type"] == "face"]) == 6
        manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
    assert manifest["geometry_execution"]["geometry_kind"] == "brep"
    assert manifest["geometry_execution"]["production_ready"] is False
    assert manifest["geometry_execution"]["source_ir_node"] == "blk"
    assert manifest["geometry_execution"]["design_space_node"] == "blk"


def test_missing_face_produces_partial_shell_no_step(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, list(range(5)), graph_region_ids=list(range(6)))
    result = reconstruct_brep_step(pkg)
    assert result["sewing"]["summary"]["shell_type"] == "partial_shell"
    assert result["sewing"]["summary"]["free_edge_count"] > 0
    assert result["step_export"]["step_exported"] is False
    assert "valid closed shell" in result["step_export"]["reason"]
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_BREP_SEWING_PATH in names
        assert MESH_BREP_STEP_EXPORT_PATH in names
        assert MESH_BREP_ROUNDTRIP_PATH in names
        assert RECONSTRUCTED_STEP_PATH not in names
        manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
    assert manifest["geometry_execution"]["geometry_kind"] == "mesh"
    assert manifest["mesh_brep_reconstruction"]["status"] == "not_exported"


def test_gapped_or_not_ready_faces_do_not_export_step(tmp_path: Path) -> None:
    faces = _faces_doc([0, 1])
    surfaces = {
        "face_candidates": [
            {
                "face_candidate_id": "face_cand_000",
                "source_region_id": "region_000",
                "surface_type": "plane",
                "boundary": {"loop_world": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]},
            },
            {
                "face_candidate_id": "face_cand_001",
                "source_region_id": "region_001",
                "surface_type": "plane",
                "boundary": {"loop_world": [[1.03, 0, 0], [2.03, 0, 0], [2.03, 1, 0], [1.03, 1, 0]]},
            },
        ],
        "provenance": _PROV,
    }
    rg = _region_graph([0, 1], [(0, 1)])
    plan, readiness = plan_brep_stitching(faces, surfaces, rg)
    pkg = tmp_path / "gapped.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr(PARTIAL_BREP_FACES_PATH, json.dumps(faces))
        zf.writestr(PARTIAL_BREP_SURFACES_PATH, json.dumps(surfaces))
        zf.writestr(MESH_BREP_STITCHING_PLAN_PATH, json.dumps(plan))
        zf.writestr(MESH_BREP_STITCHING_READINESS_PATH, json.dumps(readiness))
    result = reconstruct_brep_step(pkg)
    assert result["sewing"]["summary"]["shell_created"] is False
    assert result["step_export"]["step_exported"] is False
    with zipfile.ZipFile(pkg) as zf:
        assert RECONSTRUCTED_STEP_PATH not in zf.namelist()


def test_invalid_face_candidate_is_skipped_no_false_step(tmp_path: Path) -> None:
    pkg = _write_pkg(tmp_path, list(range(6)))
    bad_surfaces = _surfaces_doc(list(range(6)))
    bad_surfaces["face_candidates"][0]["boundary"]["loop_world"] = [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
    _replace_member(pkg, PARTIAL_BREP_SURFACES_PATH, bad_surfaces)
    result = reconstruct_brep_step(pkg)
    assert result["sewing"]["skipped_faces"]
    assert result["step_export"]["step_exported"] is False


def test_missing_inputs_degrade_with_diagnostics(tmp_path: Path) -> None:
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", "{}")
    result = reconstruct_brep_step(pkg)
    assert result["step_export"]["step_exported"] is False
    assert result["roundtrip_verification"]["status"] in {"warning", "failed"}
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert MESH_BREP_SEWING_PATH in names
        assert MESH_BREP_STEP_EXPORT_PATH in names
        assert MESH_BREP_ROUNDTRIP_PATH in names
        assert RECONSTRUCTED_STEP_PATH not in names
