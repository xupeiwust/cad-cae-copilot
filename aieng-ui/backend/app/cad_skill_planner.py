from __future__ import annotations

import re
from typing import Any


_MM_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)", re.IGNORECASE)
_COUNT_RE = re.compile(r"(?P<count>\d+)\s*(?:x|个|孔)", re.IGNORECASE)


def _first_mm(text: str) -> float | None:
    match = _MM_RE.search(text)
    if not match:
        return None
    return float(match.group("value"))


def _bolt_hole_count(text: str) -> int:
    if "四孔" in text or "4孔" in text or "四个孔" in text:
        return 4
    if "六孔" in text or "6孔" in text or "六个孔" in text:
        return 6
    if "八孔" in text or "8孔" in text or "八个孔" in text:
        return 8
    match = _COUNT_RE.search(text)
    if not match:
        return 4
    count = int(match.group("count"))
    return count if 2 <= count <= 16 else 4


def _is_flange_request(text: str) -> bool:
    lower = text.lower()
    return "法兰" in text or "flange" in lower


def _flange_code(
    *,
    outer_diameter: float,
    thickness: float,
    center_bore: float,
    bolt_circle: float,
    bolt_hole_diameter: float,
    bolt_hole_count: int,
    fillet_radius: float,
) -> str:
    return f"""from build123d import *

FLANGE_OUTER_DIAMETER = {outer_diameter:.3f}
FLANGE_THICKNESS = {thickness:.3f}
CENTER_BORE_DIAMETER = {center_bore:.3f}
BOLT_CIRCLE_DIAMETER = {bolt_circle:.3f}
BOLT_HOLE_DIAMETER = {bolt_hole_diameter:.3f}
BOLT_HOLE_COUNT = {bolt_hole_count}
FILLET_RADIUS = {fillet_radius:.3f}

with BuildPart() as flange_bp:
    Cylinder(
        radius=FLANGE_OUTER_DIAMETER / 2,
        height=FLANGE_THICKNESS,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    Hole(radius=CENTER_BORE_DIAMETER / 2, depth=FLANGE_THICKNESS)
    with PolarLocations(radius=BOLT_CIRCLE_DIAMETER / 2, count=BOLT_HOLE_COUNT):
        Hole(radius=BOLT_HOLE_DIAMETER / 2, depth=FLANGE_THICKNESS)
    fillet(flange_bp.edges().filter_by(GeomType.CIRCLE), radius=FILLET_RADIUS)

base_plate = flange_bp.part
base_plate.label = "base_plate"
base_plate.color = Color(0.56, 0.62, 0.68)

result = Compound(children=[base_plate])
"""


def plan_build123d_skill(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a skill-authored build123d execution plan without mutating files.

    The Autopilot agent remains the orchestrator: it calls this read-only tool,
    reviews the returned assumptions and execute_input, then separately calls
    cad.execute_build123d when it wants to proceed through the approval gate.
    """

    message = str(payload.get("message") or payload.get("intent") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        return {
            "status": "error",
            "code": "missing_project_id",
            "message": "project_id is required.",
        }
    if not message:
        return {
            "status": "needs_clarification",
            "skill_name": "cad.plan_build123d_skill",
            "question": "What CAD part should be generated?",
        }

    if not _is_flange_request(message):
        return {
            "status": "unsupported",
            "skill_name": "cad.plan_build123d_skill",
            "intent": message,
            "supported_patterns": ["flange / 法兰盘"],
            "recommendation": (
                "Use cad.get_source followed by agent-authored cad.execute_build123d "
                "for this request, or add a new deterministic CAD skill template."
            ),
        }

    outer_diameter = _first_mm(message) or float(payload.get("outer_diameter_mm") or 40.0)
    thickness = float(payload.get("thickness_mm") or max(4.0, round(outer_diameter * 0.15, 1)))
    center_bore = float(payload.get("center_bore_diameter_mm") or max(6.0, round(outer_diameter * 0.30, 1)))
    bolt_circle = float(payload.get("bolt_circle_diameter_mm") or round(outer_diameter * 0.75, 1))
    bolt_hole_diameter = float(payload.get("bolt_hole_diameter_mm") or 4.0)
    bolt_hole_count = int(payload.get("bolt_hole_count") or _bolt_hole_count(message))
    fillet_radius = float(payload.get("fillet_radius_mm") or min(1.5, max(0.5, thickness * 0.18)))

    edge_margin = (outer_diameter - bolt_circle) / 2
    min_edge_margin = bolt_hole_diameter
    warnings: list[str] = []
    if edge_margin < min_edge_margin:
        warnings.append(
            "Bolt-hole edge distance is below the 2x radius rule; reduce bolt_circle_diameter_mm "
            "or bolt_hole_diameter_mm before executing."
        )

    assumptions = [
        f"Interpreted {outer_diameter:g}mm as flange outside diameter.",
        f"Defaulted thickness to {thickness:g}mm.",
        f"Defaulted center bore to {center_bore:g}mm.",
        f"Defaulted bolt pattern to {bolt_hole_count} holes on a {bolt_circle:g}mm pitch circle.",
        f"Defaulted bolt-hole diameter to {bolt_hole_diameter:g}mm.",
    ]
    code = _flange_code(
        outer_diameter=outer_diameter,
        thickness=thickness,
        center_bore=center_bore,
        bolt_circle=bolt_circle,
        bolt_hole_diameter=bolt_hole_diameter,
        bolt_hole_count=bolt_hole_count,
        fillet_radius=fillet_radius,
    )
    execute_input = {
        "project_id": project_id,
        "name": f"{outer_diameter:g}mm flange",
        "code": code,
        "mode": "replace",
        "model_kind": "mechanical",
        "timeout": 60,
    }
    return {
        "status": "ready",
        "skill_name": "cad.plan_build123d_skill",
        "pattern": "flange",
        "intent": message,
        "brief": (
            f"Mechanical flange: OD {outer_diameter:g}mm, thickness {thickness:g}mm, "
            f"center bore {center_bore:g}mm, {bolt_hole_count}x {bolt_hole_diameter:g}mm "
            f"bolt holes on {bolt_circle:g}mm PCD."
        ),
        "assumptions": assumptions,
        "warnings": warnings,
        "validation_targets": [
            "base_plate named part exists",
            "mounting holes are through-holes",
            "cad.critique passes edge-distance and geometry sanity checks",
        ],
        "next_tool": "cad.execute_build123d",
        "execute_input": execute_input,
    }


__all__ = ["plan_build123d_skill"]
