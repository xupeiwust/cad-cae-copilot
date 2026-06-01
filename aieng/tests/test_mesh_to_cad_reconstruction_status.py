"""Focused tests for mesh-to-CAD reconstruction status aggregator v0.

Tests the mesh_to_cad_reconstruction_status converter:
- status classification (step_exported, closed_brep_solid, partial_brep, freeform_candidate_only, mesh_only, insufficient_data)
- blocker extraction from existing diagnostics
- coverage/readiness summary
- honesty flags
- integration with the mesh pipeline
- existing analytic STEP path unchanged
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np

from aieng.converters.mesh_to_cad_reconstruction_status import (
    STATUS_PATH,
    build_mesh_to_cad_reconstruction_status,
    write_mesh_to_cad_reconstruction_status,
)
from aieng.converters.mesh_brep_solidification import (
    MESH_BREP_ROUNDTRIP_PATH,
    MESH_BREP_SEWING_PATH,
    MESH_BREP_STEP_EXPORT_PATH,
    RECONSTRUCTED_STEP_PATH,
)
from aieng.converters.mesh_brep_stitching import (
    MESH_BREP_STITCHING_PLAN_PATH,
    MESH_BREP_STITCHING_READINESS_PATH,
)
from aieng.converters.mesh_freeform_brep_face_generation import FREEFORM_BREP_FACES_PATH
from aieng.converters.mesh_freeform_face_trimming_readiness import TRIMMING_READINESS_PATH
from aieng.converters.mesh_freeform_surface_fitting import FREEFORM_SURFACE_FIT_PATH
from aieng.converters.mesh_freeform_surface_readiness import FREEFORM_READINESS_PATH
from aieng.converters.mesh_reconstruction_readiness import MESH_RECONSTRUCTION_READINESS_PATH
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH
from aieng.converters.mesh_surface_fitting import MESH_SURFACE_FIT_PATH
from aieng.converters.mesh_brep_face_generation import PARTIAL_BREP_FACES_PATH
from aieng.converters.mesh_brep_reconstruction import MESH_BREP_PLAN_PATH, PARTIAL_BREP_SURFACES_PATH


def _make_inputs(**kwargs) -> dict[str, Any]:
    """Build minimal inputs dict for testing."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _region_graph(regions: list[dict]) -> dict[str, Any]:
    return {"regions": regions}


def _surface_fit(surfaces: list[dict]) -> dict[str, Any]:
    return {"surfaces": surfaces}


def _sewing_summary(shell_type: str) -> dict[str, Any]:
    return {"summary": {"shell_type": shell_type, "shell_created": shell_type != "failed"}}


def _step_export(exported: bool, reason: str | None = None) -> dict[str, Any]:
    doc = {"step_exported": exported}
    if reason:
        doc["reason"] = reason
    return doc


def _roundtrip(status: str) -> dict[str, Any]:
    return {"status": status}


def _partial_brep_faces(count: int) -> dict[str, Any]:
    return {"summary": {"generated_face_count": count}}


def _freeform_faces(count: int) -> dict[str, Any]:
    return {"summary": {"generated_face_count": count}}


def _trimming_readiness(faces: list[dict]) -> dict[str, Any]:
    return {"faces": faces, "status": "ready" if any(f.get("trimming_readiness") == "ready" for f in faces) else "partial"}


def _stitching_plan(can_closed: bool) -> dict[str, Any]:
    return {"summary": {"can_attempt_closed_shell": can_closed}}


# ── Part A: status classification ─────────────────────────────────────────────

