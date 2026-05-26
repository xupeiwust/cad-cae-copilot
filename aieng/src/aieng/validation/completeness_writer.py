"""Write validation/completeness_report.json to an existing .aieng package.

The report implements best-effort semantic conversion with explicit missingness:
write what is present, mark absent or unsupported information, and never infer
missing CAD/CAE facts.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

COMPLETENESS_REPORT_PATH = "validation/completeness_report.json"
VALIDATION_DIR = "validation/"

_CLAIM_POLICY: dict[str, Any] = {
    "best_effort_conversion": True,
    "missingness_explicit": True,
    "do_not_infer_missing_information": True,
    "unsupported_is_not_false": True,
    "external_tools_execute": True,
    "aieng_core_executes_external_tools": False,
}

_SOURCE_ARTIFACT_CANDIDATES = (
    "geometry/source.step",
    "geometry/normalized.step",
    "simulation/solver_deck.inp",
    "simulation/updated_deck.inp",
    "simulation/cae_imports/source_solver_deck.inp",
)


def write_completeness_report_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Generate validation/completeness_report.json for an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if COMPLETENESS_REPORT_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{COMPLETENESS_REPORT_PATH} already exists; use --overwrite to replace it"
                )
            manifest = json.loads(package.read("manifest.json"))
            members = _read_members(package, exclude={"manifest.json", COMPLETENESS_REPORT_PATH})
            evidence_index = _read_optional_json(package, "results/evidence_index.json")
            topology_map = _read_optional_json(package, "geometry/topology_map.json")
            conversion_manifest = _read_optional_json(
                package, "provenance/conversion_manifest.json"
            )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    report = build_completeness_report(
        manifest,
        names,
        evidence_index=evidence_index,
        topology_map=topology_map,
        conversion_manifest=conversion_manifest,
    )
    resources = manifest.setdefault("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("manifest resources must be an object")
    validation_resources = resources.setdefault("validation", {})
    if not isinstance(validation_resources, dict):
        raise ValueError("manifest resources.validation must be an object")
    validation_resources["completeness_report"] = COMPLETENESS_REPORT_PATH

    manifest_json = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    report_json = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    existing_filenames = {info.filename for info, _ in members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp_path = Path(fh.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out:
            for info, data in members:
                out.writestr(info, data)
            if VALIDATION_DIR not in existing_filenames:
                out.writestr(VALIDATION_DIR, b"")
            out.writestr("manifest.json", manifest_json)
            out.writestr(COMPLETENESS_REPORT_PATH, report_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return path


def build_completeness_report(
    manifest: dict[str, Any],
    names: set[str],
    *,
    evidence_index: Any | None = None,
    topology_map: Any | None = None,
    conversion_manifest: Any | None = None,
) -> dict[str, Any]:
    """Build a deterministic completeness/missingness report from package members."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    model_id = str(manifest.get("model_id") or "unknown_model")
    source_mode = str(manifest.get("source_mode") or "unknown")
    real_geometry_extraction = _real_geometry_extraction(names, topology_map=topology_map)
    categories = _categories(
        names,
        evidence_index=evidence_index,
        source_mode=source_mode,
        conversion_manifest=conversion_manifest,
    )
    return {
        "format_version": FORMAT_VERSION,
        "report_id": "completeness_001",
        "model_id": model_id,
        "generated_at_utc": now,
        "source_mode": source_mode if source_mode in {"step", "definition", "converter"} else "unknown",
        "real_geometry_extraction": real_geometry_extraction,
        "conversion_mode": "best_effort",
        "claim_policy": dict(_CLAIM_POLICY),
        "source_artifacts": [path for path in _SOURCE_ARTIFACT_CANDIDATES if path in names],
        "categories": categories,
        "next_recommended_actions": _recommended_actions(categories),
    }


