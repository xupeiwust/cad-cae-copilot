"""Unified tool transparency registry for all MCP tools.

Provides machine-readable metadata about every tool's:
- category, purpose, inputs
- side effects (files written, indices updated)
- CAD / .aieng / claim_map mutability
- runtime requirements
- dry-run support level
- default claim policy

This registry is the source of truth for inspection, preview, and audit.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolClaimPolicy(BaseModel):
    """Claim-policy declaration for a tool entry."""

    model_config = ConfigDict(extra="forbid")

    claims_advanced_default: bool = False
    requires_explicit_update_claim: bool = True
    may_auto_advance: bool = False


class ToolRegistryEntry(BaseModel):
    """Machine-readable metadata for a single MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    category: Literal[
        "cad", "cae", "reference", "evidence", "claim", "runtime", "audit", "orchestration"
    ]
    purpose: str
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    mutates_cad: bool = False
    mutates_package: bool = False
    may_update_claim_map: bool = False
    runtime_requirements: list[Literal["freecad", "fem", "mesher", "solver", "none"]] = Field(
        default_factory=list
    )
    dry_run_support: Literal["full", "partial", "none"] = "none"
    claim_policy: ToolClaimPolicy = Field(default_factory=ToolClaimPolicy)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry data
# ---------------------------------------------------------------------------

