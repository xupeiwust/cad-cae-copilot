"""Tests for the geometry reference and CAE target mapping scaffold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.aieng_bridge.references import (
    CaeTargetReference,
    GeometryReference,
    ReferenceMap,
    build_reference_map,
    load_reference_map,
    mark_references_needing_review,
    write_reference_map,
)
from freecad_mcp.tools_aieng import register_aieng_tools


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestReferenceModels:
    def test_geometry_reference_defaults(self) -> None:
        ref = GeometryReference(ref_id="geom_001")
        assert ref.mapping_method == "unresolved"
        assert ref.confidence == "unknown"
        assert ref.status == "unresolved"

    def test_cae_target_reference_defaults(self) -> None:
        target = CaeTargetReference(target_id="bc_001")
        assert target.target_type == "unknown"
        assert target.mapping_method == "unresolved"

    def test_reference_map_serialization(self) -> None:
        ref_map = ReferenceMap(
            package_path="/tmp/pkg",
            geometry_references=[GeometryReference(ref_id="g1", feature_id="f1")],
            cae_targets=[CaeTargetReference(target_id="t1")],
        )
        dumped = ref_map.model_dump(mode="json")
        assert dumped["schema_version"] == "0.1.0"
        assert len(dumped["geometry_references"]) == 1
        assert len(dumped["cae_targets"]) == 1


# ---------------------------------------------------------------------------
# Build reference map tests
# ---------------------------------------------------------------------------

class TestBuildReferenceMap:
    def _build_minimal_package(self, tmp_path: Path, **extra_files: dict[str, Any]) -> Path:
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "simulation").mkdir()
        (tmp_path / "results").mkdir()
        return tmp_path

    def test_build_from_feature_graph(self, tmp_path: Path) -> None:
        pkg = self._build_minimal_package(tmp_path)
        feature_graph = {
            "features": {
                "feat_box": {
                    "name": "Box",
                    "freecad_object_name": "Box",
                    "parameters": [],
                }
            }
        }
        (pkg / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        ref_map = build_reference_map(str(pkg))
        assert len(ref_map.geometry_references) >= 1
        box_ref = next(r for r in ref_map.geometry_references if r.feature_id == "feat_box")
        assert box_ref.freecad_object_name == "Box"
        assert box_ref.mapping_method == "freecad_object_name"
        assert box_ref.confidence == "medium"

    def test_build_from_simulation_setup(self, tmp_path: Path) -> None:
        pkg = self._build_minimal_package(tmp_path)
        sim_setup = {
            "boundary_conditions": [
                {"name": "fixed_base", "target": "base", "constraint_type": "fixed"}
            ],
            "loads": [
                {"name": "center_force", "target": "load_face", "load_type": "force", "magnitude_n": 100, "direction": "-Z"}
            ],
            "mesh": {"target_size_mm": 2.0, "element_type": "tet4", "refinement_regions": ["hole_region"]},
        }
        import yaml
        (pkg / "simulation" / "setup.yaml").write_text(yaml.safe_dump(sim_setup))

        ref_map = build_reference_map(str(pkg))
        bc_targets = [t for t in ref_map.cae_targets if t.target_type == "boundary_condition"]
        load_targets = [t for t in ref_map.cae_targets if t.target_type == "load"]
        mesh_targets = [t for t in ref_map.cae_targets if t.target_type == "mesh_region"]

        assert len(bc_targets) == 1
        assert len(load_targets) == 1
        assert len(mesh_targets) == 1
        assert bc_targets[0].mapping_method == "heuristic"

    def test_build_with_explicit_cae_mapping(self, tmp_path: Path) -> None:
        pkg = self._build_minimal_package(tmp_path)
        sim_setup = {
            "boundary_conditions": [
                {"name": "fixed_base", "target": "base", "constraint_type": "fixed"}
            ],
        }
        import yaml
        (pkg / "simulation" / "setup.yaml").write_text(yaml.safe_dump(sim_setup))

        cae_mapping = {
            "mappings": [
                {
                    "target_id": "bc_fixed_base",
                    "target_name": "fixed_base",
                    "target_type": "boundary_condition",
                    "feature_id": "feat_base",
                    "mapping_method": "user_provided",
                    "confidence": "high",
                }
            ]
        }
        (pkg / "simulation" / "cae_mapping.json").write_text(json.dumps(cae_mapping))

        ref_map = build_reference_map(str(pkg))
        target = next(t for t in ref_map.cae_targets if t.target_id == "bc_fixed_base")
        assert target.mapping_method == "user_provided"
        assert target.confidence == "high"
        assert target.status == "valid"

    def test_build_with_interface_graph(self, tmp_path: Path) -> None:
        pkg = self._build_minimal_package(tmp_path)
        (pkg / "objects").mkdir()
        interface_graph = {
            "interfaces": [
                {"interface_id": "iface_001", "name": "Mounting", "role": "fixed_support"}
            ]
        }
        (pkg / "objects" / "interface_graph.json").write_text(json.dumps(interface_graph))

        ref_map = build_reference_map(str(pkg))
        iface_ref = next(r for r in ref_map.geometry_references if r.interface_id == "iface_001")
        assert iface_ref.mapping_method == "user_provided"
        assert iface_ref.confidence == "high"

    def test_build_missing_resources_warns(self, tmp_path: Path) -> None:
        pkg = self._build_minimal_package(tmp_path)
        # No feature_graph, no simulation_setup
        ref_map = build_reference_map(str(pkg))
        assert len(ref_map.warnings) >= 1
        assert any("feature_graph" in w for w in ref_map.warnings)
        assert any("simulation" in w for w in ref_map.warnings)

    def test_build_no_package(self, tmp_path: Path) -> None:
        # Use a non-existent path
        ref_map = build_reference_map(str(tmp_path / "nonexistent"))
        assert len(ref_map.geometry_references) == 0
        assert len(ref_map.cae_targets) == 0


# ---------------------------------------------------------------------------
# Write and load tests
# ---------------------------------------------------------------------------

class TestWriteAndLoadReferenceMap:
    def test_write_reference_map_creates_objects_dir(self, tmp_path: Path) -> None:
        ref_map = ReferenceMap(package_path=str(tmp_path))
        path = write_reference_map(str(tmp_path), ref_map)
        assert Path(path).exists()
        assert (tmp_path / "objects").is_dir()

    def test_write_and_load_roundtrip(self, tmp_path: Path) -> None:
        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[
                GeometryReference(ref_id="g1", feature_id="f1", freecad_object_name="Box")
            ],
            cae_targets=[CaeTargetReference(target_id="t1", target_type="load")],
        )
        write_reference_map(str(tmp_path), ref_map)
        loaded = load_reference_map(str(tmp_path))
        assert loaded is not None
        assert len(loaded.geometry_references) == 1
        assert len(loaded.cae_targets) == 1
        assert loaded.geometry_references[0].ref_id == "g1"

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        result = load_reference_map(str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# Mark references needing review tests
# ---------------------------------------------------------------------------

class TestMarkReferencesNeedingReview:
    def test_mark_affected_feature_needs_review(self, tmp_path: Path) -> None:
        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[
                GeometryReference(ref_id="g1", feature_id="f1", status="valid"),
                GeometryReference(ref_id="g2", feature_id="f2", status="valid"),
            ],
        )
        write_reference_map(str(tmp_path), ref_map)

        updated = mark_references_needing_review(str(tmp_path), ["f1"], "Test reason")
        g1 = next(r for r in updated.geometry_references if r.ref_id == "g1")
        g2 = next(r for r in updated.geometry_references if r.ref_id == "g2")

        assert g1.status == "needs_review"
        assert "Test reason" in g1.warnings
        assert g2.status == "valid"

    def test_mark_linked_cae_targets_needs_review(self, tmp_path: Path) -> None:
        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[
                GeometryReference(ref_id="g1", feature_id="f1", status="valid"),
            ],
            cae_targets=[
                CaeTargetReference(target_id="t1", feature_id="f1", status="valid"),
                CaeTargetReference(target_id="t2", geometry_ref_id="g1", status="valid"),
                CaeTargetReference(target_id="t3", feature_id="f2", status="valid"),
            ],
        )
        write_reference_map(str(tmp_path), ref_map)

        updated = mark_references_needing_review(str(tmp_path), ["f1"])
        t1 = next(t for t in updated.cae_targets if t.target_id == "t1")
        t2 = next(t for t in updated.cae_targets if t.target_id == "t2")
        t3 = next(t for t in updated.cae_targets if t.target_id == "t3")

        assert t1.status == "needs_review"
        assert t2.status == "needs_review"
        assert t3.status == "valid"

    def test_unaffected_references_unchanged(self, tmp_path: Path) -> None:
        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[
                GeometryReference(ref_id="g1", feature_id="f1", status="valid"),
                GeometryReference(ref_id="g2", feature_id="f2", status="valid"),
            ],
        )
        write_reference_map(str(tmp_path), ref_map)

        updated = mark_references_needing_review(str(tmp_path), ["f1"])
        g2 = next(r for r in updated.geometry_references if r.ref_id == "g2")
        assert g2.status == "valid"
        assert len(g2.warnings) == 0

    def test_mark_builds_map_if_missing(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {"features": {"f1": {"freecad_object_name": "Box"}}}
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))
        (tmp_path / "results").mkdir()

        # No existing reference map
        updated = mark_references_needing_review(str(tmp_path), ["f1"])
        assert any(r.status == "needs_review" for r in updated.geometry_references)
        assert (tmp_path / "objects" / "reference_map.json").exists()


# ---------------------------------------------------------------------------
# Patch integration tests
# ---------------------------------------------------------------------------

class TestPatchIntegration:
    def test_patch_execution_marks_existing_refs_needs_review(self, tmp_path: Path) -> None:
        from freecad_mcp.bridge.executor import FreecadExecutor
        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        class SpyExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                if "setattr(obj," in code:
                    return {"success": True, "result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
                return {"success": True, "result": {}}

        # Build minimal package
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [{"name": "Length", "freecad_parameter_name": "Length"}],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps({"claims": []}))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))

        # Pre-create reference map
        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[GeometryReference(ref_id="g1", feature_id="Box", status="valid")],
        )
        write_reference_map(str(tmp_path), ref_map)

        patch = {
            "operations": [
                {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
            ]
        }
        plan = parse_patch_proposal(patch)
        import asyncio
        summary = asyncio.run(execute_patch_plan(plan, SpyExecutor(), package_path=str(tmp_path), persist_to_aieng=False))

        assert summary.status == "success"
        updated = load_reference_map(str(tmp_path))
        assert updated is not None
        g1 = next(r for r in updated.geometry_references if r.ref_id == "g1")
        assert g1.status == "needs_review"

    def test_patch_execution_no_ref_map_no_side_effect(self, tmp_path: Path) -> None:
        from freecad_mcp.bridge.executor import FreecadExecutor
        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        class SpyExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                if "setattr(obj," in code:
                    return {"success": True, "result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
                return {"success": True, "result": {}}

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [{"name": "Length", "freecad_parameter_name": "Length"}],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps({"claims": []}))

        patch = {
            "operations": [
                {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
            ]
        }
        plan = parse_patch_proposal(patch)
        import asyncio
        summary = asyncio.run(execute_patch_plan(plan, SpyExecutor(), package_path=str(tmp_path), persist_to_aieng=False))

        assert summary.status == "success"
        # No reference map should have been created
        assert not (tmp_path / "objects" / "reference_map.json").exists()

    def test_claim_map_unchanged_after_patch_with_refs(self, tmp_path: Path) -> None:
        from freecad_mcp.bridge.executor import FreecadExecutor
        from freecad_mcp.aieng_bridge.patch import execute_patch_plan, parse_patch_proposal

        class SpyExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                if "setattr(obj," in code:
                    return {"success": True, "result": {"object_name": "Box", "parameter_name": "Length", "old_value": 10.0, "new_value": 20.0}}
                return {"success": True, "result": {}}

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Box": {
                    "editability": {"executable": True},
                    "freecad_object_name": "Box",
                    "parameters": [{"name": "Length", "freecad_parameter_name": "Length"}],
                }
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))
        (tmp_path / "results").mkdir()
        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))

        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[GeometryReference(ref_id="g1", feature_id="Box", status="valid")],
        )
        write_reference_map(str(tmp_path), ref_map)

        patch = {
            "operations": [
                {"operation": "modify_parameter", "target_feature_id": "Box", "parameter_name": "Length", "new_value": 20.0}
            ]
        }
        plan = parse_patch_proposal(patch)
        import asyncio
        summary = asyncio.run(execute_patch_plan(plan, SpyExecutor(), package_path=str(tmp_path), persist_to_aieng=False))

        assert summary.status == "success"
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------

class TestMcpTools:
    def _make_mcp(self) -> Any:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.bridge.executor import FreecadExecutor

        class DummyExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                return {"success": True, "result": {}}

            async def get_version_async(self) -> dict[str, Any]:
                return {"version": "0.21.0", "gui_available": False}

        mcp = FastMCP(name="test")
        executor = DummyExecutor()
        register_aieng_tools(mcp, executor)
        return mcp

    @pytest.mark.asyncio
    async def test_get_reference_map_read_only(self, tmp_path: Path) -> None:
        mcp = self._make_mcp()
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps({"features": {}}))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))
        (tmp_path / "results").mkdir()

        tool = mcp._tool_manager._tools["aieng_get_reference_map"].fn
        response = await tool(package_path=str(tmp_path))

        assert response["status"] == "success"
        assert "reference_map" in response
        # Should not create objects/reference_map.json
        assert not (tmp_path / "objects" / "reference_map.json").exists()

    @pytest.mark.asyncio
    async def test_build_reference_map_persists(self, tmp_path: Path) -> None:
        mcp = self._make_mcp()
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps({"features": {}}))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))
        (tmp_path / "results").mkdir()

        tool = mcp._tool_manager._tools["aieng_build_reference_map"].fn
        response = await tool(package_path=str(tmp_path), persist=True)

        assert response["status"] == "success"
        assert (tmp_path / "objects" / "reference_map.json").exists()

    @pytest.mark.asyncio
    async def test_mark_references_needing_review_tool(self, tmp_path: Path) -> None:
        mcp = self._make_mcp()
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps({"features": {}}))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))
        (tmp_path / "results").mkdir()

        # Pre-create reference map
        ref_map = ReferenceMap(
            package_path=str(tmp_path),
            geometry_references=[GeometryReference(ref_id="g1", feature_id="f1", status="valid")],
        )
        write_reference_map(str(tmp_path), ref_map)

        tool = mcp._tool_manager._tools["aieng_mark_references_needing_review"].fn
        response = await tool(package_path=str(tmp_path), affected_feature_ids=["f1"])

        assert response["status"] == "success"
        updated = load_reference_map(str(tmp_path))
        assert updated is not None
        g1 = next(r for r in updated.geometry_references if r.ref_id == "g1")
        assert g1.status == "needs_review"

    @pytest.mark.asyncio
    async def test_all_tools_claims_advanced_false(self, tmp_path: Path) -> None:
        mcp = self._make_mcp()
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps({"features": {}}))
        (tmp_path / "simulation").mkdir()
        import yaml
        (tmp_path / "simulation" / "setup.yaml").write_text(yaml.safe_dump({"boundary_conditions": []}))
        (tmp_path / "results").mkdir()

        for tool_name in ["aieng_get_reference_map", "aieng_build_reference_map"]:
            tool = mcp._tool_manager._tools[tool_name].fn
            response = await tool(package_path=str(tmp_path))
            assert response["claim_policy"]["claims_advanced"] is False, f"{tool_name} should not advance claims"

        # Test mark_references separately since it requires affected_feature_ids
        tool = mcp._tool_manager._tools["aieng_mark_references_needing_review"].fn
        response = await tool(package_path=str(tmp_path), affected_feature_ids=[])
        assert response["claim_policy"]["claims_advanced"] is False, "aieng_mark_references_needing_review should not advance claims"


# ---------------------------------------------------------------------------
# Demo script test
# ---------------------------------------------------------------------------

def test_demo_script_runs() -> None:
    """Verify the reference mapping demo script exits cleanly."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "run_reference_mapping_demo.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, f"Demo script failed:\n{result.stderr}"
    assert "Demo completed successfully" in result.stdout
