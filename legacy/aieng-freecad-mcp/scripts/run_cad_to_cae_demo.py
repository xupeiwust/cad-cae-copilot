"""Optional CAD/CAE orchestration demo.

Demonstrates explicit composition of independent CAD and CAE workflows.
This is not an automatic pipeline — CAD patch execution and CAE operations
are independent first-class workflows. The orchestration helper composes
them only when explicitly invoked.

Runs using either:
- Mock/surrogate path (default, no FreeCAD required)
- Real FreeCAD + CAE backend if available

Usage:
    python scripts/run_cad_to_cae_demo.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.workflow import (
    CadToCaeWorkflowRequest,
    run_cad_to_cae_workflow,
)
from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset


class MockExecutor(FreecadExecutor):
    """Executor that simulates FreeCAD responses."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute_async(self, code: str) -> dict:
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

    async def get_version_async(self) -> dict:
        return {"version": "0.21.0_mock", "gui_available": False}


def _copy_fixture(tmp_dir: Path) -> Path:
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
    print(" CAD-to-CAE Workflow Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        print(f"\n1. Loaded .aieng package: {package_path}")

        context = load_aieng_context(str(package_path))
        print(f"   Context mode: {context.mode}")

        patch_raw = _load_patch("reduce_base_plate_thickness")
        print(f"\n2. Loaded patch: {patch_raw['patch_id']}")

        # Use mock executor + surrogate CAE by default
        executor = MockExecutor()
        facade = CAEFacade(SurrogateStaticCaeToolset())

        print("\n3. Running CAD-to-CAE workflow (surrogate mode)...")
        request = CadToCaeWorkflowRequest(
            package_path=str(package_path),
            patch_json=patch_raw,
            persist_to_aieng=True,
            dry_run=False,
            export_modified_step=True,
            export_modified_fcstd=True,
            run_mesh=True,
            export_solver_deck=True,
            run_solver=False,
            import_solver_evidence=True,
        )

        summary = await run_cad_to_cae_workflow(request, executor, facade)

        print(f"\n4. Workflow result")
        print(f"   Status: {summary.status}")
        print(f"   Mode: {summary.mode}")

        if summary.patch_summary:
            print(f"   Patch status: {summary.patch_summary.status}")
            for step in summary.patch_summary.steps:
                print(f"   CAD Step {step.operation_index}: {step.status}")
                if step.result:
                    print(f"      {step.result.get('old_value')} -> {step.result.get('new_value')}")

        print(f"\n5. CAD Artifacts")
        for artifact in summary.cad_artifacts:
            print(f"   {artifact['artifact_type']}: {Path(artifact['path']).name}")

        print(f"\n6. CAE Steps")
        for step in summary.cae_steps:
            print(f"   {step.step_name}: {step.status} (producer={step.producer_kind})")
            if step.errors:
                for err in step.errors:
                    print(f"      ERROR: {err}")

        # Verify evidence
        evidence_path = package_path / "results" / "evidence_index.json"
        evidence = json.loads(evidence_path.read_text())
        print(f"\n7. Evidence entries: {len(evidence.get('entries', []))}")

        # Verify trace
        trace_path = package_path / "provenance" / "tool_trace.json"
        trace = json.loads(trace_path.read_text())
        print(f"   Trace entries: {len(trace.get('entries', []))}")

        # Verify claim_map unchanged
        claim_map = json.loads((package_path / "results" / "claim_map.json").read_text())
        assert all(c["status"] == "unsupported" for c in claim_map.get("claims", []))
        print(f"   claim_map.json: UNCHANGED")

        # Verify workflow metadata
        if evidence["entries"]:
            last_entry = evidence["entries"][-1]
            meta = last_entry.get("metadata", {})
            print(f"\n8. Workflow metadata")
            print(f"   producer_kind: {meta.get('producer_kind')}")
            print(f"   solver_executed: {meta.get('solver_executed')}")
            print(f"   engineering_validation: {meta.get('engineering_validation')}")
            print(f"   claims_advanced: {meta.get('claims_advanced')}")
            if meta.get("warning"):
                print(f"   warning: {meta['warning']}")

    print("\n" + "=" * 60)
    print(" Demo completed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
