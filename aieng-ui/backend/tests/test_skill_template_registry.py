import pytest

from app.cad_skill_planner import plan_build123d_skill
from app.skill_template_registry import (
    SkillTemplateError,
    SkillTemplateRegistry,
    default_template_directory,
)


def test_registry_loads_builtin_gear_pulley_template() -> None:
    registry = SkillTemplateRegistry.load(default_template_directory())
    assert "gear_pulley" in registry.templates
    template = registry.templates["gear_pulley"]
    assert template.template_id == "gear_pulley"
    assert template.base_primitive.kind == "revolve_profile"
    assert any(inp.name == "outer_diameter" for inp in template.parametric_inputs)


def test_registry_rejects_unsupported_primitive(tmp_path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        "template_id: bad\n"
        "name: Bad\n"
        "base_primitive:\n"
        "  kind: unsupported_primitive\n"
        "  label: bad\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillTemplateError) as exc_info:
        SkillTemplateRegistry.load(tmp_path)
    assert "unsupported primitive" in str(exc_info.value).lower()


def test_registry_match_uses_full_tag_phrases() -> None:
    registry = SkillTemplateRegistry.load(default_template_directory())
    gear = registry.templates["gear_pulley"]

    assert gear in registry.match("make a gear pulley")
    assert gear in registry.match("design a timing pulley")
    assert gear in registry.match("建模一个皮带轮")
    # "pulley wheel" should stay with the existing hand-written wheel template.
    assert gear not in registry.match("make a 200mm pulley wheel")


def test_declarative_gear_pulley_generates_build123d_plan() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a gear pulley",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "gear_pulley"
    assert result["proposed_tool"] == "cad.execute_build123d"
    assert result["match_confidence"] > 0.9

    code = result["execute_input"]["code"]
    assert "OUTER_DIAMETER = 60.000" in code
    assert "WIDTH = 20.000" in code
    assert "BORE_DIAMETER = 10.000" in code
    assert "GROOVE_DEPTH = 3.000" in code
    assert "with BuildSketch(Plane.XZ):" in code
    assert "Polyline(" in code and "close=True" in code
    assert "make_face()" in code
    assert "revolve(axis=Axis.Z)" in code
    assert "Hole(radius=BORE_DIAMETER / 2" in code
    assert '_part.label = "gear_pulley"' in code
    assert "result = Compound(children=[_part])" in code


def test_declarative_gear_pulley_honors_payload_overrides() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a gear pulley",
        "outer_diameter_mm": 80.0,
        "width_mm": 30.0,
    })

    assert result["status"] == "ready"
    code = result["execute_input"]["code"]
    assert "OUTER_DIAMETER = 80.000" in code
    assert "WIDTH = 30.000" in code


def test_declarative_template_rejects_out_of_range_parameter() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "make a gear pulley",
        "outer_diameter_mm": 5.0,
    })

    assert result["status"] == "error"
    assert result["pattern"] == "gear_pulley"
    assert "below minimum" in result["brief"].lower()


def test_declarative_template_does_not_break_existing_templates() -> None:
    result = plan_build123d_skill({
        "project_id": "p1",
        "message": "建模一个40mm的法兰盘",
    })

    assert result["status"] == "ready"
    assert result["pattern"] == "flange"
    assert "FLANGE_OUTER_DIAMETER = 40.000" in result["execute_input"]["code"]


def test_registry_empty_directory_is_valid() -> None:
    registry = SkillTemplateRegistry.load("/nonexistent/path/for/templates")
    assert registry.templates == {}
