"""Capability inspection / gap reporting helper for .aieng packages.

Provides a read-only, planning-neutral inspection aid that exposes:
- available capabilities (by category)
- package context and runtime state
- possibly relevant tools (without prescribing order)
- missing information, unsupported operations, side effects
- policy reminders

This module does NOT:
- execute CAD or CAE operations
- modify packages or files
- advance claims
- prescribe workflow sequences or ranking
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any, Literal

from pydantic import BaseModel, Field

from freecad_mcp.freecad_runtime import detect_freecad_runtime


# ---------------------------------------------------------------------------
# New neutral models (preferred)
# ---------------------------------------------------------------------------

class CapabilityToolInfo(BaseModel):
    """Neutral description of a possibly relevant tool. No sequencing implied."""

    tool_name: str
    category: Literal["cad", "cae", "reference", "evidence", "claim", "runtime", "audit"]
    purpose: str
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    mutates_cad: bool = False
    mutates_package: bool = False
    may_update_claim_map: bool = False
    notes: list[str] = Field(default_factory=list)


class CapabilityInspectionSummary(BaseModel):
    """Neutral capability inspection result. No workflow plan or ranking."""

    status: Literal["success", "partial", "unsupported"]
    mode: Literal["standalone", "aieng_enhanced"]
    desired_outcome: str | None = None
    available_context: list[str] = Field(default_factory=list)
    available_runtime_capabilities: dict[str, Any] = Field(default_factory=dict)
    possibly_relevant_tools: list[CapabilityToolInfo] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unsupported_operations: list[str] = Field(default_factory=list)
    needs_review: list[str] = Field(default_factory=list)
    policy_reminders: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CapabilityInspectionRequest(BaseModel):
    """Input for capability inspection."""

    desired_outcome: str
    package_path: str | None = None
    include_runtime_capabilities: bool = True
    allow_cad_operations: bool = True
    allow_cae_operations: bool = True
    allow_claim_update: bool = True


# ---------------------------------------------------------------------------
# Legacy models (deprecated, preserved for backward compatibility)
# ---------------------------------------------------------------------------

class CapabilityPlanStep(BaseModel):
    """Deprecated: A single recommended step in a capability plan.

    Prefer CapabilityToolInfo for new integrations.
    """

    step_id: str
    purpose: str
    suggested_tool: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    mutates_package: bool = False
    mutates_cad: bool = False
    advances_claims: bool = False
    warnings: list[str] = Field(default_factory=list)


class CapabilityPlanSummary(BaseModel):
    """Deprecated: Overall plan output.

    Prefer CapabilityInspectionSummary for new integrations.
    """

    status: Literal["success", "partial", "unsupported"]
    mode: Literal["standalone", "aieng_enhanced"]
    desired_outcome: str
    recommended_steps: list[CapabilityPlanStep] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unsupported_steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    claim_policy_reminders: list[str] = Field(default_factory=list)


class CapabilityPlanRequest(BaseModel):
    """Deprecated: Input for the capability planner.

    Prefer CapabilityInspectionRequest for new integrations.
    """

    desired_outcome: str
    package_path: str | None = None
    include_runtime_capabilities: bool = True
    allow_cad_operations: bool = True
    allow_cae_operations: bool = True
    allow_claim_update: bool = True


# ---------------------------------------------------------------------------
# Policy reminders
# ---------------------------------------------------------------------------

_DEFAULT_POLICY_REMINDERS: list[str] = [
    "CAD modification does not automatically trigger CAE execution.",
    "CAE execution does not require a preceding CAD modification.",
    "Evidence does not automatically advance claims.",
    "Only aieng_update_claim may update claim_map.json.",
    "The agent or caller decides workflow ordering.",
    "No tool except aieng_update_claim may advance claims.",
    "Solver execution is evidence, NOT validation.",
    "Explicit claim update is required after all evidence is collected.",
]


# ---------------------------------------------------------------------------
# Tool catalog (neutral, unordered)
# ---------------------------------------------------------------------------

_TOOL_CATALOG: list[CapabilityToolInfo] = [
    CapabilityToolInfo(
        tool_name="freecad_inspect_model",
        category="cad",
        purpose="Open and inspect a CAD model; extract object tree, parameters, and bounds.",
        required_inputs=["package_path or path to FCStd/STEP file"],
        optional_inputs=["target_feature_id"],
        side_effects=["None (read-only)"],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        notes=["Works in standalone mode without .aieng package."],
    ),
    CapabilityToolInfo(
        tool_name="freecad_apply_parameter_edit",
        category="cad",
        purpose="Apply a guarded parametric edit when executable edit metadata exists.",
        required_inputs=["package_path", "edit_metadata"],
        optional_inputs=["target_feature_id", "persist_to_aieng"],
        side_effects=["Writes modified FCStd", "Writes modified STEP if exported"],
        mutates_cad=True,
        mutates_package=True,
        may_update_claim_map=False,
        notes=[
            "Rejects semantic-only parameters.",
            "Rejects edits that violate protected-region constraints.",
        ],
    ),
    CapabilityToolInfo(
        tool_name="freecad_export_step",
        category="cad",
        purpose="Export CAD geometry to STEP for traceability.",
        required_inputs=["source_fcstd_path", "output_step_path"],
        side_effects=["Writes STEP file"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
    ),
    CapabilityToolInfo(
        tool_name="freecad_create_static_structural_analysis",
        category="cae",
        purpose="Create a static structural analysis with materials, supports, and loads.",
        required_inputs=["model_path", "material", "constraints", "loads"],
        optional_inputs=["package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Creates analysis objects", "May write evidence if persisted"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        notes=[
            "Linear static only. No contact, buckling, or nonlinear.",
            "Requires FreeCAD FEM workbench.",
        ],
    ),
    CapabilityToolInfo(
        tool_name="freecad_generate_mesh",
        category="cae",
        purpose="Generate a tetrahedral mesh for FEM.",
        required_inputs=["analysis_object", "max_element_size"],
        optional_inputs=["package_path", "persist_to_aieng"],
        side_effects=["Creates mesh object", "May write evidence if persisted"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        notes=["Mesh quality is deterministic but not guaranteed."],
    ),
    CapabilityToolInfo(
        tool_name="freecad_export_calculix_deck",
        category="cae",
        purpose="Export a CalculiX input deck.",
        required_inputs=["analysis_object", "output_inp_path"],
        optional_inputs=["package_path", "persist_to_aieng"],
        side_effects=["Writes .inp deck file"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
    ),
    CapabilityToolInfo(
        tool_name="freecad_run_calculix",
        category="cae",
        purpose="Run CalculiX on an exported deck.",
        required_inputs=["input_deck_path", "output_directory"],
        optional_inputs=["package_path", "persist_to_aieng"],
        side_effects=["Writes FRD/DAT result files", "May write evidence if persisted"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        notes=[
            "Requires CalculiX solver in runtime.",
            "Solver execution is evidence, NOT validation.",
        ],
    ),
    CapabilityToolInfo(
        tool_name="aieng_postprocess_results",
        category="evidence",
        purpose="Extract deterministic numeric metrics from solver results.",
        required_inputs=["result_source path"],
        optional_inputs=["package_path", "persist_to_aieng", "export_csv", "export_vtk"],
        side_effects=["Writes CSV/VTK artifacts", "May write evidence if persisted"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        notes=[
            "Does NOT advance claims.",
            "Surrogate outputs are not solver validation evidence.",
        ],
    ),
    CapabilityToolInfo(
        tool_name="aieng_update_claim",
        category="claim",
        purpose="Explicitly update a claim status with collected evidence.",
        required_inputs=["claim_id", "evidence_ids", "decision_criteria"],
        optional_inputs=["package_path", "requested_status", "mode", "rationale", "dry_run"],
        side_effects=["Updates claim_map.json", "Appends trace entry"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=True,
        notes=[
            "ONLY tool allowed to modify claim_map.json.",
            "Evaluate mode performs deterministic criteria evaluation.",
            "Manual mode requires rationale and explicit requested_status.",
        ],
    ),
    CapabilityToolInfo(
        tool_name="aieng_generate_audit_report",
        category="audit",
        purpose="Generate an audit report of evidence, traces, and claim discipline.",
        required_inputs=["package_path"],
        optional_inputs=["output_markdown", "output_json"],
        side_effects=["Writes reports/audit_report.json and .md"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        notes=[
            "Read-only on package content; writes report files.",
            "Detects claim discipline violations.",
        ],
    ),
    CapabilityToolInfo(
        tool_name="aieng_build_reference_map",
        category="reference",
        purpose="Build or inspect a reference map for design traceability.",
        required_inputs=["package_path"],
        optional_inputs=["persist"],
        side_effects=["Writes objects/reference_map.json if persist=True"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        notes=["Mapping is traceability evidence, not engineering validation."],
    ),
    CapabilityToolInfo(
        tool_name="aieng_mark_references_needing_review",
        category="reference",
        purpose="Mark geometry references and linked CAE targets as needing review.",
        required_inputs=["package_path", "affected_feature_ids"],
        optional_inputs=["reason"],
        side_effects=["Updates objects/reference_map.json"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
    ),
    CapabilityToolInfo(
        tool_name="freecad_runtime_capabilities",
        category="runtime",
        purpose="Detect FreeCAD, FEM workbench, meshers, and solver runtime availability.",
        required_inputs=[],
        side_effects=["None (read-only)"],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        notes=["Returns structured result even when FreeCAD is unavailable."],
    ),
]


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------

def _load_package_context(package_path: str | None) -> dict[str, Any]:
    """Load lightweight context from an .aieng package if available."""
    if not package_path:
        return {}
    context: dict[str, Any] = {"package_path": package_path}
    manifest_path = os.path.join(package_path, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            context["manifest"] = manifest
        except Exception:
            context["manifest_error"] = "Failed to parse manifest.json"
    setup_path = os.path.join(package_path, "simulation", "setup.yaml")
    context["has_simulation_setup"] = os.path.isfile(setup_path)
    evidence_path = os.path.join(package_path, "results", "evidence_index.json")
    context["has_evidence"] = os.path.isfile(evidence_path)
    claim_path = os.path.join(package_path, "results", "claim_map.json")
    context["has_claims"] = os.path.isfile(claim_path)
    return context


# ---------------------------------------------------------------------------
# Core inspection logic
# ---------------------------------------------------------------------------

def _match_tools_by_outcome(
    request: CapabilityInspectionRequest,
    runtime: dict[str, Any],
    context: dict[str, Any],
) -> tuple[list[CapabilityToolInfo], list[str], list[str], list[str]]:
    """Return possibly relevant tools, missing info, unsupported ops, warnings.

    No sequencing or ranking is performed.
    """
    outcome = request.desired_outcome.lower()
    matched: list[CapabilityToolInfo] = []
    missing: list[str] = []
    unsupported: list[str] = []
    warns: list[str] = []

    # Build keyword-to-tool mapping for neutral matching
    keywords: dict[str, list[str]] = {
        "cad": ["freecad_inspect_model", "freecad_apply_parameter_edit", "freecad_export_step"],
        "inspect": ["freecad_inspect_model", "freecad_runtime_capabilities"],
        "parameter": ["freecad_inspect_model", "freecad_apply_parameter_edit"],
        "model": ["freecad_inspect_model", "freecad_runtime_capabilities"],
        "geometry": ["freecad_inspect_model", "freecad_apply_parameter_edit", "freecad_export_step"],
        "modify": ["freecad_apply_parameter_edit"],
        "edit": ["freecad_apply_parameter_edit"],
        "export": ["freecad_export_step", "freecad_export_calculix_deck"],
        "step": ["freecad_export_step"],
        "cae": ["freecad_create_static_structural_analysis", "freecad_generate_mesh", "freecad_export_calculix_deck", "freecad_run_calculix"],
        "fem": ["freecad_create_static_structural_analysis", "freecad_generate_mesh", "freecad_export_calculix_deck", "freecad_run_calculix"],
        "mesh": ["freecad_generate_mesh"],
        "solver": ["freecad_run_calculix", "aieng_postprocess_results"],
        "stress": ["freecad_run_calculix", "aieng_postprocess_results"],
        "displacement": ["freecad_run_calculix", "aieng_postprocess_results"],
        "analysis": ["freecad_create_static_structural_analysis"],
        "deck": ["freecad_export_calculix_deck"],
        "claim": ["aieng_update_claim"],
        "validate": ["aieng_update_claim", "aieng_generate_audit_report"],
        "pass": ["aieng_update_claim"],
        "fail": ["aieng_update_claim"],
        "reference": ["aieng_build_reference_map", "aieng_mark_references_needing_review"],
        "traceability": ["aieng_build_reference_map", "aieng_mark_references_needing_review"],
        "audit": ["aieng_generate_audit_report"],
        "postprocess": ["aieng_postprocess_results"],
        "runtime": ["freecad_runtime_capabilities"],
        "capabilities": ["freecad_runtime_capabilities"],
    }

    matched_tool_names: set[str] = set()
    for keyword, tool_names in keywords.items():
        if keyword in outcome:
            matched_tool_names.update(tool_names)

    # Filter by category permissions
    if not request.allow_cad_operations:
        matched_tool_names = {
            n for n in matched_tool_names
            if _tool_by_name(n).category != "cad"
        }
    if not request.allow_cae_operations:
        matched_tool_names = {
            n for n in matched_tool_names
            if _tool_by_name(n).category != "cae"
        }
    if not request.allow_claim_update:
        matched_tool_names = {
            n for n in matched_tool_names
            if _tool_by_name(n).category != "claim"
        }

    # Build matched tool list (preserve catalog order, no ranking)
    for tool in _TOOL_CATALOG:
        if tool.tool_name in matched_tool_names:
            matched.append(tool)

    # If nothing matched, return a generic note instead of a fallback step
    if not matched:
        warns.append(
            f"Desired outcome '{request.desired_outcome}' did not match any known capability keywords. "
            "Review available tools and caller-defined workflow."
        )

    # Missing / unsupported analysis
    if "freecad_run_calculix" in matched_tool_names and not runtime.get("solver_available", False):
        unsupported.append("CalculiX solver not detected. freecad_run_calculix is unsupported.")
        missing.append("CalculiX solver not available in runtime.")

    if not runtime.get("freecad_available", False):
        # CAD tools need FreeCAD
        cad_tools = [t.tool_name for t in matched if t.category == "cad"]
        if cad_tools:
            unsupported.append("FreeCAD not detected. CAD tools require FreeCAD runtime.")
        # CAE tools need FreeCAD FEM
        cae_tools = [t.tool_name for t in matched if t.category == "cae"]
        if cae_tools:
            unsupported.append("FreeCAD not detected. CAE tools require FreeCAD FEM workbench.")

    if not runtime.get("fem_workbench", False):
        cae_tools = [t.tool_name for t in matched if t.category == "cae"]
        if cae_tools:
            unsupported.append("FEM workbench not available. CAE tools are unsupported.")

    if request.allow_cae_operations and not context.get("has_simulation_setup", False):
        cae_tools = [t.tool_name for t in matched if t.category == "cae"]
        if cae_tools:
            missing.append("No simulation/setup.yaml found in package. CAE inputs must be provided explicitly.")

    if "aieng_update_claim" in matched_tool_names:
        if not context.get("has_claims", False):
            missing.append("No claim_map.json found. Claim update requires an existing claim.")
        if not context.get("has_evidence", False):
            missing.append("No evidence_index.json found. Claim update requires evidence IDs.")

    return matched, missing, unsupported, warns


def _tool_by_name(name: str) -> CapabilityToolInfo:
    for tool in _TOOL_CATALOG:
        if tool.tool_name == name:
            return tool
    # Fallback for unknown names (should not happen with internal usage)
    return CapabilityToolInfo(tool_name=name, category="runtime", purpose="Unknown tool.")


def inspect_capabilities(request: CapabilityInspectionRequest) -> CapabilityInspectionSummary:
    """Inspect available capabilities, context, and gaps.

    This function is planning-neutral. It does not:
    - execute CAD/CAE operations
    - modify packages or files
    - advance claims
    - prescribe workflow sequences or ranking
    """
    runtime: dict[str, Any] = {}
    if request.include_runtime_capabilities:
        caps = detect_freecad_runtime()
        runtime = caps.model_dump(mode="json") if hasattr(caps, "model_dump") else dict(caps)

    context = _load_package_context(request.package_path)
    mode: Literal["standalone", "aieng_enhanced"] = (
        "aieng_enhanced" if context else "standalone"
    )

    tools, missing, unsupported, warns = _match_tools_by_outcome(request, runtime, context)

    # Build available_context list
    available_context: list[str] = []
    if context:
        available_context.append(f"package_path: {request.package_path}")
        if "manifest" in context:
            available_context.append("manifest.json available")
        if context.get("has_simulation_setup"):
            available_context.append("simulation/setup.yaml available")
        if context.get("has_evidence"):
            available_context.append("results/evidence_index.json available")
        if context.get("has_claims"):
            available_context.append("results/claim_map.json available")
    else:
        available_context.append("No .aieng package context provided (standalone mode).")

    # Build needs_review
    needs_review: list[str] = []
    if "freecad_apply_parameter_edit" in {t.tool_name for t in tools}:
        needs_review.append("CAD modification requires executable edit metadata review.")
    if "freecad_run_calculix" in {t.tool_name for t in tools}:
        needs_review.append("Solver execution requires deck validation and runtime verification.")
    if "aieng_update_claim" in {t.tool_name for t in tools}:
        needs_review.append("Claim update requires evidence ID verification and criteria review.")

    status: Literal["success", "partial", "unsupported"] = "success"
    if unsupported:
        status = "unsupported"
    elif missing or warns:
        status = "partial"

    return CapabilityInspectionSummary(
        status=status,
        mode=mode,
        desired_outcome=request.desired_outcome,
        available_context=available_context,
        available_runtime_capabilities=runtime,
        possibly_relevant_tools=tools,
        missing_information=missing,
        unsupported_operations=unsupported,
        needs_review=needs_review,
        policy_reminders=_DEFAULT_POLICY_REMINDERS.copy(),
        warnings=warns,
    )


# ---------------------------------------------------------------------------
# Backward-compatible wrapper (deprecated)
# ---------------------------------------------------------------------------

def plan_capabilities(request: CapabilityPlanRequest) -> CapabilityPlanSummary:
    """Deprecated: backward-compatible wrapper around inspect_capabilities.

    Prefer inspect_capabilities for new integrations.
    """
    warnings.warn(
        "plan_capabilities is deprecated; use inspect_capabilities instead",
        DeprecationWarning,
        stacklevel=2,
    )
    # Convert legacy request to new request
    new_request = CapabilityInspectionRequest(
        desired_outcome=request.desired_outcome,
        package_path=request.package_path,
        include_runtime_capabilities=request.include_runtime_capabilities,
        allow_cad_operations=request.allow_cad_operations,
        allow_cae_operations=request.allow_cae_operations,
        allow_claim_update=request.allow_claim_update,
    )
    summary = inspect_capabilities(new_request)

    # Convert new summary back to legacy format
    legacy_steps: list[CapabilityPlanStep] = []
    for tool in summary.possibly_relevant_tools:
        legacy_steps.append(
            CapabilityPlanStep(
                step_id=tool.tool_name,
                purpose=tool.purpose,
                suggested_tool=tool.tool_name,
                required_inputs=tool.required_inputs,
                expected_outputs=[],
                mutates_package=tool.mutates_package,
                mutates_cad=tool.mutates_cad,
                advances_claims=tool.may_update_claim_map,
                warnings=tool.notes + tool.side_effects,
            )
        )

    return CapabilityPlanSummary(
        status=summary.status,
        mode=summary.mode,
        desired_outcome=summary.desired_outcome or "",
        recommended_steps=legacy_steps,
        missing_information=summary.missing_information,
        unsupported_steps=summary.unsupported_operations,
        risks=summary.warnings + summary.needs_review,
        claim_policy_reminders=summary.policy_reminders,
    )
