from __future__ import annotations

import ast
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

README_FOR_AI_PATH = "README_FOR_AI.md"
AI_SUMMARY_PATH = "ai/summary.md"
TOPOLOGY_MAP_PATH = "geometry/topology_map.json"
AAG_PATH = "graph/aag.json"
FEATURE_GRAPH_PATH = "graph/feature_graph.json"
CONSTRAINTS_PATH = "graph/constraints.json"
SIMULATION_SETUP_PATH = "simulation/setup.yaml"
PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
VISUAL_ANNOTATION_PATH = "visual/annotation_layers.json"
VISUAL_MODEL_MANIFEST_PATH = "visual/model_manifest.json"
OBJECT_REGISTRY_PATH = "objects/object_registry.json"
INTERFACE_GRAPH_PATH = "objects/interface_graph.json"
CAE_SOURCE_DECK_PATH = "simulation/cae_imports/source_solver_deck.inp"
CAE_PARSED_MATERIALS_PATH = "simulation/cae_imports/parsed_materials.json"
CAE_PARSED_BCS_PATH = "simulation/cae_imports/parsed_boundary_conditions.json"
CAE_PARSED_LOADS_PATH = "simulation/cae_imports/parsed_loads.json"
CAE_MAPPING_PATH = "simulation/cae_mapping.json"
TASK_SPEC_PATH = "task/task_spec.yaml"
EXTERNAL_TOOL_REQUIREMENTS_PATH = "task/external_tool_requirements.json"
EVIDENCE_INDEX_PATH = "results/evidence_index.json"
TOOL_TRACE_PATH = "provenance/tool_trace.json"
COMPLETENESS_REPORT_PATH = "validation/completeness_report.json"
EVIDENCE_REPORT_PATH = "validation/evidence_report.json"


class SummaryWriter:
    """Generate deterministic AI-readable summaries from structured .aieng resources."""

    def write(self, package_path: str | Path, *, overwrite: bool = False) -> Path:
        package_file = Path(package_path)
        if not package_file.exists():
            raise FileNotFoundError(f"package does not exist: {package_file}")
        if package_file.suffix != ".aieng":
            raise ValueError("package path must end with .aieng")

        try:
            with zipfile.ZipFile(package_file, mode="r") as package:
                names = set(package.namelist())
                if "manifest.json" not in names:
                    raise ValueError("package is missing manifest.json")
                existing_outputs = [path for path in (README_FOR_AI_PATH, AI_SUMMARY_PATH) if path in names]
                if existing_outputs and not overwrite:
                    raise FileExistsError(
                        f"summary resources already exist: {', '.join(existing_outputs)}; use --overwrite to replace them"
                    )

                manifest = _read_json(package, "manifest.json")
                data = SummaryData(
                    manifest=manifest,
                    topology_map=_read_optional_json(package, TOPOLOGY_MAP_PATH),
                    aag=_read_optional_json(package, AAG_PATH),
                    feature_graph=_read_optional_json(package, FEATURE_GRAPH_PATH),
                    constraints=_read_optional_json(package, CONSTRAINTS_PATH),
                    simulation_setup=_read_optional_yaml(package, SIMULATION_SETUP_PATH),
                    protected_regions=_read_optional_json(package, PROTECTED_REGIONS_PATH),
                    visual_model_manifest=_read_optional_json(package, VISUAL_MODEL_MANIFEST_PATH),
                    interface_graph=_read_optional_json(package, INTERFACE_GRAPH_PATH),
                    cae_mapping=_read_optional_json(package, CAE_MAPPING_PATH),
                    task_spec=_read_optional_yaml(package, TASK_SPEC_PATH),
                    external_tool_requirements=_read_optional_json(package, EXTERNAL_TOOL_REQUIREMENTS_PATH),
                    evidence_index=_read_optional_json(package, EVIDENCE_INDEX_PATH),
                    tool_trace=_read_optional_json(package, TOOL_TRACE_PATH),
                    completeness_report=_read_optional_json(package, COMPLETENESS_REPORT_PATH),
                    evidence_report=_read_optional_json(package, EVIDENCE_REPORT_PATH),
                    names=names,
                )
                existing_members = _read_existing_members(package)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

        readme_text = _render_readme_for_ai(data)
        summary_text = _render_ai_summary(data)
        _rewrite_package_with_summaries(package_file, existing_members, manifest, readme_text, summary_text)
        return package_file


class SummaryData:
    def __init__(
        self,
        *,
        manifest: dict[str, Any],
        topology_map: Any | None,
        aag: Any | None,
        feature_graph: Any | None,
        constraints: Any | None,
        simulation_setup: Any | None,
        protected_regions: Any | None,
        visual_model_manifest: Any | None,
        interface_graph: Any | None,
        cae_mapping: Any | None,
        task_spec: Any | None,
        external_tool_requirements: Any | None,
        evidence_index: Any | None,
        tool_trace: Any | None,
        completeness_report: Any | None,
        evidence_report: Any | None,
        names: set[str],
    ) -> None:
        self.manifest = manifest
        self.topology_map = topology_map
        self.aag = aag
        self.feature_graph = feature_graph
        self.constraints = constraints
        self.simulation_setup = simulation_setup
        self.protected_regions = protected_regions
        self.visual_model_manifest = visual_model_manifest
        self.interface_graph = interface_graph
        self.cae_mapping = cae_mapping
        self.task_spec = task_spec
        self.external_tool_requirements = external_tool_requirements
        self.evidence_index = evidence_index
        self.tool_trace = tool_trace
        self.completeness_report = completeness_report
        self.evidence_report = evidence_report
        self.names = names


def summarize_package(package_path: str | Path, *, overwrite: bool = False) -> Path:
    """Generate README_FOR_AI.md and ai/summary.md for an existing .aieng package."""
    return SummaryWriter().write(package_path, overwrite=overwrite)


def _read_json(package: zipfile.ZipFile, member: str) -> dict[str, Any]:
    data = json.loads(package.read(member))
    if not isinstance(data, dict):
        raise ValueError(f"{member} must contain a JSON object")
    return data


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    return json.loads(package.read(member))


