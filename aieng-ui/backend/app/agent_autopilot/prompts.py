from __future__ import annotations

import json
from typing import Any

from .schema import AutopilotAgentAction


def compact_tool_catalog(runtime_tools: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in runtime_tools[:limit]:
        out.append(
            {
                "name": tool.get("name"),
                "description": tool.get("description") or "",
                "requires_approval": bool(tool.get("requires_approval")),
                "input_schema": tool.get("input_schema") or {"type": "object"},
            }
        )
    return out


def build_action_prompt(
    *,
    objective: str,
    project_id: str | None,
    selected_geometry: dict[str, Any],
    agent_context: dict[str, Any] | None,
    runtime_tools: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> str:
    operating_rules = [
        "For new CAD, call cad.get_source first when a project may already have a model; otherwise propose cad.execute_build123d with mode replace and final build123d bound to result.",
        "When writing build123d code, label semantic parts and combine them in a Compound so topology exposes named parts.",
        "Use selected @face: and @edge: pointers for CAE setup when available; ask one concise question if a required support or load face is ambiguous.",
        "For preprocessing, prefer cae.apply_setup_patch; the Workbench will run solver preflight after safe setup patches.",
        "For solver execution, request cae.run_solver only after preflight/input generation is ready; the Workbench will postprocess solver results after approval.",
        "CAD mutation and solver execution are approval-gated by policy; explain the side effect in user_message when requesting them.",
        "If the provided JSON schema uses action.input_json instead of action.input, encode tool input as a JSON object string.",
    ]
    payload = {
        "objective": objective,
        "active_project_id": project_id,
        "selected_geometry": selected_geometry,
        "agent_context": agent_context or {},
        "operating_rules": operating_rules,
        "available_workbench_tools": compact_tool_catalog(runtime_tools),
        "previous_observations": observations[-8:],
        "required_action_json_schema": AutopilotAgentAction.json_schema_for_adapter(),
    }
    return (
        "You are the AIENG Workbench Local Agent Autopilot planner. "
        "Return exactly one JSON object matching required_action_json_schema. "
        "Use only available_workbench_tools. Do not use your own shell, file, "
        "network, repository-editing, or package-editing tools. Ask one concise "
        "question if required context is missing.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )
