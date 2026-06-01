from __future__ import annotations

import json
from typing import Any

import pytest

from app.agent_autopilot.context_memory import (
    ContextMemoryManager,
    MemoryLayerConfig,
    ObservationImportance,
)
from app.agent_autopilot.schema import AutopilotObservation


def _obs(kind: str, summary: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": kind, "summary": summary, "data": data or {}}


def _tool_obs(tool_name: str, summary: str, output: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": "tool_result",
        "summary": summary,
        "data": {
            "tool_name": tool_name,
            "input": {},
            "output": output or {},
        },
    }


# -- ObservationImportance --


def test_importance_user_message_is_critical() -> None:
    imp = ObservationImportance.from_observation(_obs("user_message", "make it bigger"))
    assert imp.level == "critical"
    assert "user_intent" in imp.tags


def test_importance_tool_error_is_high() -> None:
    imp = ObservationImportance.from_observation(_obs("tool_error", "something broke"))
    assert imp.level == "high"


def test_importance_agent_activity_is_low() -> None:
    imp = ObservationImportance.from_observation(_obs("agent_activity", "Invoking adapter"))
    assert imp.level == "low"


def test_importance_cad_execute_is_high() -> None:
    imp = ObservationImportance.from_observation(
        _tool_obs("cad.execute_build123d", "built bracket")
    )
    assert imp.level == "high"
    assert "cad" in imp.tags


# -- ContextMemoryManager basic lifecycle --


def test_manager_tracks_all_observations() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    assert mgr.seen_count == 0

    mgr.add_observation(_obs("user_message", "hello"))
    assert mgr.seen_count == 1

    mgr.add_observations([_obs("agent_activity", "step 1"), _obs("agent_activity", "step 2")])
    assert mgr.seen_count == 3


def test_add_observations_batch_same_as_individual() -> None:
    system = {"tools": []}
    mgr_batch = ContextMemoryManager(system_content=system)
    mgr_batch.add_observations(
        [
            _obs("user_message", "A"),
            _obs("agent_activity", "B"),
            _tool_obs("cad.execute_build123d", "C", {"named_parts": ["p1"]}),
        ]
    )

    mgr_ind = ContextMemoryManager(system_content=system)
    for obs in [
        _obs("user_message", "A"),
        _obs("agent_activity", "B"),
        _tool_obs("cad.execute_build123d", "C", {"named_parts": ["p1"]}),
    ]:
        mgr_ind.add_observation(obs)

    assert mgr_batch.seen_count == mgr_ind.seen_count
    assert mgr_batch.get_memory_stats()["working_count"] == mgr_ind.get_memory_stats()["working_count"]


# -- Working layer compression --


def test_working_layer_respects_count_limit() -> None:
    config = MemoryLayerConfig(working_max_count=3)
    mgr = ContextMemoryManager(system_content={"tools": []}, config=config)

    for i in range(5):
        mgr.add_observation(_obs("agent_activity", f"step {i}"))

    stats = mgr.get_memory_stats()
    # After adding 5 low-importance observations with max_count=3,
    # the oldest 2 should have been compressed to archive.
    assert stats["working_count"] <= 3
    assert stats["total_seen"] == 5
    assert stats["compressed_count"] >= 2


def test_critical_observations_preserved_longer() -> None:
    config = MemoryLayerConfig(working_max_count=3)
    mgr = ContextMemoryManager(system_content={"tools": []}, config=config)

    # Mix of critical and low observations
    mgr.add_observation(_obs("agent_activity", "step 0"))  # low
    mgr.add_observation(_obs("user_message", "constraint A"))  # critical
    mgr.add_observation(_obs("agent_activity", "step 1"))  # low
    mgr.add_observation(_obs("agent_activity", "step 2"))  # low
    mgr.add_observation(_obs("agent_activity", "step 3"))  # low

    working = mgr._build_working_layer_payload()
    kinds = [w["kind"] for w in working]
    # The critical user_message should still be in working layer
    assert "user_message" in kinds


def test_working_layer_respects_token_limit() -> None:
    config = MemoryLayerConfig(working_max_count=10, working_max_tokens=50)
    mgr = ContextMemoryManager(system_content={"tools": []}, config=config)

    # Add a single huge observation that exceeds the token budget
    huge_summary = "x" * 5000
    mgr.add_observation(_obs("agent_activity", huge_summary))

    stats = mgr.get_memory_stats()
    # The observation should have been truncated in place rather than removed
    assert stats["working_count"] >= 1
    assert stats["working_tokens"] <= 50


# -- Archive layer --


def test_archive_chain_stays_within_budget() -> None:
    config = MemoryLayerConfig(working_max_count=2, archive_max_tokens=10)
    mgr = ContextMemoryManager(system_content={"tools": []}, config=config)

    for i in range(20):
        mgr.add_observation(_obs("agent_activity", f"very long description of step {i} with lots of extra text"))

    stats = mgr.get_memory_stats()
    assert stats["archive_tokens"] <= 10
    # Archive should have been folded, not grown unbounded
    assert stats["compressed_count"] == 18  # 20 - 2 working


def test_reset_working_memory_clears_working_not_archive() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})

    mgr.add_observations([
        _obs("user_message", "first"),
        _obs("agent_activity", "step 1"),
        _obs("agent_activity", "step 2"),
    ])

    before_stats = mgr.get_memory_stats()
    assert before_stats["working_count"] > 0

    mgr.reset_working_memory()

    after_stats = mgr.get_memory_stats()
    assert after_stats["working_count"] == 0
    assert after_stats["archive_tokens"] > 0  # archive preserved
    assert after_stats["total_seen"] == before_stats["total_seen"]