def _categories(
    names: set[str],
    *,
    evidence_index: Any | None = None,
    source_mode: str = "unknown",
    conversion_manifest: Any | None = None,
) -> list[dict[str, Any]]:
    definition_sourced = source_mode == "definition"
    patch_paths = sorted(name for name in names if name.startswith("ai/patches/") and name.endswith(".json"))
    visual_paths = [p for p in ("visual/model_manifest.json", "visual/annotation_layers.json") if p in names]
    cae_import_paths = [
        p for p in (
            "simulation/cae_imports/source_solver_deck.inp",
            "simulation/cae_imports/parsed_materials.json",
            "simulation/cae_imports/parsed_boundary_conditions.json",
            "simulation/cae_imports/parsed_loads.json",
        )
        if p in names
    ]

    categories = [
        _category(
            "geometry",
            [p for p in ("geometry/source.step", "geometry/normalized.step") if p in names],
            missing_items=[p for p in ("geometry/source.step", "geometry/normalized.step") if p not in names],
            required_for=["cad_reference", "topology_extraction", "geometry_roundtrip"],
            available_status="available",
            notes=[
                (
                    "Definition-sourced package intentionally has no STEP geometry until an external CAD generator or import step creates it."
                    if definition_sourced
                    else "Geometry artifacts are referenced resources; semantic meaning is carried by structured .aieng resources."
                )
            ],
        ),
        _category(
            "topology",
            ["geometry/topology_map.json"] if "geometry/topology_map.json" in names else [],
            missing_items=[] if "geometry/topology_map.json" in names else ["geometry/topology_map.json"],
            required_for=["stable_face_edge_body_references", "feature_grounding"],
            notes=[
                (
                    "Topology is absent for definition-sourced packages until generated or imported CAD geometry exists."
                    if definition_sourced
                    else "Topology IDs should be used for precise AI references when available."
                )
            ],
        ),
        _category(
            "adjacency",
            ["graph/aag.json"] if "graph/aag.json" in names else [],
            missing_items=[] if "graph/aag.json" in names else ["graph/aag.json"],
            required_for=["adjacency_reasoning", "feature_grouping"],
            notes=["AAG is a generated adjacency index, not source-of-truth geometry."],
        ),
        _category(
            "features",
            ["graph/feature_graph.json"] if "graph/feature_graph.json" in names else [],
            status=("available" if definition_sourced and "graph/feature_graph.json" in names else ("partial" if "graph/feature_graph.json" in names else "missing")),
            missing_items=[] if "graph/feature_graph.json" in names else ["graph/feature_graph.json"],
            required_for=["engineering_feature_grounding", "patch_targeting"],
            notes=[
                (
                    "Feature graph is structured design definition; feature geometry references remain semantic-only until CAD generation/topology exists."
                    if definition_sourced
                    else "Feature labels are candidate-level unless stronger CAD/user evidence is provided."
                )
            ],
        ),
        _category(
            "protected_regions",
            ["ai/protected_regions.json"] if "ai/protected_regions.json" in names else [],
            missing_items=[] if "ai/protected_regions.json" in names else ["ai/protected_regions.json"],
            required_for=["safe_patch_proposals", "do_not_modify_constraints"],
            notes=["Missing protected regions means the AI must not assume editable or protected areas."],
        ),
        _category(
            "constraints",
            ["graph/constraints.json"] if "graph/constraints.json" in names else [],
            missing_items=[] if "graph/constraints.json" in names else ["graph/constraints.json"],
            required_for=["design_intent", "validation_targets"],
            notes=["Constraints are structured engineering context, not solver evidence."],
        ),
        _category(
            "simulation_setup",
            (
                ["simulation/setup.yaml"]
                if "simulation/setup.yaml" in names
                else (["engineering_context/material.yaml"] if definition_sourced and "engineering_context/material.yaml" in names else [])
            ),
            status=("partial" if definition_sourced and "engineering_context/material.yaml" in names and "simulation/setup.yaml" not in names else None),
            missing_items=[] if "simulation/setup.yaml" in names else ["simulation/setup.yaml"],
            required_for=["analysis_setup_understanding", "solver_handoff"],
            notes=[
                (
                    "Definition-sourced package may contain simulation intent in engineering_context/material.yaml, but no executable simulation/setup.yaml has been emitted."
                    if definition_sourced and "simulation/setup.yaml" not in names
                    else "Simulation setup is intent/context and does not imply mesh or solver execution."
                )
            ],
        ),
        _category(
            "cae_imports",
            cae_import_paths,
            status="partial" if 0 < len(cae_import_paths) < 4 else ("available" if len(cae_import_paths) == 4 else "missing"),
            missing_items=[
                p for p in (
                    "simulation/cae_imports/source_solver_deck.inp",
                    "simulation/cae_imports/parsed_materials.json",
                    "simulation/cae_imports/parsed_boundary_conditions.json",
                    "simulation/cae_imports/parsed_loads.json",
                )
                if p not in names
            ],
            required_for=["cae_deck_understanding", "cae_entity_mapping"],
            notes=["Imported CAE decks are parsed inputs, not solver execution evidence."],
        ),
        _category(
            "cae_mapping",
            ["simulation/cae_mapping.json"] if "simulation/cae_mapping.json" in names else [],
            missing_items=[] if "simulation/cae_mapping.json" in names else ["simulation/cae_mapping.json"],
            required_for=["cae_to_feature_traceability"],
            notes=["CAE mappings should remain explicit; do not infer unmapped CAE names as feature truth."],
        ),
        _category(
            "mesh_handoff_contract",
            ["simulation/mesh_handoff_contract.json"] if "simulation/mesh_handoff_contract.json" in names else [],
            missing_items=[] if "simulation/mesh_handoff_contract.json" in names else ["simulation/mesh_handoff_contract.json"],
            required_for=["external_meshing_handoff", "mesh_evidence_roundtrip"],
            notes=["Mesh handoff contract describes external meshing expectations; it is not mesh evidence by itself."],
        ),
        _category(
            "task_contract",
            ["task/task_spec.yaml"] if "task/task_spec.yaml" in names else [],
            missing_items=[] if "task/task_spec.yaml" in names else ["task/task_spec.yaml"],
            required_for=["agent_work_order", "forbidden_claim_policy"],
            notes=["Task specs describe requested work and forbidden claims."],
        ),
        _category(
            "external_tool_handoff",
            ["task/external_tool_requirements.json"] if "task/external_tool_requirements.json" in names else [],
            missing_items=[] if "task/external_tool_requirements.json" in names else ["task/external_tool_requirements.json"],
            required_for=["external_cad_cae_execution_boundary", "tool_handoff"],
            notes=["External tool handoff states that CAD/CAE tools execute; .aieng records and validates."],
        ),
        _category(
            "evidence_ledger",
            ["results/evidence_index.json"] if "results/evidence_index.json" in names else [],
            missing_items=[] if "results/evidence_index.json" in names else ["results/evidence_index.json"],
            required_for=["evidence_traceability", "claim_support"],
            notes=["Evidence ledger absence means no external tool evidence has been recorded in the package."],
        ),
        _category(
            "mesh_artifacts",
            _mesh_artifact_resources(evidence_index, names),
            status=_mesh_artifact_status(evidence_index, names),
            missing_items=[] if _has_mesh_evidence(evidence_index) else ["results/evidence_index.json:mesh_evidence"],
            required_for=["mesh_traceability", "claim_mesh_evidence_001"],
            notes=_mesh_artifact_notes(evidence_index),
        ),
        _category(
            "provenance_trace",
            ["provenance/tool_trace.json"] if "provenance/tool_trace.json" in names else [],
            missing_items=[] if "provenance/tool_trace.json" in names else ["provenance/tool_trace.json"],
            required_for=["external_tool_audit_trail", "writeback_traceability"],
            notes=["Tool trace records external tool-reported steps; it is not validation evidence by itself."],
        ),
        _category(
            "validation_status",
            ["validation/status.yaml"] if "validation/status.yaml" in names else [],
            missing_items=[] if "validation/status.yaml" in names else ["validation/status.yaml"],
            required_for=["engineering_claim_discipline", "validation_state_summary"],
            notes=["Validation status is a claim-policy ledger, not a solver result."],
        ),
        _category(
            "visual_resources",
            visual_paths,
            status="partial" if len(visual_paths) == 1 else ("available" if len(visual_paths) == 2 else "missing"),
            missing_items=[p for p in ("visual/model_manifest.json", "visual/annotation_layers.json") if p not in names],
            required_for=["visual_ai_grounding", "preview_mapping"],
            notes=["Visual resources are annotation/manifest scaffolds unless rendered artifacts are explicitly present."],
        ),
        _category(
            "object_registry",
            ["objects/object_registry.json"] if "objects/object_registry.json" in names else [],
            missing_items=[] if "objects/object_registry.json" in names else ["objects/object_registry.json"],
            required_for=["cross_resource_navigation"],
            notes=["Object registry is a generated index, not source-of-truth."],
        ),
        _category(
            "interface_graph",
            ["objects/interface_graph.json"] if "objects/interface_graph.json" in names else [],
            missing_items=[] if "objects/interface_graph.json" in names else ["objects/interface_graph.json"],
            required_for=["interface_reasoning", "cae_boundary_mapping"],
            notes=["Interface graph is generated from structured context and mappings."],
        ),
        _category(
            "patch_proposals",
            patch_paths,
            status="available" if patch_paths else "not_applicable",
            missing_items=[],
            required_for=["structured_modification_proposals"],
            notes=["Patch proposal absence is acceptable unless a modification task is active."],
        ),
        _source_conversion_category(
            names=names,
            source_mode=source_mode,
            conversion_manifest=conversion_manifest,
        ),
    ]
    return categories


