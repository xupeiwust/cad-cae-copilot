"""Claim proposal artifact semantics for .aieng packages.

Pure functions with no I/O. Owns the artifact schema, path conventions,
status vocabulary, and construction/validation logic for claim proposals.
Does not accept or reject claims, does not create claim maps, and has no
knowledge of ZIP files or HTTP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "CLAIM_PROPOSAL_STATUSES",
    "CLAIM_PROPOSAL_REVIEW_STATUSES",
    "CLAIM_PROPOSAL_ARTIFACT_PREFIX",
    "CLAIM_PROPOSAL_TOOL",
    "claim_proposal_path",
    "build_claim_proposal",
    "validate_claim_proposal_request",
    "validate_claim_proposal_artifact",
]

# ── vocabulary ───────────────────────────────────────────────────────────────

# Allowed values for the proposed_status field.
CLAIM_PROPOSAL_STATUSES: frozenset[str] = frozenset({
    "supported", "not_supported", "needs_review",
})

# Allowed values for the artifact-level status field (lifecycle state).
CLAIM_PROPOSAL_REVIEW_STATUSES: frozenset[str] = frozenset({
    "proposed", "draft",
})

# Directory prefix inside the .aieng ZIP where proposals are stored.
CLAIM_PROPOSAL_ARTIFACT_PREFIX: str = "claims/proposals"

# Producer tool recorded in every proposal artifact.
CLAIM_PROPOSAL_TOOL: str = "claims.propose_update"

# Required fields in a serialised claim proposal artifact.
_REQUIRED_ARTIFACT_FIELDS: tuple[str, ...] = (
    "schema_version", "proposal_id", "claim_id", "proposed_status",
    "status", "supporting_evidence", "rationale", "created_at",
    "created_by_tool", "claim_advancement",
)


# ── path helpers ─────────────────────────────────────────────────────────────

def claim_proposal_path(proposal_id: str) -> str:
    """Return the package-internal path for a proposal artifact.

    Example: ``claim_proposal_path("abc123") == "claims/proposals/abc123.json"``
    """
    return f"{CLAIM_PROPOSAL_ARTIFACT_PREFIX}/{proposal_id}.json"


# ── artifact builder ─────────────────────────────────────────────────────────

def build_claim_proposal(
    *,
    claim_id: str,
    proposed_status: str,
    supporting_evidence: list[str],
    rationale: str,
    proposal_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a claim proposal artifact dict ready for writing into the package.

    ``status`` is always ``"proposed"``. ``claim_advancement`` is always
    ``"none"``. Does not create or modify ``ai/claim_map.json`` or
    ``results/claim_map.json``.

    Args:
        claim_id: The engineering claim this proposal targets.
        proposed_status: One of the values in :data:`CLAIM_PROPOSAL_STATUSES`.
        supporting_evidence: Package-internal paths that support the proposal.
        rationale: Human-readable justification for the proposed update.
        proposal_id: Optional fixed ID; auto-generated (16-hex) when absent.
        created_at: Optional ISO 8601 timestamp; defaults to current UTC time.

    Returns:
        A dict with all required artifact fields.
    """
    return {
        "schema_version": "0.1",
        "proposal_id": proposal_id or uuid.uuid4().hex[:16],
        "claim_id": claim_id,
        "proposed_status": proposed_status,
        "status": "proposed",
        "supporting_evidence": supporting_evidence,
        "rationale": rationale,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "created_by_tool": CLAIM_PROPOSAL_TOOL,
        "claim_advancement": "none",
    }


# ── validation ───────────────────────────────────────────────────────────────

def validate_claim_proposal_request(
    *,
    claim_id: str,
    proposed_status: str,
    supporting_evidence: list[str],
    rationale: str,
) -> list[str]:
    """Validate a claim proposal request against the core artifact vocabulary.

    Checks only pure semantic rules — does not verify whether evidence paths
    exist in a specific package (that is the caller's responsibility).

    Args:
        claim_id: Must be a non-empty string.
        proposed_status: Must be in :data:`CLAIM_PROPOSAL_STATUSES`.
        supporting_evidence: Must be a non-empty list.
        rationale: Must be a non-empty string.

    Returns:
        List of human-readable error strings; empty list means the request
        is valid. The order of errors matches the order of checks.
    """
    errors: list[str] = []
    if not claim_id:
        errors.append("claim_id must be non-empty")
    if not rationale:
        errors.append("rationale must be non-empty")
    if not isinstance(supporting_evidence, list) or not supporting_evidence:
        errors.append(
            "supporting_evidence must be a non-empty list of package artifact paths"
        )
    if proposed_status not in CLAIM_PROPOSAL_STATUSES:
        errors.append(
            f"proposed_status must be one of {sorted(CLAIM_PROPOSAL_STATUSES)}"
        )
    return errors


def validate_claim_proposal_artifact(obj: dict[str, Any]) -> list[str]:
    """Validate a deserialised claim proposal artifact against the core schema.

    Args:
        obj: A dict loaded from a ``claims/proposals/*.json`` artifact.

    Returns:
        List of issue strings describing schema violations; empty = valid.
    """
    issues: list[str] = []
    for field in _REQUIRED_ARTIFACT_FIELDS:
        if field not in obj:
            issues.append(f"missing required field: {field!r}")
    if obj.get("claim_advancement") != "none":
        issues.append("claim_advancement must be 'none'")
    if obj.get("status") not in CLAIM_PROPOSAL_REVIEW_STATUSES:
        issues.append(
            f"status must be one of {sorted(CLAIM_PROPOSAL_REVIEW_STATUSES)!r}"
        )
    if "proposed_status" in obj and obj["proposed_status"] not in CLAIM_PROPOSAL_STATUSES:
        issues.append(
            f"proposed_status must be one of {sorted(CLAIM_PROPOSAL_STATUSES)}"
        )
    return issues
