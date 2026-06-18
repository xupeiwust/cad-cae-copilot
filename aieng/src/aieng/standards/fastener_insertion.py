"""Explicit package-level fastener insertion helpers.

This module is intentionally opt-in. It appends semantic standard-part features
and an insertion report to a package only when the caller explicitly selects
hole feature IDs. It does not edit CAD source, rebuild geometry, or run solvers.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng.graph.feature_graph import FEATURE_GRAPH_PATH
from aieng.standards.fastener_planner import plan_fastener_for_hole

FASTENER_INSERTION_REPORT_PATH = "graph/fastener_insertion_report.json"

NUMERIC_TYPES = (int, float)


def insert_fasteners_for_holes(
    package_path: str | Path,
    selected_hole_feature_ids: list[str],
    *,
    planner_outputs: dict[str, dict[str, Any]] | None = None,
    material: str = "Steel-1045",
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    """Explicitly append standard-part fasteners for selected hole features."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")
    if not selected_hole_feature_ids:
        raise ValueError("selected_hole_feature_ids must not be empty")

    with zipfile.ZipFile(path, mode="r") as package:
        names = set(package.namelist())
        if "manifest.json" not in names:
            raise ValueError("package is missing manifest.json")
        if FEATURE_GRAPH_PATH not in names:
            raise FileNotFoundError(f"{FEATURE_GRAPH_PATH} missing")
        manifest = json.loads(package.read("manifest.json"))
        feature_graph = json.loads(package.read(FEATURE_GRAPH_PATH))
        existing_members = _read_existing_members(package)

    features = feature_graph.get("features")
    if not isinstance(features, list):
        raise ValueError("feature_graph features must be a list")

    existing_feature_ids = {str(feature.get("id")) for feature in features if isinstance(feature, dict)}
    selected = list(dict.fromkeys(str(item) for item in selected_hole_feature_ids))
    planner_outputs = planner_outputs or {}

    inserted_features: list[dict[str, Any]] = []
    inserted_records: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []

    by_id = {str(feature.get("id")): feature for feature in features if isinstance(feature, dict) and feature.get("id")}
    for feature_id in selected:
        feature = by_id.get(feature_id)
        if feature is None:
            blockers.append(_blocker(feature_id, "feature_not_found", "Selected hole feature ID was not found."))
            continue
        if not overwrite_existing and _has_existing_insertion(features, feature_id):
            blockers.append(_blocker(feature_id, "already_inserted", "Fastener features already reference this hole."))
            continue

        hole_metadata = feature.get("hole_metadata")
        if not isinstance(hole_metadata, dict):
            blockers.append(_blocker(feature_id, "missing_hole_metadata", "Feature has no hole_metadata."))
            continue
        plan = planner_outputs.get(feature_id) or plan_fastener_for_hole(hole_metadata)
        if plan.get("status") != "matched":
            blockers.append(
                _blocker(
                    feature_id,
                    str(plan.get("status") or "planner_no_match"),
                    "Fastener planner did not return a matched candidate.",
                    plan=plan,
                )
            )
            continue

        placement = _placement_from_metadata(hole_metadata)
        if placement is None:
            blockers.append(
                _blocker(
                    feature_id,
                    "insufficient_placement",
                    "Hole metadata lacks a usable axis origin/direction.",
                    plan=plan,
                )
            )
            continue

        spec = plan.get("fastener_spec")
        if not isinstance(spec, dict):
            blockers.append(_blocker(feature_id, "missing_fastener_spec", "Planner result has no fastener_spec.", plan=plan))
            continue

        if plan.get("mode") == "threaded" or spec.get("mode") == "threaded":
            inserted = _threaded_standard_part(
                feature=feature,
                feature_id=feature_id,
                placement=placement,
                spec=spec,
                material=material,
                existing_feature_ids=existing_feature_ids,
            )
            if isinstance(inserted, dict) and inserted.get("blocker"):
                blockers.append(inserted["blocker"])
                continue
            screw_feature = inserted["feature"]
            inserted_features.append(screw_feature)
            existing_feature_ids.add(screw_feature["id"])
            inserted_records.append(
                {
                    "hole_feature_id": feature_id,
                    "inserted_feature_id": screw_feature["id"],
                    "kind": "threaded_screw",
                    "designation": screw_feature["designation"],
                    "length_mm": screw_feature["parameters"]["length_mm"],
                }
            )
            continue

        stack = hole_metadata.get("mating_stack")
        if not isinstance(stack, dict) or stack.get("status") != "known":
            blockers.append(
                _blocker(
                    feature_id,
                    "unknown_stack_thickness",
                    "Mating stack thickness is not known, so length and nut engagement cannot be verified.",
                    plan=plan,
                )
            )
            continue
        stack_thickness = _num(stack.get("thickness_mm"))
        if stack_thickness is None or stack_thickness <= 0:
            blockers.append(
                _blocker(
                    feature_id,
                    "invalid_stack_thickness",
                    "Known mating stack thickness is missing or non-positive.",
                    plan=plan,
                )
            )
            continue

        length_mm = _length_covering_stack(spec, stack_thickness)
        if length_mm is None:
            blockers.append(
                _blocker(
                    feature_id,
                    "insufficient_length_evidence",
                    "No usable fastener length could be derived from the planner/catalog evidence.",
                    plan=plan,
                )
            )
            continue

        screw_feature = _standard_part_feature(
            feature_id=feature_id,
            suffix="screw",
            name=f"{spec.get('designation', 'metric')} screw for {feature_id}",
            canonical_type="screw",
            designation=str(spec.get("designation") or spec.get("metric_size") or "unknown"),
            material=material,
            geometry_refs=feature.get("geometry_refs"),
            placement=placement,
            parameters={
                "length_mm": length_mm,
                "nominal_thread_diameter_mm": spec.get("nominal_thread_diameter_mm"),
                "clearance_hole_diameter_mm": spec.get("clearance_hole_diameter_mm"),
            },
            spec=spec,
            selected_hole_feature_id=feature_id,
            existing_feature_ids=existing_feature_ids,
        )
        inserted_features.append(screw_feature)
        existing_feature_ids.add(screw_feature["id"])
        inserted_records.append(
            {
                "hole_feature_id": feature_id,
                "inserted_feature_id": screw_feature["id"],
                "kind": "screw",
                "designation": screw_feature["designation"],
                "length_mm": length_mm,
            }
        )

        if hole_metadata.get("through") is True:
            nut_feature = _standard_part_feature(
                feature_id=feature_id,
                suffix="nut",
                name=f"{spec.get('designation', 'metric')} nut for {feature_id}",
                canonical_type="nut",
                designation=str(spec.get("designation") or spec.get("metric_size") or "unknown"),
                material=material,
                geometry_refs=feature.get("geometry_refs"),
                placement=_offset_placement(placement, stack_thickness),
                parameters={
                    "nominal_thread_diameter_mm": spec.get("nominal_thread_diameter_mm"),
                },
                spec=spec,
                selected_hole_feature_id=feature_id,
                existing_feature_ids=existing_feature_ids,
            )
            inserted_features.append(nut_feature)
            existing_feature_ids.add(nut_feature["id"])
            inserted_records.append(
                {
                    "hole_feature_id": feature_id,
                    "inserted_feature_id": nut_feature["id"],
                    "kind": "nut",
                    "designation": nut_feature["designation"],
                }
            )
        else:
            warnings.append(f"{feature_id}: hole is not marked through=true; nut was not inserted.")

    features.extend(inserted_features)
    report = {
        "status": "ok" if inserted_features else "blocked",
        "tool": "aieng.standards.fastener_insertion.insert_fasteners_for_holes",
        "explicit_opt_in": True,
        "mutates_geometry": False,
        "writes_feature_graph": bool(inserted_features),
        "selected_hole_feature_ids": selected,
        "inserted_count": len(inserted_features),
        "inserted": inserted_records,
        "blockers": blockers,
        "warnings": warnings,
        "honesty_boundary": (
            "Inserted standard_part records are semantic package features for downstream BOM/assembly logic; "
            "this helper does not rebuild CAD geometry or claim B-Rep fastener solids exist."
        ),
    }

    _rewrite_package(path, existing_members, manifest, feature_graph, report)
    return report


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    skip = {"manifest.json", FEATURE_GRAPH_PATH, FASTENER_INSERTION_REPORT_PATH}
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    feature_graph: dict[str, Any],
    report: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    graph_resources = resources.setdefault("graph", {})
    if not isinstance(graph_resources, dict):
        raise ValueError("manifest resources.graph must be an object")
    graph_resources["feature_graph"] = FEATURE_GRAPH_PATH
    graph_resources["fastener_insertion_report"] = FASTENER_INSERTION_REPORT_PATH

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)
    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", _json_bytes(manifest))
            out_package.writestr(FEATURE_GRAPH_PATH, _json_bytes(feature_graph))
            out_package.writestr(FASTENER_INSERTION_REPORT_PATH, _json_bytes(report))
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _standard_part_feature(
    *,
    feature_id: str,
    suffix: str,
    name: str,
    canonical_type: str,
    designation: str,
    material: str,
    geometry_refs: Any,
    placement: dict[str, Any],
    parameters: dict[str, Any],
    spec: dict[str, Any],
    selected_hole_feature_id: str,
    existing_feature_ids: set[str],
) -> dict[str, Any]:
    clean_params = {key: value for key, value in parameters.items() if value is not None}
    inserted_id = _unique_id(f"feat_fastener_{feature_id}_{suffix}", existing_feature_ids)
    return {
        "id": inserted_id,
        "type": "standard_part",
        "name": name,
        "geometry_refs": _geometry_refs_for_inserted_part(geometry_refs),
        "parameters": {
            **clean_params,
            "material": material,
            "placement": placement,
        },
        "parameter_source": "agent_defined",
        "parameter_confidence": "medium",
        "editable": False,
        "editability": "not_editable",
        "writeback_strategy": "none",
        "editability_reason": "Explicit fastener insertion records semantic standard-part placement only.",
        "intent": {
            "role": "inserted_fastener",
            "selected_hole_feature_id": selected_hole_feature_id,
        },
        "relationships": [
            {
                "type": "inserted_for_hole",
                "source_feature_id": inserted_id,
                "target_feature_id": selected_hole_feature_id,
            }
        ],
        "recognition": {
            "method": "explicit_fastener_insertion",
            "confidence": "medium",
            "uncertainty_notes": [
                "Semantic standard-part feature only; CAD geometry was not rebuilt.",
                "Placement depends on hole_metadata axis and stack-thickness evidence.",
            ],
        },
        "standard_part": True,
        "source_library": "aieng.standards",
        "canonical_type": canonical_type,
        "designation": designation,
        "object_label": inserted_id,
        "detection_method": "explicit_opt_in_fastener_insertion",
        "confidence": "medium",
        "standard_part_metadata": {
            "fastener_spec": spec,
            "selected_hole_feature_id": selected_hole_feature_id,
            "semantic_only": True,
        },
    }


