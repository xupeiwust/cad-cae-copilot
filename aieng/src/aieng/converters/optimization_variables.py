"""Optimization variable resolution: design-study problem → optimization_variables.json.

Deterministic, pure functions that derive ``analysis/optimization_variables.json``
from ``analysis/design_study_problem.json`` plus the editable-parameter index.

The Phase-3 shape-bearing flag is derived from tokenized ``semantic_role`` /
``cad_parameter_name`` against the catalog in ``phase3_feature_shape_optimization_plan.md`` §3.
"""
from __future__ import annotations

import re
from typing import Any

from aieng import FORMAT_VERSION

from ..converters.design_study import DESIGN_STUDY_PROBLEM_PATH

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Tokens that carry no naming signal (units, generic scaffolding) — dropped so
# they neither inflate nor dilute the match score.
_PARAM_STOPTOKENS = frozenset({
    "mm", "cm", "m", "deg", "degrees", "value", "param", "params", "parameter",
    "parameters", "global", "default", "model", "the", "of",
})

# Phase-3 catalog: feature parameters that are "shape-bearing" (fillet, hole,
# slot, rib, gusset, chamfer, taper, draft).  A variable is shape-bearing when
# its tokenized ``semantic_role`` or ``cad_parameter_name`` overlaps this set.
_SHAPE_BEARING_TOKENS = frozenset({
    "fillet", "chamfer", "hole", "slot", "rib", "gusset", "taper", "draft",
})


def _tokens(text: Any) -> set[str]:
    return {t for t in _TOKEN_RE.findall(str(text or "").lower()) if t not in _PARAM_STOPTOKENS}


def is_shape_bearing(*, semantic_role: Any, cad_parameter_name: Any) -> bool:
    """Deterministic shape-bearing check for a feature parameter. Pure.

    A parameter is shape-bearing when its tokenized ``semantic_role`` or
    ``cad_parameter_name`` contains a token from the Phase-3 catalog
    (fillet, chamfer, hole, slot, rib, gusset, taper, draft).

    Examples:
      * ``FILLET_RADIUS`` / ``fillet_radius`` → ``True``
      * ``HOLE_DIAMETER`` / ``hole_diameter`` → ``True``
      * ``WALL_THICKNESS`` / ``wall_thickness`` → ``False``
      * ``BOLT_DIA`` / ``bolt_hole`` → ``True`` (hole is shape-bearing)
    """
    tokens = _tokens(semantic_role) | _tokens(cad_parameter_name)
    return bool(tokens & _SHAPE_BEARING_TOKENS)


def resolve_optimization_variables(
    problem: dict[str, Any],
    *,
    study_id: str,
    parameter_index: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build ``analysis/optimization_variables.json`` from a design-study problem.

    Each variable is enriched with:
      * ``featureId``, ``parameterName``, ``cad_parameter_name`` from the
        optional ``parameter_index`` (best-effort binding)
      * ``binding_status`` (``bound`` / ``not_found`` / ``unverified``)
      * ``scope`` (``local`` / ``global`` / ``unscoped``)
      * ``shape_bearing`` — derived from the Phase-3 catalog

    ``parameter_index`` comes from ``build_parameter_index``; when absent the
    binding fields are left as ``unverified`` / ``null``.
    """
    if not isinstance(problem, dict):
        raise ValueError("problem must be a dict")

    problem_id = problem.get("id")
    source_variables = [v for v in (problem.get("variables") or []) if isinstance(v, dict)]

    # Build a lookup from cad_parameter_name / path → index entry
    index_by_path: dict[str, dict[str, Any]] = {}
    if parameter_index:
        for entry in parameter_index:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("cad_parameter_name") or entry.get("parameter_name") or "")
            if key:
                index_by_path[key] = entry

    variables: list[dict[str, Any]] = []
    for sv in source_variables:
        vid = str(sv.get("id") or "")
        path = str(sv.get("path") or "")
        vtype = sv.get("type")
        semantic_role = sv.get("semantic_role")

        # Best-effort binding from parameter_index
        entry = index_by_path.get(path.split("/")[-1]) if path else None
        if entry is None:
            # Try path tail
            entry = index_by_path.get(path.split("/")[-1]) if path else None

        feature_id = entry.get("feature_id") if entry else None
        parameter_name = entry.get("parameter_name") if entry else None
        cad_parameter_name = entry.get("cad_parameter_name") if entry else None
        scope = entry.get("scope", "local") if entry else "unscoped"

        if entry:
            binding_status = "bound"
        elif parameter_index is not None:
            binding_status = "not_found"
        else:
            binding_status = "unverified"

        # Derive cad_parameter_name from path when index misses
        if cad_parameter_name is None:
            cad_parameter_name = path.split("/")[-1] if path else None

        # Derive shape_bearing from catalog
        shape_bearing = is_shape_bearing(
            semantic_role=semantic_role,
            cad_parameter_name=cad_parameter_name,
        )

        var: dict[str, Any] = {
            "id": vid,
            "path": path,
            "type": vtype,
            "featureId": feature_id,
            "parameterName": parameter_name,
            "cad_parameter_name": cad_parameter_name,
            "binding_status": binding_status,
            "current_value": sv.get("current_value"),
            "min_value": sv.get("min_value"),
            "max_value": sv.get("max_value"),
            "allowed_values": sv.get("allowed_values"),
            "unit": sv.get("unit"),
            "scope": scope,
            "safe_to_modify": bool(sv.get("safe_to_modify")),
            "semantic_role": semantic_role,
            "candidate_ids": [],
            "shape_bearing": shape_bearing,
        }
        variables.append(var)

    doc: dict[str, Any] = {
        "format": "aieng.optimization_variables",
        "schema_version": "0.2",
        "study_id": study_id,
        "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
        "design_study_problem_id": problem_id,
        "variables": variables,
        "candidate_ids": [],
        "provenance": {
            "created_at": None,  # caller should stamp
            "created_by": "aieng.converters.optimization_variables",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }
    if problem_id is None:
        doc.pop("design_study_problem_id")
    return doc
