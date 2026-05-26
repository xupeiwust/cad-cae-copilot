from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

FEATURE_GRAPH_PATH = "graph/feature_graph.json"
CONSTRAINTS_PATH = "graph/constraints.json"
SIMULATION_SETUP_PATH = "simulation/setup.yaml"
PROTECTED_REGIONS_PATH = "ai/protected_regions.json"
ALLOWED_OPERATIONS_CATALOG_PATH = "graph/allowed_operations_catalog.json"
AI_SUMMARY_PATH = "ai/summary.md"
PATCH_DIR = "ai/patches/"
PATCH_PROPOSER = "aieng-rule-based-patch-proposer"
REQUIRED_VALIDATION_STEPS = [
    "geometry_validity",
    "protected_region_integrity",
    "mesh_generation",
    "static_structural_analysis",
    "max_stress_constraint",
    "manufacturing_rule_check",
]
GEOMETRY_CHANGING_OPS = {"add_feature", "modify_parameter", "remove_feature"}
MASS_REDUCTION_PATTERNS = (
    "mass reduction",
    "reduce mass",
    "reduced mass",
    "reduce weight",
    "weight reduction",
    "lightweight",
    "lightweighting",
)
LOAD_ASSIGNMENT_PATTERNS = (
    "assign load",
    "apply load",
    "set load",
    "add load",
)
BOUNDARY_ASSIGNMENT_PATTERNS = (
    "assign boundary",
    "assign boundary condition",
    "fixed support",
    "set fixed",
)


