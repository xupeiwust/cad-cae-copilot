import json
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.app_factory import create_app
from app.brep_graph import (
    BREP_DIGEST_MEMBER,
    BREP_GRAPH_MEMBER,
    ENTITY_INDEX_MEMBER,
    build_brep_graph_from_topology,
)
from app.config import Settings
from app.contextual_chat import build_context_block

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


def _sample_topology() -> dict:
    return {
        "format_version": "0.1",
        "entities": [
            {"id": "body_001", "type": "solid", "bounding_box": [0, 0, 0, 100, 50, 10]},
            {
                "id": "face_001",
                "type": "face",
                "surface_type": "plane",
                "area": 5000,
                "normal": [0, 0, -1],
                "center": [50, 25, 0],
                "bounding_box": [0, 0, 0, 100, 50, 0],
                "body_id": "body_001",
            },
            {
                "id": "face_002",
                "type": "face",
                "surface_type": "plane",
                "area": 5000,
                "normal": [0, 0, 1],
                "center": [50, 25, 10],
                "bounding_box": [0, 0, 10, 100, 50, 10],
                "body_id": "body_001",
            },
            {
                "id": "face_003",
                "type": "face",
                "surface_type": "plane",
                "area": 500,
                "normal": [1, 0, 0],
                "center": [100, 25, 5],
                "bounding_box": [100, 0, 0, 100, 50, 10],
                "body_id": "body_001",
            },
            {
                "id": "face_004",
                "type": "face",
                "surface_type": "cylinder",
                "area": 120,
                "radius": 3.2,
                "center": [25, 15, 5],
                "bounding_box": [21.8, 11.8, 0, 28.2, 18.2, 10],
                "body_id": "body_001",
            },
            {
                "id": "face_005",
                "type": "face",
                "surface_type": "cylinder",
                "area": 120,
                "radius": 3.2,
                "center": [75, 15, 5],
                "bounding_box": [71.8, 11.8, 0, 78.2, 18.2, 10],
                "body_id": "body_001",
            },
        ],
    }


def _feature_graph() -> dict:
    return {
        "features": [
            {
                "id": "feat_holes",
                "type": "mounting_hole_pattern",
                "name": "Two mounting holes",
                "geometry_refs": {"faces": ["face_004", "face_005"]},
            }
        ]
    }


def _make_project_with_package(settings: Settings, pkg_members: dict[str, bytes]) -> tuple[str, Path]:
    from app.project_io import default_project, project_dir, save_project

    project = save_project(settings, default_project("BRep graph test"))
    pkg_path = project_dir(settings, project["id"]) / "packages" / "model.aieng"
    with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in pkg_members.items():
            zf.writestr(name, content)
    project["aieng_file"] = "packages/model.aieng"
    save_project(settings, project)
    return project["id"], pkg_path


def test_build_brep_graph_from_topology_has_pointers_and_roles() -> None:
    result = build_brep_graph_from_topology(_sample_topology(), feature_graph=_feature_graph())

    graph = result["brep_graph"]
    index = result["entity_index"]
    digest = result["digest"]

    assert graph["entities"]["faces"][0]["pointer"] == "@face:face_001"
    assert index["face_001"]["pointer"] == "@face:face_001"
    assert "support_candidate" in index["face_001"]["roles"]
    assert "load_candidate" in index["face_002"]["roles"]
    assert "mounting_candidate" in index["face_004"]["roles"]
    assert "feat_holes" in index
    assert "@face:face_001" in digest
    assert "Pointer syntax" in digest


def test_build_brep_graph_infers_face_adjacency() -> None:
    result = build_brep_graph_from_topology(_sample_topology())
    relations = result["brep_graph"]["relations"]

    assert any(
        r["type"] == "face_adjacent_face"
        and {r["from"], r["to"]} == {"face_001", "face_003"}
        and r["virtual"] is True
        for r in relations
    )


def test_brep_graph_endpoint_writes_artifacts(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_id, pkg_path = _make_project_with_package(
        settings,
        {
            "geometry/topology_map.json": json.dumps(_sample_topology()).encode(),
            "graph/feature_graph.json": json.dumps(_feature_graph()).encode(),
        },
    )
    client = TestClient(create_app(settings))

    resp = client.post(f"/api/projects/{project_id}/brep-graph/build", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert BREP_GRAPH_MEMBER in data["written_artifacts"]
    assert ENTITY_INDEX_MEMBER in data["written_artifacts"]
    assert BREP_DIGEST_MEMBER in data["written_artifacts"]
    with zipfile.ZipFile(pkg_path) as zf:
        assert BREP_GRAPH_MEMBER in zf.namelist()
        assert ENTITY_INDEX_MEMBER in zf.namelist()
        assert BREP_DIGEST_MEMBER in zf.namelist()

    get_resp = client.get(f"/api/projects/{project_id}/brep-graph")
    assert get_resp.status_code == 200
    assert get_resp.json()["entity_index"]["face_001"]["pointer"] == "@face:face_001"


def test_brep_graph_and_pick_face_build_on_demand_without_persisted_graph(tmp_path: Path) -> None:
    # Agent-built CAD writes topology + feature_graph but NOT the B-Rep graph.
    # GET brep-graph and pick-face must build it on demand (not 404), so the
    # viewer's face highlight + apply-load/support popup work on fresh geometry.
    settings = _make_settings(tmp_path)
    project_id, pkg_path = _make_project_with_package(
        settings,
        {
            "geometry/topology_map.json": json.dumps(_sample_topology()).encode(),
            "graph/feature_graph.json": json.dumps(_feature_graph()).encode(),
        },
    )
    client = TestClient(create_app(settings))

    # No persisted graph member exists yet.
    with zipfile.ZipFile(pkg_path) as zf:
        assert BREP_GRAPH_MEMBER not in zf.namelist()

    # GET resolves a graph on demand (feeds the highlight's brepSnapshot).
    get_resp = client.get(f"/api/projects/{project_id}/brep-graph")
    assert get_resp.status_code == 200
    assert get_resp.json()["entity_index"]["face_001"]["pointer"] == "@face:face_001"

    # pick-face resolves a face on demand (drives the apply-load/support popup).
    pick_resp = client.post(
        f"/api/projects/{project_id}/brep/pick-face",
        json={"x": 50, "y": 25, "z": 0},
    )
    assert pick_resp.status_code == 200
    assert pick_resp.json()["pointer"] == "@face:face_001"


def test_context_block_includes_transient_brep_digest(tmp_path: Path) -> None:
    pkg = tmp_path / "model.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/topology_map.json", json.dumps(_sample_topology()))

    context = build_context_block(pkg)

    assert "B-Rep Graph Digest" in context
    assert "@face:face_001" in context
