"""Safety contract models for external CAD/CAE adapters.

This module is intentionally non-executing. It defines the manifest, preflight,
and execution-result shapes that future Gmsh/CalculiX/OpenFOAM wrappers
must satisfy before they are wired into AIENG runtime tools.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AdapterCategory = Literal["cad", "mesh", "solver", "postprocess", "report"]
ClaimAdvancement = Literal["none"]


class ExternalToolCapability(BaseModel):
    """Static capability manifest for a single external adapter operation."""

    id: str
    label: str
    category: AdapterCategory
    mutates_package: bool = False
    mutates_external_model: bool = False
    runs_external_process: bool = False
    expensive: bool = False
    requires_approval: bool = False
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    stale_artifacts_on_success: list[str] = Field(default_factory=list)
    claim_advancement: ClaimAdvancement = "none"

    @field_validator("id")
    @classmethod
    def _id_must_be_namespaced(cls, value: str) -> str:
        if "." not in value:
            raise ValueError("capability id must be namespaced, e.g. cad.inspect")
        return value

    @model_validator(mode="after")
    def _approval_and_stale_rules(self) -> "ExternalToolCapability":
        mutates = bool(self.mutates_package or self.mutates_external_model)
        runs_external = bool(self.runs_external_process)
        expensive = bool(self.expensive)
        category = self.category
        requires_approval = bool(self.requires_approval)
        stale_artifacts = self.stale_artifacts_on_success or []

        if (mutates or expensive or category == "solver" or (category == "mesh" and runs_external)) and not requires_approval:
            raise ValueError("mutating, expensive, mesh-external, and solver capabilities must require approval")
        if category == "cad" and mutates and not stale_artifacts:
            raise ValueError("CAD mutations must declare stale artifacts on success")
        return self


class AdapterPreflightResult(BaseModel):
    """Read-only adapter readiness response before any execution."""

    ok: bool
    status: Literal["ready", "partial", "not_ready", "unavailable"]
    missing_dependencies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    estimated_outputs: list[str] = Field(default_factory=list)
    requires_approval: bool = False

    @model_validator(mode="after")
    def _unavailable_must_be_honest(self) -> "AdapterPreflightResult":
        if self.status == "unavailable" and not self.missing_dependencies:
            raise ValueError("unavailable preflight must name missing dependencies")
        if self.status == "ready" and self.missing_dependencies:
            raise ValueError("ready preflight must not list missing dependencies")
        return self


class AdapterExecutionResult(BaseModel):
    """Adapter execution outcome after an approval-gated operation."""

    ok: bool
    status: Literal["completed", "skipped", "partial", "error"]
    changed_artifacts: list[str] = Field(default_factory=list)
    stale_artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    evidence_written: list[str] = Field(default_factory=list)
    claim_advancement: ClaimAdvancement = "none"

    @model_validator(mode="after")
    def _status_consistency(self) -> "AdapterExecutionResult":
        if self.ok and self.status == "error":
            raise ValueError("ok execution result cannot have error status")
        if self.status == "error" and not self.errors:
            raise ValueError("error execution result must include errors")
        return self


def registry_stub() -> list[ExternalToolCapability]:
    """Return an empty registry placeholder.

    Future work should populate this only with adapters that have preflight,
    approval, evidence writeback, stale propagation, and claim-boundary tests.
    """

    return []
