"""Tests for aieng.support_packet."""

from __future__ import annotations

from typing import Any

from aieng.support_packet import build_claim_support_packet


def _proposal() -> dict[str, Any]:
    return {
        "proposal_id": "proposal-001",
        "claim_id": "claim_bracket_displacement_ok",
        "proposed_status": "supported",
        "status": "proposed",
        "rationale": "Displacement summary is present for review.",
        "supporting_evidence": ["results/fields/displacement.summary.json"],
        "claim_advancement": "none",
    }


def _review_readiness(status: str = "ready") -> dict[str, Any]:
    return {"status": status, "checks": [], "claim_advancement": "none"}


def test_build_claim_support_packet_shape() -> None:
    resolved = [{
        "path": "results/fields/displacement.summary.json",
        "warnings": [],
        "usable_for_claim_proposal": True,
        "claim_advancement": "none",
    }]
    packet = build_claim_support_packet(
        proposal=_proposal(),
        proposal_path="claims/proposals/proposal-001.json",
        resolved_supporting_evidence=resolved,
        related_audit_events=[{"event_id": "event-001"}],
        review_readiness=_review_readiness(),
    )

    assert packet["schema_version"] == "0.1"
    assert packet["proposal_id"] == "proposal-001"
    assert packet["supporting_evidence"] == resolved
    assert packet["related_audit_events"] == [{"event_id": "event-001"}]
    assert packet["review_readiness"]["status"] == "ready"
    assert packet["claim_advancement"] == "none"


def test_build_claim_support_packet_counts_stale_and_missing_evidence() -> None:
    resolved = [
        {
            "path": "results/fields/displacement.summary.json",
            "warnings": ["evidence_from_stale_geometry_state"],
            "usable_for_claim_proposal": True,
        },
        {
            "path": "missing.json",
            "warnings": ["path_not_found_in_package_or_evidence_index"],
            "usable_for_claim_proposal": False,
        },
    ]
    packet = build_claim_support_packet(
        proposal=_proposal(),
        proposal_path="claims/proposals/proposal-001.json",
        resolved_supporting_evidence=resolved,
        related_audit_events=[],
        review_readiness=_review_readiness("warning"),
    )

    assert packet["stale_evidence_count"] == 1
    assert packet["missing_evidence_count"] == 1
    assert packet["evidence_warnings"] == [
        "evidence_from_stale_geometry_state",
        "path_not_found_in_package_or_evidence_index",
    ]


def test_build_claim_support_packet_does_not_advance_claims() -> None:
    packet = build_claim_support_packet(
        proposal={**_proposal(), "claim_advancement": "accepted"},
        proposal_path="claims/proposals/proposal-001.json",
        resolved_supporting_evidence=[],
        related_audit_events=[],
        review_readiness=_review_readiness(),
    )

    assert packet["claim_advancement"] == "none"
