"""Tests for aieng.claim_proposal."""

from __future__ import annotations

from typing import Any

import pytest

from aieng.claim_proposal import (
    CLAIM_PROPOSAL_ARTIFACT_PREFIX,
    CLAIM_PROPOSAL_REVIEW_STATUSES,
    CLAIM_PROPOSAL_STATUSES,
    CLAIM_PROPOSAL_TOOL,
    build_claim_proposal,
    claim_proposal_path,
    validate_claim_proposal_artifact,
    validate_claim_proposal_request,
)

_VALID_KWARGS: dict[str, Any] = dict(
    claim_id="c1",
    proposed_status="supported",
    supporting_evidence=["results/computed_metrics.json"],
    rationale="The simulation confirms structural integrity.",
)

_VALID_PROPOSAL = build_claim_proposal(**_VALID_KWARGS)


# ── path helpers ─────────────────────────────────────────────────────────────

class TestClaimProposalPath:
    def test_path_format(self) -> None:
        assert claim_proposal_path("abc123") == "claims/proposals/abc123.json"

    def test_uses_prefix_constant(self) -> None:
        path = claim_proposal_path("x")
        assert path.startswith(CLAIM_PROPOSAL_ARTIFACT_PREFIX + "/")

    def test_ends_with_json(self) -> None:
        assert claim_proposal_path("myid").endswith(".json")


# ── build_claim_proposal ─────────────────────────────────────────────────────

class TestBuildClaimProposal:
    def test_required_fields_present(self) -> None:
        p = build_claim_proposal(**_VALID_KWARGS)
        for field in (
            "schema_version", "proposal_id", "claim_id", "proposed_status",
            "status", "supporting_evidence", "rationale", "created_at",
            "created_by_tool", "claim_advancement",
        ):
            assert field in p, f"missing field: {field!r}"

    def test_schema_version(self) -> None:
        assert build_claim_proposal(**_VALID_KWARGS)["schema_version"] == "0.1"

    def test_status_always_proposed(self) -> None:
        assert build_claim_proposal(**_VALID_KWARGS)["status"] == "proposed"

    def test_claim_advancement_always_none(self) -> None:
        assert build_claim_proposal(**_VALID_KWARGS)["claim_advancement"] == "none"

    def test_created_by_tool(self) -> None:
        assert build_claim_proposal(**_VALID_KWARGS)["created_by_tool"] == CLAIM_PROPOSAL_TOOL

    def test_fields_propagated(self) -> None:
        p = build_claim_proposal(**_VALID_KWARGS)
        assert p["claim_id"] == "c1"
        assert p["proposed_status"] == "supported"
        assert p["rationale"] == _VALID_KWARGS["rationale"]
        assert p["supporting_evidence"] == ["results/computed_metrics.json"]

    def test_proposal_id_auto_generated(self) -> None:
        p = build_claim_proposal(**_VALID_KWARGS)
        assert isinstance(p["proposal_id"], str)
        assert len(p["proposal_id"]) > 0

    def test_proposal_id_unique_each_call(self) -> None:
        a = build_claim_proposal(**_VALID_KWARGS)
        b = build_claim_proposal(**_VALID_KWARGS)
        assert a["proposal_id"] != b["proposal_id"]

    def test_custom_proposal_id(self) -> None:
        p = build_claim_proposal(**_VALID_KWARGS, proposal_id="fixed-id")
        assert p["proposal_id"] == "fixed-id"

    def test_custom_created_at(self) -> None:
        ts = "2026-01-01T00:00:00+00:00"
        p = build_claim_proposal(**_VALID_KWARGS, created_at=ts)
        assert p["created_at"] == ts

    def test_created_at_is_iso8601(self) -> None:
        p = build_claim_proposal(**_VALID_KWARGS)
        assert "T" in p["created_at"]

    def test_all_proposed_statuses_accepted(self) -> None:
        for status in CLAIM_PROPOSAL_STATUSES:
            p = build_claim_proposal(**{**_VALID_KWARGS, "proposed_status": status})
            assert p["proposed_status"] == status


# ── validate_claim_proposal_request ──────────────────────────────────────────

