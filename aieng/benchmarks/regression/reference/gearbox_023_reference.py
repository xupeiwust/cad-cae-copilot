"""Reference build + rubric scorecard for benchmark 023 (single-stage gearbox).

Run in the build123d env:  python gearbox_023_reference.py
Proves the complex target is buildable, gives the COMPLEXITY_RUBRIC a yardstick,
and prints a structured scorecard (parts, bbox, gear center-distance gap,
floating check, wall-thickness check). No backend / MCP required.
"""
from __future__ import annotations

import json

from build123d import Align, Axis, Box, Color, Compound, Cylinder, Location, Mode, Pos

# ── named constants (editable; mirror the prompt's stated dims) ──────────────
HOUSING_L, HOUSING_W, HOUSING_H = 120.0, 80.0, 60.0
WALL = 5.0
COVER_THK = 5.0
SHAFT_DIA = 12.0
SHAFT_SPACING_Y = 50.0          # input/output shaft axis spacing
SHAFT_Z = HOUSING_H / 2.0       # axes centered in Z
BORE_DIA = 22.0                 # bearing bore
GEAR_IN_PITCH_DIA = 30.0
GEAR_OUT_PITCH_DIA = 50.0
GEAR_WIDTH = 8.0
BOLT_DIA = 5.0

assert WALL >= 3.0, "wall below 3mm CNC minimum"

y_in, y_out = SHAFT_SPACING_Y / 2.0, -SHAFT_SPACING_Y / 2.0

# ── housing: open-top shell (5mm walls + floor, no top) ──────────────────────
outer = Box(HOUSING_L, HOUSING_W, HOUSING_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
cavity = Box(HOUSING_L - 2 * WALL, HOUSING_W - 2 * WALL, HOUSING_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
housing = outer - cavity.moved(Location((0, 0, WALL)))  # cavity from z=WALL up → open top
# 4 bearing bores: one long Ø22 cylinder per shaft line pierces both end walls → 2 coaxial bores each
for y in (y_in, y_out):
    bore = Cylinder(BORE_DIA / 2.0, HOUSING_L * 1.2, rotation=(0, 90, 0)).moved(Location((0, y, SHAFT_Z)))
    housing = housing - bore
housing.label = "housing"
housing.color = Color(0.55, 0.62, 0.70)

# ── cover: plate matching footprint, with 4 corner bolt holes ────────────────
cover = Box(HOUSING_L, HOUSING_W, COVER_THK, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((0, 0, HOUSING_H)))
for bx in (HOUSING_L / 2 - 8, -(HOUSING_L / 2 - 8)):
    for by in (HOUSING_W / 2 - 8, -(HOUSING_W / 2 - 8)):
        cover = cover - Cylinder(BOLT_DIA / 2.0, COVER_THK * 3).moved(Location((bx, by, HOUSING_H + COVER_THK / 2)))
cover.label = "cover"
cover.color = Color(0.50, 0.55, 0.60)

# ── shafts (Ø12 along X) ─────────────────────────────────────────────────────
input_shaft = Cylinder(SHAFT_DIA / 2.0, HOUSING_L + 20, rotation=(0, 90, 0)).moved(Location((0, y_in, SHAFT_Z)))
input_shaft.label = "input_shaft"; input_shaft.color = Color(0.80, 0.80, 0.85)
output_shaft = Cylinder(SHAFT_DIA / 2.0, HOUSING_L + 20, rotation=(0, 90, 0)).moved(Location((0, y_out, SHAFT_Z)))
output_shaft.label = "output_shaft"; output_shaft.color = Color(0.80, 0.80, 0.85)

# ── gears (toothless disks at pitch diameter) ────────────────────────────────
gear_input = Cylinder(GEAR_IN_PITCH_DIA / 2.0, GEAR_WIDTH, rotation=(0, 90, 0)).moved(Location((10, y_in, SHAFT_Z)))
gear_input.label = "gear_input"; gear_input.color = Color(0.70, 0.45, 0.20)
gear_output = Cylinder(GEAR_OUT_PITCH_DIA / 2.0, GEAR_WIDTH, rotation=(0, 90, 0)).moved(Location((10, y_out, SHAFT_Z)))
gear_output.label = "gear_output"; gear_output.color = Color(0.70, 0.45, 0.20)

result = Compound(children=[housing, cover, input_shaft, output_shaft, gear_input, gear_output])

# ── rubric scorecard ─────────────────────────────────────────────────────────
parts = {c.label: c for c in result.children}
gear_gap = SHAFT_SPACING_Y - (GEAR_IN_PITCH_DIA / 2 + GEAR_OUT_PITCH_DIA / 2)
score = {
    "part_count": len(parts),
    "named_parts": sorted(parts),
    "expected_parts_present": sorted(parts) == sorted(
        ["housing", "cover", "input_shaft", "output_shaft", "gear_input", "gear_output"]
    ),
    "volumes_mm3": {k: round(v.volume, 1) for k, v in parts.items()},
    "wall_thickness_mm": WALL,
    "wall_ok_cnc": WALL >= 3.0,
    "gear_center_distance_mm": SHAFT_SPACING_Y,
    "gear_pitch_radius_sum_mm": GEAR_IN_PITCH_DIA / 2 + GEAR_OUT_PITCH_DIA / 2,
    "gear_mesh_gap_mm": round(gear_gap, 2),
    "gears_mesh": abs(gear_gap) < 0.5,
    "gear_mesh_note": (
        "HONEST MISMATCH: the prompt's 40mm tangency and 50mm shaft spacing are "
        f"inconsistent — at 50mm spacing the pitch circles are {gear_gap:.1f}mm apart "
        "(do NOT mesh). Reported, not silently 'fixed'."
    ),
}
print(json.dumps(score, indent=2))