def _read_optional_yaml(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    return yaml.safe_load(package.read(member))


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    skip = {"manifest.json", README_FOR_AI_PATH, AI_SUMMARY_PATH}
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _render_readme_for_ai(data: SummaryData) -> str:
    manifest = data.manifest
    model_id = str(manifest.get("model_id", "unknown_model"))
    source_paths = _known_source_of_truth_paths(data)
    resources = _resource_paths(manifest.get("resources", {}))
    feature_lines = _feature_lines(data.feature_graph)
    protected_lines = _protected_lines(data.protected_regions)
    simulation_lines = _simulation_lines(data.simulation_setup)

    lines = [
        f"# .aieng AI Reader Guide: {model_id}",
        "",
        "## What this package is",
        "This is a self-describing engineering model package for general AI. It adapts CAD/CAE data to AI by carrying structured geometry references, topology, feature candidates, user-provided context, constraints, simulation intent, and protected regions.",
        "",
        "This package is not a CAD kernel, CAE solver, mesher, manufacturing checker, or proof that the design is safe.",
        "",
        "## How a general AI should read this package",
        "Start from `manifest.json`, then inspect structured JSON/YAML resources before relying on prose summaries. Use stable object IDs when discussing topology entities, features, constraints, simulation setup, or protected regions.",
        "",
        "`README_FOR_AI.md` and `ai/summary.md` are derived summaries for readability. Structured JSON/YAML resources are the source of truth.",
        "",
        "## Required Reading Order for AI Readers",
        "",
        "If the following files are present in this package, inspect them in this order before answering questions about this model:",
        "",
        "1. `manifest.json` — package identity and complete resource index",
        "2. `validation/status.yaml` — claim policy and validation-state ledger; **read before answering any engineering validity question**",
        "3. `validation/completeness_report.json` — best-effort conversion report; explicit available/partial/missing/unsupported information",
        "4. `README_FOR_AI.md` — this file; package reading guide",
        "5. `ai/summary.md` — derived engineering narrative (derived; not source of truth)",
        "6. `graph/aag.json` — generated face adjacency index derived from topology_map; not source-of-truth",
        "7. `graph/feature_graph.json` — feature candidates with stable IDs",
        "8. `graph/constraints.json` — structured constraints targeting feature IDs",
        "9. `ai/protected_regions.json` — protected feature IDs and forbidden operations",
        "10. `simulation/setup.yaml` — simulation intent (material, boundary conditions, loads, targets)",
        "11. `simulation/solver_deck.inp` — solver deck if present; may be a scaffold only, not solver evidence",
        "12. `simulation/cae_imports/source_solver_deck.inp` — imported external CAE deck source, if present",
        "13. `simulation/cae_imports/parsed_*.json` and `simulation/cae_mapping.json` — deterministic parsed CAE entities and conservative mapping status",
        "14. `ai/patches/*.json` — patch proposals; unexecuted suggestions, not applied modifications",
        "15. `geometry/topology_map.json` — topology entity IDs; may be mock-generated in current phases",
        "16. `objects/object_registry.json` — generated cross-file index of objects and references; navigation aid only, not source of truth",
        "17. `objects/interface_graph.json` — generated interface index of mounting/protected/fixed/load interfaces; navigation aid only, not source of truth",
        "18. `visual/model_manifest.json` — visual resource manifest, if present; records whether rendered/viewable assets are generated",
        "19. `visual/annotation_layers.json` — visual annotation scaffold, if present; maps feature IDs and topology IDs to visual roles; not rendered geometry",
        "",
        "- `validation/status.yaml` is the claim-policy and validation-state ledger. Read it before making any engineering validity claim.",
        "- `validation/completeness_report.json` is the explicit missingness ledger. Treat absent information as missing/unknown/unsupported, not as permission to infer.",
        "- `simulation/solver_deck.inp` may be a scaffold only. It carries an explicit warning if no mesh or solver has run.",
        "- Imported CAE deck resources (`simulation/cae_imports/*`, `simulation/cae_mapping.json`) are parsed inputs and mapping scaffolds, not solver execution evidence.",
        "- Global import policy: imported artifacts and parsed facts do not automatically advance claims. Claim proposals require human review.",
        "- `ai/patches/*.json` are unexecuted proposals, not applied modifications. Check `patch_execution` status before assuming any patch was applied.",
        "- `geometry/topology_map.json` may be mock-generated. Topology entity IDs are stable but STEP content is not parsed.",
        "- `graph/aag.json` is a generated adjacency index from topology data and is not source-of-truth geometry.",
        "- Convexity/continuity in `graph/aag.json` may remain unknown unless backend evidence exists.",
        "- `objects/object_registry.json` is a generated index for navigation. Structured source JSON/YAML files remain authoritative.",
        "- `objects/interface_graph.json` is a generated interface index for navigation. Structured source JSON/YAML files remain authoritative.",
        "- `visual/model_manifest.json` is the source of truth for visual resource availability and rendering claims in Phase 8B.",
        "- `visual/annotation_layers.json` is a structured annotation scaffold only. No rendering, glTF, image, or 3D geometry visualization has been performed.",
        "",
        "## Before Answering Engineering Validity Questions",
        "",
        "Before answering whether this design is safe, solver-validated, manufacturable, or stress-compliant, inspect these resources if present:",
        "",
        "- `validation/status.yaml` — check `solver_mesh_status` and `claim_policy.forbidden_claims`",
        "- `simulation/solver_deck.inp` — check for scaffold warning; confirm whether a mesh or solver run exists",
        "- `results/` — check for attached solver result evidence",
        "- `ai/patches/*.json` — check `patch_execution` and `geometry_modified_by_patch` if discussing modifications",
        "",
        "Claim discipline rules:",
        "",
        "- If `solver_mesh_status.solver_execution` is `not_run`, do not claim a solver was run.",
        "- If `solver_mesh_status.stress_validation` is `not_validated`, do not claim stress targets are satisfied.",
        "- If `solver_mesh_status.manufacturing_validation` is `not_run`, do not claim manufacturability.",
        "- If `patch_status.patch_execution` is `not_run`, do not claim a patch was applied.",
        "",
        "## Source-of-truth files",
        *_bullet_lines(source_paths, missing_text="- No structured source-of-truth resources are currently indexed."),
        "",
        "## Known structured resources",
        *_bullet_lines(resources, missing_text="- No resources are indexed in manifest.json."),
        "",
        "## Engineering object summary",
        *_bullet_lines(feature_lines, missing_text="- `graph/feature_graph.json` is missing; no feature candidates are available."),
        "",
        "## Feature recognition quality",
        *_bullet_lines(
            _feature_recognition_quality_lines(data.feature_graph),
            missing_text="- Recognition quality summary unavailable because `graph/feature_graph.json` is missing.",
        ),
        "",
        "## Protected regions",
        *_bullet_lines(protected_lines, missing_text="- `ai/protected_regions.json` is missing; no protected regions are declared."),
        "",
        "## Simulation intent",
        *_bullet_lines(simulation_lines, missing_text="- `simulation/setup.yaml` is missing; no simulation intent is declared."),
        "",
        "## CAE deck imports",
        *_bullet_lines(_cae_lines(data), missing_text="- No imported CAE deck scaffold resources are present."),
        "",
        "## CAE interface mappings",
        *_bullet_lines(_interface_cae_lines(data), missing_text="- No explicit CAE deck entities are linked to interface graph entries."),
        "",
        "## Visual resources",
        *(
            [
                "- `objects/object_registry.json` is present. It can be used as a cross-file index of object IDs, definitions, and references.",
                "- It is not source-of-truth data. Original structured resources remain authoritative.",
            ]
            if OBJECT_REGISTRY_PATH in data.names
            else ["- `objects/object_registry.json` is not present. Run `aieng build-object-registry` to generate it."]
        ),
        *(
            [
                "- `objects/interface_graph.json` is present. It identifies interface-related features from structured context (mounting, protected, fixed support, and load application roles).",
                "- It is a generated index only. Source JSON/YAML files remain authoritative.",
            ]
            if INTERFACE_GRAPH_PATH in data.names
            else ["- `objects/interface_graph.json` is not present. Run `aieng build-interface-graph` to generate it."]
        ),
        *(
            [
                "- `visual/model_manifest.json` is present. It is a visual resource manifest that distinguishes annotation metadata from rendered assets.",
                "- In Phase 8B, `rendering_status.rendered_geometry_present` and `rendering_status.viewer_ready` should remain `false` unless future rendering phases are implemented.",
            ]
            if VISUAL_MODEL_MANIFEST_PATH in data.names
            else ["- `visual/model_manifest.json` is not present. Run `aieng build-visual-manifest` to generate it."]
        ),
        *(
            [
                "- `visual/annotation_layers.json` is present. It is a structured annotation scaffold that maps feature IDs and topology IDs to visual roles.",
                "- It is not rendered geometry. No glTF, image, mesh, or 3D visualization has been generated.",
                "- It can drive future visual tools and helps AI readers understand which features are candidates, protected, simulation targets, or unclassified.",
            ]
            if VISUAL_ANNOTATION_PATH in data.names
            else ["- `visual/annotation_layers.json` is not present. Run `aieng build-visual-index` to generate it."]
        ),
        "",
        "## Active task contract",
        *_bullet_lines(
            _task_spec_lines(data.task_spec),
            missing_text="- `task/task_spec.yaml` is absent; no structured task contract has been written for this package. Run `aieng write-task-spec` to generate one.",
        ),
        "",
        "## External tool handoff contract",
        *_bullet_lines(
            _external_tool_requirements_lines(data.external_tool_requirements),
            missing_text="- `task/external_tool_requirements.json` is absent; no external tool handoff contract has been written. Run `aieng write-external-tool-requirements` to generate one.",
        ),
        "",
        "## Evidence ledger",
        *_bullet_lines(
            _evidence_index_lines(data.evidence_index),
            missing_text="- `results/evidence_index.json` is absent; no evidence ledger has been written. Run `aieng write-evidence-scaffold` to generate one.",
        ),
        "",
        "## Provenance tool trace",
        *_bullet_lines(
            _tool_trace_lines(data.tool_trace),
            missing_text="- `provenance/tool_trace.json` is absent; no external tool execution steps have been recorded. Run `aieng record-trace` to record a step.",
        ),
        "",
        "## Completeness and missingness",
        *_bullet_lines(
            _completeness_report_lines(data.completeness_report),
            missing_text="- `validation/completeness_report.json` is absent; missing CAD/CAE semantic information has not been explicitly indexed. Run `aieng write-completeness-report` to generate one.",
        ),
        "",
        "## Consolidated evidence report",
        *_bullet_lines(
            _evidence_report_lines(data.evidence_report),
            missing_text="- `validation/evidence_report.json` is absent; consolidated claim/evidence validation view is not available. Run `aieng write-evidence-report` to generate one.",
        ),
        "",
        "## Validation state",
        "- Package structure and referenced resources may be checked with `aieng validate`.",
        "- Topology, feature, and context resources are structurally validated when present and referenced.",
        "- No mesh generation has been run by Phase 5A.",
        "- No solver result has been attached.",
        "- Imported CAE deck resources do not imply mesh generation, solver execution, or validated results.",
        "- Global import policy: imported artifacts and parsed facts do not automatically advance claims. Claim proposals require human review.",
        "- No stress or displacement claim is solver-validated.",
        "",
        "## Important limitations",
        "- STEP import is a resource copy; STEP content is not parsed.",
        "- Topology extraction is currently mock-based.",
        "- Feature recognition is deterministic and rule-based; detected features are candidates, not guaranteed engineering truth.",
        "- Context is user-provided engineering meaning and assumptions; it is not solver evidence.",
        "- These summaries are generated from structured resources without LLM, RAG, skill, plugin, mesher, solver, CAD parser, or manufacturing-checker calls.",
        "",
        "## Rules for AI readers",
        "- Do not claim the design is safe unless solver-validated evidence exists.",
        "- Do not treat candidate features as confirmed engineering truth.",
        "- Do not modify protected regions.",
        "- Do not invent material properties.",
        "- Distinguish extracted facts, inferred candidates, user-provided context, and validated results.",
        "- Use object IDs when referring to features, topology entities, constraints, or protected regions.",
        "",
    ]
    return "\n".join(lines)


def _render_ai_summary(data: SummaryData) -> str:
    manifest = data.manifest
    model_id = str(manifest.get("model_id", "unknown_model"))
    format_version = str(manifest.get("format_version", "unknown"))
    units = manifest.get("units", {}) if isinstance(manifest.get("units"), dict) else {}

    lines = [
        "# Engineering Summary",
        "",
        "This is a derived summary for general AI readability. Structured JSON/YAML resources are the source of truth.",
        "",
        "## Model identity",
        f"- model_id: `{model_id}`",
        f"- format_version: `{format_version}`",
        f"- units: {_inline_json(units)}",
        "",
        "## Geometry resources",
        *_bullet_lines(_geometry_resource_lines(data), missing_text="- No geometry resources are indexed."),
        "",
        "## Topology summary",
        *_bullet_lines(_topology_summary_lines(data.topology_map), missing_text="- `geometry/topology_map.json` is missing."),
        "",
        "## AAG summary",
        *_bullet_lines(_aag_lines(data.aag), missing_text="- `graph/aag.json` is missing."),
        "",
        "## Feature summary",
        *_bullet_lines(_feature_lines(data.feature_graph, include_details=True), missing_text="- `graph/feature_graph.json` is missing."),
        "",
        "## Feature recognition quality",
        *_bullet_lines(
            _feature_recognition_quality_lines(data.feature_graph),
            missing_text="- Recognition quality summary unavailable because `graph/feature_graph.json` is missing.",
        ),
        "",
        "## Constraints summary",
        *_bullet_lines(_constraint_lines(data.constraints), missing_text="- `graph/constraints.json` is missing."),
        "",
        "## Protected regions",
        *_bullet_lines(_protected_lines(data.protected_regions), missing_text="- `ai/protected_regions.json` is missing."),
        "",
        "## Simulation setup",
        *_bullet_lines(_simulation_lines(data.simulation_setup, include_materials=True), missing_text="- `simulation/setup.yaml` is missing."),
        "",
        "## CAE deck imports",
        *_bullet_lines(_cae_lines(data), missing_text="- No imported CAE deck scaffold resources are present."),
        "",
        "## CAE interface mappings",
        *_bullet_lines(_interface_cae_lines(data), missing_text="- No explicit CAE deck entities are linked to interface graph entries."),
        "",
        "## Assumptions",
        *_bullet_lines(_assumption_lines(data), missing_text="- No assumptions are recorded in context resources."),
        "",
        "## Visual resources",
        *(
            [
                "- `objects/object_registry.json` is present and can accelerate cross-file ID lookup.",
                "- It is a generated index only; source JSON/YAML resources remain authoritative.",
            ]
            if OBJECT_REGISTRY_PATH in data.names
            else ["- `objects/object_registry.json` is not present."]
        ),
        *(
            [
                "- `objects/interface_graph.json` is present and can accelerate identification of interface-related features and preservation constraints.",
                "- It is a generated index only; source JSON/YAML resources remain authoritative.",
            ]
            if INTERFACE_GRAPH_PATH in data.names
            else ["- `objects/interface_graph.json` is not present."]
        ),
        *(
            [
                "- `visual/model_manifest.json` is present. It is the source of truth for visual resource availability claims.",
                "- It indicates whether rendered/viewable geometry assets are present; in Phase 8B these remain not generated.",
            ]
            if VISUAL_MODEL_MANIFEST_PATH in data.names
            else ["- `visual/model_manifest.json` is not present."]
        ),
        *(
            [
                "- `visual/annotation_layers.json` is present. It maps feature IDs and topology IDs to visual roles (candidate_feature, protected_region, simulation_context, unclassified_geometry).",
                "- It is a structured annotation scaffold only. No rendering, glTF, image, or 3D geometry has been generated.",
            ]
            if VISUAL_ANNOTATION_PATH in data.names
            else ["- `visual/annotation_layers.json` is not present."]
        ),
        "",
        "## Active task contract",
        *_bullet_lines(
            _task_spec_lines(data.task_spec),
            missing_text="- `task/task_spec.yaml` is absent.",
        ),
        "",
        "## External tool handoff contract",
        *_bullet_lines(
            _external_tool_requirements_lines(data.external_tool_requirements),
            missing_text="- `task/external_tool_requirements.json` is absent.",
        ),
        "",
        "## Evidence ledger",
        *_bullet_lines(
            _evidence_index_lines(data.evidence_index),
            missing_text="- `results/evidence_index.json` is absent.",
        ),
        "",
        "## Provenance tool trace",
        *_bullet_lines(
            _tool_trace_lines(data.tool_trace),
            missing_text="- `provenance/tool_trace.json` is absent; no external tool steps have been recorded.",
        ),
        "",
        "## Completeness and missingness",
        *_bullet_lines(
            _completeness_report_lines(data.completeness_report),
            missing_text="- `validation/completeness_report.json` is absent; missing CAD/CAE semantic information has not been explicitly indexed.",
        ),
        "",
        "## Consolidated evidence report",
        *_bullet_lines(
            _evidence_report_lines(data.evidence_report),
            missing_text="- `validation/evidence_report.json` is absent; consolidated claim/evidence validation view is not available.",
        ),
        "",
        "## Validation status",
        *([f"- For validation-state questions, inspect `validation/status.yaml` first — it contains `solver_mesh_status` and `claim_policy`."] if "validation/status.yaml" in data.names else []),
        "- Geometry package validation may pass.",
        "- Topology, feature, and context structural validation may pass when their resources are present and referenced.",
        "- No mesh generation has been run.",
        "- No solver result has been attached.",
        "- Imported CAE deck resources do not imply mesh generation, solver execution, or validated results.",
        "- No stress/displacement claim is validated.",
        "",
        "## Missing information",
        *_bullet_lines(_missing_information_lines(data), missing_text="- No obvious Phase 5A summary inputs are missing."),
        "",
        "## Suggested next structured files to inspect",
        *_bullet_lines(_inspection_lines(data), missing_text="- Inspect `manifest.json` first."),
        "",
    ]
    return "\n".join(lines)


def _known_source_of_truth_paths(data: SummaryData) -> list[str]:
    candidates = [
        "manifest.json",
        TOPOLOGY_MAP_PATH,
        FEATURE_GRAPH_PATH,
        CONSTRAINTS_PATH,
        SIMULATION_SETUP_PATH,
        CAE_SOURCE_DECK_PATH,
        CAE_PARSED_MATERIALS_PATH,
        CAE_PARSED_BCS_PATH,
        CAE_PARSED_LOADS_PATH,
        CAE_MAPPING_PATH,
        PROTECTED_REGIONS_PATH,
        OBJECT_REGISTRY_PATH,
        INTERFACE_GRAPH_PATH,
        VISUAL_MODEL_MANIFEST_PATH,
        VISUAL_ANNOTATION_PATH,
        TASK_SPEC_PATH,
        EXTERNAL_TOOL_REQUIREMENTS_PATH,
        EVIDENCE_INDEX_PATH,
        TOOL_TRACE_PATH,
        COMPLETENESS_REPORT_PATH,
        EVIDENCE_REPORT_PATH,
    ]
    return [f"`{path}`" for path in candidates if path in data.names]


def _resource_paths(resources: Any) -> list[str]:
    paths: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            paths.append(f"`{value}`")
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(resources)
    return sorted(set(paths))


def _geometry_resource_lines(data: SummaryData) -> list[str]:
    resources = data.manifest.get("resources", {})
    geometry = resources.get("geometry", {}) if isinstance(resources, dict) else {}
    if not isinstance(geometry, dict):
        return []
    return [f"`{key}` -> `{value}`" for key, value in sorted(geometry.items()) if isinstance(value, str)]


def _topology_summary_lines(topology_map: Any | None) -> list[str]:
    if not isinstance(topology_map, dict):
        return []
    entities = topology_map.get("entities", [])
    if not isinstance(entities, list):
        return ["Topology map exists but `entities` is not a list."]
    counts: dict[str, int] = {}
    surface_counts: dict[str, int] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("type", "unknown"))
        counts[entity_type] = counts.get(entity_type, 0) + 1
        if entity_type == "face" and isinstance(entity.get("surface_type"), str):
            surface_type = entity["surface_type"]
            surface_counts[surface_type] = surface_counts.get(surface_type, 0) + 1
    lines = [f"{entity_type}: {count}" for entity_type, count in sorted(counts.items())]
    lines.extend(f"face surface `{surface}`: {count}" for surface, count in sorted(surface_counts.items()))
    return lines


