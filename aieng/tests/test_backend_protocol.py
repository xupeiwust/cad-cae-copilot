from __future__ import annotations

import pytest

from aieng.backend_adapter import BackendExecutionResult, StepExecutionResult
from aieng.backends.fake_backend import FakeBackend


class TestDataclassConstruction:
    def test_step_execution_result_defaults(self) -> None:
        res = StepExecutionResult(
            step_id="step_001",
            operation="create_box",
            status="success",
            inputs={},
            outputs={},
            artifacts_written=[],
            evidence={},
            trace={},
        )
        assert res.step_id == "step_001"
        assert res.warnings == []
        assert res.errors == []
        assert res.backend_metadata == {}

    def test_backend_execution_result_defaults(self) -> None:
        res = BackendExecutionResult(
            overall_status="success",
            plan_id="plan_001",
            backend_id="fake",
            transport_type="in_process",
        )
        assert res.steps == []
        assert res.artifacts == []
        assert res.exported_step_path is None
        assert res.evidence_entries == []
        assert res.trace_entries == []
        assert res.warnings == []
        assert res.errors == []

    def test_mutable_defaults_are_not_shared(self) -> None:
        """Frozen dataclasses with default_factory should produce independent lists."""
        r1 = BackendExecutionResult(
            overall_status="success",
            plan_id="p1",
            backend_id="fake",
            transport_type="in_process",
        )
        r2 = BackendExecutionResult(
            overall_status="success",
            plan_id="p2",
            backend_id="fake",
            transport_type="in_process",
        )
        r1.steps.append("x")  # type: ignore[arg-type]
        assert "x" not in r2.steps


class TestFakeBackendProtocolConformance:
    def test_has_required_attributes(self) -> None:
        assert hasattr(FakeBackend, "backend_id")
        assert hasattr(FakeBackend, "transport_type")
        assert hasattr(FakeBackend, "adapter_version")

    def test_has_required_methods(self) -> None:
        assert callable(getattr(FakeBackend, "validate_capabilities", None))
        assert callable(getattr(FakeBackend, "dry_run", None))
        assert callable(getattr(FakeBackend, "execute_plan", None))

    def test_status_semantics_docstring(self) -> None:
        doc = BackendExecutionResult.__doc__ or ""
        assert "success" in doc
        assert "partial" in doc
        assert "failed" in doc
