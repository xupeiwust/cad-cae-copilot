"""Tests for aieng.review_readiness."""

from __future__ import annotations

from typing import Any

import pytest

from aieng.review_readiness import build_review_readiness

_EV_PATH = "results/computed_metrics.json"
_PKG = {_EV_PATH}

_EXPECTED_CHECK_IDS = {
    "supporting_evidence_present",
    "no_missing_evidence",
    "stale_evidence",
    "proposal_status_reviewable",
    "claim_map_not_advanced",
}


# ── contract helper ──────────────────────────────────────────────────────────

def _assert_contract(obj: dict[str, Any]) -> None:
    for field in ("status", "checks", "claim_advancement"):
        assert field in obj, f"review_readiness missing field: {field!r}"
    assert obj["status"] in {"ready", "warning", "blocked"}
    assert obj["claim_advancement"] == "none"
    assert isinstance(obj["checks"], list) and len(obj["checks"]) > 0
    for check in obj["checks"]:
        assert "id" in check
        assert check.get("status") in {"ok", "warning", "blocked"}
        assert "message" in check


# ── readiness status ─────────────────────────────────────────────────────────

class TestReadinessStatus:
    def test_ready_for_fresh_valid_proposal(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=_PKG,
        )
        assert rr["status"] == "ready"

    def test_draft_status_also_ready(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="draft", pkg_names=_PKG,
        )
        assert rr["status"] == "ready"

    def test_stale_evidence_warning(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=1,
            proposal_status="proposed", pkg_names=_PKG,
        )
        assert rr["status"] == "warning"

    def test_unknown_proposal_status_warning(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="accepted", pkg_names=_PKG,
        )
        assert rr["status"] == "warning"

    def test_claim_map_present_warning(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed",
            pkg_names=_PKG | {"ai/claim_map.json"},
        )
        assert rr["status"] == "warning"

    def test_missing_evidence_blocked(self) -> None:
        rr = build_review_readiness(
            ev_paths=["missing/artifact.json"], missing_count=1, stale_count=0,
            proposal_status="proposed", pkg_names=set(),
        )
        assert rr["status"] == "blocked"

    def test_empty_evidence_list_blocked(self) -> None:
        rr = build_review_readiness(
            ev_paths=[], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=set(),
        )
        assert rr["status"] == "blocked"

    def test_blocked_beats_warning(self) -> None:
        rr = build_review_readiness(
            ev_paths=["missing/artifact.json"], missing_count=1, stale_count=1,
            proposal_status="proposed", pkg_names=set(),
        )
        assert rr["status"] == "blocked"


# ── individual check results ─────────────────────────────────────────────────

class TestIndividualChecks:
    def _get_check(self, rr: dict[str, Any], check_id: str) -> dict[str, Any]:
        return next(c for c in rr["checks"] if c["id"] == check_id)

    def test_supporting_evidence_present_ok(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=_PKG,
        )
        assert self._get_check(rr, "supporting_evidence_present")["status"] == "ok"

    def test_supporting_evidence_present_blocked_when_empty(self) -> None:
        rr = build_review_readiness(
            ev_paths=[], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=set(),
        )
        assert self._get_check(rr, "supporting_evidence_present")["status"] == "blocked"

    def test_no_missing_evidence_blocked(self) -> None:
        rr = build_review_readiness(
            ev_paths=["missing.json"], missing_count=1, stale_count=0,
            proposal_status="proposed", pkg_names=set(),
        )
        assert self._get_check(rr, "no_missing_evidence")["status"] == "blocked"

    def test_stale_evidence_check_warning(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=2,
            proposal_status="proposed", pkg_names=_PKG,
        )
        check = self._get_check(rr, "stale_evidence")
        assert check["status"] == "warning"
        assert check["details"]["stale_count"] == 2

    def test_proposal_status_warning_for_unexpected(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="rejected", pkg_names=_PKG,
        )
        assert self._get_check(rr, "proposal_status_reviewable")["status"] == "warning"

    def test_claim_map_not_advanced_warning_when_map_present(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed",
            pkg_names=_PKG | {"results/claim_map.json"},
        )
        assert self._get_check(rr, "claim_map_not_advanced")["status"] == "warning"


# ── contract and structure ───────────────────────────────────────────────────

class TestContractAndStructure:
    def test_all_five_check_ids_always_present(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=_PKG,
        )
        assert {c["id"] for c in rr["checks"]} == _EXPECTED_CHECK_IDS

    def test_claim_advancement_none(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=_PKG,
        )
        assert rr["claim_advancement"] == "none"

    def test_contract_valid_in_all_cases(self) -> None:
        cases = [
            ([], 0, 0, "proposed", set()),
            ([_EV_PATH], 0, 1, "draft", _PKG),
            ([_EV_PATH], 1, 0, "proposed", set()),
            ([_EV_PATH], 0, 0, "accepted", _PKG),
            ([_EV_PATH], 0, 0, "proposed", _PKG | {"ai/claim_map.json"}),
        ]
        for ev_paths, missing, stale, status, pkg in cases:
            rr = build_review_readiness(
                ev_paths=ev_paths, missing_count=missing, stale_count=stale,
                proposal_status=status, pkg_names=pkg,
            )
            _assert_contract(rr)

    def test_five_checks_emitted_exactly(self) -> None:
        rr = build_review_readiness(
            ev_paths=[_EV_PATH], missing_count=0, stale_count=0,
            proposal_status="proposed", pkg_names=_PKG,
        )
        assert len(rr["checks"]) == 5