def _aag_lines(aag: Any | None) -> list[str]:
    if not isinstance(aag, dict):
        return []
    nodes = aag.get("nodes") if isinstance(aag.get("nodes"), list) else []
    arcs = aag.get("arcs") if isinstance(aag.get("arcs"), list) else []
    generation_method = aag.get("generation_method") if isinstance(aag.get("generation_method"), dict) else {}
    evidence = generation_method.get("adjacency_evidence", "unknown")
    return [
        f"nodes: {len(nodes)}",
        f"arcs: {len(arcs)}",
        f"adjacency evidence: `{evidence}`",
        "AAG is generated from topology_map and is not source-of-truth geometry data.",
        "AAG adjacency/continuity data is not solver evidence.",
    ]


def _feature_lines(feature_graph: Any | None, *, include_details: bool = False) -> list[str]:
    if not isinstance(feature_graph, dict) or not isinstance(feature_graph.get("features"), list):
        return []
    lines: list[str] = []
    for feature in feature_graph["features"]:
        if not isinstance(feature, dict):
            continue
        feature_id = feature.get("id", "unknown_feature_id")
        feature_type = feature.get("type", "unknown_type")
        name = feature.get("name", "Unnamed feature")
        line = f"`{feature_id}` ({feature_type}): {name}"
        recognition = feature.get("recognition")
        if include_details and isinstance(recognition, dict):
            method = recognition.get("method", "unknown_method")
            confidence = recognition.get("confidence", "unknown_confidence")
            line += f"; candidate recognition `{method}` confidence `{confidence}`"
        geometry_refs = feature.get("geometry_refs")
        if include_details and isinstance(geometry_refs, dict):
            refs = []
            if geometry_refs.get("faces"):
                refs.append(f"faces={geometry_refs['faces']}")
            if geometry_refs.get("edges"):
                refs.append(f"edges={geometry_refs['edges']}")
            if refs:
                line += f"; refs: {'; '.join(refs)}"
        if include_details and feature.get("editable"):
            params = feature.get("parameters")
            if isinstance(params, dict) and params:
                scalar_parts = [
                    f"{k}={v}" for k, v in params.items()
                    if not isinstance(v, (list, dict))
                ]
                if scalar_parts:
                    src = feature.get("parameter_source", "unknown")
                    line += f"; editable params ({src}): {', '.join(scalar_parts)}"
        lines.append(line)
    return lines


