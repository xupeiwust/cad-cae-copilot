"""Pure, deterministic engineering critique engine.

This module contains the geometry/topology audit logic behind
``cad.critique`` without any project/backend coupling.  It reads a
topology_map + feature_graph and returns structured manufacturing-rule
findings so both the interactive CAD tool and batch design-study
evaluation can share one source of truth.
"""
from __future__ import annotations

from typing import Any

from .credibility import classify_credibility


_THIN_PART_LABELS: tuple[str, ...] = (
    "wall", "rib", "cover", "lid", "back_plate", "base_plate",
    "plate", "shell", "flange",
)

_STANDARD_HOLE_DIAMETERS_MM: tuple[float, ...] = (
    1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0,
    12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 27.0, 30.0,
)


def is_named_part_feature(feature: dict[str, Any]) -> bool:
    return feature.get("type") in {"named_part", "standard_part"} and bool(feature.get("name"))


def _has_canonical_engineering_label(feat: dict[str, Any]) -> bool:
    name = (feat.get("name") or "").lower()
    canonical = (
        "base_plate", "back_plate", "mount_plate",
        "mounting_hole", "rib", "boss", "flange",
        "interface_face", "load_interface",
        "wall", "cover", "lid", "shell",
    )
    return any(c in name for c in canonical)


def _add_finding(
    findings: list[dict[str, Any]],
    counter: int,
    severity: str,
    category: str,
    rule: str,
    feature: str,
    feature_id: str | None,
    observation: str,
    fix: str,
) -> int:
    findings.append({
        "id": f"find_{counter:03d}",
        "severity": severity,
        "category": category,
        "rule": rule,
        "feature": feature,
        "feature_id": feature_id,
        "observation": observation,
        "suggested_fix": fix,
    })
    return counter + 1


