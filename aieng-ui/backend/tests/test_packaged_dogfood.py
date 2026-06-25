"""Unit coverage for the reusable packaged dogfood evidence helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "packaged_dogfood.py"
    spec = importlib.util.spec_from_file_location("packaged_dogfood", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cad_code_names_the_evidence_parts() -> None:
    packaged_dogfood = _load_module()

    assert 'base_plate.label = "base_plate"' in packaged_dogfood.CAD_CODE
    assert 'rib.label = "rib_main"' in packaged_dogfood.CAD_CODE
    assert "result = Compound(children=[base_plate, rib])" in packaged_dogfood.CAD_CODE
    assert "export_step(" not in packaged_dogfood.CAD_CODE
    assert "export_stl(" not in packaged_dogfood.CAD_CODE
    assert "export_gltf(" not in packaged_dogfood.CAD_CODE
    assert "PROBE_SIZE = 1" in packaged_dogfood.MANAGED_PROBE_CODE
    assert 'probe_cube.label = "probe_cube"' in packaged_dogfood.MANAGED_PROBE_CODE
    assert "probe_cube.color = Color(" in packaged_dogfood.MANAGED_PROBE_CODE
    assert (
        "result = Compound(children=[probe_cube])"
        in packaged_dogfood.MANAGED_PROBE_CODE
    )
    assert "export_step(" not in packaged_dogfood.MANAGED_PROBE_CODE
    assert "export_stl(" not in packaged_dogfood.MANAGED_PROBE_CODE
    assert "export_gltf(" not in packaged_dogfood.MANAGED_PROBE_CODE


def test_result_text_flattens_mcp_blocks() -> None:
    packaged_dogfood = _load_module()

    class Block:
        def __init__(self, text: str):
            self.text = text

    class Result:
        content = [Block("first"), Block("second")]

    assert packaged_dogfood._result_text(Result()) == "first\nsecond"


def test_face_pointer_reads_first_brep_face() -> None:
    packaged_dogfood = _load_module()

    context = {
        "brep_graph": {
            "digest": "header\n- @face:face_013 plane\n- @face:face_014 plane"
        }
    }

    assert packaged_dogfood._face_pointer(context) == "@face:face_013"
    assert packaged_dogfood._face_pointers(context) == ["@face:face_013", "@face:face_014"]
    assert packaged_dogfood._face_id("@face:face_013") == "face_013"
    assert packaged_dogfood._pointer_in_context(context, "@face:face_013") is True
    assert packaged_dogfood._pointer_in_context(context, "@face:face_999") is False


def test_m1_cae_setup_patches_use_canonical_setup_and_mapping() -> None:
    packaged_dogfood = _load_module()

    patches = packaged_dogfood._m1_cae_setup_patches(
        load_pointer="@face:face_013",
        fixed_pointer="@face:face_003",
    )
    by_path = {patch["path"]: patch for patch in patches}

    assert "simulation/setup.yaml" in by_path
    assert "simulation/cae_mapping.json" in by_path
    assert "simulation/solver_settings.json" in by_path
    assert "simulation/cae_imports/parsed_materials.json" in by_path

    setup = by_path["simulation/setup.yaml"]["content"]
    assert setup["loads"][0]["target_feature"] == "load_top"
    assert setup["loads"][0]["value_n"] == 500.0
    assert setup["boundary_conditions"][0]["target_feature"] == "fixed_base"

    mapping = by_path["simulation/cae_mapping.json"]["content"]
    load_map = next(m for m in mapping["mappings"] if m["cae_entity"] == "LOAD_TOP")
    fixed_map = next(m for m in mapping["mappings"] if m["cae_entity"] == "FIXED_BASE")
    assert load_map["face_ids"] == ["face_013"]
    assert fixed_map["face_ids"] == ["face_003"]
    assert load_map["maps_to"]["target_pointers"] == ["@face:face_013"]


def test_m1_cae_setup_rejects_non_face_pointer() -> None:
    packaged_dogfood = _load_module()

    with pytest.raises(ValueError, match="expected @face pointer"):
        packaged_dogfood._m1_cae_setup_patches(
            load_pointer="face_013",
            fixed_pointer="@face:face_003",
        )


def test_backend_fetches_only_allow_http_schemes() -> None:
    packaged_dogfood = _load_module()

    assert packaged_dogfood._assert_http_url("https://example.test/api") == (
        "https://example.test/api"
    )
    with pytest.raises(ValueError, match="unsupported URL scheme: file"):
        packaged_dogfood._assert_http_url("file:///tmp/evidence.json")