def _feature_recognition_quality_lines(feature_graph: Any | None) -> list[str]:
    if not isinstance(feature_graph, dict):
        return []
    features = feature_graph.get("features")
    if not isinstance(features, list):
        return []

    confidence_counts: dict[str, int] = {}
    uncertain_count = 0
    method_counts: dict[str, int] = {}
    total = 0

    for feature in features:
        if not isinstance(feature, dict):
            continue
        total += 1
        recognition = feature.get("recognition")
        if not isinstance(recognition, dict):
            confidence_counts["unknown"] = confidence_counts.get("unknown", 0) + 1
            uncertain_count += 1
            continue

        confidence = recognition.get("confidence")
        confidence_key = confidence if isinstance(confidence, str) and confidence else "unknown"
        confidence_counts[confidence_key] = confidence_counts.get(confidence_key, 0) + 1

        method = recognition.get("method")
        if isinstance(method, str) and method:
            method_counts[method] = method_counts.get(method, 0) + 1

        notes = recognition.get("uncertainty_notes")
        if isinstance(notes, list) and notes:
            uncertain_count += 1

    if total == 0:
        return ["No feature entries are present."]

    confidence_text = ", ".join(
        f"{key}={value}" for key, value in sorted(confidence_counts.items())
    )
    lines = [
        f"feature_count: {total}",
        f"confidence_counts: {confidence_text}",
        f"features_with_explicit_uncertainty_notes: {uncertain_count}/{total}",
    ]

    if method_counts:
        method_text = ", ".join(
            f"{key}={value}" for key, value in sorted(method_counts.items())
        )
        lines.append(f"recognition_methods: {method_text}")

    lines.append("Recognition output is candidate-level and requires validation before engineering claims.")
    return lines


