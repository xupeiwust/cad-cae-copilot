"""Tests for aieng.revalidation_status."""

from __future__ import annotations

import pytest

from aieng.revalidation_status import (
    REVALIDATION_STATUS_PATH,
    build_revalidation_response,
    default_revalidation_status,
    record_geometry_edit_status,
    record_solver_validation_status,
    validate_revalidation_status,
)


# ── default_revalidation_status ──────────────────────────────────────────────

class TestDefaultRevalidationStatus:
    def test_requires_revalidation_false(self) -> None:
        s = default_revalidation_status()
        assert s["requires_revalidation"] is False

    def test_current_geometry_revision_zero(self) -> None:
        s = default_revalidation_status()
        assert s["current_geometry_revision"] == 0

    def test_last_validated_geometry_revision_none(self) -> None:
        s = default_revalidation_status()
        assert s["last_validated_geometry_revision"] is None

    def test_stale_since_geometry_revision_none(self) -> None:
        s = default_revalidation_status()
        assert s["stale_since_geometry_revision"] is None

    def test_validated_by_run_id_none(self) -> None:
        s = default_revalidation_status()
        assert s["validated_by_run_id"] is None

    def test_claim_advancement_none(self) -> None:
        s = default_revalidation_status()
        assert s["claim_advancement"] == "none"

    def test_schema_version(self) -> None:
        s = default_revalidation_status()
        assert s["schema_version"] == "0.2"

    def test_affected_domains_present(self) -> None:
        s = default_revalidation_status()
        assert isinstance(s["affected_domains"], list)
        assert len(s["affected_domains"]) > 0

    def test_valid_status(self) -> None:
        assert validate_revalidation_status(default_revalidation_status()) == []


# ── record_geometry_edit_status ──────────────────────────────────────────────

