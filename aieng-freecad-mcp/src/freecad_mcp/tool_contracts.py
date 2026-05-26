"""Standard execution result contract for all mutating/execution tools.

All mutating tools must return a superset of these fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from freecad_mcp.contracts.failure_mode import FailureDetail, map_failure_mode_to_error_code
from freecad_mcp.contracts.operation_preview import OperationPreview


class EvidenceBlock(BaseModel):
    """Evidence metadata linking execution output to .aieng evidence index."""

    model_config = ConfigDict(extra="forbid")

    evidence_ids: list[str] = []
    evidence_type: str | None = None
    producer_kind: Literal["surrogate", "freecad", "freecad_fem", "calculix", "external"] | None = None
    claim_ids_possibly_supported: list[str] = []


class ClaimPolicy(BaseModel):
    """Claim policy that must accompany every mutating tool result."""

    model_config = ConfigDict(extra="forbid")

    claims_advanced: bool = False
    requires_explicit_update_claim: bool = True


class TraceBlock(BaseModel):
    """Provenance trace metadata for .aieng tool_trace.json."""

    model_config = ConfigDict(extra="forbid")

    tool_trace_id: str | None = None
    producer: str = "freecad_mcp"
    exit_status: int | None = None


class StandardToolResult(BaseModel):
    """Standard mutating/execution result shape.

    Defaults enforce the non-negotiable boundary rule:
    - claims_advanced defaults to False
    - requires_explicit_update_claim defaults to True
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failed", "unsupported", "rejected"]
    operation: str
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

    @model_validator(mode="after")
    def _derive_primary_error_code(self) -> "StandardToolResult":
        if self.primary_error_code is None and self.failure_mode is not None:
            self.primary_error_code = map_failure_mode_to_error_code(self.failure_mode)
        return self
