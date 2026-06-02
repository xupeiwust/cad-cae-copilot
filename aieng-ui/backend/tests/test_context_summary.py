from app.agent_autopilot.context_summary import build_context_summary
from app.agent_autopilot.schema import AgentPlan, AgentPlanStep, AutopilotApproval, AutopilotRunState


def test_context_summary_redacts_and_truncates_long_user_messages() -> None:
    long_secret = "Please use api_key=secret-token and sk-abc123456789 " + ("x" * 500)

    summary = build_context_summary(
        project_id="project-1",
        session={"id": "session-1", "title": "Summary"},
        messages=[{"role": "user", "content": long_secret}],
        events=[],
    )

    dumped = str(summary.model_dump())
    assert "secret-token" not in dumped
    assert "sk-abc123456789" not in dumped
    assert summary.goal.endswith("...")
    assert len(summary.user_constraints[0]) <= 240


def test_context_summary_records_failed_steps_as_risks() -> None:
    run = AutopilotRunState(
        run_id="run-1",
        status="failed",
        message="Make a bracket",
        adapter_id="fake",
        project_id="project-1",
        session_id="session-1",
        errors=["cad.execute_build123d failed"],
        plan=AgentPlan(
            id="plan-1",
            objective="Make a bracket",
            status="failed",
            steps=[
                AgentPlanStep(id="observe", title="Observe context", status="completed"),
                AgentPlanStep(id="build", title="Build geometry", status="failed", summary="build123d error"),
            ],
        ),
    )

    summary = build_context_summary(
        project_id="project-1",
        session={"id": "session-1", "title": "Summary"},
        messages=[],
        events=[],
        run=run,
    )

    assert summary.completed_steps == ["Observe context"]
    assert any("Failed step: Build geometry" in risk for risk in summary.risks)
    assert any("cad.execute_build123d failed" in risk for risk in summary.risks)


def test_context_summary_records_pending_approval_next_action() -> None:
    run = AutopilotRunState(
        run_id="run-1",
        status="awaiting_approval",
        message="Make CAD",
        adapter_id="fake",
        project_id="project-1",
        session_id="session-1",
        pending_approval=AutopilotApproval(
            id="approval-1",
            tool_name="cad.execute_build123d",
            level="write",
            explanation="CAD mutation requires approval.",
        ),
        plan=AgentPlan(
            id="plan-1",
            objective="Make CAD",
            status="blocked",
            steps=[
                AgentPlanStep(id="approval", title="Await approval", kind="approval", status="blocked"),
            ],
        ),
    )

    summary = build_context_summary(
        project_id="project-1",
        session={"id": "session-1", "title": "Summary"},
        messages=[],
        events=[],
        run=run,
    )

    assert summary.pending_steps == ["Await approval"]
    assert any("Pending approval: cad.execute_build123d" in risk for risk in summary.risks)
    assert summary.next_action == "Review approval for cad.execute_build123d."
