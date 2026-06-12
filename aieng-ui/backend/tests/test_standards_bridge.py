"""Tests for the standards bridge BOM and standard-part utilities."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from test_api import _make_patch_settings


def _make_bom_package(pkg_path: Path, features: list[dict]) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    feature_graph = {
        "format_version": "0.1.0",
        "features": features,
    }
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "bom-test"}))
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))


def test_generate_bom_aggregates_standard_parts(tmp_path: Path) -> None:
    """BOM deduplicates standard parts by (name, type, material) and sums quantity."""
    from app.standards_bridge import generate_bom

    settings = _make_patch_settings(tmp_path)
    pkg_path = tmp_path / "bom.aieng"
    _make_bom_package(pkg_path, [
        {
            "id": "feat_bolt_1",
            "type": "standard_part",
            "name": "mounting_bolt_M6",
            "canonical_type": "screw",
            "designation": "M6-1",
            "source_library": "bd_warehouse",
            "parameters": {},
        },
        {
            "id": "feat_bolt_2",
            "type": "standard_part",
            "name": "mounting_bolt_M6",
            "canonical_type": "screw",
            "designation": "M6-1",
            "source_library": "bd_warehouse",
            "parameters": {},
        },
        {
            "id": "feat_washer_1",
            "type": "standard_part",
            "name": "washer_M6",
            "canonical_type": "washer",
            "designation": "M6",
            "source_library": "bd_warehouse",
            "parameters": {},
        },
    ])

    result = generate_bom(settings, project_id=None, package_path=str(pkg_path))
    assert result["status"] == "ok"
    assert result["total_parts"] == 3
    assert result["unique_parts"] == 2

    bolt = next(
        item for item in result["items"]
        if item["part_type"] == "standard_part" and item["canonical_type"] == "screw"
    )
    assert bolt["quantity"] == 2
    assert bolt["designation"] == "M6-1"
    assert bolt["source_library"] == "bd_warehouse"

    washer = next(
        item for item in result["items"] if item["canonical_type"] == "washer"
    )
    assert washer["quantity"] == 1
    assert washer["designation"] == "M6"


def test_generate_bom_markdown_includes_quantities(tmp_path: Path) -> None:
    """Markdown BOM output includes each item with its aggregated quantity."""
    from app.standards_bridge import generate_bom

    settings = _make_patch_settings(tmp_path)
    pkg_path = tmp_path / "bom-md.aieng"
    _make_bom_package(pkg_path, [
        {
            "id": "feat_bolt_1",
            "type": "standard_part",
            "name": "mounting_bolt_M6",
            "canonical_type": "screw",
            "designation": "M6-1",
            "source_library": "bd_warehouse",
            "parameters": {},
        },
        {
            "id": "feat_bolt_2",
            "type": "standard_part",
            "name": "mounting_bolt_M6",
            "canonical_type": "screw",
            "designation": "M6-1",
            "source_library": "bd_warehouse",
            "parameters": {},
        },
    ])

    result = generate_bom(settings, project_id=None, package_path=str(pkg_path), fmt="markdown")
    assert result["status"] == "ok"
    assert "markdown" in result
    assert "mounting_bolt_M6" in result["markdown"]
    assert "| 2 |" in result["markdown"]


def test_generate_bom_returns_error_when_package_missing(tmp_path: Path) -> None:
    """generate_bom returns a structured error when the package cannot be found."""
    from app.standards_bridge import generate_bom

    settings = _make_patch_settings(tmp_path)
    result = generate_bom(settings, project_id=None, package_path=str(tmp_path / "missing.aieng"))
    assert result["status"] == "error"
    assert result["code"] == "missing_package"
