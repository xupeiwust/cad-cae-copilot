"""Deterministic feature-parameter binding for dimensional /modify edits.

Resolves extracted parameter slots ("change the wall thickness to 5mm") against a
project's editable feature-graph parameters so the agent can be pointed at a
concrete cad.edit_parameter (featureId / parameterName) instead of a regen — with
mention_binding-style honesty (unverified when no index, not-found / ambiguous
reported, never invented). No real LLM / CAD execution.
"""

from pathlib import Path

import pytest

from app.agent_autopilot.engine import AutopilotEngine
from app.agent_autopilot.parameter_binding import (
    bind_parameter_slots,
    build_parameter_index,
    format_parameter_bindings,
)
from app.agent_autopilot.intent_resolution import ParameterSlot, extract_parameter_slots
from app.agent_autopilot.schema import AutopilotRunRequest
from app.agent_autopilot.store import AutopilotStore


# Mirrors the real feature_graph.json shape produced by cad_generation: features
# carry a `parameters` dict keyed by inferred parameter name, each with a
# cad_parameter_name (the editable UPPER_SNAKE_CASE constant) + current/min/max.
_FEATURE_GRAPH = {
    "features": [
        {
            "id": "feat_global_params",
            "type": "global_params",
            "name": "Global Parameters",
            "parameters": {
                "thickness_mm": {
                    "current_value": 3.0, "cad_parameter_name": "WALL_THICKNESS",
                    "min_value": 0.15, "max_value": 15.0,
                },
                "radius_mm": {
                    "current_value": 2.0, "cad_parameter_name": "FILLET_RADIUS",
                    "min_value": 0.1, "max_value": 10.0,
                },
            },
        },
        {
            "id": "feat_part_001",
            "type": "named_part",
            "name": "motor_pod_fl",
            "parameters": {
                "radius_mm": {
                    "current_value": 3.0, "cad_parameter_name": "MOTOR_POD_RADIUS",
                    "min_value": 0.15, "max_value": 15.0,
                },
            },
        },
    ]
}


# --------------------------------------------------------------------------- #
# build_parameter_index                                                       #
# --------------------------------------------------------------------------- #


def test_build_parameter_index_flattens_and_tokenizes() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    assert len(index) == 3
    wall = next(e for e in index if e["cad_parameter_name"] == "WALL_THICKNESS")
    assert wall["feature_id"] == "feat_global_params"
    assert wall["parameter_name"] == "thickness_mm"
    assert "wall" in wall["search_tokens"] and "thickness" in wall["search_tokens"]
    # Units / scaffolding tokens are dropped.
    assert "mm" not in wall["search_tokens"]


@pytest.mark.parametrize("bad", [None, {}, {"features": "nope"}, {"features": [1, 2]}])
def test_build_parameter_index_robust(bad) -> None:
    assert build_parameter_index(bad) == []


# --------------------------------------------------------------------------- #
# bind_parameter_slots                                                        #
# --------------------------------------------------------------------------- #


def _slot(name, value, unit=None):
    return ParameterSlot(name=name, value=value, unit=unit, raw=f"{name} to {value}")


def test_bind_unique_match_is_known_and_in_bounds() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    [binding] = bind_parameter_slots([_slot("wall thickness", 5.0, "mm")], index)
    assert binding["known"] is True
    assert binding["feature_id"] == "feat_global_params"
    assert binding["parameter_name"] == "thickness_mm"
    assert binding["cad_parameter_name"] == "WALL_THICKNESS"
    assert binding["value_within_bounds"] is True


def test_bind_out_of_range_flagged() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    [binding] = bind_parameter_slots([_slot("wall thickness", 500.0, "mm")], index)
    assert binding["known"] is True
    assert binding["value_within_bounds"] is False


def test_bind_ambiguous_lists_candidates() -> None:
    # "radius" matches both FILLET_RADIUS and MOTOR_POD_RADIUS equally → ambiguous.
    index = build_parameter_index(_FEATURE_GRAPH)
    [binding] = bind_parameter_slots([_slot("radius", 4.0, "mm")], index)
    assert binding["known"] is False
    assert "ambiguous" in binding["reason"]
    assert len(binding["candidates"]) == 2


