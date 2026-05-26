from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class StepExecutionResult:
    """Result of executing a single modeling step through a backend."""

    step_id: str
    operation: str
    status: str  # "success" | "failed" | "unsupported"
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    artifacts_written: list[str]
    evidence: dict[str, Any]
    trace: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    backend_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BackendExecutionResult:
    """Result of executing a full modeling plan through a backend.

    overall_status semantics:
      - "success": all modeling steps succeeded AND an artifact was exported.
      - "partial": at least one modeling step succeeded, but a later step
        failed or the final artifact export failed.
      - "failed": no modeling step succeeded, or the backend could not start.

    Backends write temporary artifacts to ``output_dir``. They do NOT write
    ``.aieng`` packages; assembly is the orchestrator's responsibility.
    """

    overall_status: str  # "success" | "partial" | "failed"
    plan_id: str
    backend_id: str
    transport_type: str
    kernel: str | None = None
    steps: list[StepExecutionResult] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    exported_step_path: str | None = None
    construction_history: dict[str, Any] = field(default_factory=dict)
    evidence_entries: list[dict[str, Any]] = field(default_factory=list)
    trace_entries: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BackendAdapter(Protocol):
    """Backend-agnostic adapter protocol.

    Implementations live in their own packages (e.g. aieng_freecad_mcp).
    The core ``aieng`` package defines only the protocol; it never imports
    concrete backends directly.
    """

    backend_id: str
    transport_type: str
    adapter_version: str

    def validate_capabilities(self, plan: dict[str, Any]) -> list[str]:
        """Return list of unsupported operations or missing capabilities.

        An empty list means the plan is fully supported.
        """
        ...

    def dry_run(self, plan: dict[str, Any], output_dir: Path) -> BackendExecutionResult:
        """Validate plan without executing geometry operations.

        Returns a ``BackendExecutionResult`` with status and diagnostic
        messages. No artifacts are written to ``output_dir``.
        """
        ...

    def execute_plan(self, plan: dict[str, Any], output_dir: Path) -> BackendExecutionResult:
        """Execute plan and produce geometry artifacts.

        Args:
            plan: Parsed modeling_plan JSON dict.
            output_dir: Temporary directory where the backend MAY write
                intermediate artifacts (STEP, images, logs). The caller
                owns cleanup of this directory.

        Returns:
            BackendExecutionResult containing step results, artifact paths,
            construction history, evidence/trace entries.
        """
        ...
