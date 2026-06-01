from __future__ import annotations

import re
from typing import Any

from .agent_autopilot.schema import SkillToolOutput


_MM_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)", re.IGNORECASE)
_COUNT_RE = re.compile(r"(?P<count>\d+)\s*(?:x|个|孔)", re.IGNORECASE)
_DIMENSION_RE = re.compile(
    r"(?P<a>\d+(?:\.\d+)?)\s*(?:x|×|by|乘)\s*(?P<b>\d+(?:\.\d+)?)(?:\s*(?:x|×|by|乘)\s*(?P<c>\d+(?:\.\d+)?))?\s*(?:mm|毫米|公厘)?",
    re.IGNORECASE,
)
_METRIC_HOLE_RE = re.compile(r"\bM(?P<diameter>\d+(?:\.\d+)?)\b", re.IGNORECASE)
_HEIGHT_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)?\s*(?:高|height|tall)", re.IGNORECASE)
_WALL_RE = re.compile(r"(?:壁厚|wall\s*thickness)\s*(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)?", re.IGNORECASE)
_OD_RE = re.compile(r"(?:外径|OD|outer\s*diameter)\s*(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)?", re.IGNORECASE)
_ID_RE = re.compile(r"(?:内径|ID|inner\s*diameter|bore)\s*(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)?", re.IGNORECASE)
_LENGTH_RE = re.compile(r"(?:长度|长|length)\s*(?P<value>\d+(?:\.\d+)?)\s*(?:mm|毫米|公厘)?", re.IGNORECASE)


def _first_mm(text: str) -> float | None:
    match = _MM_RE.search(text)
    if not match:
        return None
    return float(match.group("value"))


def _dimension_values(text: str) -> list[float]:
    match = _DIMENSION_RE.search(text)
    if not match:
        return []
    values = [float(match.group("a")), float(match.group("b"))]
    if match.group("c"):
        values.append(float(match.group("c")))
    return values


def _bolt_hole_count(text: str) -> int:
    lower = text.lower()
    if "四孔" in text or "4孔" in text or ("四个" in text and "孔" in text):
        return 4
    if "六孔" in text or "6孔" in text or ("六个" in text and "孔" in text):
        return 6
    if "八孔" in text or "8孔" in text or ("八个" in text and "孔" in text):
        return 8
    hole_match = re.search(r"(?P<count>\d+)\s*(?:holes|hole)", lower)
    if hole_match:
        count = int(hole_match.group("count"))
        return count if 2 <= count <= 16 else 4
    match = _COUNT_RE.search(text)
    if not match:
        return 4
    count = int(match.group("count"))
    return count if 2 <= count <= 16 else 4


def _is_flange_request(text: str) -> bool:
    lower = text.lower()
    return "法兰" in text or "flange" in lower


def _is_mounting_plate_request(text: str) -> bool:
    lower = text.lower()
    return "安装板" in text or "mounting plate" in lower or "base plate" in lower


def _is_l_bracket_request(text: str) -> bool:
    lower = text.lower()
    return "l型支架" in lower or "l 型支架" in lower or "角码" in text or "l bracket" in lower or "angle bracket" in lower


def _is_enclosure_request(text: str) -> bool:
    lower = text.lower()
    return "外壳" in text or "盒子" in text or "enclosure" in lower or "case" in lower


def _is_bushing_request(text: str) -> bool:
    lower = text.lower()
    return "轴套" in text or "衬套" in text or "隔套" in text or "spacer" in lower or "bushing" in lower or "sleeve" in lower


def _height_value(text: str) -> float | None:
    match = _HEIGHT_RE.search(text)
    if not match:
        return None
    return float(match.group("value"))


def _wall_thickness_value(text: str) -> float | None:
    match = _WALL_RE.search(text)
    if not match:
        return None
    return float(match.group("value"))


def _tagged_value(text: str, pattern: re.Pattern[str]) -> float | None:
    match = pattern.search(text)
    if not match:
        return None
    return float(match.group("value"))


def _hole_diameter(text: str, default: float) -> float:
    metric = _METRIC_HOLE_RE.search(text)
    if metric:
        return float(metric.group("diameter"))
    lower = text.lower()
    for match in _MM_RE.finditer(text):
        end = min(len(lower), match.end() + 8)
        if "孔" in lower[match.start():end] or "hole" in lower[match.start():end]:
            return float(match.group("value"))
    return default


