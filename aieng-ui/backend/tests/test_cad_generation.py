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


def _load_topology_map(settings: Settings, project_id: str) -> dict:
    # execute_build123d_code returns a compact topology_summary and writes the
    # full topology_map to the package; read it from there.
    from app.main import project_dir
    from app.project_io import get_project
    project = get_project(settings, project_id)
    pkg_path = project_dir(settings, project_id) / project["aieng_file"]
    with zipfile.ZipFile(pkg_path, "r") as zf:
        return json.loads(zf.read("geometry/topology_map.json"))


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
    assert fg["features"] == []


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


def test_feature_graph_surfaces_standard_parts_with_provenance() -> None:
    from app.cad_generation import _named_parts_from_feature_graph, _topology_to_feature_graph

    topo = {
        "entities": [
            {
                "id": "body_001",
                "type": "solid",
                "name": "mounting_bolt_M6",
                "bounding_box": [-3, -3, 0, 3, 3, 12],
                "standard_part": True,
                "source_library": "bd_warehouse",
                "source_module": "bd_warehouse.fastener",
                "source_class": "SocketHeadCapScrew",
                "canonical_type": "screw",
                "designation": "M6-1",
                "object_label": "mounting_bolt_M6",
                "detection_method": "bd_warehouse_type",
                "confidence": "high",
            },
            {
                "id": "face_001",
                "type": "face",
                "surface_type": "cylinder",
                "radius": 3.0,
                "body_id": "body_001",
            },
        ]
    }

    fg = _topology_to_feature_graph(topo)

    standard = [f for f in fg["features"] if f["type"] == "standard_part"]
    assert len(standard) == 1
    screw = standard[0]
    assert screw["name"] == "mounting_bolt_M6"
    assert screw["standard_part"] is True
    assert screw["source_library"] == "bd_warehouse"
    assert screw["canonical_type"] == "screw"
    assert screw["designation"] == "M6-1"
    assert screw["recognition"] == {"method": "bd_warehouse_type", "confidence": "high"}
    assert screw["geometry_refs"] == {"body": "body_001", "faces": ["face_001"]}
    assert _named_parts_from_feature_graph(fg) == ["mounting_bolt_M6"]
    assert fg["metadata"]["standard_parts"]["count"] == 1
    assert fg["metadata"]["standard_parts"]["by_canonical_type"] == {"screw": 1}


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


def test_execute_build123d_code_with_bd_warehouse_fastener() -> None:
    """#3: bd_warehouse standard-parts modules are pre-bound in the runner
    namespace, so agent code can produce spec-compliant ISO/DIN/ANSI parts
    (a real M6 socket-head cap screw) instead of approximating with primitives.
    Runs the real subprocess; skipped when build123d/bd_warehouse are absent."""
    pytest.importorskip("build123d")
    pytest.importorskip("bd_warehouse")
    from app.cad_generation import _execute_build123d_code, _topology_to_feature_graph

    code = (
        "screw = fastener.SocketHeadCapScrew('M6-1', length=12, simple=True)\n"
        "screw.label = 'mounting_bolt_M6'\n"
        "result = screw\n"
    )
    step_bytes, stl_bytes, _glb_bytes, topo = _execute_build123d_code(code)
    assert step_bytes[:13] == b"ISO-10303-21;"
    assert stl_bytes
    assert isinstance(topo, dict) and topo.get("entities")
    screw_body = next(
        entity for entity in topo["entities"]
        if entity.get("type") == "solid" and entity.get("name") == "mounting_bolt_M6"
    )
    assert screw_body["standard_part"] is True
    assert screw_body["source_library"] == "bd_warehouse"
    assert screw_body["source_module"] == "bd_warehouse.fastener"
    assert screw_body["source_class"] == "SocketHeadCapScrew"
    assert screw_body["canonical_type"] == "screw"
    assert screw_body["designation"] == "M6-1"

    fg = _topology_to_feature_graph(topo, source_code=code)
    standard = next(f for f in fg["features"] if f["type"] == "standard_part")
    assert standard["name"] == "mounting_bolt_M6"
    assert standard["source_library"] == "bd_warehouse"
    assert standard["canonical_type"] == "screw"