def _constraint_lines(constraints: Any | None) -> list[str]:
    if not isinstance(constraints, dict) or not isinstance(constraints.get("constraints"), list):
        return []
    lines: list[str] = []
    for constraint in constraints["constraints"]:
        if not isinstance(constraint, dict):
            continue
        constraint_id = constraint.get("id", "unknown_constraint_id")
        constraint_type = constraint.get("type", "unknown_type")
        target = constraint.get("target", "unknown_target")
        reason = constraint.get("reason", "No reason recorded.")
        metric = constraint.get("metric")
        value = constraint.get("value")
        operator = constraint.get("operator")
        suffix = f"; target metric `{metric}` {operator} {value}" if metric is not None else ""
        lines.append(f"`{constraint_id}` ({constraint_type}) targets `{target}`: {reason}{suffix}")
    return lines


def _protected_lines(protected_regions: Any | None) -> list[str]:
    if not isinstance(protected_regions, dict) or not isinstance(protected_regions.get("protected_regions"), list):
        return []
    lines: list[str] = []
    for region in protected_regions["protected_regions"]:
        if not isinstance(region, dict):
            continue
        feature_id = region.get("feature_id", "unknown_feature_id")
        reason = region.get("reason", "No reason recorded.")
        forbidden = region.get("forbidden_operations", [])
        lines.append(f"`{feature_id}`: {reason} Forbidden operations: {forbidden}")
    return lines


def _simulation_lines(simulation_setup: Any | None, *, include_materials: bool = False) -> list[str]:
    if not isinstance(simulation_setup, dict):
        return []
    lines = [
        f"simulation_id: `{simulation_setup.get('simulation_id', 'unknown')}`",
        f"simulation_type: `{simulation_setup.get('simulation_type', 'unknown')}`",
        f"solver_target: `{simulation_setup.get('solver_target', 'unknown')}`",
    ]
    if include_materials:
        materials = simulation_setup.get("materials", {})
        if isinstance(materials, dict):
            for name, properties in sorted(materials.items()):
                lines.append(f"material `{name}`: {_inline_json(properties)}")
        assignments = simulation_setup.get("assignments", [])
        if isinstance(assignments, list):
            for assignment in assignments:
                if isinstance(assignment, dict):
                    lines.append(
                        f"material assignment: `{assignment.get('material', 'unknown')}` -> body `{assignment.get('target_body', 'unknown')}`"
                    )
    boundary_conditions = simulation_setup.get("boundary_conditions", [])
    if isinstance(boundary_conditions, list):
        for bc in boundary_conditions:
            if isinstance(bc, dict):
                lines.append(f"boundary condition `{bc.get('id', 'unknown')}`: {bc.get('type', 'unknown')} on `{bc.get('target_feature', 'unknown')}`")
    loads = simulation_setup.get("loads", [])
    if isinstance(loads, list):
        for load in loads:
            if isinstance(load, dict):
                lines.append(
                    f"load `{load.get('id', 'unknown')}`: {load.get('type', 'unknown')} {load.get('value_n', 'unknown')} N on `{load.get('target_feature', 'unknown')}` direction {load.get('direction', 'unknown')}"
                )
    targets = simulation_setup.get("targets", {})
    if isinstance(targets, dict):
        for key, value in sorted(targets.items()):
            lines.append(f"target `{key}`: {value}")
    return lines


def _assumption_lines(data: SummaryData) -> list[str]:
    assumptions: list[str] = []
    for resource in (data.constraints, data.simulation_setup):
        if isinstance(resource, dict) and isinstance(resource.get("assumptions"), list):
            for assumption in resource["assumptions"]:
                if isinstance(assumption, str) and assumption not in assumptions:
                    assumptions.append(assumption)
    return assumptions


