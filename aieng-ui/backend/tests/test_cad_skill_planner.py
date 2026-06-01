from app.cad_skill_planner import plan_build123d_skill


def test_flange_skill_returns_agent_executable_build123d_plan() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个40mm的法兰盘",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "flange"
    assert "OD 40mm" in result["brief"]
    execute_input = result["execute_input"]
    assert execute_input["project_id"] == "p1"
    assert execute_input["mode"] == "replace"
    assert execute_input["model_kind"] == "mechanical"
    assert "FLANGE_OUTER_DIAMETER = 40.000" in execute_input["code"]
    assert 'base_plate.label = "base_plate"' in execute_input["code"]
    assert "result = Compound(children=[base_plate])" in execute_input["code"]


def test_cad_skill_planner_reports_unsupported_patterns_without_mutation() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个机器人",
    })

    assert result["status"] == "unsupported"
    assert result["supported_patterns"] == ["flange / 法兰盘"]
