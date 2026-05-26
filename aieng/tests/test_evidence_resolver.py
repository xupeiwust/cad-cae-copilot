"""Tests for aieng.evidence_resolver."""

from __future__ import annotations

from typing import Any

import pytest

from aieng.evidence_resolver import STALE_EVIDENCE_CATEGORIES, resolve_evidence_reference


# ── shared fixtures ──────────────────────────────────────────────────────────

_DISP_PATH = "results/fields/displacement.summary.json"
_FRD_PATH = "simulation/runs/run_001/outputs/result.frd"
_CM_PATH = "results/computed_metrics.json"

_BASE_ENTRIES: list[dict[str, Any]] = [
    {
        "id": "cm_entry",
        "path": _CM_PATH,
        "kind": "result",
        "role": "computed_extrema",
        "exists": True,
        "supports": ["audit"],
    },
    {
        "id": "frd_entry",
        "path": _FRD_PATH,
        "kind": "solver_raw_output",
        "role": "solver_raw_output",
        "exists": True,
        "supports": ["numerical_result_source"],
    },
]

_BASE_PATHS: list[str] = [
    "manifest.json",
    _CM_PATH,
    _FRD_PATH,
    _DISP_PATH,
    "results/evidence_index.json",
]

_STALE_RS: dict[str, Any] = {
    "requires_revalidation": True,
    "current_geometry_revision": 2,
    "last_validated_geometry_revision": 1,
}

_FRESH_RS: dict[str, Any] = {
    "requires_revalidation": False,
    "current_geometry_revision": 2,
    "last_validated_geometry_revision": 2,
}


# ── contract helper ──────────────────────────────────────────────────────────

def _assert_contract(obj: dict[str, Any]) -> None:
    required = (
        "schema_version", "path", "exists", "in_evidence_index",
        "evidence_index_entry", "manifest_category", "manifest_kind",
        "evidence_role", "requires_revalidation", "current_geometry_revision",
        "last_validated_geometry_revision", "usable_for_claim_proposal",
        "warnings", "claim_advancement",
    )
    for field in required:
        assert field in obj, f"resolved reference missing field: {field!r}"
    assert obj["schema_version"] == "0.1"
    assert obj["claim_advancement"] == "none"
    assert isinstance(obj["exists"], bool)
    assert isinstance(obj["in_evidence_index"], bool)
    assert isinstance(obj["usable_for_claim_proposal"], bool)
    assert isinstance(obj["requires_revalidation"], bool)
    assert isinstance(obj["warnings"], list)
    assert isinstance(obj["path"], str)
    assert isinstance(obj["manifest_category"], str)
    assert isinstance(obj["manifest_kind"], str)


# ── classification integration ───────────────────────────────────────────────

class TestClassificationIntegration:
    def test_field_summary_category(self) -> None:
        ref = resolve_evidence_reference(
            path=_DISP_PATH,
            package_paths=_BASE_PATHS,
        )
        _assert_contract(ref)
        assert ref["manifest_category"] == "field_summary"
        assert ref["manifest_kind"] == "field"
        assert ref["evidence_role"] == "displacement_extrema"

    def test_frd_category(self) -> None:
        ref = resolve_evidence_reference(
            path=_FRD_PATH,
            package_paths=_BASE_PATHS,
        )
        _assert_contract(ref)
        assert ref["manifest_category"] == "solver_output"
        assert ref["manifest_kind"] == "solver_raw_output"

    def test_computed_metrics_category(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
        )
        assert ref["manifest_category"] == "solver_output"

    def test_unknown_path_category(self) -> None:
        ref = resolve_evidence_reference(
            path="custom/deep/file.bin",
            package_paths=[],
        )
        _assert_contract(ref)
        assert ref["manifest_category"] == "unknown"
        assert ref["manifest_kind"] == "unknown"
        assert ref["evidence_role"] is None


# ── existence and evidence index ─────────────────────────────────────────────

class TestExistenceAndIndex:
    def test_existing_path_exists_true(self) -> None:
        ref = resolve_evidence_reference(
            path=_DISP_PATH,
            package_paths=_BASE_PATHS,
        )
        assert ref["exists"] is True
        assert ref["usable_for_claim_proposal"] is True

    def test_missing_path_exists_false(self) -> None:
        ref = resolve_evidence_reference(
            path="missing/artifact.json",
            package_paths=_BASE_PATHS,
        )
        assert ref["exists"] is False

    def test_path_in_evidence_index(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            evidence_entries=_BASE_ENTRIES,
        )
        assert ref["in_evidence_index"] is True
        assert ref["evidence_index_entry"] is not None
        assert ref["evidence_index_entry"]["path"] == _CM_PATH

    def test_path_not_in_evidence_index(self) -> None:
        ref = resolve_evidence_reference(
            path=_DISP_PATH,
            package_paths=_BASE_PATHS,
            evidence_entries=_BASE_ENTRIES,
        )
        assert ref["in_evidence_index"] is False
        assert ref["evidence_index_entry"] is None

    def test_path_absent_but_in_evidence_index_is_usable(self) -> None:
        # A path that is in the evidence index but not in the package ZIP
        # (e.g. catalogued but file not yet materialised) is still usable.
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=["manifest.json"],   # CM not in package
            evidence_entries=_BASE_ENTRIES,
        )
        assert ref["exists"] is False
        assert ref["in_evidence_index"] is True
        assert ref["usable_for_claim_proposal"] is True

    def test_missing_entirely_not_usable(self) -> None:
        ref = resolve_evidence_reference(
            path="results/ghost.json",
            package_paths=_BASE_PATHS,
            evidence_entries=_BASE_ENTRIES,
        )
        assert ref["exists"] is False
        assert ref["in_evidence_index"] is False
        assert ref["usable_for_claim_proposal"] is False
        assert "path_not_found_in_package_or_evidence_index" in ref["warnings"]


