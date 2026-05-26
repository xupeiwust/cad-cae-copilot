"""Tests for contextual_chat pointer display, validation, and stale mapping."""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.contextual_chat import build_context_block, _format_pointer_block
from app.cad_generation import _mark_cae_mapping_stale


def test_format_pointer_block_with_valid_group_pointer() -> None:
    parts: list[str] = []
    _format_pointer_block(
        parts,
        {"id": "bc_001", "target_pointers": ["@group:feat_holes"], "target_feature": "feat_holes"},
        "BC",
        {"feat_holes": {"kind": "group", "members": ["face_003", "face_004"]}},
        {"mappings": [{"maps_to": {"feature_id": "feat_holes"}, "confidence": "explicit"}]},
    )
    assert any("face_003, face_004" in p for p in parts)
    assert not any("⚠️" in p for p in parts)


def test_format_pointer_block_with_invalid_pointer_and_ai_generated() -> None:
    parts: list[str] = []
    _format_pointer_block(
        parts,
        {"id": "bc_002", "target_pointers": ["@face:face_999"], "target_feature": "feat_base"},
        "BC",
        {},
        {"mappings": [{"maps_to": {"feature_id": "feat_base"}, "confidence": "ai_generated"}]},
    )
    assert any("NOT FOUND" in p for p in parts)
    assert any("AI-generated selection" in p for p in parts)


def test_format_pointer_block_with_stale_mapping() -> None:
    parts: list[str] = []
    _format_pointer_block(
        parts,
        {"id": "load_001", "target_pointers": ["@face:face_002"], "target_feature": "load_face"},
        "Load",
        {"face_002": {"kind": "face"}},
        {"stale": True, "mappings": [{"maps_to": {"feature_id": "load_face"}, "confidence": "explicit"}]},
    )
    assert any("STALE" in p for p in parts)


def test_build_context_block_shows_pointer_mappings(tmp_path: Path) -> None:
    pkg = tmp_path / "model.aieng"
    setup = {
        "material_name": "Al6061-T6",
        "boundary_conditions": [
            {
                "id": "bc_001",
                "target_feature": "feat_holes",
                "target_pointers": ["@group:feat_holes"],
                "target_face_ids": ["face_003", "face_004"],
                "type": "fixed",
            }
        ],
        "loads": [
            {
                "id": "load_001",
                "target_feature": "load_face",
                "target_pointers": ["@face:face_002"],
                "target_face_ids": ["face_002"],
                "type": "force",
                "value_n": 500.0,
                "direction": [0, 0, -1],
            }
        ],
        "mesh": {"target_size_mm": 2.5},
    }
    cae_mapping = {
        "mappings": [
            {"maps_to": {"feature_id": "feat_holes"}, "confidence": "explicit"},
            {"maps_to": {"feature_id": "load_face"}, "confidence": "explicit"},
        ]
    }
    entity_index = {
        "feat_holes": {"kind": "group", "members": ["face_003", "face_004"]},
        "face_002": {"kind": "face"},
    }
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/topology_map.json", json.dumps({"entities": []}))
        zf.writestr("simulation/setup.yaml", __import__("yaml").dump(setup))
        zf.writestr("simulation/cae_mapping.json", json.dumps(cae_mapping))
        zf.writestr("graph/entity_index.json", json.dumps(entity_index))

    ctx = build_context_block(pkg)
    assert "BC bc_001" in ctx
    assert "face_003, face_004" in ctx
    assert "Load load_001" in ctx


def test_build_context_block_warns_on_stale_mapping(tmp_path: Path) -> None:
    pkg = tmp_path / "model.aieng"
    setup = {
        "material_name": "Al6061-T6",
        "boundary_conditions": [],
        "loads": [],
        "mesh": {"target_size_mm": 2.5},
    }
    cae_mapping = {"stale": True, "mappings": []}
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("geometry/topology_map.json", json.dumps({"entities": []}))
        zf.writestr("simulation/setup.yaml", __import__("yaml").dump(setup))
        zf.writestr("simulation/cae_mapping.json", json.dumps(cae_mapping))

    ctx = build_context_block(pkg)
    assert "STALE" in ctx


def test_mark_cae_mapping_stale(tmp_path: Path) -> None:
    pkg = tmp_path / "model.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("simulation/cae_mapping.json", json.dumps({"mappings": [{"cae_entity": "BC1"}]}))

    _mark_cae_mapping_stale(pkg)

    with zipfile.ZipFile(pkg, "r") as zf:
        data = json.loads(zf.read("simulation/cae_mapping.json"))

    assert data.get("stale") is True
    assert "CAD geometry changed" in data.get("stale_reason", "")
    assert "stale_at" in data