def test_execute_build123d_freeform_faces_get_rich_surface_metadata() -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import _execute_build123d_code

    code = """
body = lofted_stack([(0, 20, 10), (15, 26, 14), (30, 12, 8)], label="shell")
result = body
"""
    _step, _stl, _glb, topo = _execute_build123d_code(code, timeout=60)
    freeform_faces = [
        entity for entity in topo.get("entities", [])
        if entity.get("type") == "face" and entity.get("freeform") is True
    ]
    assert freeform_faces
    assert any(face.get("surface_type") in {"bspline", "bezier", "freeform"} for face in freeform_faces)
    assert any("uv_bounds" in face or "proxy_normal" in face for face in freeform_faces)


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


def test_execute_build123d_preserves_labels_with_positional_compound_list(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "named-positional-compound")
    code = (
        "from build123d import *\n"
        "body = Box(40, 40, 10); body.label = 'base_plate'\n"
        "dome = Sphere(8); dome.label = 'dome_head'\n"
        "result = Compound([body, dome])\n"
    )
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["status"] == "ok"
    assert out["named_parts"] == ["base_plate", "dome_head"]
    named = [f for f in out["feature_graph"]["features"] if f["type"] == "named_part"]
    assert sorted(f["name"] for f in named) == ["base_plate", "dome_head"]


def test_execute_build123d_preserves_parent_assembly_and_child_labels(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "named-parent-compound")
    code = (
        "from build123d import *\n"
        "body = Box(40, 30, 10); body.label = 'drone_body'\n"
        "arm_l = Box(50, 5, 5).moved(Location((-45, 0, 0))); arm_l.label = 'arm_L'\n"
        "arm_r = Box(50, 5, 5).moved(Location((45, 0, 0))); arm_r.label = 'arm_R'\n"
        "result = Compound(children=[body, arm_l, arm_r])\n"
        "result.label = 'drone_assembly'\n"
    )
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["status"] == "ok"
    assert out["named_parts"] == ["drone_assembly", "drone_body", "arm_L", "arm_R"]

    topo = _load_topology_map(settings, pid)
    solids = [e for e in topo["entities"] if e.get("type") == "solid"]
    assert [s.get("name") for s in solids] == ["drone_assembly", "drone_body", "arm_L", "arm_R"]
    assert solids[0].get("assembly") is True
    assert not any(e.get("type") == "face" and e.get("body_id") == solids[0]["id"] for e in topo["entities"])
    named = [f for f in out["feature_graph"]["features"] if f["type"] == "named_part"]
    assert [f["name"] for f in named] == ["drone_assembly", "drone_body", "arm_L", "arm_R"]


def test_execute_build123d_single_labeled_body_regression(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "single-label")
    code = (
        "from build123d import *\n"
        "result = Box(10, 10, 10)\n"
        "result.label = 'single_body'\n"
    )
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["status"] == "ok"
    assert out["named_parts"] == ["single_body"]
    topo = _load_topology_map(settings, pid)
    solids = [e for e in topo["entities"] if e.get("type") == "solid"]
    assert [s.get("name") for s in solids] == ["single_body"]
    assert solids[0].get("assembly") is not True


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
    assert data["status"] == "ok"
    assert data["mode"] == "refine"
    assert data["refined_code"] == _REFINED_CODE
    assert data["preview_format"] == "glb"
    assert "geometry/preview.stl" in data["written_artifacts"]
    assert "geometry/preview.glb" in data["written_artifacts"]


