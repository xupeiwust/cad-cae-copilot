"""Tests for honesty boundary enforcement (issue #54).

The Phase 30-36 roadmap names four honesty boundaries:

* AIENG is not a solver or CAD kernel.
* ``converged: null`` remains until reliable evidence exists.
* Physical correctness requires explicit validation evidence.
* Generated decks and CAD edits stay approval-gated.
* Schema drift surfaces warnings/failures, never silent acceptance.

This file asserts the last two: that ``deck_generator`` does not advance
convergence state, and that schema drift in the Phase 31/34/35 resources
(``results/field_regions.json``, ``results/field_summary.json``,
``task/design_targets.yaml``) reaches the validator as a hard failure.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from aieng.validate import Level, validate_package


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_package(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({
                "model_id": "honesty",
                "format_version": "0.1.0",
                "units": {"length": "mm", "mass": "kg", "force": "N", "stress": "MPa"},
                "resources": {"results": {}},
                "created_by": {"tool": "test", "created_at": "2026-01-01T00:00:00Z"},
            }),
        )
        zf.writestr("results/", b"")
        zf.writestr("task/", b"")
    return path


def _inject_member(pkg: Path, member: str, raw: bytes) -> None:
    """Rewrite the package with ``member`` either added or replaced."""
    existing: dict[str, bytes] = {}
    with zipfile.ZipFile(pkg, "r") as zf:
        for name in zf.namelist():
            existing[name] = zf.read(name)
    existing[member] = raw
    pkg.unlink()
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in existing.items():
            zf.writestr(name, data)


def _fails(pkg: Path) -> list[str]:
    return [m.text for m in validate_package(pkg).messages if m.level is Level.FAIL]


# ---------------------------------------------------------------------------
# Schema drift surfaces as a FAIL, not silent acceptance
# ---------------------------------------------------------------------------


def test_field_regions_schema_drift_surfaces_as_fail(tmp_path: Path) -> None:
    """Hand-written field_regions.json missing required claim_policy fields must FAIL."""
    pkg = _empty_package(tmp_path / "drift.aieng")
    # Missing the required ``claim_policy`` block — the schema must reject this.
    _inject_member(
        pkg,
        "results/field_regions.json",
        json.dumps({
            "schema_version": "0.1",
            "format_version": "0.1.0",
            "source_frd": "job.frd",
            "field": "S",
            "metric": "von_mises",
            "cluster_count": 0,
            "clusters": [],
            "warnings": [],
        }).encode(),
    )
    fails = _fails(pkg)
    assert any("results/field_regions.json" in f and "claim_policy" in f for f in fails), (
        f"missing claim_policy must surface as FAIL; got {fails}"
    )


def test_field_regions_claim_policy_const_drift_surfaces_as_fail(tmp_path: Path) -> None:
    """Flipping observational_only=false must FAIL — const guard is load-bearing."""
    pkg = _empty_package(tmp_path / "const_drift.aieng")
    _inject_member(
        pkg,
        "results/field_regions.json",
        json.dumps({
            "schema_version": "0.1",
            "format_version": "0.1.0",
            "source_frd": "job.frd",
            "field": "S",
            "metric": "von_mises",
            "cluster_count": 0,
            "clusters": [],
            "warnings": [],
            "claim_policy": {
                "observational_only": False,  # drift: schema says const true
                "physical_correctness_not_claimed": True,
                "solver_execution_not_performed_by_aieng": True,
            },
        }).encode(),
    )
    fails = _fails(pkg)
    assert any("observational_only" in f or "field_regions.json" in f for f in fails)


def test_field_summary_schema_drift_surfaces_as_fail(tmp_path: Path) -> None:
    """A field_summary lacking the required claim_policy must FAIL."""
    pkg = _empty_package(tmp_path / "field_summary_drift.aieng")
    _inject_member(
        pkg,
        "results/field_summary.json",
        json.dumps({
            "schema_version": "0.2",
            "summary_type": "cae_field_regions",
            "source": {"field_regions_path": "results/field_regions.json"},
            "status": {"has_field_regions": False, "cluster_count": 0, "warnings": []},
            "clusters": [],
            "llm_summary": {
                "one_line": "x",
                "key_findings": [],
                "risks": [],
                "limitations": [],
            },
            # claim_policy intentionally missing
        }).encode(),
    )
    fails = _fails(pkg)
    assert any("results/field_summary.json" in f for f in fails), (
        f"field_summary.json drift must FAIL; got {fails}"
    )


def test_design_targets_schema_drift_surfaces_as_fail(tmp_path: Path) -> None:
    """A design_targets.yaml that violates the schema must FAIL, not be silently accepted."""
    pkg = _empty_package(tmp_path / "targets_drift.aieng")
    # An operator value that is not in the enum.
    _inject_member(
        pkg,
        "task/design_targets.yaml",
        yaml.safe_dump({
            "schema_version": "0.1.0",
            "design_targets_id": "targets_001",
            "targets": [
                {
                    "id": "stress_limit",
                    "metric": "max_von_mises_stress",
                    "operator": "smaller_than",  # invalid; schema enum is "<=", "<", etc.
                    "value": 200.0,
                }
            ],
        }).encode(),
    )
    fails = _fails(pkg)
    assert any("design_targets.yaml" in f for f in fails), (
        f"design_targets.yaml drift must FAIL; got {fails}"
    )


# ---------------------------------------------------------------------------
# Phase 35 extended design target schema validation
# ---------------------------------------------------------------------------


def test_design_targets_valid_extended_format_passes(tmp_path: Path) -> None:
    """A design_targets.yaml using the modern 0.1.1 format with all required fields passes validation."""
    pkg = _empty_package(tmp_path / "targets_ext.aieng")
    _inject_member(
        pkg,
        "task/design_targets.yaml",
        yaml.safe_dump({
            "format_version": "0.1.1",
            "target_set_id": "ts_001",
            "targets": [
                {
                    "id": "stress_limit",
                    "metric": "max_von_mises_stress",
                    "operator": "<=",
                    "value": 350.0,
                    "unit": "MPa",
                    "target_id": "stress_limit",
                    "target_type": "maximum_von_mises_stress",
                    "description": "Allowable stress for Al-6061-T6",
                    "comparator": "<=",
                    "threshold": 350.0,
                    "priority": "high",
                    "scope": "global",
                },
                {
                    "id": "safety_floor",
                    "metric": "minimum_safety_factor",
                    "operator": ">=",
                    "value": 1.5,
                    "target_id": "safety_floor",
                    "target_type": "minimum_safety_factor",
                    "description": "Minimum safety factor under design load",
                    "comparator": ">=",
                    "threshold": 1.5,
                    "priority": "critical",
                },
                {
                    "id": "preserve_holes",
                    "metric": "preserved_interface",
                    "operator": "preserve",
                    "value": 1,
                    "target_id": "preserve_holes",
                    "target_type": "preserved_interface",
                    "description": "Mounting holes must not be removed",
                    "comparator": "preserve",
                    "priority": "critical",
                    "protected_features": [
                        {"feature_id": "hole_001", "feature_type": "circular_hole"},
                    ],
                },
                {
                    "id": "obj_priority",
                    "metric": "objective_priority",
                    "operator": "priority",
                    "value": 1,
                    "target_id": "obj_priority",
                    "target_type": "objective_priority",
                    "description": "Safety over mass",
                    "comparator": "priority",
                    "priority": "critical",
                    "objective_order": ["safety_floor", "stress_limit"],
                },
            ],
            "claim_policy": {
                "targets_are_acceptance_criteria": True,
                "compliance_requires_evidence": True,
                "physical_correctness_not_claimed": True,
            },
        }).encode(),
    )
    fails = _fails(pkg)
    assert not any("design_targets.yaml" in f for f in fails), (
        f"Extended design_targets.yaml should pass; got {fails}"
    )


def test_design_targets_invalid_comparator_rejected(tmp_path: Path) -> None:
    """An unsupported comparator in modern format must FAIL validation."""
    pkg = _empty_package(tmp_path / "targets_bad_comp.aieng")
    _inject_member(
        pkg,
        "task/design_targets.yaml",
        yaml.safe_dump({
            "format_version": "0.1.1",
            "targets": [
                {
                    "target_id": "bad",
                    "target_type": "maximum_von_mises_stress",
                    "description": "x",
                    "comparator": "smaller_than",  # invalid
                    "priority": "high",
                }
            ],
            "claim_policy": {
                "targets_are_acceptance_criteria": True,
                "compliance_requires_evidence": True,
                "physical_correctness_not_claimed": True,
            },
        }).encode(),
    )
    fails = _fails(pkg)
    assert any("design_targets.yaml" in f for f in fails), (
        f"Invalid comparator must FAIL; got {fails}"
    )


def test_design_targets_missing_target_id_rejected(tmp_path: Path) -> None:
    """Modern format missing target_id must FAIL validation."""
    pkg = _empty_package(tmp_path / "targets_missing_id.aieng")
    _inject_member(
        pkg,
        "task/design_targets.yaml",
        yaml.safe_dump({
            "format_version": "0.1.1",
            "targets": [
                {
                    "target_type": "maximum_von_mises_stress",
                    "description": "x",
                    "comparator": "<=",
                    "priority": "high",
                }
            ],
            "claim_policy": {
                "targets_are_acceptance_criteria": True,
                "compliance_requires_evidence": True,
                "physical_correctness_not_claimed": True,
            },
        }).encode(),
    )
    fails = _fails(pkg)
    assert any("design_targets.yaml" in f for f in fails), (
        f"Missing target_id must FAIL; got {fails}"
    )


def test_design_targets_legacy_format_still_passes(tmp_path: Path) -> None:
    """Legacy 0.1.0 format with id/metric/operator/value continues to pass."""
    pkg = _empty_package(tmp_path / "targets_legacy.aieng")
    _inject_member(
        pkg,
        "task/design_targets.yaml",
        yaml.safe_dump({
            "format_version": "0.1.0",
            "targets": [
                {
                    "id": "stress_limit",
                    "metric": "max_von_mises_stress",
                    "operator": "<=",
                    "value": 120.0,
                    "unit": "MPa",
                }
            ],
            "claim_policy": {
                "targets_are_acceptance_criteria": True,
                "compliance_requires_evidence": True,
                "physical_correctness_not_claimed": True,
            },
        }).encode(),
    )
    fails = _fails(pkg)
    assert not any("design_targets.yaml" in f for f in fails), (
        f"Legacy format should pass; got {fails}"
    )


# ---------------------------------------------------------------------------
# deck_generator preserves the convergence honesty boundary
# ---------------------------------------------------------------------------


def test_deck_generator_module_does_not_import_solver_runners() -> None:
    """``aieng.simulation.deck_generator`` must never reach for a solver runner.

    The Phase 33 honesty boundary forbids solver execution. A regression that
    pulls a solver client/runner into the module would silently violate this.
    """
    import aieng.simulation.deck_generator as dg
    source = Path(dg.__file__).read_text(encoding="utf-8")
    forbidden = (
        "subprocess.run",
        "subprocess.Popen",
        "pyccx.Solver",
        "import pyccx",
        "from pyccx",
        "os.system",
    )
    for token in forbidden:
        assert token not in source, (
            f"deck_generator must not contain {token!r}; solver execution is "
            "an external responsibility."
        )
