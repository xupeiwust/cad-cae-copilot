"""Tests for aieng.package_consistency."""

from __future__ import annotations

import json
from typing import Any

import pytest

from aieng.package_consistency import (
    check_claim_proposals,
    is_internal_package_path,
    rollup_check_status,
    run_package_consistency_checks,
)


# ── shared fixtures ──────────────────────────────────────────────────────────

_FRD_PATH = "simulation/runs/run_001/outputs/result.frd"
_DISP_PATH = "results/fields/displacement.summary.json"
_EI_PATH = "results/evidence_index.json"

_BASE_PATHS = [
    "manifest.json",
    _EI_PATH,
    _FRD_PATH,
    _DISP_PATH,
    "results/computed_metrics.json",
]

_VALID_EI_RAW = json.dumps({
    "entries": [
        {"id": "e1", "path": _FRD_PATH, "exists": True},
        {"id": "e2", "path": _DISP_PATH, "exists": True},
    ]
}).encode()

_FRESH_RS: dict[str, Any] = {
    "requires_revalidation": False,
    "current_geometry_revision": 2,
    "last_validated_geometry_revision": 2,
}

_STALE_RS: dict[str, Any] = {
    "requires_revalidation": True,
    "current_geometry_revision": 3,
    "last_validated_geometry_revision": 2,
}


# ── is_internal_package_path ─────────────────────────────────────────────────

class TestIsInternalPackagePath:
    def test_empty_string_false(self) -> None:
        assert is_internal_package_path("") is False

    def test_absolute_unix_false(self) -> None:
        assert is_internal_package_path("/etc/passwd") is False

    def test_windows_drive_false(self) -> None:
        assert is_internal_package_path("C:\\Users\\file.txt") is False

    def test_windows_drive_forward_slash_false(self) -> None:
        assert is_internal_package_path("C:/Users/file.txt") is False

    def test_backslash_in_path_false(self) -> None:
        assert is_internal_package_path("results\\file.json") is False

    def test_valid_relative_true(self) -> None:
        assert is_internal_package_path("results/evidence_index.json") is True

    def test_nested_relative_true(self) -> None:
        assert is_internal_package_path("simulation/runs/run_001/outputs/result.frd") is True


# ── rollup_check_status ──────────────────────────────────────────────────────

class TestRollupCheckStatus:
    def test_empty_returns_ok(self) -> None:
        assert rollup_check_status([]) == "ok"

    def test_all_ok(self) -> None:
        checks = [{"status": "ok"}, {"status": "ok"}]
        assert rollup_check_status(checks) == "ok"

    def test_one_warning(self) -> None:
        checks = [{"status": "ok"}, {"status": "warning"}]
        assert rollup_check_status(checks) == "warning"

    def test_one_error(self) -> None:
        checks = [{"status": "ok"}, {"status": "error"}]
        assert rollup_check_status(checks) == "error"

    def test_error_beats_warning(self) -> None:
        checks = [{"status": "warning"}, {"status": "error"}, {"status": "ok"}]
        assert rollup_check_status(checks) == "error"


# ── check_claim_proposals ────────────────────────────────────────────────────

