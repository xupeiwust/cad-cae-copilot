"""CAD modeling-fidelity benchmark scorecard v0.

This module is intentionally deterministic and geometry-artifact based. It does
not call an LLM, render images, or claim visual equivalence; it scores explicit
spatial/semantic criteria that can be checked from topology_map / feature_graph
and optional geometry_report signals.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

SCORECARD_FORMAT = "aieng.cad_fidelity.scorecard.v0"

CAD_FIDELITY_CASES: list[dict[str, Any]] = [
    {
        "case_id": "flange_m6_four_hole_pattern",
        "prompt": "Create a circular flange with center bore and four M6 mounting holes.",
        "source_provenance": "AIENG-authored regression prompt inspired by common mechanical flange tasks.",
        "required_named_parts": ["flange"],
        "required_feature_types": [
            {"type": "mounting_hole_pattern", "min_count": 1},
            {"type": "bore", "min_count": 1},
        ],
        "bbox_proportions": [1.0, 1.0, 0.12],
        "bbox_tolerance": 0.35,
        "failure_conditions": [
            "exports only a featureless cylinder or box",
            "missing center bore or mounting-hole semantic feature",
        ],
    },
    {
        "case_id": "ribbed_mounting_plate",
        "prompt": "Create a rectangular mounting plate with two stiffening ribs and four corner holes.",
        "source_provenance": "AIENG-authored regression prompt for rib/plate placement.",
        "required_named_parts": ["base_plate"],
        "required_feature_types": [
            {"type": "mounting_hole_pattern", "min_count": 1},
            {"type": "rib", "min_count": 1},
        ],
        "bbox_proportions": [1.0, 0.65, 0.18],
        "bbox_tolerance": 0.35,
        "failure_conditions": [
            "ribs are absent or unlabeled",
            "holes export geometrically but are not represented as a hole pattern",
        ],
    },
    {
        "case_id": "open_top_housing_shell",
        "prompt": "Create an open-top electronics housing with wall thickness, filleted edges, and bosses.",
        "source_provenance": "AIENG-authored enclosure prompt; no external geometry copied.",
        "required_named_parts": ["housing"],
        "required_feature_types": [
            {"type": "hollow_body", "min_count": 1},
            {"type": "fillet", "min_count": 1},
            {"type": "boss", "min_count": 1},
        ],
        "bbox_proportions": [1.0, 0.7, 0.45],
        "bbox_tolerance": 0.4,
        "failure_conditions": [
            "solid block instead of shell/housing",
            "edge-breaking or boss intent missing from feature graph",
        ],
    },
    {
        "case_id": "slotted_adjustment_bracket",
        "prompt": "Create an L-bracket with a slotted adjustment hole and filleted internal corner.",
        "source_provenance": "AIENG-authored bracket prompt.",
        "required_named_parts": ["bracket"],
        "required_feature_types": [
            {"type": "slot", "min_count": 1},
            {"type": "fillet", "min_count": 1},
        ],
        "bbox_proportions": [1.0, 0.55, 0.75],
        "bbox_tolerance": 0.45,
        "failure_conditions": [
            "slot modeled as an unlabeled circular hole",
            "two bracket legs are mispositioned or not connected",
        ],
    },
    {
        "case_id": "threaded_boss_plate",
        "prompt": "Create a plate with a raised screw boss and threaded hole.",
        "source_provenance": "AIENG-authored fastener-interface prompt.",
        "required_named_parts": ["boss"],
        "required_feature_types": [
            {"type": "boss", "min_count": 1},
            {"type": "thread", "min_count": 1},
        ],
        "bbox_proportions": [1.0, 0.7, 0.25],
        "bbox_tolerance": 0.45,
        "failure_conditions": [
            "boss not identified separately from base plate",
            "thread intent absent or claimed without recognition metadata",
        ],
    },
    {
        "case_id": "clevis_pin_bracket",
        "prompt": "Create a clevis bracket with two parallel ears and aligned pin holes.",
        "source_provenance": "AIENG-authored clevis prompt based on standard mechanical vocabulary.",
        "required_named_parts": ["clevis"],
        "required_feature_types": [
            {"type": "mounting_hole", "min_count": 1},
            {"type": "fillet", "min_count": 1},
        ],
        "bbox_proportions": [1.0, 0.55, 0.65],
        "bbox_tolerance": 0.5,
        "failure_conditions": [
            "single solid block with no ear/hole semantics",
            "pin holes not represented as cylindrical features",
        ],
    },
    {
        "case_id": "two_plate_bolted_stack",
        "prompt": "Create two aligned plates joined by four bolts and nuts.",
        "source_provenance": "AIENG-authored assembly prompt for spatial alignment checks.",
        "required_named_parts": ["plate", "bolt"],
        "required_feature_types": [
            {"type": "standard_part", "min_count": 4},
            {"type": "mounting_hole_pattern", "min_count": 1},
        ],
        "max_floating_parts": 0,
        "bbox_proportions": [1.0, 0.7, 0.2],
        "bbox_tolerance": 0.5,
        "failure_conditions": [
            "bolts are floating or not coaxial with hole pattern",
            "standard-part semantics missing from feature graph/BOM",
        ],
    },
    {
        "case_id": "robot_joint_yoke",
        "prompt": "Create a compact robot joint yoke with mirrored side cheeks, central bore, and fillets.",
        "source_provenance": "AIENG-authored robot-joint prompt; inspired by generic yoke geometry.",
        "required_named_parts": ["joint", "yoke"],
        "required_feature_types": [
            {"type": "bore", "min_count": 1},
            {"type": "fillet", "min_count": 1},
        ],
        "max_symmetry_issues": 0,
        "bbox_proportions": [1.0, 0.75, 0.65],
        "bbox_tolerance": 0.5,
        "failure_conditions": [
            "left/right side features are asymmetric without intent",
            "central bore absent from feature graph",
        ],
    },
]


def list_cad_fidelity_cases() -> list[dict[str, Any]]:
    """Return a copy of the built-in CAD-fidelity benchmark cases."""
    return deepcopy(CAD_FIDELITY_CASES)


def score_cad_fidelity_case(
    case_id: str,
    *,
    topology_map: dict[str, Any] | None = None,
    feature_graph: dict[str, Any] | None = None,
    geometry_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one benchmark case against explicit topology/feature criteria."""
    cases = {case["case_id"]: case for case in CAD_FIDELITY_CASES}
    if case_id not in cases:
        raise ValueError(f"unknown CAD fidelity case_id: {case_id}")
    return _score_case(
        cases[case_id],
        topology_map=topology_map or {},
        feature_graph=feature_graph or {},
        geometry_report=geometry_report or {},
    )


