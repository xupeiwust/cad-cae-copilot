"""Pydantic models for CAD MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from freecad_mcp.contracts.failure_mode import FailureDetail, map_failure_mode_to_error_code
from freecad_mcp.contracts.operation_preview import OperationPreview
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, TraceBlock


class CadBaseRequest(BaseModel):
    """Base request carrying optional .aieng context fields."""

    model_config = ConfigDict(extra="forbid")

    package_path: str | None = None
    persist_to_aieng: bool = False
    target_feature_id: str | None = None


class CadToolResponse(BaseModel):
    """CAD tool response with StandardToolResult-compatible fields.

    Uses ``extra="allow"`` so original FreeCAD result fields can be
    merged in at the top level for backward compatibility.
    """

    model_config = ConfigDict(extra="allow")

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

    @model_validator(mode="after")
    def _derive_primary_error_code(self) -> "CadToolResponse":
        if self.primary_error_code is None and self.failure_mode is not None:
            self.primary_error_code = map_failure_mode_to_error_code(self.failure_mode)
        return self
