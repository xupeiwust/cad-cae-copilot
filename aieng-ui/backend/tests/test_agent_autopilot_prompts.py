from app.agent_autopilot.prompts import build_action_prompt, build_system_layer, compact_tool_catalog
from app.agent_autopilot.project_skills import discover_project_skills


def test_compact_tool_catalog_strips_verbose_schema_descriptions() -> None:
    tools = [
        {
            "name": "aieng.agent_context",
            "description": "x" * 1000,
            "requires_approval": False,
            "input_schema": {
                "type": "object",
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string", "description": "y" * 1000},
                    "field": {"type": "string", "enum": ["stress", "displacement"]},
                },
            },
        }
    ]
    catalog = compact_tool_catalog(tools)
    assert catalog[0]["description"].endswith("]")
    assert catalog[0]["input_schema"]["properties"]["project_id"] == {"type": "string"}
    assert "description" not in catalog[0]["input_schema"]["properties"]["field"]


def test_project_skills_are_discovered_for_local_agent_prompt() -> None:
    skills = discover_project_skills()
    names = {skill["name"] for skill in skills}
    assert {"aieng-cad-authoring", "aieng-cad-cae-copilot", "aieng-closed-loop-copilot"} <= names
    cae = next(skill for skill in skills if skill["name"] == "aieng-cad-cae-copilot")
    assert "inspect cae state" in cae["description"]
    assert "Operating Rules" in cae["instruction_excerpt"]


def test_system_layer_includes_project_skill_catalog() -> None:
    layer = build_system_layer([
        {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
        {"name": "cad.plan_build123d_skill", "description": "skill", "input_schema": {"type": "object"}},
    ])
    skills = layer["project_agent_skills"]["skills"]
    assert any(skill["name"] == "aieng-cad-cae-copilot" for skill in skills)
    assert "legacy" in layer["project_agent_skills"]["activation_policy"]
    tool_names = [tool["name"] for tool in layer["available_workbench_tools"]]
    assert "cad.plan_build123d_skill" in tool_names


def test_local_and_llm_paths_share_compact_tool_catalog() -> None:
    runtime_tools = [
        {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
        {"name": "cad.plan_build123d_skill", "description": "skill", "input_schema": {"type": "object"}},
        {"name": "cad.execute_build123d", "description": "cad", "requires_approval": True, "input_schema": {"type": "object"}},
    ]

    local_layer = build_system_layer(runtime_tools)
    llm_layer = build_system_layer(runtime_tools)
    local_tool_names = [tool["name"] for tool in local_layer["available_workbench_tools"]]
    llm_tool_names = [tool["name"] for tool in llm_layer["available_workbench_tools"]]

    assert local_tool_names == llm_tool_names
    assert "cad.plan_build123d_skill" in local_tool_names
    assert local_layer["available_workbench_tools"] == llm_layer["available_workbench_tools"]


def test_action_prompt_compacts_large_agent_context_observation() -> None:
    prompt = build_action_prompt(
        objective="Explain this model",
        project_id="p1",
        selected_geometry={},
        agent_context={"project": {"name": "Schenkel"}},
        runtime_tools=[
            {"name": "aieng.agent_context", "description": "context", "input_schema": {"type": "object"}},
        ],
        observations=[
            {
                "kind": "tool_result",
                "summary": "Loaded initial project context with aieng.agent_context.",
                "data": {
                    "tool_name": "aieng.agent_context",
                    "output": {
                        "schema_version": "0.1",
                        "project_id": "p1",
                        "project": {"name": "Schenkel"},
                        "agent_brief": {"part_summary": "Schenkel: CAD geometry evidence level is exported_geometry."},
                        "brep_graph": {"digest": "face adjacency\n" * 2000},
                    },
                },
            }
        ],
    )
    assert "Schenkel" in prompt
    assert "face adjacency" in prompt
    assert "CAD BRIEF GATE" in prompt
    assert "CAD SKILL ROUTING" in prompt
    assert "project_agent_skills" in prompt
    assert "aieng-cad-cae-copilot" in prompt
    assert len(prompt) < 17000


def test_action_prompt_compacts_cad_critique_observation() -> None:
    prompt = build_action_prompt(
        objective="improve bracket",
        project_id="p1",
        selected_geometry={},
        agent_context={},
        runtime_tools=[
            {"name": "cad.critique", "description": "critique", "input_schema": {"type": "object"}},
        ],
        observations=[
            {
                "kind": "tool_result",
                "summary": "Executed Autopilot follow-up: cad.critique",
                "data": {
                    "tool_name": "cad.critique",
                    "output": {
                        "status": "ok",
                        "mode": "engineering",
                        "fail_first_objections": ["hole edge distance too small"],
                        "findings": [
                            {"severity": "high", "observation": f"finding {idx}", "details": "x" * 1000}
                            for idx in range(20)
                        ],
                    },
                },
            }
        ],
    )
    assert "hole edge distance too small" in prompt
    assert "finding_count" in prompt
    assert "finding 19" not in prompt
    assert len(prompt) < 9300


def test_action_prompt_compacts_cad_build_error_for_repair() -> None:
    prompt = build_action_prompt(
        objective="fix the failed CAD build",
        project_id="p1",
        selected_geometry={},
        agent_context={},
        runtime_tools=[
            {"name": "cad.execute_build123d", "description": "cad", "input_schema": {"type": "object"}},
        ],
        observations=[
            {
                "kind": "tool_error",
                "summary": "Tool cad.execute_build123d failed",
                "data": {
                    "tool_name": "cad.execute_build123d",
                    "error_class": "cad_build_error",
                    "recoverable": True,
                    "input": {
                        "project_id": "p1",
                        "mode": "replace",
                        "model_kind": "mechanical",
                        "code": "from build123d import *\nresult = Box(10, 10, HEIGHT)",
                    },
                    "error": (
                        "Traceback (most recent call last):\n"
                        "  File \"geometry/source.py\", line 2, in <module>\n"
                        "NameError: name 'HEIGHT' is not defined"
                    ),
                },
            }
        ],
    )

    assert "CAD BUILD REPAIR" in prompt
    assert "NameError" in prompt
    assert "top_traceback_line" in prompt
    assert "source_snippet" in prompt
    assert "project_id" in prompt


def test_action_prompt_prefers_skill_contract_fields() -> None:
    prompt = build_action_prompt(
        objective="make a flange",
        project_id="p1",
        selected_geometry={},
        agent_context={},
        runtime_tools=[
            {"name": "cad.plan_build123d_skill", "description": "skill", "input_schema": {"type": "object"}},
        ],
        observations=[
            {
                "kind": "tool_result",
                "summary": "Planned CAD skill.",
                "data": {
                    "tool_name": "cad.plan_build123d_skill",
                    "output": {
                        "status": "ready",
                        "skill_name": "cad.plan_build123d_skill",
                        "intent": "make a flange",
                        "brief": "40mm flange",
                        "proposed_tool": "cad.execute_build123d",
                        "proposed_input": {"project_id": "p1", "code": "result = None", "mode": "replace"},
                        "verification_targets": ["base_plate named part exists"],
                        "match_confidence": 0.96,
                        "matched_terms": ["flange"],
                    },
                },
            }
        ],
    )

    assert "proposed_input" in prompt
    assert "result = None" in prompt
    assert "verification_targets" in prompt
    assert "match_confidence" in prompt
    assert "flange" in prompt
