"""Natural-language intent resolution — the composer "point and shoot" front door.

When a run carries no explicit slash command, the engine resolves the plain-text
message into one of the routed commands (build / modify / critique / explain /
simulate) so the EXISTING routing + guards apply verbatim. Three tiers:

  1. explicit /command always wins,
  2. an optional (app-wired, LLM-backed) classifier,
  3. a deterministic keyword heuristic.

When an inferred command is actionable but low-confidence / ambiguous, the engine
injects a clarification bias (toward ask_user) instead of routing on a guess.

These tests use the deterministic fake adapter (keyword tier — fake/replay runs
skip the LLM classifier) plus direct method calls with a stub classifier to
exercise the clarification path. No real Claude/Codex/LLM and no CAD execution.
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent_autopilot.engine import (
    AutopilotEngine,
    BUILD_COMMAND_INSTRUCTION,
    EXPLAIN_COMMAND_INSTRUCTION,
    GEOMETRY_MUTATION_REPAIR_INSTRUCTION,
    INTENT_CLARIFY_INSTRUCTION,
    PARAMETRIC_EDIT_INSTRUCTION,
    _MUTATION_REQUIRED_COMMANDS,
    _READ_ONLY_COMMANDS,
    _SIMULATION_COMMANDS,
    _COMMAND_INTENT_LABELS,
)
from app.agent_autopilot.intent_resolution import (
    INTENT_REGISTRY,
    IntentResolution,
    extract_parameter_slots,
    format_parameter_slots,
    keyword_classify,
    parse_classifier_json,
    resolve_intent,
)
from app.agent_autopilot.schema import AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore
from app.main import Settings, create_app, default_project, save_project


# --------------------------------------------------------------------------- #
# Unit tests — registry derivation                                            #
# --------------------------------------------------------------------------- #


def test_engine_command_sets_derive_from_registry() -> None:
    # The engine's command views must stay in lockstep with the registry.
    assert _MUTATION_REQUIRED_COMMANDS == {"build", "modify"}
    assert _READ_ONLY_COMMANDS == {"critique", "explain"}
    assert _SIMULATION_COMMANDS == {"simulate"}
    assert _COMMAND_INTENT_LABELS == {
        c: spec.intent_type for c, spec in INTENT_REGISTRY.items()
    }


# --------------------------------------------------------------------------- #
# Unit tests — resolver tiers                                                 #
# --------------------------------------------------------------------------- #


def test_explicit_command_always_wins() -> None:
    # Free text says "build", but the explicit /critique command must win.
    res = resolve_intent("should I build a new frame", existing_command="critique")
    assert res.command == "critique"
    assert res.source == "explicit_command"
    assert res.confidence == 1.0
    assert res.needs_clarification is False


@pytest.mark.parametrize(
    "message,expected",
    [
        ("create a mounting bracket", "build"),
        ("生成一个支架", "build"),
        ("add a rib to the plate", "modify"),       # modify beats build precedence
        ("make it taller", "modify"),
        ("explain what this project contains", "explain"),
        ("run a stress simulation", "simulate"),
        ("review the manufacturability", "critique"),
    ],
)
def test_keyword_classifier_routes(message: str, expected: str) -> None:
    res = keyword_classify(message)
    assert res.command == expected
    assert res.intent_type == INTENT_REGISTRY[expected].intent_type
    assert res.source == "keyword_heuristic"
    # Keyword matches are confident enough to route directly — no surprise prompts.
    assert res.needs_clarification is False


def test_keyword_mutation_beats_readonly() -> None:
    # "add ... and simulate" is a geometry edit first, not a read-only plan.
    res = keyword_classify("add a load case and simulate it")
    assert res.command == "modify"


@pytest.mark.parametrize("message", ["hello there", "what can you do?", "   "])
def test_keyword_no_actionable_intent(message: str) -> None:
    res = keyword_classify(message)
    assert res.command is None
    assert res.needs_clarification is False


def test_classifier_low_confidence_triggers_clarification() -> None:
    def stub(_msg, _ctx):
        return IntentResolution(
            command="modify", intent_type="modify_geometry",
            confidence=0.2, source="llm_classifier",
        )

    res = resolve_intent("tweak the thing", classifier=stub)
    assert res.command == "modify"
    assert res.needs_clarification is True


def test_classifier_ambiguous_triggers_clarification_even_if_confident() -> None:
    def stub(_msg, _ctx):
        return IntentResolution(
            command="build", intent_type="create_geometry",
            confidence=0.95, source="llm_classifier", ambiguous=True,
        )

    res = resolve_intent("do the bracket thing", classifier=stub)
    assert res.needs_clarification is True


def test_classifier_error_falls_back_to_keyword() -> None:
    def boom(_msg, _ctx):
        raise RuntimeError("provider exploded")

    res = resolve_intent("create a box", classifier=boom)
    assert res.command == "build"
    assert res.source == "keyword_heuristic"


def test_classifier_invalid_command_falls_back() -> None:
    def stub(_msg, _ctx):
        return IntentResolution(
            command="frobnicate", intent_type="???",
            confidence=0.9, source="llm_classifier",
        )

    # Invalid command is sanitized to None → keyword heuristic takes over.
    res = resolve_intent("create a box", classifier=stub)
    assert res.command == "build"
    assert res.source == "keyword_heuristic"


@pytest.mark.parametrize(
    "raw,expected_command",
    [
        ('{"command": "build", "confidence": 0.9}', "build"),
        ('```json\n{"command": "modify", "confidence": 0.8}\n```', "modify"),
        ('Sure! {"command": "simulate", "confidence": 0.7} hope that helps', "simulate"),
        ('{"command": null, "reason": "small talk"}', None),
        ("not json at all", None),
        ('{"command": "nope"}', None),
    ],
)
def test_parse_classifier_json(raw: str, expected_command) -> None:
    res = parse_classifier_json(raw)
    if expected_command is None:
        assert res is None or res.command is None
    else:
        assert res is not None and res.command == expected_command


# --------------------------------------------------------------------------- #
# Unit tests — parameter slot extraction                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "message,name,value,unit",
    [
        ("change the wall thickness to 5mm", "wall thickness", 5.0, "mm"),
        ("set radius to 12", "radius", 12.0, None),
        ("increase wall thickness to 6 mm", "wall thickness", 6.0, "mm"),
        ("make the fillet radius 8mm", "fillet radius", 8.0, "mm"),
        ("把壁厚改成5", "壁厚", 5.0, None),
        ("the bolt diameter to 4.5mm", "bolt diameter", 4.5, "mm"),
    ],
)
def test_extract_parameter_slots(message: str, name: str, value: float, unit) -> None:
    slots = extract_parameter_slots(message)
    assert slots, f"expected a slot from {message!r}"
    assert slots[0].name == name
    assert slots[0].value == value
    assert slots[0].unit == unit


@pytest.mark.parametrize(
    "message",
    ["build a bracket", "make it 5mm taller", "explain the project", "hello"],
)
def test_extract_parameter_slots_no_false_positive(message: str) -> None:
    # "make it 5mm taller" → name "it" is a stopword, dropped.
    assert extract_parameter_slots(message) == []


def test_extract_parameter_slots_dedup() -> None:
    slots = extract_parameter_slots("set radius to 5 and set radius to 5")
    assert len(slots) == 1


def test_format_parameter_slots() -> None:
    slots = extract_parameter_slots("change wall thickness to 5mm")
    assert format_parameter_slots(slots) == "wall thickness→5mm"


# --------------------------------------------------------------------------- #
# Engine integration — keyword tier via fake adapter + TestClient             #
# --------------------------------------------------------------------------- #


def _make_runtime_settings(tmp_path: Path) -> Settings:
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )


def _wait_for_status(client: TestClient, run_id: str, statuses: set, timeout_s: float = 6.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/agent/autopilot/runs/{run_id}")
        if resp.status_code == 200:
            last = resp.json()
            if last.get("status") in statuses:
                return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}; last={last}")


def _summaries(run: dict) -> list:
    return [str(o.get("summary", "")) for o in run.get("observations", [])]


def test_nl_build_is_routed_and_mutation_guard_fires(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("nl-build"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            # No slash command, no composer_intent: pure natural language.
            "message": "build me a mounting bracket",
            "project_id": project["id"],
            "adapter_id": "fake",
            "max_steps": 3,  # bound the loop; the bare final keeps being rejected
            "fake_actions": [{"action": {"type": "final", "message": "done"}, "done": True}],
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    # The mutation guard must reject the premature final — proving NL "build ..."
    # was resolved to the mutation-required /build command.
    deadline = time.time() + 6.0
    guarded = False
    final = None
    while time.time() < deadline:
        final = client.get(f"/api/agent/autopilot/runs/{run_id}").json()
        if any(GEOMETRY_MUTATION_REPAIR_INSTRUCTION in s for s in _summaries(final)):
            guarded = True
            break
        time.sleep(0.05)
    assert guarded, "expected the geometry mutation guard to fire for resolved /build"

    assert final["composer_intent"]["command"] == "build"
    assert final["composer_intent"]["intent_source"] == "keyword_heuristic"
    assert final["composer_intent"]["resolved_intent"]["command"] == "build"
    assert any(BUILD_COMMAND_INSTRUCTION in s for s in _summaries(final))


def test_nl_explain_is_routed_read_only_and_completes(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("nl-explain"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "explain what this project contains",
            "project_id": project["id"],
            "adapter_id": "fake",
            "fake_actions": [
                {"action": {"type": "final", "message": "This project is empty."}, "done": True}
            ],
        },
    )
    assert resp.status_code == 200
    final = _wait_for_status(client, resp.json()["run_id"], {"completed", "failed"})

    assert final["status"] == "completed"  # read-only: final allowed
    assert final["composer_intent"]["command"] == "explain"
    summaries = _summaries(final)
    assert any(EXPLAIN_COMMAND_INSTRUCTION in s for s in summaries)
    # The mutation guard must NOT have fired for a read-only resolution.
    assert not any(GEOMETRY_MUTATION_REPAIR_INSTRUCTION in s for s in summaries)


def test_explicit_command_beats_natural_language_keywords(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("explicit-wins"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "/critique should I build a whole new frame",
            "project_id": project["id"],
            "adapter_id": "fake",
            "composer_intent": {
                "command": "critique", "commandRaw": "/critique",
                "text": "should I build a whole new frame", "mentions": [], "errors": [],
            },
            "fake_actions": [{"action": {"type": "final", "message": "Looks fine."}, "done": True}],
        },
    )
    assert resp.status_code == 200
    final = _wait_for_status(client, resp.json()["run_id"], {"completed", "failed"})

    assert final["status"] == "completed"
    assert final["composer_intent"]["command"] == "critique"
    # Explicit command short-circuits resolution — no inferred intent recorded.
    assert "resolved_intent" not in final["composer_intent"]


def test_nl_greeting_forces_no_command(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("nl-greeting"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "hi, what can you help me with?",
            "project_id": project["id"],
            "adapter_id": "fake",
            "fake_actions": [{"action": {"type": "final", "message": "I can model CAD."}, "done": True}],
        },
    )
    assert resp.status_code == 200
    final = _wait_for_status(client, resp.json()["run_id"], {"completed", "failed"})

    assert final["status"] == "completed"  # no command forced → final allowed
    intent = final.get("composer_intent") or {}
    assert intent.get("command") is None
    assert (intent.get("resolved_intent") or {}).get("command") is None


# --------------------------------------------------------------------------- #
# Engine method — clarification path with a stub classifier                   #
# --------------------------------------------------------------------------- #


def _engine(tmp_path: Path, classifier) -> AutopilotEngine:
    store = AutopilotStore(tmp_path / "runs")
    return AutopilotEngine(store=store, runtime_tools=[], intent_classifier=classifier)


def test_resolve_method_injects_clarification_bias(tmp_path: Path) -> None:
    def stub(_msg, _ctx):
        return IntentResolution(
            command="modify", intent_type="modify_geometry",
            confidence=0.2, source="llm_classifier", reason="weak guess",
        )

    engine = _engine(tmp_path, stub)
    # fake_actions=None so the classifier is NOT skipped.
    request = AutopilotRunRequest(message="tweak that part somehow", adapter_id="fake")
    state = engine._new_state(request)

    engine._resolve_natural_language_intent(state, request)

    # Actionable but weak → clarification bias, NOT a forced command.
    assert state.composer_intent.get("command") is None
    assert state.composer_intent["resolved_intent"]["needs_clarification"] is True
    assert any(
        INTENT_CLARIFY_INSTRUCTION.split("{")[0] in str(o.summary)
        for o in state.observations
    )


def test_resolve_method_confident_classifier_sets_command(tmp_path: Path) -> None:
    def stub(_msg, _ctx):
        return IntentResolution(
            command="build", intent_type="create_geometry",
            confidence=0.92, source="llm_classifier",
        )

    engine = _engine(tmp_path, stub)
    request = AutopilotRunRequest(message="I need a new enclosure", adapter_id="fake")
    state = engine._new_state(request)

    engine._resolve_natural_language_intent(state, request)

    assert state.composer_intent["command"] == "build"
    assert state.composer_intent["intent_source"] == "llm_classifier"
    assert state.composer_intent["resolved_intent"]["needs_clarification"] is False


def test_nl_modify_with_slot_injects_parametric_bias(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("nl-param-edit"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "change the wall thickness to 5mm",
            "project_id": project["id"],
            "adapter_id": "fake",
            "max_steps": 2,  # modify is mutation-required; bare final keeps bouncing
            "fake_actions": [{"action": {"type": "final", "message": "done"}, "done": True}],
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    # Give the run a moment to inject the startup context observations.
    final = _wait_for_status(client, run_id, {"completed", "failed", "blocked", "running"}, timeout_s=4.0)
    deadline = time.time() + 4.0
    found = False
    slots = None
    while time.time() < deadline:
        final = client.get(f"/api/agent/autopilot/runs/{run_id}").json()
        for obs in final.get("observations", []):
            if "wall thickness" in str(obs.get("summary", "")) and "cad.edit_parameter" in str(obs.get("summary", "")):
                found = True
                slots = (obs.get("data") or {}).get("parameter_slots")
        if found:
            break
        time.sleep(0.05)

    assert found, "expected a parametric-edit bias observation for the dimensional modify"
    assert final["composer_intent"]["command"] == "modify"
    assert slots and slots[0]["name"] == "wall thickness" and slots[0]["value"] == 5.0


def test_explicit_modify_with_slot_injects_parametric_bias(tmp_path: Path) -> None:
    settings = _make_runtime_settings(tmp_path)
    project = save_project(settings, default_project("explicit-param-edit"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/autopilot/runs",
        json={
            "message": "/modify set the radius to 12mm",
            "project_id": project["id"],
            "adapter_id": "fake",
            "max_steps": 2,
            "composer_intent": {
                "command": "modify", "commandRaw": "/modify",
                "text": "set the radius to 12mm", "mentions": [], "errors": [],
            },
            "fake_actions": [{"action": {"type": "final", "message": "done"}, "done": True}],
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    deadline = time.time() + 4.0
    found = False
    while time.time() < deadline:
        final = client.get(f"/api/agent/autopilot/runs/{run_id}").json()
        if any(
            "radius" in str(o.get("summary", "")) and PARAMETRIC_EDIT_INSTRUCTION[:30] in str(o.get("summary", ""))
            for o in final.get("observations", [])
        ):
            found = True
            break
        time.sleep(0.05)
    assert found, "explicit /modify with a dimensional slot should also get the parametric bias"


def _engine_with_loader(tmp_path: Path, loader=None) -> AutopilotEngine:
    store = AutopilotStore(tmp_path / "runs")
    return AutopilotEngine(store=store, runtime_tools=[], feature_parameter_loader=loader)


def test_followup_modify_with_slot_emits_parametric_binding(tmp_path: Path) -> None:
    index = [{
        "feature_id": "feat_global_params", "feature_name": "Global Parameters",
        "feature_type": "global_params", "scope": "global",
        "parameter_name": "thickness_mm", "cad_parameter_name": "WALL_THICKNESS",
        "current_value": 3.0, "min_value": 0.15, "max_value": 15.0,
        "search_tokens": ["thickness", "wall"],
    }]
    engine = _engine_with_loader(tmp_path, lambda _pid: index)
    request = AutopilotRunRequest(message="build a bracket", project_id="p1", adapter_id="fake")
    state = engine._new_state(request)
    before = len(state.observations)

    engine._normalize_followup_intent(state, "now change the wall thickness to 6mm")

    new = state.observations[before:]
    assert any(o.data.get("parameter_slots") for o in new)
    binding = next(o for o in new if o.data.get("parameter_bindings")).data["parameter_bindings"][0]
    assert binding["known"] is True and binding["cad_parameter_name"] == "WALL_THICKNESS"


def test_followup_non_modify_records_normalized_intent(tmp_path: Path) -> None:
    engine = _engine_with_loader(tmp_path)
    request = AutopilotRunRequest(message="build a bracket", project_id="p1", adapter_id="fake")
    state = engine._new_state(request)
    before = len(state.observations)

    engine._normalize_followup_intent(state, "now explain what this looks like")

    new = state.observations[before:]
    assert len(new) == 1
    assert new[0].data["followup_intent"]["command"] == "explain"
    assert "Normalized follow-up intent: /explain" in new[0].summary


def test_followup_no_actionable_intent_is_noop(tmp_path: Path) -> None:
    engine = _engine_with_loader(tmp_path)
    request = AutopilotRunRequest(message="build a bracket", project_id="p1", adapter_id="fake")
    state = engine._new_state(request)
    before = len(state.observations)

    engine._normalize_followup_intent(state, "thanks, that looks good")

    assert len(state.observations) == before  # nothing forced — the agent proceeds


def test_resolve_method_skips_classifier_for_fake_runs(tmp_path: Path) -> None:
    calls = {"n": 0}

    def stub(_msg, _ctx):
        calls["n"] += 1
        return IntentResolution(command="build", intent_type="create_geometry",
                                confidence=0.9, source="llm_classifier")

    engine = _engine(tmp_path, stub)
    # fake_actions present → engine must NOT call the LLM classifier (determinism).
    request = AutopilotRunRequest(
        message="create a box", adapter_id="fake",
        fake_actions=[{"action": {"type": "final", "message": "x"}, "done": True}],
    )
    state = engine._new_state(request)
    engine._resolve_natural_language_intent(state, request)

    assert calls["n"] == 0  # classifier skipped
    # Keyword tier still resolves "create" → build.
    assert state.composer_intent["command"] == "build"
    assert state.composer_intent["intent_source"] == "keyword_heuristic"
