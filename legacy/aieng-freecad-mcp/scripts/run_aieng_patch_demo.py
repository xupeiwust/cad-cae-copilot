"""End-to-end demo: .aieng patch execution with evidence writeback.

This script demonstrates the complete workflow:
  .aieng package → patch proposal → guarded FreeCAD parameter edit
  → modified CAD artifact export → evidence/trace writeback
  → claim_map unchanged

Usage:
    python scripts/run_aieng_patch_demo.py

If FreeCAD is not available, the script runs in mock mode using a
SpyExecutor and still validates the .aieng-level logic.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Add src/ to path so imports work when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.patch import (
    execute_patch_plan,
    load_patch_proposal,
    parse_patch_proposal,
)
from freecad_mcp.bridge.executor import FreecadExecutor


class MockExecutor(FreecadExecutor):
    """Executor that simulates FreeCAD responses without a real connection."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute_async(self, code: str) -> dict:
        self.calls.append(code)
        # Simulate parameter change
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
        # Simulate STEP export
        if "exportStep" in code:
            return {"success": True, "result": {"file_path": "/mock/output.step", "object_count": 1}}
        # Simulate FCStd export
        if "saveAs" in code:
            return {"success": True, "result": {"file_path": "/mock/output.FCStd", "document": "Unnamed"}}
        return {"success": True, "result": {}}

    async def get_version_async(self) -> dict:
        return {"version": "0.21.0_mock", "gui_available": False}


def _copy_fixture(tmp_dir: Path) -> Path:
    """Copy the reference fixture into a temporary directory."""
    fixture_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
    fixture_dst = tmp_dir / "package"
    shutil.copytree(fixture_src, fixture_dst)
    return fixture_dst


def _load_patch(patch_name: str) -> dict:
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
    print("=" * 60)
    print(" .aieng Patch Execution Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        print(f"\n1. Loaded .aieng package: {package_path}")

        # Load context
        context = load_aieng_context(str(package_path))
        print(f"   Context mode: {context.mode}")
        print(f"   Feature graph features: {list(context.feature_graph.get('features', {}).keys())}")

        # Load valid patch
        patch_raw = _load_patch("reduce_base_plate_thickness")
        print(f"\n2. Loaded patch: {patch_raw['patch_id']}")
        print(f"   Operations: {len(patch_raw['operations'])}")

        # Parse
        plan = parse_patch_proposal(patch_raw)
        print(f"\n3. Parsed patch plan")
        print(f"   Supported: {len(plan.operations)}")
        print(f"   Unsupported: {len(plan.unsupported_operations)}")

        # Create mock executor
        executor = MockExecutor()

        # Dry run
        print("\n4. Dry-run execution...")
        dry_summary = await execute_patch_plan(
            plan, executor, package_path=str(package_path), dry_run=True
        )
        print(f"   Status: {dry_summary.status}")
        for step in dry_summary.steps:
            print(f"   Step {step.operation_index}: {step.status} ({step.operation})")

        # Real execution with persistence and export
        print("\n5. Real execution with persistence + artifact export...")
        summary = await execute_patch_plan(
            plan,
            executor,
            package_path=str(package_path),
            persist_to_aieng=True,
            export_modified_step=True,
            export_modified_fcstd=True,
        )
        print(f"   Status: {summary.status}")
        for step in summary.steps:
            print(f"   Step {step.operation_index}: {step.status} ({step.operation})")
            if step.result:
                print(f"      old_value={step.result.get('old_value')}, new_value={step.result.get('new_value')}")
        print(f"   Artifacts written: {summary.artifacts_written}")
        print(f"   Evidence IDs: {summary.evidence_ids}")
        print(f"   Trace IDs: {summary.trace_ids}")

        # Verify evidence index was appended
        evidence_index_path = package_path / "results" / "evidence_index.json"
        evidence_index = json.loads(evidence_index_path.read_text())
        print(f"\n6. Evidence index entries: {len(evidence_index.get('entries', []))}")

        # Verify trace was appended
        tool_trace_path = package_path / "provenance" / "tool_trace.json"
        tool_trace = json.loads(tool_trace_path.read_text())
        print(f"   Tool trace entries: {len(tool_trace.get('entries', []))}")

        # Verify patch run record was created
        runs_dir = package_path / "execution" / "patch_runs"
        if runs_dir.exists():
            run_files = list(runs_dir.glob("*.json"))
            print(f"   Patch run records: {len(run_files)}")
            for rf in run_files:
                print(f"      {rf.name}")
        else:
            print("   Patch run records: 0 (directory not created)")

        # Verify claim_map was NOT modified
        claim_map_path = package_path / "results" / "claim_map.json"
        claim_map = json.loads(claim_map_path.read_text())
        original_claim_map = {
            "claims": [
                {
                    "id": "claim_mass_under_500g",
                    "description": "Total mass of bracket must be under 500g",
                    "status": "unsupported",
                    "criteria": {"max_mass_g": 500},
                },
                {
                    "id": "claim_stress_under_yield",
                    "description": "Maximum von Mises stress must be under yield strength",
                    "status": "unsupported",
                    "criteria": {"safety_factor": 1.5},
                },
                {
                    "id": "claim_max_displacement_under_limit",
                    "description": "Maximum displacement under static load must be <= 2.0 mm",
                    "status": "unsupported",
                    "criteria": {"max_displacement_mm": 2.0},
                },
            ]
        }
        assert claim_map == original_claim_map, "claim_map.json was modified!"
        print(f"\n7. claim_map.json: UNCHANGED (claims remain unsupported)")

        # Test rejected patches
        print("\n8. Testing rejected patches...")

        protected_patch = _load_patch("reject_protected_hole_edit")
        protected_plan = parse_patch_proposal(protected_patch)
        protected_summary = await execute_patch_plan(
            protected_plan, executor, package_path=str(package_path)
        )
        print(f"   Protected hole edit: {protected_summary.status}")
        assert protected_summary.status == "rejected"

        semantic_patch = _load_patch("reject_semantic_only_edit")
        semantic_plan = parse_patch_proposal(semantic_patch)
        semantic_summary = await execute_patch_plan(
            semantic_plan, executor, package_path=str(package_path)
        )
        print(f"   Semantic-only rib edit: {semantic_summary.status}")
        assert semantic_summary.status == "rejected"

    print("\n" + "=" * 60)
    print(" Demo completed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
