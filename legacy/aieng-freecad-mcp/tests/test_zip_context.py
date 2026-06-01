"""Tests for .aieng zip package context loading."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.aieng_bridge.context import load_aieng_context


def _build_aieng_zip(
    tmp_path: Path,
    files: dict[str, Any] | None = None,
) -> Path:
    """Create a .aieng zip package from a dict of file paths to JSON-serializable data."""
    zip_path = tmp_path / "test_package.aieng"
    files = files or {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files.items():
            if isinstance(content, (dict, list)):
                data = json.dumps(content, indent=2)
            else:
                data = str(content)
            zf.writestr(arcname, data)
    return zip_path


class TestZipContextLoading:
    def test_load_full_zip_package(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "manifest.json": {"model_id": "test-001", "format_version": "0.1.0"},
                "graph/feature_graph.json": {"features": {"f1": {"name": "Feature1"}}},
                "graph/constraints.json": {"constraints": []},
                "task/task_spec.yaml": "allowed_operations:\n  - cad_set_parameter\n",
                "task/external_tool_requirements.json": {"tools": []},
                "simulation/setup.yaml": "solver: calculix\n",
                "simulation/cae_mapping.json": {"mapping": {}},
                "results/claim_map.json": {"claims": []},
                "results/evidence_index.json": {"entries": []},
                "provenance/tool_trace.json": {"entries": []},
                "validation/completeness_report.json": {"status": "complete"},
                "objects/reference_map.json": {"references": []},
                "objects/interface_graph.json": {"interfaces": []},
            },
        )

        ctx = load_aieng_context(str(zip_path))

        assert ctx.available is True
        assert ctx.mode == "aieng_enhanced"
        assert ctx.manifest == {"model_id": "test-001", "format_version": "0.1.0"}
        assert ctx.feature_graph == {"features": {"f1": {"name": "Feature1"}}}
        assert ctx.claim_map == {"claims": []}
        assert ctx.evidence_index == {"entries": []}
        assert ctx.tool_trace == {"entries": []}
        assert ctx.reference_map == {"references": []}
        assert ctx.package_path == str(zip_path.resolve())

    def test_load_zip_with_missing_optional_resources(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "manifest.json": {"model_id": "test-002"},
            },
        )

        ctx = load_aieng_context(str(zip_path))

        assert ctx.available is True
        assert ctx.mode == "aieng_enhanced"
        assert ctx.manifest == {"model_id": "test-002"}
        assert ctx.feature_graph is None
        assert ctx.claim_map is None
        assert ctx.evidence_index is None
        assert ctx.tool_trace is None
        assert "manifest.json not found" not in " ".join(ctx.warnings)

    def test_load_zip_missing_manifest(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "graph/feature_graph.json": {"features": {}},
            },
        )

        ctx = load_aieng_context(str(zip_path))

        assert ctx.available is True
        assert ctx.mode == "aieng_enhanced"
        assert ctx.manifest is None
        assert "manifest.json not found" in " ".join(ctx.warnings)

    def test_load_directory_still_works(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "test_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps({"model_id": "dir-test"}))
        (pkg_dir / "graph").mkdir()
        (pkg_dir / "graph" / "feature_graph.json").write_text(json.dumps({"features": {}}))
        (pkg_dir / "results").mkdir()
        (pkg_dir / "results" / "claim_map.json").write_text(json.dumps({"claims": []}))
        (pkg_dir / "provenance").mkdir()
        (pkg_dir / "provenance" / "tool_trace.json").write_text(json.dumps({"entries": []}))

        ctx = load_aieng_context(str(pkg_dir))

        assert ctx.available is True
        assert ctx.mode == "aieng_enhanced"
        assert ctx.manifest == {"model_id": "dir-test"}
        assert ctx.claim_map == {"claims": []}

    def test_load_nonexistent_path_returns_standalone(self, tmp_path: Path) -> None:
        ctx = load_aieng_context(str(tmp_path / "does_not_exist"))

        assert ctx.available is False
        assert ctx.mode == "standalone"
        assert "does not exist" in " ".join(ctx.warnings)

    def test_load_none_returns_standalone(self) -> None:
        ctx = load_aieng_context(None)

        assert ctx.available is False
        assert ctx.mode == "standalone"
        assert "No .aieng context provided" in " ".join(ctx.warnings)

    def test_load_malformed_zip_returns_standalone(self, tmp_path: Path) -> None:
        bad_zip = tmp_path / "bad.aieng"
        bad_zip.write_text("this is not a zip file")

        ctx = load_aieng_context(str(bad_zip))

        assert ctx.available is False
        assert ctx.mode == "standalone"
        assert "Malformed" in " ".join(ctx.warnings)

    def test_zip_and_dir_parity(self, tmp_path: Path) -> None:
        """Same content loaded from zip vs dir must produce identical contexts."""
        # Build directory
        pkg_dir = tmp_path / "parity_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text(json.dumps({"model_id": "parity-test"}))
        (pkg_dir / "graph").mkdir()
        (pkg_dir / "graph" / "feature_graph.json").write_text(
            json.dumps({"features": {"f1": {"name": "Hole"}}})
        )
        (pkg_dir / "results").mkdir()
        (pkg_dir / "results" / "claim_map.json").write_text(
            json.dumps({"claims": [{"id": "c1", "status": "unsupported"}]})
        )
        (pkg_dir / "provenance").mkdir()
        (pkg_dir / "provenance" / "tool_trace.json").write_text(json.dumps({"entries": []}))

        # Build zip with same content
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "manifest.json": {"model_id": "parity-test"},
                "graph/feature_graph.json": {"features": {"f1": {"name": "Hole"}}},
                "results/claim_map.json": {"claims": [{"id": "c1", "status": "unsupported"}]},
                "provenance/tool_trace.json": {"entries": []},
            },
        )

        ctx_dir = load_aieng_context(str(pkg_dir))
        ctx_zip = load_aieng_context(str(zip_path))

        assert ctx_dir.available == ctx_zip.available
        assert ctx_dir.mode == ctx_zip.mode
        assert ctx_dir.manifest == ctx_zip.manifest
        assert ctx_dir.feature_graph == ctx_zip.feature_graph
        assert ctx_dir.claim_map == ctx_zip.claim_map