def test_get_named_part_bbox_found_and_not_found(tmp_path: Path) -> None:
    from app import runtime as _rt
    from app.main import default_project, project_dir, save_project

    settings = _make_settings(tmp_path)
    create_app(settings)
    project = save_project(settings, default_project("bbox"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "bbox.aieng"
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr(
            "geometry/topology_map.json",
            json.dumps(
                {
                    "entities": [
                        {
                            "id": "body_001",
                            "type": "solid",
                            "name": "thigh_L",
                            "bounding_box": [-50, -18, -130, -10, 18, -40],
                        },
                        {
                            "id": "body_002",
                            "type": "solid",
                            "name": "torso",
                            "bounding_box": [-30, -20, -40, 30, 20, 40],
                        },
                    ]
                }
            ),
        )
    project["aieng_file"] = "bbox.aieng"
    save_project(settings, project)

    found = _rt.invoke_tool("cad.get_named_part_bbox", {"project_id": project_id, "part_name": "thigh_L"})
    assert found["status"] == "ok"
    assert found["bounding_box"] == [-50, -18, -130, -10, 18, -40]
    assert found["center"] == [-30.0, 0.0, -85.0]
    assert found["available_parts"] == ["thigh_L", "torso"]

    missing = _rt.invoke_tool("cad.get_named_part_bbox", {"project_id": project_id, "part_name": "thigh_R"})
    assert missing["status"] == "error"
    assert missing["message"] == "part 'thigh_R' not found"
    assert missing["available_parts"] == ["thigh_L", "torso"]


def test_cad_refine_tool_uses_server_env_key_and_mocked_refinement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import runtime as _rt
    from app.main import default_project, project_dir, save_project
    from app.project_io import get_project, resolve_project_path

    settings = _make_settings(tmp_path)
    create_app(settings)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-from-env")

    project = save_project(settings, default_project("refine-tool"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "tool_refine.aieng"
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("geometry/source.py", _SAMPLE_CODE)
        zf.writestr(
            "graph/feature_graph.json",
            json.dumps({"features": [{"type": "named_part", "name": "torso"}]}),
        )
    project["aieng_file"] = "tool_refine.aieng"
    save_project(settings, project)

    refined_code = (
        "from build123d import *\n"
        "torso = Box(10, 10, 10); torso.label = 'torso'\n"
        "leg = Box(10, 10, 20); leg.label = 'thigh_L'\n"
        "result = Compound(children=[torso, leg])\n"
    )
    topo = {
        "entities": [
            {"id": "body_001", "type": "solid", "name": "torso", "bounding_box": [0, 0, 0, 10, 10, 10]},
            {"id": "body_002", "type": "solid", "name": "thigh_L", "bounding_box": [0, 0, -20, 10, 10, 0]},
            {"id": "face_001", "type": "face", "body_id": "body_001", "surface_type": "plane", "bounding_box": [0, 0, 0, 10, 10, 0]},
        ]
    }

    with (
        patch("app.cad_generation.Build123dBackend.can_generate", return_value=True),
        patch("app.cad_generation.call_claude_for_build123d_refinement", return_value=refined_code) as refine_mock,
        patch("app.cad_generation._execute_build123d_code", return_value=(_FAKE_STEP, _FAKE_STL, _FAKE_GLB, topo)),
    ):
        out = _rt.invoke_tool(
            "cad.refine",
            {"project_id": project_id, "feedback": "move thigh_L down by 20mm", "write_files": True, "timeout": 60},
        )

    assert out["status"] == "ok"
    assert out["mode"] == "refine"
    assert out["named_parts"] == ["torso", "thigh_L"]
    assert out["parts_added"] == ["thigh_L"]
    assert out["topology_summary"]["bounding_box"] == [0, 0, 0, 10, 10, 10]
    refine_mock.assert_called_once()
    assert refine_mock.call_args.kwargs["api_key"] is None

    project = get_project(settings, project_id)
    resolved = resolve_project_path(settings, project_id, project.get("aieng_file"))
    assert resolved is not None and resolved.exists()


def test_cad_refine_tool_requires_server_env_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import runtime as _rt

    settings = _make_settings(tmp_path)
    create_app(settings)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    out = _rt.invoke_tool("cad.refine", {"project_id": "proj_123", "feedback": "make the torso narrower"})
    assert out["status"] == "error"
    assert out["message"] == "ANTHROPIC_API_KEY not configured; cad.refine requires LLM access"


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
    assert "cad.plan_build123d_skill" in tools
    assert tools["cad.plan_build123d_skill"]["requires_approval"] is False
    skill_schema = tools["cad.plan_build123d_skill"]["input_schema"]
    assert set(skill_schema["required"]) == {"project_id", "message"}
    assert "cad.execute_build123d" in tools
    assert tools["cad.execute_build123d"]["requires_approval"] is True
    schema = tools["cad.execute_build123d"]["input_schema"]
    assert "code" in schema["properties"]
    assert set(schema["required"]) == {"project_id", "code"}


# ── geometry report ───────────────────────────────────────────────────────────

def test_geometry_report_flags_asymmetry_and_floating() -> None:
    from app.cad_generation import _compute_geometry_report

    topo = {"entities": [
        {"type": "solid", "id": "b1", "name": "torso", "bounding_box": [-30, -15, 100, 30, 15, 300]},
        {"type": "solid", "id": "b2", "name": "arm_L", "bounding_box": [-50, -10, 150, -30, 10, 290]},
        {"type": "solid", "id": "b3", "name": "arm_R", "bounding_box": [30, -10, 150, 50, 10, 250]},
        {"type": "solid", "id": "b4", "name": "foot_FL", "bounding_box": [-200, -10, -20, -180, 10, 0]},
    ]}
    report = _compute_geometry_report(topo)
    assert report["available"] is True
    assert report["part_count"] == 4
    # asymmetric arm pair (different Z extents) flagged
    arm = next(s for s in report["symmetry"] if s.get("pair") == ["arm_L", "arm_R"])
    assert arm["ok"] is False
    assert arm["mirror_axis"] == "x"
    # foot_FL has no partner and is far from everything
    assert "foot_FL" in report.get("floating_parts", [])
    # always-present contact summary spans every part and the buckets add up
    gs = report["gaps_summary"]
    assert gs["total"] == 4
    assert gs["floating"] >= 1
    assert gs["touching"] + gs["near"] + gs["floating"] == gs["total"]


# ── geometry regression diff ──────────────────────────────────────────────────

def _topo_from(parts: list[tuple[str, list[float]]]) -> dict:
    return {"entities": [
        {"type": "solid", "id": f"b{i}", "name": n, "bounding_box": bb}
        for i, (n, bb) in enumerate(parts)
    ]}


def test_diff_topology_clean_edit() -> None:
    from app.cad_generation import _diff_topology

    before = _topo_from([("torso", [-30, -15, 100, 30, 15, 300]), ("arm_L", [-50, -10, 150, -30, 10, 290])])
    after = _topo_from([("torso", [-30, -15, 100, 30, 15, 300]), ("arm_L", [-50, -10, 150, -30, 10, 330])])
    diff = _diff_topology(before, after, expected_parts={"arm_L"})
    assert diff["verdict"] == "clean"
    assert diff["collateral_parts"] == []
    assert diff["changed"][0]["part"] == "arm_L"
    assert diff["changed"][0]["expected"] is True


def test_diff_topology_flags_collateral_change() -> None:
    from app.cad_generation import _diff_topology

    before = _topo_from([("torso", [-30, -15, 100, 30, 15, 300]), ("arm_L", [-50, -10, 150, -30, 10, 290])])
    # both torso AND arm_L changed, but only arm_L was the target
    after = _topo_from([("torso", [-30, -15, 100, 30, 15, 360]), ("arm_L", [-50, -10, 150, -30, 10, 330])])
    diff = _diff_topology(before, after, expected_parts={"arm_L"})
    assert diff["verdict"] == "collateral_change"
    assert diff["collateral_parts"] == ["torso"]


def test_diff_topology_identical_is_noop() -> None:
    from app.cad_generation import _diff_topology

    before = _topo_from([("torso", [-30, -15, 100, 30, 15, 300])])
    diff = _diff_topology(before, before, expected_parts={"torso"})
    assert diff["verdict"] == "identical"


def test_diff_topology_global_param_no_collateral_judgment() -> None:
    from app.cad_generation import _diff_topology

    before = _topo_from([("torso", [-30, -15, 100, 30, 15, 300]), ("arm_L", [-50, -10, 150, -30, 10, 290])])
    after = _topo_from([("torso", [-32, -17, 100, 32, 17, 300]), ("arm_L", [-52, -12, 150, -28, 12, 290])])
    diff = _diff_topology(before, after, expected_parts=None)
    assert diff["verdict"] == "clean"
    assert diff["collateral_parts"] == []
    assert len(diff["changed"]) == 2


# ── parametric edit end-to-end (real build123d) ───────────────────────────────

def test_edit_build123d_parameter_end_to_end(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import edit_build123d_parameter, execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "param-edit")
    # Named constants → the feature graph exposes an editable parameter.
    code = (
        "from build123d import *\n"
        "BODY_LENGTH = 120\n"
        "BODY_WIDTH = 80\n"
        "BODY_HEIGHT = 8\n"
        "body = Box(BODY_LENGTH, BODY_WIDTH, BODY_HEIGHT); body.label = 'base_plate'\n"
        "result = Compound(children=[body])\n"
    )
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["status"] == "ok"
    # find the base_plate feature + its length parameter
    feat = next(
        f for f in out["feature_graph"]["features"]
        if f.get("name") == "base_plate" and (f.get("parameters") or {})
    )
    assert "length_mm" in feat["parameters"]
    assert feat["parameters"]["length_mm"]["cad_parameter_name"] == "BODY_LENGTH"

    edited = edit_build123d_parameter(
        settings, pid,
        feature_id=feat["id"], parameter_name="length_mm", new_value=200,
    )
    assert edited["status"] == "ok"
    assert edited["previous_value"] == 120
    assert edited["new_value"] == 200
    # the box got longer in X
    bbox = edited["topology_summary"]["bounding_box"]
    assert abs((bbox[3] - bbox[0]) - 200) < 1.0
    # regression diff: base_plate changed as expected, nothing collateral
    diff = edited["regression_diff"]
    assert diff["verdict"] in ("clean", "topology_changed")
    assert diff["collateral_parts"] == []


def test_edit_build123d_parameter_invalid_value_preserves_geometry(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import edit_build123d_parameter, execute_build123d_code

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "param-edit-bad")
    code = (
        "from build123d import *\n"
        "BODY_LENGTH = 120\n"
        "body = Box(BODY_LENGTH, 80, 8); body.label = 'base_plate'\n"
        "result = Compound(children=[body])\n"
    )
    execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    feat = next(
        f for f in execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})["feature_graph"]["features"]
        if f.get("name") == "base_plate" and (f.get("parameters") or {})
    )
    # 0-length box is geometrically invalid → build fails, prior geometry preserved
    edited = edit_build123d_parameter(
        settings, pid,
        feature_id=feat["id"], parameter_name="length_mm", new_value=0,
    )
    assert edited["status"] == "error"
    assert edited["code"] in ("execution_failed", "invalid_contract")


# ── F1: organic models skip mechanical heuristics ─────────────────────────────

def test_feature_graph_organic_skips_mechanical_heuristics() -> None:
    from app.cad_generation import _topology_to_feature_graph

    # Two cylinders of equal radius would normally trip the bolt-pattern heuristic.
    topo = {"entities": [
        {"type": "solid", "id": "b1", "name": "arm_L", "bounding_box": [-50, -10, 0, -30, 10, 200]},
        {"type": "solid", "id": "b2", "name": "arm_R", "bounding_box": [30, -10, 0, 50, 10, 200]},
        {"type": "face", "id": "f1", "body_id": "b1", "surface_type": "cylinder", "radius": 20.0},
        {"type": "face", "id": "f2", "body_id": "b2", "surface_type": "cylinder", "radius": 20.0},
        {"type": "face", "id": "f3", "body_id": "b1", "surface_type": "plane",
         "normal": [0, 0, -1], "center": [-40, 0, 0], "area": 1200, "bounding_box": [-50, -10, 0, -30, 10, 0]},
    ]}
    src = "from build123d import *\narm_L = capsule(20, 160)\nresult = Compound(children=[arm_L])\n"
    fg = _topology_to_feature_graph(topo, source_code=src, model_kind="auto")
    types = {f["type"] for f in fg["features"]}
    assert fg["model_kind"] == "organic"
    assert "mounting_hole" not in types and "mounting_hole_pattern" not in types
    assert "base_plate" not in types


def test_feature_graph_mechanical_keeps_heuristics() -> None:
    from app.cad_generation import _topology_to_feature_graph

    topo = {"entities": [
        {"type": "solid", "id": "b1", "name": "base_plate", "bounding_box": [0, 0, 0, 100, 60, 8]},
        {"type": "face", "id": "f1", "body_id": "b1", "surface_type": "cylinder", "radius": 5.0},
        {"type": "face", "id": "f2", "body_id": "b1", "surface_type": "cylinder", "radius": 5.0},
    ]}
    fg = _topology_to_feature_graph(topo, model_kind="auto")
    assert fg["model_kind"] == "mechanical"
    assert any(f["type"] in ("mounting_hole", "mounting_hole_pattern") for f in fg["features"])


# ── F2: remove / replace a named part (real build123d) ────────────────────────

def _ironman_stub_code() -> str:
    return (
        "from build123d import *\n"
        "torso = lofted_stack([(0,300,200),(400,360,220)], label='torso', color=(0.7,0.1,0.1))\n"
        "head = Sphere(80).moved(Location((0,0,520))); head.label='head'; head.color=Color(0.85,0.66,0.12)\n"
        "arm_L = capsule(40, 200, label='arm_L').moved(Location((-220,0,300)))\n"
        "result = Compound(children=[torso, head, arm_L])\n"
    )


def test_remove_part_drops_named_part(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code, remove_build123d_part

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "ironman-remove")
    execute_build123d_code(settings, pid, {"code": _ironman_stub_code(), "thumbnail": False})

    out = remove_build123d_part(settings, pid, label="head")
    assert out["status"] == "ok"
    assert "head" not in out["named_parts"]
    assert sorted(out["named_parts"]) == ["arm_L", "torso"]
    assert "head" in out["regression_diff"]["removed"]


def test_remove_part_unknown_label_errors(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code, remove_build123d_part

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "ironman-remove-bad")
    execute_build123d_code(settings, pid, {"code": _ironman_stub_code(), "thumbnail": False})

    out = remove_build123d_part(settings, pid, label="cape")
    assert out["status"] == "error"
    assert out["code"] == "part_not_found"
    assert "head" in out["available_parts"]


def test_replace_part_swaps_named_part(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code, replace_build123d_part

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "ironman-replace")
    execute_build123d_code(settings, pid, {"code": _ironman_stub_code(), "thumbnail": False})

    # swap the spherical head for a taller lofted helmet, same label
    new_head = (
        "from build123d import *\n"
        "result = lofted_stack([(440,150,170),(560,90,110)], label='head', color=(0.85,0.66,0.12))\n"
    )
    out = replace_build123d_part(settings, pid, label="head", code=new_head)
    assert out["status"] == "ok"
    assert sorted(out["named_parts"]) == ["arm_L", "head", "torso"]
    # head changed, torso/arm should not be collateral
    assert out["regression_diff"]["collateral_parts"] == []


def test_replace_part_contract_requires_result(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code, replace_build123d_part

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "ironman-replace-bad")
    execute_build123d_code(settings, pid, {"code": _ironman_stub_code(), "thumbnail": False})

    out = replace_build123d_part(settings, pid, label="head", code="x = Sphere(50)")
    assert out["status"] == "error"
    assert out["code"] == "contract_violation"


# ── free-form faces carry a proxy normal (CAE face-binding fix) ───────────────

def test_freeform_faces_get_proxy_normal(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import _execute_build123d_code

    # capsule = sphere caps + cylinder → all free-form / curved faces
    _step, _stl, _glb, topo = _execute_build123d_code(
        "arm = capsule(20, 80, label='arm')\nresult = Compound(children=[arm])\n"
    )
    others = [e for e in topo["entities"] if e.get("type") == "face" and e.get("surface_type") == "other"]
    assert others, "capsule should produce free-form 'other' faces"
    # every free-form face now carries a proxy normal + freeform flag so CAE can bind it
    for f in others:
        assert f.get("freeform") is True
        assert f.get("normal") and len(f["normal"]) == 3


# ── agent builds populate the UI viewer asset (web_asset) ─────────────────────

def test_execute_build123d_publishes_web_asset(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code
    from app.main import get_project, project_dir

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "viewer-asset")
    code = "from build123d import *\nresult = Box(40, 40, 10)\n"
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    assert out["status"] == "ok"
    # the build must point web_asset at viewer/model.* so the UI viewer loads it
    project = get_project(settings, pid)
    assert project.get("web_asset"), "web_asset must be set so the UI viewer can load the model"
    assert project.get("web_asset_format") in ("glb", "stl")
    viewer_file = project_dir(settings, pid) / project["web_asset"]
    assert viewer_file.exists() and viewer_file.stat().st_size > 0


# ── project discoverability: auto-naming + named_parts + part search ──────────

def test_derive_project_name_prefixed_assembly() -> None:
    from app.cad_generation import _derive_project_name
    # parts sharing prefixes (an assembly) -> "Optimus + Bee"
    assert _derive_project_name(["optimus_torso", "optimus_head", "bee_torso", "bee_head"]) == "Optimus + Bee"


def test_derive_project_name_flat_falls_back_to_count() -> None:
    from app.cad_generation import _derive_project_name
    # flat labels with no shared scheme -> count-based fallback (agent should pass `name`)
    flat = ["torso", "windshield", "grille", "waist", "neck", "head"]
    assert _derive_project_name(flat) == "6-part model"
    assert _derive_project_name([]) is None


def test_is_placeholder_project_name() -> None:
    from app.cad_generation import _is_placeholder_project_name
    assert _is_placeholder_project_name("STEP workbench project")
    assert _is_placeholder_project_name("  untitled project ")
    assert _is_placeholder_project_name("")
    assert not _is_placeholder_project_name("Optimus + Bumblebee")
    assert not _is_placeholder_project_name("Iron Man Mark III")


def test_named_parts_from_package_reads_feature_graph(tmp_path: Path) -> None:
    from app.cad_generation import _named_parts_from_package
    pkg = tmp_path / "m.aieng"
    fg = {"features": [
        {"type": "named_part", "name": "base_plate"},
        {"type": "named_part", "name": "rib_main"},
        {"type": "loft", "name": "Loft"},  # non-part feature ignored
    ]}
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("graph/feature_graph.json", json.dumps(fg))
    assert _named_parts_from_package(pkg) == ["base_plate", "rib_main"]


def test_named_parts_from_package_falls_back_to_topology(tmp_path: Path) -> None:
    from app.cad_generation import _named_parts_from_package
    pkg = tmp_path / "m.aieng"
    topo = {"entities": [
        {"type": "solid", "name": "body_a"},
        {"type": "solid", "name": "body_b"},
        {"type": "face"},
    ]}
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/topology_map.json", json.dumps(topo))
    assert _named_parts_from_package(pkg) == ["body_a", "body_b"]


def test_find_projects_by_part_tool(tmp_path: Path) -> None:
    from app.runtime_tool_schemas import get_schema
    schema = get_schema("aieng.find_projects_by_part")
    assert schema and "query" in schema["properties"]


# ── Shape IR: post-execution provenance reconciliation ───────────────────────

def test_reconcile_shape_ir_provenance_refreshes_registry_and_manifest(tmp_path: Path) -> None:
    """After Shape IR source executes, object_registry is rebuilt against the
    real executed ids and the conversion manifest is stamped — no dangling
    projected slug references remain."""
    from app.cad_generation import reconcile_shape_ir_provenance

    pkg = tmp_path / "m.aieng"
    projected_registry = {"objects": [{"id": "body_helmet_shell", "kind": "topology_entity"}], "relationships": []}
    manifest = {
        "format_version": "0.1",
        "converter": {"converter_id": "shape_ir_reference"},
        "coverage_categories": [{"category": "geometry", "status": "inferred"}],
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("objects/object_registry.json", json.dumps(projected_registry))
        zf.writestr("provenance/conversion_manifest.json", json.dumps(manifest))
        zf.writestr("geometry/source.py", "x = 1\n")

    topo = {
        "format_version": "0.1",
        "entities": [
            {"id": "body_001", "type": "solid", "name": "helmet"},
            {"id": "face_001", "type": "face", "body_id": "body_001"},
        ],
    }
    fg = {"features": [{
        "id": "feat_body_001", "type": "named_part", "name": "helmet",
        "geometry_refs": {"entities": ["body_001"], "faces": ["face_001"]},
    }]}

    reconcile_shape_ir_provenance(pkg, topo, fg, executed_at="2026-01-01T00:00:00Z")

    with zipfile.ZipFile(pkg) as zf:
        reg = json.loads(zf.read("objects/object_registry.json"))
        man = json.loads(zf.read("provenance/conversion_manifest.json"))

    ids = {o["id"] for o in reg["objects"]}
    assert "body_001" in ids and "feat_body_001" in ids
    assert "body_helmet_shell" not in ids  # projected slug id is gone
    assert all(o["status"] == "compiled_and_executed" for o in reg["objects"])
    assert man["geometry_execution"]["executed"] is True
    assert man["geometry_execution"]["real_geometry"] is True
    assert man["geometry_execution"]["executed_at_utc"] == "2026-01-01T00:00:00Z"


# ── implicit SDF runner (Shape IR representation: implicit_sdf) ───────────────

def test_mesh_feature_graph_reads_representation_from_topology() -> None:
    from app.cad_generation import _mesh_feature_graph
    topo = {
        "metadata": {"representation": "manifold_mesh", "extractor": "ManifoldRunner"},
        "entities": [
            {"id": "body_001", "type": "solid", "name": "manifold_body", "face_ids": ["face_001"]},
            {"id": "face_001", "type": "face", "body_id": "body_001"},
        ],
    }
    fg = _mesh_feature_graph(topo)
    assert len(fg["features"]) == 1
    feat = fg["features"][0]
    assert feat["type"] == "named_part" and feat["id"] == "feat_body_001"
    assert "body_001" in feat["geometry_refs"]["entities"]
    assert "face_001" in feat["geometry_refs"]["faces"]
    # representation/recognizer flow through from the topology the runner wrote
    assert fg["metadata"]["representation"] == "manifold_mesh"
    assert fg["metadata"]["recognizer"] == "ManifoldRunner"


def test_execute_sdf_code_meshes_a_field() -> None:
    """End-to-end SDF run: meshes a field to STL + GLB and projects mesh topology.
    Skips where the SDF runtime isn't installed (runs in aieng311/CI)."""
    pytest.importorskip("sdf")
    pytest.importorskip("trimesh")
    from app.cad_generation import _execute_sdf_code
    src = "from sdf import *\nf = sphere(10) | sphere(8).translate((0, 0, 12))\n"
    stl, glb, topo = _execute_sdf_code(src, timeout=120, samples=2 ** 15)
    assert len(stl) > 0 and len(glb) > 0
    assert topo["metadata"]["extractor"] == "SDFRunner"
    assert topo["metadata"]["representation"] == "implicit_sdf"
    faces = [e for e in topo["entities"] if e.get("type") == "face"]
    assert faces and faces[0]["surface_type"] == "freeform"


def test_execute_manifold_code_meshes_a_solid() -> None:
    """End-to-end Manifold run: CSG -> mesh STL + GLB + region topology.
    Skips where manifold3d isn't installed (runs in aieng311/CI)."""
    pytest.importorskip("manifold3d")
    pytest.importorskip("trimesh")
    from app.cad_generation import _execute_manifold_code
    src = (
        "from manifold3d import Manifold\n"
        "result = Manifold.sphere(10.0) - Manifold.cube((6.0, 6.0, 6.0), True).translate((0, 0, 6))\n"
    )
    stl, glb, topo = _execute_manifold_code(src, timeout=120)
    assert len(stl) > 0 and len(glb) > 0
    assert topo["metadata"]["extractor"] == "ManifoldRunner"
    assert topo["metadata"]["representation"] == "manifold_mesh"
    faces = [e for e in topo["entities"] if e.get("type") == "face"]
    assert faces and faces[0]["surface_type"] == "mesh_region"


def test_execute_nurbs_source_builds_brep_face() -> None:
    """nurbs_brep compiles to build123d+OCP source that builds a real B-Rep NURBS
    face (surface_type 'bspline') and exports STEP. Runs in aieng311 (build123d+OCP)."""
    pytest.importorskip("build123d")
    from aieng.converters.shape_ir_nurbs import compile_shape_ir_to_nurbs_source
    from app.cad_generation import _execute_build123d_code

    payload = {"representation": "nurbs_brep", "parts": [
        {"id": "patch", "type": "nurbs_surface", "control_net": [
            [[0, 0, 0], [10, 0, 5], [20, 0, 0]],
            [[0, 10, 5], [10, 10, -4], [20, 10, 5]],
            [[0, 20, 0], [10, 20, 5], [20, 20, 0]],
        ]},
    ]}
    src = compile_shape_ir_to_nurbs_source(payload)
    step, stl, glb, topo = _execute_build123d_code(src, timeout=120)
    assert len(step) > 0
    faces = [e for e in topo.get("entities", []) if e.get("type") == "face"]
    assert faces, "NURBS surface must yield at least one B-Rep face"
    assert any(f.get("surface_type") == "bspline" for f in faces)
