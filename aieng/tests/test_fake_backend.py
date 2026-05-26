from __future__ import annotations

import json
from pathlib import Path

import pytest

from aieng.backends.fake_backend import FakeBackend
from aieng.modeling_plan.validate import validate_modeling_plan


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


class TestValidateCapabilities:
    def test_valid_plan_returns_empty(self) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        assert backend.validate_capabilities(plan) == []

    def test_unsupported_operation_returns_message(self) -> None:
        backend = FakeBackend()
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
    def test_does_not_write_artifact(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.dry_run(plan, tmp_path)
        assert result.overall_status == "success"
        assert not any(Path(p).exists() for p in result.artifacts)

    def test_generates_step_results(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.dry_run(plan, tmp_path)
        assert len(result.steps) == 1
        assert result.steps[0].status == "success"


class TestExecutePlan:
    def test_writes_fake_step_artifact(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        assert result.overall_status == "success"
        assert result.exported_step_path is not None
        assert Path(result.exported_step_path).exists()

    def test_each_step_has_evidence_entry(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        assert len(result.evidence_entries) >= len(plan["steps"])
        for entry in result.evidence_entries:
            assert "evidence_id" in entry
            assert "evidence_type" in entry
            assert entry["producer"]["kind"] == "backend_adapter"
            assert entry["producer"]["tool_id"] == "fake"

    def test_each_step_has_trace_entry(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        assert len(result.trace_entries) >= len(plan["steps"])
        for entry in result.trace_entries:
            assert entry["trace_type"] == "modeling_execution"
            assert "step_id" in entry
            assert "backend_id" in entry

    def test_construction_history_has_backend_metadata(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        hist = result.construction_history
        assert hist["backend_id"] == "fake"
        assert hist["transport_type"] == "in_process"
        assert hist["kernel"] == "fake"
        for step in hist["steps"]:
            assert "backend_metadata" in step
            assert step["backend_metadata"]["backend_id"] == "fake"

    def test_result_is_json_serializable(self, tmp_path: Path) -> None:
        backend = FakeBackend()
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        # Verify we can round-trip through JSON
        raw = json.dumps(result.construction_history, default=str)
        assert json.loads(raw) == result.construction_history


class TestFailureScenarios:
    def test_fail_at_step_id_produces_partial(self, tmp_path: Path) -> None:
        backend = FakeBackend(fail_at_step_id="step_002")
        plan = _make_plan(
            steps=[
                {
                    "step_id": "step_001",
                    "operation": "create_box",
                    "creates": "base",
                    "parameters": {"length": 120.0, "width": 80.0, "height": 10.0, "name": "base"},
                },
                {
                    "step_id": "step_002",
                    "operation": "create_cylindrical_cut",
                    "creates": "hole",
                    "target": "step_001",
                    "parameters": {"radius": 5.0, "depth": 12.0, "position": [10.0, 10.0, 0.0], "name": "hole"},
                },
            ]
        )
        result = backend.execute_plan(plan, tmp_path)
        assert result.overall_status == "partial"
        assert result.steps[0].status == "success"
        assert result.steps[1].status == "failed"
        assert any("Artificial failure" in e for e in result.steps[1].errors)

    def test_fail_export_produces_partial(self, tmp_path: Path) -> None:
        backend = FakeBackend(fail_export=True)
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        assert result.overall_status == "partial"
        assert result.exported_step_path is None

    def test_unsupported_operation_produces_failed(self, tmp_path: Path) -> None:
        backend = FakeBackend()
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
        result = backend.execute_plan(plan, tmp_path)
        assert result.overall_status == "failed"
        assert result.steps[0].status == "unsupported"

    def test_failed_step_evidence_is_validation_report(self, tmp_path: Path) -> None:
        backend = FakeBackend(fail_at_step_id="step_001")
        plan = _make_plan()
        result = backend.execute_plan(plan, tmp_path)
        entry = result.evidence_entries[0]
        assert entry["evidence_type"] == "validation_report"
        assert entry["verification"]["status"] == "missing"
