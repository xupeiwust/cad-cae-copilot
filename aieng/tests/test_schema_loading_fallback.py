"""Tests for schema-loading fallback warning behaviour."""

from __future__ import annotations

import warnings as _warnings
from pathlib import Path

import pytest
import yaml


VALID_DEFINITION = {
    "model_id": "fallback_warning_test",
    "label": "Fallback warning test",
    "description": "Minimal definition for fallback warning test.",
    "coordinate_system": {
        "type": "cartesian",
        "handedness": "right",
        "units": {"length": "mm", "angle": "deg"},
        "origin": [0, 0, 0],
        "axes": {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]},
    },
    "material": {
        "name": "Al6061-T6",
        "properties": {
            "youngs_modulus_mpa": 69000,
            "poisson_ratio": 0.33,
            "density_kg_m3": 2700,
            "yield_strength_mpa": 276,
        },
    },
    "features": [
        {
            "feature_id": "feat_base_001",
            "type": "base_plate",
            "name": "Base plate",
            "parameters": {"length_mm": 100, "width_mm": 50, "thickness_mm": 5},
        }
    ],
    "constraints": [],
}


def test_read_schema_text_warns_when_falling_back_to_source_tree(monkeypatch) -> None:
    """_read_schema_text emits a RuntimeWarning when it falls back to the source tree."""
    from aieng.validate import _read_schema_text

    def _broken_files(*_args, **_kwargs):
        raise ModuleNotFoundError("simulated missing package schema")

    monkeypatch.setattr("importlib.resources.files", _broken_files)

    # Use a schema that exists in the source tree because tests run from checkout.
    with pytest.warns(RuntimeWarning, match="source tree fallback"):
        text = _read_schema_text("model_definition.schema.json")

    assert text is not None
    assert '"$schema"' in text or '"title"' in text or "model_definition" in text


def test_validate_definition_warns_when_falling_back_to_source_tree(monkeypatch) -> None:
    """_validate_definition emits a RuntimeWarning when it falls back to the source tree."""
    from aieng.definition import _validate_definition

    def _broken_files(*_args, **_kwargs):
        raise ModuleNotFoundError("simulated missing package schema")

    monkeypatch.setattr("importlib.resources.files", _broken_files)

    with pytest.warns(RuntimeWarning, match="source tree fallback"):
        # Should not raise; schema is available from source tree fallback.
        _validate_definition(VALID_DEFINITION)


def test_define_package_no_fallback_warning_when_schema_packaged(tmp_path: Path) -> None:
    """When schemas are available via importlib.resources, no source-tree fallback warning is emitted."""
    from aieng.cli import main

    definition_path = tmp_path / "definition.yaml"
    definition_path.write_text(yaml.safe_dump(VALID_DEFINITION, sort_keys=False), encoding="utf-8")
    package_path = tmp_path / "fallback_warning_test.aieng"

    with _warnings.catch_warnings(record=True) as warning_list:
        _warnings.simplefilter("always")
        assert main(["define", str(definition_path), "--out", str(package_path)]) == 0

    fallback_warnings = [
        w for w in warning_list
        if issubclass(w.category, RuntimeWarning) and "source tree fallback" in str(w.message)
    ]
    assert fallback_warnings == []