_REGISTRY: list[ToolRegistryEntry] = [
    # ------------------------------------------------------------------
    # CAD tools (tools_cad)
    # ------------------------------------------------------------------
    ToolRegistryEntry(
        tool_name="cad_get_version",
        category="cad",
        purpose="Get FreeCAD version and runtime info.",
        required_inputs=[],
        optional_inputs=["package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_document",
        category="cad",
        purpose="Create a new FreeCAD document.",
        required_inputs=[],
        optional_inputs=["name", "label"],
        side_effects=["Creates new FreeCAD document in memory"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_save_document",
        category="cad",
        purpose="Save a FreeCAD document to disk.",
        required_inputs=[],
        optional_inputs=["doc_name", "path"],
        side_effects=["Writes .FCStd file to disk"],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_close_document",
        category="cad",
        purpose="Close a FreeCAD document, optionally saving first.",
        required_inputs=[],
        optional_inputs=["doc_name", "save_changes"],
        side_effects=["Closes document in FreeCAD memory", "May write .FCStd if save_changes=True"],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_list_documents",
        category="cad",
        purpose="List all open FreeCAD documents.",
        required_inputs=[],
        optional_inputs=["package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_list_objects",
        category="cad",
        purpose="List all objects in a FreeCAD document.",
        required_inputs=[],
        optional_inputs=["doc_name", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_inspect_object",
        category="cad",
        purpose="Get detailed info (bbox, volume, faces, edges) about a FreeCAD object.",
        required_inputs=["object_name"],
        optional_inputs=["doc_name", "include_shape", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_delete_object",
        category="cad",
        purpose="Delete an object from a FreeCAD document.",
        required_inputs=["object_name"],
        optional_inputs=["doc_name"],
        side_effects=["Removes object from document", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_set_placement",
        category="cad",
        purpose="Set object position and rotation.",
        required_inputs=["object_name"],
        optional_inputs=["x", "y", "z", "rotation", "doc_name"],
        side_effects=["Modifies object Placement", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_box",
        category="cad",
        purpose="Create a Part::Box primitive.",
        required_inputs=[],
        optional_inputs=["length", "width", "height", "name", "doc_name"],
        side_effects=["Adds new object to document", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_cylinder",
        category="cad",
        purpose="Create a Part::Cylinder primitive.",
        required_inputs=[],
        optional_inputs=["radius", "height", "angle", "name", "doc_name"],
        side_effects=["Adds new object to document", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_sphere",
        category="cad",
        purpose="Create a Part::Sphere primitive.",
        required_inputs=[],
        optional_inputs=["radius", "name", "doc_name"],
        side_effects=["Adds new object to document", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_cone",
        category="cad",
        purpose="Create a Part::Cone primitive.",
        required_inputs=[],
        optional_inputs=["radius1", "radius2", "height", "name", "doc_name"],
        side_effects=["Adds new object to document", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_partdesign_body",
        category="cad",
        purpose="Create a PartDesign::Body container.",
        required_inputs=[],
        optional_inputs=["name", "doc_name"],
        side_effects=["Adds new body to document", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_create_sketch",
        category="cad",
        purpose="Create a Sketch attached to a PartDesign Body or standalone.",
        required_inputs=[],
        optional_inputs=["body_name", "plane", "name", "doc_name"],
        side_effects=["Adds new sketch to document/body", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_pad_sketch",
        category="cad",
        purpose="Create a Pad (extrusion) from a sketch inside a PartDesign Body.",
        required_inputs=["sketch_name", "length"],
        optional_inputs=["symmetric", "reversed", "name", "doc_name"],
        side_effects=["Adds Pad feature to body", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_pocket_sketch",
        category="cad",
        purpose="Create a Pocket (cut extrusion) from a sketch inside a PartDesign Body.",
        required_inputs=["sketch_name", "length"],
        optional_inputs=["pocket_type", "name", "doc_name"],
        side_effects=["Adds Pocket feature to body", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_fillet_edges",
        category="cad",
        purpose="Add fillet (rounded edges) to an object.",
        required_inputs=["object_name", "radius"],
        optional_inputs=["edges", "name", "doc_name"],
        side_effects=["Adds Fillet feature", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_chamfer_edges",
        category="cad",
        purpose="Add chamfer (beveled edges) to an object.",
        required_inputs=["object_name", "size"],
        optional_inputs=["edges", "name", "doc_name"],
        side_effects=["Adds Chamfer feature", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_boolean_fuse",
        category="cad",
        purpose="Fuse (union) multiple objects.",
        required_inputs=["objects"],
        optional_inputs=["name", "doc_name"],
        side_effects=["Creates new fused object", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_boolean_cut",
        category="cad",
        purpose="Cut one object from another.",
        required_inputs=["base", "tool"],
        optional_inputs=["name", "doc_name"],
        side_effects=["Creates new cut object", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_boolean_common",
        category="cad",
        purpose="Intersect (common) multiple objects.",
        required_inputs=["objects"],
        optional_inputs=["name", "doc_name"],
        side_effects=["Creates new common object", "Triggers recompute"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cad_export_step",
        category="cad",
        purpose="Export objects to STEP format.",
        required_inputs=["file_path"],
        optional_inputs=["doc_name", "object_names", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes .step file to disk"],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["dry_run will validate inputs but cannot preview file content without FreeCAD"],
    ),
    ToolRegistryEntry(
        tool_name="cad_export_fcstd",
        category="cad",
        purpose="Export document to FCStd format.",
        required_inputs=["file_path"],
        optional_inputs=["doc_name", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes .FCStd file to disk"],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["dry_run will validate inputs but cannot preview file content without FreeCAD"],
    ),
    ToolRegistryEntry(
        tool_name="cad_set_parameter",
        category="cad",
        purpose="Set a parametric property on an object and recompute.",
        required_inputs=["object_name", "parameter_name", "value"],
        optional_inputs=["doc_name", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Modifies object parameter", "Triggers recompute", "May change topology"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
        notes=["Topology-stable face IDs are not guaranteed after parameter change"],
    ),
    ToolRegistryEntry(
        tool_name="cad_import_step",
        category="cad",
        purpose="Import a STEP file into the active document.",
        required_inputs=["file_path"],
        optional_inputs=["doc_name", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Adds imported objects to document"],
        mutates_cad=True,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="none",
        claim_policy=ToolClaimPolicy(),
    ),
    # ------------------------------------------------------------------
    # CAE tools (tools_cae/server.py)
    # ------------------------------------------------------------------
    ToolRegistryEntry(
        tool_name="aieng_inspect_context",
        category="cae",
        purpose="Inspect an optional .aieng package and report available resources.",
        required_inputs=[],
        optional_inputs=["package_path"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cae_create_analysis",
        category="cae",
        purpose="Create a structured CAE analysis spec for the current task and CAD spec.",
        required_inputs=["run_dir", "task_spec", "cad_spec"],
        optional_inputs=["stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes analysis spec to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cae_generate_mesh",
        category="cae",
        purpose="Prepare geometry, generate mesh, assign material, and apply boundary conditions.",
        required_inputs=["run_dir", "cad_spec", "build_result", "analysis_spec"],
        optional_inputs=["stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes mesh files to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "mesher"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Surrogate backend does not require FreeCAD mesher"],
    ),
    ToolRegistryEntry(
        tool_name="cae_run_static_analysis",
        category="cae",
        purpose="Run a static structural analysis through the CAE facade.",
        required_inputs=["run_dir", "task_spec", "cad_spec", "analysis_spec", "mass_properties"],
        optional_inputs=["stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes solver output to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem", "solver"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Surrogate backend runs without FreeCAD; real FEM requires CalculiX"],
    ),
    ToolRegistryEntry(
        tool_name="cae_extract_results",
        category="cae",
        purpose="Convert solver output into a structured CAE result summary.",
        required_inputs=["run_dir", "task_spec", "analysis_spec", "solver_output"],
        optional_inputs=["stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes result summary to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cae_generate_report_data",
        category="cae",
        purpose="Build the structured CAE report payload for the current run.",
        required_inputs=["run_dir", "task_spec", "cad_spec", "analysis_spec", "mass_properties", "result_summary"],
        optional_inputs=["stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes report data to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="cae_inspect_geometry",
        category="cae",
        purpose="Inspect a solid's faces and get geometric suggestions for FEM setup.",
        required_inputs=["document_path", "object_name"],
        optional_inputs=["doc_name", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
        notes=["Requires FreeCAD FEM backend; not available with surrogate"],
    ),
    ToolRegistryEntry(
        tool_name="cae_run_thermal_analysis",
        category="cae",
        purpose="Run a steady-state thermal analysis.",
        required_inputs=["run_dir", "thermal_spec"],
        optional_inputs=["cad_spec", "stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes solver output to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem", "solver"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Surrogate: 1D conduction formula; Real FEM: experimental"],
    ),
    ToolRegistryEntry(
        tool_name="cae_run_modal_analysis",
        category="cae",
        purpose="Run a modal (natural frequency) analysis.",
        required_inputs=["run_dir", "modal_spec"],
        optional_inputs=["cad_spec", "stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes solver output to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem", "solver"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Surrogate: Euler-Bernoulli cantilever beam; Real FEM: experimental"],
    ),
    ToolRegistryEntry(
        tool_name="cae_run_buckling_analysis",
        category="cae",
        purpose="Run a linear buckling analysis.",
        required_inputs=["run_dir", "buckling_spec"],
        optional_inputs=["cad_spec", "stage", "package_path", "persist_to_aieng", "target_feature_id"],
        side_effects=["Writes solver output to run_dir", "May append to tool_trace.jsonl"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem", "solver"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Surrogate: Euler column buckling formula; Real FEM: experimental"],
    ),
    # ------------------------------------------------------------------
    # .aieng bridge / reference tools (tools_aieng)
    # ------------------------------------------------------------------
    ToolRegistryEntry(
        tool_name="aieng_parse_patch",
        category="evidence",
        purpose="Parse an .aieng patch proposal without executing anything.",
        required_inputs=[],
        optional_inputs=["package_path", "patch_path", "patch_json"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="aieng_execute_patch",
        category="evidence",
        purpose="Execute an .aieng patch proposal with guard checks and optional persistence.",
        required_inputs=[],
        optional_inputs=[
            "package_path", "patch_path", "patch_json", "persist_to_aieng",
            "dry_run", "export_modified_step", "export_modified_fcstd", "artifact_output_dir",
        ],
        side_effects=[
            "May modify CAD model",
            "May write .step / .FCStd artifacts",
            "May write evidence_index.json",
            "May write tool_trace.json",
        ],
        mutates_cad=True,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["dry_run=True skips execution but returns planned steps"],
    ),
    ToolRegistryEntry(
        tool_name="aieng_run_cad_to_cae_workflow",
        category="orchestration",
        purpose="Optional explicit CAD/CAE evidence orchestration helper.",
        required_inputs=[],
        optional_inputs=[
            "package_path", "patch_path", "patch_json", "persist_to_aieng", "dry_run",
            "export_modified_fcstd", "export_modified_step", "run_mesh", "export_solver_deck",
            "run_solver", "import_solver_evidence", "run_postprocess", "export_postprocess_csv",
            "export_postprocess_vtk", "analysis_type", "stop_on_failure",
        ],
        side_effects=[
            "May modify CAD model",
            "May write mesh/solver/deck artifacts",
            "May write evidence_index.json",
            "May write tool_trace.json",
        ],
        mutates_cad=True,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem", "mesher", "solver"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=[
            "This is an optional orchestration convenience, not a default pipeline",
            "CAD and CAE are independent first-class workflows",
        ],
    ),
    ToolRegistryEntry(
        tool_name="aieng_orchestrate_cad_cae_sequence",
        category="orchestration",
        purpose="Alias for aieng_run_cad_to_cae_workflow.",
        required_inputs=[],
        optional_inputs=[],
        side_effects=[],
        mutates_cad=True,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["freecad", "fem", "mesher", "solver"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Deprecated alias"],
    ),
    ToolRegistryEntry(
        tool_name="aieng_postprocess_results",
        category="evidence",
        purpose="Post-process CAE results: extract metrics and export artifacts.",
        required_inputs=[],
        optional_inputs=[
            "package_path", "result_source", "persist_to_aieng", "export_csv",
            "export_vtk", "output_dir", "producer_kind", "analysis_type",
        ],
        side_effects=["May write CSV/VTK artifacts", "May write evidence_index.json"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Surrogate outputs are not solver evidence"],
    ),
    ToolRegistryEntry(
        tool_name="aieng_update_claim",
        category="claim",
        purpose="Explicitly update a claim status based on evidence and criteria.",
        required_inputs=["package_path", "claim_id", "evidence_ids"],
        optional_inputs=["decision_criteria", "requested_status", "mode", "rationale", "dry_run"],
        side_effects=["Writes claim_map.json"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=True,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(
            claims_advanced_default=False,
            requires_explicit_update_claim=True,
            may_auto_advance=False,
        ),
        notes=["This is the ONLY tool allowed to modify claim_map.json"],
    ),
    ToolRegistryEntry(
        tool_name="aieng_get_reference_map",
        category="reference",
        purpose="Read-only: get the current reference map for an .aieng package.",
        required_inputs=["package_path"],
        optional_inputs=[],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="aieng_build_reference_map",
        category="reference",
        purpose="Build and optionally persist a reference map.",
        required_inputs=["package_path"],
        optional_inputs=["persist"],
        side_effects=["Writes objects/reference_map.json when persist=True"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="aieng_mark_references_needing_review",
        category="reference",
        purpose="Mark references as needing review after geometry changes.",
        required_inputs=["package_path", "affected_feature_ids"],
        optional_inputs=["reason"],
        side_effects=["Updates objects/reference_map.json"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="aieng_inspect_capabilities",
        category="runtime",
        purpose="Inspect available capabilities, context, and gaps for a desired outcome.",
        required_inputs=[],
        optional_inputs=[
            "desired_outcome", "package_path", "include_runtime_capabilities",
            "allow_cad_operations", "allow_cae_operations", "allow_claim_update",
        ],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    ToolRegistryEntry(
        tool_name="aieng_plan_capabilities",
        category="runtime",
        purpose="Deprecated alias for aieng_inspect_capabilities.",
        required_inputs=[],
        optional_inputs=[],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
        notes=["Deprecated: use aieng_inspect_capabilities"],
    ),
    ToolRegistryEntry(
        tool_name="aieng_read_design_targets",
        category="evidence",
        purpose="Read-only: inspect design targets from an .aieng package.",
        required_inputs=["package_path"],
        optional_inputs=[],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
        notes=[
            "Read-only inspection tool",
            "Does not mutate package",
            "Does not advance claims",
            "Safe for agent preflight",
        ],
    ),
    ToolRegistryEntry(
        tool_name="aieng_read_design_target_comparisons",
        category="evidence",
        purpose="Read-only: inspect design target comparisons from an .aieng package.",
        required_inputs=["package_path"],
        optional_inputs=[],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
        notes=[
            "Read-only inspection tool",
            "Does not generate comparisons automatically",
            "Does not mutate package",
            "Does not advance claims",
            "Safe for agent preflight",
        ],
    ),
    ToolRegistryEntry(
        tool_name="aieng_generate_audit_report",
        category="audit",
        purpose="Generate an audit report for an .aieng package.",
        required_inputs=["package_path"],
        optional_inputs=["output_markdown", "output_json"],
        side_effects=["Writes reports/audit_report.json", "May write reports/audit_report.md"],
        mutates_cad=False,
        mutates_package=True,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="partial",
        claim_policy=ToolClaimPolicy(),
        notes=["Read-only except for writing the audit report itself"],
    ),
    ToolRegistryEntry(
        tool_name="freecad_runtime_capabilities",
        category="runtime",
        purpose="Detect FreeCAD, FEM, meshers, and solver runtime capabilities.",
        required_inputs=[],
        optional_inputs=[],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
    # ------------------------------------------------------------------
    # Registry introspection tool itself
    # ------------------------------------------------------------------
    ToolRegistryEntry(
        tool_name="aieng_tool_registry_query",
        category="runtime",
        purpose="Query the unified tool transparency registry.",
        required_inputs=[],
        optional_inputs=["category", "keyword", "mutability"],
        side_effects=[],
        mutates_cad=False,
        mutates_package=False,
        may_update_claim_map=False,
        runtime_requirements=["none"],
        dry_run_support="full",
        claim_policy=ToolClaimPolicy(),
    ),
]


# ---------------------------------------------------------------------------
# Registry API
# ---------------------------------------------------------------------------

class ToolRegistry:
    """In-memory tool registry with filtering and lookup."""

    def __init__(self, entries: list[ToolRegistryEntry] | None = None) -> None:
        self._entries: list[ToolRegistryEntry] = list(entries) if entries is not None else []
        self._by_name: dict[str, ToolRegistryEntry] = {e.tool_name: e for e in self._entries}

    def get(self, tool_name: str) -> ToolRegistryEntry | None:
        """Lookup a single tool by exact name."""
        return self._by_name.get(tool_name)

    def list_all(self) -> list[ToolRegistryEntry]:
        """Return all entries."""
        return list(self._entries)

    def filter(
        self,
        category: str | None = None,
        keyword: str | None = None,
        mutability: str | None = None,
    ) -> list[ToolRegistryEntry]:
        """Filter registry entries.

        Args:
            category: Exact category match.
            keyword: Substring match against tool_name, purpose, or notes.
            mutability: One of "any", "cad", "package", "claim_map", "none".
                "cad" -> mutates_cad=True
                "package" -> mutates_package=True
                "claim_map" -> may_update_claim_map=True
                "none" -> none of the above
                "any" -> at least one of the above
        """
        results = list(self._entries)

        if category is not None:
            results = [e for e in results if e.category == category]

        if keyword is not None:
            kw = keyword.lower()
            results = [
                e
                for e in results
                if kw in e.tool_name.lower()
                or kw in e.purpose.lower()
                or any(kw in n.lower() for n in e.notes)
            ]

        if mutability is not None:
            if mutability == "cad":
                results = [e for e in results if e.mutates_cad]
            elif mutability == "package":
                results = [e for e in results if e.mutates_package]
            elif mutability == "claim_map":
                results = [e for e in results if e.may_update_claim_map]
            elif mutability == "none":
                results = [
                    e for e in results if not e.mutates_cad and not e.mutates_package and not e.may_update_claim_map
                ]
            elif mutability == "any":
                results = [
                    e for e in results if e.mutates_cad or e.mutates_package or e.may_update_claim_map
                ]

        return results

    def model_dump(self, mode: str = "json") -> list[dict[str, Any]]:
        """Serialize all entries to plain dicts."""
        return [e.model_dump(mode=mode) for e in self._entries]


def default_registry() -> ToolRegistry:
    """Return the built-in registry populated with all known tools."""
    return ToolRegistry(_REGISTRY)
