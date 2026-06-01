"""Tests for the v1.0.0 unified end-to-end demo.

These tests verify the complete workflow in mock/surrogate mode:
- package copy -> reference map -> patch -> CAD-to-CAE -> claim update -> audit

All tests run without FreeCAD.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _copy_parametric_bracket(tmp_path: Path) -> Path:
    fixture = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
    assert fixture.exists(), f"Fixture not found: {fixture}"
    dst = tmp_path / "package"
    shutil.copytree(fixture, dst)
    return dst


class TestV1EndToEndDemoScript:
    def test_demo_script_runs_successfully(self, tmp_path: Path) -> None:
        """The unified demo script must complete without errors in mock mode."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_end_to_end_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Demo failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "v1.0.0 Demo completed successfully." in result.stdout

    def test_demo_produces_audit_report(self, tmp_path: Path) -> None:
        """The demo must produce an audit report."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_end_to_end_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "reports/audit_report.json exists -> OK" in result.stdout
        assert "reports/audit_report.md exists -> OK" in result.stdout

    def test_demo_claim_map_changes_only_after_explicit_update(self, tmp_path: Path) -> None:
        """The demo must only change claim_map through aieng_update_claim."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_end_to_end_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "claim_map.json updated only via aieng_update_claim -> OK" in result.stdout
        assert "No hidden claim advancement in evidence -> OK" in result.stdout


class TestV1WorkflowComponents:
    def test_reference_map_builds_and_persists(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.references import build_reference_map, write_reference_map

        package_path = _copy_parametric_bracket(tmp_path)
        ref_map = build_reference_map(str(package_path))
        assert len(ref_map.geometry_references) > 0
        written = write_reference_map(str(package_path), ref_map)
        assert Path(written).exists()

    def test_patch_execution_marks_refs_needing_review(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal
        from freecad_mcp.aieng_bridge.references import (
            build_reference_map,
            load_reference_map,
            write_reference_map,
        )
        from freecad_mcp.bridge.executor import FreecadExecutor

        class _MockExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict:
                if "setattr(obj," in code:
                    return {
                        "success": True,
                        "result": {
                            "object_name": "BasePlate",
                            "parameter_name": "Thickness",
                            "old_value": 10.0,
                            "new_value": 8.0,
                        },
                    }
                if "exportStep" in code:
                    return {"success": True, "result": {"file_path": "/mock/output.step", "object_count": 1}}
                if "saveAs" in code:
                    return {"success": True, "result": {"file_path": "/mock/output.FCStd", "document": "Unnamed"}}
                return {"success": True, "result": {}}

            async def get_version_async(self) -> dict:
                return {"version": "0.21.0_mock", "gui_available": False}

        package_path = _copy_parametric_bracket(tmp_path)
        ref_map = build_reference_map(str(package_path))
        write_reference_map(str(package_path), ref_map)

        patch_raw = {
            "patch_id": "test_patch",
            "operations": [
                {
                    "operation": "modify_parameter",
                    "target_feature_id": "feat_base_plate_001",
                    "parameter_name": "thickness_mm",
                    "new_value": 8.0,
                }
            ],
        }
        plan = parse_patch_proposal(patch_raw)

        import asyncio
        summary = asyncio.run(
            execute_patch_plan(
                plan,
                _MockExecutor(),
                package_path=str(package_path),
                persist_to_aieng=True,
                export_modified_step=True,
            )
        )
        assert summary.status == "success"

        updated = load_reference_map(str(package_path))
        assert updated is not None
        affected = [g for g in updated.geometry_references if g.feature_id == "feat_base_plate_001"]
        assert any(g.status == "needs_review" for g in affected)

    def test_claim_update_only_modifies_target_claim(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.claims import (
            ClaimDecisionCriterion,
            ClaimUpdateRequest,
            update_claim_status,
        )
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry

        package_path = _copy_parametric_bracket(tmp_path)
        append_evidence_entry(
            str(package_path),
            {
                "evidence_id": "ev-test",
                "evidence_type": "test",
                "producer_kind": "mock",
                "status": "success",
                "metadata": {
                    "metrics": [
                        {"name": "max_displacement_mm", "value": 1.5, "unit": "mm", "status": "found"}
                    ],
                    "engineering_validation": False,
                    "claims_advanced": False,
                },
            },
        )

        request = ClaimUpdateRequest(
            package_path=str(package_path),
            claim_id="claim_max_displacement_under_limit",
            evidence_ids=["ev-test"],
            decision_criteria=[
                ClaimDecisionCriterion(
                    metric_name="max_displacement_mm",
                    operator="<=",
                    threshold=2.0,
                    unit="mm",
                )
            ],
            mode="evaluate",
            dry_run=False,
        )
        summary = update_claim_status(request)
        assert summary.status == "success"
        assert summary.new_status == "pass"
        assert summary.claim_map_updated is True

        claim_map = json.loads((package_path / "results" / "claim_map.json").read_text())
        updated = next(c for c in claim_map["claims"] if c["id"] == "claim_max_displacement_under_limit")
        assert updated["status"] == "pass"

        other = [c for c in claim_map["claims"] if c["id"] != "claim_max_displacement_under_limit"]
        assert all(c["status"] == "unsupported" for c in other)



class TestV1ComposableDemoScript:
    def test_v1_demo_all_paths_pass(self) -> None:
        """The composable v1 demo must run all five paths successfully."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script), "--path", "all"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Demo failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "All five composable paths completed successfully." in result.stdout
        assert "cad-only     -> PASS" in result.stdout
        assert "cae-only     -> PASS" in result.stdout
        assert "cad-cae      -> PASS" in result.stdout
        assert "reference    -> PASS" in result.stdout
        assert "claim        -> PASS" in result.stdout

    def test_v1_demo_cad_only_path(self) -> None:
        """The composable v1 demo must support the cad-only path."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script), "--path", "cad-only"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "CAD-only" in result.stdout
        assert "SUCCESS: run_aieng_patch_demo.py" in result.stdout

    def test_v1_demo_cae_only_path(self) -> None:
        """The composable v1 demo must support the cae-only path."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script), "--path", "cae-only"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "CAE-only" in result.stdout
        assert "SUCCESS: run_postprocessing_demo.py" in result.stdout

    def test_v1_demo_cad_cae_path(self) -> None:
        """The composable v1 demo must support the cad-cae path."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script), "--path", "cad-cae"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Optional CAD->CAE" in result.stdout
        assert "SUCCESS: run_cad_to_cae_demo.py" in result.stdout

    def test_v1_demo_reference_path(self) -> None:
        """The composable v1 demo must support the reference path."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script), "--path", "reference"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Reference" in result.stdout
        assert "SUCCESS: run_reference_mapping_demo.py" in result.stdout

    def test_v1_demo_claim_path(self) -> None:
        """The composable v1 demo must support the claim path."""
        demo_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "run_v1_demo.py"
        )
        result = subprocess.run(
            [sys.executable, str(demo_script), "--path", "claim"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Claim" in result.stdout
        assert "SUCCESS: run_claim_update_demo.py" in result.stdout