def test_status_step_exported():
    inputs = _make_inputs(
        step_export=_step_export(True),
        roundtrip_verification=_roundtrip("passed"),
        sewing=_sewing_summary("closed_shell"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "step_exported"
    assert result["step_available"] is True
    assert result["step_verified"] is True
    assert result["cad_editability"] == "step_solid"
    assert result["recommended_next_action"] == "use_reconstructed_step"


def test_status_step_exported_roundtrip_warning():
    inputs = _make_inputs(
        step_export=_step_export(True),
        roundtrip_verification=_roundtrip("warning"),
        sewing=_sewing_summary("closed_shell"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "step_exported"
    assert result["step_verified"] is True


def test_status_closed_brep_solid_no_step():
    inputs = _make_inputs(
        step_export=_step_export(False, "solid invalid"),
        sewing=_sewing_summary("closed_shell"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "closed_brep_solid"
    assert result["step_available"] is False
    assert result["recommended_next_action"] == "export_step_or_verify"


def test_status_partial_brep():
    inputs = _make_inputs(
        partial_brep_faces=_partial_brep_faces(3),
        sewing=_sewing_summary("partial_shell"),
        stitching_plan=_stitching_plan(True),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "partial_brep"
    assert result["cad_editability"] == "partial_faces"
    assert result["step_available"] is False


def test_status_partial_brep_no_shell():
    inputs = _make_inputs(
        partial_brep_faces=_partial_brep_faces(3),
        sewing=_sewing_summary("failed"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "partial_brep"
    assert result["recommended_next_action"] == "use_partial_brep"


def test_status_freeform_candidate_only():
    inputs = _make_inputs(
        freeform_faces=_freeform_faces(2),
        freeform_trimming_readiness=_trimming_readiness([
            {"face_id": "f1", "trimming_readiness": "partial"},
        ]),
        region_graph=_region_graph([{"region_id": "r1", "area": 10.0}]),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "freeform_candidate_only"
    assert result["cad_editability"] == "candidate_faces_only"
    assert result["geometry_kind"] == "mixed"


def test_status_freeform_trimming_ready():
    inputs = _make_inputs(
        freeform_faces=_freeform_faces(2),
        freeform_trimming_readiness=_trimming_readiness([
            {"face_id": "f1", "trimming_readiness": "ready"},
        ]),
        region_graph=_region_graph([{"region_id": "r1", "area": 10.0}]),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "freeform_candidate_only"
    assert result["recommended_next_action"] == "attempt_freeform_trimming"


def test_status_freeform_trimming_not_ready_boundary_missing():
    inputs = _make_inputs(
        freeform_faces=_freeform_faces(1),
        freeform_trimming_readiness=_trimming_readiness([
            {"face_id": "f1", "trimming_readiness": "not_ready", "blocking_issues": ["boundary_missing"]},
        ]),
        region_graph=_region_graph([{"region_id": "r1", "area": 10.0}]),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "freeform_candidate_only"
    assert result["recommended_next_action"] == "improve_boundary"
    blocker_types = [b["type"] for b in result["blockers"]]
    assert "freeform_boundary_not_ready" in blocker_types


def test_status_mesh_only():
    inputs = _make_inputs(
        region_graph=_region_graph([{"region_id": "r1", "area": 10.0}]),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "mesh_only"
    assert result["geometry_kind"] == "mesh"
    assert result["cad_editability"] == "mesh_only"


def test_status_insufficient_data():
    inputs = _make_inputs()
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "insufficient_data"
    assert result["recommended_next_action"] == "request_user_input"


def test_step_exported_overrides_freeform():
    """If STEP is exported, freeform candidates should not downgrade status."""
    inputs = _make_inputs(
        step_export=_step_export(True),
        roundtrip_verification=_roundtrip("passed"),
        sewing=_sewing_summary("closed_shell"),
        freeform_faces=_freeform_faces(5),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert result["status"] == "step_exported"
    assert result["coverage"]["freeform_candidate_face_count"] == 5


# ── Part B: blocker extraction ────────────────────────────────────────────────

def test_blocker_step_roundtrip_failed():
    inputs = _make_inputs(
        step_export=_step_export(True),
        roundtrip_verification=_roundtrip("failed"),
        sewing=_sewing_summary("closed_shell"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    blocker_types = [b["type"] for b in result["blockers"]]
    assert "step_roundtrip_failed" in blocker_types
    assert result["status"] != "step_exported"  # critical blocker downgrades


def test_blocker_step_export_failed():
    inputs = _make_inputs(
        step_export=_step_export(False, "OCC solid invalid"),
        sewing=_sewing_summary("closed_shell"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    blocker_types = [b["type"] for b in result["blockers"]]
    assert "step_export_failed" in blocker_types


def test_blocker_sewing_failed():
    inputs = _make_inputs(
        sewing=_sewing_summary("failed"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    blocker_types = [b["type"] for b in result["blockers"]]
    assert "sewing_failed" in blocker_types


def test_blocker_no_duplicates():
    inputs = _make_inputs(
        sewing=_sewing_summary("partial_shell"),
        stitching_plan={"blocking_issues": [{"issue": "incomplete_stitching"}]},
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    # Should not produce duplicate blockers for the same root cause
    types = [b["type"] for b in result["blockers"]]
    assert types.count("incomplete_stitching") <= 1


# ── Part C: coverage and readiness ────────────────────────────────────────────

def test_coverage_computed():
    inputs = _make_inputs(
        region_graph=_region_graph([
            {"region_id": "r1", "area": 6.0},
            {"region_id": "r2", "area": 3.0},
            {"region_id": "r3", "area": 1.0},
        ]),
        surface_fit=_surface_fit([
            {"source_region_id": "r1", "surface_type": "plane"},
            {"source_region_id": "r2", "surface_type": "cylinder"},
        ]),
        freeform_fit=_surface_fit([
            {"source_region_id": "r3", "surface_type": "bspline"},
        ]),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    cov = result["coverage"]
    assert cov["analytic_fitted_area_fraction"] == 0.9
    assert cov["freeform_fitted_area_fraction"] == 0.1
    assert cov["region_count"] == 3
    assert cov["analytic_fitted_count"] == 2
    assert cov["freeform_fitted_count"] == 1


def test_readiness_flags():
    inputs = _make_inputs(
        reconstruction_readiness={"readiness": {"partial_brep_candidate": True}},
        freeform_readiness={"status": "ready"},
        freeform_faces=_freeform_faces(1),
        stitching_plan=_stitching_plan(True),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    rd = result["readiness"]
    assert rd["analytic_reconstruction_ready"] is True
    assert rd["freeform_evidence_ready"] is True
    assert rd["freeform_face_candidates_ready"] is True
    assert rd["closed_shell_possible"] is True


# ── Part D: honesty flags ─────────────────────────────────────────────────────

def test_honesty_step_exported():
    inputs = _make_inputs(
        step_export=_step_export(True),
        roundtrip_verification=_roundtrip("passed"),
        sewing=_sewing_summary("closed_shell"),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    h = result["honesty"]
    assert h["mesh_is_not_brep"] is False
    assert h["freeform_candidates_are_not_stitched"] is False
    assert h["production_cad_certified"] is False


def test_honesty_freeform_only():
    inputs = _make_inputs(
        freeform_faces=_freeform_faces(2),
        region_graph=_region_graph([{"region_id": "r1", "area": 10.0}]),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    h = result["honesty"]
    assert h["freeform_candidates_are_not_stitched"] is True


# ── Part E: integration / artifact writing ────────────────────────────────────

def test_artifact_written_into_package(tmp_path: Path):
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "aieng.package"}))
        zf.writestr(MESH_REGION_GRAPH_PATH, json.dumps(_region_graph([
            {"region_id": "r1", "area": 10.0},
        ])))

    result = write_mesh_to_cad_reconstruction_status(pkg)
    assert result["format"] == "aieng.mesh_to_cad.reconstruction_status.v0"

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert STATUS_PATH in names
        loaded = json.loads(zf.read(STATUS_PATH))
        assert loaded["status"] == "mesh_only"


def test_missing_artifacts_degrade_gracefully(tmp_path: Path):
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "aieng.package"}))

    result = write_mesh_to_cad_reconstruction_status(pkg)
    assert result["status"] == "insufficient_data"
    assert result["recommended_next_action"] == "request_user_input"
    assert result["coverage"]["region_count"] == 0


# ── Part F: source artifacts tracking ─────────────────────────────────────────

def test_source_artifacts_listed():
    inputs = _make_inputs(
        region_graph=_region_graph([{"region_id": "r1"}]),
        surface_fit=_surface_fit([{"source_region_id": "r1"}]),
        step_export=_step_export(True),
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    src = result["source_artifacts"]
    assert MESH_REGION_GRAPH_PATH in src
    assert MESH_SURFACE_FIT_PATH in src
    assert MESH_BREP_STEP_EXPORT_PATH in src


# ── Part G: warnings/errors propagation ───────────────────────────────────────

def test_warnings_propagated():
    inputs = _make_inputs(
        sewing={"summary": {"shell_type": "partial_shell"}, "warnings": ["some faces skipped"]},
    )
    result = build_mesh_to_cad_reconstruction_status("test.aieng", inputs)
    assert "some faces skipped" in result["warnings"]