def test_bind_specific_radius_disambiguates() -> None:
    # "motor pod radius" covers more tokens of MOTOR_POD_RADIUS → unique winner.
    index = build_parameter_index(_FEATURE_GRAPH)
    [binding] = bind_parameter_slots([_slot("motor pod radius", 4.0, "mm")], index)
    assert binding["known"] is True
    assert binding["cad_parameter_name"] == "MOTOR_POD_RADIUS"


def test_bind_no_match_is_known_false() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    [binding] = bind_parameter_slots([_slot("flange width", 4.0)], index)
    assert binding["known"] is False
    assert "no matching" in binding["reason"]


def test_bind_no_index_is_unverified() -> None:
    # No feature graph available → honest "unverified" (None), never a false negative.
    [binding] = bind_parameter_slots([_slot("wall thickness", 5.0)], None)
    assert binding["known"] is None


def test_bind_empty_index_is_known_false() -> None:
    [binding] = bind_parameter_slots([_slot("wall thickness", 5.0)], [])
    assert binding["known"] is False
    assert "no editable parameters" in binding["reason"]


def test_format_parameter_bindings_lines() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    bindings = bind_parameter_slots(
        [_slot("wall thickness", 5.0, "mm"), _slot("radius", 4.0), _slot("flange width", 2.0)],
        index,
    )
    text = format_parameter_bindings(bindings)
    assert "cad.edit_parameter featureId=feat_global_params parameterName=thickness_mm" in text
    assert "AMBIGUOUS" in text
    assert "no matching editable parameter" in text


# --------------------------------------------------------------------------- #
# Engine integration — _inject_parametric_edit_context with a stub loader      #
# --------------------------------------------------------------------------- #


def _engine(tmp_path: Path, loader) -> AutopilotEngine:
    store = AutopilotStore(tmp_path / "runs")
    return AutopilotEngine(store=store, runtime_tools=[], feature_parameter_loader=loader)


def test_engine_binds_slot_to_concrete_parameter(tmp_path: Path) -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    engine = _engine(tmp_path, lambda _pid: index)
    request = AutopilotRunRequest(
        message="change the wall thickness to 5mm",
        project_id="p1",
        adapter_id="fake",
        composer_intent={"command": "modify"},
    )
    state = engine._new_state(request)

    engine._inject_parametric_edit_context(state)

    obs = [o for o in state.observations if "cad.edit_parameter" in str(o.summary)]
    assert obs, "expected a parametric-edit observation with a resolved target"
    binding = obs[0].data["parameter_bindings"][0]
    assert binding["known"] is True
    assert binding["feature_id"] == "feat_global_params"
    assert binding["parameter_name"] == "thickness_mm"


def test_engine_unverified_when_no_loader(tmp_path: Path) -> None:
    engine = _engine(tmp_path, None)  # no feature_parameter_loader
    request = AutopilotRunRequest(
        message="change the wall thickness to 5mm",
        project_id="p1",
        adapter_id="fake",
        composer_intent={"command": "modify"},
    )
    state = engine._new_state(request)

    engine._inject_parametric_edit_context(state)

    # Still injects the slot bias, but bindings are honestly "unverified".
    obs = [o for o in state.observations if o.data.get("parameter_slots")]
    assert obs
    binding = obs[0].data["parameter_bindings"][0]
    assert binding["known"] is None


def test_engine_skips_for_non_modify(tmp_path: Path) -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    engine = _engine(tmp_path, lambda _pid: index)
    request = AutopilotRunRequest(
        message="change the wall thickness to 5mm",
        project_id="p1",
        adapter_id="fake",
        composer_intent={"command": "explain"},  # not modify
    )
    state = engine._new_state(request)

    engine._inject_parametric_edit_context(state)

    assert not any(o.data.get("parameter_slots") for o in state.observations)
