"""Backend mention routing — @part / @artifact composer mentions reach context.

The composer parses "@kind:value" mentions (composerIntent.ts) and persists them
on composer_intent.mentions. The engine surfaces @part / @artifact to the agent
as a prompt/context section and (v1 strict binding) resolves them against the
available workspace context into mention_bindings (known/unknown/unverified).
Still prompt/context only — no CAD-execution change, approval/mutation-guard
unchanged.

Uses the deterministic fake adapter — no real Claude/Codex/LLM and no build123d
execution required.
"""

from pathlib import Path
from types import SimpleNamespace

from app.agent_autopilot.engine import (
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    AutopilotEngine,
    mention_context_label,
    mentioned_artifacts,
    mentioned_parts,
)
from app.agent_autopilot.schema import AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
    {"name": "cad.get_source", "description": "source", "input_schema": {"type": "object"}},
    {"name": "cad.execute_build123d", "description": "cad", "input_schema": {"type": "object"}},
]


def _engine(tmp_path: Path, **kwargs) -> AutopilotEngine:
    return AutopilotEngine(store=AutopilotStore(tmp_path / "runs"), runtime_tools=RUNTIME_TOOLS, **kwargs)


def _intent(command: str | None, text: str, mentions: list[dict]) -> dict:
    return {
        "command": command,
        "commandRaw": f"/{command}" if command else None,
        "text": text,
        "mentions": mentions,
        "errors": [],
    }


def _part(value: str) -> dict:
    return {"kind": "part", "raw": f"@part:{value}", "value": value}


def _artifact(value: str) -> dict:
    return {"kind": "artifact", "raw": f"@artifact:{value}", "value": value}


def _summaries(state) -> list[str]:
    return [str(o.summary) for o in state.observations]


# --- Unit-level helper coverage ---------------------------------------------


def test_mention_helpers_read_parts_and_artifacts() -> None:
    obj = SimpleNamespace(
        composer_intent=_intent("explain", "x", [_part("rotor_1"), _artifact("model.glb"), _part("rotor_1")])
    )
    # De-duplicated, order-preserving.
    assert mentioned_parts(obj) == ["rotor_1"]
    assert mentioned_artifacts(obj) == ["model.glb"]
    label = mention_context_label(obj)
    assert label is not None
    assert "rotor_1" in label and "model.glb" in label


def test_mention_helpers_backward_compatible() -> None:
    # Missing / malformed metadata never crashes and yields empty results.
    for intent in (None, "oops", {}, {"mentions": "nope"}, {"mentions": [{"kind": "part"}]}):
        obj = SimpleNamespace(composer_intent=intent)
        assert mentioned_parts(obj) == []
        assert mentioned_artifacts(obj) == []
        assert mention_context_label(obj) is None
    assert mention_context_label(SimpleNamespace()) is None


def test_mention_context_label_is_command_aware() -> None:
    explain = SimpleNamespace(composer_intent=_intent("explain", "x", [_part("rotor_1")]))
    assert "read-only explanation" in mention_context_label(explain)
    critique = SimpleNamespace(composer_intent=_intent("critique", "x", [_part("rotor_1")]))
    assert "read-only critique" in mention_context_label(critique)
    modify = SimpleNamespace(composer_intent=_intent("modify", "x", [_part("rotor_1")]))
    assert "CAD edit" in mention_context_label(modify)


# --- Mentions reach the run context -----------------------------------------


