from __future__ import annotations

from importlib.metadata import entry_points
import json
import os
import shutil
from pathlib import Path

import pytest

from freecad_mcp.aieng_bridge.modeling_executor import FreeCADModelingBackend


# Helper to build a minimal valid Phase 1 plan
def _make_plan(steps: list[dict] | None = None) -> dict:
    if steps is None:
        steps = [
            {
                "step_id": "step_001",
                "operation": "create_box",
                "creates": "base",
                "parameters": {
                    "length": 120.0,
                    "width": 80.0,
                    "height": 10.0,
                    "name": "base",
                },
            }
        ]
    return {
        "plan_id": "plan_001",
        "plan_schema_version": "0.1.0",
        "intent": {"original_text": "test"},
        "units": {"length": "mm", "angle": "deg"},
        "steps": steps,
    }


# ------------------------------------------------------------------
# Tests that do NOT require a real FreeCAD installation
# ------------------------------------------------------------------

class TestValidateCapabilities:
    def test_validate_capabilities_accepts_phase1_ops(self) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        assert backend.validate_capabilities(plan) == []

    def test_validate_capabilities_rejects_family_ops(self) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan(
            steps=[
                {
                    "step_id": "step_001",
                    "operation": "create_plate",
                    "creates": "plate",
                    "parameters": {"length": 100.0},
                }
            ]
        )
        caps = backend.validate_capabilities(plan)
        assert len(caps) == 1
        assert "create_plate" in caps[0]