def _threaded_standard_part(
    *,
    feature: dict[str, Any],
    feature_id: str,
    placement: dict[str, Any],
    spec: dict[str, Any],
    material: str,
    existing_feature_ids: set[str],
) -> dict[str, Any]:
    hole_metadata = feature.get("hole_metadata") if isinstance(feature.get("hole_metadata"), dict) else {}
    depth_mm = _num(hole_metadata.get("depth_mm"))
    if depth_mm is None or depth_mm <= 0:
        return {
            "blocker": _blocker(
                feature_id,
                "missing_thread_depth",
                "Threaded insertion requires known positive hole depth to avoid overlong insertion.",
                plan={"fastener_spec": spec, "mode": "threaded"},
            )
        }
    length_mm = _threaded_length(spec, depth_mm)
    if length_mm is None or length_mm <= 0 or length_mm > depth_mm:
        return {
            "blocker": _blocker(
                feature_id,
                "unsupported_thread_length",
                "No threaded fastener length could be chosen within the known hole depth.",
                plan={"fastener_spec": spec, "mode": "threaded", "depth_mm": depth_mm},
            )
        }
    feature_out = _standard_part_feature(
        feature_id=feature_id,
        suffix="threaded_screw",
        name=f"{spec.get('designation', 'metric')} threaded screw for {feature_id}",
        canonical_type="screw",
        designation=str(spec.get("designation") or spec.get("metric_size") or "unknown"),
        material=material,
        geometry_refs=feature.get("geometry_refs"),
        placement=placement,
        parameters={
            "length_mm": length_mm,
            "thread_engagement_depth_mm": depth_mm,
            "nominal_thread_diameter_mm": spec.get("nominal_thread_diameter_mm"),
            "thread_pitch_mm": spec.get("thread_pitch_mm"),
        },
        spec=spec,
        selected_hole_feature_id=feature_id,
        existing_feature_ids=existing_feature_ids,
    )
    feature_out["intent"]["role"] = "inserted_threaded_fastener"
    feature_out["standard_part_metadata"]["threaded_hole"] = True
    return {"feature": feature_out}


