from app.agent_autopilot.policy import classify_known_tool, evaluate_tool_call


RUNTIME_TOOLS = [
    {"name": "aieng.agent_context"},
    {"name": "aieng.create_project"},
    {"name": "cad.plan_build123d_skill"},
    {"name": "cad.execute_build123d"},
    {"name": "cad.critique"},
    {"name": "cae.run_solver"},
    {"name": "cae.apply_setup_patch"},
]


def test_policy_classifies_expected_permission_levels() -> None:
    assert classify_known_tool("aieng.agent_context") == "auto_read"
    assert classify_known_tool("aieng.create_project") == "auto_write_safe"
    assert classify_known_tool("cad.plan_build123d_skill") == "auto_read"
    assert classify_known_tool("cad.execute_build123d") == "approval_mutation"
    assert classify_known_tool("cad.critique") == "auto_read"
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


def test_policy_allows_project_creation_without_an_existing_project_id() -> None:
    decision = evaluate_tool_call(
        tool_name="aieng.create_project",
        tool_input={"name": "New model"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
    )

    assert decision.allowed
    assert not decision.requires_approval
    assert decision.level == "auto_write_safe"


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


def test_policy_approval_modes_adjust_low_risk_automation_only() -> None:
    balanced_safe = evaluate_tool_call(
        tool_name="cae.apply_setup_patch",
        tool_input={"project_id": "active"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
        approval_mode="balanced",
    )
    assert balanced_safe.allowed
    assert not balanced_safe.requires_approval

    strict_safe = evaluate_tool_call(
        tool_name="cae.apply_setup_patch",
        tool_input={"project_id": "active"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
        approval_mode="strict",
    )
    assert strict_safe.allowed
    assert strict_safe.requires_approval
    assert strict_safe.level == "auto_write_safe"

    manual_read = evaluate_tool_call(
        tool_name="aieng.agent_context",
        tool_input={"project_id": "active"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
        approval_mode="manual",
    )
    assert manual_read.allowed
    assert manual_read.requires_approval
    assert manual_read.level == "auto_read"

    mutation = evaluate_tool_call(
        tool_name="cad.execute_build123d",
        tool_input={"project_id": "active", "code": "result = None"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
        approval_mode="balanced",
    )
    solver = evaluate_tool_call(
        tool_name="cae.run_solver",
        tool_input={"project_id": "active"},
        active_project_id="active",
        registered_tools=RUNTIME_TOOLS,
        approval_mode="balanced",
    )
    assert mutation.requires_approval
    assert solver.requires_approval
