"""Tests for the simulation runner module."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.config import Settings

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project(settings: Settings, name: str, package: str) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package
    project["aieng_file"] = package
    save_project(settings, project)
    return project_id, pkg_path


_TOPOLOGY: dict[str, Any] = {
    "entities": [
        {"id": "face_001", "type": "face", "surface_type": "plane",
         "area": 5000.0, "normal": [0, 0, -1], "bounding_box": [0, 0, 0, 100, 50, 0]},
        {"id": "face_002", "type": "face", "surface_type": "plane",
         "area": 5000.0, "normal": [0, 0, 1], "bounding_box": [0, 0, 10, 100, 50, 10]},
        {"id": "face_003", "type": "face", "surface_type": "cylinder",
         "radius": 4.0, "bounding_box": [8, 8, 0, 12, 12, 10]},
    ]
}

_SETUP_YAML: dict[str, Any] = {
    "schema_version": "0.1",
    "ai_generated": True,
    "analysis_type": "static_structural",
    "material_name": "Al6061-T6",
    "material_reason": "lightweight bracket material",
    "materials": {
        "Al6061-T6": {
            "youngs_modulus_mpa": 69000,
            "poisson_ratio": 0.33,
            "density_kg_m3": 2700,
            "yield_strength_mpa": 276,
        }
    },
    "boundary_conditions": [
        {"id": "bc_001", "target_feature": "feat_hole_001", "type": "fixed", "reason": "bolted"},
    ],
    "loads": [
        {"id": "load_001", "target_feature": "feat_base_001", "type": "force",
         "value_n": 500.0, "direction": [0.0, 0.0, -1.0], "reason": "downward"},
    ],
    "mesh": {"target_size_mm": 2.5, "refinement_note": ""},
    "assumptions": [],
    "warnings": [],
}

_CAE_MAPPING: dict[str, Any] = {
    "schema_version": "0.1",
    "ai_generated": True,
    "mappings": [
        {
            "cae_entity": "FEAT_HOLE_001",
            "maps_to": {"feature_id": "feat_hole_001", "role": "fixed_support"},
            "face_ids": ["face_003"],
        },
        {
            "cae_entity": "FEAT_BASE_001_L",
            "maps_to": {"feature_id": "feat_base_001", "role": "load_application"},
            "face_ids": ["face_002"],
        },
    ],
}

_FAKE_STEP = b"ISO-10303-21;DATA;END-ISO-10303-21;"


def _build_test_package(pkg_path: Path, *, include_step: bool = True) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
        zf.writestr("geometry/topology_map.json", json.dumps(_TOPOLOGY))
        zf.writestr("simulation/setup.yaml", yaml.dump(_SETUP_YAML))
        zf.writestr("simulation/cae_mapping.json", json.dumps(_CAE_MAPPING))
        if include_step:
            zf.writestr("geometry/generated.step", _FAKE_STEP)


# ── check_simulation_tools ────────────────────────────────────────────────────

def test_check_tools_structure() -> None:
    from app.simulation_runner import check_simulation_tools

    result = check_simulation_tools()
    assert "gmsh" in result
    assert "calculix" in result
    assert "ready" in result
    assert "missing" in result
    assert isinstance(result["missing"], list)


def test_check_tools_ready_only_when_both_present() -> None:
    from app.simulation_runner import check_simulation_tools

    with patch("app.simulation_runner._gmsh_available", return_value=True), \
         patch("app.simulation_runner._find_ccx", return_value="/usr/bin/ccx"):
        result = check_simulation_tools()
        assert result["ready"] is True
        assert result["missing"] == []

    with patch("app.simulation_runner._gmsh_available", return_value=False), \
         patch("app.simulation_runner._find_ccx", return_value=None):
        result = check_simulation_tools()
        assert result["ready"] is False
        assert set(result["missing"]) == {"gmsh", "ccx"}


# ── _nodes_on_face ────────────────────────────────────────────────────────────

def test_nodes_on_planar_face() -> None:
    from app.simulation_runner import _nodes_on_face

    nodes = {
        1: (10.0, 10.0, 10.0),   # on top face (z=10)
        2: (50.0, 25.0, 10.0),   # on top face
        3: (50.0, 25.0, 5.0),    # mid-body — not on top
        4: (0.0, 0.0, 0.0),      # on bottom face (z=0)
    }
    top_face = {"type": "face", "surface_type": "plane",
                "bounding_box": [0, 0, 10, 100, 50, 10]}
    on_top = _nodes_on_face(nodes, top_face)
    assert 1 in on_top
    assert 2 in on_top
    assert 3 not in on_top
    assert 4 not in on_top


def test_nodes_on_cylinder_face() -> None:
    from app.simulation_runner import _nodes_on_face
    import math

    r = 4.0
    cx, cy = 10.0, 10.0
    nodes = {
        1: (cx + r, cy, 5.0),          # on cylinder surface
        2: (cx, cy + r, 3.0),          # on cylinder surface
        3: (cx, cy, 5.0),              # at center — NOT on surface
        4: (cx + r + 2, cy, 5.0),      # outside
    }
    cyl_face = {"type": "face", "surface_type": "cylinder", "radius": r,
                "bounding_box": [8, 8, 0, 12, 12, 10]}
    on_cyl = _nodes_on_face(nodes, cyl_face)
    assert 1 in on_cyl
    assert 2 in on_cyl
    assert 3 not in on_cyl
    assert 4 not in on_cyl


def test_nodes_on_face_empty_bbox() -> None:
    from app.simulation_runner import _nodes_on_face

    nodes = {1: (0.0, 0.0, 0.0)}
    result = _nodes_on_face(nodes, {"surface_type": "plane", "bounding_box": []})
    assert result == []


# ── _build_nsets ──────────────────────────────────────────────────────────────

def test_build_nsets_maps_cylinder_face() -> None:
    from app.simulation_runner import _build_nsets
    import math

    r = 4.0
    cx, cy = 10.0, 10.0
    nodes = {
        1: (cx + r, cy, 5.0),
        2: (cx, cy + r, 3.0),
        3: (50.0, 25.0, 10.0),  # top face node
    }
    nsets = _build_nsets(nodes, _TOPOLOGY, _CAE_MAPPING)
    # face_003 is a cylinder → FEAT_HOLE_001 NSET
    assert "FEAT_HOLE_001" in nsets
    assert 1 in nsets["FEAT_HOLE_001"]
    assert 2 in nsets["FEAT_HOLE_001"]
    assert 3 not in nsets["FEAT_HOLE_001"]


def test_build_nsets_empty_when_no_topology() -> None:
    from app.simulation_runner import _build_nsets

    nodes = {1: (0.0, 0.0, 0.0)}
    nsets = _build_nsets(nodes, {}, _CAE_MAPPING)
    # no topology entities → all NSETs are empty lists
    for node_list in nsets.values():
        assert node_list == []


# ── _unresolved_bc_load_faces (fail-fast on empty mapped NSETs) ────────────────

def test_unresolved_bc_load_faces_flags_empty_mapped_nset() -> None:
    from app.simulation_runner import _unresolved_bc_load_faces

    # bc target's NSET (FEAT_HOLE_001) caught no nodes; load target is fine.
    nsets = {"FEAT_HOLE_001": [], "FEAT_BASE_001_L": [3, 4]}
    problems = _unresolved_bc_load_faces(_SETUP_YAML, _CAE_MAPPING, nsets)
    assert len(problems) == 1
    assert problems[0]["kind"] == "boundary_condition"
    assert problems[0]["cae_entity"] == "FEAT_HOLE_001"
    assert problems[0]["face_pointers"] == ["@face:face_003"]


def test_unresolved_bc_load_faces_none_when_all_resolved() -> None:
    from app.simulation_runner import _unresolved_bc_load_faces

    nsets = {"FEAT_HOLE_001": [5], "FEAT_BASE_001_L": [4]}
    assert _unresolved_bc_load_faces(_SETUP_YAML, _CAE_MAPPING, nsets) == []


# ── _build_calculix_deck ──────────────────────────────────────────────────────

_MINIMAL_MESH_INP = """\
*Node
1, 0.0, 0.0, 0.0
2, 10.0, 0.0, 0.0
3, 5.0, 10.0, 0.0
4, 5.0, 5.0, 10.0
5, 14.0, 10.0, 5.0
*Element, type=C3D4, ELSET=EALL
1, 1, 2, 3, 4
"""
# Node 4 lands on the top face (face_002 → load NSET); node 5 on the cylinder
# surface (face_003 → fixed-support NSET) so the full-mock run resolves both
# the load and the BC and reaches the solver (see fail-fast on empty mappings).


def test_build_calculix_deck_structure() -> None:
    from app.simulation_runner import _build_calculix_deck

    nsets = {
        "FEAT_HOLE_001": [1, 2],
        "FEAT_BASE_001_L": [3, 4],
    }
    deck, bc_count, load_count = _build_calculix_deck(_MINIMAL_MESH_INP, _SETUP_YAML, nsets, _CAE_MAPPING)

    assert "*MATERIAL" in deck
    assert "Al6061_T6" in deck
    assert "*ELASTIC" in deck
    assert "*SOLID SECTION" in deck
    assert "*STEP" in deck
    assert "*STATIC" in deck
    assert "*END STEP" in deck
    assert "*NODE FILE" in deck
    assert "*EL FILE" in deck
    assert bc_count == 1
    assert load_count == 1


def test_build_calculix_deck_nset_definitions() -> None:
    from app.simulation_runner import _build_calculix_deck

    nsets = {"FEAT_HOLE_001": [10, 20, 30]}
    deck, _, _ = _build_calculix_deck(_MINIMAL_MESH_INP, _SETUP_YAML, nsets, _CAE_MAPPING)

    assert "NSET=FEAT_HOLE_001" in deck
    assert "10, 20, 30" in deck


def test_build_calculix_deck_no_bc_when_nset_empty() -> None:
    from app.simulation_runner import _build_calculix_deck

    nsets = {"FEAT_HOLE_001": [], "FEAT_BASE_001_L": []}
    _, bc_count, load_count = _build_calculix_deck(_MINIMAL_MESH_INP, _SETUP_YAML, nsets, _CAE_MAPPING)

    assert bc_count == 0
    assert load_count == 0


# ── endpoint: requires confirmed=true ─────────────────────────────────────────

def test_run_simulation_requires_confirmed(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)

    project_id, pkg_path = _make_project(settings, "sim-test", "sim.aieng")
    _build_test_package(pkg_path)

    resp = client.post(f"/api/projects/{project_id}/run-simulation", json={})
    assert resp.status_code == 400
    assert "confirmed" in resp.text


# ── endpoint: missing package ─────────────────────────────────────────────────

def test_run_simulation_missing_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)

    from app.main import default_project, save_project
    project = save_project(settings, default_project("no-pkg"))
    project_id = project["id"]

    resp = client.post(
        f"/api/projects/{project_id}/run-simulation",
        json={"confirmed": True},
    )
    assert resp.status_code == 404


# ── endpoint: tools unavailable ───────────────────────────────────────────────

def test_run_simulation_tools_unavailable(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)

    project_id, pkg_path = _make_project(settings, "sim-notools", "sim_notools.aieng")
    _build_test_package(pkg_path)

    with patch("app.simulation_runner._gmsh_available", return_value=False), \
         patch("app.simulation_runner._find_ccx", return_value=None):
        resp = client.post(
            f"/api/projects/{project_id}/run-simulation",
            json={"confirmed": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "tools_unavailable"
    assert "gmsh" in data["missing_tools"]
    assert "ccx" in data["missing_tools"]


# ── endpoint: missing setup.yaml ─────────────────────────────────────────────

def test_run_simulation_missing_setup_yaml(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)

    project_id, pkg_path = _make_project(settings, "sim-nosetup", "sim_nosetup.aieng")
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("geometry/generated.step", _FAKE_STEP)

    with patch("app.simulation_runner._gmsh_available", return_value=True), \
         patch("app.simulation_runner._find_ccx", return_value="/usr/bin/ccx"):
        resp = client.post(
            f"/api/projects/{project_id}/run-simulation",
            json={"confirmed": True},
        )

    assert resp.status_code == 422
    assert "setup.yaml" in resp.text


# ── endpoint: full mock run ───────────────────────────────────────────────────

_MOCK_FRD_METRICS = {
    "schema_version": "0.1",
    "metrics_source": "CalculiX",
    "load_cases": {
        "load_case_001": {
            "max_displacement_mm": 0.123,
            "max_von_mises_stress_mpa": 45.6,
        }
    },
    "warnings": [],
}


def _fake_mesh(step_path, work_dir, mesh_size_mm):
    """Write a minimal valid .inp mesh file without running Gmsh."""
    out = work_dir / "mesh.inp"
    out.write_text(_MINIMAL_MESH_INP)
    return out


def _fake_calculix(inp_path, work_dir, timeout=180):
    """Pretend CalculiX succeeded and create a fake .frd file."""
    frd = work_dir / f"{inp_path.stem}.frd"
    frd.write_bytes(b"fake frd content")
    return 0, "CalculiX completed\n", frd


def test_run_simulation_full_mock(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)

    project_id, pkg_path = _make_project(settings, "sim-full", "sim_full.aieng")
    _build_test_package(pkg_path)

    with patch("app.simulation_runner._gmsh_available", return_value=True), \
         patch("app.simulation_runner._find_ccx", return_value="/usr/bin/ccx"), \
         patch("app.simulation_runner._mesh_with_gmsh", side_effect=_fake_mesh), \
         patch("app.simulation_runner._run_calculix", side_effect=_fake_calculix), \
         patch("app.simulation_runner._extract_metrics", return_value=_MOCK_FRD_METRICS):
        resp = client.post(
            f"/api/projects/{project_id}/run-simulation",
            json={"confirmed": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["von_mises_max_mpa"] == pytest.approx(45.6)
    assert data["displacement_max_mm"] == pytest.approx(0.123)
    assert "simulation/solver_log.txt" in data["written_artifacts"]
    assert "simulation/result.frd" in data["written_artifacts"]
    assert "simulation/results_summary.json" in data["written_artifacts"]

    # Verify artifacts written to package
    with zipfile.ZipFile(pkg_path, "r") as zf:
        names = zf.namelist()
        assert "simulation/solver_log.txt" in names
        assert "simulation/results_summary.json" in names
        assert "simulation/result.frd" in names
        summary = json.loads(zf.read("simulation/results_summary.json"))
        assert summary["status"] == "success"
        assert summary["von_mises_max_mpa"] == pytest.approx(45.6)


def _fake_mesh_missing_hole(step_path, work_dir, mesh_size_mm):
    """Mesh that covers the top (load) face but NOT the cylinder (BC) face."""
    out = work_dir / "mesh.inp"
    out.write_text(
        "*Node\n"
        "1, 0.0, 0.0, 0.0\n"
        "4, 5.0, 5.0, 10.0\n"   # on top face → load NSET resolves; nothing on hole
        "*Element, type=C3D4, ELSET=EALL\n"
        "1, 1, 1, 1, 4\n"
    )
    return out


def test_run_simulation_aborts_on_unresolved_face(tmp_path: Path) -> None:
    """A load/BC face that matches zero mesh nodes aborts before the solver."""
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)

    project_id, pkg_path = _make_project(settings, "sim-unresolved", "sim_unresolved.aieng")
    _build_test_package(pkg_path)

    with patch("app.simulation_runner._gmsh_available", return_value=True), \
         patch("app.simulation_runner._find_ccx", return_value="/usr/bin/ccx"), \
         patch("app.simulation_runner._mesh_with_gmsh", side_effect=_fake_mesh_missing_hole), \
         patch("app.simulation_runner._run_calculix", side_effect=_fake_calculix) as ccx, \
         patch("app.simulation_runner._extract_metrics", return_value=_MOCK_FRD_METRICS):
        resp = client.post(
            f"/api/projects/{project_id}/run-simulation",
            json={"confirmed": True},
        )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "unresolved_face_mapping"
    assert any("@face:face_003" in p["face_pointers"] for p in detail["unresolved"])
    # The solver must NOT have been invoked.
    ccx.assert_not_called()


# ── GET /api/simulation/tools ─────────────────────────────────────────────────

def test_get_simulation_tools_endpoint(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    resp = client.get("/api/simulation/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "gmsh" in data
    assert "calculix" in data
    assert "ready" in data
    assert "missing" in data
