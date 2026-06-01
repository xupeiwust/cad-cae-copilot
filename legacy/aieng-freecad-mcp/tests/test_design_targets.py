"""Tests for freecad_mcp.aieng_bridge.design_targets read-only inspection."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

import yaml

from freecad_mcp.aieng_bridge.design_targets import (
    read_design_targets,
    read_design_target_comparisons,
    summarize_design_target_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pkg_with_design_targets(tmp_path: Path, design_targets: dict[str, Any] | None) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test"}))
        if design_targets is not None:
            zf.writestr("task/design_targets.yaml", yaml.safe_dump(design_targets))
    return pkg


def _make_pkg_with_comparisons(tmp_path: Path, comparisons: dict[str, Any] | None) -> Path:
    pkg = tmp_path / "test.aieng"
    result_summary: dict[str, Any] = {}
    if comparisons is not None:
        result_summary["design_target_comparisons"] = comparisons
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test"}))
        zf.writestr("results/result_summary.json", json.dumps(result_summary))
    return pkg


def _make_pkg_with_result_summary_no_comparisons(tmp_path: Path) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test"}))
        zf.writestr("results/result_summary.json", json.dumps({"status": "ok"}))
    return pkg


def _make_empty_pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test"}))
    return pkg


# ---------------------------------------------------------------------------
# read_design_targets
# ---------------------------------------------------------------------------

class TestReadDesignTargets:
    def test_valid_design_targets(self, tmp_path: Path) -> None:
        design_targets = {
            "target_set_id": "ts-001",
            "format_version": "1.0",
            "targets": [
                {"target_id": "mass_reduce_10pct", "description": "reduce mass by at least 10%", "priority": "high"},
                {"target_id": "safety_factor_min", "description": "minimum safety factor >= 1.5", "priority": "critical"},
            ],
            "claim_policy": {"auto_advance": False},
        }
        pkg = _make_pkg_with_design_targets(tmp_path, design_targets)
        result = read_design_targets(str(pkg))
        assert result["ok"] is True
        assert result["has_design_targets"] is True
        assert result["target_set_id"] == "ts-001"
        assert result["format_version"] == "1.0"
        assert len(result["targets"]) == 2
        assert result["claim_policy"]["auto_advance"] is False
        assert result["warnings"] == []

    def test_missing_design_targets(self, tmp_path: Path) -> None:
        pkg = _make_empty_pkg(tmp_path)
        result = read_design_targets(str(pkg))
        assert result["ok"] is True
        assert result["has_design_targets"] is False
        assert result["target_set_id"] is None
        assert result["targets"] == []
        assert any("not found" in w for w in result["warnings"])

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        pkg = tmp_path / "test.aieng"
        with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("task/design_targets.yaml", "[{bad yaml")
        result = read_design_targets(str(pkg))
        assert result["ok"] is False
        assert "malformed" in result["error"].lower() or "Failed to read" in result["error"]

    def test_legacy_target_fields_accepted(self, tmp_path: Path) -> None:
        design_targets = {
            "targets": [
                {"target_id": "legacy_target", "threshold": 100.0, "unit": "mm"},
            ],
        }
        pkg = _make_pkg_with_design_targets(tmp_path, design_targets)
        result = read_design_targets(str(pkg))
        assert result["ok"] is True
        assert result["has_design_targets"] is True
        assert result["targets"][0]["target_id"] == "legacy_target"
        assert result["targets"][0]["threshold"] == 100.0

    def test_modern_target_fields_accepted(self, tmp_path: Path) -> None:
        design_targets = {
            "targets": [
                {"target_id": "modern_target", "comparator": "gte", "expected": {"threshold": 1.5}, "priority": "critical"},
            ],
        }
        pkg = _make_pkg_with_design_targets(tmp_path, design_targets)
        result = read_design_targets(str(pkg))
        assert result["ok"] is True
        assert result["has_design_targets"] is True
        assert result["targets"][0]["comparator"] == "gte"
        assert result["targets"][0]["expected"]["threshold"] == 1.5

    def test_claim_map_unchanged(self, tmp_path: Path) -> None:
        design_targets = {
            "targets": [{"target_id": "t1", "priority": "high"}],
        }
        pkg = _make_pkg_with_design_targets(tmp_path, design_targets)
        # Pre-read claim_map (none exists)
        result_before = read_design_targets(str(pkg))
        # Read again
        result_after = read_design_targets(str(pkg))
        assert result_before == result_after


# ---------------------------------------------------------------------------
# read_design_target_comparisons
# ---------------------------------------------------------------------------

class TestReadDesignTargetComparisons:
    def test_valid_comparisons(self, tmp_path: Path) -> None:
        comparisons = {
            "present": True,
            "target_set_id": "ts-001",
            "evaluated_at": "2026-05-17T00:00:00Z",
            "summary": {"total": 2, "pass": 1, "fail": 1, "unknown": 0, "not_evaluated": 0},
            "items": [
                {"target_id": "mass_reduce_10pct", "status": "pass"},
                {"target_id": "safety_factor_min", "status": "fail"},
            ],
        }
        pkg = _make_pkg_with_comparisons(tmp_path, comparisons)
        result = read_design_target_comparisons(str(pkg))
        assert result["ok"] is True
        assert result["has_comparisons"] is True
        assert result["design_target_comparisons"]["summary"]["pass"] == 1
        assert result["design_target_comparisons"]["summary"]["fail"] == 1
        assert result["summary"]["total"] == 2

    def test_missing_result_summary(self, tmp_path: Path) -> None:
        pkg = _make_empty_pkg(tmp_path)
        result = read_design_target_comparisons(str(pkg))
        assert result["ok"] is True
        assert result["has_comparisons"] is False
        assert result["design_target_comparisons"] is None
        assert any("not found" in w for w in result["warnings"])

    def test_result_summary_without_comparisons(self, tmp_path: Path) -> None:
        pkg = _make_pkg_with_result_summary_no_comparisons(tmp_path)
        result = read_design_target_comparisons(str(pkg))
        assert result["ok"] is True
        assert result["has_comparisons"] is False
        assert result["design_target_comparisons"] is None
        assert any("no design_target_comparisons" in w.lower() for w in result["warnings"])

    def test_malformed_result_summary(self, tmp_path: Path) -> None:
        pkg = tmp_path / "test.aieng"
        with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("results/result_summary.json", "not json")
        result = read_design_target_comparisons(str(pkg))
        assert result["ok"] is False
        assert "malformed" in result["error"].lower() or "Failed to read" in result["error"]

    def test_claim_map_unchanged(self, tmp_path: Path) -> None:
        comparisons = {"present": False}
        pkg = _make_pkg_with_comparisons(tmp_path, comparisons)
        result_before = read_design_target_comparisons(str(pkg))
        result_after = read_design_target_comparisons(str(pkg))
        assert result_before == result_after


# ---------------------------------------------------------------------------
# summarize_design_target_context
# ---------------------------------------------------------------------------

class TestSummarizeDesignTargetContext:
    def test_summary_with_targets_and_comparisons(self, tmp_path: Path) -> None:
        design_targets = {
            "targets": [
                {"target_id": "mass_reduce_10pct", "description": "reduce mass by at least 10%", "priority": "high"},
                {"target_id": "safety_factor_min", "description": "minimum safety factor >= 1.5", "priority": "critical"},
            ],
        }
        comparisons = {
            "present": True,
            "summary": {"total": 2, "pass": 1, "fail": 1, "unknown": 0, "not_evaluated": 0},
        }
        pkg = tmp_path / "test.aieng"
        with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("task/design_targets.yaml", yaml.safe_dump(design_targets))
            zf.writestr("results/result_summary.json", json.dumps({"design_target_comparisons": comparisons}))

        result = summarize_design_target_context(str(pkg))
        assert result["ok"] is True
        assert result["has_design_targets"] is True
        assert result["has_comparisons"] is True
        assert "mass_reduce_10pct" in result["summary_text"]
        assert "1 pass" in result["summary_text"]
        assert "Artifact-level requirements only" in result["summary_text"]

    def test_summary_without_targets(self, tmp_path: Path) -> None:
        pkg = _make_empty_pkg(tmp_path)
        result = summarize_design_target_context(str(pkg))
        assert result["ok"] is True
        assert result["has_design_targets"] is False
        assert "No design targets found" in result["summary_text"]


# ---------------------------------------------------------------------------
# Directory-form package support
# ---------------------------------------------------------------------------

class TestDirectoryPackages:
    def test_read_design_targets_from_directory(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "test_pkg"
        task_dir = pkg_dir / "task"
        task_dir.mkdir(parents=True)
        design_targets = {
            "target_set_id": "ts-dir",
            "targets": [{"target_id": "dir_target", "priority": "low"}],
        }
        (task_dir / "design_targets.yaml").write_text(yaml.safe_dump(design_targets), encoding="utf-8")

        result = read_design_targets(str(pkg_dir))
        assert result["ok"] is True
        assert result["has_design_targets"] is True
        assert result["target_set_id"] == "ts-dir"

    def test_read_comparisons_from_directory(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "test_pkg"
        results_dir = pkg_dir / "results"
        results_dir.mkdir(parents=True)
        comparisons = {"present": True, "summary": {"total": 1, "pass": 1}}
        (results_dir / "result_summary.json").write_text(
            json.dumps({"design_target_comparisons": comparisons}), encoding="utf-8"
        )

        result = read_design_target_comparisons(str(pkg_dir))
        assert result["ok"] is True
        assert result["has_comparisons"] is True
