"""Tests for the Milestone-1 acceptance driver.

These tests verify the script behaves correctly in both:
- FreeCAD-absent environments (controlled skip/unsupported)
- FreeCAD-present environments (full execution)

Key semantic assertions:
- checks 8/9 must not pass with empty evidence/trace
- check 5 must execute (not just parse) when FreeCAD is available
- all file-based checks read from the temp run directory, not FIXTURE_PACKAGE
- check 11 validation target is the run directory
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import run_milestone1_acceptance as m1
from run_milestone1_acceptance import (
    FIXTURE_PACKAGE,
    Milestone1Report,
    run_acceptance,
    _freecad_available,
)


class TestMilestone1ReportStructure:
    def test_run_produces_structured_output(self) -> None:
        report = run_acceptance()
        data = report.to_dict()
        assert "status" in data
        assert data["status"] in ("pass", "fail", "partial")
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) == 11
        assert isinstance(data["artifacts_written"], list)
        assert isinstance(data["evidence_ids"], list)
        assert isinstance(data["trace_ids"], list)
        assert isinstance(data["claims_advanced"], bool)
        assert isinstance(data["warnings"], list)
        assert isinstance(data["errors"], list)

    def test_all_checks_have_required_fields(self) -> None:
        report = run_acceptance()
        for check in report.checks:
            d = check.to_dict()
            assert "id" in d
            assert "name" in d
            assert "status" in d
            assert d["status"] in ("pass", "fail", "skipped", "unsupported", "pending")
            assert "details" in d

    def test_claims_advanced_never_true(self) -> None:
        report = run_acceptance()
        assert report.claims_advanced is False
        data = report.to_dict()
        assert data["claims_advanced"] is False

    def test_check_10_verifies_no_auto_advance(self) -> None:
        report = run_acceptance()
        check10 = next((c for c in report.checks if c.id == "10"), None)
        assert check10 is not None
        assert check10.status in ("pass", "unsupported")

    @pytest.mark.skipif(_freecad_available(), reason="FreeCAD is available; this test validates absent-FreeCAD behavior")
    def test_status_is_not_fail_when_freecad_missing(self) -> None:
        report = run_acceptance()
        data = report.to_dict()
        assert data["status"] in ("pass", "partial")

    @pytest.mark.skipif(_freecad_available(), reason="FreeCAD is available; this test validates absent-FreeCAD behavior")
    def test_freecad_checks_are_skipped_when_unavailable(self) -> None:
        report = run_acceptance()
        freecad_dependent = {"2", "3", "5", "6", "7"}
        for check in report.checks:
            if check.id in freecad_dependent:
                assert check.status in ("skipped", "pass"), (
                    f"Check {check.id} ({check.name}) should be skipped or pass, "
                    f"got {check.status}"
                )

    def test_json_output_is_valid(self) -> None:
        report = run_acceptance()
        data = report.to_dict()
        dumped = json.dumps(data)
        loaded = json.loads(dumped)
        assert loaded["status"] == data["status"]
        assert len(loaded["checks"]) == 11


class TestMilestone1SemanticConstraints:
    """Semantic assertions that caught the original defects."""

    def test_check_8_pass_implies_evidence_non_empty(self) -> None:
        """If check 8 is pass, evidence_ids must be non-empty."""
        report = run_acceptance()
        check8 = next((c for c in report.checks if c.id == "8"), None)
        assert check8 is not None
        if check8.status == "pass":
            assert len(report.evidence_ids) > 0, (
                "check 8 is pass but evidence_ids is empty"
            )
        else:
            assert check8.status in ("unsupported", "fail", "skipped"), (
                f"check 8 should not be pass with empty evidence; got {check8.status}"
            )

    def test_check_9_pass_implies_trace_non_empty(self) -> None:
        """If check 9 is pass, trace_ids must be non-empty."""
        report = run_acceptance()
        check9 = next((c for c in report.checks if c.id == "9"), None)
        assert check9 is not None
        if check9.status == "pass":
            assert len(report.trace_ids) > 0, (
                "check 9 is pass but trace_ids is empty"
            )
        else:
            assert check9.status in ("unsupported", "fail", "skipped"), (
                f"check 9 should not be pass with empty trace; got {check9.status}"
            )

    def test_check_5_is_not_pure_parse(self) -> None:
        """check 5 must either execute or be skipped; pure parse without execution is not pass."""
        report = run_acceptance()
        check5 = next((c for c in report.checks if c.id == "5"), None)
        assert check5 is not None
        if check5.status == "pass":
            details = check5.details
            assert isinstance(details, dict)
            assert "patch_status" in details or "actual_value" in details, (
                "check 5 passed but lacks execution evidence in details"
            )
        else:
            assert check5.status in ("skipped", "fail", "unsupported"), (
                f"check 5 has unexpected status: {check5.status}"
            )

    def test_errors_list_is_populated_on_failures(self) -> None:
        """If any check fails, errors list must contain human-readable messages."""
        report = run_acceptance()
        failed_checks = [c for c in report.checks if c.status == "fail"]
        if failed_checks:
            assert len(report.errors) > 0, (
                "Checks failed but errors list is empty"
            )
            for err in report.errors:
                assert isinstance(err, str) and len(err) > 0


class TestRunDirectoryIsolation:
    """Verify file-based checks operate on the temporary run directory."""

    def test_checks_8_9_10_11_receive_run_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Wrap file-based checks to record the pkg_path they receive.
        Assert none of them receive the static fixture path."""
        captured: list[tuple[str, str]] = []

        orig_8 = m1._check_8_evidence
        def wrap_8(report: Milestone1Report, pkg_path: Path, baseline_count: int = 0, **kwargs: Any) -> None:
            captured.append(("8", str(pkg_path)))
            return orig_8(report, pkg_path, baseline_count, **kwargs)
        monkeypatch.setattr(m1, "_check_8_evidence", wrap_8)

        orig_9 = m1._check_9_trace
        def wrap_9(report: Milestone1Report, pkg_path: Path, baseline_count: int = 0, **kwargs: Any) -> None:
            captured.append(("9", str(pkg_path)))
            return orig_9(report, pkg_path, baseline_count, **kwargs)
        monkeypatch.setattr(m1, "_check_9_trace", wrap_9)

        orig_10 = m1._check_10_no_auto_claims
        def wrap_10(report: Milestone1Report, pkg_path: Path, **kwargs: Any) -> None:
            captured.append(("10", str(pkg_path)))
            return orig_10(report, pkg_path, **kwargs)
        monkeypatch.setattr(m1, "_check_10_no_auto_claims", wrap_10)

        orig_11 = m1._check_11_aieng_validate
        def wrap_11(report: Milestone1Report, pkg_path: Path, **kwargs: Any) -> None:
            captured.append(("11", str(pkg_path)))
            return orig_11(report, pkg_path, **kwargs)
        monkeypatch.setattr(m1, "_check_11_aieng_validate", wrap_11)

        report = m1.run_acceptance()

        assert len(captured) == 4, f"Expected 4 wrapped calls, got {len(captured)}: {captured}"
        for check_id, path in captured:
            assert str(FIXTURE_PACKAGE) not in path, (
                f"check {check_id} received fixture path: {path}"
            )
            # The path must be inside a temporary directory and end with /package
            path_obj = Path(path)
            assert path_obj.name == "package" or path_obj.parts[-1] == "package", (
                f"check {check_id} did not receive a run-directory package path: {path}"
            )
            assert "tmp" in str(path_obj).lower() or "temp" in str(path_obj).lower(), (
                f"check {check_id} path does not look like a temp directory: {path}"
            )

    def test_check_11_subprocess_targets_run_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Monkeypatch shutil.which and subprocess.run to intercept the validate call.
        Assert the target path is the run directory, not FIXTURE_PACKAGE."""
        import shutil

        captured_cmds: list[list[str]] = []

        orig_which = shutil.which
        def fake_which(cmd: str) -> str | None:
            if cmd == "aieng":
                return "/fake/aieng"
            return orig_which(cmd)
        monkeypatch.setattr(shutil, "which", fake_which)

        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            captured_cmds.append(list(cmd))
            class MockResult:
                returncode = 0
                stdout = "mock ok"
                stderr = ""
            return MockResult()
        monkeypatch.setattr(subprocess, "run", fake_run)

        report = m1.run_acceptance()

        validate_calls = [c for c in captured_cmds if len(c) >= 3 and c[1] == "validate"]
        assert len(validate_calls) == 1, f"Expected 1 validate call, got {validate_calls}"
        target_path = validate_calls[0][2]
        assert str(FIXTURE_PACKAGE) not in target_path, (
            f"check 11 validated fixture path: {target_path}"
        )
        assert "package" in target_path, (
            f"check 11 target does not contain 'package': {target_path}"
        )


class TestMilestone1ReportModel:
    def test_report_update_status_pass(self) -> None:
        r = Milestone1Report()
        r.checks = []
        r._update_status()
        assert r.status == "pass"

    def test_report_update_status_fail(self) -> None:
        r = Milestone1Report()
        c = r.add_check("x", "test")
        c.status = "fail"
        r._update_status()
        assert r.status == "fail"

    def test_report_update_status_partial(self) -> None:
        r = Milestone1Report()
        c1 = r.add_check("a", "pass")
        c1.status = "pass"
        c2 = r.add_check("b", "skip")
        c2.status = "skipped"
        r._update_status()
        assert r.status == "partial"
