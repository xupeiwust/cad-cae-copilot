"""Intent-constrained action selection for CAD/CAE agents.

``agent_context.available_actions`` is a capability/recommendation surface, not
an execution queue. This module intersects those candidates with the user's
current request so the agent can recommend an action without doing work the user
did not ask for.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "0.1"

POLICY_SUMMARY = (
    "available_actions are candidates only. The agent may recommend or explain "
    "an action, but it must not execute CAD edits, exports, setup completion, "
    "mesh/solver runs, or result imports unless the user request explicitly asks "
    "for that kind of work."
)

_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "inspect": (
        "inspect", "status", "state", "summary", "what is", "show", "explain", "understand",
        "check", "review", "look at", "看看", "查看", "检查", "状态", "解释", "总结", "理解",
    ),
    "cad_modify": (
        "modify", "edit", "change", "redesign", "optimize", "reduce weight", "thicken",
        "make thinner", "add hole", "parameter", "修改", "更改", "改", "优化", "减重", "加厚",
        "变薄", "打孔", "参数",
    ),
    "cad_create": (
        "create", "generate", "build", "model", "draw", "fixture",
        "创建", "生成", "建立", "建模", "绘制",
    ),
    "export": ("export", "step", "fcstd", "download", "导出", "输出"),
    "setup": (
        "setup", "material", "load", "boundary", "constraint", "fea setup", "补全", "设置",
        "材料", "载荷", "边界", "约束", "仿真设置",
    ),
    "mesh_or_solver": (
        "mesh", "solver", "simulate", "simulation", "run", "calculix", "ccx", "求解",
        "仿真", "运行", "网格",
    ),
    "results": (
        "result", "metric", "postprocess", "extract", "compare", "target", "stress",
        "displacement", "结果", "指标", "后处理", "提取", "比较", "目标", "应力", "位移",
    ),
}

_ACTION_TAGS_BY_ID: dict[str, set[str]] = {
    "generate_cad_fixture": {"cad_create", "setup"},
    "import_real_geometry": {"cad_create", "export"},
    "label_functional_regions": {"setup"},
    "identify_load_candidates": {"setup"},
    "identify_support_candidates": {"setup"},
    "inspect_geometry_readiness": {"inspect", "setup"},
    "review_cad_observation": {"inspect"},
    "import_computed_metrics": {"results"},
    "compare_targets": {"inspect", "results"},
}

_ACTION_TAGS_BY_TOOL: dict[str, set[str]] = {
    "cae.extract_solver_results": {"results"},
    "cae.prepare_solver_run": {"inspect", "mesh_or_solver"},
    "cae.run_solver": {"mesh_or_solver"},
    "engineering_template.generate_cad_fixture": {"cad_create", "setup"},
}


def infer_user_intents(message: str) -> list[str]:
    text = (message or "").lower()
    intents: list[str] = []
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            intents.append(intent)
    if not intents:
        intents.append("inspect")
    return intents


def annotate_available_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        item = dict(action)
        tags = _action_tags(item)
        item["intent_tags"] = sorted(tags)
        item["execution_policy"] = {
            "candidate_only": True,
            "requires_matching_user_intent": sorted(tags - {"inspect"}) or ["inspect"],
            "must_not_auto_execute": True,
        }
        annotated.append(item)
    return annotated


def select_actions_for_intent(
    *,
    message: str,
    available_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Intersect user intent with agent-context action candidates."""

    intents = infer_user_intents(message)
    intent_set = set(intents)
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for raw in annotate_available_actions(available_actions):
        tags = set(raw.get("intent_tags") or [])
        if _is_allowed(tags, intent_set):
            allowed.append({**raw, "selection_reason": _selection_reason(tags, intent_set)})
        else:
            blocked.append({
                **raw,
                "blocked_reason": (
                    "Candidate requires explicit user intent for "
                    f"{', '.join(sorted(tags - {'inspect'}) or sorted(tags) or ['action'])}."
                ),
            })

    recommended = _recommended_action(allowed, intent_set)
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": POLICY_SUMMARY,
        "user_intents": intents,
        "allowed_actions": allowed,
        "recommended_action": recommended,
        "blocked_actions": blocked,
    }


def _action_tags(action: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for tag in action.get("intent_tags") or []:
        if isinstance(tag, str):
            tags.add(tag)
    action_id = str(action.get("id") or "")
    tool_hint = str(action.get("tool_hint") or "")
    tags.update(_ACTION_TAGS_BY_ID.get(action_id, set()))
    tags.update(_ACTION_TAGS_BY_TOOL.get(tool_hint, set()))
    if not tags:
        tags.add("inspect")
    return tags


def _is_allowed(tags: set[str], intents: set[str]) -> bool:
    if not tags:
        return False
    if tags <= {"inspect"}:
        return True
    # Status/explanation requests should not silently trigger setup, export,
    # solver, result-import, or CAD-mutation actions.
    return bool(tags & intents)


def _selection_reason(tags: set[str], intents: set[str]) -> str:
    if tags <= {"inspect"}:
        return "Read-only inspection is allowed for any project-understanding request."
    matched = sorted(tags & intents)
    return f"Matches explicit user intent: {', '.join(matched)}."


def _recommended_action(
    allowed: list[dict[str, Any]],
    intents: set[str],
) -> dict[str, Any] | None:
    if not allowed:
        return None
    # Prefer non-mutating/read-only actions unless the user explicitly asked for
    # CAD modification, setup, export, solver, or result processing.
    action_intent = bool(intents - {"inspect"})
    if not action_intent:
        for action in allowed:
            if "inspect" in set(action.get("intent_tags") or []):
                return action
    for action in allowed:
        tags = set(action.get("intent_tags") or [])
        if tags & intents:
            return action
    return allowed[0]


__all__ = [
    "POLICY_SUMMARY",
    "SCHEMA_VERSION",
    "annotate_available_actions",
    "infer_user_intents",
    "select_actions_for_intent",
]
