"""OperationPreview model for dry-run and mutation preview across all tools.

Every mutating tool should be able to produce an OperationPreview that tells
the caller what would happen without actually doing it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OperationPreview(BaseModel):
    """Preview of what an operation would do before execution.

    This must be a true dry-run structure: no files may be written while
    building this preview.
    """

    model_config = ConfigDict(extra="forbid")

    operation_name: str
    would_write_artifacts: list[str] = Field(default_factory=list)
    would_update_evidence: bool = False
    would_update_traces: bool = False
    would_touch_claims: bool = False
    guard_checks_required: list[str] = Field(default_factory=list)
    unavailable_runtime_blocks: list[str] = Field(default_factory=list)
    expected_duration_estimate: str = "unknown"
    warnings: list[str] = Field(default_factory=list)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return super().model_dump(**kwargs)
