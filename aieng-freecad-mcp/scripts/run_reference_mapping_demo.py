"""Reference mapping demo.

Demonstrates geometry reference and CAE target mapping scaffold.

Usage:
    python scripts/run_reference_mapping_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from freecad_mcp.aieng_bridge.references import (
    build_reference_map,
    load_reference_map,
    write_reference_map,
)
from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.aieng_bridge.patch import (
    execute_patch_plan,
    parse_patch_proposal,
)


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
    # Also copy the new fixture resources
    for subdir in ["objects", "simulation", "visual"]:
        src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / subdir
        if src.exists():
            dst = fixture_dst.parent / subdir
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    # Copy simulation/cae_mapping.json into package
    cae_mapping_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "simulation" / "cae_mapping.json"
    if cae_mapping_src.exists():
        sim_dir = fixture_dst / "simulation"
        sim_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cae_mapping_src, sim_dir / "cae_mapping.json")
    # Copy objects/interface_graph.json into package
    iface_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "objects" / "interface_graph.json"
    if iface_src.exists():
        obj_dir = fixture_dst / "objects"
        obj_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(iface_src, obj_dir / "interface_graph.json")
    # Copy visual/annotation_layers.json into package
    visual_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "visual" / "annotation_layers.json"
    if visual_src.exists():
        vis_dir = fixture_dst / "visual"
        vis_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(visual_src, vis_dir / "annotation_layers.json")
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
    print(" Reference Mapping Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        print(f"\n1. Loaded .aieng package: {package_path}")

        # Build reference map
        print("\n2. Building reference map...")
        ref_map = build_reference_map(str(package_path))
        print(f"   Geometry references: {len(ref_map.geometry_references)}")
        for geo in ref_map.geometry_references:
            print(f"      {geo.ref_id}: feature={geo.feature_id}, method={geo.mapping_method}, confidence={geo.confidence}")

        print(f"   CAE targets: {len(ref_map.cae_targets)}")
        for target in ref_map.cae_targets:
            print(f"      {target.target_id}: type={target.target_type}, method={target.mapping_method}, confidence={target.confidence}")

        # Persist reference map
        print("\n3. Persisting reference map...")
        written_path = write_reference_map(str(package_path), ref_map)
        print(f"   Written to: {written_path}")
        assert Path(written_path).exists()

        # Verify load roundtrip
        loaded = load_reference_map(str(package_path))
        assert loaded is not None
        assert len(loaded.geometry_references) == len(ref_map.geometry_references)
        print("   Load roundtrip: OK")

        # Execute valid patch
        print("\n4. Executing patch (reduce base plate thickness)...")
        patch_raw = _load_patch("reduce_base_plate_thickness")
        plan = parse_patch_proposal(patch_raw)
        executor = MockExecutor()
        summary = await execute_patch_plan(
            plan,
            executor,
            package_path=str(package_path),
            persist_to_aieng=False,
            export_modified_step=True,
        )
        print(f"   Patch status: {summary.status}")

        # Verify affected references marked needs_review
        print("\n5. Checking reference map after patch...")
        updated = load_reference_map(str(package_path))
        assert updated is not None

        affected_geo = [g for g in updated.geometry_references if g.feature_id == "feat_base_plate_001"]
        assert any(g.status == "needs_review" for g in affected_geo), "Affected geometry ref should be needs_review"
        print(f"   Affected geometry refs marked needs_review: OK")

        linked_cae = [c for c in updated.cae_targets if c.feature_id == "feat_base_plate_001"]
        assert any(c.status == "needs_review" for c in linked_cae), "Linked CAE targets should be needs_review"
        print(f"   Linked CAE targets marked needs_review: OK")

        unaffected = [g for g in updated.geometry_references if g.feature_id == "feat_mounting_holes_001"]
        assert all(g.status != "needs_review" for g in unaffected), "Unaffected refs should not be marked"
        print(f"   Unaffected refs unchanged: OK")

        # Verify claim_map unchanged
        claim_map = json.loads((package_path / "results" / "claim_map.json").read_text())
        assert all(c["status"] == "unsupported" for c in claim_map.get("claims", []))
        print(f"   claim_map.json: UNCHANGED")

    print("\n" + "=" * 60)
    print(" Demo completed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