def propose_patch_package(package_path: str | Path, intent: str) -> Path:
    """Generate one deterministic structured patch proposal for an existing .aieng package."""
    package_file = Path(package_path)
    normalized_intent = intent.strip()
    if not normalized_intent:
        raise ValueError("intent must be a non-empty string")
    if not package_file.exists():
        raise FileNotFoundError(f"package does not exist: {package_file}")
    if package_file.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(package_file, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if FEATURE_GRAPH_PATH not in names:
                raise FileNotFoundError(f"{FEATURE_GRAPH_PATH} missing")

            manifest = _read_json(package, "manifest.json")
            feature_graph = _read_json(package, FEATURE_GRAPH_PATH)
            constraints = _read_optional_json(package, CONSTRAINTS_PATH)
            protected_regions = _read_optional_json(package, PROTECTED_REGIONS_PATH)
            allowed_operations_catalog = _read_optional_json(package, ALLOWED_OPERATIONS_CATALOG_PATH)
            simulation_setup = _read_optional_yaml(package, SIMULATION_SETUP_PATH)
            existing_members = _read_existing_members(package)
            existing_patch_paths = _existing_patch_paths(names)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {package_file}") from exc

    patch_id = _next_patch_id(existing_patch_paths)
    patch_path = f"{PATCH_DIR}{patch_id}.json"
    source_files = _source_files_consulted(
        constraints=constraints,
        protected_regions=protected_regions,
        allowed_operations_catalog=allowed_operations_catalog,
        simulation_setup=simulation_setup,
        names=names,
    )
    patch = _build_patch(
        patch_id=patch_id,
        intent=normalized_intent,
        feature_graph=feature_graph,
        constraints=constraints,
        protected_regions=protected_regions,
        allowed_operations_catalog=allowed_operations_catalog,
        source_files=source_files,
    )
    _rewrite_package_with_patch(package_file, existing_members, manifest, patch_path, patch)
    return package_file


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
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename == "manifest.json" or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _existing_patch_paths(names: set[str]) -> list[str]:
    return sorted(name for name in names if name.startswith(PATCH_DIR) and name.endswith(".json"))


def _next_patch_id(existing_patch_paths: list[str]) -> str:
    max_index = 0
    for path in existing_patch_paths:
        match = re.fullmatch(r"ai/patches/patch_(\d{4})\.json", path)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"patch_{max_index + 1:04d}"


def _source_files_consulted(
    *,
    constraints: Any | None,
    protected_regions: Any | None,
    allowed_operations_catalog: Any | None,
    simulation_setup: Any | None,
    names: set[str],
) -> list[str]:
    source_files = [FEATURE_GRAPH_PATH]
    if constraints is not None:
        source_files.append(CONSTRAINTS_PATH)
    if protected_regions is not None:
        source_files.append(PROTECTED_REGIONS_PATH)
    if allowed_operations_catalog is not None:
        source_files.append(ALLOWED_OPERATIONS_CATALOG_PATH)
    if simulation_setup is not None:
        source_files.append(SIMULATION_SETUP_PATH)
    if AI_SUMMARY_PATH in names:
        source_files.append(AI_SUMMARY_PATH)
    return source_files


def _build_patch(
    *,
    patch_id: str,
    intent: str,
    feature_graph: dict[str, Any],
    constraints: Any | None,
    protected_regions: Any | None,
    allowed_operations_catalog: Any | None,
    source_files: list[str],
) -> dict[str, Any]:
    features = _features(feature_graph)
    feature_ids = {feature["id"] for feature in features}
    protected_ids = sorted(_protected_feature_ids(protected_regions, constraints) & feature_ids)
    recognized_mass_reduction = _is_mass_reduction_intent(intent)
    recognized_load_assignment = _is_load_assignment_intent(intent)
    recognized_boundary_assignment = _is_boundary_assignment_intent(intent)
    percent = _extract_percent(intent)

    warnings = [
        "This patch proposal has not been executed.",
        "No geometry has been modified.",
        "No solver result has been attached.",
        "Candidate features may not represent confirmed engineering intent.",
    ]
    operations: list[dict[str, Any]] = []
    target_feature_ids: list[str] = []
    expected_effects: dict[str, Any] = {"stress_risk": "unknown_requires_validation"}

    if recognized_mass_reduction:
        target = _mass_reduction_target(features, protected_ids)
        if percent is not None:
            expected_effects["mass_change_target_percent"] = -percent
        if target is None:
            status = "needs_review"
            summary = "Mass reduction intent was recognized, but no non-protected candidate feature was available for a geometry-changing proposal."
            warnings.append("No non-protected base_plate, rib, flange, or unknown_feature candidate was available for modification.")
        else:
            op_policy = _allowed_operation_policy(allowed_operations_catalog, target["id"], "add_feature")
            if op_policy.get("status") == "forbidden":
                status = "needs_review"
                summary = (
                    "Mass reduction intent was recognized, but operation policy blocks geometry-changing "
                    f"proposal on {target['id']}."
                )
                warnings.append(
                    f"Operation add_feature on {target['id']} is forbidden by allowed_operations_catalog."
                )
            else:
                status = "proposed"
                target_feature_ids.append(target["id"])
                parameters: dict[str, Any] = {
                    "mass_reduction_target_percent": percent,
                    "avoid_protected_features": protected_ids,
                }
                policy_preconditions = op_policy.get("preconditions", [])
                if isinstance(policy_preconditions, list) and policy_preconditions:
                    parameters["policy_preconditions"] = [item for item in policy_preconditions if isinstance(item, str)]
                operations.append(
                    {
                        "op": "add_feature",
                        "feature_type": "lightening_pocket_candidate",
                        "target": target["id"],
                        "parameters": parameters,
                        "rationale": (
                            f"{target['id']} is a non-protected {target.get('type', 'feature')} candidate; "
                            "geometry and stress validation are required."
                        ),
                    }
                )
                if op_policy.get("status") == "conditional":
                    warnings.append(
                        f"Operation add_feature on {target['id']} is conditional and requires policy preconditions."
                    )
                summary = "Proposes lightweighting changes while avoiding protected mounting interfaces."
    elif recognized_load_assignment:
        target = _role_target(allowed_operations_catalog, role="load_application_interface", fallback_features=features)
        if target is None:
            status = "needs_review"
            summary = "Load-assignment intent was recognized, but no suitable target feature was found."
            warnings.append("No load_application_interface feature was found; provide explicit target mapping.")
        else:
            op_policy = _allowed_operation_policy(allowed_operations_catalog, target["id"], "assign_load")
            if op_policy.get("status") == "forbidden":
                status = "needs_review"
                summary = f"Load-assignment intent was recognized, but policy blocks assign_load on {target['id']}."
                warnings.append(f"Operation assign_load on {target['id']} is forbidden by allowed_operations_catalog.")
            else:
                status = "proposed"
                target_feature_ids.append(target["id"])
                parameters: dict[str, Any] = {
                    "load_type": "force",
                    "target_mapping_required": True,
                }
                policy_preconditions = op_policy.get("preconditions", [])
                if isinstance(policy_preconditions, list) and policy_preconditions:
                    parameters["policy_preconditions"] = [item for item in policy_preconditions if isinstance(item, str)]
                operations.append(
                    {
                        "op": "assign_load",
                        "target": target["id"],
                        "parameters": parameters,
                        "rationale": "Intent requests load assignment; selected target from interface-role-aware policy context.",
                    }
                )
                if op_policy.get("status") == "conditional":
                    warnings.append(f"Operation assign_load on {target['id']} is conditional and requires policy preconditions.")
                summary = "Proposes structured load assignment for a role-consistent interface feature."
    elif recognized_boundary_assignment:
        target = _role_target(allowed_operations_catalog, role="fixed_support_interface", fallback_features=features)
        if target is None:
            status = "needs_review"
            summary = "Boundary-condition intent was recognized, but no suitable target feature was found."
            warnings.append("No fixed_support_interface feature was found; provide explicit target mapping.")
        else:
            op_policy = _allowed_operation_policy(allowed_operations_catalog, target["id"], "assign_boundary_condition")
            if op_policy.get("status") == "forbidden":
                status = "needs_review"
                summary = f"Boundary-condition intent was recognized, but policy blocks assign_boundary_condition on {target['id']}."
                warnings.append(
                    f"Operation assign_boundary_condition on {target['id']} is forbidden by allowed_operations_catalog."
                )
            else:
                status = "proposed"
                target_feature_ids.append(target["id"])
                parameters = {
                    "boundary_condition_type": "fixed",
                    "target_mapping_required": True,
                }
                policy_preconditions = op_policy.get("preconditions", [])
                if isinstance(policy_preconditions, list) and policy_preconditions:
                    parameters["policy_preconditions"] = [item for item in policy_preconditions if isinstance(item, str)]
                operations.append(
                    {
                        "op": "assign_boundary_condition",
                        "target": target["id"],
                        "parameters": parameters,
                        "rationale": "Intent requests boundary-condition assignment; selected target from interface-role-aware policy context.",
                    }
                )
                if op_policy.get("status") == "conditional":
                    warnings.append(
                        f"Operation assign_boundary_condition on {target['id']} is conditional and requires policy preconditions."
                    )
                summary = "Proposes structured fixed-support assignment for a role-consistent interface feature."
    else:
        status = "needs_review"
        summary = "The rule-based patch proposer did not recognize this intent, so no geometry-changing operations are proposed."
        warnings.append("Intent was not recognized by the rule-based proposer.")

    return {
        "patch_id": patch_id,
        "created_by": PATCH_PROPOSER,
        "user_intent": intent,
        "status": status,
        "summary": summary,
        "operations": operations,
        "target_feature_ids": target_feature_ids,
        "protected_target_checks": [
            {"feature_id": feature_id, "status": "avoided", "reason": "Protected by context or constraints."}
            for feature_id in protected_ids
        ],
        "protected_targets_checked": protected_ids,
        "protected_targets_avoided": protected_ids,
        "warnings": warnings,
        "expected_effects": expected_effects,
        "required_validation_steps": list(REQUIRED_VALIDATION_STEPS),
        "requires_validation": list(REQUIRED_VALIDATION_STEPS),
        "source_files_consulted": source_files,
        "created_from": {
            "method": "rule_based",
            "llm_used": False,
            "rag_used": False,
            "external_cad_tools_used": False,
        },
        "no_geometry_modified": True,
        "no_solver_run": True,
    }


def _features(feature_graph: dict[str, Any]) -> list[dict[str, Any]]:
    raw_features = feature_graph.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("feature_graph features must be a list")
    features = [feature for feature in raw_features if isinstance(feature, dict) and isinstance(feature.get("id"), str)]
    if not features:
        raise ValueError("feature_graph contains no feature IDs")
    return features


def _protected_feature_ids(protected_regions: Any | None, constraints: Any | None) -> set[str]:
    protected: set[str] = set()
    if isinstance(protected_regions, dict) and isinstance(protected_regions.get("protected_regions"), list):
        for region in protected_regions["protected_regions"]:
            if isinstance(region, dict) and isinstance(region.get("feature_id"), str):
                protected.add(region["feature_id"])
    if isinstance(constraints, dict) and isinstance(constraints.get("constraints"), list):
        for constraint in constraints["constraints"]:
            if not isinstance(constraint, dict):
                continue
            if constraint.get("type") in {"protect_geometry", "protect_position", "protect_dimension", "preserve_interface"}:
                target = constraint.get("target")
                if isinstance(target, str):
                    protected.add(target)
    return protected


def _is_mass_reduction_intent(intent: str) -> bool:
    normalized = intent.lower()
    return any(pattern in normalized for pattern in MASS_REDUCTION_PATTERNS)


def _is_load_assignment_intent(intent: str) -> bool:
    normalized = intent.lower()
    return any(pattern in normalized for pattern in LOAD_ASSIGNMENT_PATTERNS)


def _is_boundary_assignment_intent(intent: str) -> bool:
    normalized = intent.lower()
    return any(pattern in normalized for pattern in BOUNDARY_ASSIGNMENT_PATTERNS)


def _extract_percent(intent: str) -> float | int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", intent)
    if not match:
        return None
    value = float(match.group(1))
    return int(value) if value.is_integer() else value


def _mass_reduction_target(features: list[dict[str, Any]], protected_ids: list[str]) -> dict[str, Any] | None:
    protected = set(protected_ids)
    priority = {"base_plate": 0, "rib": 1, "flange": 2, "unknown_feature": 3}
    candidates = [
        feature for feature in features
        if feature["id"] not in protected and feature.get("type") in priority
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda feature: (priority[str(feature.get("type"))], str(feature["id"])))[0]


def _allowed_operation_policy(catalog: Any | None, feature_id: str, operation_type: str) -> dict[str, Any]:
    if not isinstance(catalog, dict):
        return {}
    entries = catalog.get("feature_operations")
    if not isinstance(entries, list):
        return {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("feature_id") != feature_id:
            continue
        operations = entry.get("operations")
        if not isinstance(operations, list):
            return {}
        for op in operations:
            if isinstance(op, dict) and op.get("operation_type") == operation_type:
                return op
        return {}
    return {}


def _role_target(catalog: Any | None, *, role: str, fallback_features: list[dict[str, Any]]) -> dict[str, Any] | None:
    if isinstance(catalog, dict):
        entries = catalog.get("feature_operations")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                feature_id = entry.get("feature_id")
                roles = entry.get("interface_roles")
                if isinstance(feature_id, str) and isinstance(roles, list) and role in roles:
                    for feature in fallback_features:
                        if feature.get("id") == feature_id:
                            return feature
    if fallback_features:
        return sorted(fallback_features, key=lambda item: str(item.get("id", "")))[0]
    return None


def _rewrite_package_with_patch(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    patch_path: str,
    patch: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("manifest resources must be an object")
    ai_resources = resources.setdefault("ai", {})
    if not isinstance(ai_resources, dict):
        raise ValueError("manifest resources.ai must be an object")
    existing_patches = ai_resources.setdefault("patches", [])
    if not isinstance(existing_patches, list):
        raise ValueError("manifest resources.ai.patches must be an array")
    if patch_path not in existing_patches:
        existing_patches.append(patch_path)
    # Backward-compatible root-level index for readers that look directly under resources.
    resources["patches"] = list(existing_patches)

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    patch_json = json.dumps(patch, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(patch_path, patch_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
