"""Tests for text-to-CAD generation (build123d backend)."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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


def _make_project(settings: Settings, name: str) -> str:
    from app.main import default_project, save_project
    project = save_project(settings, default_project(name))
    return project["id"]


# ── sample topology ───────────────────────────────────────────────────────────

_SAMPLE_TOPOLOGY: dict = {
    "format_version": "0.1",
    "entities": [
        {
            "id": "body_001",
            "type": "solid",
            "bounding_box": [0.0, 0.0, 0.0, 100.0, 50.0, 10.0],
        },
        {
            "id": "face_001",
            "type": "face",
            "surface_type": "plane",
            "area": 5000.0,
            "normal": [0.0, 0.0, -1.0],
            "center": [50.0, 25.0, 0.0],
            "bounding_box": [0.0, 0.0, 0.0, 100.0, 50.0, 0.0],
        },
        {
            "id": "face_002",
            "type": "face",
            "surface_type": "plane",
            "area": 5000.0,
            "normal": [0.0, 0.0, 1.0],
            "center": [50.0, 25.0, 10.0],
            "bounding_box": [0.0, 0.0, 10.0, 100.0, 50.0, 10.0],
        },
        {
            "id": "face_003",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "center": [10.0, 10.0, 5.0],
            "bounding_box": [8.0, 8.0, 0.0, 12.0, 12.0, 10.0],
        },
        {
            "id": "face_004",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "center": [90.0, 10.0, 5.0],
            "bounding_box": [88.0, 8.0, 0.0, 92.0, 12.0, 10.0],
        },
        {
            "id": "face_005",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "center": [10.0, 40.0, 5.0],
            "bounding_box": [8.0, 38.0, 0.0, 12.0, 42.0, 10.0],
        },
        {
            "id": "face_006",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "center": [90.0, 40.0, 5.0],
            "bounding_box": [88.0, 38.0, 0.0, 92.0, 42.0, 10.0],
        },
    ],
}

_SAMPLE_CODE = """\
with BuildPart() as bp:
    Box(100, 50, 10)
    with Locations((10, 10, 0), (90, 10, 0), (10, 40, 0), (90, 40, 0)):
        Hole(radius=4, depth=10)
