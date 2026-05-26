from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-not-found]

from . import FORMAT_VERSION, __version__
from .package import PACKAGE_DIRECTORIES, build_manifest
from .validation.status_writer import ALLOWED_CLAIMS, FORBIDDEN_CLAIMS

try:
    from jsonschema import Draft202012Validator  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - dependency is part of the supported install.
    Draft202012Validator = None  # type: ignore[assignment]

FEATURE_GRAPH_PATH = "graph/feature_graph.json"
CONSTRAINTS_PATH = "graph/constraints.json"
MATERIAL_PATH = "engineering_context/material.yaml"
STATUS_PATH = "validation/status.yaml"
README_FOR_AI_PATH = "README_FOR_AI.md"
COMPLETENESS_REPORT_PATH = "validation/completeness_report.json"


def define_package(
    definition_path: str | Path,
    out: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Create a definition-sourced .aieng package from structured YAML."""
    definition_file = Path(definition_path)
    out_path = Path(out)

    if not definition_file.exists():
        raise FileNotFoundError(f"definition file does not exist: {definition_file}")
    if not definition_file.is_file():
        raise ValueError(f"definition path is not a file: {definition_file}")
    if out_path.suffix != ".aieng":
        raise ValueError("output path must end with .aieng")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"package already exists: {out_path}")

    definition = _read_definition(definition_file)
    _validate_definition(definition)

    model_id = definition["model_id"].strip()
    manifest = _build_definition_manifest(model_id)
    feature_graph = _build_feature_graph(definition)
    constraints = {
        "format_version": FORMAT_VERSION,
        "constraints": list(definition.get("constraints", [])),
        "assumptions": list(definition.get("assumptions", [])) + [
            "Package is definition-sourced and does not contain STEP geometry.",
            "Feature geometry references are semantic-only until geometry generation is implemented.",
        ],
    }
    material = _build_material(definition)
    status = _build_status(definition)
    readme = _build_readme(definition)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for directory in PACKAGE_DIRECTORIES:
            package.writestr(directory, b"")
        package.writestr(FEATURE_GRAPH_PATH, json.dumps(feature_graph, indent=2, sort_keys=True) + "\n")
        package.writestr(CONSTRAINTS_PATH, json.dumps(constraints, indent=2, sort_keys=True) + "\n")
        package.writestr(MATERIAL_PATH, yaml.safe_dump(material, sort_keys=False))
        package.writestr(STATUS_PATH, yaml.safe_dump(status, sort_keys=False))
        package.writestr(README_FOR_AI_PATH, readme)

    # Definition-sourced packages intentionally lack STEP geometry and topology.
    # Generate the completeness report immediately so AI readers can see that
    # missingness explicitly rather than inferring CAD/CAE state from absence.
    from .validation.completeness_writer import write_completeness_report_package

    write_completeness_report_package(out_path, overwrite=True)
    return out_path


def _read_definition(definition_file: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(definition_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"definition YAML is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("definition YAML must contain a mapping at the top level")
    return data


def _validate_definition(definition: dict[str, Any]) -> None:
    schema_text: str | None = None
    try:
        from importlib.resources import files

        resource = files("aieng.schemas").joinpath("model_definition.schema.json")
        if resource.is_file():
            schema_text = resource.read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, AttributeError):
        schema_text = None
    if schema_text is None:
        fallback = Path(__file__).resolve().parent / "schemas" / "model_definition.schema.json"
        if not fallback.exists():
            raise ValueError("model_definition.schema.json missing")
        schema_text = fallback.read_text(encoding="utf-8")
    if Draft202012Validator is None:
        return

    schema = json.loads(schema_text)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(definition), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "$"
        raise ValueError(f"definition schema error at {path}: {first.message}")

    feature_ids = [
        feature.get("feature_id")
        for feature in definition.get("features", [])
        if isinstance(feature, dict)
    ]
    duplicate_ids = sorted({feature_id for feature_id in feature_ids if feature_ids.count(feature_id) > 1})
    if duplicate_ids:
        raise ValueError(f"feature_id values are not unique: {', '.join(duplicate_ids)}")


def _build_definition_manifest(model_id: str) -> dict[str, Any]:
    manifest = build_manifest(model_id).to_dict()
    manifest["source_mode"] = "definition"
    manifest["resources"]["graph"] = {
        "feature_graph": FEATURE_GRAPH_PATH,
        "constraints": CONSTRAINTS_PATH,
    }
    manifest["resources"]["engineering_context"] = {"material": MATERIAL_PATH}
    manifest["resources"]["validation"] = {
        "status": STATUS_PATH,
        "completeness_report": COMPLETENESS_REPORT_PATH,
    }
    manifest["resources"]["ai"]["readme"] = README_FOR_AI_PATH
    return manifest


def _build_feature_graph(definition: dict[str, Any]) -> dict[str, Any]:
    features = []
    for feature in definition["features"]:
        normalized = {
            "id": feature["feature_id"],
            "type": feature["type"],
            "name": feature["name"],
            "geometry_refs": dict(feature.get("geometry_refs", {})),
            "parameters": dict(feature.get("parameters", {})),
            "parameter_source": "agent_defined",
            "editable": bool(feature.get("parameters")),
            "editability": "proposal_allowed" if feature.get("parameters") else "semantic_only",
            "writeback_strategy": "none",
            "editability_reason": (
                "Definition-sourced semantic parameters are available for proposals, "
                "but no geometry regeneration backend is attached."
            ),
            "parameter_confidence": "medium",
            "recognition": {
                "method": "structured_definition",
                "confidence": "medium",
            },
        }
        for optional_key in ("intent", "relationships", "children"):
            if optional_key in feature:
                normalized[optional_key] = feature[optional_key]
        features.append(normalized)

    return {
        "format_version": FORMAT_VERSION,
        "features": features,
        "metadata": {
            "source_mode": "definition",
            "definition_sourced": True,
            "geometry_generation": "not_implemented",
            "provenance": dict(definition.get("provenance", {})),
            "design_requirements": dict(definition.get("design_requirements", {})),
            "manufacturing": dict(definition.get("manufacturing", {})),
            "simulation": dict(definition.get("simulation", {})),
            "assumptions": list(definition.get("assumptions", [])),
            "known_limitations": list(definition.get("known_limitations", [])),
            "limitations": list(definition.get("known_limitations", [])) + [
                "No STEP geometry is present.",
                "No topology map is present.",
                "Feature geometry references are semantic-only.",
            ],
        },
    }


def _build_material(definition: dict[str, Any]) -> dict[str, Any]:
    provenance = dict(definition.get("provenance", {}))
    if "source" in definition["material"]:
        provenance.setdefault("material_data_source", definition["material"]["source"])
    return {
        "format_version": FORMAT_VERSION,
        "source_mode": "definition",
        "name": definition["material"]["name"],
        "properties": dict(definition["material"].get("properties", {})),
        "coordinate_system": dict(definition["coordinate_system"]),
        "provenance": provenance,
        "design_requirements": dict(definition.get("design_requirements", {})),
        "manufacturing": dict(definition.get("manufacturing", {})),
        "simulation": dict(definition.get("simulation", {})),
        "assumptions": list(definition.get("assumptions", [])),
        "known_limitations": list(definition.get("known_limitations", [])),
        "notes": [
            "Material is part of the structured definition.",
            "No body assignment to generated geometry has been validated.",
        ],
    }


def _build_status(definition: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    has_constraints = bool(definition.get("constraints"))
    has_simulation = isinstance(definition.get("simulation"), dict) and bool(definition["simulation"])
    has_manufacturing = isinstance(definition.get("manufacturing"), dict) and bool(definition["manufacturing"])
    return {
        "generated_by": f"aieng {__version__}",
        "model_id": definition["model_id"],
        "package_format_version": FORMAT_VERSION,
        "generated_at": now,
        "package_validation": {
            "package_resources_present": True,
            "manifest_present": True,
            "structured_resources_validated": "schema_checked",
        },
        "geometry_status": {
            "step_imported": False,
            "definition_sourced": True,
            "source_geometry_present": False,
            "normalized_geometry_present": False,
            "real_geometry_parsing": "not_run",
            "real_geometry_validity": "not_run",
            "geometry_generation": "not_implemented",
            "reason": "Definition-sourced package contains semantic model data but no STEP geometry.",
        },
        "topology_status": {
            "topology_map_present": False,
            "aag_present": False,
            "extraction_mode": "none",
            "status": "not_generated",
            "warning": "No topology exists until a geometry generation or import step runs.",
        },
        "feature_status": {
            "feature_graph_present": True,
            "recognition_mode": "structured_definition",
            "status": "semantic_definition",
            "warning": "Features are structured design intent, not validated geometry.",
        },
        "engineering_context_status": {
            "context_source": "structured_definition",
            "status": "structured_context_present",
            "material_present": True,
            "constraints_present": has_constraints,
            "assumptions_present": bool(definition.get("assumptions")),
            "known_limitations_present": bool(definition.get("known_limitations")),
            "design_requirements_present": bool(definition.get("design_requirements")),
            "manufacturing_intent_present": has_manufacturing,
            "simulation_intent_present": has_simulation or any(
                constraint.get("type") == "simulation_target"
                for constraint in definition.get("constraints", [])
                if isinstance(constraint, dict)
            ),
        },
        "solver_mesh_status": {
            "mesh_generation": "not_run",
            "solver_execution": "not_run",
            "stress_validation": "not_validated",
            "displacement_validation": "not_validated",
            "manufacturing_validation": "not_run",
        },
        "patch_status": {
            "patch_proposals_present": False,
            "patch_execution": "not_run",
            "geometry_modified_by_patch": False,
            "solver_run_for_patch": False,
            "patch_validation_required": False,
        },
        "claim_policy": {
            "allowed_claims": list(ALLOWED_CLAIMS),
            "forbidden_claims": list(FORBIDDEN_CLAIMS),
        },
    }


def _build_readme(definition: dict[str, Any]) -> str:
    sections = [
        f"# {definition['label']}\n",
        "This is a definition-sourced `.aieng` package.\n",
        "No STEP geometry is present. The package contains structured feature, "
        "constraint, material, and coordinate-system definitions only.\n",
        "The feature graph records semantic design intent. Its geometry references "
        "are semantic-only until a downstream geometry generator creates real CAD "
        "geometry and validation evidence.\n",
        "This package must not be treated as solver or geometry validation evidence. "
        "No mesh has been generated, no solver has been run, and no manufacturing "
        "or stress claim has been validated.\n",
    ]

    if definition.get("design_requirements"):
        sections.append("## Design requirements\n")
        sections.append(yaml.safe_dump(definition["design_requirements"], sort_keys=False).strip() + "\n")
    if definition.get("manufacturing"):
        sections.append("## Manufacturing intent\n")
        sections.append(yaml.safe_dump(definition["manufacturing"], sort_keys=False).strip() + "\n")
    if definition.get("simulation"):
        sections.append("## Simulation intent\n")
        sections.append(yaml.safe_dump(definition["simulation"], sort_keys=False).strip() + "\n")
    if definition.get("known_limitations"):
        sections.append("## Known limitations\n")
        sections.extend(f"- {item}\n" for item in definition["known_limitations"])

    sections.append(f"\nModel ID: `{definition['model_id']}`\n")
    return "\n".join(sections)


def _build_legacy_readme(definition: dict[str, Any]) -> str:
    return (
        f"# {definition['label']}\n\n"
        "This is a definition-sourced `.aieng` package.\n\n"
        "No STEP geometry is present. The package contains structured feature, "
        "constraint, material, and coordinate-system definitions only.\n\n"
        "The feature graph records semantic design intent. Its geometry references "
        "are semantic-only until a downstream geometry generator creates real CAD "
        "geometry and validation evidence.\n\n"
        "This package must not be treated as solver or geometry validation evidence. "
        "No mesh has been generated, no solver has been run, and no manufacturing "
        "or stress claim has been validated.\n\n"
        f"Model ID: `{definition['model_id']}`\n"
    )
