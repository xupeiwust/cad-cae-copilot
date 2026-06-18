"""Pure hole-to-fastener planning helpers.

The planner consumes feature-graph ``hole_metadata`` and returns an advisory
fastener specification. It never mutates CAD, writes packages, inserts parts, or
claims that a standard part is present in the model.
"""
from __future__ import annotations

from typing import Any

from aieng.modeling.standard_parts import FASTENERS

NUMERIC_TYPES = (int, float)


def plan_fastener_for_hole(
    hole_metadata: dict[str, Any] | None,
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    tolerance_mm: float = 0.25,
) -> dict[str, Any]:
    """Return an advisory fastener candidate for one hole metadata record."""
    if not isinstance(hole_metadata, dict):
        return _result("unsupported", reasons=["hole_metadata must be an object"])

    catalog = catalog or FASTENERS
    threaded = _thread_evidence(hole_metadata)
    if threaded is not None:
        return _threaded_match(threaded, catalog=catalog, tolerance_mm=tolerance_mm)

    diameter = _num(hole_metadata.get("diameter_mm"))
    if diameter is None or diameter <= 0:
        return _result("no_match", reasons=["hole diameter is missing or invalid"])

    matches = _catalog_matches(
        diameter,
        catalog=catalog,
        field="clearance_hole",
        tolerance_mm=tolerance_mm,
    )
    if not matches:
        return _result(
            "no_match",
            reasons=[f"diameter {diameter:g} mm is outside the supported metric clearance-hole catalog"],
            observed={"diameter_mm": diameter},
        )
    if len(matches) > 1:
        return _result(
            "ambiguous",
            reasons=[f"diameter {diameter:g} mm matches multiple metric clearance-hole entries"],
            candidates=[_candidate_summary(size, data) for size, data in matches],
            observed={"diameter_mm": diameter},
        )

    size, data = matches[0]
    mode, head_style, part_type = _mode_and_head_style(hole_metadata)
    spec = _base_spec(size, data, mode=mode, part_type=part_type, head_style=head_style)
    spec["hole_diameter_mm"] = diameter
    if hole_metadata.get("hole_depth_kind") in {"through", "blind"}:
        spec["hole_depth_kind"] = hole_metadata["hole_depth_kind"]
    if isinstance(hole_metadata.get("through"), bool):
        spec["through"] = hole_metadata["through"]
    if isinstance(hole_metadata.get("counterbore"), dict):
        spec["counterbore"] = dict(hole_metadata["counterbore"])
    if isinstance(hole_metadata.get("countersink"), dict):
        spec["countersink"] = dict(hole_metadata["countersink"])

    length = _suggested_length(hole_metadata, data)
    if length is not None:
        spec["suggested_length_mm"] = length

    spec["nut_requirement"] = _nut_requirement(hole_metadata)
    return _result(
        "matched",
        mode=mode,
        fastener_spec=spec,
        reasons=[f"diameter {diameter:g} mm matched {size} clearance-hole catalog"],
    )


def plan_fasteners_for_features(
    features: list[dict[str, Any]],
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    tolerance_mm: float = 0.25,
) -> list[dict[str, Any]]:
    """Plan advisory fasteners for feature records carrying ``hole_metadata``."""
    plans: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        metadata = feature.get("hole_metadata")
        if not isinstance(metadata, dict):
            continue
        plan = plan_fastener_for_hole(metadata, catalog=catalog, tolerance_mm=tolerance_mm)
        plan["feature_id"] = feature.get("id")
        plan["feature_type"] = feature.get("type")
        plans.append(plan)
    return plans


def _threaded_match(
    threaded: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    tolerance_mm: float,
) -> dict[str, Any]:
    designation = threaded.get("designation")
    if isinstance(designation, str) and designation in catalog:
        size = designation
        data = catalog[size]
    else:
        diameter = _num(threaded.get("diameter_mm"))
        if diameter is None:
            return _result("no_match", reasons=["thread evidence is explicit but lacks designation or diameter"])
        matches = _catalog_matches(
            diameter,
            catalog=catalog,
            field="thread_diameter",
            tolerance_mm=tolerance_mm,
        )
        if not matches:
            return _result(
                "no_match",
                reasons=[f"thread diameter {diameter:g} mm is outside the supported metric catalog"],
                observed={"thread_diameter_mm": diameter},
            )
        if len(matches) > 1:
            return _result(
                "ambiguous",
                reasons=[f"thread diameter {diameter:g} mm matches multiple catalog entries"],
                candidates=[_candidate_summary(size, data) for size, data in matches],
                observed={"thread_diameter_mm": diameter},
            )
        size, data = matches[0]

    spec = _base_spec(size, data, mode="threaded", part_type="socket_head_cap_screw", head_style="socket_head")
    spec["threaded_hole"] = True
    spec["nut_requirement"] = "not_required_threaded_hole"
    if isinstance(threaded.get("pitch_mm"), NUMERIC_TYPES):
        spec["thread_pitch_mm"] = float(threaded["pitch_mm"])
    return _result(
        "matched",
        mode="threaded",
        fastener_spec=spec,
        reasons=[f"explicit thread evidence matched {size} metric fastener catalog"],
    )


