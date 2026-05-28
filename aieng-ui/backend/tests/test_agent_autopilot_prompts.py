from app.agent_autopilot.prompts import build_action_prompt


def test_prompt_includes_selected_geometry_and_vertical_slice_rules() -> None:
    prompt = build_action_prompt(
        objective="Create a bracket and prepare analysis",
        project_id="p1",
        selected_geometry={"pointers": ["@face:f_left"], "faces": [{"pointer": "@face:f_left"}]},
        agent_context={"summary": "empty project"},
        runtime_tools=[
            {"name": "cad.execute_build123d", "description": "Run build123d", "input_schema": {"type": "object"}},
            {"name": "cae.apply_setup_patch", "description": "Patch setup", "input_schema": {"type": "object"}},
        ],
        observations=[],
    )

    assert "@face:f_left" in prompt
    assert "cad.execute_build123d" in prompt
    assert "build123d" in prompt
    assert "label semantic parts" in prompt
    assert "solver preflight" in prompt
    assert "postprocess solver results" in prompt
    assert "Do not use your own shell" in prompt
