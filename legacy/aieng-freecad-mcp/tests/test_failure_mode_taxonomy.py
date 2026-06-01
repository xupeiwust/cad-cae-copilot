"""Tests for unified failure mode taxonomy."""

from __future__ import annotations

import pytest

from freecad_mcp.contracts.failure_mode import (
    FAILURE_MODE_DESCRIPTIONS,
    AMBIGUOUS,
    EXECUTION_FAILED,
    EXPORT_FAILED,
    INVALID_INPUT,
    MESH_FAILED,
    MISSING_ARTIFACT,
    MISSING_RUNTIME,
    NOT_FOUND,
    NEEDS_REVIEW,
    POLICY_VIOLATION,
    SOLVER_UNAVAILABLE,
    FailureDetail,
    FailureMode,
    classify_exception,
    derive_primary_error_code,
    map_failure_mode_to_error_code,
)
from freecad_mcp.tool_contracts import StandardToolResult
from freecad_mcp.tools_cad.models import CadToolResponse
from freecad_mcp.tools_cae.models import CaeBaseResponse


class TestFailureModeConstants:
    def test_known_modes_have_descriptions(self) -> None:
        for mode in [
            FailureMode.MISSING_INPUT,
            FailureMode.MISSING_ARTIFACT,
            FailureMode.MISSING_RUNTIME,
            FailureMode.SOLVER_UNAVAILABLE,
            FailureMode.MESH_FAILED,
            FailureMode.GUARD_REJECTED,
            FailureMode.SEMANTIC_ONLY_REJECTED,
            FailureMode.PROTECTED_REGION_VIOLATED,
            FailureMode.RECOMPUTE_FAILED,
            FailureMode.EXPORT_FAILED,
            FailureMode.NOT_FOUND,
            FailureMode.AMBIGUOUS,
            FailureMode.NEEDS_REVIEW,
            FailureMode.UNKNOWN,
        ]:
            assert mode in FAILURE_MODE_DESCRIPTIONS, f"Missing description for {mode}"


class TestClassifyException:
    def test_value_error_not_found(self) -> None:
        detail = classify_exception(ValueError("Object not found: Foo"))
        assert detail.mode == FailureMode.MISSING_ARTIFACT

    def test_value_error_missing_input(self) -> None:
        detail = classify_exception(ValueError("Missing required field"))
        assert detail.mode == FailureMode.MISSING_INPUT

    def test_value_error_guard(self) -> None:
        detail = classify_exception(ValueError("Guard rejected: protected region"))
        assert detail.mode == FailureMode.GUARD_REJECTED

    def test_file_not_found(self) -> None:
        detail = classify_exception(FileNotFoundError("/tmp/missing.step"))
        assert detail.mode == FailureMode.MISSING_ARTIFACT

    def test_recompute_failed(self) -> None:
        detail = classify_exception(RuntimeError("Document recompute failed"))
        assert detail.mode == FailureMode.RECOMPUTE_FAILED

    def test_export_failed(self) -> None:
        detail = classify_exception(RuntimeError("STEP export failed"))
        assert detail.mode == FailureMode.EXPORT_FAILED

    def test_mesh_failed(self) -> None:
        detail = classify_exception(RuntimeError("Mesh generation failed"))
        assert detail.mode == FailureMode.MESH_FAILED

    def test_solver_unavailable(self) -> None:
        detail = classify_exception(RuntimeError("Solver not available"))
        assert detail.mode == FailureMode.SOLVER_UNAVAILABLE

    def test_unknown_fallback(self) -> None:
        detail = classify_exception(Exception("Something weird happened"))
        assert detail.mode == FailureMode.UNKNOWN
        assert "Something weird happened" in detail.message

    def test_context_is_empty_by_default(self) -> None:
        detail = classify_exception(ValueError("test"))
        assert detail.context == {}


class TestFailureDetailModel:
    def test_construction_and_serialization(self) -> None:
        detail = FailureDetail(
            mode=FailureMode.GUARD_REJECTED,
            message="Guard said no",
            context={"feature_id": "f123"},
        )
        dumped = detail.model_dump(mode="json")
        assert dumped["mode"] == "guard_rejected"
        assert dumped["message"] == "Guard said no"
        assert dumped["context"] == {"feature_id": "f123"}

    def test_defaults(self) -> None:
        detail = FailureDetail()
        assert detail.mode == FailureMode.UNKNOWN
        assert detail.message == ""


