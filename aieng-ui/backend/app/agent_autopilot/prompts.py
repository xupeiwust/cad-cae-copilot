from __future__ import annotations

import json
from typing import Any

from .schema import AutopilotAgentAction
from .project_skills import project_skill_context


CORE_TOOL_ORDER = [
    "aieng.agent_readme",
    "aieng.agent_context",
    "aieng.inspect_package",
    "aieng.validate",
    "aieng.read_audit_log",
    "cad.get_source",
    "cad.plan_build123d_skill",
    "cad.execute_build123d",
    "cad.edit_parameter",
    "cad.critique",
    "cae.apply_setup_patch",
    "cae.prepare_solver_run",
    "cae.generate_solver_input",
    "cae.run_solver",
    "cae.extract_solver_results",
    "cae.extract_field_regions",
    "postprocess.refresh_cae_summary",
]

OPERATING_RULES = [
    "TOKEN BUDGET: be concise. Do not paste long source/context unless needed; prefer compact named parameters and brief validation notes.",
    "PROJECT SKILLS: before planning or choosing a tool, check project_agent_skills. Use matching skills as workflow/claim-discipline guidance, but do not invent tools from them.",
    "Skill conflict rule: active workbench runtime tools and AGENTS.md instructions override legacy skill workflows unless the user explicitly asks for that legacy/schema-bound flow.",
    "Retrieve facts before claims: use aieng.agent_context for model details; do not guess topology, dimensions, materials, or results.",
    "For greetings/meta questions use chat. For factual model work use tool_call.",
    "When the user asks what tools are available or what the workbench can do, call aieng.agent_readme (do not guess or summarize from memory). Return the result via chat, not final.",
    "CAD SKILL ROUTING: for create-new CAD requests, call cad.plan_build123d_skill first when the request matches a supported skill/template. Review its assumptions and proposed_input, then call cad.execute_build123d only if the plan fits the user intent.",
    "CAD BRIEF GATE: before cad.execute_build123d, form a compact brief from either cad.plan_build123d_skill output or your own analysis: model, units/origin, key dimensions, features, labels, validation targets, assumptions. Put a <=900 char summary in user_message when requesting approval.",
    "For new CAD call cad.get_source first unless clearly starting empty. Then propose cad.execute_build123d with result bound to final geometry.",
    "EMPTY PROJECT RULE: if agent_context shows no CAD evidence or no readable .aieng package and the user asked to create new CAD, do not block on aieng.inspect_package; proceed with cad.plan_build123d_skill or author a fresh cad.execute_build123d plan.",
    "CAD SOURCE STYLE: named parameters first; semantic .label and .color on each part; Compound(children=[...]); closed solids; no export/show calls.",
    "Mechanical parts: use canonical labels base_plate, mounting_hole_pattern, rib, boss, flange, interface_face, wall, cover; honor min wall >=3mm, hole-edge >=2x radius, internal radius >=2mm where practical.",
    "Visible products/vehicles/characters: use loft/revolve/sweep + mirror + final fillets; avoid Box stacking for exterior curves.",
    "After cad.execute_build123d, review named_parts/parts_added and thumbnail if provided. State 3-5 fail-first visual/geometric objections before further CAD edits.",
    "If cad.critique output is present, treat fail_first_objections as blockers before finalizing engineering parts.",
    "REPAIR LOOP: for recoverable tool_error, repair only failed input; preserve user intent and project_id; avoid redesign unless required.",
    "CAD BUILD REPAIR: when cad.execute_build123d fails, use the compact traceback line and source_snippet to fix imports/API misuse first; keep constants, labels, and dimensions unless the error proves they are invalid.",
    "CAE setup: use selected @face:/@edge:/@group: pointers when available; ask one concise question only if required support/load face is ambiguous.",
    "cae.apply_setup_patch is followed by solver preflight; cae.run_solver only after preflight/input are ready and requires confirmation.",
    "CAD mutation and solver execution are approval-gated; user_message must explain side effects and include the compact CAD brief/plan for CAD actions.",
    "Schema note: if action.input_json is required, encode tool input as a JSON object string; unused flattened string fields should be empty strings, not null.",
    "Final/chat messages must be complete and report only checks that actually ran. Use exact counts from tool outputs when available.",
]


