"""Backend package-write tests for optimization artifacts."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
AIENG_SRC = WORKSPACE_ROOT / "aieng" / "src"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
for path in (AIENG_SRC, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.optimization_artifacts import save_optimization_artifact


def _problem() -> dict:
    return {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "source_001",
        "variables": [
            {
                "id": "wall_t",
                "path": "parts/0/params/WALL_THICKNESS",
                "type": "continuous",
                "current_value": 3.0,
                "min_value": 2.0,
                "max_value": 8.0,
                "unit": "mm",
                "safe_to_modify": True,
            }
        ],
        "objective": {"sense": "minimize", "metric": "volume"},
        "constraints": [],
    }


def _variables() -> dict:
    return {
        "format": "aieng.optimization_variables",
        "schema_version": "0.2",
        "study_id": "opt_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": "source_001",
        "variables": [
            {
                "id": "wall_t",
                "path": "parts/0/params/WALL_THICKNESS",
                "type": "continuous",
                "featureId": "feat_wall",
                "parameterName": "thickness",
                "cad_parameter_name": "WALL_THICKNESS",
                "binding_status": "bound",
                "current_value": 3.0,
                "min_value": 2.0,
                "max_value": 8.0,
                "allowed_values": None,
                "unit": "mm",
                "scope": "local",
                "safe_to_modify": True,
                "candidate_ids": [],
            }
        ],
        "candidate_ids": [],
        "provenance": {
            "created_at": "2026-06-10T00:00:00Z",
            "created_by": "test",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }


def _make_package(path: Path) -> bytes:
    revalidation = {
        "schema_version": "0.2",
        "current_geometry_revision": 3,
        "requires_revalidation": False,
        "claim_advancement": "none",
    }
    revalidation_bytes = json.dumps(revalidation).encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", "{}")
        package.writestr("analysis/design_study_problem.json", json.dumps(_problem()))
        package.writestr("state/revalidation_status.json", revalidation_bytes)
    return revalidation_bytes


def test_save_optimization_artifact_writes_package_and_audit_without_revalidation_change(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "study.aieng"
    original_revalidation = _make_package(package_path)

    result = save_optimization_artifact(
        package_path,
        "variables",
        _variables(),
        tool_name="opt.define_variables",
    )

    assert result["artifact_path"] == "analysis/optimization_variables.json"
    assert result["baseline_modified"] is False
    assert result["claim_advancement"] == "none"
    with zipfile.ZipFile(package_path) as package:
        assert json.loads(package.read(result["artifact_path"])) == _variables()
        assert package.read("state/revalidation_status.json") == original_revalidation
        events = [
            json.loads(line)
            for line in package.read("audit/events.jsonl").decode().splitlines()
            if line.strip()
        ]
    assert events[-1]["event_type"] == "optimization_artifact_written"
    assert events[-1]["tool"] == "opt.define_variables"
    assert events[-1]["claim_advancement"] == "none"
    assert events[-1]["state_changes"]["baseline_modified"] is False


def test_save_rejects_schema_invalid_document_before_write(tmp_path: Path) -> None:
    package_path = tmp_path / "study.aieng"
    _make_package(package_path)
    document = _variables()
    document["claim_policy"]["baseline_unchanged"] = False

    with pytest.raises(ValueError, match="baseline_unchanged"):
        save_optimization_artifact(
            package_path,
            "variables",
            document,
            tool_name="opt.define_variables",
        )

    with zipfile.ZipFile(package_path) as package:
        assert "analysis/optimization_variables.json" not in package.namelist()
        assert "audit/events.jsonl" not in package.namelist()


def test_save_rejects_document_that_forks_design_study_problem(tmp_path: Path) -> None:
    package_path = tmp_path / "study.aieng"
    _make_package(package_path)
    document = _variables()
    document["variables"][0]["max_value"] = 80.0

    with pytest.raises(ValueError, match="max_value does not match design study"):
        save_optimization_artifact(
            package_path,
            "variables",
            document,
            tool_name="opt.define_variables",
        )
