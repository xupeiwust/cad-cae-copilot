"""Tests for stable blocked reason code metadata."""

from __future__ import annotations

from app import blocked_reason_codes as codes


def test_details_for_codes_preserves_order_and_deduplicates() -> None:
    details = codes.details_for_codes([
        codes.MISSING_MESH,
        codes.SOLVER_UNAVAILABLE,
        codes.MISSING_MESH,
    ])

    assert [item["code"] for item in details] == [codes.MISSING_MESH, codes.SOLVER_UNAVAILABLE]
    assert details[0]["label"] == "Missing mesh"
    assert "mesh" in details[0]["recommended_action"].lower()


def test_detail_for_unknown_code_is_still_actionable() -> None:
    detail = codes.detail_for_code("custom_adapter_blocker")

    assert detail["code"] == "custom_adapter_blocker"
    assert detail["label"] == "Custom adapter blocker"
    assert detail["recommended_action"]
