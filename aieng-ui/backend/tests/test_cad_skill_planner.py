from app.cad_skill_planner import plan_build123d_skill


def test_flange_skill_returns_agent_executable_build123d_plan() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个40mm的法兰盘",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "flange"
    assert "OD 40mm" in result["brief"]
    assert result["proposed_tool"] == "cad.execute_build123d"
    assert result["match_confidence"] > 0.9
    assert result["matched_terms"]
    assert result["verification_targets"]
    assert result["proposed_input"] == result["execute_input"]
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
    assert result["proposed_tool"] is None
    assert result["proposed_input"] == {}
    assert "cad.get_source" in result["fallback_recommendation"]
    assert result["match_confidence"] == 0.0
    assert result["rejection_reason"] == "no_supported_template_matched"


def test_cad_skill_planner_reports_needs_clarification_contract() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "",
    })

    assert result["status"] == "needs_clarification"
    assert result["skill_name"] == "cad.plan_build123d_skill"
    assert result["assumptions"] == []
    assert result["warnings"] == []
    assert result["proposed_input"] == {}
    assert result["question"] == "What CAD part should be generated?"


def test_mounting_plate_skill_returns_parameterized_template() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个120x80x8mm安装板，四个M6孔",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "mounting_plate"
    assert result["proposed_tool"] == "cad.execute_build123d"
    assert "120x80x8mm" in result["brief"]
    code = result["proposed_input"]["code"]
    assert "PLATE_LENGTH = 120.000" in code
    assert "PLATE_WIDTH = 80.000" in code
    assert "PLATE_THICKNESS = 8.000" in code
    assert "MOUNTING_HOLE_DIAMETER = 6.000" in code
    assert "MOUNTING_HOLE_COUNT_X = 2" in code
    assert "MOUNTING_HOLE_COUNT_Y = 2" in code
    assert 'base_plate.label = "base_plate"' in code
    assert "hole-edge distance" in " ".join(result["verification_targets"])


def test_mounting_plate_skill_warns_on_thin_plate() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a 100 by 60 mounting plate with 4 holes",
        "thickness_mm": 2,
    })

    assert result["status"] == "ready"
    assert any("below the 3mm" in warning for warning in result["warnings"])


def test_l_bracket_skill_returns_canonical_parts() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个L型支架，底板80x40，立板60高，M5孔",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "l_bracket"
    assert "L bracket" in result["brief"]
    code = result["proposed_input"]["code"]
    assert "BASE_LENGTH = 80.000" in code
    assert "BASE_WIDTH = 40.000" in code
    assert "BACK_HEIGHT = 60.000" in code
    assert "MOUNTING_HOLE_DIAMETER = 5.000" in code
    assert 'base_plate.label = "base_plate"' in code
    assert 'back_plate.label = "back_plate"' in code
    assert 'rib_1.label = "rib_1"' in code
    assert 'rib_2.label = "rib_2"' in code
    assert "cad.critique" in " ".join(result["verification_targets"])


def test_enclosure_skill_returns_walls_cover_and_bosses() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个100x60x30mm外壳，壁厚3mm",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "enclosure"
    assert "Electronics enclosure" in result["brief"]
    code = result["proposed_input"]["code"]
    assert "OUTER_LENGTH = 100.000" in code
    assert "OUTER_WIDTH = 60.000" in code
    assert "OUTER_HEIGHT = 30.000" in code
    assert "WALL_THICKNESS = 3.000" in code
    assert 'wall_body.label = "wall_body"' in code
    assert 'cover.label = "cover"' in code
    assert 'boss.label = f"boss_{index}"' in code
    assert "WALL_THICKNESS" in " ".join(result["verification_targets"])


def test_enclosure_skill_warns_on_thin_wall() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a 100x60x30 enclosure with screw bosses",
        "wall_thickness_mm": 1.5,
    })

    assert result["status"] == "ready"
    assert any("below the 3mm" in warning for warning in result["warnings"])


def test_bushing_skill_returns_axisymmetric_template() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个外径20mm内径8mm长度30mm的轴套",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "bushing"
    assert "OD 20mm" in result["brief"]
    code = result["proposed_input"]["code"]
    assert "OUTER_DIAMETER = 20.000" in code
    assert "INNER_DIAMETER = 8.000" in code
    assert "BUSHING_LENGTH = 30.000" in code
    assert 'bushing.label = "bushing"' in code
    assert "INNER_DIAMETER" in " ".join(result["verification_targets"])


def test_bushing_skill_rejects_invalid_od_id() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a bushing",
        "outer_diameter_mm": 8,
        "inner_diameter_mm": 12,
        "length_mm": 20,
    })

    assert result["status"] == "error"
    assert result["code"] == "invalid_bushing_dimensions"
    assert result["proposed_input"] == {}


# ── organic starter families (aircraft / vehicle / wheel) ────────────────────

def test_aircraft_skill_returns_organic_starter() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "model an airplane, fuselage length 500mm",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "aircraft_fuselage"
    code = result["proposed_input"]["code"]
    assert result["proposed_input"]["model_kind"] == "organic"
    assert "FUSELAGE_LENGTH = 500.000" in code
    assert "fuselage_profile(" in code and "naca_airfoil(" in code
    assert 'fuselage.label = "fuselage"' in code
    assert "result = Compound(children=[fuselage, wing, tail_fin])" in code


def test_vehicle_skill_returns_organic_starter_with_four_wheels() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "design a car body 420x180x140mm",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "vehicle_body"
    code = result["proposed_input"]["code"]
    assert result["proposed_input"]["model_kind"] == "organic"
    assert "BODY_LENGTH = 420.000" in code
    assert "WHEEL_RADIUS" in code and "wheel(" in code
    assert 'w.label = f"wheel_{_i}"' in code  # 4-wheel loop, label not f-string-mangled


def test_wheel_skill_returns_organic_starter() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a 200mm pulley wheel",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "wheel"
    code = result["proposed_input"]["code"]
    assert result["proposed_input"]["model_kind"] == "organic"
    assert "RIM_RADIUS" in code and "WHEEL_WIDTH" in code
    assert 'wheel_part.label = "wheel"' in code


def test_vehicle_trigger_respects_word_boundaries() -> None:
    # "scar"/"carbon" contain the substring "car" but must NOT match the vehicle family.
    for msg in ("a scar on the panel", "a carbon fiber bracket"):
        result = plan_build123d_skill({"project_id": "p1", "message": msg})
        assert result.get("pattern") != "vehicle_body", msg