class TestValidateClaimProposalRequest:
    def test_valid_request_returns_empty(self) -> None:
        assert validate_claim_proposal_request(**_VALID_KWARGS) == []

    def test_empty_claim_id_error(self) -> None:
        errors = validate_claim_proposal_request(**{**_VALID_KWARGS, "claim_id": ""})
        assert any("claim_id" in e for e in errors)

    def test_empty_rationale_error(self) -> None:
        errors = validate_claim_proposal_request(**{**_VALID_KWARGS, "rationale": ""})
        assert any("rationale" in e for e in errors)

    def test_empty_supporting_evidence_error(self) -> None:
        errors = validate_claim_proposal_request(**{**_VALID_KWARGS, "supporting_evidence": []})
        assert any("supporting_evidence" in e for e in errors)

    def test_non_list_supporting_evidence_error(self) -> None:
        errors = validate_claim_proposal_request(
            **{**_VALID_KWARGS, "supporting_evidence": "not-a-list"}  # type: ignore[arg-type]
        )
        assert any("supporting_evidence" in e for e in errors)

    def test_invalid_proposed_status_error(self) -> None:
        errors = validate_claim_proposal_request(**{**_VALID_KWARGS, "proposed_status": "accepted"})
        assert any("proposed_status" in e for e in errors)

    def test_multiple_errors_returned(self) -> None:
        errors = validate_claim_proposal_request(
            claim_id="", proposed_status="bad",
            supporting_evidence=[], rationale="",
        )
        assert len(errors) >= 2

    def test_all_valid_statuses_accepted(self) -> None:
        for status in CLAIM_PROPOSAL_STATUSES:
            errors = validate_claim_proposal_request(**{**_VALID_KWARGS, "proposed_status": status})
            assert not any("proposed_status" in e for e in errors)


# ── validate_claim_proposal_artifact ─────────────────────────────────────────

class TestValidateClaimProposalArtifact:
    def test_valid_artifact_no_issues(self) -> None:
        assert validate_claim_proposal_artifact(_VALID_PROPOSAL) == []

    def test_missing_field_reported(self) -> None:
        bad = {k: v for k, v in _VALID_PROPOSAL.items() if k != "claim_id"}
        issues = validate_claim_proposal_artifact(bad)
        assert any("claim_id" in i for i in issues)

    def test_wrong_claim_advancement_reported(self) -> None:
        bad = {**_VALID_PROPOSAL, "claim_advancement": "accepted"}
        issues = validate_claim_proposal_artifact(bad)
        assert any("claim_advancement" in i for i in issues)

    def test_invalid_proposed_status_reported(self) -> None:
        bad = {**_VALID_PROPOSAL, "proposed_status": "validated"}
        issues = validate_claim_proposal_artifact(bad)
        assert any("proposed_status" in i for i in issues)

    def test_invalid_status_reported(self) -> None:
        bad = {**_VALID_PROPOSAL, "status": "accepted"}
        issues = validate_claim_proposal_artifact(bad)
        assert any("status" in i for i in issues)


# ── vocabulary constants ─────────────────────────────────────────────────────

class TestVocabularyConstants:
    def test_supported_in_statuses(self) -> None:
        assert "supported" in CLAIM_PROPOSAL_STATUSES

    def test_not_supported_in_statuses(self) -> None:
        assert "not_supported" in CLAIM_PROPOSAL_STATUSES

    def test_needs_review_in_statuses(self) -> None:
        assert "needs_review" in CLAIM_PROPOSAL_STATUSES

    def test_accepted_not_in_statuses(self) -> None:
        assert "accepted" not in CLAIM_PROPOSAL_STATUSES

    def test_validated_not_in_statuses(self) -> None:
        assert "validated" not in CLAIM_PROPOSAL_STATUSES

    def test_review_statuses_contains_proposed(self) -> None:
        assert "proposed" in CLAIM_PROPOSAL_REVIEW_STATUSES

    def test_review_statuses_contains_draft(self) -> None:
        assert "draft" in CLAIM_PROPOSAL_REVIEW_STATUSES

    def test_artifact_prefix_path(self) -> None:
        assert CLAIM_PROPOSAL_ARTIFACT_PREFIX == "claims/proposals"