def score_cad_fidelity_suite(
    *,
    topology_map: dict[str, Any] | None = None,
    feature_graph: dict[str, Any] | None = None,
    geometry_report: dict[str, Any] | None = None,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Score a model against multiple built-in CAD-fidelity cases."""
    selected = case_ids or [case["case_id"] for case in CAD_FIDELITY_CASES]
    results = [
        score_cad_fidelity_case(
            cid,
            topology_map=topology_map,
            feature_graph=feature_graph,
            geometry_report=geometry_report,
        )
        for cid in selected
    ]
    possible = sum(r["score"]["possible"] for r in results)
    earned = sum(r["score"]["earned"] for r in results)
    return {
        "format": SCORECARD_FORMAT,
        "status": "passed" if possible and earned == possible else "partial",
        "summary": {
            "case_count": len(results),
            "earned": earned,
            "possible": possible,
            "score_fraction": round(earned / possible, 4) if possible else 0.0,
            "passed_cases": sum(1 for r in results if r["status"] == "passed"),
            "failed_cases": sum(1 for r in results if r["status"] == "failed"),
        },
        "cases": results,
        "honesty_boundary": (
            "CAD fidelity scorecard covers explicit measurable criteria only; "
            "it is regression evidence, not certification or visual equivalence."
        ),
    }


def _score_case(
    case: dict[str, Any],
    *,
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
    geometry_report: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.extend(_check_named_parts(case, topology_map, feature_graph))
    checks.extend(_check_feature_types(case, feature_graph))
    checks.extend(_check_bbox_proportions(case, topology_map))
    checks.extend(_check_geometry_report_limits(case, geometry_report))
    earned = sum(1 for c in checks if c["status"] == "pass")
    possible = len(checks)
    status = "passed" if possible and earned == possible else "failed"
    return {
        "format": SCORECARD_FORMAT,
        "case_id": case["case_id"],
        "prompt": case["prompt"],
        "source_provenance": case["source_provenance"],
        "status": status,
        "score": {
            "earned": earned,
            "possible": possible,
            "fraction": round(earned / possible, 4) if possible else 0.0,
        },
        "checks": checks,
        "failure_conditions": list(case.get("failure_conditions") or []),
        "honesty_boundary": (
            "No visual-equivalence or manufacturing-certification claim is implied."
        ),
    }


def _features(feature_graph: dict[str, Any]) -> list[dict[str, Any]]:
    raw = feature_graph.get("features", [])
    if isinstance(raw, dict):
        return [v for v in raw.values() if isinstance(v, dict)]
    if isinstance(raw, list):
        return [v for v in raw if isinstance(v, dict)]
    return []


def _named_part_labels(topology_map: dict[str, Any], feature_graph: dict[str, Any]) -> set[str]:
    labels = {
        str(e.get("name")).lower()
        for e in topology_map.get("entities", [])
        if isinstance(e, dict) and e.get("type") == "solid" and e.get("name")
    }
    for feat in _features(feature_graph):
        if feat.get("type") in {"named_part", "standard_part"} and feat.get("name"):
            labels.add(str(feat["name"]).lower())
    return labels


def _check_named_parts(
    case: dict[str, Any],
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    labels = _named_part_labels(topology_map, feature_graph)
    checks = []
    for expected in case.get("required_named_parts", []) or []:
        needle = str(expected).lower()
        matched = any(needle in label for label in labels)
        checks.append({
            "id": f"named_part:{expected}",
            "category": "semantic_parts",
            "status": "pass" if matched else "fail",
            "expected": expected,
            "observed": sorted(labels),
        })
    return checks


def _check_feature_types(case: dict[str, Any], feature_graph: dict[str, Any]) -> list[dict[str, Any]]:
    features = _features(feature_graph)
    checks = []
    for spec in case.get("required_feature_types", []) or []:
        ftype = str(spec.get("type"))
        min_count = int(spec.get("min_count", 1))
        count = sum(1 for feat in features if feat.get("type") == ftype)
        recognized = [
            feat for feat in features
            if feat.get("type") == ftype and isinstance(feat.get("recognition"), dict)
        ]
        check: dict[str, Any] = {
            "id": f"feature_type:{ftype}",
            "category": "semantic_features",
            "status": "pass" if count >= min_count else "fail",
            "expected": {"type": ftype, "min_count": min_count},
            "observed": {"count": count},
        }
        if ftype in {"fillet", "slot", "pocket", "rib", "thread", "hollow_body"}:
            check["recognition_metadata_count"] = len(recognized)
            if count >= min_count and len(recognized) < min_count:
                check["status"] = "fail"
                check["message"] = "candidate feature lacks recognition metadata"
        checks.append(check)
    return checks


def _solid_bbox(topology_map: dict[str, Any]) -> list[float] | None:
    boxes = [
        e.get("bounding_box")
        for e in topology_map.get("entities", [])
        if isinstance(e, dict)
        and e.get("type") == "solid"
        and isinstance(e.get("bounding_box"), list)
        and len(e.get("bounding_box")) == 6
    ]
    if not boxes:
        return None
    return [
        min(float(b[0]) for b in boxes),
        min(float(b[1]) for b in boxes),
        min(float(b[2]) for b in boxes),
        max(float(b[3]) for b in boxes),
        max(float(b[4]) for b in boxes),
        max(float(b[5]) for b in boxes),
    ]


def _normalized_bbox_proportions(bbox: list[float]) -> list[float]:
    dims = [max(0.0, float(bbox[3 + i]) - float(bbox[i])) for i in range(3)]
    scale = max(dims) or 1.0
    return [round(d / scale, 4) for d in dims]


def _check_bbox_proportions(case: dict[str, Any], topology_map: dict[str, Any]) -> list[dict[str, Any]]:
    expected = case.get("bbox_proportions")
    if not expected:
        return []
    bbox = _solid_bbox(topology_map)
    if bbox is None:
        return [{
            "id": "bbox_proportions",
            "category": "spatial_proportions",
            "status": "fail",
            "expected": expected,
            "observed": None,
            "message": "no solid bounding box available",
        }]
    observed = _normalized_bbox_proportions(bbox)
    tolerance = float(case.get("bbox_tolerance", 0.35))
    max_error = max(abs(float(a) - float(b)) for a, b in zip(observed, expected))
    return [{
        "id": "bbox_proportions",
        "category": "spatial_proportions",
        "status": "pass" if max_error <= tolerance else "fail",
        "expected": expected,
        "observed": observed,
        "tolerance": tolerance,
        "max_error": round(max_error, 4),
    }]


def _geometry_report_count(report: dict[str, Any], *keys: str) -> int | None:
    node: Any = report
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, int):
        return node
    if isinstance(node, list):
        return len(node)
    return None


def _check_geometry_report_limits(case: dict[str, Any], geometry_report: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if "max_floating_parts" in case:
        observed = (
            _geometry_report_count(geometry_report, "summary", "floating_parts")
            or _geometry_report_count(geometry_report, "structural", "floating_parts")
            or 0
        )
        maximum = int(case["max_floating_parts"])
        checks.append({
            "id": "max_floating_parts",
            "category": "spatial_assembly",
            "status": "pass" if observed <= maximum else "fail",
            "expected": {"max": maximum},
            "observed": observed,
        })
    if "max_symmetry_issues" in case:
        observed = (
            _geometry_report_count(geometry_report, "summary", "symmetry_issues")
            or _geometry_report_count(geometry_report, "structural", "symmetry_issues")
            or 0
        )
        maximum = int(case["max_symmetry_issues"])
        checks.append({
            "id": "max_symmetry_issues",
            "category": "spatial_symmetry",
            "status": "pass" if observed <= maximum else "fail",
            "expected": {"max": maximum},
            "observed": observed,
        })
    return checks
