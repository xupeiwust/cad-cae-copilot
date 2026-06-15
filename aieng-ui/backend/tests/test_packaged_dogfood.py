"""Unit coverage for the reusable packaged dogfood evidence helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


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
    assert packaged_dogfood._pointer_in_context(context, "@face:face_013") is True
    assert packaged_dogfood._pointer_in_context(context, "@face:face_999") is False
