from app.agent_autopilot.prompts import build_action_prompt, compact_tool_catalog


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


def test_action_prompt_compacts_large_agent_context_observation() -> None:
    prompt = build_action_prompt(
        objective="解释一下这个模型",
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
    assert len(prompt) < 18000
