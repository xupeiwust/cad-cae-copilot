"""Tests for the shared honesty / claim boundary constants."""

from __future__ import annotations

from app.honesty import (
    AGENT_OBSERVATION_CLAIM_BOUNDARY,
    CAD_OBSERVATION_CLAIM_BOUNDARY,
    CAD_PARAMETER_EDIT_CLAIM_BOUNDARY,
    INTENT_PLANNER_CLAIM_BOUNDARY,
)


def test_all_claim_boundaries_are_non_empty() -> None:
    constants = [
        INTENT_PLANNER_CLAIM_BOUNDARY,
        AGENT_OBSERVATION_CLAIM_BOUNDARY,
        CAD_OBSERVATION_CLAIM_BOUNDARY,
        CAD_PARAMETER_EDIT_CLAIM_BOUNDARY,
    ]
    for const in constants:
        assert isinstance(const, str)
        assert len(const) > 0
        assert "engineering claims" in const.lower()
