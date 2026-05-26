"""Tests for the Phase 35 PR 3 ``aieng compare-design-targets`` CLI command
and its public helper ``compare_design_targets_for_package``.

The CLI surface must:
- Read-only by default (no package mutation).
- Reuse comparison logic from ``cae_result_summary.py`` (no duplication).
- Support ``--output text`` (default) and ``--output json``.
- Support ``--write-summary`` for an atomic ZIP rewrite that injects
  ``design_target_comparisons`` into ``results/result_summary.json``,
  preserving all existing summary fields.
- NEVER mutate ``results/claim_map.json``.
- Return a non-zero exit code with a clear message when
  ``task/design_targets.yaml`` is missing.
- Preserve legacy 0.1.0 target format compatibility.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from aieng.cae_result_summary import compare_design_targets_for_package
from aieng.cli import main


def _build_package(tmp_path: Path, members: dict[str, bytes]) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        for name, data in members.items():
            zf.writestr(name, data)
    return pkg


def _computed_metrics(stress: float, sf: float | None = None) -> bytes:
    metrics: dict[str, dict[str, object]] = {
        "max_von_mises_stress": {"value": stress, "unit": "MPa"},
    }
    if sf is not None:
        metrics["minimum_safety_factor"] = {"value": sf, "unit": None}
    return json.dumps({
        "load_cases": [{"id": "lc1", "metrics": metrics}],
    }).encode()


_MODERN_TARGETS = b"""
format_version: "0.1.1"
target_set_id: "bracket_v2"
targets:
  - target_id: stress_limit
    target_type: maximum_von_mises_stress
    description: Allowable stress for Al-6061-T6
    comparator: "<="
    threshold: 350.0
    unit: MPa
    priority: high
claim_policy:
  targets_are_acceptance_criteria: true
  compliance_requires_evidence: true
  physical_correctness_not_claimed: true
"""

_LEGACY_TARGETS = b"""
format_version: "0.1.0"
targets:
  - id: stress_limit
    metric: max_von_mises_stress
    operator: "<="
    value: 350.0
    unit: MPa
claim_policy:
  targets_are_acceptance_criteria: true
  compliance_requires_evidence: true
  physical_correctness_not_claimed: true