def _missing_information_lines(data: SummaryData) -> list[str]:
    checks = [
        (TOPOLOGY_MAP_PATH, "Topology map is missing; topology IDs and surface types are unavailable."),
        (FEATURE_GRAPH_PATH, "Feature graph is missing; engineering feature candidates are unavailable."),
        (CONSTRAINTS_PATH, "Constraints are missing; protected engineering requirements may be unavailable."),
        (SIMULATION_SETUP_PATH, "Simulation setup is missing; no analysis intent is declared."),
        (CAE_SOURCE_DECK_PATH, "Imported CAE deck source is missing; no external CAE deck import has been attached."),
        (CAE_MAPPING_PATH, "CAE mapping scaffold is missing; imported CAE entities cannot be checked against feature/interface IDs."),
        (PROTECTED_REGIONS_PATH, "Protected regions are missing; modification restrictions are unavailable."),
        (EVIDENCE_INDEX_PATH, "Evidence ledger is absent; no external tool evidence has been recorded. Run `aieng write-evidence-scaffold` to generate the scaffold."),
        (COMPLETENESS_REPORT_PATH, "Completeness report is absent; available/partial/missing/unsupported CAD/CAE information has not been explicitly indexed."),
        (EVIDENCE_REPORT_PATH, "Consolidated evidence report is absent; claim/evidence read-view synthesis is not available."),
    ]
    lines: list[str] = []
    for path, message in checks:
        if path.endswith("/"):
            if not any(name.startswith(path) and not name.endswith("/") for name in data.names):
                lines.append(message)
        elif path not in data.names:
            lines.append(message)
    return lines


def _inspection_lines(data: SummaryData) -> list[str]:
    ordered = [
        "manifest.json",
        TASK_SPEC_PATH,
        EXTERNAL_TOOL_REQUIREMENTS_PATH,
        EVIDENCE_INDEX_PATH,
        COMPLETENESS_REPORT_PATH,
        TOPOLOGY_MAP_PATH,
        AAG_PATH,
        FEATURE_GRAPH_PATH,
        CONSTRAINTS_PATH,
        SIMULATION_SETUP_PATH,
        CAE_SOURCE_DECK_PATH,
        CAE_PARSED_MATERIALS_PATH,
        CAE_PARSED_BCS_PATH,
        CAE_PARSED_LOADS_PATH,
        CAE_MAPPING_PATH,
        PROTECTED_REGIONS_PATH,
        OBJECT_REGISTRY_PATH,
        VISUAL_MODEL_MANIFEST_PATH,
        VISUAL_ANNOTATION_PATH,
    ]
    return [f"`{path}`" for path in ordered if path in data.names]


def _cae_lines(data: SummaryData) -> list[str]:
    lines: list[str] = []
    if CAE_SOURCE_DECK_PATH in data.names:
        lines.append("`simulation/cae_imports/source_solver_deck.inp` is present (imported external deck source).")
    if CAE_PARSED_MATERIALS_PATH in data.names:
        lines.append("`simulation/cae_imports/parsed_materials.json` is present.")
    if CAE_PARSED_BCS_PATH in data.names:
        lines.append("`simulation/cae_imports/parsed_boundary_conditions.json` is present.")
    if CAE_PARSED_LOADS_PATH in data.names:
        lines.append("`simulation/cae_imports/parsed_loads.json` is present.")

    mapping = data.cae_mapping if isinstance(data.cae_mapping, dict) else None
    if CAE_MAPPING_PATH in data.names:
        if mapping and isinstance(mapping.get("mapping_summary"), dict):
            mapped_count = mapping["mapping_summary"].get("mapped_count", 0)
            unmapped_count = mapping["mapping_summary"].get("unmapped_count", 0)
            lines.append(
                "`simulation/cae_mapping.json` is present: "
                f"mapped={mapped_count}, unmapped={unmapped_count}."
            )
            mappings = mapping.get("mappings")
            if isinstance(mappings, list):
                user_provided_count = sum(
                    1
                    for item in mappings
                    if isinstance(item, dict)
                    and item.get("mapping_method") == "user_provided"
                    and item.get("mapping_status") in {"mapped", "partially_mapped"}
                )
                if user_provided_count > 0:
                    lines.append(
                        "Mapped CAE entities include explicit user-provided references to feature/interface IDs "
                        f"(count={user_provided_count})."
                    )
                    lines.append(
                        "These mappings are user-provided and not automatically inferred from CAE target names."
                    )
        else:
            lines.append("`simulation/cae_mapping.json` is present.")

    if lines:
        lines.append("CAE import resources are parsed scaffold inputs and do not indicate mesh generation or solver execution.")
    return lines