class TestStandardToolResultWithFailureMode:
    def test_accepts_failure_mode(self) -> None:
        detail = FailureDetail(mode=FailureMode.MISSING_INPUT, message="bad input")
        result = StandardToolResult(
            status="rejected",
            operation="test",
            failure_mode=detail,
        )
        dumped = result.model_dump(mode="json")
        assert dumped["failure_mode"]["mode"] == "missing_input"

    def test_failure_mode_none(self) -> None:
        result = StandardToolResult(status="success", operation="test")
        dumped = result.model_dump(mode="json")
        assert dumped["failure_mode"] is None


class TestCadResponseWithFailureMode:
    def test_cad_response_failure_mode(self) -> None:
        detail = FailureDetail(mode=FailureMode.EXPORT_FAILED, message="export bad")
        resp = CadToolResponse(
            status="failed",
            operation="cad_export_step",
            failure_mode=detail,
        )
        dumped = resp.model_dump(mode="json")
        assert dumped["failure_mode"]["mode"] == "export_failed"


class TestCaeResponseWithFailureMode:
    def test_cae_response_failure_mode(self) -> None:
        detail = FailureDetail(mode=FailureMode.MESH_FAILED, message="mesh bad")
        resp = CaeBaseResponse(
            status="failed",
            operation="cae_generate_mesh",
            failure_mode=detail,
        )
        dumped = resp.model_dump(mode="json")
        assert dumped["failure_mode"]["mode"] == "mesh_failed"


class TestMapFailureModeToErrorCode:
    def test_all_known_modes_map_correctly(self) -> None:
        assert map_failure_mode_to_error_code(FailureMode.MISSING_INPUT) == INVALID_INPUT
        assert map_failure_mode_to_error_code(FailureMode.MISSING_ARTIFACT) == MISSING_ARTIFACT
        assert map_failure_mode_to_error_code(FailureMode.MISSING_RUNTIME) == MISSING_RUNTIME
        assert map_failure_mode_to_error_code(FailureMode.SOLVER_UNAVAILABLE) == SOLVER_UNAVAILABLE
        assert map_failure_mode_to_error_code(FailureMode.MESH_FAILED) == MESH_FAILED
        assert map_failure_mode_to_error_code(FailureMode.GUARD_REJECTED) == POLICY_VIOLATION
        assert map_failure_mode_to_error_code(FailureMode.SEMANTIC_ONLY_REJECTED) == POLICY_VIOLATION
        assert map_failure_mode_to_error_code(FailureMode.PROTECTED_REGION_VIOLATED) == POLICY_VIOLATION
        assert map_failure_mode_to_error_code(FailureMode.RECOMPUTE_FAILED) == EXECUTION_FAILED
        assert map_failure_mode_to_error_code(FailureMode.EXPORT_FAILED) == EXPORT_FAILED
        assert map_failure_mode_to_error_code(FailureMode.NOT_FOUND) == NOT_FOUND
        assert map_failure_mode_to_error_code(FailureMode.AMBIGUOUS) == AMBIGUOUS
        assert map_failure_mode_to_error_code(FailureMode.NEEDS_REVIEW) == NEEDS_REVIEW
        assert map_failure_mode_to_error_code(FailureMode.UNKNOWN) == FailureMode.UNKNOWN

    def test_failure_detail_object(self) -> None:
        detail = FailureDetail(mode=FailureMode.GUARD_REJECTED, message="guard")
        assert map_failure_mode_to_error_code(detail) == POLICY_VIOLATION

    def test_none_returns_none(self) -> None:
        assert map_failure_mode_to_error_code(None) is None

    def test_unknown_mode_fallback(self) -> None:
        assert map_failure_mode_to_error_code("totally_new_mode") == FailureMode.UNKNOWN