class TestCheckClaimProposals:
    def test_no_proposals_ok(self) -> None:
        result = check_claim_proposals(set(_BASE_PATHS), [], None)
        assert result["status"] == "ok"
        assert result["id"] == "claim_proposals"

    def test_valid_proposal_ok(self) -> None:
        raw = json.dumps({
            "status": "proposed",
            "claim_advancement": "none",
            "supporting_evidence": [_FRD_PATH],
        }).encode()
        result = check_claim_proposals(set(_BASE_PATHS), [("claims/proposals/p1.json", raw)], None)
        assert result["status"] == "ok"

    def test_draft_status_ok(self) -> None:
        raw = json.dumps({
            "status": "draft",
            "claim_advancement": "none",
            "supporting_evidence": [],
        }).encode()
        result = check_claim_proposals(set(_BASE_PATHS), [("claims/proposals/p1.json", raw)], None)
        assert result["status"] == "ok"

    def test_invalid_json_warning(self) -> None:
        result = check_claim_proposals(
            set(_BASE_PATHS), [("claims/proposals/bad.json", b"not-json")], None
        )
        assert result["status"] == "warning"

    def test_unexpected_status_warning(self) -> None:
        raw = json.dumps({
            "status": "accepted",
            "claim_advancement": "none",
            "supporting_evidence": [],
        }).encode()
        result = check_claim_proposals(set(_BASE_PATHS), [("claims/proposals/p.json", raw)], None)
        assert result["status"] == "warning"
        assert any("unexpected status" in issue for issue in result["details"]["issues"])

    def test_non_none_claim_advancement_warning(self) -> None:
        raw = json.dumps({
            "status": "proposed",
            "claim_advancement": "accepted",
            "supporting_evidence": [],
        }).encode()
        result = check_claim_proposals(set(_BASE_PATHS), [("claims/proposals/p.json", raw)], None)
        assert result["status"] == "warning"

    def test_missing_evidence_warning(self) -> None:
        raw = json.dumps({
            "status": "proposed",
            "claim_advancement": "none",
            "supporting_evidence": ["results/ghost.json"],
        }).encode()
        result = check_claim_proposals(set(_BASE_PATHS), [("claims/proposals/p.json", raw)], None)
        assert result["status"] == "warning"

    def test_evidence_in_index_counts_as_present(self) -> None:
        raw = json.dumps({
            "status": "proposed",
            "claim_advancement": "none",
            "supporting_evidence": [_FRD_PATH],
        }).encode()
        # FRD is not in pkg_names but IS in evidence_raw index
        result = check_claim_proposals(
            {"manifest.json"},
            [("claims/proposals/p.json", raw)],
            _VALID_EI_RAW,
        )
        assert result["status"] == "ok"


# ── run_package_consistency_checks ───────────────────────────────────────────

class TestRunPackageConsistencyChecks:
    def test_returns_list_of_dicts(self) -> None:
        checks = run_package_consistency_checks(package_paths=_BASE_PATHS)
        assert isinstance(checks, list)
        for c in checks:
            assert "id" in c
            assert "status" in c
            assert "message" in c

    def test_absent_evidence_index_warning(self) -> None:
        checks = run_package_consistency_checks(package_paths=["manifest.json"])
        check_a = next(c for c in checks if c["id"] == "evidence_paths_exist")
        assert check_a["status"] == "warning"

    def test_valid_evidence_index_ok(self) -> None:
        checks = run_package_consistency_checks(
            package_paths=_BASE_PATHS,
            evidence_raw=_VALID_EI_RAW,
        )
        check_a = next(c for c in checks if c["id"] == "evidence_paths_exist")
        assert check_a["status"] == "ok"

    def test_invalid_evidence_json_error(self) -> None:
        checks = run_package_consistency_checks(
            package_paths=_BASE_PATHS,
            evidence_raw=b"not-json",
        )
        check_a = next(c for c in checks if c["id"] == "evidence_paths_exist")
        assert check_a["status"] == "error"

    def test_stale_revalidation_warning(self) -> None:
        checks = run_package_consistency_checks(
            package_paths=_BASE_PATHS,
            revalidation_status=_STALE_RS,
        )
        check_d = next(c for c in checks if c["id"] == "revalidation_status_consistency")
        assert check_d["status"] == "warning"

    def test_fresh_revalidation_ok(self) -> None:
        checks = run_package_consistency_checks(
            package_paths=_BASE_PATHS,
            revalidation_status=_FRESH_RS,
        )
        check_d = next(c for c in checks if c["id"] == "revalidation_status_consistency")
        assert check_d["status"] == "ok"

    def test_claim_map_present_warning(self) -> None:
        checks = run_package_consistency_checks(
            package_paths=_BASE_PATHS + ["ai/claim_map.json"],
        )
        check_e = next(c for c in checks if c["id"] == "claim_map_absent")
        assert check_e["status"] == "warning"

    def test_no_audit_log_ok(self) -> None:
        checks = run_package_consistency_checks(package_paths=_BASE_PATHS)
        check_b = next(c for c in checks if c["id"] == "audit_artifact_references")
        assert check_b["status"] == "ok"

    def test_field_summary_missing_source_warning(self) -> None:
        disp_raw = json.dumps({
            "source": {"frd_path": "simulation/runs/run_001/outputs/result.frd"}
        }).encode()
        checks = run_package_consistency_checks(
            package_paths=["manifest.json"],  # FRD not present
            displacement_summary_raw=disp_raw,
        )
        check_c = next(c for c in checks if c["id"] == "field_summary_source_displacement")
        assert check_c["status"] == "warning"

    def test_package_paths_as_generator(self) -> None:
        checks = run_package_consistency_checks(
            package_paths=(p for p in _BASE_PATHS),
        )
        assert isinstance(checks, list)
