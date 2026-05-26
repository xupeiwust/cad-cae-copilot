"""Shared honesty / claim boundary constants.

Every module that produces reviewable output should use one of these constants
so the claim-boundary wording is centralized, auditable, and easy to keep
consistent across the backend.
"""

from __future__ import annotations

INTENT_PLANNER_CLAIM_BOUNDARY = (
    "Intent Planner output is a reviewable preview only. The planner does "
    "not execute CAD/mesh/solver tools, does not certify the design, and "
    "does not advance engineering claims. Mutating actions remain "
    "approval-gated through the existing runtime."
)

AGENT_OBSERVATION_CLAIM_BOUNDARY = (
    "Agent Observation Loop output is a reviewable summary of one action only. "
    "It does not certify the design, does not run CAD/mesh/solver tools, and "
    "does not advance engineering claims. Stale and unknown states are "
    "reported honestly."
)

CAD_OBSERVATION_CLAIM_BOUNDARY = (
    "CAD observation is a structural read of existing package state. "
    "It does not certify that CAD geometry is valid, watertight, "
    "meshable, or simulation-ready. Metadata-only artifacts cannot "
    "back physical claims; only real exported geometry or a live CAD "
    "snapshot can. AIENG does not advance engineering claims here."
)

CAD_PARAMETER_EDIT_CLAIM_BOUNDARY = (
    "This approved CAD parameter edit records a geometry mutation only. "
    "It does not run mesh/solver workflows, does not certify the design, "
    "and does not advance engineering claims."
)