def _placement_from_metadata(hole_metadata: dict[str, Any]) -> dict[str, Any] | None:
    axis = hole_metadata.get("axis")
    if not isinstance(axis, dict):
        return None
    origin = _vec3(axis.get("origin_mm"))
    direction = _vec3(axis.get("direction"))
    if origin is None or direction is None:
        return None
    return {
        "axis_origin_mm": origin,
        "axis_direction": direction,
        "axis_origin_source": axis.get("origin_source"),
        "axis_direction_source": axis.get("direction_source"),
    }


def _offset_placement(placement: dict[str, Any], distance_mm: float) -> dict[str, Any]:
    origin = _vec3(placement.get("axis_origin_mm")) or [0.0, 0.0, 0.0]
    direction = _vec3(placement.get("axis_direction")) or [0.0, 0.0, 1.0]
    return {
        **placement,
        "axis_origin_mm": [origin[i] + direction[i] * distance_mm for i in range(3)],
        "offset_from_hole_origin_mm": distance_mm,
    }


def _length_covering_stack(spec: dict[str, Any], stack_thickness_mm: float) -> float | None:
    diameter = _num(spec.get("nominal_thread_diameter_mm")) or 0.0
    required = stack_thickness_mm + max(diameter, 0.0)
    suggested = _num(spec.get("suggested_length_mm"))
    catalog_lengths = spec.get("standard_lengths") or spec.get("catalog_standard_lengths")
    if isinstance(catalog_lengths, list):
        numeric = sorted(float(item) for item in catalog_lengths if isinstance(item, NUMERIC_TYPES))
        for length in numeric:
            if length >= required:
                return length
        if numeric:
            return numeric[-1] if numeric[-1] >= stack_thickness_mm else None
    if suggested is not None and suggested >= required:
        return suggested
    return required