def _skill_output(output: SkillToolOutput, **compat: Any) -> dict[str, Any]:
    data = output.model_dump()
    if output.proposed_tool:
        data["next_tool"] = output.proposed_tool
    if output.proposed_input:
        data["execute_input"] = output.proposed_input
    if output.verification_targets:
        data["validation_targets"] = output.verification_targets
    data.update(compat)
    return data


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


def _hole_grid_counts(total_count: int) -> tuple[int, int]:
    if total_count <= 4:
        return 2, 2
    if total_count <= 6:
        return 3, 2
    return max(2, total_count // 2), 2


def _mounting_plate_code(
    *,
    length: float,
    width: float,
    thickness: float,
    hole_diameter: float,
    count_x: int,
    count_y: int,
    margin_x: float,
    margin_y: float,
    fillet_radius: float,
) -> str:
    return f"""from build123d import *

PLATE_LENGTH = {length:.3f}
PLATE_WIDTH = {width:.3f}
PLATE_THICKNESS = {thickness:.3f}
MOUNTING_HOLE_DIAMETER = {hole_diameter:.3f}
MOUNTING_HOLE_COUNT_X = {count_x}
MOUNTING_HOLE_COUNT_Y = {count_y}
MOUNTING_HOLE_MARGIN_X = {margin_x:.3f}
MOUNTING_HOLE_MARGIN_Y = {margin_y:.3f}
FILLET_RADIUS = {fillet_radius:.3f}

hole_locations = []
for ix in range(MOUNTING_HOLE_COUNT_X):
    x = -PLATE_LENGTH / 2 + MOUNTING_HOLE_MARGIN_X
    if MOUNTING_HOLE_COUNT_X > 1:
        x += ix * (PLATE_LENGTH - 2 * MOUNTING_HOLE_MARGIN_X) / (MOUNTING_HOLE_COUNT_X - 1)
    for iy in range(MOUNTING_HOLE_COUNT_Y):
        y = -PLATE_WIDTH / 2 + MOUNTING_HOLE_MARGIN_Y
        if MOUNTING_HOLE_COUNT_Y > 1:
            y += iy * (PLATE_WIDTH - 2 * MOUNTING_HOLE_MARGIN_Y) / (MOUNTING_HOLE_COUNT_Y - 1)
        hole_locations.append((x, y, 0))

with BuildPart() as plate_bp:
    Box(
        PLATE_LENGTH,
        PLATE_WIDTH,
        PLATE_THICKNESS,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    with Locations(*hole_locations):
        Hole(radius=MOUNTING_HOLE_DIAMETER / 2, depth=PLATE_THICKNESS)
    try:
        fillet(plate_bp.edges().filter_by(Axis.Z), radius=FILLET_RADIUS)
    except Exception:
        pass

base_plate = plate_bp.part
base_plate.label = "base_plate"
base_plate.color = Color(0.55, 0.62, 0.70)

result = Compound(children=[base_plate])
"""


def _l_bracket_code(
    *,
    base_length: float,
    base_width: float,
    back_height: float,
    thickness: float,
    hole_diameter: float,
    rib_thickness: float,
    fillet_radius: float,
) -> str:
    rib_height = max(10.0, back_height - thickness)
    rib_length = max(10.0, base_width - thickness)
    rib_x = max(thickness * 2.0, base_length * 0.28)
    return f"""from build123d import *

BASE_LENGTH = {base_length:.3f}
BASE_WIDTH = {base_width:.3f}
BACK_HEIGHT = {back_height:.3f}
PLATE_THICKNESS = {thickness:.3f}
MOUNTING_HOLE_DIAMETER = {hole_diameter:.3f}
RIB_THICKNESS = {rib_thickness:.3f}
FILLET_RADIUS = {fillet_radius:.3f}

with BuildPart() as base_bp:
    Box(
        BASE_LENGTH,
        BASE_WIDTH,
        PLATE_THICKNESS,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    with Locations((-BASE_LENGTH * 0.30, 0, 0), (BASE_LENGTH * 0.30, 0, 0)):
        Hole(radius=MOUNTING_HOLE_DIAMETER / 2, depth=PLATE_THICKNESS)
    try:
        fillet(base_bp.edges().filter_by(Axis.Z), radius=FILLET_RADIUS)
    except Exception:
        pass
base_plate = base_bp.part
base_plate.label = "base_plate"
base_plate.color = Color(0.55, 0.62, 0.70)

with BuildPart() as back_bp:
    Box(
        BASE_LENGTH,
        PLATE_THICKNESS,
        BACK_HEIGHT,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    with Locations((-BASE_LENGTH * 0.30, 0, BACK_HEIGHT * 0.55), (BASE_LENGTH * 0.30, 0, BACK_HEIGHT * 0.55)):
        Hole(radius=MOUNTING_HOLE_DIAMETER / 2, depth=PLATE_THICKNESS)
    try:
        fillet(back_bp.edges().filter_by(Axis.Z), radius=FILLET_RADIUS)
    except Exception:
        pass
back_plate = back_bp.part.moved(Location((0, BASE_WIDTH / 2 - PLATE_THICKNESS / 2, PLATE_THICKNESS)))
back_plate.label = "back_plate"
back_plate.color = Color(0.55, 0.62, 0.70)

rib_1 = Box(
    RIB_THICKNESS,
    {rib_length:.3f},
    {rib_height:.3f},
    align=(Align.CENTER, Align.CENTER, Align.MIN),
).moved(Location((-{rib_x:.3f}, BASE_WIDTH / 2 - {rib_length:.3f} / 2, PLATE_THICKNESS)))
rib_1.label = "rib_1"
rib_1.color = Color(0.47, 0.55, 0.63)

rib_2 = Box(
    RIB_THICKNESS,
    {rib_length:.3f},
    {rib_height:.3f},
    align=(Align.CENTER, Align.CENTER, Align.MIN),
).moved(Location(({rib_x:.3f}, BASE_WIDTH / 2 - {rib_length:.3f} / 2, PLATE_THICKNESS)))
rib_2.label = "rib_2"
rib_2.color = Color(0.47, 0.55, 0.63)

result = Compound(children=[base_plate, back_plate, rib_1, rib_2])
"""


def _enclosure_code(
    *,
    length: float,
    width: float,
    height: float,
    wall_thickness: float,
    boss_diameter: float,
    screw_diameter: float,
    corner_radius: float,
) -> str:
    boss_margin = max(wall_thickness + boss_diameter * 0.65, min(length, width) * 0.16)
    boss_height = max(wall_thickness * 2.0, height - wall_thickness)
    return f"""from build123d import *

OUTER_LENGTH = {length:.3f}
OUTER_WIDTH = {width:.3f}
OUTER_HEIGHT = {height:.3f}
WALL_THICKNESS = {wall_thickness:.3f}
BOSS_DIAMETER = {boss_diameter:.3f}
SCREW_DIAMETER = {screw_diameter:.3f}
CORNER_RADIUS = {corner_radius:.3f}
BOSS_MARGIN = {boss_margin:.3f}

with BuildPart() as body_bp:
    Box(
        OUTER_LENGTH,
        OUTER_WIDTH,
        OUTER_HEIGHT,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    with Locations((0, 0, WALL_THICKNESS)):
        Box(
            OUTER_LENGTH - 2 * WALL_THICKNESS,
            OUTER_WIDTH - 2 * WALL_THICKNESS,
            OUTER_HEIGHT,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )
    try:
        fillet(body_bp.edges().filter_by(Axis.Z), radius=CORNER_RADIUS)
    except Exception:
        pass
wall_body = body_bp.part
wall_body.label = "wall_body"
wall_body.color = Color(0.42, 0.52, 0.62)

cover = Box(
    OUTER_LENGTH,
    OUTER_WIDTH,
    WALL_THICKNESS,
    align=(Align.CENTER, Align.CENTER, Align.MIN),
).moved(Location((0, 0, OUTER_HEIGHT + WALL_THICKNESS)))
cover.label = "cover"
cover.color = Color(0.55, 0.62, 0.70)

bosses = []
for index, (x, y) in enumerate([
    (-OUTER_LENGTH / 2 + BOSS_MARGIN, -OUTER_WIDTH / 2 + BOSS_MARGIN),
    ( OUTER_LENGTH / 2 - BOSS_MARGIN, -OUTER_WIDTH / 2 + BOSS_MARGIN),
    ( OUTER_LENGTH / 2 - BOSS_MARGIN,  OUTER_WIDTH / 2 - BOSS_MARGIN),
    (-OUTER_LENGTH / 2 + BOSS_MARGIN,  OUTER_WIDTH / 2 - BOSS_MARGIN),
], start=1):
    with BuildPart() as boss_bp:
        Cylinder(radius=BOSS_DIAMETER / 2, height={boss_height:.3f}, align=(Align.CENTER, Align.CENTER, Align.MIN))
        Hole(radius=SCREW_DIAMETER / 2, depth={boss_height:.3f})
    boss = boss_bp.part.moved(Location((x, y, WALL_THICKNESS)))
    boss.label = f"boss_{{index}}"
    boss.color = Color(0.50, 0.58, 0.66)
    bosses.append(boss)

result = Compound(children=[wall_body, cover, *bosses])
"""


def _bushing_code(
    *,
    outer_diameter: float,
    inner_diameter: float,
    length: float,
    chamfer_radius: float,
) -> str:
    return f"""from build123d import *

OUTER_DIAMETER = {outer_diameter:.3f}
INNER_DIAMETER = {inner_diameter:.3f}
BUSHING_LENGTH = {length:.3f}
CHAMFER_RADIUS = {chamfer_radius:.3f}

with BuildPart() as bushing_bp:
    Cylinder(
        radius=OUTER_DIAMETER / 2,
        height=BUSHING_LENGTH,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    Hole(radius=INNER_DIAMETER / 2, depth=BUSHING_LENGTH)
    try:
        chamfer(bushing_bp.edges().filter_by(GeomType.CIRCLE), length=CHAMFER_RADIUS)
    except Exception:
        pass

bushing = bushing_bp.part
bushing.label = "bushing"
bushing.color = Color(0.62, 0.64, 0.66)

result = Compound(children=[bushing])
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
        return _skill_output(
            SkillToolOutput(
                status="error",
                skill_name="cad.plan_build123d_skill",
                intent=message,
                brief="project_id is required.",
                fallback_recommendation="Select or create a project before planning CAD geometry.",
                rejection_reason="missing_project_id",
                code="missing_project_id",
            ),
            message="project_id is required.",
        )
    if not message:
        return _skill_output(
            SkillToolOutput(
                status="needs_clarification",
                skill_name="cad.plan_build123d_skill",
                question="What CAD part should be generated?",
                brief="The CAD request is empty.",
                rejection_reason="empty_request",
            )
        )

    if _is_bushing_request(message):
        dims = _dimension_values(message)
        outer_diameter = float(payload.get("outer_diameter_mm") or _tagged_value(message, _OD_RE) or (dims[0] if len(dims) >= 1 else 20.0))
        inner_diameter = float(payload.get("inner_diameter_mm") or _tagged_value(message, _ID_RE) or (dims[1] if len(dims) >= 2 else 8.0))
        length = float(payload.get("length_mm") or _tagged_value(message, _LENGTH_RE) or (dims[2] if len(dims) >= 3 else 30.0))
        wall_thickness = (outer_diameter - inner_diameter) / 2
        if inner_diameter <= 0 or outer_diameter <= 0 or length <= 0:
            return _skill_output(
                SkillToolOutput(
                    status="needs_clarification",
                    skill_name="cad.plan_build123d_skill",
                    intent=message,
                    brief="Bushing dimensions must all be positive.",
                    question="What positive outer diameter, inner diameter, and length should the bushing use?",
                    match_confidence=0.96,
                    matched_terms=["bushing/spacer/sleeve", "轴套/衬套/隔套"],
                    rejection_reason="non_positive_bushing_dimension",
                ),
                pattern="bushing",
            )
        if inner_diameter >= outer_diameter:
            return _skill_output(
                SkillToolOutput(
                    status="error",
                    skill_name="cad.plan_build123d_skill",
                    intent=message,
                    brief="Bushing inner diameter must be smaller than outer diameter.",
                    warnings=["Invalid OD/ID combination; no CAD code was generated."],
                    fallback_recommendation="Provide an inner diameter smaller than the outer diameter.",
                    rejection_reason="inner_diameter_not_smaller_than_outer_diameter",
                    code="invalid_bushing_dimensions",
                ),
                pattern="bushing",
            )
        warnings: list[str] = []
        if wall_thickness < 1.5:
            warnings.append("Bushing wall thickness is below 1.5mm; confirm manufacturing mode before executing.")
        chamfer_radius = float(payload.get("chamfer_radius_mm") or min(1.0, max(0.25, wall_thickness * 0.25)))
        code = _bushing_code(
            outer_diameter=outer_diameter,
            inner_diameter=inner_diameter,
            length=length,
            chamfer_radius=chamfer_radius,
        )
        proposed_input = {
            "project_id": project_id,
            "name": f"OD{outer_diameter:g}_ID{inner_diameter:g}_L{length:g}mm bushing",
            "code": code,
            "mode": "replace",
            "model_kind": "mechanical",
            "timeout": 60,
        }
        return _skill_output(
            SkillToolOutput(
                status="ready",
                skill_name="cad.plan_build123d_skill",
                intent=message,
                brief=(
                    f"Bushing/spacer: OD {outer_diameter:g}mm, ID {inner_diameter:g}mm, "
                    f"length {length:g}mm, wall {wall_thickness:g}mm."
                ),
                assumptions=[
                    f"Interpreted outer diameter as {outer_diameter:g}mm.",
                    f"Interpreted inner diameter as {inner_diameter:g}mm.",
                    f"Interpreted length as {length:g}mm.",
                    f"Derived wall thickness as {wall_thickness:g}mm.",
                ],
                warnings=warnings,
                proposed_tool="cad.execute_build123d",
                proposed_input=proposed_input,
                verification_targets=[
                    "bushing named part exists",
                    "INNER_DIAMETER remains smaller than OUTER_DIAMETER",
                    "wall thickness is at least the manufacturing default",
                    "cad.critique reports a single connected component",
                ],
                match_confidence=0.96,
                matched_terms=["bushing/spacer/sleeve", "轴套/衬套/隔套"],
            ),
            pattern="bushing",
        )

    if _is_enclosure_request(message):
        dims = _dimension_values(message)
        length = float(payload.get("length_mm") or (dims[0] if len(dims) >= 1 else 100.0))
        width = float(payload.get("width_mm") or (dims[1] if len(dims) >= 2 else 60.0))
        height = float(payload.get("height_mm") or (dims[2] if len(dims) >= 3 else 30.0))
        wall_thickness = float(payload.get("wall_thickness_mm") or _wall_thickness_value(message) or 3.0)
        boss_diameter = float(payload.get("boss_diameter_mm") or max(6.0, wall_thickness * 2.5))
        screw_diameter = float(payload.get("screw_diameter_mm") or 3.0)
        corner_radius = float(payload.get("corner_radius_mm") or min(4.0, max(1.0, wall_thickness)))
        warnings: list[str] = []
        if wall_thickness < 3.0:
            warnings.append("Wall thickness is below the 3mm CNC default; confirm manufacturing mode before executing.")
        if length <= 2 * wall_thickness or width <= 2 * wall_thickness or height <= wall_thickness:
            warnings.append("Wall thickness leaves no valid internal cavity; increase outer dimensions or reduce wall thickness.")

        code = _enclosure_code(
            length=length,
            width=width,
            height=height,
            wall_thickness=wall_thickness,
            boss_diameter=boss_diameter,
            screw_diameter=screw_diameter,
            corner_radius=corner_radius,
        )
        proposed_input = {
            "project_id": project_id,
            "name": f"{length:g}x{width:g}x{height:g}mm enclosure",
            "code": code,
            "mode": "replace",
            "model_kind": "mechanical",
            "timeout": 60,
        }
        return _skill_output(
            SkillToolOutput(
                status="ready",
                skill_name="cad.plan_build123d_skill",
                intent=message,
                brief=(
                    f"Electronics enclosure: {length:g}x{width:g}x{height:g}mm, "
                    f"{wall_thickness:g}mm walls, cover, four screw bosses."
                ),
                assumptions=[
                    f"Interpreted outer dimensions as {length:g}x{width:g}x{height:g}mm.",
                    f"Defaulted wall thickness to {wall_thickness:g}mm.",
                    f"Defaulted boss diameter to {boss_diameter:g}mm and screw bore to {screw_diameter:g}mm.",
                    "Included a separate cover above the open box body.",
                ],
                warnings=warnings,
                proposed_tool="cad.execute_build123d",
                proposed_input=proposed_input,
                verification_targets=[
                    "wall_body named part exists",
                    "cover named part exists",
                    "boss_1 through boss_4 named parts exist",
                    "wall thickness is surfaced as WALL_THICKNESS",
                    "cad.critique checks wall thickness and floating components",
                ],
                match_confidence=0.94,
                matched_terms=["enclosure/case", "外壳/盒子"],
            ),
            pattern="enclosure",
        )

    if _is_l_bracket_request(message):
        dims = _dimension_values(message)
        base_length = float(payload.get("base_length_mm") or (dims[0] if len(dims) >= 1 else 80.0))
        base_width = float(payload.get("base_width_mm") or (dims[1] if len(dims) >= 2 else 40.0))
        back_height = float(payload.get("back_height_mm") or _height_value(message) or 60.0)
        thickness = float(payload.get("thickness_mm") or 6.0)
        hole_diameter = float(payload.get("hole_diameter_mm") or _hole_diameter(message, 5.0))
        rib_thickness = float(payload.get("rib_thickness_mm") or max(3.0, thickness))
        fillet_radius = float(payload.get("fillet_radius_mm") or min(2.0, max(0.5, thickness * 0.25)))
        warnings: list[str] = []
        if thickness < 3.0 or rib_thickness < 3.0:
            warnings.append("Bracket thickness is below the 3mm CNC default; confirm manufacturing mode before executing.")
        if base_length * 0.20 < hole_diameter:
            warnings.append("Hole edge distance may be below the 2x radius rule; increase base length or reduce hole diameter.")

        code = _l_bracket_code(
            base_length=base_length,
            base_width=base_width,
            back_height=back_height,
            thickness=thickness,
            hole_diameter=hole_diameter,
            rib_thickness=rib_thickness,
            fillet_radius=fillet_radius,
        )
        proposed_input = {
            "project_id": project_id,
            "name": f"{base_length:g}x{base_width:g}x{back_height:g}mm L bracket",
            "code": code,
            "mode": "replace",
            "model_kind": "mechanical",
            "timeout": 60,
        }
        return _skill_output(
            SkillToolOutput(
                status="ready",
                skill_name="cad.plan_build123d_skill",
                intent=message,
                brief=(
                    f"L bracket: base {base_length:g}x{base_width:g}mm, back height "
                    f"{back_height:g}mm, {thickness:g}mm plates, {hole_diameter:g}mm holes, two ribs."
                ),
                assumptions=[
                    f"Interpreted base plate as {base_length:g}x{base_width:g}mm.",
                    f"Defaulted vertical back plate height to {back_height:g}mm.",
                    f"Defaulted plate thickness to {thickness:g}mm.",
                    f"Defaulted hole diameter to {hole_diameter:g}mm.",
                    "Included two ribs for stiffness.",
                ],
                warnings=warnings,
                proposed_tool="cad.execute_build123d",
                proposed_input=proposed_input,
                verification_targets=[
                    "base_plate named part exists",
                    "back_plate named part exists",
                    "rib_1 and rib_2 named parts exist",
                    "cad.critique checks wall thickness and hole-edge distance",
                ],
                match_confidence=0.95,
                matched_terms=["L bracket/angle bracket", "L型支架/角码"],
            ),
            pattern="l_bracket",
        )

    if _is_mounting_plate_request(message):
        dims = _dimension_values(message)
        length = float(payload.get("length_mm") or (dims[0] if len(dims) >= 1 else 100.0))
        width = float(payload.get("width_mm") or (dims[1] if len(dims) >= 2 else 60.0))
        thickness = float(payload.get("thickness_mm") or (dims[2] if len(dims) >= 3 else 8.0))
        hole_count = int(payload.get("hole_count") or _bolt_hole_count(message))
        count_x = int(payload.get("mounting_hole_count_x") or _hole_grid_counts(hole_count)[0])
        count_y = int(payload.get("mounting_hole_count_y") or _hole_grid_counts(hole_count)[1])
        hole_diameter = float(payload.get("hole_diameter_mm") or _hole_diameter(message, 6.0))
        min_margin = hole_diameter
        margin_x = float(payload.get("edge_margin_x_mm") or max(min_margin, round(length * 0.18, 1)))
        margin_y = float(payload.get("edge_margin_y_mm") or max(min_margin, round(width * 0.18, 1)))
        fillet_radius = float(payload.get("fillet_radius_mm") or min(2.0, max(0.5, thickness * 0.25)))

        warnings: list[str] = []
        if thickness < 3.0:
            warnings.append("Plate thickness is below the 3mm CNC default; confirm manufacturing mode before executing.")
        if margin_x < min_margin or margin_y < min_margin:
            warnings.append("Hole edge margin is below the 2x radius rule; increase edge margins or reduce hole diameter.")

        code = _mounting_plate_code(
            length=length,
            width=width,
            thickness=thickness,
            hole_diameter=hole_diameter,
            count_x=count_x,
            count_y=count_y,
            margin_x=margin_x,
            margin_y=margin_y,
            fillet_radius=fillet_radius,
        )
        proposed_input = {
            "project_id": project_id,
            "name": f"{length:g}x{width:g}x{thickness:g}mm mounting plate",
            "code": code,
            "mode": "replace",
            "model_kind": "mechanical",
            "timeout": 60,
        }
        return _skill_output(
            SkillToolOutput(
                status="ready",
                skill_name="cad.plan_build123d_skill",
                intent=message,
                brief=(
                    f"Mounting plate: {length:g}x{width:g}x{thickness:g}mm with "
                    f"{count_x}x{count_y} through holes, {hole_diameter:g}mm diameter."
                ),
                assumptions=[
                    f"Interpreted dimensions as length {length:g}mm, width {width:g}mm, thickness {thickness:g}mm.",
                    f"Defaulted rectangular hole grid to {count_x} by {count_y}.",
                    f"Defaulted hole diameter to {hole_diameter:g}mm.",
                    f"Defaulted hole edge margins to {margin_x:g}mm x {margin_y:g}mm.",
                ],
                warnings=warnings,
                proposed_tool="cad.execute_build123d",
                proposed_input=proposed_input,
                verification_targets=[
                    "base_plate named part exists",
                    "mounting holes are through-holes",
                    "hole-edge distance satisfies the 2x radius rule",
                    "cad.critique reports no floating components",
                ],
                match_confidence=0.94,
                matched_terms=["mounting plate/base plate", "安装板"],
            ),
            pattern="mounting_plate",
        )

    if not _is_flange_request(message):
        fallback = (
            "Use cad.get_source followed by agent-authored cad.execute_build123d "
            "for this request, or add a new deterministic CAD skill template."
        )
        return _skill_output(
            SkillToolOutput(
                status="unsupported",
                skill_name="cad.plan_build123d_skill",
                intent=message,
                brief="No deterministic CAD skill template matched this request.",
                fallback_recommendation=fallback,
                match_confidence=0.0,
                matched_terms=[],
                rejection_reason="no_supported_template_matched",
            ),
            supported_patterns=["flange / 法兰盘"],
            recommendation=fallback,
        )

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
    return _skill_output(
        SkillToolOutput(
            status="ready",
            skill_name="cad.plan_build123d_skill",
            intent=message,
            brief=(
                f"Mechanical flange: OD {outer_diameter:g}mm, thickness {thickness:g}mm, "
                f"center bore {center_bore:g}mm, {bolt_hole_count}x {bolt_hole_diameter:g}mm "
                f"bolt holes on {bolt_circle:g}mm PCD."
            ),
            assumptions=assumptions,
            warnings=warnings,
            proposed_tool="cad.execute_build123d",
            proposed_input=execute_input,
            verification_targets=[
                "base_plate named part exists",
                "mounting holes are through-holes",
                "cad.critique passes edge-distance and geometry sanity checks",
            ],
            match_confidence=0.96,
            matched_terms=["flange", "法兰"],
        ),
        pattern="flange",
    )


__all__ = ["plan_build123d_skill"]
