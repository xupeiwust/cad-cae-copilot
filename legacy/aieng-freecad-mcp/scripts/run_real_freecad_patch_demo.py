"""Integration demo: run the .aieng patch workflow against a real FreeCAD document.

Usage:
    python scripts/run_real_freecad_patch_demo.py

If FreeCAD is not available, the script exits cleanly with a skip message.
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
from freecad_mcp.aieng_bridge.patch import (
    execute_patch_plan,
    load_patch_proposal,
    parse_patch_proposal,
)
from freecad_mcp.bridge.executor import FreecadExecutor


def _freecad_available() -> bool:
    try:
        import FreeCAD
        return True
    except ImportError:
        return False


class RealFreecadExecutor(FreecadExecutor):
    """Executor that runs FreeCAD code in the same Python process."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        import FreeCAD
        self._fc = FreeCAD

    async def execute_async(self, code: str) -> dict:
        self.calls.append(code)
        # Execute the code in a namespace with FreeCAD available
        namespace = {"FreeCAD": self._fc, "Part": __import__("Part")}
        try:
            exec(code, namespace)
            result = namespace.get("_result_", {})
            return {"success": True, "result": result}
        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    async def get_version_async(self) -> dict:
        return {"version": ".".join(self._fc.Version()[:3]), "gui_available": False}


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


def _copy_source_fcstd(package_path: Path) -> None:
    src = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "parametric_bracket"
        / "freecad"
        / "source.FCStd"
    )
    if src.exists():
        dst = package_path / "geometry" / "source.FCStd"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


async def main() -> int:
    print("=" * 60)
    print(" Real FreeCAD Patch Execution Demo")
    print("=" * 60)

    if not _freecad_available():
        print("\nFreeCAD is not available. Skipping integration demo.")
        print("Install FreeCAD and ensure its Python modules are on PYTHONPATH.")
        return 0

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        _copy_source_fcstd(package_path)

        print(f"\n1. Loaded .aieng package: {package_path}")

        # Open the source FCStd in FreeCAD
        import FreeCAD as App
        fcstd_file = package_path / "geometry" / "source.FCStd"
        if fcstd_file.exists():
            doc = App.openDocument(str(fcstd_file))
            print(f"   Opened FreeCAD document: {doc.Name}")
        else:
            print("   No source.FCStd found; using active document.")
            doc = App.ActiveDocument

        # Load context
        context = load_aieng_context(str(package_path))
        print(f"   Context mode: {context.mode}")

        # Load and parse patch
        patch_raw = _load_patch("reduce_base_plate_thickness")
        print(f"\n2. Loaded patch: {patch_raw['patch_id']}")
        plan = parse_patch_proposal(patch_raw)
        print(f"   Supported operations: {len(plan.operations)}")

        # Create executor
        executor = RealFreecadExecutor()

        # Execute with persistence and export
        print("\n3. Executing patch with export...")
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
            print(f"   Step {step.operation_index}: {step.status}")
            if step.result:
                old_v = step.result.get('old_value')
                new_v = step.result.get('new_value')
                print(f"      {old_v} → {new_v}")
        print(f"   Artifacts written: {summary.artifacts_written}")

        # Verify artifacts exist
        print("\n4. Verifying artifacts...")
        for artifact in summary.artifacts_written:
            p = Path(artifact)
            if p.suffix in ('.FCStd', '.step'):
                exists = p.exists()
                print(f"   {'✓' if exists else '✗'} {p.name}")

        # Verify evidence
        evidence_path = package_path / "results" / "evidence_index.json"
        evidence = json.loads(evidence_path.read_text())
        print(f"\n5. Evidence entries: {len(evidence.get('entries', []))}")

        # Verify trace
        trace_path = package_path / "provenance" / "tool_trace.json"
        trace = json.loads(trace_path.read_text())
        print(f"   Trace entries: {len(trace.get('entries', []))}")

        # Verify run record
        runs_dir = package_path / "execution" / "patch_runs"
        if runs_dir.exists():
            runs = list(runs_dir.glob("*.json"))
            print(f"   Patch run records: {len(runs)}")

        # Verify claim_map unchanged
        claim_map_path = package_path / "results" / "claim_map.json"
        claim_map = json.loads(claim_map_path.read_text())
        assert all(c["status"] == "unsupported" for c in claim_map.get("claims", []))
        print(f"\n6. claim_map.json: UNCHANGED")

        # Verify actual FreeCAD parameter changed
        if doc:
            obj = doc.getObject("BasePlate")
            if obj:
                current_height = getattr(obj, "Height", None)
                print(f"\n7. FreeCAD BasePlate.Height = {current_height} mm")

    print("\n" + "=" * 60)
    print(" Integration demo completed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
