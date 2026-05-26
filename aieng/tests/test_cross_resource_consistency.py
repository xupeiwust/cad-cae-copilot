"""Tests for Phase 15C: Cross-resource consistency validator."""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from aieng.package import create_package
from aieng.task.task_spec_writer import write_task_spec_package
from aieng.task.external_tool_requirements_writer import write_external_tool_requirements_package
from aieng.results.evidence_writer import write_evidence_scaffold_package, record_evidence_package
from aieng.validation.status_writer import update_validation_status_package
from aieng.validate import validate_package, Level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "test.aieng"
    create_package("test_model", pkg)
    return pkg


def _make_full_package(tmp_path: Path) -> Path:
    pkg = _make_package(tmp_path)
    write_task_spec_package(pkg, "Reduce mass by 15% keeping mounting holes.", task_id="task_001")
    write_external_tool_requirements_package(pkg, handoff_id="handoff_001")
    write_evidence_scaffold_package(pkg)
    update_validation_status_package(pkg)
    return pkg


def _messages(pkg: Path) -> list:
    return list(validate_package(pkg).messages)


def _fails(pkg: Path) -> list[str]:
    return [m.text for m in _messages(pkg) if m.level is Level.FAIL]


def _warns(pkg: Path) -> list[str]:
    return [m.text for m in _messages(pkg) if m.level is Level.WARN]


def _rewrite_member(pkg: Path, member: str, raw: bytes) -> None:
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(pkg) as zf:
        for name in zf.namelist():
            members[name] = zf.read(name)
    members[member] = raw
    tmp = str(pkg) + ".tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    os.replace(tmp, pkg)


def _inject_evidence_item(pkg: Path, item: dict) -> None:
    """Append an evidence item directly into evidence_index.json, bypassing writer guards."""
    with zipfile.ZipFile(pkg) as zf:
        data = json.loads(zf.read("results/evidence_index.json"))
    data["evidence_items"].append(item)
    _rewrite_member(pkg, "results/evidence_index.json", json.dumps(data, indent=2).encode("utf-8"))



def _record_solver_evidence(pkg: Path, evidence_id: str, claim_support: list[str],
                             artifact_path: str = "results/out.vtk") -> None:
    record_evidence_package(
        pkg,
        evidence_id=evidence_id,
        evidence_type="solver_result",
        producer_kind="external_solver",
        producer_tool="freecad",
        artifact_kind="result_file",
        artifact_path=artifact_path,
        claim_support=claim_support,
    )


# ---------------------------------------------------------------------------
# Rule 4: forbidden_core_actions + aieng_core solver evidence → FAIL
# ---------------------------------------------------------------------------

def test_aieng_core_solver_evidence_fails(tmp_path):
    pkg = _make_full_package(tmp_path)
    _inject_evidence_item(pkg, {
        "evidence_id": "ev_bad_solver",
        "evidence_type": "solver_result",
        "producer": {"kind": "aieng_core"},
        "artifact": {"kind": "result_file", "path": "results/bad.vtk"},
        "claim_support": [],
        "verification": {"status": "available"},
    })
    fails = _fails(pkg)
    assert any("aieng_core" in f and "solver_result" in f and "run_solver" in f for f in fails)


def test_external_solver_evidence_no_rule4_fail(tmp_path):
    pkg = _make_full_package(tmp_path)
    _record_solver_evidence(pkg, "ev_ext_solver", ["claim_solver_result_001"])
    fails = _fails(pkg)
    assert not any("aieng_core" in f and "solver_result" in f and "run_solver" in f for f in fails)


# ---------------------------------------------------------------------------
# Rule 6: in-package artifact paths missing from ZIP → WARN
# ---------------------------------------------------------------------------

def test_missing_in_package_artifact_warns(tmp_path):
    pkg = _make_full_package(tmp_path)
    _inject_evidence_item(pkg, {
        "evidence_id": "ev_missing",
        "evidence_type": "solver_result",
        "producer": {"kind": "external_solver", "tool_id": "freecad"},
        "artifact": {"kind": "result_file", "path": "results/nonexistent_output.vtk"},
        "claim_support": [],
        "verification": {"status": "available"},
    })
    warns = _warns(pkg)
    assert any("nonexistent_output.vtk" in w and "not present in the package" in w for w in warns)


def test_present_in_package_artifact_no_warn(tmp_path):
    pkg = _make_full_package(tmp_path)
    _inject_evidence_item(pkg, {
        "evidence_id": "ev_task_spec",
        "evidence_type": "task_spec",
        "producer": {"kind": "aieng_core"},
        "artifact": {"kind": "yaml", "path": "task/task_spec.yaml"},
        "claim_support": [],
        "verification": {"status": "available"},
    })
    warns = _warns(pkg)
    assert not any("task/task_spec.yaml" in w and "not present in the package" in w for w in warns)


def test_external_url_artifact_no_warn(tmp_path):
    pkg = _make_full_package(tmp_path)
    _inject_evidence_item(pkg, {
        "evidence_id": "ev_external",
        "evidence_type": "solver_result",
        "producer": {"kind": "external_solver", "tool_id": "freecad"},
        "artifact": {"kind": "result_file", "path": "https://storage.example.com/results/output.vtk"},
        "claim_support": [],
        "verification": {"status": "available"},
    })
    warns = _warns(pkg)
    assert not any("storage.example.com" in w and "not present in the package" in w for w in warns)


# ---------------------------------------------------------------------------
# No-data scenario
# ---------------------------------------------------------------------------

def test_cross_resource_silent_with_no_ledgers(tmp_path):
    pkg = _make_package(tmp_path)
    msgs = _messages(pkg)
    assert not any(m.level is Level.FAIL and "cross-resource" in m.text for m in msgs)


# ---------------------------------------------------------------------------
# Boundary: validate.py must not import execution modules
# ---------------------------------------------------------------------------

def test_no_execution_imports_in_validate_source():
    source = Path(__file__).parent.parent / "src" / "aieng" / "validate.py"
    text = source.read_text()
    forbidden = ["subprocess", "FreeCAD", "gmsh", "calculix"]
    for kw in forbidden:
        assert kw not in text, f"validate.py must not reference '{kw}'"