def _source_conversion_category(
    *,
    names: set[str],
    source_mode: str,
    conversion_manifest: Any | None,
) -> dict[str, Any]:
    conversion_manifest_path = "provenance/conversion_manifest.json"
    converter_capabilities_path = "provenance/converter_capabilities.json"
    resources = [
        path
        for path in (conversion_manifest_path, converter_capabilities_path)
        if path in names
    ]

    if source_mode != "converter" and conversion_manifest_path not in names:
        return _category(
            "source_conversion",
            resources,
            status="not_applicable",
            missing_items=[],
            required_for=["cad_cae_to_aieng_conversion_provenance"],
            notes=[
                "Package was not produced by a CAD/CAE-to-.aieng converter; conversion manifest is not required.",
            ],
        )

    notes: list[str] = []
    declared_levels: list[int] = []
    achieved_levels: list[int] = []
    converter_id = "unknown_converter"
    source_system = "unknown_source_system"
    if isinstance(conversion_manifest, dict):
        converter_block = conversion_manifest.get("converter")
        if isinstance(converter_block, dict):
            converter_id = str(converter_block.get("converter_id") or converter_id)
            source_system = str(converter_block.get("source_system") or source_system)
        declared_levels = sorted(
            {
                int(entry.get("level"))
                for entry in conversion_manifest.get("declared_capability_levels", []) or []
                if isinstance(entry, dict) and isinstance(entry.get("level"), int)
            }
        )
        achieved_levels = sorted(
            {
                int(entry.get("level"))
                for entry in conversion_manifest.get("achieved_capability_levels", []) or []
                if isinstance(entry, dict) and isinstance(entry.get("level"), int)
            }
        )
    notes.append(f"converter_id={converter_id}")
    notes.append(f"source_system={source_system}")
    if declared_levels:
        notes.append(f"declared_levels={declared_levels}")
    if achieved_levels:
        notes.append(f"achieved_levels={achieved_levels}")
    if declared_levels and achieved_levels:
        gap = sorted(set(declared_levels) - set(achieved_levels))
        if gap:
            notes.append(
                "Source artifact did not provide the information required to reach declared levels: "
                + ",".join(str(level) for level in gap)
            )
    if conversion_manifest_path not in names:
        notes.append(
            "source_mode=converter but provenance/conversion_manifest.json is missing; this is a converter implementation bug."
        )

    status = "available"
    missing_items: list[str] = []
    if conversion_manifest_path not in names:
        status = "missing"
        missing_items.append(conversion_manifest_path)
    elif achieved_levels and 0 not in achieved_levels:
        # L0 is the floor; if a converter ran and did not even achieve L0, that's partial.
        status = "partial"
    elif declared_levels and achieved_levels and set(achieved_levels) < set(declared_levels):
        status = "partial"

    return _category(
        "source_conversion",
        resources,
        status=status,
        missing_items=missing_items,
        required_for=[
            "cad_cae_to_aieng_conversion_provenance",
            "converter_capability_audit",
        ],
        notes=notes,
    )


