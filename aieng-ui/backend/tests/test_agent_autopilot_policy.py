from app.agent_autopilot.policy import classify_known_tool, evaluate_tool_call


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context"},
    {"name": "cad.execute_build123d"},
    {"name": "cae.run_solver"},
    {"name": "cae.apply_setup_patch"},
]


def test_policy_classifies_expected_permission_levels() -> None:
    assert classify_known_tool("aieng.agent_context") == "auto_read"
    assert classify_known_tool("cad.execute_build123d") == "approval_mutation"
    assert classify_known_tool("cae.run_solver") == "explicit_confirm"
    assert classify_known_tool("no.such.tool") == "blocked"


def test_policy_enforces_active_project_scope() -> None:
    decision = evaluate_tool_call(
        tool_name="aieng.agent_context",
        tool_input={"project_id": "other"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
    )
    assert decision.level == "blocked"
    assert not decision.allowed


def test_policy_allows_safe_write_and_requires_approval_for_mutation() -> None:
    safe = evaluate_tool_call(
        tool_name="cae.apply_setup_patch",
        tool_input={"project_id": "active"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
    )
    assert safe.allowed
    assert not safe.requires_approval
    assert safe.level == "auto_write_safe"

    mutation = evaluate_tool_call(
        tool_name="cad.execute_build123d",
        tool_input={"project_id": "active", "code": "result = None"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
    )
    assert mutation.allowed
    assert mutation.requires_approval
    assert mutation.level == "approval_mutation"
