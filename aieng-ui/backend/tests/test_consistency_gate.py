"""Tests for the multi-sample LLM consistency gate (#220)."""

from app.consistency_gate import (
    consistency_samples,
    consistency_threshold,
    evaluate_consistency,
    low_consistency_reply,
    plan_decision_signature,
)


def test_plan_signature_is_ordered_tool_sequence() -> None:
    steps = [{"tool_name": "cad.critique"}, {"tool_name": "cad.execute_build123d"}]
    assert plan_decision_signature(steps) == "cad.critique|cad.execute_build123d"
    assert plan_decision_signature([]) == "__none__"
    # order matters — a different order is a different decision
    assert plan_decision_signature(steps) != plan_decision_signature(list(reversed(steps)))


def test_high_agreement_is_consistent() -> None:
    v = evaluate_consistency(["a|b", "a|b", "a|b"], threshold=0.6)
    assert v["consistent"] is True
    assert v["modal_signature"] == "a|b"
    assert v["agreement"] == 1.0
    assert v["distinct"] == 1


def test_split_decision_is_inconsistent() -> None:
    # 3 distinct plans across 3 samples → modal agreement 1/3 < 0.6
    v = evaluate_consistency(["a", "b", "c"], threshold=0.6)
    assert v["consistent"] is False
    assert v["agreement"] < 0.6
    assert v["distinct"] == 3


def test_modal_majority_meets_threshold() -> None:
    v = evaluate_consistency(["a", "a", "b"], threshold=0.6)
    assert v["modal_signature"] == "a"
    assert round(v["agreement"], 3) == 0.667
    assert v["consistent"] is True


def test_zero_samples_is_not_consistent() -> None:
    v = evaluate_consistency([], threshold=0.6)
    assert v["consistent"] is False
    assert v["n_samples"] == 0


def test_single_sample_is_trivially_consistent() -> None:
    v = evaluate_consistency(["a|b"], threshold=0.6)
    assert v["consistent"] is True
    assert v["agreement"] == 1.0


def test_samples_default_disabled_and_clamped() -> None:
    assert consistency_samples(None) == 1
    assert consistency_samples({}) == 1
    assert consistency_samples({"consistency_samples": 5}) == 5
    assert consistency_samples({"consistency_samples": 99}) == 7  # capped
    assert consistency_samples({"consistency_samples": "bad"}) == 1


def test_replay_and_fake_runs_bypass_sampling() -> None:
    assert consistency_samples({"consistency_samples": 5, "replay": True}) == 1
    assert consistency_samples({"consistency_samples": 5, "fake": True}) == 1
    assert consistency_samples({"consistency_samples": 5, "provider": "fake"}) == 1
    assert consistency_samples({"consistency_samples": 5, "provider": "replay"}) == 1


def test_threshold_parsing_and_clamp() -> None:
    assert consistency_threshold({}) == 0.6
    assert consistency_threshold({"consistency_threshold": 0.8}) == 0.8
    assert consistency_threshold({"consistency_threshold": 2.0}) == 1.0
    assert consistency_threshold({"consistency_threshold": "x"}) == 0.6


def test_low_consistency_reply_is_a_clarifying_question() -> None:
    v = evaluate_consistency(["a", "b", "c"], threshold=0.6)
    msg = low_consistency_reply(v)
    assert "clarify" in msg.lower()
    assert "?" in msg


# ── build_agent_plan integration (gate wraps the LLM-judged step) ─────────────

import app.agent_engine as agent_engine

_RUNTIME_TOOLS = [
    {"name": "cad.critique", "requires_approval": False},
    {"name": "cad.execute_build123d", "requires_approval": True},
]


def _plan(*tool_names: str):
    """A stub llm_agent_plan return: (steps, warnings, reply, raw)."""
    steps = [{"id": f"s{i}", "tool_name": t, "description": t, "input": {}} for i, t in enumerate(tool_names)]
    return steps, [], "stub reply", "{}"


def _call(monkeypatch, plans, llm_config):
    """Drive build_agent_plan with a stubbed llm_agent_plan that yields `plans` in order."""
    seq = iter(plans)
    monkeypatch.setattr(agent_engine, "llm_agent_plan", lambda **_: next(seq))
    return agent_engine.build_agent_plan(
        settings=object(),
        message="add a rib",
        project_id="p1",
        project_summary={},
        runtime_tools=_RUNTIME_TOOLS,
        capabilities=[],
        llm_config=llm_config,
    )


def test_low_consistency_routes_to_ask_user(monkeypatch) -> None:
    # 3 disagreeing samples → modal agreement 1/3 < 0.6 → ask the user, take no action
    plans = [_plan("cad.critique"), _plan("cad.execute_build123d"), _plan()]
    result = _call(monkeypatch, plans, {"consistency_samples": 3, "consistency_threshold": 0.6})
    assert result["requires_user_input"] is True
    assert result["steps"] == []
    assert result["consistency"]["consistent"] is False
    assert "clarify" in result["reply"].lower()


def test_high_consistency_acts_on_modal_plan(monkeypatch) -> None:
    plans = [_plan("cad.critique"), _plan("cad.critique"), _plan("cad.critique")]
    result = _call(monkeypatch, plans, {"consistency_samples": 3})
    assert result["requires_user_input"] is False
    assert [s["tool_name"] for s in result["steps"]] == ["cad.critique"]
    assert result["consistency"]["agreement"] == 1.0


def test_single_sample_default_keeps_one_call_and_no_gate(monkeypatch) -> None:
    calls = {"n": 0}

    def _stub(**_):
        calls["n"] += 1
        return _plan("cad.critique")

    monkeypatch.setattr(agent_engine, "llm_agent_plan", _stub)
    result = agent_engine.build_agent_plan(
        settings=object(), message="m", project_id="p1", project_summary={},
        runtime_tools=_RUNTIME_TOOLS, capabilities=[], llm_config={"provider": "openai"},
    )
    assert calls["n"] == 1  # gate disabled by default → exactly one judged sample
    assert result["consistency"] is None
    assert [s["tool_name"] for s in result["steps"]] == ["cad.critique"]


def test_replay_run_bypasses_sampling(monkeypatch) -> None:
    calls = {"n": 0}

    def _stub(**_):
        calls["n"] += 1
        return _plan("cad.critique")

    monkeypatch.setattr(agent_engine, "llm_agent_plan", _stub)
    result = agent_engine.build_agent_plan(
        settings=object(), message="m", project_id="p1", project_summary={},
        runtime_tools=_RUNTIME_TOOLS, capabilities=[],
        llm_config={"consistency_samples": 5, "replay": True},
    )
    assert calls["n"] == 1  # replay forces a single sample even with samples=5
    assert result["consistency"] is None
