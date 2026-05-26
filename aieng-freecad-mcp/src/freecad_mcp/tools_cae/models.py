"""Pydantic request/response models for CAE MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from freecad_mcp.cae_core.schemas import (
    AnalysisSpec,
    BucklingAnalysisSpec,
    BucklingResultSummary,
    CadSpec,
    MassProperties,
    ModalAnalysisSpec,
    ModalResultSummary,
    ResultSummary,
    TaskSpec,
    ThermalAnalysisSpec,
    ThermalResultSummary,
)
from freecad_mcp.contracts import CADBuildResult
from freecad_mcp.contracts.failure_mode import (
    FailureDetail,
    FailureMode,
    _LEGACY_CODE_TO_CODE,
    map_failure_mode_to_error_code,
)
from freecad_mcp.contracts.operation_preview import OperationPreview
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, TraceBlock

CAE_MCP_SCHEMA_VERSION = "0.2.0"
"""Semver for the CAE MCP request/response schema."""


class CaeBaseResponse(BaseModel):
    """Base response carrying the standard mutating-tool result contract."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failed", "unsupported", "rejected"] = "success"
    operation: str = ""
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    artifacts_written: list[str] = []
    evidence: EvidenceBlock = Field(default_factory=EvidenceBlock)
    claim_policy: ClaimPolicy = Field(default_factory=ClaimPolicy)
    trace: TraceBlock = Field(default_factory=TraceBlock)
    preview: OperationPreview | None = None
    failure_mode: FailureDetail | None = None
    primary_error_code: str | None = None
    warnings: list[str] = []
    unsupported: list[str] = []
    errors: list[str] = []
    persistence: dict[str, Any] | None = None
    schema_version: str = CAE_MCP_SCHEMA_VERSION

    @model_validator(mode="after")
    def _derive_primary_error_code(self) -> "CaeBaseResponse":
        if self.primary_error_code is None and self.failure_mode is not None:
            self.primary_error_code = map_failure_mode_to_error_code(self.failure_mode)
        return self


class CaeErrorResponse(CaeBaseResponse):
    """Structured error returned by CAE tool calls on failure.

    Keeps ``error`` and ``error_code`` for backward compatibility while
    also exposing the standard result/claim/evidence/trace fields.
    """

    error: Literal[True] = True
    error_code: Literal[
        "unknown_tool",
        "validation_error",
        "backend_error",
        "internal_error",
    ]
    tool_name: str
    message: str
    detail: str | None = None
    status: Literal["failed", "unsupported", "rejected"] = "failed"

    @model_validator(mode="after")
    def _derive_primary_error_code_from_legacy(self) -> "CaeErrorResponse":
        if self.primary_error_code is None or self.primary_error_code == FailureMode.UNKNOWN:
            if self.error_code is not None:
                mapped = _LEGACY_CODE_TO_CODE.get(self.error_code, FailureMode.UNKNOWN)
                if mapped != FailureMode.UNKNOWN:
                    self.primary_error_code = mapped
        return self


class CaeBaseRequest(BaseModel):
    """Base request carrying optional .aieng context fields."""

    model_config = ConfigDict(extra="forbid")

    package_path: str | None = None
    persist_to_aieng: bool = False
    target_feature_id: str | None = None


class CaeCreateAnalysisRequest(CaeBaseRequest):
    run_dir: str
    task_spec: TaskSpec
    cad_spec: CadSpec
    stage: str = "cae_setup"


class CaeCreateAnalysisResponse(CaeBaseResponse):
    analysis_spec: AnalysisSpec


class CaeGenerateMeshRequest(CaeBaseRequest):
    run_dir: str
    cad_spec: CadSpec
    build_result: CADBuildResult
    analysis_spec: AnalysisSpec
    stage: str = "cae_setup"


class CaeGenerateMeshResponse(CaeBaseResponse):
    prepared_geometry: dict[str, Any]
    mesh_summary: dict[str, Any]
    material_assignment: dict[str, Any]
    boundary_conditions: dict[str, Any]


class CaeRunStaticAnalysisRequest(CaeBaseRequest):
    run_dir: str
    task_spec: TaskSpec
    cad_spec: CadSpec
    analysis_spec: AnalysisSpec
    mass_properties: MassProperties
    stage: str = "solve"


class CaeRunStaticAnalysisResponse(CaeBaseResponse):
    solver_output: dict[str, Any]


class CaeExtractResultsRequest(CaeBaseRequest):
    run_dir: str
    task_spec: TaskSpec
    analysis_spec: AnalysisSpec
    solver_output: dict[str, Any]
    stage: str = "result_check"


class CaeExtractResultsResponse(CaeBaseResponse):
    result_summary: ResultSummary


class CaeGenerateReportDataRequest(CaeBaseRequest):
    run_dir: str
    task_spec: TaskSpec
    cad_spec: CadSpec
    analysis_spec: AnalysisSpec
    mass_properties: MassProperties
    result_summary: ResultSummary
    stage: str = "report"


class CaeGenerateReportDataResponse(CaeBaseResponse):
    report_data: dict[str, Any]


class CaeInspectGeometryRequest(CaeBaseRequest):
    document_path: str
    object_name: str
    doc_name: str | None = None


class CaeInspectGeometryResponse(CaeBaseResponse):
    document_path: str
    object_name: str
    global_bbox: dict[str, float]
    faces: list[dict[str, Any]]
    suggested_fixed: list[str]
    suggested_load: list[str]
    notes: list[str]


class CaeRunThermalAnalysisRequest(CaeBaseRequest):
    run_dir: str
    thermal_spec: ThermalAnalysisSpec
    cad_spec: CadSpec | None = None
    stage: str = "solve"


class CaeRunThermalAnalysisResponse(CaeBaseResponse):
    result: ThermalResultSummary


class CaeRunModalAnalysisRequest(CaeBaseRequest):
    run_dir: str
    modal_spec: ModalAnalysisSpec
    cad_spec: CadSpec | None = None
    stage: str = "solve"


class CaeRunModalAnalysisResponse(CaeBaseResponse):
    result: ModalResultSummary


class CaeRunBucklingAnalysisRequest(CaeBaseRequest):
    run_dir: str
    buckling_spec: BucklingAnalysisSpec
    cad_spec: CadSpec | None = None
    stage: str = "solve"


class CaeRunBucklingAnalysisResponse(CaeBaseResponse):
    result: BucklingResultSummary