def _threaded_length(spec: dict[str, Any], depth_mm: float) -> float | None:
    suggested = _num(spec.get("suggested_length_mm"))
    if suggested is not None and suggested <= depth_mm:
        return suggested
    lengths = spec.get("standard_lengths")
    if isinstance(lengths, list):
        numeric = sorted(float(item) for item in lengths if isinstance(item, NUMERIC_TYPES))
        shorter_or_equal = [length for length in numeric if length <= depth_mm]
        if shorter_or_equal:
            return shorter_or_equal[-1]
    return depth_mm


def _geometry_refs_for_inserted_part(geometry_refs: Any) -> dict[str, list[str]]:
    if isinstance(geometry_refs, dict):
        return {
            key: list(value)
            for key, value in geometry_refs.items()
            if key in {"faces", "edges", "entities"} and isinstance(value, list)
        }
    if isinstance(geometry_refs, list):
        return {"entities": [str(item) for item in geometry_refs]}
    return {"entities": []}


def _has_existing_insertion(features: list[Any], hole_feature_id: str) -> bool:
    for feature in features:
        if not isinstance(feature, dict):
            continue
        for relationship in feature.get("relationships", []) or []:
            if not isinstance(relationship, dict):
                continue
            if relationship.get("type") == "inserted_for_hole" and relationship.get("target_feature_id") == hole_feature_id:
                return True
    return False


def _blocker(feature_id: str, code: str, message: str, *, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    blocker: dict[str, Any] = {"feature_id": feature_id, "code": code, "message": message}
    if plan is not None:
        blocker["planner_result"] = plan
    return blocker


def _unique_id(base: str, existing: set[str]) -> str:
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base).strip("_") or "feat_fastener"
    candidate = clean
    index = 2
    while candidate in existing:
        candidate = f"{clean}_{index}"
        index += 1
    return candidate


def _vec3(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    if not all(isinstance(item, NUMERIC_TYPES) for item in value):
        return None
    return [float(item) for item in value]


def _num(value: Any) -> float | None:
    if isinstance(value, NUMERIC_TYPES):
        return float(value)
    return None


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
