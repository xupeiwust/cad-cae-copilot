"""Optimization-study artifact contracts and consistency validation.

The optimization front-end extends the existing design-study lifecycle. These
artifacts describe resolved parameter bindings and agent-visible study choices,
but ``analysis/design_study_problem.json`` remains the source of truth for the
variables, objective, and constraints consumed by the existing executor.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Mapping

from jsonschema import Draft202012Validator

DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"
OPTIMIZATION_STUDY_PATH = "analysis/optimization_study.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
OPTIMIZATION_OBJECTIVES_PATH = "analysis/optimization_objectives.json"
OPTIMIZATION_CONSTRAINTS_PATH = "analysis/optimization_constraints.json"
OPTIMIZATION_DECISION_LOG_PATH = "analysis/optimization_decision_log.json"

OPTIMIZATION_ARTIFACT_PATHS: dict[str, str] = {
    "study": OPTIMIZATION_STUDY_PATH,
    "variables": OPTIMIZATION_VARIABLES_PATH,
    "objectives": OPTIMIZATION_OBJECTIVES_PATH,
    "constraints": OPTIMIZATION_CONSTRAINTS_PATH,
    "decision_log": OPTIMIZATION_DECISION_LOG_PATH,
}

OPTIMIZATION_SCHEMA_FILES: dict[str, str] = {
    "study": "optimization_study.schema.json",
    "variables": "optimization_variables.schema.json",
    "objectives": "optimization_objectives.schema.json",
    "constraints": "optimization_constraints.schema.json",
    "decision_log": "optimization_decision_log.schema.json",
}

# Machine-auditable reasons shared by backend decisions and the decision-log
# schema. New codes should be added deliberately and covered by tests.
OPTIMIZATION_REASON_CODES: frozenset[str] = frozenset(
    {
        "initial_mvp",
        "user_selected",
        "no_gradient_available",
        "discrete_variables_present",
        "small_number_of_design_variables",
        "expensive_cae_eval",
        "cae_evaluation_available",
        "static_metrics_only",
        "constraint_violation",
        "candidate_build_failed",
        "candidate_evaluation_failed",
        "candidate_out_of_bounds",
        "protected_parameter",
        "duplicate_candidate",
        "candidate_cap_reached",
        "missing_metric",
        "unknown_feasibility",
        "needs_more_evaluation",
        "converged_objective_delta",
        "budget_exhausted",
        "needs_user_input",
        "human_approval_required",
        "advisory_recommendation",
        # Phase 2 — iterative loop (#60)
        "proposer_exhausted",
        "max_consecutive_failures",
        "local_refinement",
        "no_incumbent_fallback",
        "trust_region_shrink",
    }
)


def _load_schema(schema_name: str) -> dict[str, Any]:
    resource = files("aieng.schemas").joinpath(schema_name)
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_optimization_artifact(
    artifact_kind: str,
    document: Any,
) -> list[str]:
    """Return JSON-schema validation issues for one optimization artifact."""
    schema_name = OPTIMIZATION_SCHEMA_FILES.get(artifact_kind)
    if schema_name is None:
        return [f"unknown optimization artifact kind: {artifact_kind!r}"]

    validator = Draft202012Validator(_load_schema(schema_name))
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    issues: list[str] = []
    for error in errors:
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.absolute_path
        )
        issues.append(f"{path}: {error.message}")
    return issues


def validate_optimization_artifact_set(
    documents: Mapping[str, Any],
    *,
    design_study_problem: Any | None = None,
) -> list[str]:
    """Validate schemas plus cross-artifact/design-study consistency.

    ``documents`` is keyed by artifact kind (``study``, ``variables``,
    ``objectives``, ``constraints``, ``decision_log``). Missing kinds are
    allowed so callers can validate an artifact set incrementally.
    """
    issues: list[str] = []
    for kind, document in documents.items():
        issues.extend(f"{kind}: {issue}" for issue in validate_optimization_artifact(kind, document))

    valid_docs = {
        kind: document
        for kind, document in documents.items()
        if kind in OPTIMIZATION_ARTIFACT_PATHS and isinstance(document, dict)
    }
    study_ids = {
        str(document.get("study_id"))
        for document in valid_docs.values()
        if document.get("study_id")
    }
    if len(study_ids) > 1:
        issues.append(f"artifact set has inconsistent study_id values: {sorted(study_ids)}")

    for kind, document in valid_docs.items():
        ref = document.get("design_study_problem_ref")
        if ref != DESIGN_STUDY_PROBLEM_PATH:
            issues.append(
                f"{kind}: design_study_problem_ref must be {DESIGN_STUDY_PROBLEM_PATH!r}"
            )

    if isinstance(design_study_problem, dict):
        issues.extend(_validate_design_study_consistency(valid_docs, design_study_problem))
    return issues


def _validate_design_study_consistency(
    documents: Mapping[str, dict[str, Any]],
    problem: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    problem_id = problem.get("id")
    for kind, document in documents.items():
        linked_id = document.get("design_study_problem_id")
        if linked_id is not None and linked_id != problem_id:
            issues.append(
                f"{kind}: design_study_problem_id {linked_id!r} does not match {problem_id!r}"
            )

    variable_doc = documents.get("variables")
    if variable_doc:
        problem_variables = {
            item.get("id"): item
            for item in problem.get("variables", [])
            if isinstance(item, dict) and item.get("id")
        }
        for variable in variable_doc.get("variables", []):
            if not isinstance(variable, dict):
                continue
            variable_id = variable.get("id")
            source = problem_variables.get(variable_id)
            if source is None:
                issues.append(f"variables: variable {variable_id!r} is absent from design study")
                continue
            _compare_fields(
                issues,
                f"variables[{variable_id}]",
                variable,
                source,
                (
                    "path",
                    "type",
                    "current_value",
                    "min_value",
                    "max_value",
                    "allowed_values",
                    "unit",
                    "safe_to_modify",
                ),
            )

    objective_doc = documents.get("objectives")
    if objective_doc:
        problem_objectives = problem.get("objectives")
        if isinstance(problem_objectives, list):
            source_objectives = problem_objectives
        else:
            source_objective = problem.get("objective")
            source_objectives = [source_objective] if isinstance(source_objective, dict) else []

        opt_objectives = objective_doc.get("objectives") or []
        for idx, objective in enumerate(opt_objectives):
            if not isinstance(objective, dict):
                continue
            source = source_objectives[idx] if idx < len(source_objectives) else None
            if source is None:
                issues.append(
                    f"objectives[{idx}]: no corresponding objective in design-study problem"
                )
                continue
            if not isinstance(source, dict):
                issues.append(
                    f"objectives[{idx}]: design-study objective at index {idx} is not an object"
                )
                continue
            direction = objective.get("direction")
            if direction != source.get("sense"):
                issues.append(
                    f"objectives[{idx}]: direction does not match design-study objective sense"
                )
            if objective.get("metric") != source.get("metric"):
                issues.append(
                    f"objectives[{idx}]: metric does not match design-study objective metric"
                )

    constraint_doc = documents.get("constraints")
    if constraint_doc:
        problem_constraints = {
            item.get("id"): item
            for item in problem.get("constraints", [])
            if isinstance(item, dict) and item.get("id")
        }
        for constraint in constraint_doc.get("constraints", []):
            if not isinstance(constraint, dict):
                continue
            constraint_id = constraint.get("id")
            source = problem_constraints.get(constraint_id)
            if source is None:
                issues.append(
                    f"constraints: constraint {constraint_id!r} is absent from design study"
                )
                continue
            if constraint.get("metric") != source.get("type"):
                issues.append(
                    f"constraints[{constraint_id}]: metric does not match design-study type"
                )
            if "limit" in source and constraint.get("limit") != source.get("limit"):
                issues.append(
                    f"constraints[{constraint_id}]: limit does not match design-study limit"
                )
    return issues


def _compare_fields(
    issues: list[str],
    prefix: str,
    derived: dict[str, Any],
    source: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        if field in source and derived.get(field) != source.get(field):
            issues.append(f"{prefix}: {field} does not match design study")