# ── stale behavior ───────────────────────────────────────────────────────────

class TestStaleBehavior:
    def test_stale_categories_constant(self) -> None:
        for cat in ("solver_output", "summary", "field_summary", "evidence_index"):
            assert cat in STALE_EVIDENCE_CATEGORIES

    def test_stale_warning_on_solver_output(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        assert ref["requires_revalidation"] is True
        assert "evidence_from_stale_geometry_state" in ref["warnings"]

    def test_stale_warning_on_field_summary(self) -> None:
        ref = resolve_evidence_reference(
            path=_DISP_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        assert "evidence_from_stale_geometry_state" in ref["warnings"]

    def test_stale_warning_on_result_summary(self) -> None:
        ref = resolve_evidence_reference(
            path="results/result_summary.json",
            package_paths=["results/result_summary.json"],
            revalidation_status=_STALE_RS,
        )
        assert "evidence_from_stale_geometry_state" in ref["warnings"]

    def test_stale_warning_on_evidence_index(self) -> None:
        ref = resolve_evidence_reference(
            path="results/evidence_index.json",
            package_paths=["results/evidence_index.json"],
            revalidation_status=_STALE_RS,
        )
        assert "evidence_from_stale_geometry_state" in ref["warnings"]

    def test_no_stale_warning_on_geometry(self) -> None:
        ref = resolve_evidence_reference(
            path="geometry/source.step",
            package_paths=["geometry/source.step"],
            revalidation_status=_STALE_RS,
        )
        assert "evidence_from_stale_geometry_state" not in ref["warnings"]

    def test_stale_evidence_remains_usable(self) -> None:
        ref = resolve_evidence_reference(
            path=_DISP_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        assert "evidence_from_stale_geometry_state" in ref["warnings"]
        assert ref["usable_for_claim_proposal"] is True

    def test_fresh_revalidation_no_stale_warning(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_FRESH_RS,
        )
        assert ref["requires_revalidation"] is False
        assert "evidence_from_stale_geometry_state" not in ref["warnings"]

    def test_no_revalidation_status_no_stale_warning(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
        )
        assert ref["requires_revalidation"] is False
        assert "evidence_from_stale_geometry_state" not in ref["warnings"]


# ── geometry revisions ───────────────────────────────────────────────────────

class TestGeometryRevisions:
    def test_current_revision_surfaced(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        assert ref["current_geometry_revision"] == 2

    def test_last_validated_revision_surfaced(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        assert ref["last_validated_geometry_revision"] == 1

    def test_revisions_none_when_no_revalidation_status(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
        )
        assert ref["current_geometry_revision"] is None
        assert ref["last_validated_geometry_revision"] is None

    def test_fresh_revisions_equal(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_FRESH_RS,
        )
        assert ref["current_geometry_revision"] == ref["last_validated_geometry_revision"] == 2


# ── claim advancement contract ───────────────────────────────────────────────

class TestClaimAdvancement:
    def test_claim_advancement_none_always(self) -> None:
        for path in (_DISP_PATH, _FRD_PATH, _CM_PATH, "missing/file.json"):
            ref = resolve_evidence_reference(
                path=path,
                package_paths=_BASE_PATHS,
                revalidation_status=_STALE_RS,
            )
            assert ref["claim_advancement"] == "none", (
                f"claim_advancement must be 'none' for {path!r}"
            )

    def test_contract_all_cases(self) -> None:
        cases = [
            (_DISP_PATH, _BASE_PATHS, None, None),
            (_FRD_PATH, _BASE_PATHS, _BASE_ENTRIES, _STALE_RS),
            ("missing/x.json", [], None, None),
            (_CM_PATH, _BASE_PATHS, _BASE_ENTRIES, _FRESH_RS),
        ]
        for path, pkg, entries, rs in cases:
            ref = resolve_evidence_reference(
                path=path,
                package_paths=pkg,
                evidence_entries=entries,
                revalidation_status=rs,
            )
            _assert_contract(ref)


# ── edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_package_paths(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=[],
        )
        assert ref["exists"] is False
        assert ref["usable_for_claim_proposal"] is False

    def test_none_evidence_entries_treated_as_empty(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            evidence_entries=None,
        )
        assert ref["in_evidence_index"] is False

    def test_package_paths_as_generator(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=(p for p in _BASE_PATHS),
        )
        assert ref["exists"] is True

    def test_evidence_entries_as_generator(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            evidence_entries=(e for e in _BASE_ENTRIES),
        )
        assert ref["in_evidence_index"] is True

    def test_duplicate_warnings_not_emitted(self) -> None:
        ref = resolve_evidence_reference(
            path=_CM_PATH,
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        assert ref["warnings"].count("evidence_from_stale_geometry_state") == 1

    def test_frd_in_index_and_package(self) -> None:
        ref = resolve_evidence_reference(
            path=_FRD_PATH,
            package_paths=_BASE_PATHS,
            evidence_entries=_BASE_ENTRIES,
        )
        assert ref["exists"] is True
        assert ref["in_evidence_index"] is True
        assert ref["usable_for_claim_proposal"] is True