class TestRecordGeometryEditStatus:
    def test_from_absent_increments_to_one(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["current_geometry_revision"] == 1

    def test_from_zero_increments_to_one(self) -> None:
        s = record_geometry_edit_status({"current_geometry_revision": 0})
        assert s["current_geometry_revision"] == 1

    def test_repeated_edits_increment(self) -> None:
        s1 = record_geometry_edit_status(None)
        s2 = record_geometry_edit_status(s1)
        s3 = record_geometry_edit_status(s2)
        assert s3["current_geometry_revision"] == 3

    def test_requires_revalidation_true(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["requires_revalidation"] is True

    def test_geometry_modified_true(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["geometry_modified"] is True

    def test_reason_geometry_changed(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["reason"] == "geometry_changed"

    def test_default_triggering_tool(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["triggering_tool"] == "cad.edit_parameter"

    def test_custom_triggering_tool(self) -> None:
        s = record_geometry_edit_status(None, triggering_tool="cad.other")
        assert s["triggering_tool"] == "cad.other"

    def test_stale_since_equals_new_revision(self) -> None:
        s = record_geometry_edit_status({"current_geometry_revision": 2})
        assert s["stale_since_geometry_revision"] == 3

    def test_preserves_last_validated_geometry_revision(self) -> None:
        prev = {"current_geometry_revision": 3, "last_validated_geometry_revision": 2}
        s = record_geometry_edit_status(prev)
        assert s["last_validated_geometry_revision"] == 2

    def test_last_validated_none_when_never_validated(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["last_validated_geometry_revision"] is None

    def test_validated_by_run_id_cleared(self) -> None:
        prev = {"current_geometry_revision": 1, "validated_by_run_id": "run_001"}
        s = record_geometry_edit_status(prev)
        assert s["validated_by_run_id"] is None

    def test_affected_artifacts_stored(self) -> None:
        s = record_geometry_edit_status(None, affected_artifacts=["geometry/source.step"])
        assert s["affected_artifacts"] == ["geometry/source.step"]

    def test_affected_artifacts_default_empty(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["affected_artifacts"] == []

    def test_claim_advancement_none(self) -> None:
        s = record_geometry_edit_status(None)
        assert s["claim_advancement"] == "none"

    def test_custom_timestamp(self) -> None:
        ts = "2026-01-01T00:00:00+00:00"
        s = record_geometry_edit_status(None, timestamp=ts)
        assert s["recorded_at"] == ts

    def test_timestamp_auto_generated(self) -> None:
        s = record_geometry_edit_status(None)
        assert "T" in s["recorded_at"]

    def test_schema_version(self) -> None:
        assert record_geometry_edit_status(None)["schema_version"] == "0.2"

    def test_valid_status(self) -> None:
        assert validate_revalidation_status(record_geometry_edit_status(None)) == []


# ── record_solver_validation_status ─────────────────────────────────────────

class TestRecordSolverValidationStatus:
    def test_requires_revalidation_false(self) -> None:
        prev = record_geometry_edit_status(None)
        s = record_solver_validation_status(prev)
        assert s["requires_revalidation"] is False

    def test_geometry_modified_false(self) -> None:
        s = record_solver_validation_status(None)
        assert s["geometry_modified"] is False

    def test_reason_solver_rerun_completed(self) -> None:
        s = record_solver_validation_status(None)
        assert s["reason"] == "solver_rerun_completed"

    def test_triggering_tool(self) -> None:
        s = record_solver_validation_status(None)
        assert s["triggering_tool"] == "cae.run_solver"

    def test_preserves_current_geometry_revision(self) -> None:
        prev = record_geometry_edit_status({"current_geometry_revision": 4})
        s = record_solver_validation_status(prev)
        assert s["current_geometry_revision"] == 5

    def test_last_validated_equals_current(self) -> None:
        prev = record_geometry_edit_status({"current_geometry_revision": 2})
        s = record_solver_validation_status(prev)
        assert s["last_validated_geometry_revision"] == s["current_geometry_revision"]

    def test_stale_since_cleared(self) -> None:
        prev = record_geometry_edit_status(None)
        s = record_solver_validation_status(prev)
        assert s["stale_since_geometry_revision"] is None

    def test_validated_by_run_id_stored(self) -> None:
        s = record_solver_validation_status(None, run_id="run_042")
        assert s["validated_by_run_id"] == "run_042"

    def test_validated_by_run_id_none_when_absent(self) -> None:
        s = record_solver_validation_status(None)
        assert s["validated_by_run_id"] is None

    def test_from_absent_status(self) -> None:
        s = record_solver_validation_status(None)
        assert s["current_geometry_revision"] == 0
        assert s["last_validated_geometry_revision"] == 0

    def test_claim_advancement_none(self) -> None:
        s = record_solver_validation_status(None)
        assert s["claim_advancement"] == "none"

    def test_custom_timestamp(self) -> None:
        ts = "2026-06-01T12:00:00+00:00"
        s = record_solver_validation_status(None, timestamp=ts)
        assert s["recorded_at"] == ts

    def test_affected_artifacts_always_empty(self) -> None:
        s = record_solver_validation_status(None)
        assert s["affected_artifacts"] == []

    def test_valid_status(self) -> None:
        assert validate_revalidation_status(record_solver_validation_status(None)) == []


# ── build_revalidation_response ──────────────────────────────────────────────

class TestBuildRevalidationResponse:
    def test_none_input_defaults(self) -> None:
        r = build_revalidation_response(None)
        assert r["requires_revalidation"] is False
        assert r["current_geometry_revision"] == 0
        assert r["reason"] is None
        assert r["claim_advancement"] == "none"

    def test_none_input_all_nullable_fields_none(self) -> None:
        r = build_revalidation_response(None)
        for key in ("reason", "triggering_tool", "affected_domains", "recorded_at",
                    "last_validated_geometry_revision", "stale_since_geometry_revision",
                    "validated_by_run_id"):
            assert r[key] is None, f"{key!r} should be None"

    def test_stale_status_propagated(self) -> None:
        s = record_geometry_edit_status(None)
        r = build_revalidation_response(s)
        assert r["requires_revalidation"] is True
        assert r["current_geometry_revision"] == 1

    def test_validated_status_propagated(self) -> None:
        prev = record_geometry_edit_status({"current_geometry_revision": 2})
        s = record_solver_validation_status(prev)
        r = build_revalidation_response(s)
        assert r["requires_revalidation"] is False
        assert r["last_validated_geometry_revision"] == 3

    def test_claim_advancement_always_none(self) -> None:
        r = build_revalidation_response({"requires_revalidation": True, "claim_advancement": "advanced"})
        assert r["claim_advancement"] == "none"

    def test_all_expected_keys_present(self) -> None:
        r = build_revalidation_response(None)
        for key in (
            "requires_revalidation", "reason", "triggering_tool",
            "affected_domains", "recorded_at", "current_geometry_revision",
            "last_validated_geometry_revision", "stale_since_geometry_revision",
            "validated_by_run_id", "claim_advancement",
        ):
            assert key in r, f"missing key: {key!r}"

    def test_stale_since_geometry_revision_propagated(self) -> None:
        s = record_geometry_edit_status({"current_geometry_revision": 3})
        r = build_revalidation_response(s)
        assert r["stale_since_geometry_revision"] == 4


# ── validate_revalidation_status ─────────────────────────────────────────────

class TestValidateRevalidationStatus:
    def test_valid_edit_status_no_issues(self) -> None:
        s = record_geometry_edit_status(None)
        assert validate_revalidation_status(s) == []

    def test_valid_solver_status_no_issues(self) -> None:
        s = record_solver_validation_status(None)
        assert validate_revalidation_status(s) == []

    def test_missing_schema_version_reported(self) -> None:
        bad = {k: v for k, v in record_geometry_edit_status(None).items() if k != "schema_version"}
        issues = validate_revalidation_status(bad)
        assert any("schema_version" in i for i in issues)

    def test_missing_requires_revalidation_reported(self) -> None:
        bad = {k: v for k, v in record_geometry_edit_status(None).items() if k != "requires_revalidation"}
        issues = validate_revalidation_status(bad)
        assert any("requires_revalidation" in i for i in issues)

    def test_missing_current_geometry_revision_reported(self) -> None:
        bad = {k: v for k, v in record_geometry_edit_status(None).items() if k != "current_geometry_revision"}
        issues = validate_revalidation_status(bad)
        assert any("current_geometry_revision" in i for i in issues)

    def test_wrong_claim_advancement_reported(self) -> None:
        bad = {**record_geometry_edit_status(None), "claim_advancement": "accepted"}
        issues = validate_revalidation_status(bad)
        assert any("claim_advancement" in i for i in issues)

    def test_empty_dict_reports_multiple_issues(self) -> None:
        issues = validate_revalidation_status({})
        assert len(issues) >= 3


# ── vocabulary constants ─────────────────────────────────────────────────────

class TestVocabularyConstants:
    def test_revalidation_status_path(self) -> None:
        assert REVALIDATION_STATUS_PATH == "state/revalidation_status.json"
