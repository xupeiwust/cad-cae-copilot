"""Claim support packet assembly semantics for .aieng packages.

Pure functions with no I/O. The caller supplies an already-built claim
proposal, already-resolved supporting evidence, already-filtered related audit
events, and already-built review readiness. This module only assembles the
stable support-packet object and never resolves evidence, reads ZIPs, mutates
artifacts, or advances claims.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "build_claim_support_packet",
]


def build_claim_support_packet(
    *,
    proposal: dict[str, Any],
    proposal_path: str,
    resolved_supporting_evidence: list[dict[str, Any]],
    related_audit_events: list[dict[str, Any]],
    review_readiness: dict[str, Any],
) -> dict[str, Any]:
    """Assemble a stable claim support packet object.

    Args:
        proposal: Deserialised claim proposal artifact.
        proposal_path: Package-internal path to the proposal artifact.
        resolved_supporting_evidence: Evidence references already resolved by
            :func:`aieng.evidence_resolver.resolve_evidence_reference`.
        related_audit_events: Already-filtered audit events related to the
            proposal.
        review_readiness: Already-built readiness rollup from
            :func:`aieng.review_readiness.build_review_readiness`.

    Returns:
        Stable support-packet dict with evidence warning counts and
        ``claim_advancement: "none"``. Proposal is not acceptance; this helper
        never creates claim maps or advances engineering claims.
    """
    all_warnings: list[str] = [
        warning
        for ref in resolved_supporting_evidence
        for warning in ref.get("warnings", [])
    ]
    stale_count = sum(
        1
        for ref in resolved_supporting_evidence
        if "evidence_from_stale_geometry_state" in ref.get("warnings", [])
    )
    missing_count = sum(
        1 for ref in resolved_supporting_evidence if not ref.get("usable_for_claim_proposal")
    )

    return {
        "schema_version": "0.1",
        "proposal_id": proposal.get("proposal_id"),
        "proposal_path": proposal_path,
        "claim_id": proposal.get("claim_id"),
        "proposed_status": proposal.get("proposed_status"),
        "proposal_status": proposal.get("status"),
        "rationale": proposal.get("rationale"),
        "supporting_evidence": resolved_supporting_evidence,
        "evidence_warnings": all_warnings,
        "stale_evidence_count": stale_count,
        "missing_evidence_count": missing_count,
        "related_audit_events": related_audit_events,
        "review_readiness": review_readiness,
        "claim_advancement": "none",
    }