result = bp.part
"""


# ── _coerce_code ──────────────────────────────────────────────────────────────

def test_coerce_code_strips_python_fence() -> None:
    from app.cad_generation import _coerce_code

    raw = "```python\nresult = Box(10, 10, 10)\n```"
    assert _coerce_code(raw) == "result = Box(10, 10, 10)"


def test_coerce_code_strips_plain_fence() -> None:
    from app.cad_generation import _coerce_code

    raw = "```\nresult = Box(10, 10, 10)\n```"
    assert _coerce_code(raw) == "result = Box(10, 10, 10)"


def test_coerce_code_plain_text_unchanged() -> None:
    from app.cad_generation import _coerce_code

    raw = "result = Box(10, 10, 10)"
    assert _coerce_code(raw) == raw


# ── _topology_to_feature_graph ────────────────────────────────────────────────

def test_feature_graph_detects_bolt_pattern() -> None:
    from app.cad_generation import _topology_to_feature_graph

    fg = _topology_to_feature_graph(_SAMPLE_TOPOLOGY)
    patterns = [f for f in fg["features"] if f["type"] == "mounting_hole_pattern"]
    assert len(patterns) == 1
    assert patterns[0]["parameters"]["count"] == 4
    assert set(patterns[0]["geometry_refs"]["faces"]) == {
        "face_003", "face_004", "face_005", "face_006"
    }


def test_feature_graph_detects_base_plate() -> None:
    from app.cad_generation import _topology_to_feature_graph

    fg = _topology_to_feature_graph(_SAMPLE_TOPOLOGY)
    plates = [f for f in fg["features"] if f["type"] == "base_plate"]
    assert len(plates) == 1
    assert plates[0]["geometry_refs"]["faces"] == ["face_001"]


def test_feature_graph_empty_topology() -> None:
    from app.cad_generation import _topology_to_feature_graph

    fg = _topology_to_feature_graph({})
    assert fg == {"features": []}


def test_feature_graph_surfaces_named_parts() -> None:
    """Named solids (from build123d .label) become named_part features the agent
    can reference, with id derived from the body id for stability."""
    from app.cad_generation import _topology_to_feature_graph

    topo = {
        "entities": [
            {"id": "body_001", "type": "solid", "name": "fuselage", "bounding_box": [0, 0, 0, 40, 40, 10]},
            {"id": "body_002", "type": "solid", "name": "motor_pod_FL", "bounding_box": [50, 0, 0, 56, 0, 30]},
            {"id": "face_001", "type": "face", "surface_type": "plane", "body_id": "body_001"},
            {"id": "face_002", "type": "face", "surface_type": "cylinder", "radius": 3.0, "body_id": "body_002"},
        ]
    }
    fg = _topology_to_feature_graph(topo)
    named = [f for f in fg["features"] if f["type"] == "named_part"]
    assert [f["name"] for f in named] == ["fuselage", "motor_pod_FL"]
    fuselage = next(f for f in named if f["name"] == "fuselage")
    assert fuselage["id"] == "feat_body_001"
    assert fuselage["geometry_refs"]["body"] == "body_001"
    assert fuselage["geometry_refs"]["faces"] == ["face_001"]


def test_feature_graph_unnamed_solid_has_no_named_part() -> None:
    from app.cad_generation import _topology_to_feature_graph

    topo = {"entities": [{"id": "body_001", "type": "solid", "bounding_box": [0, 0, 0, 10, 10, 10]}]}
    fg = _topology_to_feature_graph(topo)
    assert [f for f in fg["features"] if f["type"] == "named_part"] == []


def test_feature_graph_two_hole_groups() -> None:
    from app.cad_generation import _topology_to_feature_graph

    topo = {
        "entities": [
            {"id": "body_001", "type": "solid", "bounding_box": [0, 0, 0, 100, 100, 20]},
            {"id": "f1", "type": "face", "surface_type": "cylinder", "radius": 4.0, "area": 251.3, "center": [10, 10, 10]},
            {"id": "f2", "type": "face", "surface_type": "cylinder", "radius": 4.0, "area": 251.3, "center": [90, 10, 10]},
            {"id": "f3", "type": "face", "surface_type": "cylinder", "radius": 8.0, "area": 502.6, "center": [50, 50, 10]},
            {"id": "f4", "type": "face", "surface_type": "cylinder", "radius": 8.0, "area": 502.6, "center": [50, 80, 10]},
        ]
    }
    fg = _topology_to_feature_graph(topo)
    types = [f["type"] for f in fg["features"]]
    # Both groups have 2 cylinders → both become "mounting_hole"
    assert types.count("mounting_hole") == 2


# ── Build123dBackend.can_generate ─────────────────────────────────────────────

def test_build123d_backend_can_generate_true() -> None:
    from app.cad_generation import Build123dBackend

    backend = Build123dBackend(MagicMock())
    fake_module = MagicMock()
    with patch.dict("sys.modules", {"build123d": fake_module}):
        assert backend.can_generate() is True


def test_build123d_backend_cannot_generate_without_build123d() -> None:
    from app.cad_generation import Build123dBackend

    backend = Build123dBackend(MagicMock())
    with patch.dict("sys.modules", {"build123d": None}):
        assert backend.can_generate() is False


# ── _execute_build123d_code ───────────────────────────────────────────────────

def test_execute_build123d_code_success(tmp_path: Path) -> None:
    from app.cad_generation import _execute_build123d_code

    fake_step = b"ISO-10303-21;"
    fake_stl = b"solid result\nendsolid result"
    fake_glb = b"glTF\x02\x00\x00\x00"
    fake_topo = json.dumps(_SAMPLE_TOPOLOGY)

    def _fake_run(cmd, **kwargs):
        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stderr = ""
        out_step = Path(cmd[2])
        out_topo = Path(cmd[3])
        out_stl = Path(cmd[4])
        out_glb = Path(cmd[5])
        out_step.write_bytes(fake_step)
        out_topo.write_text(fake_topo, encoding="utf-8")
        out_stl.write_bytes(fake_stl)
        out_glb.write_bytes(fake_glb)
        return result_mock

    with patch("app.cad_generation.subprocess.run", side_effect=_fake_run):
        step_bytes, stl_bytes, glb_bytes, topo = _execute_build123d_code("result = Box(10, 10, 10)")

    assert step_bytes == fake_step
    assert stl_bytes == fake_stl
    assert glb_bytes == fake_glb
    assert topo["format_version"] == "0.1"


def test_execute_build123d_code_failure() -> None:
    from app.cad_generation import _execute_build123d_code

    fail_mock = MagicMock()
    fail_mock.returncode = 1
    fail_mock.stderr = "NameError: name 'result' is not defined"

    with patch("app.cad_generation.subprocess.run", return_value=fail_mock):
        with pytest.raises(RuntimeError, match="build123d execution failed"):
            _execute_build123d_code("Box(10, 10, 10)  # missing result =")


# ── thumbnail rendering ───────────────────────────────────────────────────────

def test_render_mesh_thumbnail_returns_png_base64() -> None:
    """A valid ASCII STL renders to a base64-encoded PNG (headless, no GL)."""
    import base64

    from app.cad_generation import render_mesh_thumbnail

    # Minimal single-triangle ASCII STL.
    stl = (
        b"solid t\n"
        b"facet normal 0 0 1\n outer loop\n"
        b"  vertex 0 0 0\n  vertex 10 0 0\n  vertex 0 10 0\n"
        b" endloop\nendfacet\n"
        b"endsolid t\n"
    )
    out = render_mesh_thumbnail(stl)
    assert out is not None
    raw = base64.b64decode(out)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_mesh_thumbnail_empty_bytes_returns_none() -> None:
    from app.cad_generation import render_mesh_thumbnail

    assert render_mesh_thumbnail(b"") is None


# ── named parts + append mode (real build123d) ────────────────────────────────

def test_execute_build123d_captures_part_labels(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "named")
    code = (
        "from build123d import *\n"
        "body = Box(40, 40, 10); body.label = 'fuselage'\n"
        "fl = Cylinder(3, 30); fl.label = 'motor_pod_FL'\n"
        "result = Compound(children=[body, fl])\n"
    )
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["status"] == "ok"
    named = [f for f in out["feature_graph"]["features"] if f["type"] == "named_part"]
    assert sorted(f["name"] for f in named) == ["fuselage", "motor_pod_FL"]


def test_execute_build123d_append_preserves_prior_parts(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "append")
    base = (
        "from build123d import *\n"
        "body = Box(40, 40, 10); body.label = 'fuselage'\n"
        "result = Compound(children=[body])\n"
    )
    assert execute_build123d_code(settings, pid, {"code": base, "thumbnail": False})["status"] == "ok"

    add = (
        "from build123d import *\n"
        "arm = Cylinder(3, 30); arm.label = 'motor_pod_FL'\n"
        "result = Compound(children=[previous_result, arm])\n"
    )
    out = execute_build123d_code(settings, pid, {"code": add, "mode": "append", "thumbnail": False})
    assert out["status"] == "ok"
    named = {f["name"] for f in out["feature_graph"]["features"] if f["type"] == "named_part"}
    assert named == {"fuselage", "motor_pod_FL"}
    # response summary fields: append consumed the base and added only the new part
    assert out["mode"] == "append"
    assert out["used_base"] is True
    assert out["named_parts"] == ["fuselage", "motor_pod_FL"]
    assert out["parts_added"] == ["motor_pod_FL"]


def test_execute_build123d_replace_summary_fields(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "replace-summary")
    code = (
        "from build123d import *\n"
        "b = Box(40, 40, 10); b.label = 'fuselage'\n"
        "result = Compound(children=[b])\n"
    )
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["mode"] == "replace"
    assert out["used_base"] is False
    # in a fresh replace, everything is newly added
    assert out["named_parts"] == ["fuselage"]
    assert out["parts_added"] == ["fuselage"]


def test_execute_build123d_append_without_base_errors(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "no-base")
    out = execute_build123d_code(
        settings, pid,
        {"code": "from build123d import *\nresult = Box(1, 1, 1)", "mode": "append", "thumbnail": False},
    )
    assert out["status"] == "error"
    assert out["code"] == "append_without_base"


def test_read_cad_source_no_geometry_yet(tmp_path: Path) -> None:
    from app.cad_generation import read_cad_source

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "empty")
    out = read_cad_source(settings, pid)
    assert out["status"] == "ok"
    assert out["has_base"] is False
    assert out["source"] is None
    assert out["named_parts"] == []
    assert out["mode"] == "build123d"


def test_read_cad_source_after_build(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code, read_cad_source

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "with-geo")
    code = (
        "from build123d import *\n"
        "b = Box(40, 40, 10); b.label = 'fuselage'\n"
        "result = Compound(children=[b])\n"
    )
    execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    out = read_cad_source(settings, pid)
    assert out["status"] == "ok"
    assert out["has_base"] is True
    assert "Box(40, 40, 10)" in out["source"]
    assert out["named_parts"] == ["fuselage"]


# ── endpoint integration tests ────────────────────────────────────────────────

def test_generate_cad_endpoint_missing_description(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)
    project_id = _make_project(settings, "test-proj")

    resp = client.post(f"/api/projects/{project_id}/generate-cad", json={})
    assert resp.status_code == 400
    assert "description" in resp.text


def test_generate_cad_endpoint_no_build123d(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)
    project_id = _make_project(settings, "no-b3d")

    with patch("app.cad_generation.Build123dBackend.can_generate", return_value=False):
        resp = client.post(
            f"/api/projects/{project_id}/generate-cad",
            json={"description": "simple bracket"},
        )
    assert resp.status_code == 503
    assert "build123d" in resp.text


_FAKE_STEP = b"ISO-10303-21;"
_FAKE_STL = b"solid result\nendsolid result"
_FAKE_GLB = b"glTF\x02\x00\x00\x00"  # minimal GLB magic


def _fake_execute_ok(code, timeout=60):
    return _FAKE_STEP, _FAKE_STL, _FAKE_GLB, _SAMPLE_TOPOLOGY


def test_generate_cad_endpoint_dry_run(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)
    project_id = _make_project(settings, "dry-run")

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation.call_claude_for_build123d_code", return_value=_SAMPLE_CODE),
        patch("app.cad_generation._execute_build123d_code", side_effect=_fake_execute_ok),
    ):
        resp = client.post(
            f"/api/projects/{project_id}/generate-cad",
            json={
                "description": "100x50x10mm plate with 4 corner bolt holes r=4mm",
                "write_files": False,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == "build123d"
    assert "result = bp.part" in data["generated_code"]
    assert data["topology_summary"]["face_count"] == 6
    assert data["written_artifacts"] == []
    assert data["preview_format"] == "glb"


def test_generate_cad_endpoint_writes_artifacts(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)
    project_id = _make_project(settings, "write-test")

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation.call_claude_for_build123d_code", return_value=_SAMPLE_CODE),
        patch("app.cad_generation._execute_build123d_code", side_effect=_fake_execute_ok),
    ):
        resp = client.post(
            f"/api/projects/{project_id}/generate-cad",
            json={
                "description": "100x50x10mm plate with 4 corner bolt holes r=4mm",
                "write_files": True,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "geometry/generated.step" in data["written_artifacts"]
    assert "geometry/preview.stl" in data["written_artifacts"]
    assert "geometry/preview.glb" in data["written_artifacts"]
    assert "geometry/topology_map.json" in data["written_artifacts"]
    assert "graph/feature_graph.json" in data["written_artifacts"]
    assert "geometry/source.py" in data["written_artifacts"]

    from app.main import project_dir
    from app.project_io import get_project
    project = get_project(settings, project_id)
    pkg_path = project_dir(settings, project_id) / project["aieng_file"]
    assert pkg_path.exists()

    with zipfile.ZipFile(pkg_path, "r") as zf:
        names = zf.namelist()
        assert "geometry/generated.step" in names
        assert "geometry/preview.stl" in names
        assert "geometry/preview.glb" in names
        assert "geometry/topology_map.json" in names
        assert "geometry/source.py" in names

        topo = json.loads(zf.read("geometry/topology_map.json"))
        assert topo["format_version"] == "0.1"

        fg = json.loads(zf.read("graph/feature_graph.json"))
        assert len(fg["features"]) >= 1


# ── cad-preview endpoint ──────────────────────────────────────────────────────

def test_cad_preview_endpoint_returns_glb(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)
    project_id = _make_project(settings, "preview-test")

    # First generate to create the package with both preview.stl and preview.glb
    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation.call_claude_for_build123d_code", return_value=_SAMPLE_CODE),
        patch("app.cad_generation._execute_build123d_code", side_effect=_fake_execute_ok),
    ):
        client.post(
            f"/api/projects/{project_id}/generate-cad",
            json={"description": "simple plate", "write_files": True},
        )

    resp = client.get(f"/api/projects/{project_id}/cad-preview")
    assert resp.status_code == 200
    # GLB is preferred over STL when available
    assert resp.content == _FAKE_GLB
    assert resp.headers["content-type"] == "model/gltf-binary"


def test_cad_preview_endpoint_404_without_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)
    project_id = _make_project(settings, "no-pkg-preview")

    resp = client.get(f"/api/projects/{project_id}/cad-preview")
    assert resp.status_code == 404


# ── refine-cad endpoint ───────────────────────────────────────────────────────

def test_refine_cad_endpoint_missing_feedback(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)
    project_id = _make_project(settings, "refine-no-feedback")

    resp = client.post(f"/api/projects/{project_id}/refine-cad", json={})
    assert resp.status_code == 400
    assert "feedback" in resp.text


def test_refine_cad_endpoint_no_source(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)
    project_id = _make_project(settings, "refine-no-source")

    # Create empty package (no source.py)
    from app.main import project_dir, save_project
    from app.project_io import get_project
    project = get_project(settings, project_id)
    pkg_path = project_dir(settings, project_id) / "test.aieng"
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("manifest.json", "{}")
    project["aieng_file"] = "test.aieng"
    save_project(settings, project)

    with patch("app.cad_generation.Build123dBackend.can_generate", return_value=True):
        resp = client.post(
            f"/api/projects/{project_id}/refine-cad",
            json={"feedback": "make it taller"},
        )
    assert resp.status_code == 404


def test_refine_cad_endpoint_success(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)
    project_id = _make_project(settings, "refine-ok")

    _REFINED_CODE = "with BuildPart() as bp:\n    Box(100, 50, 15)\nresult = bp.part\n"

    # First generate
    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation.call_claude_for_build123d_code", return_value=_SAMPLE_CODE),
        patch("app.cad_generation._execute_build123d_code", side_effect=_fake_execute_ok),
    ):
        client.post(
            f"/api/projects/{project_id}/generate-cad",
            json={"description": "plate", "write_files": True},
        )

    # Then refine
    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation.call_claude_for_build123d_refinement", return_value=_REFINED_CODE),
        patch("app.cad_generation._execute_build123d_code", side_effect=_fake_execute_ok),
    ):
        resp = client.post(
            f"/api/projects/{project_id}/refine-cad",
            json={"feedback": "make thickness 15mm", "write_files": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["refined_code"] == _REFINED_CODE
    assert data["preview_format"] == "glb"
    assert "geometry/preview.stl" in data["written_artifacts"]
    assert "geometry/preview.glb" in data["written_artifacts"]


# ── execute_build123d_code (agent-supplied code, no LLM) ──────────────────────

def _fake_stream_ok(code, timeout=60):
    """Mimic _execute_build123d_code_streaming: a heartbeat then a result."""
    yield {"kind": "heartbeat", "elapsed_s": 0}
    yield {
        "kind": "result",
        "step_bytes": _FAKE_STEP,
        "stl_bytes": _FAKE_STL,
        "glb_bytes": _FAKE_GLB,
        "topo": _SAMPLE_TOPOLOGY,
    }


def _fake_stream_error(code, timeout=60):
    yield {"kind": "heartbeat", "elapsed_s": 0}
    yield {"kind": "error", "error": "NameError: name 'Bx' is not defined"}


def test_execute_build123d_code_writes_artifacts(tmp_path: Path) -> None:
    from app import cad_generation

    settings = _make_settings(tmp_path)
    create_app(settings)
    project_id = _make_project(settings, "agent-cad")

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation._execute_build123d_code_streaming", side_effect=_fake_stream_ok),
    ):
        result = cad_generation.execute_build123d_code(
            settings,
            project_id,
            {"code": "from build123d import *\nresult = Box(100, 50, 10)"},
        )

    assert result["status"] == "ok"
    assert result["backend"] == "build123d"
    assert result["topology_summary"]["face_count"] == 6
    assert "geometry/source.py" in result["written_artifacts"]
    assert "geometry/preview.glb" in result["written_artifacts"]
    assert result["preview_format"] == "glb"


def test_execute_build123d_code_persists_source(tmp_path: Path) -> None:
    """The exact agent-supplied code must land in geometry/source.py."""
    from app import cad_generation
    from app.main import get_project
    from app.project_io import resolve_project_path

    settings = _make_settings(tmp_path)
    create_app(settings)
    project_id = _make_project(settings, "agent-cad-src")
    code = "from build123d import *\nresult = Box(120, 60, 8)"

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation._execute_build123d_code_streaming", side_effect=_fake_stream_ok),
    ):
        cad_generation.execute_build123d_code(settings, project_id, {"code": code})

    project = get_project(settings, project_id)
    pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    with zipfile.ZipFile(pkg_path, "r") as zf:
        source = zf.read("geometry/source.py").decode("utf-8")
    assert "Box(120, 60, 8)" in source


def test_execute_build123d_code_dry_run_no_write(tmp_path: Path) -> None:
    from app import cad_generation

    settings = _make_settings(tmp_path)
    create_app(settings)
    project_id = _make_project(settings, "agent-cad-dry")

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation._execute_build123d_code_streaming", side_effect=_fake_stream_ok),
    ):
        result = cad_generation.execute_build123d_code(
            settings, project_id, {"code": "from build123d import *\nresult = Box(1,1,1)", "write_files": False},
        )

    assert result["status"] == "ok"
    assert result["written_artifacts"] == []


def test_execute_build123d_code_missing_code(tmp_path: Path) -> None:
    from app import cad_generation

    settings = _make_settings(tmp_path)
    create_app(settings)
    project_id = _make_project(settings, "agent-cad-nocode")

    result = cad_generation.execute_build123d_code(settings, project_id, {})
    assert result["status"] == "error"
    assert result["code"] == "missing_code"


def test_execute_build123d_code_execution_error(tmp_path: Path) -> None:
    from app import cad_generation

    settings = _make_settings(tmp_path)
    create_app(settings)
    project_id = _make_project(settings, "agent-cad-err")

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation._execute_build123d_code_streaming", side_effect=_fake_stream_error),
    ):
        result = cad_generation.execute_build123d_code(
            settings, project_id, {"code": "result = Bx(1,1,1)"},
        )

    assert result["status"] == "error"
    assert result["code"] == "execution_failed"
    assert "NameError" in result["message"]


def test_execute_build123d_code_build123d_unavailable(tmp_path: Path) -> None:
    from app import cad_generation

    settings = _make_settings(tmp_path)
    create_app(settings)
    project_id = _make_project(settings, "agent-cad-unavail")

    with patch("app.cad_generation.Build123dBackend.can_generate", return_value=False):
        result = cad_generation.execute_build123d_code(
            settings, project_id, {"code": "from build123d import *\nresult = Box(1,1,1)"},
        )

    assert result["status"] == "error"
    assert result["code"] == "build123d_unavailable"


def test_cad_execute_build123d_tool_registered_with_approval() -> None:
    from app import runtime
    from app.app_factory import create_app as _ca

    _ca()
    tools = {t["name"]: t for t in runtime.list_tools_for_mcp()}
    assert "cad.execute_build123d" in tools
    assert tools["cad.execute_build123d"]["requires_approval"] is True
    schema = tools["cad.execute_build123d"]["input_schema"]
    assert "code" in schema["properties"]
    assert set(schema["required"]) == {"project_id", "code"}