def critique_geometry(
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
    *,
    mode: str = "auto",
    min_wall_mm: float = 3.0,
    min_corner_radius_mm: float = 2.0,
) -> dict[str, Any]:
    mode = str(mode or "auto")
    min_wall = float(min_wall_mm)
    min_corner_radius = float(min_corner_radius_mm)

    findings: list[dict[str, Any]] = []
    counter = 1

    entities = topology_map.get("entities", [])
    bodies = {e["id"]: e for e in entities if e.get("type") == "solid"}
    body_count = len(bodies)

    if body_count == 0:
        return {
            "status": "ok",
            "mode": mode,
            "verdict": "skipped",
            "message": "No solids in the topology map; nothing to critique.",
            "findings": [],
            "summary": {
                "findings_count": 0,
                "by_severity": {"high": 0, "medium": 0, "low": 0},
                "named_part_count": 0,
                "engineering_audit_run": False,
            },
            "rules_applied": {
                "min_wall_mm": min_wall,
                "min_corner_radius_mm": min_corner_radius,
                "standard_hole_diameters_mm": list(_STANDARD_HOLE_DIAMETERS_MM),
            },
            "rule_source": "aieng/schemas/constraints.schema.json (manufacturing_rule type)",
            "credibility": classify_credibility("critique"),
        }

    if body_count >= 2:
        body_data: list[tuple[str, dict[str, Any], tuple[float, float, float], float]] = []
        for body_id, b in bodies.items():
            bb = b.get("bounding_box") or []
            if len(bb) < 6:
                continue
            center = ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)
            size = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
            body_data.append((body_id, b, center, size))

        if len(body_data) >= 2:
            mean_size = sum(d[3] for d in body_data) / len(body_data)
            gap_threshold = max(mean_size, 50.0)

            for body_id, b, c1, s1 in body_data:
                min_gap = float("inf")
                for other_id, _, c2, s2 in body_data:
                    if other_id == body_id:
                        continue
                    center_dist = (
                        (c1[0] - c2[0]) ** 2
                        + (c1[1] - c2[1]) ** 2
                        + (c1[2] - c2[2]) ** 2
                    ) ** 0.5
                    gap = center_dist - (s1 + s2) / 2.0
                    if gap < min_gap:
                        min_gap = gap

                if min_gap > gap_threshold:
                    counter = _add_finding(
                        findings,
                        counter,
                        "high",
                        "geometry",
                        "floating_component",
                        b.get("name", body_id),
                        body_id,
                        f"{b.get('name', body_id)}: nearest other part is "
                        f"~{min_gap:.0f}mm away (typical part size {mean_size:.0f}mm) "
                        "— this part is disconnected from the rest of the model.",
                        "Check the Location() / .moved() coordinates for this part; "
                        "it may be a typo that placed it far from the body.",
                    )

    features = feature_graph.get("features", [])
    named_features = [f for f in features if is_named_part_feature(f)]

    engineering_eligible = (
        mode == "engineering"
        or (mode == "auto" and any(_has_canonical_engineering_label(f) for f in named_features))
    )

    if engineering_eligible:
        for feat in named_features:
            name = feat.get("name") or ""
            name_lower = name.lower()
            if not any(t in name_lower for t in _THIN_PART_LABELS):
                continue
            geo = feat.get("geometry_refs") or {}
            body_id = geo.get("body") if isinstance(geo, dict) else None
            body = bodies.get(body_id) if body_id else None
            if not body:
                continue
            bb = body.get("bounding_box") or []
            if len(bb) < 6:
                continue
            dims = (bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
            positive = [d for d in dims if d > 0]
            if not positive:
                continue
            thinnest = min(positive)
            if thinnest < min_wall:
                severity = "high" if any(t in name_lower for t in ("wall", "shell", "back_plate")) else "medium"
                counter = _add_finding(
                    findings,
                    counter,
                    severity,
                    "manufacturing_rule",
                    "min_wall_thickness",
                    name,
                    body_id,
                    f"{name}: thinnest dimension is {thinnest:.2f}mm; CNC minimum is {min_wall:.1f}mm.",
                    f"Increase the thinnest dimension of {name} to at least {min_wall:.1f}mm "
                    f"(or downgrade target process to sheet metal / FDM and lower min_wall_mm).",
                )

        for feat in features:
            if feat.get("type") not in ("mounting_hole", "mounting_hole_pattern"):
                continue
            params = feat.get("parameters") or {}
            diameter = params.get("hole_diameter_mm")
            if isinstance(diameter, (int, float)):
                nearest = min(_STANDARD_HOLE_DIAMETERS_MM, key=lambda d: abs(d - float(diameter)))
                if abs(float(diameter) - nearest) > 0.3:
                    counter = _add_finding(
                        findings,
                        counter,
                        "low",
                        "manufacturing_rule",
                        "standard_hole_size",
                        feat.get("name", "<unnamed>"),
                        (feat.get("geometry_refs", {}) or {}).get("body")
                        if isinstance(feat.get("geometry_refs"), dict) else None,
                        f"{feat.get('name', '<unnamed>')}: hole diameter {float(diameter):.2f}mm is "
                        f"non-standard; closest standard drill is {nearest:.1f}mm.",
                        f"Round the hole diameter to {nearest:.1f}mm to use an off-the-shelf drill.",
                    )

        looks_like_bracket = any(
            "bracket" in (b.get("name") or "").lower()
            or "plate" in (b.get("name") or "").lower()
            for b in bodies.values()
        )
        has_mounting = any(
            f.get("type") in ("mounting_hole", "mounting_hole_pattern") for f in features
        )
        if looks_like_bracket and not has_mounting:
            counter = _add_finding(
                findings,
                counter,
                "medium",
                "engineering",
                "missing_mounting_interface",
                "(model)",
                None,
                "Model contains a plate / bracket part but no mounting holes were detected.",
                "Add at least one Hole() / cboreHole() / cskHole() to expose a mounting interface, "
                "or label the holes you have so the topology heuristic picks them up.",
            )

    severity_counts = {
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "medium": sum(1 for f in findings if f["severity"] == "medium"),
        "low": sum(1 for f in findings if f["severity"] == "low"),
    }
    if severity_counts["high"] > 0:
        verdict = "fails_audit"
    elif severity_counts["medium"] > 0:
        verdict = "passes_with_warnings"
    elif severity_counts["low"] > 0:
        verdict = "passes_with_notes"
    else:
        verdict = "passes"

    fail_first = [
        f"{f['feature']}: {f['observation']}"
        for f in findings
        if f["severity"] in ("high", "medium")
    ][:5]

    return {
        "status": "ok",
        "mode": mode,
        "verdict": verdict,
        "summary": {
            "findings_count": len(findings),
            "by_severity": severity_counts,
            "named_part_count": len(named_features),
            "engineering_audit_run": engineering_eligible,
        },
        "fail_first_objections": fail_first,
        "findings": findings,
        "rules_applied": {
            "min_wall_mm": min_wall,
            "min_corner_radius_mm": min_corner_radius,
            "standard_hole_diameters_mm": list(_STANDARD_HOLE_DIAMETERS_MM),
        },
        "rule_source": "aieng/schemas/constraints.schema.json (manufacturing_rule type)",
        "credibility": classify_credibility("critique"),
    }
