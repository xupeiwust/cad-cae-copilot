from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ai.patch_proposer import propose_patch_package
from .converters.base import ConverterError
from .converters.cli_runners import (
    convert_source,
    list_converter_capabilities,
    readiness_report_payload,
    readiness_report_text,
)
from .task.task_spec_writer import write_task_spec_package
from .task.external_tool_requirements_writer import write_external_tool_requirements_package
from .provenance.tool_trace_writer import record_trace_package
from .results.evidence_writer import (
    record_evidence_package,
    write_evidence_scaffold_package,
)
from .patch.executor import PatchNotExecutable, apply_patch_package
from .simulation.deck_exporter import export_updated_deck_package
from .ai.summary_writer import summarize_package
from .context.apply_context import apply_context_package
from .definition import define_package
from .geometry.backend import detect_occ_runtime
from .geometry.step_importer import import_step_package
from .geometry.topology_extractor import extract_topology_package
from .graph.aag import build_aag_package
from .graph.allowed_operations_catalog_writer import build_allowed_operations_catalog_package
from .graph.feature_graph import recognize_features_package
from .assembly.assembly_graph_writer import build_assembly_graph_package
from .objects.interface_graph_writer import build_interface_graph_package
from .objects.registry_writer import build_object_registry_package
from .package import create_package
from .simulation.cae_deck_importer import import_cae_deck_package
from .simulation.cae_mapping_applier import apply_cae_mapping_package
from .simulation.calculix_exporter import export_calculix_package
from .simulation.deck_generator import generate_solver_input_package
from .simulation.mesh_handoff_writer import write_mesh_handoff_package
from .simulation.mesh_evidence_importer import import_mesh_evidence_package
from .simulation.solver_evidence_importer import import_solver_evidence_package
from .modeling_plan.planner import RuleBasedModelingPlanner
from .modeling_plan.validate import validate_modeling_plan, validate_modeling_plan_file
from .orchestration.init_from_plan import init_from_plan
from .validate import validate_package
from .validation.completeness_writer import write_completeness_report_package
from .validation.evidence_report_writer import write_evidence_report_package
from .validation.status_writer import update_validation_status_package
from .visual.annotation_writer import build_visual_index_package
from .visual.model_manifest_writer import build_visual_manifest_package
from .reference import inspect_ref, list_refs, ref_check_package