def _interface_cae_lines(data: SummaryData) -> list[str]:
    graph = data.interface_graph if isinstance(data.interface_graph, dict) else None
    if not graph or not isinstance(graph.get("interfaces"), list):
        return []

    lines: list[str] = []
    for interface in graph["interfaces"]:
        if not isinstance(interface, dict):
            continue
        interface_id = interface.get("id", "unknown_interface")
        refs = interface.get("cae_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            maps_to = ref.get("maps_to") if isinstance(ref.get("maps_to"), dict) else {}
            feature_id = maps_to.get("feature_id", "unknown_feature")
            method = ref.get("mapping_method", "unknown_method")
            confidence = ref.get("confidence", "unknown_confidence")
            lines.append(
                "`{entity}` ({cae_type}) is explicitly linked to interface `{iface}` "
                "and feature `{feature}`; mapping_method=`{method}`, confidence=`{confidence}`."
                .format(
                    entity=ref.get("cae_entity", "unknown_cae_entity"),
                    cae_type=ref.get("cae_type", "unknown_cae_type"),
                    iface=interface_id,
                    feature=feature_id,
                    method=method,
                    confidence=confidence,
                )
            )

    if lines:
        lines.append(
            "Explicit CAE interface mappings improve traceability but do not imply mesh generation, solver execution, or solver results."
        )
    return lines


def _external_tool_requirements_lines(ext_req: Any | None) -> list[str]:
    if not isinstance(ext_req, dict):
        return []
    lines: list[str] = []
    handoff_id = ext_req.get("handoff_id")
    if isinstance(handoff_id, str):
        lines.append(f"handoff_id: `{handoff_id}`")
    source_task_id = ext_req.get("source_task_id")
    if isinstance(source_task_id, str):
        lines.append(f"source_task_id: `{source_task_id}`")
    policy = ext_req.get("handoff_policy")
    if isinstance(policy, dict):
        ext_exec = policy.get("external_tools_execute")
        core_exec = policy.get("aieng_core_executes_external_tools")
        if ext_exec is True:
            lines.append("external_tools_execute: true — CAD modification, mesh generation, solver execution performed by external tools only")
        if core_exec is False:
            lines.append("aieng_core_executes_external_tools: false — .aieng core does not invoke CAD kernels, meshers, solvers, or manufacturing checkers")
    caps = ext_req.get("required_capabilities")
    if isinstance(caps, list):
        required = [c.get("capability") for c in caps if isinstance(c, dict) and c.get("required") is True]
        optional = [c.get("capability") for c in caps if isinstance(c, dict) and c.get("required") is False]
        if required:
            lines.append(f"required capabilities: {[c for c in required if c]}")
        if optional:
            lines.append(f"optional capabilities (external tools only): {[c for c in optional if c]}")
    writeback = ext_req.get("writeback_requirements")
    if isinstance(writeback, list):
        lines.append(f"writeback_requirements: {writeback}")
    forbidden = ext_req.get("forbidden_core_actions")
    if isinstance(forbidden, list):
        lines.append(f"forbidden_core_actions: {forbidden}")
    return lines


def _task_spec_lines(task_spec: Any | None) -> list[str]:
    if not isinstance(task_spec, dict):
        return []
    lines: list[str] = []
    task_id = task_spec.get("task_id")
    if isinstance(task_id, str):
        lines.append(f"task_id: `{task_id}`")
    intent = task_spec.get("intent")
    if isinstance(intent, str):
        lines.append(f"intent: {intent}")
    mode = task_spec.get("mode")
    if isinstance(mode, str):
        lines.append(f"mode: `{mode}`")
    required_outputs = task_spec.get("required_outputs")
    if isinstance(required_outputs, list):
        lines.append(f"required_outputs: {required_outputs}")
    forbidden_claims = task_spec.get("forbidden_claims")
    if isinstance(forbidden_claims, list):
        lines.append(f"forbidden_claims: {forbidden_claims}")
    evidence = task_spec.get("evidence_required_before_acceptance")
    if isinstance(evidence, list):
        lines.append(f"evidence_required_before_acceptance: {evidence}")
    return lines


def _evidence_index_lines(evidence_index: Any | None) -> list[str]:
    if not isinstance(evidence_index, dict):
        return []
    lines: list[str] = []
    ev_id = evidence_index.get("evidence_index_id")
    if isinstance(ev_id, str):
        lines.append(f"evidence_index_id: `{ev_id}`")
    source_task_id = evidence_index.get("source_task_id")
    if isinstance(source_task_id, str):
        lines.append(f"source_task_id: `{source_task_id}`")
    source_handoff_id = evidence_index.get("source_handoff_id")
    if isinstance(source_handoff_id, str):
        lines.append(f"source_handoff_id: `{source_handoff_id}`")
    items = evidence_index.get("evidence_items")
    if isinstance(items, list):
        lines.append(f"evidence_items: {len(items)} item(s)")

        # Breakdown by evidence_type
        type_counts: dict[str, int] = {}
        producer_counts: dict[str, int] = {}
        vstatus_counts: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            ev_type = item.get("evidence_type", "unknown")
            type_counts[ev_type] = type_counts.get(ev_type, 0) + 1
            producer_kind = item.get("producer", {}).get("kind", "unknown") if isinstance(item.get("producer"), dict) else "unknown"
            producer_counts[producer_kind] = producer_counts.get(producer_kind, 0) + 1
            vstatus = item.get("verification", {}).get("status", "unknown") if isinstance(item.get("verification"), dict) else "unknown"
            vstatus_counts[vstatus] = vstatus_counts.get(vstatus, 0) + 1

        if type_counts:
            type_summary = ", ".join(f"{k}: {v}" for k, v in sorted(type_counts.items()))
            lines.append(f"  by type: {type_summary}")
        if producer_counts:
            prod_summary = ", ".join(f"{k}: {v}" for k, v in sorted(producer_counts.items()))
            lines.append(f"  by producer kind: {prod_summary}")
        if vstatus_counts:
            vstatus_summary = ", ".join(f"{k}: {v}" for k, v in sorted(vstatus_counts.items()))
            lines.append(f"  by verification status: {vstatus_summary}")

        solver_import_summaries = _solver_import_marker_summaries(items)
        if solver_import_summaries:
            lines.append(f"  solver evidence imports with known marker summaries: {len(solver_import_summaries)}")
            for summary in solver_import_summaries[:3]:
                lines.append(f"    {summary}")
            if len(solver_import_summaries) > 3:
                lines.append(f"    ... {len(solver_import_summaries) - 3} more")

        mesh_import_summaries, mesh_without_quality = _mesh_import_summaries(items)
        if mesh_import_summaries:
            lines.append(f"  mesh evidence imports with known summaries: {len(mesh_import_summaries)}")
            for summary in mesh_import_summaries[:3]:
                lines.append(f"    {summary}")
            if len(mesh_import_summaries) > 3:
                lines.append(f"    ... {len(mesh_import_summaries) - 3} more")
            if mesh_without_quality:
                lines.append(
                    f"  mesh quality metrics not declared in {mesh_without_quality} imported mesh evidence item(s); do not infer quality pass/fail."
                )

    policy = evidence_index.get("claim_policy")
    if isinstance(policy, dict):
        if policy.get("external_tools_execute") is True:
            lines.append("external_tools_execute: true — solver, mesh, and CAD modification performed by external tools only")
        if policy.get("aieng_core_generates_solver_evidence") is False:
            lines.append("aieng_core_generates_solver_evidence: false — .aieng core does not run solvers")
        if policy.get("aieng_core_generates_mesh_evidence") is False:
            lines.append("aieng_core_generates_mesh_evidence: false — .aieng core does not generate meshes")
        if policy.get("aieng_core_modifies_cad_geometry") is False:
            lines.append("aieng_core_modifies_cad_geometry: false — .aieng core does not directly modify CAD geometry")
    lines.append("Imported or recorded evidence artifacts do not automatically update claim verification status; claim proposals require human review.")
    return lines


def _solver_import_marker_summaries(items: list[Any]) -> list[str]:
    summaries: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("evidence_type") != "solver_result":
            continue
        notes = item.get("notes")
        if not isinstance(notes, str):
            continue
        marker_line: str | None = None
        line_count_line: str | None = None
        for note_line in notes.splitlines():
            stripped = note_line.strip()
            if "known_marker_counts=" in stripped:
                marker_line = stripped
            elif "line_count=" in stripped:
                line_count_line = stripped
        if marker_line is None and line_count_line is None:
            continue
        evidence_id = item.get("evidence_id", "unknown")
        details = "; ".join(part for part in [line_count_line, marker_line] if part)
        summaries.append(f"`{evidence_id}`: {details}")
    return summaries


def _mesh_import_summaries(items: list[Any]) -> tuple[list[str], int]:
    summaries: list[str] = []
    mesh_without_quality = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("evidence_type") != "mesh_evidence":
            continue
        structured = _structured_mesh_summary(item)
        if structured is not None:
            summaries.append(structured["line"])
            if structured["quality_missing"]:
                mesh_without_quality += 1
            continue

        notes = item.get("notes")
        if not isinstance(notes, str):
            continue
        mesh_summary_line: str | None = None
        for note_line in notes.splitlines():
            stripped = note_line.strip()
            if "mesh_summary=" in stripped:
                mesh_summary_line = stripped
                break
        if mesh_summary_line is None:
            continue

        summary_value = mesh_summary_line.split("mesh_summary=", 1)[1].strip()
        parsed: dict[str, Any] | None = None
        try:
            maybe = ast.literal_eval(summary_value)
            if isinstance(maybe, dict):
                parsed = maybe
        except (SyntaxError, ValueError):
            parsed = None

        evidence_id = item.get("evidence_id", "unknown")
        if not isinstance(parsed, dict):
            summaries.append(f"`{evidence_id}`: mesh_summary=unparsed")
            continue

        detected = parsed.get("detected_format", "unknown")
        version = parsed.get("format_version")
        nodes = parsed.get("nodes_declared")
        elements = parsed.get("elements_declared")
        quality_present = parsed.get("quality_metrics_present") is True
        if not quality_present:
            mesh_without_quality += 1
        version_text = f" v{version}" if isinstance(version, str) else ""
        summaries.append(
            f"`{evidence_id}`: format={detected}{version_text}, nodes_declared={nodes}, elements_declared={elements}, quality_metrics_present={quality_present}"
        )
    return summaries, mesh_without_quality


def _structured_mesh_summary(item: dict[str, Any]) -> dict[str, Any] | None:
    payload = item.get("structured_payload")
    if not isinstance(payload, dict) or payload.get("payload_type") != "mesh_artifact_summary":
        return None
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return None
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        artifact = {}
    quality = summary.get("quality_metrics")
    if not isinstance(quality, dict):
        quality = {}

    evidence_id = item.get("evidence_id", "unknown")
    mesh_format = payload.get("mesh_format", "unknown")
    version = summary.get("format_version")
    nodes = summary.get("nodes_declared")
    elements = summary.get("elements_declared")
    storage_mode = artifact.get("storage_mode", "unknown")
    quality_present = quality.get("metrics_present") is True
    version_text = f" v{version}" if isinstance(version, str) else ""
    return {
        "line": (
            f"`{evidence_id}`: format={mesh_format}{version_text}, storage_mode={storage_mode}, "
            f"nodes_declared={nodes}, elements_declared={elements}, quality_metrics_present={quality_present}"
        ),
        "quality_missing": not quality_present,
    }


def _tool_trace_lines(tool_trace: Any | None) -> list[str]:
    if not isinstance(tool_trace, dict):
        return []
    lines: list[str] = []
    trace_id = tool_trace.get("tool_trace_id")
    if isinstance(trace_id, str):
        lines.append(f"tool_trace_id: `{trace_id}`")
    source_task_id = tool_trace.get("source_task_id")
    if isinstance(source_task_id, str):
        lines.append(f"source_task_id: `{source_task_id}`")
    source_handoff_id = tool_trace.get("source_handoff_id")
    if isinstance(source_handoff_id, str):
        lines.append(f"source_handoff_id: `{source_handoff_id}`")
    entries = tool_trace.get("entries")
    if isinstance(entries, list):
        lines.append(f"entries: {len(entries)} step(s) recorded")
        tool_ids: list[str] = []
        exit_counts: dict[str, int] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            tool = entry.get("tool")
            if isinstance(tool, dict):
                tid = tool.get("tool_id")
                if isinstance(tid, str) and tid not in tool_ids:
                    tool_ids.append(tid)
            step = entry.get("step")
            if isinstance(step, dict):
                exit_status = step.get("exit_status", "unknown")
                exit_counts[exit_status] = exit_counts.get(exit_status, 0) + 1
        if tool_ids:
            lines.append(f"  tools involved: {tool_ids}")
        if exit_counts:
            exit_summary = ", ".join(f"{k}: {v}" for k, v in sorted(exit_counts.items()))
            lines.append(f"  exit statuses: {exit_summary}")
        failures = exit_counts.get("failure", 0)
        if failures:
            lines.append(f"  WARNING: {failures} step(s) recorded exit_status=failure — review tool trace for details")
    lines.append(
        "Tool trace records external tool-reported steps; .aieng did not execute them. "
        "Tool trace is audit/provenance, not engineering validation by itself."
    )
    return lines


def _completeness_report_lines(report: Any | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    lines: list[str] = []
    report_id = report.get("report_id")
    if isinstance(report_id, str):
        lines.append(f"report_id: `{report_id}`")
    conversion_mode = report.get("conversion_mode")
    if isinstance(conversion_mode, str):
        lines.append(f"conversion_mode: `{conversion_mode}`")
    policy = report.get("claim_policy")
    if isinstance(policy, dict):
        if policy.get("best_effort_conversion") is True:
            lines.append("best_effort_conversion: true — convert available CAD/CAE information without requiring all fields to exist")
        if policy.get("missingness_explicit") is True:
            lines.append("missingness_explicit: true — missing/unknown/unsupported information must be stated, not guessed")
        if policy.get("unsupported_is_not_false") is True:
            lines.append("unsupported_is_not_false: true — unsupported claims are not false; they lack evidence")
    categories = report.get("categories")
    if isinstance(categories, list):
        counts: dict[str, int] = {}
        missing_categories: list[str] = []
        partial_categories: list[str] = []
        unsupported_categories: list[str] = []
        for category in categories:
            if not isinstance(category, dict):
                continue
            status = category.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
            name = category.get("category", "unknown")
            if status == "missing":
                missing_categories.append(name)
            elif status == "partial":
                partial_categories.append(name)
            elif status == "unsupported":
                unsupported_categories.append(name)
        if counts:
            lines.append("category status counts: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
        if missing_categories:
            lines.append(f"missing categories: {missing_categories}")
        if partial_categories:
            lines.append(f"partial categories: {partial_categories}")
        if unsupported_categories:
            lines.append(f"unsupported categories: {unsupported_categories}")
    actions = report.get("next_recommended_actions")
    if isinstance(actions, list) and actions:
        compact_actions = [
            action.get("action")
            for action in actions
            if isinstance(action, dict) and isinstance(action.get("action"), str)
        ]
        if compact_actions:
            lines.append(f"next_recommended_actions: {compact_actions}")
    return lines


def _evidence_report_lines(report: Any | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    lines: list[str] = []
    report_id = report.get("report_id")
    if isinstance(report_id, str):
        lines.append(f"report_id: `{report_id}`")

    counts = report.get("claim_status_counts")
    if isinstance(counts, dict):
        lines.append(
            "claim_status_counts: "
            + ", ".join(
                f"{key}={counts.get(key, 0)}"
                for key in ("pass", "fail", "unsupported", "partially_supported", "needs_review")
            )
        )

    snapshot = report.get("validation_state_snapshot")
    if isinstance(snapshot, dict):
        lines.append(
            "validation_state_snapshot: "
            f"solver_execution={snapshot.get('solver_execution')}, "
            f"mesh_generation={snapshot.get('mesh_generation')}, "
            f"patch_execution={snapshot.get('patch_execution')}"
        )

    source_files = report.get("source_files")
    if isinstance(source_files, list) and source_files:
        lines.append(f"source_files: {source_files}")

    lines.append("Consolidated evidence report is a derived view only; source ledgers remain authoritative.")
    return lines


def _bullet_lines(items: list[str], *, missing_text: str) -> list[str]:
    if not items:
        return [missing_text]
    return [item if item.startswith("-") else f"- {item}" for item in items]


def _inline_json(value: Any) -> str:
    return "`" + json.dumps(value, sort_keys=True) + "`"


def _rewrite_package_with_summaries(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    readme_text: str,
    summary_text: str,
) -> None:
    resources = manifest.setdefault("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("manifest resources must be an object")
    ai_resources = resources.setdefault("ai", {})
    if not isinstance(ai_resources, dict):
        raise ValueError("manifest resources.ai must be an object")
    resources["readme_for_ai"] = README_FOR_AI_PATH
    ai_resources["summary"] = AI_SUMMARY_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    readme_bytes = readme_text.rstrip() + "\n"
    summary_bytes = summary_text.rstrip() + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(README_FOR_AI_PATH, readme_bytes)
            out_package.writestr(AI_SUMMARY_PATH, summary_bytes)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