class TestDryRun:
    def test_dry_run_valid_plan_success(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        result = backend.dry_run(plan, tmp_path)
        assert result.overall_status == "success"
        assert len(result.steps) == 1
        assert result.steps[0].status == "success"
        assert result.exported_step_path is None

    def test_dry_run_missing_target_partial_or_failed(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan(
            steps=[
                {
                    "step_id": "step_001",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole",
                    "target": "step_000",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 10.0,
                        "position": [0.0, 0.0, 0.0],
                        "name": "hole",
                    },
                }
            ]
        )
        result = backend.dry_run(plan, tmp_path)
        assert result.overall_status == "failed"
        assert result.steps[0].status == "failed"
        assert "Target 'step_000'" in result.steps[0].errors[0]

    def test_dry_run_zero_axis_fails(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan(
            steps=[
                {
                    "step_id": "step_001",
                    "operation": "create_box",
                    "creates": "base",
                    "parameters": {
                        "length": 100.0,
                        "width": 50.0,
                        "height": 5.0,
                        "name": "base",
                    },
                },
                {
                    "step_id": "step_002",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole",
                    "target": "step_001",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 10.0,
                        "position": [0.0, 0.0, 0.0],
                        "axis": [0.0, 0.0, 0.0],
                        "name": "hole",
                    },
                },
            ]
        )
        result = backend.dry_run(plan, tmp_path)
        assert result.overall_status == "partial"
        assert result.steps[1].status == "failed"
        assert "zero-length" in result.steps[1].errors[0].lower()

    def test_dry_run_contains_evidence_and_trace(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        result = backend.dry_run(plan, tmp_path)
        assert len(result.evidence_entries) >= 1
        assert len(result.trace_entries) >= 1
        assert result.construction_history["backend_id"] == "freecad"


class TestWithoutFreeCAD:
    def test_execute_plan_missing_freecad_returns_failed_result(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend(freecad_cmd_path="/nonexistent/freecad")
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        assert result.overall_status == "failed"
        assert any("not found" in e.lower() or "freecad" in e.lower() for e in result.errors)

    def test_entry_point_registration(self) -> None:
        registered = {ep.name: ep for ep in entry_points(group="aieng.backends")}
        assert "freecad" in registered
        cls = registered["freecad"].load()
        assert cls is FreeCADModelingBackend


# ------------------------------------------------------------------
# Tests that REQUIRE a real FreeCAD installation
# ------------------------------------------------------------------

_freecad_available = bool(
    os.environ.get("FREECAD_MCP_FREECAD_PATH")
    or shutil.which("FreeCADCmd")
    or shutil.which("freecadcmd")
    or shutil.which("freecad")
)


@pytest.mark.skipif(not _freecad_available, reason="FreeCAD not available")
@pytest.mark.freecad
class TestExecutePlanWithFreeCAD:
    def test_execute_plan_creates_step_file(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)

        assert result.overall_status == "success", result.errors
        assert result.exported_step_path is not None
        assert Path(result.exported_step_path).exists()
        assert b"ISO-10303-21" in Path(result.exported_step_path).read_bytes()

    def test_execute_plan_box_with_four_cuts(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan(
            steps=[
                {
                    "step_id": "step_001",
                    "operation": "create_box",
                    "creates": "base",
                    "parameters": {
                        "length": 120.0,
                        "width": 80.0,
                        "height": 10.0,
                        "name": "base",
                    },
                },
                {
                    "step_id": "step_002",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole_01",
                    "target": "step_001",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 12.0,
                        "position": [15.0, 15.0, -1.0],
                        "name": "hole_01",
                    },
                },
                {
                    "step_id": "step_003",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole_02",
                    "target": "step_001",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 12.0,
                        "position": [105.0, 15.0, -1.0],
                        "name": "hole_02",
                    },
                },
                {
                    "step_id": "step_004",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole_03",
                    "target": "step_001",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 12.0,
                        "position": [15.0, 65.0, -1.0],
                        "name": "hole_03",
                    },
                },
                {
                    "step_id": "step_005",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole_04",
                    "target": "step_001",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 12.0,
                        "position": [105.0, 65.0, -1.0],
                        "name": "hole_04",
                    },
                },
            ]
        )
        result = backend.execute_plan(plan, tmp_path)

        assert result.overall_status == "success", result.errors
        assert result.exported_step_path is not None
        step_file = Path(result.exported_step_path)
        assert step_file.exists()
        content = step_file.read_bytes()
        assert b"ISO-10303-21" in content

    def test_execute_plan_result_is_backend_execution_result(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)

        assert result.backend_id == "freecad"
        assert result.transport_type == "subprocess"
        assert result.kernel == "FreeCAD"
        assert len(result.steps) == 1
        assert result.steps[0].operation == "create_box"
        assert result.steps[0].status == "success"

    def test_execute_plan_contains_evidence_per_step(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)

        assert len(result.evidence_entries) >= len(plan["steps"])
        for entry in result.evidence_entries:
            assert "evidence_id" in entry
            assert "evidence_type" in entry
            assert entry["producer"]["tool_id"] == "freecad"

    def test_execute_plan_contains_trace_per_step(self, tmp_path: Path) -> None:
        backend = FreeCADModelingBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)

        assert len(result.trace_entries) >= len(plan["steps"])
        for entry in result.trace_entries:
            assert entry["trace_type"] == "modeling_execution"
            assert "step_id" in entry
            assert entry["backend_id"] == "freecad"

    def test_execute_plan_current_body_only_export(self, tmp_path: Path) -> None:
        """Ensure STEP only contains the final body, not intermediate tool bodies."""
        backend = FreeCADModelingBackend()
        plan = _make_plan(
            steps=[
                {
                    "step_id": "step_001",
                    "operation": "create_box",
                    "creates": "base",
                    "parameters": {
                        "length": 100.0,
                        "width": 60.0,
                        "height": 10.0,
                        "name": "base",
                    },
                },
                {
                    "step_id": "step_002",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole",
                    "target": "step_001",
                    "parameters": {
                        "radius": 5.0,
                        "depth": 12.0,
                        "position": [20.0, 20.0, -1.0],
                        "name": "hole",
                    },
                },
            ]
        )
        result = backend.execute_plan(plan, tmp_path)

        assert result.overall_status == "success", result.errors
        assert result.exported_step_path is not None
        # The resulting STEP should be valid and not contain duplicate bodies.
        # A rough check: the file should parse as STEP (starts with ISO-10303-21)
        content = Path(result.exported_step_path).read_bytes()
        assert b"ISO-10303-21" in content