def _truncate_text(value: str, limit: int = 6000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated {len(value) - limit} chars]"


def _schema_summary(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    compact_props: dict[str, Any] = {}
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            compact_props[name] = {}
            continue
        entry: dict[str, Any] = {}
        if "type" in prop:
            entry["type"] = prop.get("type")
        if "enum" in prop:
            entry["enum"] = prop.get("enum")
        compact_props[name] = entry
    return {
        "type": schema.get("type", "object"),
        "required": schema.get("required", []),
        "properties": compact_props,
    }


def compact_tool_catalog(runtime_tools: list[dict[str, Any]], limit: int = 34) -> list[dict[str, Any]]:
    by_name = {str(tool.get("name")): tool for tool in runtime_tools if tool.get("name")}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in CORE_TOOL_ORDER:
        tool = by_name.get(name)
        if tool:
            ordered.append(tool)
            seen.add(name)
    for tool in runtime_tools:
        name = str(tool.get("name") or "")
        if name and name not in seen:
            ordered.append(tool)
            seen.add(name)

    out: list[dict[str, Any]] = []
    for tool in ordered[:limit]:
        out.append(
            {
                "name": tool.get("name"),
                "description": _truncate_text(str(tool.get("description") or ""), 240),
                "requires_approval": bool(tool.get("requires_approval")),
                "input_schema": _schema_summary(tool.get("input_schema") or {"type": "object"}),
            }
        )
    return out


def _json_safe_truncate(value: Any, limit: int = 8000) -> Any:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return value
    return {"summary": _truncate_text(text, limit)}


def _compact_tool_output(output: Any) -> Any:
    if not isinstance(output, dict):
        return _json_safe_truncate(output, 3000)
    if output.get("skill_name") == "cad.plan_build123d_skill":
        proposed_input = output.get("proposed_input") if isinstance(output.get("proposed_input"), dict) else {}
        if not proposed_input:
            proposed_input = output.get("execute_input") if isinstance(output.get("execute_input"), dict) else {}
        return {
            "status": output.get("status"),
            "skill_name": output.get("skill_name"),
            "pattern": output.get("pattern"),
            "intent": output.get("intent"),
            "brief": output.get("brief"),
            "assumptions": output.get("assumptions"),
            "warnings": output.get("warnings"),
            "verification_targets": output.get("verification_targets") or output.get("validation_targets"),
            "fallback_recommendation": output.get("fallback_recommendation") or output.get("recommendation"),
            "match_confidence": output.get("match_confidence"),
            "matched_terms": output.get("matched_terms"),
            "rejection_reason": output.get("rejection_reason"),
            "proposed_tool": output.get("proposed_tool") or output.get("next_tool"),
            "proposed_input": {
                "project_id": proposed_input.get("project_id"),
                "name": proposed_input.get("name"),
                "code": proposed_input.get("code"),
                "mode": proposed_input.get("mode"),
                "model_kind": proposed_input.get("model_kind"),
                "timeout": proposed_input.get("timeout"),
            } if proposed_input else None,
        }
    if "schema_version" in output and "project_id" in output:
        cad = output.get("cad") if isinstance(output.get("cad"), dict) else {}
        cae = output.get("cae") if isinstance(output.get("cae"), dict) else {}
        brep = output.get("brep_graph") if isinstance(output.get("brep_graph"), dict) else {}
        topology = cad.get("topology_references") if isinstance(cad.get("topology_references"), dict) else {}
        feature_ids = topology.get("feature_ids") if isinstance(topology.get("feature_ids"), list) else []
        hole_feature_count = sum(1 for feature_id in feature_ids if str(feature_id).startswith("feat_hole_"))
        return {
            "project": output.get("project"),
            "agent_brief": output.get("agent_brief"),
            "cad": {
                "status": cad.get("status"),
                "geometry_evidence_level": cad.get("geometry_evidence_level"),
                "summary": cad.get("summary"),
                "topology_references": topology,
                "derived_counts": {
                    "feature_count": topology.get("feature_count"),
                    "hole_feature_count": hole_feature_count,
                },
                "missing_information": cad.get("missing_information"),
            },
            "brep_graph": {
                "face_count": brep.get("face_count"),
                "edge_count": brep.get("edge_count"),
                "selection_group_count": brep.get("selection_group_count"),
                "digest": _truncate_text(str(brep.get("digest") or ""), 2500),
            },
            "cae": {
                "present": cae.get("present"),
                "materials_count": cae.get("materials_count"),
                "loads_count": cae.get("loads_count"),
                "boundary_conditions_count": cae.get("boundary_conditions_count"),
                "results_available": cae.get("results_available"),
            },
            "design_targets": output.get("design_targets"),
            "warnings": output.get("warnings"),
        }
    if {"findings", "fail_first_objections"}.intersection(output):
        findings = output.get("findings") if isinstance(output.get("findings"), list) else []
        top_findings = []
        for finding in findings[:5]:
            if not isinstance(finding, dict):
                top_findings.append(_truncate_text(str(finding), 240))
                continue
            top_findings.append({
                key: _truncate_text(str(finding.get(key) or ""), 240)
                for key in ("severity", "category", "rule", "affected_feature", "observation", "suggested_fix")
                if finding.get(key) is not None
            })
        return {
            "status": output.get("status"),
            "mode": output.get("mode"),
            "summary": output.get("summary"),
            "verdict": output.get("verdict"),
            "fail_first_objections": output.get("fail_first_objections"),
            "finding_count": len(findings),
            "top_findings": top_findings,
        }
    return _json_safe_truncate(output, 8000)


def _top_traceback_line(error: str) -> str:
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    if not lines:
        return ""
    for line in reversed(lines):
        if line.startswith("File ") or line.startswith("^") or line == "Traceback (most recent call last):":
            continue
        return line[:500]
    return lines[-1][:500]


def _exception_type(line: str) -> str | None:
    if ":" not in line:
        return None
    candidate = line.split(":", 1)[0].strip()
    if not candidate or " " in candidate:
        return None
    if candidate.endswith(("Error", "Exception")) or "." in candidate:
        return candidate
    return None


def _compact_cad_build_error(data: dict[str, Any]) -> dict[str, Any]:
    tool_input = data.get("input") if isinstance(data.get("input"), dict) else {}
    code = tool_input.get("code") if isinstance(tool_input, dict) else None
    top_line = _top_traceback_line(str(data.get("error") or ""))
    compact: dict[str, Any] = {
        "tool_name": data.get("tool_name") or "cad.execute_build123d",
        "error_class": data.get("error_class") or "cad_build_error",
        "recoverable": data.get("recoverable", True),
        "exception_type": _exception_type(top_line),
        "top_traceback_line": top_line,
        "failing_input": {
            "project_id": tool_input.get("project_id"),
            "name": tool_input.get("name"),
            "mode": tool_input.get("mode"),
            "model_kind": tool_input.get("model_kind"),
            "timeout": tool_input.get("timeout"),
            "code_chars": len(code) if isinstance(code, str) else 0,
        },
    }
    if isinstance(code, str):
        compact["source_snippet"] = _truncate_text(code, 1800)
    return compact


def _compact_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for observation in observations[-12:]:
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        next_item = {
            "kind": observation.get("kind"),
            "summary": _truncate_text(str(observation.get("summary") or ""), 1200),
            "data": data,
        }
        if observation.get("kind") == "tool_result":
            next_data = dict(data)
            if "output" in next_data:
                next_data["output"] = _compact_tool_output(next_data.get("output"))
            next_item["data"] = _json_safe_truncate(next_data, 12000)
        elif observation.get("kind") == "tool_error" and (
            data.get("error_class") == "cad_build_error"
            or (data.get("tool_name") == "cad.execute_build123d" and data.get("error"))
        ):
            next_item["data"] = _compact_cad_build_error(data)
        else:
            next_item["data"] = _json_safe_truncate(data, 5000)
        compact.append(next_item)
    return compact


def _compact_agent_context(agent_context: dict[str, Any] | None) -> dict[str, Any]:
    """Return a lightweight summary for the initial prompt.

    Keeps only the agent_brief, project identity, and warnings.
    Full CAD/CAE/BREP details are available via the aieng.agent_context tool.
    """
    if not isinstance(agent_context, dict):
        return {}
    # Only expose the most minimal identity info; the agent should actively
    # query what it needs via aieng.agent_context rather than receiving a
    # bloated static payload that slows down every step.
    return {
        "project_name": (agent_context.get("project") or {}).get("name"),
        "note": (
            "You have access to the full aieng.agent_context tool. "
            "If you need CAD geometry, BREP topology, CAE setup, design targets, "
            "or computed metrics to answer the user's request, call it first. "
            "Do not guess or hallucinate details that you have not retrieved."
        ),
    }


def build_system_layer(
    runtime_tools: list[dict[str, Any]],
    rules: list[str] | None = None,
) -> dict[str, Any]:
    """Build the immutable system-layer payload for ContextMemoryManager.

    This is extracted from the legacy build_action_prompt so that the
    system context (rules + tool catalog + schema) can be initialized
    once and reused across steps instead of being re-transmitted every
    time.
    """
    return {
        "operating_rules": (rules or OPERATING_RULES) + [_THOUGHT_SUMMARY_GUIDELINE],
        "project_agent_skills": project_skill_context(),
        "available_workbench_tools": compact_tool_catalog(runtime_tools),
        "required_action_json_schema": AutopilotAgentAction.json_schema_for_adapter(),
    }


_THOUGHT_SUMMARY_GUIDELINE = (
    "THOUGHT_SUMMARY: Every action MUST include a concise thought_summary. "
    "It should (1) briefly summarize what the PREVIOUS step produced and what it means, "
    "(2) point out any key numbers, issues, or blockers noticed, and "
    "(3) state the intent for the NEXT action. "
    "Example good: 'Generated bracket with 3 parts. Critique found wall thickness 2.1mm < 3mm minimum. "
    "Next: edit WALL_THICKNESS parameter.' "
    "Example bad: 'Proceeding with next tool call.'"
)


def build_action_prompt(
    *,
    objective: str,
    project_id: str | None,
    selected_geometry: dict[str, Any],
    agent_context: dict[str, Any] | None,
    runtime_tools: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> str:
    """DEPRECATED: Use ContextMemoryManager instead.

    Kept temporarily for backward compatibility during the migration.
    Will be removed once engine.py is fully migrated.
    """
    # Use the module-level constant to avoid duplicating the rule list.
    # This function is deprecated; new code should use ContextMemoryManager.
    operating_rules = list(OPERATING_RULES)

    payload = {
        "objective": objective,
        "active_project_id": project_id,
        "selected_geometry": selected_geometry,
        "agent_context": _compact_agent_context(agent_context),
        "operating_rules": operating_rules,
        "project_agent_skills": project_skill_context(),
        "available_workbench_tools": compact_tool_catalog(runtime_tools),
        "previous_observations": _compact_observations(observations),
        "required_action_json_schema": AutopilotAgentAction.json_schema_for_adapter(),
    }
    return (
        "You are the AIENG Workbench Local Agent. "
        "You have access to workbench tools but you are NOT given a pre-loaded data dump. "
        "If the user asks about the model, you must retrieve the facts via aieng.agent_context first. "
        "Return exactly one JSON object matching required_action_json_schema. "
        "Do not use your own shell, file, network, repository-editing, or package-editing tools.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )
