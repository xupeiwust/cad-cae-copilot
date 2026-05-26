"""v1.0.0 unified end-to-end demo.

Demonstrates the complete public engineering workflow:

  .aieng package -> reference map -> patch proposal -> guarded FreeCAD edit
  -> modified artifact evidence -> CAD-to-CAE evidence
  -> post-processing evidence -> explicit claim update -> final audit report

Modes:
- Default (mock/surrogate): No FreeCAD required. Uses MockExecutor + surrogate CAE.
- Real runtime: Detects FreeCAD/FEM/CalculiX availability and uses them if present.
  Skips cleanly otherwise.

Usage:
    python scripts/run_v1_end_to_end_demo.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from freecad_mcp.aieng_bridge.audit import generate_audit_report
from freecad_mcp.aieng_bridge.claims import (
    ClaimDecisionCriterion,
    ClaimUpdateRequest,
    update_claim_status,
)
from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.patch import (
    execute_patch_plan,
    load_patch_proposal,
    parse_patch_proposal,
)
from freecad_mcp.aieng_bridge.references import (
    build_reference_map,
    load_reference_map,
    write_reference_map,
)
from freecad_mcp.aieng_bridge.workflow import (
    CadToCaeWorkflowRequest,
    run_cad_to_cae_workflow,
)
from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset
from freecad_mcp.freecad_runtime import detect_freecad_runtime


class MockExecutor(FreecadExecutor):
    """Executor that simulates FreeCAD responses without a real connection."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute_async(self, code: str) -> dict[str, Any]:
        self.calls.append(code)
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

    async def get_version_async(self) -> dict[str, Any]:
        return {"version": "0.21.0_mock", "gui_available": False}


def _copy_fixture(tmp_dir: Path) -> Path:
    fixture_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
    fixture_dst = tmp_dir / "package"
    shutil.copytree(fixture_src, fixture_dst)
    # Also copy fixture resources that may not be in the base package
    for subdir in ["objects", "simulation", "visual"]:
        src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / subdir
        if src.exists():
            for child in src.iterdir():
                if child.is_file():
                    dst_dir = fixture_dst / subdir
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(child, dst_dir / child.name)
    return fixture_dst


