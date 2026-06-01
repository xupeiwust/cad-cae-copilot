"""Subprocess test for Milestone-1 acceptance driver --dry-run mode.

Runs the acceptance driver as a real subprocess, parses its JSON output,
and asserts all 11 checks pass with correct invariants.

Rules:
- No mocking at test level — the script handles FreeCAD stubbing internally.
- Real file I/O is exercised against the fixture package.
- Evidence and trace entries must be produced by patch execution.
- Claims must not be auto-advanced.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "run_milestone1_acceptance.py"


@pytest.fixture
def dryrun_report() -> dict:
    """Run the acceptance driver in dry-run mode and return parsed JSON."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--json"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    # Ensure the script exits cleanly
    assert result.returncode == 0, (
        f"Acceptance driver exited {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    data = json.loads(result.stdout)
    return data


def test_dryrun_overall_status_pass(dryrun_report: dict) -> None:
    """Overall status must be 'pass' when all 11 checks pass."""
    assert dryrun_report["status"] == "pass"


def test_dryrun_all_11_checks_pass(dryrun_report: dict) -> None:
    """Every one of the 11 acceptance checks must report pass."""
    checks = dryrun_report["checks"]
    assert len(checks) == 11, f"Expected 11 checks, got {len(checks)}"
    for check in checks:
        assert check["status"] == "pass", (
            f"Check {check['id']} ({check['name']}) did not pass: {check['status']}"
        )


def test_dryrun_evidence_ids_non_empty(dryrun_report: dict) -> None:
    """Check 8 must produce real evidence entries (delta > 0 from baseline)."""
    assert dryrun_report["evidence_ids"], "evidence_ids must be non-empty"


def test_dryrun_trace_ids_non_empty(dryrun_report: dict) -> None:
    """Check 9 must produce real trace entries (delta > 0 from baseline)."""
    assert dryrun_report["trace_ids"], "trace_ids must be non-empty"


def test_dryrun_claims_not_advanced(dryrun_report: dict) -> None:
    """Check 10 invariant: no automatic claim advancement."""
    assert dryrun_report["claims_advanced"] is False


def test_dryrun_artifacts_written(dryrun_report: dict) -> None:
    """Check 7 must produce artifact paths."""
    artifacts = dryrun_report["artifacts_written"]
    assert any(".step" in a for a in artifacts), "Expected a .step artifact"
    assert any(".FCStd" in a for a in artifacts), "Expected a .FCStd artifact"


def test_dryrun_no_errors(dryrun_report: dict) -> None:
    """A clean dry-run must produce no errors."""
    assert dryrun_report["errors"] == []


def test_dryrun_check_details_contain_dry_run_flag(dryrun_report: dict) -> None:
    """FreeCAD-dependent checks should document that they ran in dry-run mode."""
    freecad_checks = {"2", "3", "5", "6", "7"}
    for check in dryrun_report["checks"]:
        if check["id"] in freecad_checks:
            details = check.get("details", {})
            assert details.get("dry_run") is True, (
                f"Check {check['id']} should have dry_run=True in details"
            )