def test_run_stores_part_mention_in_context(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/explain @part:rotor_1 what is this",
            project_id="p1",
            composer_intent=_intent("explain", "what is this", [_part("rotor_1")]),
            fake_actions=[
                {"action": {"type": "final", "message": "rotor_1 is a propeller."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    # A mention context observation carries the referenced part and the values.
    assert any("rotor_1" in s and "referenced these CAD parts" in s for s in _summaries(state))
    mention_obs = next(
        o for o in state.observations if isinstance(o.data, dict) and o.data.get("mentioned_parts")
    )
    assert mention_obs.data["mentioned_parts"] == ["rotor_1"]


def test_run_stores_artifact_mention_in_context(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/explain @artifact:model.glb describe it",
            project_id="p1",
            composer_intent=_intent("explain", "describe it", [_artifact("model.glb")]),
            fake_actions=[
                {"action": {"type": "final", "message": "It is the GLB preview."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert any("model.glb" in s and "referenced these artifacts" in s for s in _summaries(state))


def test_no_mentions_is_backward_compatible(tmp_path: Path) -> None:
    # A run with no mentions injects no mention-context observation.
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/explain the model",
            project_id="p1",
            composer_intent=_intent("explain", "the model", []),
            fake_actions=[
                {"action": {"type": "final", "message": "It is a bracket."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert not any("referenced these CAD parts" in s for s in _summaries(state))
    assert not any(
        isinstance(o.data, dict) and o.data.get("mentioned_parts") for o in state.observations
    )


# --- Mentions do not change command routing ---------------------------------


def test_explain_part_does_not_require_mutation(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/explain @part:rotor_1 should I add ribs",
            project_id="p1",
            composer_intent=_intent("explain", "should I add ribs", [_part("rotor_1")]),
            fake_actions=[
                {"action": {"type": "final", "message": "rotor_1 is fine as-is."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))


def test_critique_part_remains_read_only(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/critique @part:rotor_1 add fillets?",
            project_id="p1",
            composer_intent=_intent("critique", "add fillets?", [_part("rotor_1")]),
            fake_actions=[
                {"action": {"type": "final", "message": "No issues on rotor_1."}, "done": True},
            ],
        )
    )
    assert state.status == "completed"
    assert not any(s == GEOMETRY_MUTATION_REPAIR_INSTRUCTION for s in _summaries(state))


def test_modify_part_still_requires_mutation(tmp_path: Path) -> None:
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/modify @part:rotor_1 make it bigger",
            project_id="p1",
            composer_intent=_intent("modify", "make it bigger", [_part("rotor_1")]),
            max_steps=2,
            fake_actions=[
                {"action": {"type": "final", "message": "Resized."}, "done": True},
                {"action": {"type": "ask_user", "question": "By how much?"}},
            ],
        )
    )
    # The mutation guard still fires for /modify even with a part mention.
    assert state.status == "blocked"
    guard_obs = [o for o in state.observations if o.summary == GEOMETRY_MUTATION_REPAIR_INSTRUCTION]
    assert guard_obs and guard_obs[-1].data["intent"] == "modify_geometry"
    # The target part still reached the context.
    assert any("rotor_1" in s and "Target your CAD edit" in s for s in _summaries(state))


# --- v1 strict binding: mention_bindings against workspace context ----------


def _mention_obs(state):
    return next(
        (o for o in state.observations if isinstance(o.data, dict) and "mention_bindings" in o.data),
        None,
    )


def test_known_part_binding_from_named_parts(tmp_path: Path) -> None:
    engine = _engine(tmp_path, agent_context={"cad": {"named_parts": ["rotor_1", "body"]}})
    state = engine.start(
        AutopilotRunRequest(
            message="/explain @part:rotor_1",
            project_id="p1",
            composer_intent=_intent("explain", "explain", [_part("rotor_1")]),
            fake_actions=[{"action": {"type": "final", "message": "ok"}, "done": True}],
        )
    )
    obs = _mention_obs(state)
    assert obs is not None
    binding = obs.data["mention_bindings"][0]
    assert binding["known"] is True
    assert binding["source"] == "cad.named_parts"
    assert binding["canonical_id"] == "rotor_1"
    # The label annotates the known status.
    assert "rotor_1 (known)" in obs.summary


def test_unknown_part_binding_is_false(tmp_path: Path) -> None:
    engine = _engine(tmp_path, agent_context={"cad": {"named_parts": ["body"]}})
    state = engine.start(
        AutopilotRunRequest(
            message="/explain @part:ghost",
            project_id="p1",
            composer_intent=_intent("explain", "explain", [_part("ghost")]),
            fake_actions=[{"action": {"type": "ask_user", "question": "No such part — which one?"}}],
        )
    )
    binding = _mention_obs(state).data["mention_bindings"][0]
    assert binding["known"] is False
    assert "not found" in binding["reason"]


def test_unavailable_context_marks_binding_unverified(tmp_path: Path) -> None:
    # No agent_context → no authoritative index → known=None (not False).
    state = _engine(tmp_path).start(
        AutopilotRunRequest(
            message="/explain @part:rotor_1",
            project_id="p1",
            composer_intent=_intent("explain", "explain", [_part("rotor_1")]),
            fake_actions=[{"action": {"type": "final", "message": "ok"}, "done": True}],
        )
    )
    binding = _mention_obs(state).data["mention_bindings"][0]
    assert binding["known"] is None
    assert "rotor_1 (unverified)" in _mention_obs(state).summary


def test_known_artifact_binding(tmp_path: Path) -> None:
    engine = _engine(tmp_path, agent_context={"artifacts": ["model.glb", "result.step"]})
    state = engine.start(
        AutopilotRunRequest(
            message="/explain @artifact:model.glb",
            project_id="p1",
            composer_intent=_intent("explain", "explain", [_artifact("model.glb")]),
            fake_actions=[{"action": {"type": "final", "message": "ok"}, "done": True}],
        )
    )
    binding = _mention_obs(state).data["mention_bindings"][0]
    assert binding["kind"] == "artifact"
    assert binding["known"] is True
    assert binding["source"] == "workspace_artifacts"
