"""Golden-shape tests for pure package semantics outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aieng.audit_event import build_audit_event
from aieng.claim_proposal import build_claim_proposal
from aieng.evidence_resolver import resolve_evidence_reference
from aieng.package_consistency import rollup_check_status, run_package_consistency_checks
from aieng.package_manifest import generate_artifact_manifest
from aieng.revalidation_status import record_geometry_edit_status, record_solver_validation_status
from aieng.review_readiness import build_review_readiness

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
FIXED_TIME = "2026-01-01T00:00:00+00:00"


def _load_golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def test_artifact_manifest_minimal_golden() -> None:
    generated = generate_artifact_manifest(
        ["manifest.json", "geometry/source.step", "results/computed_metrics.json"],
        revalidation_status={"requires_revalidation": False, "current_geometry_revision": 1},
        generated_at=FIXED_TIME,
    )
    assert generated == _load_golden("artifact_manifest.minimal.json")


def test_evidence_reference_field_summary_golden() -> None:
    evidence_entries = [
        {
            "id": "displacement_summary",
            "path": "results/fields/displacement.summary.json",
            "kind": "field",
            "role": "displacement_extrema",
            "exists": True,
            "supports": ["claim_proposal_review"],
        }
    ]
    generated = resolve_evidence_reference(
        path="results/fields/displacement.summary.json",
        package_paths=["results/fields/displacement.summary.json", "results/evidence_index.json"],
        evidence_entries=evidence_entries,
        revalidation_status={
            "requires_revalidation": False,
            "current_geometry_revision": 2,
            "last_validated_geometry_revision": 2,
        },
    )
    assert generated == _load_golden("evidence_reference.field_summary.json")


def test_revalidation_status_stale_golden() -> None:
    fresh = record_solver_validation_status(
        {"current_geometry_revision": 1},
        run_id="run_001",
        timestamp=FIXED_TIME,
    )
    generated = record_geometry_edit_status(
        fresh,
        affected_artifacts=["geometry/source.step"],
        timestamp="2026-01-01T00:10:00+00:00",
    )
    assert generated == _load_golden("revalidation_status.stale.json")


def test_claim_proposal_valid_golden() -> None:
    generated = build_claim_proposal(
        claim_id="claim_bracket_displacement_ok",
        proposed_status="supported",
        supporting_evidence=["results/fields/displacement.summary.json"],
        rationale="Displacement summary is present for human/agent review.",
        proposal_id="proposal-001",
        created_at=FIXED_TIME,
    )
    assert generated == _load_golden("claim_proposal.valid.json")


def test_review_readiness_ready_golden() -> None:
    generated = build_review_readiness(
        ev_paths=["results/fields/displacement.summary.json"],
        missing_count=0,
        stale_count=0,
        proposal_status="proposed",
        pkg_names={"results/fields/displacement.summary.json", "claims/proposals/proposal-001.json"},
    )
    assert generated == _load_golden("review_readiness.ready.json")


def test_audit_event_claim_proposal_created_golden() -> None:
    generated = build_audit_event(
        tool="claims.propose_update",
        event_type="claim_proposal_created",
        status="completed",
        artifacts_written=["claims/proposals/proposal-001.json"],
        evidence_created=[],
        state_changes={"claim_id": "claim_bracket_displacement_ok", "proposed_status": "supported"},
        geometry_revision=1,
        revalidation_status="fresh",
        event_id="event-001",
        timestamp=FIXED_TIME,
    )
    assert generated == _load_golden("audit_event.claim_proposal_created.json")


def test_package_consistency_ok_golden() -> None:
    proposal = build_claim_proposal(
        claim_id="claim_bracket_displacement_ok",
        proposed_status="supported",
        supporting_evidence=["results/fields/displacement.summary.json"],
        rationale="Displacement summary is present for human/agent review.",
        proposal_id="proposal-001",
        created_at=FIXED_TIME,
    )
    evidence_index = {
        "entries": [
            {"id": "displacement_summary", "path": "results/fields/displacement.summary.json", "exists": True}
        ]
    }
    package_paths = [
        "manifest.json",
        "results/evidence_index.json",
        "results/fields/displacement.summary.json",
        "claims/proposals/proposal-001.json",
    ]
    checks = run_package_consistency_checks(
        package_paths=package_paths,
        evidence_raw=json.dumps(evidence_index).encode("utf-8"),
        revalidation_status={"requires_revalidation": False, "current_geometry_revision": 1, "last_validated_geometry_revision": 1},
        claim_proposals=[("claims/proposals/proposal-001.json", json.dumps(proposal).encode("utf-8"))],
    )
    generated = {"rollup": rollup_check_status(checks), "checks": checks}
    assert generated == _load_golden("package_consistency.ok.json")
