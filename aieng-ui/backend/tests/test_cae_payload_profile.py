"""Tests for cae_payload_profile — B4 simulation payload profiling."""
from __future__ import annotations

import json
import logging

import pytest

from app.cae_payload_profile import (
    COMPACT_TOKENS,
    WARN_TOKENS,
    compact_cae_block,
    estimate_tokens,
    profile_payload,
)


def _make_large_cae_block(
    *,
    materials: int = 0,
    loads: int = 0,
    boundary_conditions: int = 0,
    draft_size: int = 0,
) -> dict:
    """Build a CAE block with controllable list sizes and draft bloat."""
    block = {
        "present": True,
        "materials": [{"id": f"mat_{i}", "name": f"Material {i}"} for i in range(materials)],
        "loads": [{"id": f"load_{i}", "force": 100.0 + i} for i in range(loads)],
        "boundary_conditions": [{"id": f"bc_{i}", "type": "fixed"} for i in range(boundary_conditions)],
        "constraints_count": boundary_conditions,
        "materials_count": materials,
        "loads_count": loads,
        "boundary_conditions_count": boundary_conditions,
        "results_available": False,
        "available_fields": [],
        "solver_status": {},
        "mapping": None,
        "artifact_detection": {"status": "ok"},
        "preprocessing_summary": None,
        "simulation_run_summary": None,
        "result_summary": None,
        "fea_setup_draft": None,
        "template_fixture": None,
    }
    if draft_size:
        block["fea_setup_draft"] = {
            "analysis_type": "linear_static",
            "nodes": [{"id": i, "x": i, "y": i, "z": i} for i in range(draft_size)],
        }
    return block


class TestEstimateTokens:
    def test_empty_dict_is_one_token(self) -> None:
        assert estimate_tokens({}) == 1

    def test_simple_dict_estimate(self) -> None:
        data = {"key": "value"}
        expected = max(1, len(json.dumps(data)) // 4)
        assert estimate_tokens(data) == expected

    def test_nested_structure_estimate(self) -> None:
        data = {"a": [1, 2, 3], "b": {"c": "hello"}}
        expected = max(1, len(json.dumps(data)) // 4)
        assert estimate_tokens(data) == expected


class TestProfilePayload:
    def test_profiles_small_payload(self) -> None:
        data = {"status": "ok"}
        profile = profile_payload(data, label="test")
        assert profile["label"] == "test"
        assert profile["bytes"] > 0
        assert profile["estimated_tokens"] >= 1

    def test_warns_when_threshold_exceeded(self, caplog: pytest.LogCaptureFixture) -> None:
        # Create a payload large enough to trigger the warning.
        data = {"items": [{"id": i, "text": "x" * 100} for i in range(200)]}
        logger = logging.getLogger("app.cae_payload_profile")
        logger.addHandler(caplog.handler)
        try:
            with caplog.at_level("WARNING", logger="app.cae_payload_profile"):
                profile = profile_payload(data, label="large_test")
        finally:
            logger.removeHandler(caplog.handler)
        assert profile["estimated_tokens"] >= WARN_TOKENS
        assert "large_test" in caplog.text
        assert "bytes" in caplog.text

    def test_no_warning_below_threshold(self, caplog: pytest.LogCaptureFixture) -> None:
        data = {"status": "ok"}
        with caplog.at_level("WARNING", logger="app.cae_payload_profile"):
            profile_payload(data, label="small_test")
        assert "small_test" not in caplog.text


class TestCompactCaeBlock:
    def test_small_block_unchanged(self) -> None:
        block = _make_large_cae_block(materials=2)
        result = compact_cae_block(block)
        assert result == block
        assert "_payload_profile" not in result

    def test_compacts_draft_when_over_threshold(self) -> None:
        # A block with a large draft should exceed COMPACT_TOKENS.
        block = _make_large_cae_block(draft_size=2000)
        assert estimate_tokens(block) > COMPACT_TOKENS
        result = compact_cae_block(block, label="test_draft")
        assert "_payload_profile" in result
        assert result["fea_setup_draft"]["_compacted"] is True
        assert result["fea_setup_draft"]["reason"] == "payload_size"
        assert estimate_tokens(result) <= COMPACT_TOKENS

    def test_compacts_fixture_when_over_threshold(self) -> None:
        block = _make_large_cae_block(materials=0)
        block["template_fixture"] = {
            "geometry": [{"id": i, "data": "y" * 200} for i in range(2000)],
        }
        assert estimate_tokens(block) > COMPACT_TOKENS
        result = compact_cae_block(block)
        assert result["template_fixture"]["_compacted"] is True

    def test_truncates_long_lists(self) -> None:
        # Many list items alone can push the block over the limit.
        block = _make_large_cae_block(materials=500, loads=500, boundary_conditions=500)
        assert estimate_tokens(block) > COMPACT_TOKENS
        result = compact_cae_block(block)
        assert "_payload_profile" in result
        # Lists should be truncated.
        assert any(item.get("_truncated") for item in result["materials"])
        assert any(item.get("_truncated") for item in result["loads"])
        assert any(item.get("_truncated") for item in result["boundary_conditions"])
        # Original counts preserved in the truncation marker.
        truncated = [i for i in result["materials"] if i.get("_truncated")]
        assert truncated[0]["original_count"] == 500

    def test_respects_custom_max_tokens(self) -> None:
        block = _make_large_cae_block(materials=100)
        # Use a very high threshold so no compaction occurs.
        result = compact_cae_block(block, max_tokens=100_000)
        assert result == block

    def test_profile_includes_original_and_post_compaction_tokens(self) -> None:
        block = _make_large_cae_block(draft_size=2000)
        result = compact_cae_block(block, label="profile_test")
        profile = result["_payload_profile"]
        assert profile["label"] == "profile_test"
        assert profile["compacted"] is True
        assert "post_compaction_tokens" in profile
        assert profile["post_compaction_tokens"] <= COMPACT_TOKENS