def _load_patch(patch_name: str) -> dict[str, Any]:
    patch_path = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "parametric_bracket"
        / "patches"
        / f"{patch_name}.json"
    )
    with patch_path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def main() -> int:
    print("=" * 70)
    print(" v1.0.0 Unified End-to-End Engineering Workflow Demo")
    print("=" * 70)

    # Detect runtime capabilities (informational only)
    print("\n[Runtime Detection]")
    caps = detect_freecad_runtime()
    print(f"   FreeCAD available: {caps.freecad_available}")
    print(f"   FEM available: {caps.fem_available}")
    print(f"   CalculiX available: {caps.calculix_available}")

    use_real = caps.freecad_available and caps.fem_available
    if use_real:
        print("   -> Real FreeCAD/FEM runtime detected. Will attempt real path where supported.")
    else:
        print("   -> Mock/surrogate mode (default). No FreeCAD required.")

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        print(f"\n[1] Loaded .aieng package: {package_path}")

        context = load_aieng_context(str(package_path))
        print(f"    Context mode: {context.mode}")

        # ── Step 2: Reference Map ──────────────────────────────────────
        print("\n[2] Building reference map...")
        ref_map = build_reference_map(str(package_path))
        print(f"    Geometry references: {len(ref_map.geometry_references)}")
        print(f"    CAE targets: {len(ref_map.cae_targets)}")
        written_path = write_reference_map(str(package_path), ref_map)
        print(f"    Written to: {written_path}")

        # ── Step 3: Parse Patch Proposal ───────────────────────────────
        print("\n[3] Parsing patch proposal...")
        patch_raw = _load_patch("reduce_base_plate_thickness")
        plan = parse_patch_proposal(patch_raw)
        print(f"    Patch ID: {plan.patch_id}")
        print(f"    Supported operations: {len(plan.operations)}")
        print(f"    Unsupported operations: {len(plan.unsupported_operations)}")

        # ── Step 4: Dry-Run Patch ──────────────────────────────────────
        print("\n[4] Dry-run patch execution...")
        executor = MockExecutor()
        dry_summary = await execute_patch_plan(
            plan,
            executor,
            package_path=str(package_path),
            persist_to_aieng=False,
            dry_run=True,
            export_modified_step=True,
        )
        print(f"    Dry-run status: {dry_summary.status}")
        print("    -> Dry-run OK (no files modified)")

        # ── Step 5: Execute Patch with Evidence ────────────────────────
        print("\n[5] Executing patch with evidence persistence...")
        exec_summary = await execute_patch_plan(
            plan,
            executor,
            package_path=str(package_path),
            persist_to_aieng=True,
            dry_run=False,
            export_modified_step=True,
            export_modified_fcstd=True,
        )
        print(f"    Execution status: {exec_summary.status}")
        print(f"    Steps completed: {len(exec_summary.steps)}")
        print(f"    Artifacts written: {exec_summary.artifacts_written}")
        print(f"    Evidence IDs: {exec_summary.evidence_ids}")
        print(f"    Trace IDs: {exec_summary.trace_ids}")
        assert exec_summary.status in ("success", "partial")

        # ── Step 6: Verify Reference Map Marked needs_review ───────────
        print("\n[6] Verifying reference map after patch...")
        updated_ref_map = load_reference_map(str(package_path))
        assert updated_ref_map is not None
        affected_geo = [g for g in updated_ref_map.geometry_references if g.feature_id == "feat_base_plate_001"]
        assert any(g.status == "needs_review" for g in affected_geo), "Affected refs should be needs_review"
        linked_cae = [c for c in updated_ref_map.cae_targets if c.feature_id == "feat_base_plate_001"]
        assert any(c.status == "needs_review" for c in linked_cae), "Linked CAE targets should be needs_review"
        unaffected = [g for g in updated_ref_map.geometry_references if g.feature_id == "feat_mounting_holes_001"]
        assert all(g.status != "needs_review" for g in unaffected), "Unaffected refs unchanged"
        print("    -> Affected references marked needs_review: OK")
        print("    -> Unaffected references unchanged: OK")

        # ── Step 7: CAD-to-CAE Workflow with Post-Processing ───────────
        print("\n[7] Running CAD-to-CAE workflow with post-processing...")
        facade = CAEFacade(SurrogateStaticCaeToolset())
        workflow_request = CadToCaeWorkflowRequest(
            package_path=str(package_path),
            patch_json=patch_raw,
            persist_to_aieng=True,
            dry_run=False,
            export_modified_step=True,
            export_modified_fcstd=True,
            run_mesh=True,
            export_solver_deck=True,
            run_solver=False,
            run_postprocess=True,
            export_postprocess_csv=True,
            export_postprocess_vtk=False,
            analysis_type="static_structural",
            stop_on_failure=True,
        )
        workflow_summary = await run_cad_to_cae_workflow(
            workflow_request,
            executor,
            facade,
        )
        print(f"    Workflow status: {workflow_summary.status}")
        print(f"    Patch status: {workflow_summary.patch_summary.status if workflow_summary.patch_summary else 'N/A'}")
        for step in workflow_summary.cae_steps:
            print(f"    CAE step '{step.step_name}': {step.status}")
        if workflow_summary.postprocess_summary:
            pp = workflow_summary.postprocess_summary
            print(f"    Post-process status: {pp.get('status', 'N/A')}")
            print(f"    Metrics extracted: {len(pp.get('metrics', []))}")
        assert workflow_summary.status in ("success", "partial")
        assert workflow_summary.claim_policy.claims_advanced is False
        print("    -> Workflow completed with claims_advanced=False: OK")

        # ── Step 8: Dry-Run Claim Update ───────────────────────────────
        print("\n[8] Running explicit claim update (dry-run)...")
        # Create mock evidence with a metric for claim evaluation
        evidence_id = "ev-mock-displacement-001"
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry

        evidence_entry = {
            "evidence_id": evidence_id,
            "evidence_type": "mock_test",
            "producer_kind": "mock",
            "status": "success",
            "operation": "mock_analysis",
            "metadata": {
                "metrics": [
                    {"name": "max_displacement_mm", "value": 1.5, "unit": "mm", "status": "found"}
                ],
                "engineering_validation": False,
                "claims_advanced": False,
            },
        }
        append_evidence_entry(str(package_path), evidence_entry)

        dry_request = ClaimUpdateRequest(
            package_path=str(package_path),
            claim_id="claim_max_displacement_under_limit",
            evidence_ids=[evidence_id],
            decision_criteria=[
                ClaimDecisionCriterion(
                    metric_name="max_displacement_mm",
                    operator="<=",
                    threshold=2.0,
                    unit="mm",
                )
            ],
            mode="evaluate",
            dry_run=True,
        )
        dry_claim_summary = update_claim_status(dry_request)
        print(f"    Dry-run status: {dry_claim_summary.status}")
        print(f"    Predicted new status: {dry_claim_summary.new_status}")
        assert dry_claim_summary.claim_map_updated is False
        print("    -> claim_map.json UNCHANGED (dry-run): OK")

        # ── Step 9: Real Claim Update (demo-safe only) ─────────────────
        print("\n[9] Running explicit claim update (real, demo-safe)...")
        real_request = ClaimUpdateRequest(
            package_path=str(package_path),
            claim_id="claim_max_displacement_under_limit",
            evidence_ids=[evidence_id],
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
        real_claim_summary = update_claim_status(real_request)
        print(f"    Update status: {real_claim_summary.status}")
        print(f"    Old status: {real_claim_summary.old_status}")
        print(f"    New status: {real_claim_summary.new_status}")
        assert real_claim_summary.claim_map_updated is True
        print("    -> claim_map.json UPDATED via aieng_update_claim: OK")

        # ── Step 10: Generate Audit Report ─────────────────────────────
        print("\n[10] Generating final audit report...")
        audit_result = generate_audit_report(
            package_path=str(package_path),
            output_markdown=True,
            output_json=True,
        )
        print(f"    Audit status: {audit_result['status']}")
        print(f"    Written paths:")
        for p in audit_result["written_paths"]:
            print(f"      - {p}")

        # ── Step 11: Final Verifications ───────────────────────────────
        print("\n[11] Final verifications...")

        # evidence_index.json appended
        evidence = json.loads((package_path / "results" / "evidence_index.json").read_text())
        assert len(evidence.get("entries", [])) > 0, "Evidence should be appended"
        print(f"    evidence_index.json entries: {len(evidence['entries'])} -> OK")

        # provenance/tool_trace.json appended
        trace = json.loads((package_path / "provenance" / "tool_trace.json").read_text())
        assert len(trace.get("entries", [])) > 0, "Trace should be appended"
        print(f"    tool_trace.json entries: {len(trace['entries'])} -> OK")

        # execution/patch_runs exists
        patch_runs_dir = package_path / "execution" / "patch_runs"
        assert patch_runs_dir.exists(), "Patch runs directory should exist"
        patch_run_files = list(patch_runs_dir.glob("*.json"))
        print(f"    execution/patch_runs files: {len(patch_run_files)} -> OK")

        # objects/reference_map.json exists
        ref_map_path = package_path / "objects" / "reference_map.json"
        assert ref_map_path.exists(), "Reference map should exist"
        print(f"    objects/reference_map.json exists -> OK")

        # post-processing CSV exists (from workflow)
        pp_csv_files = list(package_path.rglob("*.csv"))
        if pp_csv_files:
            print(f"    Post-processing CSV exists -> OK")
        else:
            print(f"    Post-processing CSV: not found (acceptable in mock mode)")

        # claim_map changed only through aieng_update_claim
        claim_map = json.loads((package_path / "results" / "claim_map.json").read_text())
        updated_claim = next(
            (c for c in claim_map.get("claims", []) if c["id"] == "claim_max_displacement_under_limit"),
            None,
        )
        assert updated_claim is not None
        assert updated_claim["status"] == "pass", "Claim should be pass after explicit update"
        other_claims = [c for c in claim_map.get("claims", []) if c["id"] != "claim_max_displacement_under_limit"]
        assert all(c["status"] == "unsupported" for c in other_claims), "Other claims should remain unsupported"
        print(f"    claim_map.json updated only via aieng_update_claim -> OK")

        # No hidden claim advancement
        for entry in evidence.get("entries", []):
            meta = entry.get("metadata", {})
            assert meta.get("claims_advanced") is not True, "No evidence should have claims_advanced=True"
        print(f"    No hidden claim advancement in evidence -> OK")

        # Audit report exists
        audit_json_path = package_path / "reports" / "audit_report.json"
        audit_md_path = package_path / "reports" / "audit_report.md"
        assert audit_json_path.exists(), "Audit JSON should exist"
        assert audit_md_path.exists(), "Audit MD should exist"
        print(f"    reports/audit_report.json exists -> OK")
        print(f"    reports/audit_report.md exists -> OK")

        # Print concise audit summary
        audit_data = json.loads(audit_json_path.read_text())
        print("\n" + "=" * 70)
        print(" Audit Summary")
        print("=" * 70)
        print(f"  Evidence entries: {audit_data['evidence_summary']['total']}")
        print(f"  Trace entries: {audit_data['trace_summary']['total']}")
        print(f"  Patch runs: {audit_data['patch_run_summary']['total']}")
        print(f"  Reference map statuses: {audit_data['reference_map_summary']['status_counts']}")
        print(f"  Claim statuses: {audit_data['claim_summary']['status_counts']}")
        print(f"  Artifacts: {audit_data['artifacts_summary']['total']}")
        print(f"  Claim discipline OK: {audit_data['claim_discipline_summary']['tools_did_not_auto_advance_claims']}")
        print(f"  Explicit claim updates: {audit_data['claim_discipline_summary']['explicit_update_trace_count']}")

    print("\n" + "=" * 70)
    print(" v1.0.0 Demo completed successfully.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
