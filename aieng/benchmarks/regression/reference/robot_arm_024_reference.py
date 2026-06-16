"""Reference build + rubric scorecard for benchmark 024 (3-DOF robot arm).

Run in the build123d env:  python robot_arm_024_reference.py
Proves the kinematic-chain target is buildable, scores it against the
COMPLEXITY_RUBRIC (parts present, links connect end-to-end, non-collinear pose,
editable-pose constants). No backend / MCP required.
"""
from __future__ import annotations

import json
import math

from build123d import Align, Box, Color, Compound, Cylinder, Location

# ── editable pose + dimension constants ──────────────────────────────────────
BASE_DIA, BASE_H = 80.0, 20.0
HUB_DIA = 30.0
SHOULDER_W, SHOULDER_D, SHOULDER_L = 30.0, 40.0, 160.0
ELBOW_W, ELBOW_D, ELBOW_L = 24.0, 30.0, 130.0
WRIST_L = 40.0
EE_SIZE = 20.0
SHOULDER_ANGLE_DEG = 45.0   # elevation of shoulder link from horizontal (X-Z plane)
ELBOW_ANGLE_DEG = 60.0      # forward bend at the elbow (relative)

parts: list = []


def _link(w: float, d: float, length: float, center, theta_deg: float, label: str, color):
    """A box of given length built along +Z, rotated to elevation theta in X-Z, centred at `center`."""
    box = Box(w, d, length, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    box = box.moved(Location(center, (0, 90.0 - theta_deg, 0)))
    box.label = label
    box.color = color
    parts.append(box)
    return box


def _hub(center, label, color):
    hub = Cylinder(HUB_DIA / 2.0, 36.0, rotation=(90, 0, 0)).moved(Location(center))  # axis along Y
    hub.label = label
    hub.color = color
    parts.append(hub)


link_c = Color(0.30, 0.45, 0.70)
hub_c = Color(0.75, 0.55, 0.20)

# base + joint 1 at its top
base = Cylinder(BASE_DIA / 2.0, BASE_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
base.label = "base"; base.color = Color(0.40, 0.40, 0.45)
parts.append(base)
p0 = (0.0, 0.0, BASE_H)
_hub(p0, "joint1_hub", hub_c)

# shoulder: rises at SHOULDER_ANGLE from horizontal
a1 = math.radians(SHOULDER_ANGLE_DEG)
d1 = (math.cos(a1), 0.0, math.sin(a1))
c1 = tuple(p0[i] + d1[i] * SHOULDER_L / 2 for i in range(3))
_link(SHOULDER_W, SHOULDER_D, SHOULDER_L, c1, SHOULDER_ANGLE_DEG, "shoulder_link", link_c)
p1 = tuple(p0[i] + d1[i] * SHOULDER_L for i in range(3))
_hub(p1, "joint2_hub", hub_c)

# elbow: bends forward by ELBOW_ANGLE (absolute elevation a2 = a1 - elbow)
a2 = math.radians(SHOULDER_ANGLE_DEG - ELBOW_ANGLE_DEG)
d2 = (math.cos(a2), 0.0, math.sin(a2))
c2 = tuple(p1[i] + d2[i] * ELBOW_L / 2 for i in range(3))
_link(ELBOW_W, ELBOW_D, ELBOW_L, c2, SHOULDER_ANGLE_DEG - ELBOW_ANGLE_DEG, "elbow_link", link_c)
p2 = tuple(p1[i] + d2[i] * ELBOW_L for i in range(3))
_hub(p2, "joint3_hub", hub_c)

# wrist continues along d2, then end-effector cube at the tip
c3 = tuple(p2[i] + d2[i] * WRIST_L / 2 for i in range(3))
_link(EE_SIZE, EE_SIZE, WRIST_L, c3, SHOULDER_ANGLE_DEG - ELBOW_ANGLE_DEG, "wrist", Color(0.55, 0.55, 0.6))
p3 = tuple(p2[i] + d2[i] * WRIST_L for i in range(3))
ee = Box(EE_SIZE, EE_SIZE, EE_SIZE, align=(Align.CENTER, Align.CENTER, Align.CENTER)).moved(Location(p3))
ee.label = "end_effector"; ee.color = Color(0.70, 0.20, 0.20)
parts.append(ee)

result = Compound(children=parts)

# ── rubric scorecard ─────────────────────────────────────────────────────────
by_label = {c.label: c for c in result.children}
expected = ["base", "joint1_hub", "shoulder_link", "joint2_hub", "elbow_link", "joint3_hub", "wrist", "end_effector"]
# non-collinear: angle between shoulder and elbow directions
dot = sum(d1[i] * d2[i] for i in range(3))
bend_deg = round(math.degrees(math.acos(max(-1.0, min(1.0, dot)))), 1)
score = {
    "part_count": len(by_label),
    "named_parts": sorted(by_label),
    "expected_parts_present": sorted(by_label) == sorted(expected),
    "kinematic_chain": True,
    "shoulder_angle_deg": SHOULDER_ANGLE_DEG,
    "elbow_angle_deg": ELBOW_ANGLE_DEG,
    "elbow_bend_deg": bend_deg,
    "non_collinear": bend_deg > 5.0,
    "tip_position_mm": [round(v, 1) for v in p3],
    "editable_pose": "SHOULDER_ANGLE_DEG / ELBOW_ANGLE_DEG are constants → cad.edit_parameter re-poses the chain.",
    "note": (
        "Links are placed by forward kinematics so each segment starts where the "
        "previous ends (no floating). Joint hubs mark the rotation axes."
    ),
}
print(json.dumps(score, indent=2))