def _category(
    category: str,
    resources: list[str],
    *,
    status: str | None = None,
    missing_items: list[str] | None = None,
    required_for: list[str] | None = None,
    notes: list[str] | None = None,
    available_status: str = "available",
) -> dict[str, Any]:
    return {
        "category": category,
        "status": status or (available_status if resources else "missing"),
        "resources": resources,
        "missing_items": list(missing_items or []),
        "required_for": list(required_for or []),
        "notes": list(notes or []),
    }


def _recommended_actions(categories: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    by_category = {c["category"]: c for c in categories}

    def add(category: str, action: str, reason: str) -> None:
        actions.append({"category": category, "action": action, "reason": reason})

    if by_category["topology"]["status"] == "missing":
        add("topology", "run_extract_topology_or_emit_topology_map", "Stable topology IDs are needed for grounded feature and patch references.")
    if by_category["features"]["status"] == "missing":
        add("features", "run_recognize_features_or_emit_feature_graph", "Feature candidates help agents target and discuss engineering regions.")
    if by_category["protected_regions"]["status"] == "missing":
        add("protected_regions", "provide_protected_regions", "Modification proposals should not assume which regions may be edited.")
    if by_category["simulation_setup"]["status"] == "missing":
        add("simulation_setup", "provide_simulation_setup", "Material, loads, and boundary conditions are required before analysis claims are meaningful.")
    if by_category["mesh_handoff_contract"]["status"] == "missing":
        add("mesh_handoff_contract", "write_mesh_handoff_contract", "External meshing handoff should be explicit and schema-validated before importing mesh evidence.")
    if by_category["evidence_ledger"]["status"] == "missing":
        add("evidence_ledger", "write_evidence_scaffold", "Claims should be traceable to evidence or explicitly unsupported.")
    if by_category.get("mesh_artifacts", {}).get("status") == "missing":
        add(
            "mesh_artifacts",
            "import_mesh_artifact_or_record_reference",
            "Mesh evidence must be imported from an external mesher or explicitly recorded as an external reference before mesh claims are supported.",
        )
    if by_category["provenance_trace"]["status"] == "missing":
        add("provenance_trace", "record_external_tool_trace_when_tools_run", "External CAD/CAE execution should be auditable after handoff.")
    return actions


def _mesh_evidence_items(evidence_index: Any | None) -> list[dict[str, Any]]:
    if not isinstance(evidence_index, dict):
        return []
    items = evidence_index.get("evidence_items")
    if not isinstance(items, list):
        return []
    return [
        item for item in items
        if isinstance(item, dict) and item.get("evidence_type") == "mesh_evidence"
    ]


def _has_mesh_evidence(evidence_index: Any | None) -> bool:
    return bool(_mesh_evidence_items(evidence_index))


def _mesh_artifact_resources(evidence_index: Any | None, names: set[str]) -> list[str]:
    resources: list[str] = []
    for item in _mesh_evidence_items(evidence_index):
        artifact = item.get("artifact")
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
            path = artifact["path"]
            payload = item.get("structured_payload")
            storage_mode = None
            if isinstance(payload, dict) and isinstance(payload.get("artifact"), dict):
                storage_mode = payload["artifact"].get("storage_mode")
            if storage_mode == "external_reference" or path in names:
                resources.append(path)
    return sorted(set(resources))


def _mesh_artifact_status(evidence_index: Any | None, names: set[str]) -> str:
    items = _mesh_evidence_items(evidence_index)
    if not items:
        return "missing"
    resources = _mesh_artifact_resources(evidence_index, names)
    valid_payload_count = 0
    for item in items:
        payload = item.get("structured_payload")
        if isinstance(payload, dict) and payload.get("payload_type") == "mesh_artifact_summary":
            valid_payload_count += 1
    if resources and valid_payload_count == len(items):
        return "available"
    return "partial"


def _mesh_artifact_notes(evidence_index: Any | None) -> list[str]:
    items = _mesh_evidence_items(evidence_index)
    if not items:
        return ["No mesh evidence has been imported; do not claim mesh generation or mesh quality."]
    return [
        f"Mesh evidence is present for {len(items)} artifact(s), but quality pass/fail remains unknown unless a separate validation report is attached."
    ]


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return json.loads(package.read(member))
    except Exception:
        return None


def _real_geometry_extraction(names: set[str], topology_map: Any | None = None) -> bool:
    if "geometry/topology_map.json" not in names:
        return False
    if not isinstance(topology_map, dict):
        return False
    metadata = topology_map.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("real_step_parsing") is True and metadata.get("extraction_backend") == "occ")


def _read_members(package: zipfile.ZipFile, exclude: set[str]) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in exclude or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members

