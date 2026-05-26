from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.external_adapters import AdapterExecutionResult, AdapterPreflightResult, ExternalToolCapability, registry_stub


def test_capability_manifest_validates_safe_read_only_tool() -> None:
    cap = ExternalToolCapability(
        id="cad.inspect_features",
        label="Inspect CAD features",
        category="cad",
        input_artifacts=["geometry/source.FCStd"],
        output_artifacts=["graph/feature_graph.json"],
        claim_advancement="none",
    )
    assert cap.requires_approval is False
    assert cap.claim_advancement == "none"


def test_expensive_capability_must_require_approval() -> None:
    with pytest.raises(ValidationError):
        ExternalToolCapability(
            id="solver.run_ccx",
            label="Run CalculiX",
            category="solver",
            runs_external_process=True,
            expensive=True,
            requires_approval=False,
        )


def test_claim_advancement_can_only_be_none() -> None:
    with pytest.raises(ValidationError):
        ExternalToolCapability(
            id="report.bad_claim",
            label="Bad claim writer",
            category="report",
            claim_advancement="accepted",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        AdapterExecutionResult(ok=True, status="completed", claim_advancement="accepted")  # type: ignore[arg-type]


def test_execution_result_cannot_imply_claim_advancement_or_hide_errors() -> None:
    result = AdapterExecutionResult(
        ok=True,
        status="completed",
        changed_artifacts=["results/computed_metrics.json"],
        evidence_written=["results/computed_metrics.json"],
        claim_advancement="none",
    )
    assert result.claim_advancement == "none"
    with pytest.raises(ValidationError):
        AdapterExecutionResult(ok=True, status="error", errors=["impossible"])
    with pytest.raises(ValidationError):
        AdapterExecutionResult(ok=False, status="error", errors=[])


def test_registry_stub_is_empty_non_executing_placeholder() -> None:
    assert registry_stub() == []