class TestDerivePrimaryErrorCode:
    def test_priority_primary_error_code(self) -> None:
        assert derive_primary_error_code(
            primary_error_code="EXPLICIT_CODE",
            failure_mode=FailureMode.MISSING_INPUT,
            legacy_error_code="validation_error",
        ) == "EXPLICIT_CODE"

    def test_priority_failure_mode_when_primary_missing(self) -> None:
        assert derive_primary_error_code(
            failure_mode=FailureMode.MISSING_INPUT,
            legacy_error_code="validation_error",
        ) == INVALID_INPUT

    def test_priority_legacy_when_others_missing(self) -> None:
        assert derive_primary_error_code(
            legacy_error_code="validation_error",
        ) == INVALID_INPUT
        assert derive_primary_error_code(
            legacy_error_code="PERSISTENCE_FAILED",
        ) == "PERSISTENCE_FAILED"

    def test_all_none_returns_none(self) -> None:
        assert derive_primary_error_code() is None

    def test_unknown_legacy_fallback(self) -> None:
        assert derive_primary_error_code(legacy_error_code="totally_new_code") == FailureMode.UNKNOWN

    def test_unknown_failure_mode_returns_lowercase_unknown(self) -> None:
        """Unknown failure_mode must return 'unknown' to stay consistent with docs."""
        assert derive_primary_error_code(failure_mode=FailureMode.UNKNOWN) == "unknown"
        assert derive_primary_error_code(failure_mode=FailureDetail(mode=FailureMode.UNKNOWN, message="?")) == "unknown"

    def test_consumer_priority_strategy_with_real_values(self) -> None:
        """End-to-end priority chain using exact values produced by the system.

        Ensures the strategy does not break when codes come from different
        sources with different casing conventions (UPPER_SNAKE vs lowercase).
        """
        # Scenario A: claim update rejection (primary_error_code already set)
        assert derive_primary_error_code(primary_error_code="MISSING_EVIDENCE_IDS") == "MISSING_EVIDENCE_IDS"

        # Scenario B: CAD tool failure (failure_mode -> mapped code)
        detail = FailureDetail(mode=FailureMode.EXPORT_FAILED, message="export bad")
        assert derive_primary_error_code(failure_mode=detail) == "EXPORT_FAILED"

        # Scenario C: CAE persistence failure (legacy error_code)
        assert derive_primary_error_code(legacy_error_code="PERSISTENCE_FAILED") == "PERSISTENCE_FAILED"

        # Scenario D: CAE internal error where failure_mode is unknown but legacy code is present.
        # derive_primary_error_code follows strict priority: failure_mode beats legacy_error_code.
        # The CaeErrorResponse model handles the override when failure_mode maps to "unknown".
        assert derive_primary_error_code(
            failure_mode=FailureDetail(mode=FailureMode.UNKNOWN, message="..."),
            legacy_error_code="internal_error",
        ) == "unknown"

        # Scenario E: fully unknown legacy code falls back to "unknown"
        assert derive_primary_error_code(legacy_error_code="brand_new_code") == "unknown"

        # Scenario F: all empty -> None
        assert derive_primary_error_code() is None


class TestAutoDerivationOnModels:
    def test_standard_tool_result_derives_from_failure_mode(self) -> None:
        detail = FailureDetail(mode=FailureMode.MISSING_INPUT, message="bad")
        result = StandardToolResult(status="rejected", operation="test", failure_mode=detail)
        assert result.primary_error_code == INVALID_INPUT
        dumped = result.model_dump(mode="json")
        assert dumped["primary_error_code"] == INVALID_INPUT

    def test_standard_tool_result_preserves_explicit_code(self) -> None:
        detail = FailureDetail(mode=FailureMode.MISSING_INPUT, message="bad")
        result = StandardToolResult(
            status="rejected",
            operation="test",
            failure_mode=detail,
            primary_error_code="CUSTOM_CODE",
        )
        assert result.primary_error_code == "CUSTOM_CODE"

    def test_cad_tool_response_derives_from_failure_mode(self) -> None:
        detail = FailureDetail(mode=FailureMode.EXPORT_FAILED, message="export bad")
        resp = CadToolResponse(status="failed", operation="cad_export_step", failure_mode=detail)
        assert resp.primary_error_code == EXPORT_FAILED
        dumped = resp.model_dump(mode="json")
        assert dumped["primary_error_code"] == EXPORT_FAILED

    def test_cae_base_response_derives_from_failure_mode(self) -> None:
        detail = FailureDetail(mode=FailureMode.MESH_FAILED, message="mesh bad")
        resp = CaeBaseResponse(status="failed", operation="cae_generate_mesh", failure_mode=detail)
        assert resp.primary_error_code == MESH_FAILED

    def test_cae_error_response_derives_from_failure_mode(self) -> None:
        from freecad_mcp.tools_cae.models import CaeErrorResponse
        detail = FailureDetail(mode=FailureMode.GUARD_REJECTED, message="guard")
        resp = CaeErrorResponse(
            status="rejected",
            operation="cae_run_static",
            error_code="validation_error",
            tool_name="cae_run_static",
            message="guard rejected",
            failure_mode=detail,
        )
        assert resp.primary_error_code == POLICY_VIOLATION

    def test_cae_error_response_fallback_from_legacy_error_code(self) -> None:
        from freecad_mcp.tools_cae.models import CaeErrorResponse
        detail = FailureDetail(mode=FailureMode.UNKNOWN, message="something weird")
        resp = CaeErrorResponse(
            status="failed",
            operation="cae_run_static",
            error_code="internal_error",
            tool_name="cae_run_static",
            message="internal error",
            failure_mode=detail,
        )
        assert resp.primary_error_code == "INTERNAL_ERROR"

    def test_no_failure_mode_means_no_primary_error_code(self) -> None:
        result = StandardToolResult(status="success", operation="test")
        assert result.primary_error_code is None
