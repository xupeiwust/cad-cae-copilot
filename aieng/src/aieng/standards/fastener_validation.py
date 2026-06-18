"""Read-only validation for explicitly inserted fastener features."""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

from aieng.graph.feature_graph import FEATURE_GRAPH_PATH

NUMERIC_TYPES = (int, float)


def validate_inserted_fasteners_package(package_path: str | Path, *, tolerance_mm: float = 0.25) -> dict[str, Any]:
    """Read ``graph/feature_graph.json`` and validate inserted fastener records."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        if FEATURE_GRAPH_PATH not in names:
            raise FileNotFoundError(f"{FEATURE_GRAPH_PATH} missing")
        feature_graph = json.loads(package.read(FEATURE_GRAPH_PATH))
    return validate_inserted_fasteners(feature_graph, tolerance_mm=tolerance_mm)


def validate_inserted_fasteners(feature_graph: dict[str, Any], *, tolerance_mm: float = 0.25) -> dict[str, Any]:
    """Validate explicit fastener insertions and expose safe bolted proxies."""
    features = feature_graph.get("features") if isinstance(feature_graph, dict) else None
    if not isinstance(features, list):
        return _report([], [], [{"code": "missing_feature_graph", "message": "feature_graph features must be a list."}])

    by_id = {str(feature.get("id")): feature for feature in features if isinstance(feature, dict) and feature.get("id")}
    inserted = [feature for feature in features if _inserted_hole_id(feature)]
    validations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    grouped: dict[str, list[dict[str, Any]]] = {}
    for feature in inserted:
        hole_id = _inserted_hole_id(feature)
        if hole_id:
            grouped.setdefault(hole_id, []).append(feature)

    for feature in inserted:
        hole_id = _inserted_hole_id(feature)
        hole = by_id.get(str(hole_id)) if hole_id else None
        validation = _validate_one(feature, hole, tolerance_mm=tolerance_mm)
        validations.append(validation)
        if validation["status"] in {"warning", "unknown", "fail"}:
            warnings.append(
                {
                    "feature_id": feature.get("id"),
                    "hole_feature_id": hole_id,
                    "status": validation["status"],
                    "reasons": validation["reasons"],
                }
            )

    connections = _bolted_proxy_connections(grouped, by_id, validations)
    return _report(validations, connections, warnings)


def _validate_one(feature: dict[str, Any], hole: dict[str, Any] | None, *, tolerance_mm: float) -> dict[str, Any]:
    reasons: list[str] = []
    checks: dict[str, Any] = {}
    if hole is None:
        return _validation(feature, "unknown", checks, ["target_hole_missing"])

    placement = ((feature.get("parameters") or {}).get("placement") or {}) if isinstance(feature.get("parameters"), dict) else {}
    hole_metadata = hole.get("hole_metadata") if isinstance(hole.get("hole_metadata"), dict) else {}
    fastener_axis = _axis(placement, "axis_origin_mm", "axis_direction")
    hole_axis = _axis(hole_metadata.get("axis") if isinstance(hole_metadata.get("axis"), dict) else {}, "origin_mm", "direction")
    if fastener_axis is None or hole_axis is None:
        checks["coaxiality"] = {"status": "unknown", "reason": "missing fastener or hole axis"}
        reasons.append("missing_axis_evidence")
    else:
        distance = _axis_distance(fastener_axis["origin"], hole_axis["origin"], hole_axis["direction"])
        angle = _axis_angle_deg(fastener_axis["direction"], hole_axis["direction"])
        coaxial = distance <= tolerance_mm and min(angle, abs(180.0 - angle)) <= 2.0
        checks["coaxiality"] = {
            "status": "pass" if coaxial else "fail",
            "offset_mm": distance,
            "angle_deg": angle,
            "tolerance_mm": tolerance_mm,
        }
        if not coaxial:
            reasons.append("fastener_not_coaxial")

    if not _geometry_refs(feature):
        checks["floating"] = {"status": "warning", "reason": "inserted fastener has no topology references"}
        reasons.append("floating_or_unresolved_fastener")
    else:
        checks["floating"] = {"status": "pass"}

    role = ((feature.get("intent") or {}).get("role") if isinstance(feature.get("intent"), dict) else "")
    if role == "inserted_threaded_fastener":
        _threaded_depth_check(feature, hole_metadata, checks, reasons)
    else:
        _clearance_stack_check(feature, hole_metadata, checks, reasons, tolerance_mm=tolerance_mm)

    status = _status_from_reasons(reasons, checks)
    return _validation(feature, status, checks, reasons)


def _threaded_depth_check(
    feature: dict[str, Any],
    hole_metadata: dict[str, Any],
    checks: dict[str, Any],
    reasons: list[str],
) -> None:
    length = _num(((feature.get("parameters") or {}).get("length_mm") if isinstance(feature.get("parameters"), dict) else None))
    depth = _num(hole_metadata.get("depth_mm"))
    if length is None or depth is None:
        checks["thread_depth"] = {"status": "unknown", "reason": "missing length or depth"}
        reasons.append("missing_thread_depth_evidence")
        return
    ok = length <= depth
    checks["thread_depth"] = {"status": "pass" if ok else "fail", "length_mm": length, "depth_mm": depth}
    if not ok:
        reasons.append("threaded_fastener_overlong")


def _clearance_stack_check(
    feature: dict[str, Any],
    hole_metadata: dict[str, Any],
    checks: dict[str, Any],
    reasons: list[str],
    *,
    tolerance_mm: float,
) -> None:
    stack = hole_metadata.get("mating_stack")
    if not isinstance(stack, dict) or stack.get("status") != "known":
        checks["seating"] = {"status": "unknown", "reason": "missing known stack thickness"}
        reasons.append("missing_stack_evidence")
        return
    stack_thickness = _num(stack.get("thickness_mm"))
    length = _num(((feature.get("parameters") or {}).get("length_mm") if isinstance(feature.get("parameters"), dict) else None))
    diameter = _num(((feature.get("parameters") or {}).get("nominal_thread_diameter_mm") if isinstance(feature.get("parameters"), dict) else None))
    if stack_thickness is None or length is None:
        if feature.get("canonical_type") == "nut":
            placement = (feature.get("parameters") or {}).get("placement") if isinstance(feature.get("parameters"), dict) else None
            offset = _num(placement.get("offset_from_hole_origin_mm")) if isinstance(placement, dict) else None
            if stack_thickness is not None and offset is not None:
                ok = abs(offset - stack_thickness) <= tolerance_mm
                checks["seating"] = {
                    "status": "pass" if ok else "fail",
                    "nut_offset_mm": offset,
                    "stack_thickness_mm": stack_thickness,
                    "tolerance_mm": tolerance_mm,
                }
                if not ok:
                    reasons.append("nut_not_seated_at_stack_exit")
                return
        checks["seating"] = {"status": "unknown", "reason": "missing length or stack thickness"}
        reasons.append("missing_stack_evidence")
        return
    required = stack_thickness + max(diameter or 0.0, 0.0)
    ok = length >= required
    checks["seating"] = {
        "status": "pass" if ok else "fail",
        "length_mm": length,
        "required_length_mm": required,
        "stack_thickness_mm": stack_thickness,
    }
    if not ok:
        reasons.append("fastener_too_short_for_stack")


def _bolted_proxy_connections(
    grouped: dict[str, list[dict[str, Any]]],
    by_id: dict[str, dict[str, Any]],
    validations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pass_by_feature = {item["feature_id"] for item in validations if item.get("status") == "pass"}
    connections: list[dict[str, Any]] = []
    for hole_id, fasteners in grouped.items():
        hole = by_id.get(hole_id)
        if not isinstance(hole, dict):
            continue
        hole_metadata = hole.get("hole_metadata") if isinstance(hole.get("hole_metadata"), dict) else {}
        stack = hole_metadata.get("mating_stack") if isinstance(hole_metadata, dict) else None
        part_ids = _stack_part_ids(stack)
        has_screw = any(
            feature.get("canonical_type") == "screw" and feature.get("id") in pass_by_feature
            for feature in fasteners
        )
        has_nut = any(
            feature.get("canonical_type") == "nut" and feature.get("id") in pass_by_feature
            for feature in fasteners
        )
        if len(part_ids) < 2 or not has_screw or not has_nut:
            continue
        connections.append(
            {
                "id": f"conn_bolted_proxy_{hole_id}",
                "type": "bolted_proxy",
                "part_a": part_ids[0],
                "part_b": part_ids[1],
                "source_hole_feature_id": hole_id,
                "fastener_feature_ids": [str(feature.get("id")) for feature in fasteners if feature.get("id")],
                "evidence": "explicit_fastener_insertion_validation",
                "limitations": [
                    "Proxy connection only; no bolt preload, contact separation, friction, or thread mechanics modeled.",
                    "Generated only when inserted screw/nut validation passes and stack part IDs are known.",
                ],
            }
        )
    return connections


def _stack_part_ids(stack: Any) -> list[str]:
    if not isinstance(stack, dict):
        return []
    raw = stack.get("part_ids") or stack.get("joined_part_ids") or stack.get("parts")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str) and item]


def _inserted_hole_id(feature: Any) -> str | None:
    if not isinstance(feature, dict) or feature.get("type") != "standard_part":
        return None
    for relationship in feature.get("relationships", []) or []:
        if not isinstance(relationship, dict):
            continue
        if relationship.get("type") == "inserted_for_hole" and relationship.get("target_feature_id"):
            return str(relationship["target_feature_id"])
    return None


def _axis(container: dict[str, Any], origin_key: str, direction_key: str) -> dict[str, list[float]] | None:
    origin = _vec3(container.get(origin_key))
    direction = _vec3(container.get(direction_key))
    if origin is None or direction is None:
        return None
    return {"origin": origin, "direction": _normalized(direction)}


def _axis_distance(point: list[float], axis_origin: list[float], axis_direction: list[float]) -> float:
    delta = [point[i] - axis_origin[i] for i in range(3)]
    cross = [
        delta[1] * axis_direction[2] - delta[2] * axis_direction[1],
        delta[2] * axis_direction[0] - delta[0] * axis_direction[2],
        delta[0] * axis_direction[1] - delta[1] * axis_direction[0],
    ]
    return math.sqrt(sum(item * item for item in cross))


def _axis_angle_deg(a: list[float], b: list[float]) -> float:
    dot = max(-1.0, min(1.0, sum(a[i] * b[i] for i in range(3))))
    return math.degrees(math.acos(dot))


def _normalized(value: list[float]) -> list[float]:
    mag = math.sqrt(sum(item * item for item in value))
    if mag <= 0:
        return [0.0, 0.0, 1.0]
    return [item / mag for item in value]


def _geometry_refs(feature: dict[str, Any]) -> list[str]:
    refs = feature.get("geometry_refs")
    if isinstance(refs, dict):
        out: list[str] = []
        for value in refs.values():
            if isinstance(value, list):
                out.extend(str(item) for item in value if item)
            elif isinstance(value, str):
                out.append(value)
        return out
    if isinstance(refs, list):
        return [str(item) for item in refs if item]
    return []


def _status_from_reasons(reasons: list[str], checks: dict[str, Any]) -> str:
    if any(check.get("status") == "fail" for check in checks.values() if isinstance(check, dict)):
        return "fail"
    if any(check.get("status") == "warning" for check in checks.values() if isinstance(check, dict)):
        return "warning"
    if reasons:
        return "unknown"
    return "pass"


def _validation(feature: dict[str, Any], status: str, checks: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        "feature_id": feature.get("id"),
        "canonical_type": feature.get("canonical_type"),
        "designation": feature.get("designation"),
        "status": status,
        "checks": checks,
        "reasons": reasons,
    }


def _report(
    validations: list[dict[str, Any]],
    bolted_proxy_connections: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "ok" if not warnings else "review",
        "mutates_geometry": False,
        "runs_solver": False,
        "validation_count": len(validations),
        "validations": validations,
        "bolted_proxy_connections": bolted_proxy_connections,
        "warnings": warnings,
        "honesty_boundary": (
            "Fastener validation is deterministic package evidence only; bolted_proxy connections are simplified "
            "assembly semantics, not preload/contact/thread-physics simulation."
        ),
    }


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
