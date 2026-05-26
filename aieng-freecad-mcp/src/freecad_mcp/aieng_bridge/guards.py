"""Operation guard checks against .aieng package constraints.

Rules:
- Standalone mode allows operations by default.
- .aieng-enhanced mode validates against task_spec, feature_graph, and constraints.
- Guards never auto-advance claims.
- Forbidden claims in task_spec produce warnings, not execution blocks.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from freecad_mcp.aieng_bridge.context import AiengPackageContext


class GuardResult(BaseModel):
    """Result of checking whether an operation is allowed."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    mode: Literal["standalone", "aieng_enhanced"]
    reasons: list[str] = []
    warnings: list[str] = []
    unsupported: list[str] = []
    protected_region_conflicts: list[str] = []


def check_operation_allowed(
    context: AiengPackageContext,
    operation: str,
    target_feature_id: str | None = None,
    requested_outputs: list[str] | None = None,
    is_modification: bool = False,
) -> GuardResult:
    """Check whether a requested operation is allowed given the .aieng context.

    Args:
        context: Loaded .aieng package context.
        operation: Tool operation name (e.g. ``cae_run_static_analysis``).
        target_feature_id: Optional CAD feature ID being modified.
        requested_outputs: Optional list of output artifacts being requested.
        is_modification: Whether the operation modifies CAD geometry or parameters.

    Returns:
        GuardResult with ``allowed=True`` if the operation may proceed.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    unsupported: list[str] = []
    protected_region_conflicts: list[str] = []

    if context.mode == "standalone" or not context.available:
        reasons.append("No .aieng context provided; running in standalone mode without package-level constraints.")
        return GuardResult(
            allowed=True,
            mode="standalone",
            reasons=reasons,
            warnings=[*context.warnings, *warnings],
            unsupported=unsupported,
            protected_region_conflicts=protected_region_conflicts,
        )

    reasons.append(".aieng context loaded; applying package-level constraints.")
    mode: Literal["standalone", "aieng_enhanced"] = "aieng_enhanced"

    # Task spec: allowed operations
    task_spec = context.task_spec or {}
    allowed_ops = task_spec.get("allowed_operations")
    if isinstance(allowed_ops, list):
        if operation not in allowed_ops:
            return GuardResult(
                allowed=False,
                mode=mode,
                reasons=[f"Operation '{operation}' is not in task_spec.allowed_operations."],
                warnings=context.warnings,
                unsupported=unsupported,
                protected_region_conflicts=protected_region_conflicts,
            )
        reasons.append(f"Operation '{operation}' is listed in task_spec.allowed_operations.")

    # Task spec: forbidden claims (warning only, does not block execution)
    forbidden_claims = task_spec.get("forbidden_claims", [])
    if isinstance(forbidden_claims, list) and forbidden_claims:
        warnings.append(
            f"task_spec declares forbidden claims: {forbidden_claims}. "
            "Execution is allowed, but claim advancement must avoid these."
        )

    # Feature graph: semantic-only or non-executable features
    if target_feature_id is not None:
        feature_graph = context.feature_graph or {}
        features = feature_graph.get("features", feature_graph)
        if isinstance(features, dict):
            feature = features.get(target_feature_id)
            if feature is None:
                warnings.append(
                    f"Target feature '{target_feature_id}' not found in feature_graph."
                )
            else:
                editability = feature.get("editability", {}) if isinstance(feature, dict) else {}
                if is_modification and editability.get("executable") is False:
                    return GuardResult(
                        allowed=False,
                        mode=mode,
                        reasons=[
                            f"Feature '{target_feature_id}' is marked semantic-only or not executable in feature_graph."
                        ],
                        warnings=[*context.warnings, *warnings],
                        unsupported=unsupported,
                        protected_region_conflicts=protected_region_conflicts,
                    )
                if editability.get("executable") is False:
                    warnings.append(
                        f"Feature '{target_feature_id}' is semantic-only; read-only inspection allowed."
                    )
                else:
                    reasons.append(f"Feature '{target_feature_id}' is executable per feature_graph.")

    # Constraints / protected regions
    constraints = context.constraints or {}
    protected_regions = constraints.get("protected_regions", [])
    if isinstance(protected_regions, list) and target_feature_id is not None:
        for region in protected_regions:
            if not isinstance(region, dict):
                continue
            region_features = region.get("features", [])
            if target_feature_id in region_features:
                protected_region_conflicts.append(
                    f"Feature '{target_feature_id}' is in protected region '{region.get('name', 'unknown')}'."
                )
        if protected_region_conflicts:
            return GuardResult(
                allowed=False,
                mode=mode,
                reasons=[
                    f"Feature '{target_feature_id}' conflicts with protected regions: "
                    f"{protected_region_conflicts}"
                ],
                warnings=[*context.warnings, *warnings],
                unsupported=unsupported,
                protected_region_conflicts=protected_region_conflicts,
            )

    # External tool requirements
    ext_reqs = context.external_tool_requirements or {}
    required_capabilities = ext_reqs.get("required_capabilities", [])
    if isinstance(required_capabilities, list):
        # For now, just record unsupported if the operation seems unmet.
        # A future version can map operation names to capability tags.
        pass

    return GuardResult(
        allowed=True,
        mode=mode,
        reasons=reasons,
        warnings=[*context.warnings, *warnings],
        unsupported=unsupported,
        protected_region_conflicts=protected_region_conflicts,
    )
