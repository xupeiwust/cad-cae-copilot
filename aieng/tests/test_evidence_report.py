from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from aieng.ai.summary_writer import AI_SUMMARY_PATH, summarize_package
from aieng.cli import main
from aieng.mcp.server import tool_get_evidence_report
from aieng.package import create_package
from aieng.results.evidence_writer import write_evidence_scaffold_package
from aieng.validate import Level, validate_package
from aieng.validation.evidence_report_writer import EVIDENCE_REPORT_PATH, write_evidence_report_package
from aieng.validation.status_writer import update_validation_status_package


def _read_json(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _read_text(pkg: Path, member: str) -> str:
    with zipfile.ZipFile(pkg) as zf:
        return zf.read(member).decode("utf-8")


def _names(pkg: Path) -> set[str]:
    with zipfile.ZipFile(pkg) as zf:
        return set(zf.namelist())


def _pkg_with_ledgers(tmp_path: Path) -> Path:
    pkg = tmp_path / "model.aieng"
    create_package("model_001", pkg)
    update_validation_status_package(pkg)
    write_evidence_scaffold_package(pkg)
    return pkg


def _rewrite_member(pkg: Path, member: str, data: dict) -> None:
    with zipfile.ZipFile(pkg, "r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != member
        ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        tmp_pkg = Path(fh.name)

    try:
        with zipfile.ZipFile(tmp_pkg, "w") as zf:
            for info, payload in members:
                zf.writestr(info, payload)
            zf.writestr(member, json.dumps(data, indent=2).encode("utf-8"))
        shutil.move(str(tmp_pkg), str(pkg))
    finally:
        if tmp_pkg.exists():
            tmp_pkg.unlink()


def test_write_evidence_report_creates_resource_and_manifest_entry(tmp_path):
    pkg = _pkg_with_ledgers(tmp_path)
    write_evidence_report_package(pkg)

    assert EVIDENCE_REPORT_PATH in _names(pkg)
    manifest = _read_json(pkg, "manifest.json")
    assert manifest["resources"]["validation"]["evidence_report"] == EVIDENCE_REPORT_PATH


def test_write_evidence_report_requires_source_ledgers(tmp_path):
    pkg = tmp_path / "model.aieng"
    create_package("model_001", pkg)
    try:
        write_evidence_report_package(pkg)
    except FileNotFoundError as exc:
        assert "evidence report requires" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_cli_write_evidence_report(tmp_path, capsys):
    pkg = _pkg_with_ledgers(tmp_path)
    assert main(["write-evidence-report", str(pkg)]) == 0
    out = capsys.readouterr().out
    assert "PASS wrote evidence report" in out
    assert EVIDENCE_REPORT_PATH in _names(pkg)


def test_validate_passes_valid_evidence_report(tmp_path):
    pkg = _pkg_with_ledgers(tmp_path)
    write_evidence_report_package(pkg)
    report = validate_package(pkg)
    failures = [m for m in report.messages if m.level is Level.FAIL and "evidence_report" in m.text]
    assert not failures


def test_validate_evidence_report_without_claim_map(tmp_path):
    """Evidence report validates cleanly when claim_map is absent (alpha policy)."""
    pkg = _pkg_with_ledgers(tmp_path)
    write_evidence_report_package(pkg)
    report = validate_package(pkg)
    failures = [m for m in report.messages if m.level is Level.FAIL and "evidence_report" in m.text]
    assert not failures


def test_summary_mentions_evidence_report_when_present(tmp_path):
    pkg = _pkg_with_ledgers(tmp_path)
    write_evidence_report_package(pkg)
    summarize_package(pkg)

    summary = _read_text(pkg, AI_SUMMARY_PATH)
    assert "Consolidated evidence report" in summary
    assert "claim_status_counts" in summary


def test_summary_mentions_absent_evidence_report(tmp_path):
    pkg = _pkg_with_ledgers(tmp_path)
    summarize_package(pkg)
    summary = _read_text(pkg, AI_SUMMARY_PATH)
    assert "validation/evidence_report.json` is absent" in summary


def test_mcp_get_evidence_report_returns_data(tmp_path):
    pkg = _pkg_with_ledgers(tmp_path)
    write_evidence_report_package(pkg)
    result = tool_get_evidence_report(pkg)
    assert result["report_id"] == "evidence_report_001"
    assert "claim_status_counts" in result


def test_mcp_get_evidence_report_returns_not_found(tmp_path):
    pkg = _pkg_with_ledgers(tmp_path)
    result = tool_get_evidence_report(pkg)
    assert result["status"] == "not_found"
    assert result["member"] == EVIDENCE_REPORT_PATH