def _thread_evidence(hole_metadata: dict[str, Any]) -> dict[str, Any] | None:
    thread = hole_metadata.get("thread")
    if isinstance(thread, dict):
        return {
            "designation": thread.get("designation") or thread.get("size"),
            "diameter_mm": thread.get("diameter_mm") or thread.get("major_diameter_mm"),
            "pitch_mm": thread.get("pitch_mm") or thread.get("thread_pitch_mm"),
        }
    if hole_metadata.get("threaded") is True or hole_metadata.get("tapped") is True:
        return {
            "designation": hole_metadata.get("thread_designation") or hole_metadata.get("designation"),
            "diameter_mm": hole_metadata.get("thread_diameter_mm"),
            "pitch_mm": hole_metadata.get("thread_pitch_mm"),
        }
    return None


def _mode_and_head_style(hole_metadata: dict[str, Any]) -> tuple[str, str, str]:
    if isinstance(hole_metadata.get("counterbore"), dict):
        return "counterbore", "socket_head", "socket_head_cap_screw"
    if isinstance(hole_metadata.get("countersink"), dict):
        return "countersunk", "countersunk", "flat_head_socket_screw"
    return "clearance", "general", "hex_bolt"


def _catalog_matches(
    value: float,
    *,
    catalog: dict[str, dict[str, Any]],
    field: str,
    tolerance_mm: float,
) -> list[tuple[str, dict[str, Any]]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for size, data in sorted(catalog.items()):
        target = _num(data.get(field))
        if target is not None and abs(value - target) <= tolerance_mm:
            matches.append((size, data))
    return matches


def _base_spec(
    size: str,
    data: dict[str, Any],
    *,
    mode: str,
    part_type: str,
    head_style: str,
) -> dict[str, Any]:
    spec = {
        "designation": size,
        "metric_size": size,
        "mode": mode,
        "part_type": part_type,
        "head_style": head_style,
        "nominal_thread_diameter_mm": float(data["thread_diameter"]),
        "clearance_hole_diameter_mm": float(data["clearance_hole"]),
        "source": "aieng.modeling.standard_parts.FASTENERS",
        "advisory_only": True,
    }
    for source_key, target_key in (
        ("counterbore_diameter", "catalog_counterbore_diameter_mm"),
        ("counterbore_depth", "catalog_counterbore_depth_mm"),
        ("head_diameter", "catalog_head_diameter_mm"),
        ("head_height", "catalog_head_height_mm"),
    ):
        value = _num(data.get(source_key))
        if value is not None:
            spec[target_key] = value
    lengths = data.get("standard_lengths")
    if isinstance(lengths, list):
        spec["standard_lengths"] = [float(length) for length in lengths if isinstance(length, NUMERIC_TYPES)]
    return spec


def _candidate_summary(size: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "designation": size,
        "thread_diameter_mm": _num(data.get("thread_diameter")),
        "clearance_hole_diameter_mm": _num(data.get("clearance_hole")),
    }


def _suggested_length(hole_metadata: dict[str, Any], data: dict[str, Any]) -> float | None:
    target = _num(hole_metadata.get("depth_mm"))
    stack = hole_metadata.get("mating_stack")
    if isinstance(stack, dict) and stack.get("status") == "known":
        stack_thickness = _num(stack.get("thickness_mm"))
        if stack_thickness is not None:
            target = max(target or 0.0, stack_thickness)
    if target is None:
        return None
    lengths = data.get("standard_lengths")
    if not isinstance(lengths, list):
        return target
    numeric_lengths = sorted(float(length) for length in lengths if isinstance(length, NUMERIC_TYPES))
    for length in numeric_lengths:
        if length >= target:
            return length
    return numeric_lengths[-1] if numeric_lengths else target


def _nut_requirement(hole_metadata: dict[str, Any]) -> str:
    stack = hole_metadata.get("mating_stack")
    if isinstance(stack, dict) and stack.get("status") == "known":
        return "unknown_requires_design_review"
    if hole_metadata.get("through") is True:
        return "unknown_through_clearance_hole"
    return "unknown"


def _result(
    status: str,
    *,
    mode: str | None = None,
    fastener_spec: dict[str, Any] | None = None,
    reasons: list[str] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    observed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "advisory_only": True,
        "mutates_geometry": False,
        "reasons": reasons or [],
    }
    if mode is not None:
        result["mode"] = mode
    if fastener_spec is not None:
        result["fastener_spec"] = fastener_spec
    if candidates is not None:
        result["candidates"] = candidates
    if observed is not None:
        result["observed"] = observed
    return result


def _num(value: Any) -> float | None:
    if isinstance(value, NUMERIC_TYPES):
        return float(value)
    return None
