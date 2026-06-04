"""Deterministic feature-parameter binding for dimensional /modify edits.

Resolves extracted parameter slots ("change the wall thickness to 5mm") against a
project's editable feature-graph parameters so the agent can be pointed at a
concrete cad.edit_parameter (featureId / parameterName) instead of a regen — with
mention_binding-style honesty (unverified when no index, not-found / ambiguous
reported, never invented). No real LLM / CAD execution.
"""

from pathlib import Path

import pytest

from app.agent_autopilot.parameter_binding import (
    bind_parameter_slots,
    build_parameter_index,
    format_parameter_bindings,
    parameter_scope,
    summarize_parameter_index,
)


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


def test_index_carries_scope() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    wall = next(e for e in index if e["cad_parameter_name"] == "WALL_THICKNESS")
    motor = next(e for e in index if e["cad_parameter_name"] == "MOTOR_POD_RADIUS")
    # global_params → shared/global; a named_part → local (the safe edit).
    assert wall["scope"] == "global"
    assert wall["feature_type"] == "global_params"
    assert motor["scope"] == "local"


def test_parameter_scope_mapping() -> None:
    assert parameter_scope("global_params") == "global"
    assert parameter_scope("model_params") == "unscoped"
    assert parameter_scope("named_part") == "local"
    assert parameter_scope(None) == "local"


def test_summarize_parameter_index() -> None:
    index = build_parameter_index(_FEATURE_GRAPH)
    summary = summarize_parameter_index(index)
    assert summary["total"] == 3
    # WALL_THICKNESS + FILLET_RADIUS are global; MOTOR_POD_RADIUS is local.
    assert summary["by_scope"]["global"] == 2
    assert summary["by_scope"]["local"] == 1
    assert summary["by_scope"]["unscoped"] == 0
    assert summarize_parameter_index(None) == {"total": 0, "by_scope": {"local": 0, "global": 0, "unscoped": 0}}


# --------------------------------------------------------------------------- #
# bind_parameter_slots                                                        #
# --------------------------------------------------------------------------- #


def _slot(name, value, unit=None):
    # bind_parameter_slots accepts dicts with name/value/unit (see its docstring),
    # so use a plain dict — this keeps the binding tests independent of the retired
    # intent_resolution.ParameterSlot type.
    return {"name": name, "value": value, "unit": unit, "raw": f"{name} to {value}"}


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


def test_list_editable_parameters_tool_registered_and_empty(tmp_path: Path) -> None:
    # The read-only explorer tool returns a well-formed empty listing for a project
    # with no feature graph yet (no build123d needed for the glue + registration).
    from fastapi.testclient import TestClient

    from app.main import Settings, create_app, default_project, save_project

    settings = Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )
    project = save_project(settings, default_project("param-explorer"))
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/invoke-tool",
        json={"tool": "cad.list_editable_parameters", "input": {"project_id": project["id"]}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["parameters"] == []
    assert body["summary"] == {"total": 0, "by_scope": {"local": 0, "global": 0, "unscoped": 0}}
    assert isinstance(body.get("message"), str) and body["message"]


def test_editable_parameters_endpoint_empty(tmp_path: Path) -> None:
    # The read-only GET endpoint the frontend panel consumes returns a well-formed
    # empty listing (200, not 404) for a project with no feature graph.
    from fastapi.testclient import TestClient

    from app.main import Settings, create_app, default_project, save_project

    settings = Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )
    project = save_project(settings, default_project("param-panel"))
    client = TestClient(create_app(settings))

    resp = client.get(f"/api/projects/{project['id']}/editable-parameters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parameters"] == []
    assert body["summary"] == {"total": 0, "by_scope": {"local": 0, "global": 0, "unscoped": 0}}


def test_critique_and_readiness_endpoints_smoke(tmp_path: Path) -> None:
    # The two read-only quality/readiness panel endpoints return well-formed
    # bodies (200) for a project with no geometry/CAE — best-effort, never 500.
    from fastapi.testclient import TestClient

    from app.main import Settings, create_app, default_project, save_project

    settings = Settings(
        platform_root=tmp_path / "platform",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "workspace" / "aieng",
        sample_step=tmp_path / "workspace" / "sample.step",
    )
    project = save_project(settings, default_project("quality-panels"))
    client = TestClient(create_app(settings))

    crit = client.get(f"/api/projects/{project['id']}/critique")
    assert crit.status_code == 200
    assert isinstance(crit.json().get("findings"), list)

    readiness = client.get(f"/api/projects/{project['id']}/simulation-readiness")
    assert readiness.status_code == 200
    body = readiness.json()
    assert "inputs" in body and "setup_source" in body
    # No solver was run building the report.
    assert body.get("solver_executed") is False