def _parse_csv_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aieng", description="Tools for .aieng engineering data packages")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create an empty .aieng package")
    init_parser.add_argument("--model-id", required=True, help="Stable model identifier")
    init_parser.add_argument("--out", required=True, help="Output .aieng package path")
    init_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing package")
    init_parser.add_argument(
        "--design-targets",
        help="Optional task/design_targets.yaml file to include in the new package",
    )

    import_step_parser = subparsers.add_parser(
        "import-step",
        help="Import a STEP file as geometry resources (evidence-only import; no automatic claim updates)",
    )
    import_step_parser.add_argument("step_file", help="Input .step or .stp file")
    import_step_parser.add_argument("--out", required=True, help="Output .aieng package path")
    import_step_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing package")

    define_parser = subparsers.add_parser(
        "define",
        help="Create a definition-sourced .aieng package from structured YAML",
    )
    define_parser.add_argument("definition_yaml", help="Input structured model definition YAML")
    define_parser.add_argument("--out", required=True, help="Output .aieng package path")
    define_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing package")

    convert_parser = subparsers.add_parser(
        "convert",
        help=(
            "Convert a CAD/CAE source file into a .aieng package via a registered "
            "converter (Phase 20). Read-only semantic conversion; no solver, mesh, "
            "or CAD edit is executed."
        ),
    )
    convert_parser.add_argument("source", help="Input CAD/CAE source file (e.g. .FCStd)")
    convert_parser.add_argument("--out", required=True, help="Output .aieng package path")
    convert_parser.add_argument(
        "--converter",
        default=None,
        help="Converter id to use (default: inferred from source extension). See 'aieng converter-capabilities'.",
    )
    convert_parser.add_argument(
        "--model-id",
        default=None,
        help="Stable model identifier (default: inferred from output filename)",
    )
    convert_parser.add_argument(
        "--runtime-mode",
        default="auto",
        choices=["auto", "offline", "runtime"],
        help="Whether to use the source tool's runtime API if available (default: auto)",
    )
    convert_parser.add_argument(
        "--no-embed-capabilities",
        action="store_true",
        help="Do not embed provenance/converter_capabilities.json in the package",
    )
    convert_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing package")

    subparsers.add_parser(
        "converter-capabilities",
        help="List registered CAD/CAE-to-.aieng converters and their declared capability profiles",
    )

    readiness_parser = subparsers.add_parser(
        "readiness-report",
        help=(
            "Print a structured AI-readability / readiness report derived from an existing "
            "converter-produced .aieng package. No external tool is executed."
        ),
    )
    readiness_parser.add_argument("package", help="Path to a .aieng package")
    readiness_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON",
    )

    extract_topology_parser = subparsers.add_parser(
        "extract-topology",
        help="Generate a topology map for an existing .aieng package",
    )
    extract_topology_parser.add_argument("package", help="Path to a .aieng package")
    extract_topology_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing geometry/topology_map.json",
    )
    extract_topology_parser.add_argument(
        "--backend",
        default="auto",
        help="Geometry backend to use (default: auto; supported: auto, mock, occ[experimental])",
    )

    write_mesh_handoff_parser = subparsers.add_parser(
        "write-mesh-handoff",
        help="Write simulation/mesh_handoff_contract.json for external meshing handoff",
    )
    write_mesh_handoff_parser.add_argument("package", help="Path to a .aieng package")
    write_mesh_handoff_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing simulation/mesh_handoff_contract.json",
    )

    recognize_features_parser = subparsers.add_parser(
        "recognize-features",
        help="Generate a rule-based feature graph from topology_map.json",
    )
    recognize_features_parser.add_argument("package", help="Path to a .aieng package")
    recognize_features_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing graph/feature_graph.json",
    )

    build_aag_parser = subparsers.add_parser(
        "build-aag",
        help="Generate an attributed adjacency graph from geometry/topology_map.json",
    )
    build_aag_parser.add_argument("package", help="Path to a .aieng package")
    build_aag_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing graph/aag.json",
    )

    apply_context_parser = subparsers.add_parser(
        "apply-context",
        help="Apply user engineering context YAML to structured resources",
    )
    apply_context_parser.add_argument("package", help="Path to a .aieng package")
    apply_context_parser.add_argument("--context", required=True, help="Path to context YAML")
    apply_context_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated context resources",
    )

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Generate AI-readable derived summaries from structured resources",
    )
    summarize_parser.add_argument("package", help="Path to a .aieng package")
    summarize_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing README_FOR_AI.md and ai/summary.md",
    )

    apply_patch_parser = subparsers.add_parser(
        "apply-patch",
        help="Execute an accepted patch proposal and update feature parameters (Phase 13B)",
    )
    apply_patch_parser.add_argument("package", help="Path to a .aieng package")
    apply_patch_parser.add_argument("--patch", required=True, help="Patch ID to execute (e.g. patch_0001)")
    apply_patch_parser.add_argument("--out", help="Optional path to copy the modified STEP file")
    apply_patch_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing execution output")

    propose_patch_parser = subparsers.add_parser(
        "propose-patch",
        help="Generate a structured unexecuted patch proposal from package resources",
    )
    propose_patch_parser.add_argument("package", help="Path to a .aieng package")
    propose_patch_parser.add_argument("--intent", required=True, help="User intent for the proposed engineering change")

    export_updated_deck_parser = subparsers.add_parser(
        "export-updated-deck",
        help="Export an updated CalculiX deck reflecting the current simulation/setup.yaml (Phase 13C)",
    )
    export_updated_deck_parser.add_argument("package", help="Path to a .aieng package")
    export_updated_deck_parser.add_argument("--out", help="Optional external path to copy the updated deck")
    export_updated_deck_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing updated deck")

    export_calculix_parser = subparsers.add_parser(
        "export-calculix",
        help="Export a CalculiX scaffold deck from simulation/setup.yaml",
    )
    export_calculix_parser.add_argument("package", help="Path to a .aieng package")
    export_calculix_parser.add_argument(
        "--out",
        default=None,
        help="Optional external output path for the scaffold deck (e.g. build/solver_deck.inp)",
    )
    export_calculix_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing solver_deck.inp inside the package and/or --out path",
    )

    generate_solver_input_parser = subparsers.add_parser(
        "generate-solver-input",
        help="Generate a runnable CalculiX solver input deck from existing setup artifacts (Phase 33)",
    )
    generate_solver_input_parser.add_argument("package", help="Path to a .aieng package")
    generate_solver_input_parser.add_argument(
        "--run-id",
        default="run_001",
        help="Solver run identifier (default: run_001)",
    )
    generate_solver_input_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing solver input deck for this run_id",
    )

    extract_field_regions_parser = subparsers.add_parser(
        "extract-field-regions",
        help="Extract high-magnitude field clusters from a CalculiX FRD file (Phase 31)",
    )
    extract_field_regions_parser.add_argument("package", help="Path to a .aieng package")
    extract_field_regions_parser.add_argument("--frd", required=True, help="Path to external CalculiX .frd file")
    extract_field_regions_parser.add_argument("--field", default="S", help="FRD field to analyze (default: S)")
    extract_field_regions_parser.add_argument("--metric", default="von_mises", help="Metric to compute (default: von_mises)")
    extract_field_regions_parser.add_argument("--max-clusters", type=int, default=3, help="Maximum clusters to return")
    extract_field_regions_parser.add_argument(
        "--threshold-percentile",
        type=float,
        default=90.0,
        help="Percentile cutoff for high-magnitude nodes",
    )
    extract_field_regions_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing field_regions.json")

    import_cae_deck_parser = subparsers.add_parser(
        "import-cae-deck",
        help="Import a minimal CAE deck scaffold into simulation/cae_imports resources",
    )
    import_cae_deck_parser.add_argument("package", help="Path to a .aieng package")
    import_cae_deck_parser.add_argument("--deck", required=True, help="Path to external CAE solver deck text file")
    import_cae_deck_parser.add_argument(
        "--format",
        required=True,
        help="CAE deck format (Phase 10A supports: calculix)",
    )
    import_cae_deck_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing simulation/cae_imports resources",
    )

    apply_cae_mapping_parser = subparsers.add_parser(
        "apply-cae-mapping",
        help="Apply explicit user-provided CAE entity mappings to simulation/cae_mapping.json",
    )
    apply_cae_mapping_parser.add_argument("package", help="Path to a .aieng package")
    apply_cae_mapping_parser.add_argument(
        "--mapping",
        required=True,
        help="Path to CAE mapping YAML file",
    )
    apply_cae_mapping_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing mapped CAE entries",
    )

    update_validation_status_parser = subparsers.add_parser(
        "update-validation-status",
        help="Generate validation/status.yaml for an existing .aieng package",
    )
    update_validation_status_parser.add_argument("package", help="Path to a .aieng package")
    update_validation_status_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing validation/status.yaml",
    )

    write_completeness_parser = subparsers.add_parser(
        "write-completeness-report",
        help="Write validation/completeness_report.json with explicit available/partial/missing/unsupported information",
    )
    write_completeness_parser.add_argument("package", help="Path to a .aieng package")
    write_completeness_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing validation/completeness_report.json",
    )

    write_evidence_report_parser = subparsers.add_parser(
        "write-evidence-report",
        help="Write validation/evidence_report.json as a consolidated derived view from validation and results ledgers",
    )
    write_evidence_report_parser.add_argument("package", help="Path to a .aieng package")
    write_evidence_report_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing validation/evidence_report.json",
    )

    build_visual_index_parser = subparsers.add_parser(
        "build-visual-index",
        help="Generate visual/annotation_layers.json for an existing .aieng package",
    )
    build_visual_index_parser.add_argument("package", help="Path to a .aieng package")
    build_visual_index_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing visual/annotation_layers.json",
    )

    build_visual_manifest_parser = subparsers.add_parser(
        "build-visual-manifest",
        help="Generate visual/model_manifest.json for an existing .aieng package",
    )
    build_visual_manifest_parser.add_argument("package", help="Path to a .aieng package")
    build_visual_manifest_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing visual/model_manifest.json",
    )

    build_object_registry_parser = subparsers.add_parser(
        "build-object-registry",
        help="Generate objects/object_registry.json for an existing .aieng package",
    )
    build_object_registry_parser.add_argument("package", help="Path to a .aieng package")
    build_object_registry_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing objects/object_registry.json",
    )

    build_interface_graph_parser = subparsers.add_parser(
        "build-interface-graph",
        help="Generate objects/interface_graph.json for an existing .aieng package",
    )
    build_interface_graph_parser.add_argument("package", help="Path to a .aieng package")
    build_interface_graph_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing objects/interface_graph.json",
    )

    build_assembly_graph_parser = subparsers.add_parser(
        "build-assembly-graph",
        help="Generate assembly/assembly_graph.json for an existing .aieng package",
    )
    build_assembly_graph_parser.add_argument("package", help="Path to a .aieng package")
    build_assembly_graph_parser.add_argument(
        "--definition",
        required=True,
        metavar="YAML",
        help="Path to the assembly definition YAML file",
    )
    build_assembly_graph_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing assembly/assembly_graph.json",
    )

    build_allowed_operations_catalog_parser = subparsers.add_parser(
        "build-allowed-operations-catalog",
        help="Generate graph/allowed_operations_catalog.json for an existing .aieng package",
    )
    build_allowed_operations_catalog_parser.add_argument("package", help="Path to a .aieng package")
    build_allowed_operations_catalog_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing graph/allowed_operations_catalog.json",
    )

    write_task_spec_parser = subparsers.add_parser(
        "write-task-spec",
        help="Write a structured task specification (task/task_spec.yaml) to an existing .aieng package",
    )
    write_task_spec_parser.add_argument("package", help="Path to a .aieng package")
    write_task_spec_parser.add_argument(
        "--intent",
        required=True,
        help="Human-readable task intent (e.g. 'Reduce mass by 15%% while keeping mounting holes unchanged.')",
    )
    write_task_spec_parser.add_argument(
        "--task-id",
        default=None,
        help="Stable task identifier (default: task_001)",
    )
    write_task_spec_parser.add_argument(
        "--mode",
        default="proposal_only",
        help="Task execution mode: proposal_only | analysis_ready | execution_ready (default: proposal_only)",
    )
    write_task_spec_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing task/task_spec.yaml",
    )

    write_ext_tool_req_parser = subparsers.add_parser(
        "write-external-tool-requirements",
        help="Write a structured external tool handoff contract (task/external_tool_requirements.json) to an existing .aieng package",
    )
    write_ext_tool_req_parser.add_argument("package", help="Path to a .aieng package")
    write_ext_tool_req_parser.add_argument(
        "--handoff-id",
        default=None,
        help="Stable handoff identifier (default: handoff_001)",
    )
    write_ext_tool_req_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing task/external_tool_requirements.json",
    )

    write_evidence_parser = subparsers.add_parser(
        "write-evidence-scaffold",
        help="Write results/evidence_index.json to an existing .aieng package",
    )
    write_evidence_parser.add_argument("package", help="Path to a .aieng package")
    write_evidence_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing evidence_index.json",
    )

    record_evidence_parser = subparsers.add_parser(
        "record-evidence",
        help="Record externally produced evidence into results/evidence_index.json",
    )
    record_evidence_parser.add_argument("package", help="Path to a .aieng package")
    record_evidence_parser.add_argument(
        "--kind",
        required=True,
        choices=["solver_result", "mesh_evidence", "geometry_modification", "validation_report"],
        help="Evidence type to record",
    )
    record_evidence_parser.add_argument(
        "--producer-kind",
        required=True,
        choices=["external_cad", "external_cae", "external_solver", "external_agent", "aieng_core"],
        help="Producer category",
    )
    record_evidence_parser.add_argument(
        "--producer-tool",
        required=True,
        help="Producer tool identifier",
    )
    record_evidence_parser.add_argument(
        "--artifact-kind",
        required=True,
        choices=["yaml", "json", "inp", "step", "result_file"],
        help="Artifact file kind",
    )
    record_evidence_parser.add_argument(
        "--artifact-path",
        required=True,
        help="Artifact path in package or external reference",
    )
    record_evidence_parser.add_argument(
        "--claim-support",
        required=True,
        help="Comma-separated claim IDs supported by this evidence",
    )
    record_evidence_parser.add_argument(
        "--evidence-id",
        default=None,
        help="Optional explicit evidence ID (default: deterministic next ID by evidence kind)",
    )
    record_evidence_parser.add_argument(
        "--verification-status",
        default="available",
        choices=["available", "missing", "unverified", "schema_validated"],
        help="Evidence verification status (default: available)",
    )
    record_evidence_parser.add_argument(
        "--notes",
        action="append",
        default=[],
        help="Optional note; repeat --notes for multiple lines",
    )

    import_solver_evidence_parser = subparsers.add_parser(
        "import-solver-evidence",
        help="Import external solver result artifact as evidence-only writeback (no automatic claim status change)",
    )
    import_solver_evidence_parser.add_argument("package", help="Path to a .aieng package")
    import_solver_evidence_parser.add_argument(
        "--result-file",
        required=True,
        help="Path to external solver result file",
    )
    import_solver_evidence_parser.add_argument(
        "--format",
        required=True,
        choices=["calculix_dat"],
        help="Result format (currently supported: calculix_dat)",
    )
    import_solver_evidence_parser.add_argument(
        "--producer-tool",
        default="calculix",
        help="External solver tool identifier (default: calculix)",
    )
    import_solver_evidence_parser.add_argument(
        "--claim-support",
        default="claim_solver_result_001",
        help="Comma-separated claim IDs supported by this evidence (default: claim_solver_result_001)",
    )
    import_solver_evidence_parser.add_argument(
        "--verification-status",
        default="unverified",
        choices=["available", "missing", "unverified", "schema_validated"],
        help="Evidence verification status (default: unverified)",
    )
    import_solver_evidence_parser.add_argument(
        "--evidence-id",
        default=None,
        help="Optional explicit evidence ID",
    )
    import_solver_evidence_parser.add_argument(
        "--notes",
        action="append",
        default=[],
        help="Optional note; repeat --notes for multiple lines",
    )

    import_mesh_evidence_parser = subparsers.add_parser(
        "import-mesh-evidence",
        help="Import external mesh artifact as evidence-only writeback (no automatic claim status change)",
    )
    import_mesh_evidence_parser.add_argument("package", help="Path to a .aieng package")
    import_mesh_evidence_parser.add_argument(
        "--mesh-file",
        required=True,
        help="Path to external mesh artifact file",
    )
    import_mesh_evidence_parser.add_argument(
        "--format",
        required=True,
        choices=["gmsh_msh"],
        help="Mesh format (currently supported: gmsh_msh)",
    )
    import_mesh_evidence_parser.add_argument(
        "--producer-tool",
        default="gmsh",
        help="External mesher tool identifier (default: gmsh)",
    )
    import_mesh_evidence_parser.add_argument(
        "--claim-support",
        default="claim_mesh_evidence_001",
        help="Comma-separated claim IDs supported by this evidence (default: claim_mesh_evidence_001)",
    )
    import_mesh_evidence_parser.add_argument(
        "--verification-status",
        default="unverified",
        choices=["available", "missing", "unverified", "schema_validated"],
        help="Evidence verification status (default: unverified)",
    )
    import_mesh_evidence_parser.add_argument(
        "--evidence-id",
        default=None,
        help="Optional explicit evidence ID",
    )
    import_mesh_evidence_parser.add_argument(
        "--reference-only",
        action="store_true",
        help="Record an external mesh reference without copying the artifact into the package",
    )
    import_mesh_evidence_parser.add_argument(
        "--package-path",
        default=None,
        help="Optional package-relative mesh artifact path (default: results/mesh_artifacts/<evidence_id>.msh)",
    )
    import_mesh_evidence_parser.add_argument(
        "--notes",
        action="append",
        default=[],
        help="Optional note; repeat --notes for multiple lines",
    )

    record_trace_parser = subparsers.add_parser(
        "record-trace",
        help="Record an external tool execution step in provenance/tool_trace.json",
    )
    record_trace_parser.add_argument("package", help="Path to a .aieng package")
    record_trace_parser.add_argument("--tool-id", required=True, help="External tool identifier")
    record_trace_parser.add_argument(
        "--tool-role",
        required=True,
        choices=[
            "agent_runtime",
            "cad_runtime",
            "cae_runtime",
            "cae_preprocessor",
            "solver",
            "postprocessor",
            "manufacturing_checker",
        ],
        help="Functional role of the tool",
    )
    record_trace_parser.add_argument("--step-name", required=True, help="Name of the executed step")
    record_trace_parser.add_argument(
        "--exit-status",
        required=True,
        choices=["success", "failure", "skipped"],
        help="Step exit status as reported by the external tool",
    )
    record_trace_parser.add_argument(
        "--tool-version",
        default=None,
        help="Optional tool version string",
    )
    record_trace_parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        default=[],
        metavar="PATH",
        help="Input path used by the step; repeat for multiple",
    )
    record_trace_parser.add_argument(
        "--output",
        dest="outputs",
        action="append",
        default=[],
        metavar="PATH",
        help="Output path produced by the step; repeat for multiple",
    )
    record_trace_parser.add_argument(
        "--artifact",
        dest="artifacts",
        action="append",
        default=[],
        metavar="EVIDENCE_ID",
        help="Evidence ID recorded for this step; repeat for multiple",
    )
    record_trace_parser.add_argument(
        "--claim",
        dest="claims",
        action="append",
        default=[],
        metavar="CLAIM_ID",
        help="Claim ID advanced by this step; repeat for multiple",
    )
    record_trace_parser.add_argument(
        "--notes",
        action="append",
        default=[],
        help="Optional note; repeat for multiple lines",
    )

    sample_candidates_parser = subparsers.add_parser(
        "sample-candidates",
        help="Generate candidate parameter sets from optimization variables using grid/random/LHS sampling",
    )
    sample_candidates_parser.add_argument("package", help="Path to a .aieng package")
    sample_candidates_parser.add_argument(
        "--algorithm",
        default=None,
        choices=["grid", "random", "latin_hypercube", "lhs"],
        help="Sampling algorithm (default: from optimization_study.json or grid)",
    )
    sample_candidates_parser.add_argument(
        "--count", type=int, default=None,
        help="Number of candidates to generate (for random/LHS; auto-computed for grid)",
    )
    sample_candidates_parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducibility (default: 0 or from study)",
    )
    sample_candidates_parser.add_argument(
        "--max-candidates", type=int, default=None,
        help="Hard cap on emitted candidates (default: 50 or from study)",
    )
    sample_candidates_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Explicitly overwrite existing candidate patches with the same IDs",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start an MCP server exposing .aieng package resources as agent-callable tools",
    )
    serve_parser.add_argument("package", help="Path to a .aieng package")
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port for SSE transport (default: stdio)",
    )

    subparsers.add_parser(
        "geometry-backends",
        help="List available geometry backends and their dependency status",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate a .aieng package")
    validate_parser.add_argument("package", help="Path to a .aieng package")

    ref_inspect_parser = subparsers.add_parser(
        "ref-inspect",
        help="Resolve one canonical @aieng[<resource-path>#<id>] reference",
    )
    ref_inspect_parser.add_argument("package", help="Path to a .aieng package")
    ref_inspect_parser.add_argument("ref", help="Canonical @aieng[...] reference")
    ref_inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output",
    )

    ref_list_parser = subparsers.add_parser(
        "ref-list",
        help="List canonical references in a package by type",
    )
    ref_list_parser.add_argument("package", help="Path to a .aieng package")
    ref_list_parser.add_argument(
        "--type",
        required=True,
        choices=[
            "feature",
            "topology",
            "interface",
            "claim",
            "evidence",
            "trace",
            "patch",
            "constraint",
            "protected_region",
            "cae_mapping",
            "completeness_item",
            "task_spec_item",
            "all",
        ],
        help="Reference kind to enumerate",
    )
    ref_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON array",
    )

    ref_check_parser = subparsers.add_parser(
        "ref-check",
        help="Validate canonical reference resolution and cross-resource ID links",
    )
    ref_check_parser.add_argument("package", help="Path to a .aieng package")

    detect_cae_artifacts_parser = subparsers.add_parser(
        "detect-cae-artifacts",
        help="Detect CAE artifact presence in a .aieng package (honest scan; no solver execution)",
    )
    detect_cae_artifacts_parser.add_argument("package", help="Path to a .aieng package")
    detect_cae_artifacts_parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output",
    )

    summarize_cae_results_parser = subparsers.add_parser(
        "summarize-cae-results",
        help="Generate CAE/post-processing result summary from detected artifacts (no solver execution)",
    )
    summarize_cae_results_parser.add_argument("package", help="Path to a .aieng package")
    summarize_cae_results_parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of markdown",
    )
    summarize_cae_results_parser.add_argument(
        "--write",
        action="store_true",
        help="Write results/result_summary.json, results/evidence_index.json, and results/postprocessing_summary.md into the package",
    )
    summarize_cae_results_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing summary files inside the package",
    )

    summarize_cae_preprocessing_parser = subparsers.add_parser(
        "summarize-cae-preprocessing",
        help="Generate CAE pre-processing setup summary from detected artifacts (no solver execution)",
    )
    summarize_cae_preprocessing_parser.add_argument("package", help="Path to a .aieng package")
    summarize_cae_preprocessing_parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of markdown",
    )
    summarize_cae_preprocessing_parser.add_argument(
        "--write",
        action="store_true",
        help="Write simulation/preprocessing_summary.json and simulation/preprocessing_summary.md into the package",
    )
    summarize_cae_preprocessing_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing summary files inside the package",
    )

    summarize_field_parser = subparsers.add_parser(
        "summarize-field-regions",
        help="Generate LLM-readable summary artifacts from results/field_regions.json",
    )
    summarize_field_parser.add_argument("package", help="Path to a .aieng package")
    summarize_field_parser.add_argument("--json", action="store_true", help="Print structured JSON instead of markdown")
    summarize_field_parser.add_argument("--write", action="store_true", help="Write results/field_summary.json and .md")
    summarize_field_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing field summary artifacts")

    summarize_cae_runs_parser = subparsers.add_parser(
        "summarize-cae-runs",
        help="Generate CAE simulation run summary from detected run metadata (no solver execution)",
    )
    summarize_cae_runs_parser.add_argument("package", help="Path to a .aieng package")
    summarize_cae_runs_parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of markdown",
    )
    summarize_cae_runs_parser.add_argument(
        "--write",
        action="store_true",
        help="Write simulation/simulation_run_summary.json and simulation/simulation_run_summary.md into the package",
    )
    summarize_cae_runs_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing summary files inside the package",
    )

    compare_design_targets_parser = subparsers.add_parser(
        "compare-design-targets",
        help=(
            "Compare task/design_targets.yaml against available evidence "
            "(no solver execution; read-only comparison)"
        ),
    )
    compare_design_targets_parser.add_argument("package", help="Path to a .aieng package")
    compare_design_targets_parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    compare_design_targets_parser.add_argument(
        "--write-summary",
        action="store_true",
        help=(
            "Inject design_target_comparisons into results/result_summary.json "
            "inside the package (atomic rewrite; preserves existing summary fields)"
        ),
    )
    compare_design_targets_parser.add_argument(
        "--summary-path",
        default="results/result_summary.json",
        help="In-package path for the rewritten summary (default: results/result_summary.json)",
    )

    recommend_cad_parser = subparsers.add_parser(
        "recommend-cad-modifications",
        help=(
            "Generate a ranked list of CAD modification proposals from design "
            "targets + per-feature stress + computed metrics (read-only; "
            "proposals are hypotheses, verification by re-simulation required)"
        ),
    )
    recommend_cad_parser.add_argument("package", help="Path to a .aieng package")
    recommend_cad_parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    verify_cad_parser = subparsers.add_parser(
        "verify-cad-modifications",
        help=(
            "Run the pre-execution verification gate on Phase 36 proposals "
            "(schema, preserved-feature, manufacturability, and regression "
            "checks; read-only; does not replace re-simulation)"
        ),
    )
    verify_cad_parser.add_argument("package", help="Path to a .aieng package")
    verify_cad_parser.add_argument(
        "--proposals",
        help=(
            "Path to a JSON file containing the output of "
            "`recommend-cad-modifications --output json`. If omitted, the "
            "verifier regenerates the proposals from the package."
        ),
    )
    verify_cad_parser.add_argument(
        "--strictness",
        choices=["lenient", "default", "strict"],
        default="default",
        help="Strictness mode (default: default)",
    )
    verify_cad_parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # ------------------------------------------------------------------
    # Modeling plan commands (Phase 1)
    # ------------------------------------------------------------------
    plan_parser = subparsers.add_parser(
        "plan",
        help="Generate a modeling_plan.json from natural language intent",
    )
    plan_parser.add_argument(
        "--intent", required=True, help="Natural language modeling intent"
    )
    plan_parser.add_argument(
        "--out", required=True, help="Output modeling_plan.json path"
    )
    plan_parser.add_argument(
        "--units",
        default="mm",
        help="Length unit (mm, cm, m, in). Default: mm",
    )
    plan_parser.add_argument(
        "--json",
        action="store_true",
        help="Also print the generated plan JSON to stdout",
    )

    validate_plan_parser = subparsers.add_parser(
        "validate-plan",
        help="Validate a modeling_plan.json against Phase 1 schema and rules",
    )
    validate_plan_parser.add_argument("plan_file", help="Path to modeling_plan.json")

    init_from_plan_parser = subparsers.add_parser(
        "init-from-plan",
        help="Execute a modeling plan and create a .aieng package",
    )
    init_from_plan_parser.add_argument("plan_file", help="Path to modeling_plan.json")
    init_from_plan_parser.add_argument("--out", required=True, help="Output .aieng package path")
    init_from_plan_parser.add_argument("--backend", default="fake", help="Backend adapter ID (default: fake)")
    init_from_plan_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing package")
    init_from_plan_parser.add_argument(
        "--no-postprocess",
        dest="run_postprocess",
        action="store_false",
        default=True,
        help="Skip semantic post-processing (topology, AAG, feature graph)",
    )
    init_from_plan_parser.add_argument(
        "--postprocess-strict",
        dest="postprocess_strict",
        action="store_true",
        default=False,
        help="Fail and return non-zero exit code if post-processing fails",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        try:
            out = create_package(
                args.model_id,
                Path(args.out),
                overwrite=args.overwrite,
                design_targets=Path(args.design_targets) if args.design_targets else None,
            )
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS created {out}")
        if args.design_targets:
            print("PASS task/design_targets.yaml written")
        return 0

    if args.command == "import-step":
        try:
            out = import_step_package(Path(args.step_file), Path(args.out), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS imported {args.step_file} -> {out}")
        print("PASS geometry/source.step written")
        print("PASS geometry/normalized.step written")
        print("PASS import is evidence-only; no automatic claim status update performed")
        return 0

    if args.command == "define":
        try:
            out = define_package(Path(args.definition_yaml), Path(args.out), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS created definition-sourced package -> {out}")
        print("PASS graph/feature_graph.json written")
        print("PASS graph/constraints.json written")
        print("PASS engineering_context/material.yaml written")
        print("PASS validation/status.yaml written")
        print("PASS validation/completeness_report.json written")
        print("PASS README_FOR_AI.md written")
        return 0

    if args.command == "convert":
        source_path = Path(args.source)
        out_path = Path(args.out)
        model_id = args.model_id or out_path.stem.strip() or source_path.stem.strip()
        try:
            out = convert_source(
                source_path=source_path,
                out=out_path,
                model_id=model_id,
                converter_id=args.converter,
                overwrite=args.overwrite,
                runtime_mode=args.runtime_mode,
                embed_capabilities=not args.no_embed_capabilities,
            )
        except ConverterError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        except (ValueError, FileNotFoundError, FileExistsError, KeyError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS converted {source_path} -> {out}")
        print("PASS provenance/conversion_manifest.json written")
        if not args.no_embed_capabilities:
            print("PASS provenance/converter_capabilities.json written")
        print("PASS validation/completeness_report.json refreshed")
        print("PASS no solver, mesher, optimizer, or CAD edit was executed by the converter")
        return 0

    if args.command == "converter-capabilities":
        profiles = list_converter_capabilities()
        print(json.dumps(profiles, indent=2, sort_keys=True))
        return 0

    if args.command == "readiness-report":
        try:
            if args.json:
                report = readiness_report_payload(Path(args.package))
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(readiness_report_text(Path(args.package)))
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "extract-topology":
        backend_name = _resolve_extract_topology_backend(args.backend)
        try:
            out = extract_topology_package(Path(args.package), overwrite=args.overwrite, backend=backend_name)
        except NotImplementedError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS extracted {backend_name} topology -> {out}")
        print("PASS geometry/topology_map.json written")
        return 0

    if args.command == "write-mesh-handoff":
        try:
            out = write_mesh_handoff_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS wrote mesh handoff contract -> {out}")
        print("PASS simulation/mesh_handoff_contract.json written")
        return 0

    if args.command == "recognize-features":
        try:
            out = recognize_features_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS recognized rule-based feature candidates -> {out}")
        print("PASS graph/feature_graph.json written")
        return 0

    if args.command == "build-aag":
        try:
            out = build_aag_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built attributed adjacency graph -> {out}")
        print("PASS graph/aag.json written")
        return 0

    if args.command == "apply-context":
        try:
            out = apply_context_package(Path(args.package), Path(args.context), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS applied engineering context -> {out}")
        print("PASS graph/constraints.json written")
        print("PASS simulation/setup.yaml written")
        print("PASS ai/protected_regions.json written")
        return 0

    if args.command == "summarize":
        try:
            out = summarize_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS generated AI-readable summaries -> {out}")
        print("PASS README_FOR_AI.md written")
        print("PASS ai/summary.md written")
        return 0

    if args.command == "apply-patch":
        try:
            out = apply_patch_package(
                Path(args.package),
                args.patch,
                out=Path(args.out) if args.out else None,
                overwrite=args.overwrite,
            )
        except PatchNotExecutable as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS applied patch {args.patch} -> {out}")
        print("PASS graph/feature_graph.json parameters updated")
        if args.out:
            print(f"PASS modified STEP written -> {args.out}")
        return 0

    if args.command == "propose-patch":
        try:
            out = propose_patch_package(Path(args.package), args.intent)
        except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS generated structured patch proposal -> {out}")
        print("PASS ai/patches/patch proposal written")
        return 0

    if args.command == "export-updated-deck":
        try:
            out = export_updated_deck_package(
                Path(args.package),
                out=Path(args.out) if args.out else None,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS exported updated deck -> {out}")
        print("PASS simulation/updated_deck.inp written")
        if args.out:
            print(f"PASS external deck copy written -> {args.out}")
        return 0

    if args.command == "export-calculix":
        try:
            out = export_calculix_package(
                Path(args.package),
                out=Path(args.out) if args.out else None,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS generated CalculiX scaffold deck -> {out}")
        print("PASS simulation/solver_deck.inp written inside package")
        if args.out:
            print(f"PASS external deck copy written -> {args.out}")
        return 0

    if args.command == "generate-solver-input":
        from .simulation.deck_generator import MissingSetupError

        try:
            result = generate_solver_input_package(
                Path(args.package),
                run_id=args.run_id,
                overwrite=args.overwrite,
            )
        except MissingSetupError as exc:
            print(f"FAIL missing setup: {exc}", file=sys.stderr)
            return 2
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS generated solver input -> {result['out_path']}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"WARN {w}")
        print(f"PASS {result['out_path']} written inside package")
        return 0

    if args.command == "extract-field-regions":
        from .simulation.field_region_extractor import (
            FieldRegionError,
            extract_field_regions_package,
        )

        try:
            result = extract_field_regions_package(
                Path(args.package),
                Path(args.frd),
                field=args.field,
                metric=args.metric,
                max_clusters=args.max_clusters,
                threshold_percentile=args.threshold_percentile,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError, FieldRegionError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS extracted field regions -> {result['out_path']}")
        print(f"PASS cluster_count = {result['cluster_count']}")
        for warning in result.get("warnings", []):
            print(f"WARN {warning}")
        return 0

    if args.command == "import-cae-deck":
        try:
            out = import_cae_deck_package(
                Path(args.package),
                deck_path=Path(args.deck),
                deck_format=args.format,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS imported CAE deck scaffold -> {out}")
        print("PASS simulation/cae_imports/source_solver_deck.inp written")
        print("PASS simulation/cae_imports/parsed_materials.json written")
        print("PASS simulation/cae_imports/parsed_boundary_conditions.json written")
        print("PASS simulation/cae_imports/parsed_loads.json written")
        print("PASS simulation/cae_mapping.json written")
        print("PASS import is evidence-only; no automatic claim status update performed")
        return 0

    if args.command == "apply-cae-mapping":
        try:
            out = apply_cae_mapping_package(
                Path(args.package),
                mapping_path=Path(args.mapping),
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS applied explicit CAE mapping -> {out}")
        print("PASS simulation/cae_mapping.json updated")
        return 0

    if args.command == "update-validation-status":
        try:
            out = update_validation_status_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS generated validation status -> {out}")
        print("PASS validation/status.yaml written")
        return 0

    if args.command == "write-completeness-report":
        try:
            out = write_completeness_report_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS wrote completeness report -> {out}")
        print("PASS validation/completeness_report.json written")
        return 0

    if args.command == "write-evidence-report":
        try:
            out = write_evidence_report_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS wrote evidence report -> {out}")
        print("PASS validation/evidence_report.json written")
        return 0

    if args.command == "build-visual-index":
        try:
            out = build_visual_index_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built visual annotation index -> {out}")
        print("PASS visual/annotation_layers.json written")
        return 0

    if args.command == "build-visual-manifest":
        try:
            out = build_visual_manifest_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built visual resource manifest -> {out}")
        print("PASS visual/model_manifest.json written")
        return 0

    if args.command == "build-object-registry":
        try:
            out = build_object_registry_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built object registry -> {out}")
        print("PASS objects/object_registry.json written")
        return 0

    if args.command == "build-assembly-graph":
        try:
            out = build_assembly_graph_package(
                Path(args.package),
                Path(args.definition),
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built assembly graph -> {out}")
        print("PASS assembly/assembly_graph.json written")
        return 0

    if args.command == "build-interface-graph":
        try:
            out = build_interface_graph_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built interface graph -> {out}")
        print("PASS objects/interface_graph.json written")
        return 0

    if args.command == "build-allowed-operations-catalog":
        try:
            out = build_allowed_operations_catalog_package(Path(args.package), overwrite=args.overwrite)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS built allowed operations catalog -> {out}")
        print("PASS graph/allowed_operations_catalog.json written")
        return 0

    if args.command == "write-task-spec":
        try:
            out = write_task_spec_package(
                Path(args.package),
                args.intent,
                task_id=args.task_id,
                mode=args.mode,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS wrote task specification -> {out}")
        print("PASS task/task_spec.yaml written")
        return 0

    if args.command == "write-external-tool-requirements":
        try:
            out = write_external_tool_requirements_package(
                Path(args.package),
                handoff_id=args.handoff_id,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS wrote external tool requirements -> {out}")
        print("PASS task/external_tool_requirements.json written")
        return 0

    if args.command == "write-evidence-scaffold":
        try:
            out = write_evidence_scaffold_package(
                Path(args.package),
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS wrote evidence scaffold -> {out}")
        print("PASS results/evidence_index.json written")
        return 0

    if args.command == "record-evidence":
        try:
            out = record_evidence_package(
                Path(args.package),
                evidence_type=args.kind,
                producer_kind=args.producer_kind,
                producer_tool=args.producer_tool,
                artifact_kind=args.artifact_kind,
                artifact_path=args.artifact_path,
                claim_support=_parse_csv_ids(args.claim_support),
                evidence_id=args.evidence_id,
                verification_status=args.verification_status,
                notes=args.notes,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS recorded evidence -> {out}")
        print("PASS results/evidence_index.json updated")
        return 0

    if args.command == "import-solver-evidence":
        try:
            out, summary = import_solver_evidence_package(
                Path(args.package),
                result_file=Path(args.result_file),
                result_format=args.format,
                producer_tool=args.producer_tool,
                claim_support=_parse_csv_ids(args.claim_support),
                verification_status=args.verification_status,
                evidence_id=args.evidence_id,
                notes=args.notes,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS imported solver evidence -> {out}")
        print("PASS results/evidence_index.json updated")
        print(f"PASS parsed known markers -> {summary.get('marker_counts', {})}")
        print(f"PASS parsed known numeric observations -> {summary.get('numeric_observations', {})}")
        print(f"PASS claim review suggestions (manual update only) -> {summary.get('claim_review_suggestions', [])}")
        print("PASS no automatic claim status update performed")
        return 0

    if args.command == "import-mesh-evidence":
        try:
            out, summary = import_mesh_evidence_package(
                Path(args.package),
                mesh_file=Path(args.mesh_file),
                mesh_format=args.format,
                producer_tool=args.producer_tool,
                claim_support=_parse_csv_ids(args.claim_support),
                verification_status=args.verification_status,
                evidence_id=args.evidence_id,
                reference_only=args.reference_only,
                package_artifact_path=args.package_path,
                notes=args.notes,
            )
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS imported mesh evidence -> {out}")
        print("PASS results/evidence_index.json updated")
        print(f"PASS parsed known mesh summary -> {summary}")
        if args.reference_only:
            print(f"PASS mesh artifact referenced externally -> {args.mesh_file}")
        else:
            print("PASS mesh artifact copied into package")
        print("PASS no automatic claim status update performed")
        return 0

    if args.command == "record-trace":
        try:
            out = record_trace_package(
                Path(args.package),
                tool_id=args.tool_id,
                tool_role=args.tool_role,
                step_name=args.step_name,
                exit_status=args.exit_status,
                tool_version=args.tool_version,
                inputs=args.inputs,
                outputs=args.outputs,
                artifacts_recorded=args.artifacts,
                claims_advanced=args.claims,
                notes=args.notes,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS recorded tool trace entry -> {out}")
        print("PASS provenance/tool_trace.json updated")
        return 0

    if args.command == "sample-candidates":
        from .converters.optimization_sampler import sample_candidates_package

        try:
            result = sample_candidates_package(
                Path(args.package),
                algorithm=args.algorithm,
                count=args.count,
                seed=args.seed,
                max_candidates=args.max_candidates,
                overwrite=args.overwrite,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        if result.get("status") == "error":
            print(f"FAIL {result.get('message', 'unknown error')}", file=sys.stderr)
            return 2
        print(f"PASS sampled candidates ({result['algorithm']}): "
              f"{result['candidate_count']} written, "
              f"{result['total_generated']} generated, "
              f"{result['dropped_count']} dropped (cap={result['capped']})")
        for path in result.get("artifacts_written", []):
            print(f"PASS wrote {path}")
        for w in result.get("warnings", []):
            print(f"WARN {w}")
        return 0

    if args.command == "serve":
        from .mcp.server import serve
        try:
            serve(Path(args.package), port=args.port)
        except FileNotFoundError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        except (ValueError, ImportError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "geometry-backends":
        occ_runtime = detect_occ_runtime()
        print("Geometry backends:")
        print("  mock: available")
        if occ_runtime["available"]:
            if occ_runtime["provider"] == "OCP":
                print(
                    "  occ: runtime detected (OCP/CadQuery) — "
                    "experimental real STEP extraction available (Phase 7B.2)"
                )
            else:
                print(
                    f"  occ: runtime detected ({occ_runtime['provider']}) — "
                    "Phase 7B.2 implements OCP/CadQuery only; pythonocc-core extraction not yet supported"
                )
        else:
            print(f"  occ: not available — {occ_runtime['message']}")
        return 0

    if args.command == "validate":
        report = validate_package(Path(args.package))
        rendered = report.render()
        if rendered:
            print(rendered)
        return 0 if report.ok else 1

    if args.command == "ref-inspect":
        try:
            resolved = inspect_ref(Path(args.package), args.ref)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(resolved, indent=2, sort_keys=True))
        else:
            print(f"PASS resolved {resolved['ref']}")
            print(f"PASS kind = {resolved['kind']}")
            print(f"PASS resource = {resolved['resource_path']}")
            print(f"PASS id = {resolved['id']}")
        return 0

    if args.command == "ref-list":
        try:
            refs = list_refs(Path(args.package), kind=args.type)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "ref": item.ref,
                            "kind": item.kind,
                            "resource_path": item.resource_path,
                            "id": item.record_id,
                        }
                        for item in refs
                    ],
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            for item in refs:
                print(item.ref)
        return 0

    if args.command == "ref-check":
        try:
            ok, messages = ref_check_package(Path(args.package))
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        for message in messages:
            print(f"{message.level} {message.text}")
        return 0 if ok else 1

    if args.command == "detect-cae-artifacts":
        from .cae_artifact_detector import detect_cae_artifacts

        try:
            result = detect_cae_artifacts(Path(args.package))
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Mode: {result['mode']}")
            print(f"Detected {result['detected_count']} / {result['total_count']} artifacts")
            print("")
            for path, present in result["artifacts"].items():
                status = "YES" if present else "NO"
                print(f"  [{status}] {path}")
            print("")
            print("Flags:")
            print(f"  has_cae_setup      = {result['has_cae_setup']}")
            print(f"  has_mesh           = {result['has_mesh']}")
            print(f"  has_solver_settings= {result['has_solver_settings']}")
            print(f"  has_results        = {result['has_results']}")
            print(f"  has_fields         = {result['has_fields']}")
            print(f"  has_validation     = {result['has_validation']}")
        return 0

    if args.command == "summarize-cae-results":
        from .cae_result_summary import (
            generate_cae_result_summary,
            generate_evidence_index,
            generate_postprocessing_markdown,
            write_cae_result_summary_package,
        )

        try:
            if args.write:
                out = write_cae_result_summary_package(
                    Path(args.package),
                    overwrite=args.overwrite,
                )
                print(f"PASS wrote CAE result summary -> {out}")
                print("PASS results/result_summary.json written")
                print("PASS results/evidence_index.json written")
                print("PASS results/postprocessing_summary.md written")
                print("PASS no solver was executed; summary is based on artifact presence only")
                return 0

            summary = generate_cae_result_summary(Path(args.package))
            evidence = generate_evidence_index(Path(args.package))
            if args.json:
                print(json.dumps({"summary": summary, "evidence_index": evidence}, indent=2, sort_keys=True))
            else:
                markdown = generate_postprocessing_markdown(summary, evidence)
                print(markdown)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "compare-design-targets":
        from .cae_result_summary import (
            compare_design_targets_for_package,
            write_design_target_comparisons_package,
        )

        try:
            comparisons = compare_design_targets_for_package(Path(args.package))
        except (ValueError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2

        if args.write_summary:
            try:
                out = write_design_target_comparisons_package(
                    Path(args.package),
                    summary_path=args.summary_path,
                )
            except (ValueError, FileNotFoundError) as exc:
                print(f"FAIL {exc}", file=sys.stderr)
                return 2
            print(f"PASS wrote design_target_comparisons -> {out}:{args.summary_path}")
            print("PASS evidence resources were not modified")
            return 0

        if args.output == "json":
            print(json.dumps(comparisons, indent=2, sort_keys=True))
            return 0

        summary_counts = comparisons.get("summary", {})
        total = summary_counts.get("total", 0)
        passed = summary_counts.get("pass", 0)
        failed = summary_counts.get("fail", 0)
        unknown = summary_counts.get("unknown", 0)
        not_evaluated = summary_counts.get("not_evaluated", 0)
        target_set_id = comparisons.get("target_set_id")
        if target_set_id:
            print(f"Design target set: {target_set_id}")
        print(
            f"{total} target(s): {passed} pass, {failed} fail, "
            f"{unknown} unknown, {not_evaluated} not_evaluated"
        )
        print("")
        for item in comparisons.get("items", []):
            tid = item.get("target_id", "<unnamed>")
            ttype = item.get("target_type", "?")
            status = item.get("status", "?")
            expected = item.get("expected", {})
            actual = item.get("actual", {})
            comparator = item.get("comparator", "?")
            threshold = expected.get("threshold")
            threshold_min = expected.get("threshold_min")
            threshold_max = expected.get("threshold_max")
            if threshold is not None:
                expected_str = f"{comparator} {threshold}"
            elif threshold_min is not None or threshold_max is not None:
                expected_str = f"within [{threshold_min}, {threshold_max}]"
            else:
                expected_str = comparator
            actual_value = actual.get("value")
            actual_unit = actual.get("unit") or ""
            actual_str = (
                f"{actual_value} {actual_unit}".strip()
                if actual_value is not None
                else "—"
            )
            line = f"[{status}] {tid} ({ttype}): expected {expected_str}, actual {actual_str}"
            notes = item.get("notes")
            if notes:
                line += f" — {notes}"
            print(line)
        print("")
        print("Comparison is evidence-based; status:pass means available evidence meets the threshold, not engineering certification.")
        return 0

    if args.command == "recommend-cad-modifications":
        from .cae_recommendation import (
            generate_cad_modification_recommendations,
            generate_recommendations_markdown,
        )

        recommendations = generate_cad_modification_recommendations(Path(args.package))

        if args.output == "json":
            print(json.dumps(recommendations, indent=2, sort_keys=True))
        else:
            print(generate_recommendations_markdown(recommendations))

        return 0 if recommendations.get("ok") else 2

    if args.command == "verify-cad-modifications":
        from .cae_recommendation import generate_cad_modification_recommendations
        from .cae_verification import (
            generate_verification_markdown,
            verify_recommendations,
        )

        if args.proposals:
            try:
                with open(args.proposals, "r", encoding="utf-8") as fh:
                    recommendations = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"FAIL could not read proposals file: {exc}", file=sys.stderr)
                return 2
        else:
            recommendations = generate_cad_modification_recommendations(Path(args.package))

        result = verify_recommendations(
            recommendations, Path(args.package), strictness=args.strictness
        )

        if args.output == "json":
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(generate_verification_markdown(result))

        summary = result.get("summary", {})
        # Exit code: 0 if no fails; 1 if any fails (so CI / orchestrators can gate).
        return 1 if summary.get("fail", 0) > 0 else 0

    if args.command == "summarize-cae-preprocessing":
        from .cae_preprocessing_summary import (
            generate_preprocessing_summary,
            generate_preprocessing_markdown,
            write_preprocessing_summary_package,
        )

        try:
            if args.write:
                out = write_preprocessing_summary_package(
                    Path(args.package),
                    overwrite=args.overwrite,
                )
                print(f"PASS wrote CAE pre-processing summary -> {out}")
                print("PASS simulation/preprocessing_summary.json written")
                print("PASS simulation/preprocessing_summary.md written")
                print("PASS no solver was executed; summary is based on artifact presence only")
                return 0

            summary = generate_preprocessing_summary(Path(args.package))
            if args.json:
                print(json.dumps(summary, indent=2, sort_keys=True))
            else:
                markdown = generate_preprocessing_markdown(summary)
                print(markdown)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "summarize-field-regions":
        from .cae_field_summary import (
            generate_field_summary,
            generate_field_summary_markdown,
            write_field_summary_package,
        )

        try:
            if args.write:
                out = write_field_summary_package(
                    Path(args.package),
                    overwrite=args.overwrite,
                )
                print(f"PASS wrote field summary -> {out}")
                print("PASS results/field_summary.json written")
                print("PASS results/field_summary.md written")
                print("PASS no physical correctness claim was made")
                return 0

            summary = generate_field_summary(Path(args.package))
            if args.json:
                print(json.dumps(summary, indent=2, sort_keys=True))
            else:
                print(generate_field_summary_markdown(summary))
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "summarize-cae-runs":
        from .cae_simulation_run_summary import (
            generate_simulation_run_summary,
            generate_simulation_run_markdown,
            write_simulation_run_summary_package,
        )

        try:
            if args.write:
                out = write_simulation_run_summary_package(
                    Path(args.package),
                    overwrite=args.overwrite,
                )
                print(f"PASS wrote CAE simulation run summary -> {out}")
                print("PASS simulation/simulation_run_summary.json written")
                print("PASS simulation/simulation_run_summary.md written")
                print("PASS no solver was executed; summary is based on recorded run metadata only")
                return 0

            summary = generate_simulation_run_summary(Path(args.package))
            if args.json:
                print(json.dumps(summary, indent=2, sort_keys=True))
            else:
                markdown = generate_simulation_run_markdown(summary)
                print(markdown)
        except (ValueError, FileNotFoundError, FileExistsError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "plan":
        planner = RuleBasedModelingPlanner()
        try:
            plan = planner.plan(
                args.intent,
                units={"length": args.units.lower(), "angle": "deg"},
            )
        except Exception as exc:
            print(f"FAIL planner error: {exc}", file=sys.stderr)
            return 2

        # Self-validation
        report = validate_modeling_plan(plan)
        if not report.ok:
            print(f"FAIL generated plan is invalid:\n{report.render()}", file=sys.stderr)
            return 2

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2, sort_keys=True)
                f.write("\n")
        except OSError as exc:
            print(f"FAIL could not write output: {exc}", file=sys.stderr)
            return 2

        print(f"PASS written modeling plan -> {out_path}")
        if args.json:
            print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if args.command == "validate-plan":
        try:
            report = validate_modeling_plan_file(args.plan_file)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(report.render())
        return 0 if report.ok else 1

    if args.command == "init-from-plan":
        try:
            out = init_from_plan(
                Path(args.plan_file),
                Path(args.out),
                backend_id=args.backend,
                overwrite=args.overwrite,
                run_postprocess=args.run_postprocess,
                postprocess_strict=args.postprocess_strict,
            )
        except (ValueError, RuntimeError, FileNotFoundError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(f"PASS written package -> {out}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _resolve_extract_topology_backend(requested_backend: str | None) -> str:
    backend = (requested_backend or "auto").strip().lower()
    if backend in {"mock", "occ"}:
        return backend
    if backend != "auto":
        return backend

    runtime = detect_occ_runtime()
    if runtime.get("available") and runtime.get("provider") == "OCP":
        return "occ"
    return "mock"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