"""


class TestHelper:
    def test_returns_comparisons_block_with_modern_format(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
            },
        )
        block = compare_design_targets_for_package(pkg)
        assert block["present"] is True
        assert block["target_set_id"] == "bracket_v2"
        assert block["summary"]["total"] == 1
        assert block["summary"]["pass"] == 1
        assert block["items"][0]["status"] == "pass"
        assert block["items"][0]["target_id"] == "stress_limit"

    def test_legacy_format_still_works(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _LEGACY_TARGETS,
            },
        )
        block = compare_design_targets_for_package(pkg)
        assert block["present"] is True
        assert block["summary"]["pass"] == 1
        assert block["items"][0]["target_id"] == "stress_limit"
        assert block["items"][0]["status"] == "pass"

    def test_missing_evidence_returns_not_evaluated(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {"task/design_targets.yaml": _MODERN_TARGETS},
        )
        block = compare_design_targets_for_package(pkg)
        assert block["present"] is True
        # No computed_metrics.json present → not_evaluated
        assert block["summary"]["not_evaluated"] == 1
        assert block["items"][0]["status"] == "not_evaluated"

    def test_missing_design_targets_yaml_raises(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {"results/computed_metrics.json": _computed_metrics(100.0)},
        )
        with pytest.raises(FileNotFoundError):
            compare_design_targets_for_package(pkg)

    def test_missing_package_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compare_design_targets_for_package(tmp_path / "does_not_exist.aieng")


class TestCliReadOnly:
    def test_text_output(self, tmp_path: Path, capsys) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
            },
        )
        rc = main(["compare-design-targets", str(pkg)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "bracket_v2" in out
        assert "1 pass" in out
        assert "[pass] stress_limit" in out
        assert "engineering certification" in out

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
            },
        )
        rc = main(["compare-design-targets", str(pkg), "--output", "json"])
        assert rc == 0
        out = capsys.readouterr().out
        block = json.loads(out)
        assert block["present"] is True
        assert block["summary"]["pass"] == 1
        assert block["target_set_id"] == "bracket_v2"

    def test_does_not_mutate_package(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
            },
        )
        before = hashlib.sha256(pkg.read_bytes()).hexdigest()
        rc = main(["compare-design-targets", str(pkg)])
        assert rc == 0
        after = hashlib.sha256(pkg.read_bytes()).hexdigest()
        assert before == after, "Read-only invocation must not modify the package bytes"

    def test_missing_design_targets_returns_nonzero(self, tmp_path: Path, capsys) -> None:
        pkg = _build_package(
            tmp_path,
            {"results/computed_metrics.json": _computed_metrics(100.0)},
        )
        rc = main(["compare-design-targets", str(pkg)])
        assert rc == 2
        err = capsys.readouterr().err
        assert "task/design_targets.yaml" in err
        assert "FAIL" in err

    def test_missing_evidence_does_not_crash(self, tmp_path: Path, capsys) -> None:
        pkg = _build_package(
            tmp_path,
            {"task/design_targets.yaml": _MODERN_TARGETS},
        )
        rc = main(["compare-design-targets", str(pkg), "--output", "json"])
        assert rc == 0
        block = json.loads(capsys.readouterr().out)
        assert block["items"][0]["status"] == "not_evaluated"

    def test_legacy_format_via_cli(self, tmp_path: Path, capsys) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(400.0),  # fail >350
                "task/design_targets.yaml": _LEGACY_TARGETS,
            },
        )
        rc = main(["compare-design-targets", str(pkg), "--output", "json"])
        assert rc == 0
        block = json.loads(capsys.readouterr().out)
        assert block["summary"]["fail"] == 1
        assert block["items"][0]["status"] == "fail"


class TestCliWriteSummary:
    def test_writes_design_target_comparisons(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
            },
        )
        rc = main(["compare-design-targets", str(pkg), "--write-summary"])
        assert rc == 0
        with zipfile.ZipFile(pkg, "r") as zf:
            data = json.loads(zf.read("results/result_summary.json"))
        assert "design_target_comparisons" in data
        block = data["design_target_comparisons"]
        assert block["present"] is True
        assert block["summary"]["pass"] == 1

    def test_preserves_existing_summary_fields(self, tmp_path: Path) -> None:
        existing_summary = {
            "schema_version": "0.3",
            "summary_type": "cae_postprocessing",
            "status": {"mode": "cae_result", "warnings": []},
            "load_cases": [{"id": "lc1"}],
            "computed_values": {"extrema_computed": True},
            "design_target_comparisons": {
                "present": False,
                "summary": {"total": 0, "pass": 0, "fail": 0, "unknown": 0, "not_evaluated": 0},
                "items": [],
            },
        }
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
                "results/result_summary.json": json.dumps(existing_summary).encode(),
            },
        )
        rc = main(["compare-design-targets", str(pkg), "--write-summary"])
        assert rc == 0
        with zipfile.ZipFile(pkg, "r") as zf:
            data = json.loads(zf.read("results/result_summary.json"))
        # All previous fields preserved
        assert data["status"] == {"mode": "cae_result", "warnings": []}
        assert data["load_cases"] == [{"id": "lc1"}]
        assert data["computed_values"] == {"extrema_computed": True}
        assert data["summary_type"] == "cae_postprocessing"
        assert data["schema_version"] == "0.3"
        # Comparison block was replaced with fresh evaluation
        assert data["design_target_comparisons"]["summary"]["pass"] == 1

    def test_does_not_modify_evidence_index(self, tmp_path: Path) -> None:
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
            },
        )
        with zipfile.ZipFile(pkg, "r") as zf:
            before = zf.read("results/evidence_index.json") if "results/evidence_index.json" in zf.namelist() else None
        rc = main(["compare-design-targets", str(pkg), "--write-summary"])
        assert rc == 0
        with zipfile.ZipFile(pkg, "r") as zf:
            after = zf.read("results/evidence_index.json") if "results/evidence_index.json" in zf.namelist() else None
        assert before == after, "evidence_index.json must be unchanged after --write-summary"

    def test_no_duplicate_result_summary_entries(self, tmp_path: Path) -> None:
        existing_summary = {"schema_version": "0.3", "foo": "bar"}
        pkg = _build_package(
            tmp_path,
            {
                "results/computed_metrics.json": _computed_metrics(298.0),
                "task/design_targets.yaml": _MODERN_TARGETS,
                "results/result_summary.json": json.dumps(existing_summary).encode(),
            },
        )
        rc = main(["compare-design-targets", str(pkg), "--write-summary"])
        assert rc == 0
        with zipfile.ZipFile(pkg, "r") as zf:
            names = zf.namelist()
        # The summary path appears exactly once
        assert names.count("results/result_summary.json") == 1

    def test_missing_design_targets_writeback_fails(self, tmp_path: Path, capsys) -> None:
        pkg = _build_package(
            tmp_path,
            {"results/computed_metrics.json": _computed_metrics(100.0)},
        )
        rc = main(["compare-design-targets", str(pkg), "--write-summary"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "task/design_targets.yaml" in err