# -- Prompt building --


def test_full_prompt_includes_all_layers() -> None:
    mgr = ContextMemoryManager(
        system_content={"rules": ["rule1"], "tools": [{"name": "t1"}]},
    )
    mgr.add_observation(_obs("user_message", "do something"))
    mgr.add_observation(_tool_obs("cad.execute_build123d", "done", {"named_parts": ["body"]}))

    prompt = mgr.build_full_prompt(objective="build a bracket")
    payload = json.loads(prompt)

    assert payload["objective"] == "build a bracket"
    assert "system_context" in payload
    assert "archive_digest" in payload
    assert "working_memory" in payload
    assert len(payload["working_memory"]) > 0


def test_full_prompt_includes_optional_fields() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    prompt = mgr.build_full_prompt(
        objective="test",
        project_id="proj_001",
        selected_geometry={"faces": ["f1"]},
        agent_context={"brief": "hello"},
    )
    payload = json.loads(prompt)
    assert payload["active_project_id"] == "proj_001"
    assert payload["selected_geometry"] == {"faces": ["f1"]}
    assert payload["agent_context"] == {"brief": "hello"}


def test_incremental_prompt_only_has_new_obs() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    mgr.add_observations([
        _obs("user_message", "first"),
        _obs("agent_activity", "step 1"),
    ])

    prompt = mgr.build_incremental_prompt(
        objective="continue",
        new_observation=_obs("tool_result", "result arrived"),
    )
    payload = json.loads(prompt)

    assert payload["objective"] == "continue"
    assert "new_observation" in payload
    assert "system_context" not in payload
    assert "working_memory" not in payload


def test_incremental_prompt_without_new_observation() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    prompt = mgr.build_incremental_prompt(objective="continue")
    payload = json.loads(prompt)
    assert "new_observation" not in payload
    assert "instruction" in payload


# -- Memory stats --


def test_memory_stats_accurate() -> None:
    mgr = ContextMemoryManager(
        system_content={"rules": ["r" * 100]},
        config=MemoryLayerConfig(working_max_count=5),
    )
    mgr.add_observations([_obs("agent_activity", f"step {i}") for i in range(10)])

    stats = mgr.get_memory_stats()
    assert stats["total_seen"] == 10
    assert stats["working_count"] <= 5
    assert stats["compressed_count"] == 10 - stats["working_count"]
    assert 0.0 <= stats["compression_ratio"] <= 1.0


# -- Domain-aware compaction --


def test_compact_agent_context_output() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    obs = _tool_obs(
        "aieng.agent_context",
        "loaded context",
        output={
            "schema_version": "1.0",
            "project_id": "p1",
            "project": {"name": "Test"},
            "cad": {"status": "ready", "topology_references": {"feature_count": 42}},
            "brep_graph": {"face_count": 12},
        },
    )
    mgr.add_observation(obs)

    working = mgr._build_working_layer_payload()
    assert len(working) == 1
    data = working[0].get("data", {})
    assert data.get("feature_count") == 42
    assert data.get("face_count") == 12


def test_compact_critique_output() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    obs = _tool_obs(
        "cad.critique",
        "critique done",
        output={
            "verdict": "needs_work",
            "findings": [{"severity": "high"}, {"severity": "medium"}, {"severity": "low"}],
            "fail_first_objections": ["obj1", "obj2", "obj3", "obj4"],
        },
    )
    mgr.add_observation(obs)

    working = mgr._build_working_layer_payload()
    data = working[0].get("data", {})
    assert data.get("verdict") == "needs_work"
    assert data.get("finding_count") == 3


# -- Edge cases --


def test_empty_manager_builds_valid_prompts() -> None:
    mgr = ContextMemoryManager(system_content={"tools": []})
    full = json.loads(mgr.build_full_prompt("test"))
    assert full["archive_digest"] == "No prior history."
    assert full["working_memory"] == []

    inc = json.loads(mgr.build_incremental_prompt("test"))
    assert "new_observation" not in inc


def test_very_large_single_observation() -> None:
    config = MemoryLayerConfig(working_max_count=3, working_max_tokens=100)
    mgr = ContextMemoryManager(system_content={"tools": []}, config=config)

    huge = _obs("user_message", "x" * 10000)
    mgr.add_observation(huge)

    # Should not crash; should truncate in place
    stats = mgr.get_memory_stats()
    assert stats["working_count"] == 1
    assert stats["working_tokens"] <= 100


def test_importance_from_autopilot_observation_instance() -> None:
    obs = AutopilotObservation(
        id="obs_001",
        kind="tool_result",
        summary="built part",
        data={"tool_name": "cad.execute_build123d"},
    )
    imp = ObservationImportance.from_observation(obs)
    assert imp.level == "high"
