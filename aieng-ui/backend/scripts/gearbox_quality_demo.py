"""Modeling-quality demo: the SAME gearbox, crude vs scaffolded, scored by the
deterministic modeling-fidelity check.

Proves the lever-1 (fidelity feedback) + lever-2 (scaffold helpers) work converts
a crude primitive-stack into a designed part with a measurable score delta.

Run from aieng-ui/backend:  conda run -n aieng311 python scripts/gearbox_quality_demo.py
No backend / MCP required — it drives the real build + critique pipeline in-process.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.cad_generation import design_review, execute_build123d_code
from app.config import Settings

_WS = Path(__file__).resolve().parents[3]

CRUDE = """
from build123d import *
# raw Box-Box gearbox — the original crude build
outer = Box(120, 80, 60, align=(Align.CENTER, Align.CENTER, Align.MIN))
cavity = Box(110, 70, 60, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((0, 0, 5)))
housing_b = outer - cavity
for y in (25, -25):
    housing_b -= Cylinder(11, 150, rotation=(0, 90, 0)).moved(Location((0, y, 30)))
housing_b.label = "housing"
cover = Box(120, 80, 5, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(Location((0, 0, 60)))
cover.label = "cover"
gi = Cylinder(15, 8, rotation=(0, 90, 0)).moved(Location((10, 25, 30))); gi.label = "gear_input"
go = Cylinder(25, 8, rotation=(0, 90, 0)).moved(Location((10, -25, 30))); go.label = "gear_output"
result = Compound(children=[housing_b, cover, gi, go])
"""

DESIGNED = """
from build123d import *
WALL = 5.0
body = housing(120, 80, 60, wall=WALL, label="housing"); body.color = Color(0.55, 0.62, 0.70)
cover = rounded_box(120, 80, 6, radius=4).moved(Location((0, 0, 60))); cover.label = "cover"; cover.color = Color(0.50, 0.55, 0.60)
seats = []
for sx in (55, -55):
    for sy in (25, -25):
        s = boss(26, 6, hole_dia=22, axis="X").moved(Location((sx, sy, 30)))
        s.label = "bearing_seat_%s_%s" % ("R" if sx > 0 else "L", "in" if sy > 0 else "out")
        s.color = Color(0.60, 0.66, 0.72); seats.append(s)
ish = Cylinder(6, 150, rotation=(0, 90, 0)).moved(Location((0, 25, 30))); ish.label = "input_shaft"; ish.color = Color(0.80, 0.80, 0.85)
osh = Cylinder(6, 150, rotation=(0, 90, 0)).moved(Location((0, -25, 30))); osh.label = "output_shaft"; osh.color = Color(0.80, 0.80, 0.85)
gi = Cylinder(15, 8, rotation=(0, 90, 0)).moved(Location((10, 25, 30))); gi.label = "gear_input"; gi.color = Color(0.70, 0.45, 0.20)
go = Cylinder(25, 8, rotation=(0, 90, 0)).moved(Location((10, -25, 30))); go.label = "gear_output"; go.color = Color(0.70, 0.45, 0.20)
ribs = []
for i, sx in enumerate((60, -60)):
    r = rib(18, 28, 5).moved(Location((sx, 0, 0))); r.label = "rib_%d" % (i + 1); r.color = Color(0.45, 0.55, 0.50); ribs.append(r)
feet = []
for fx in (60, -60):
    for fy in (34, -34):
        f = mounting_tab(24, 18, 6, 5).moved(Location((fx, fy, 0)))
        f.label = "foot_%s%s" % ("R" if fx > 0 else "L", "F" if fy > 0 else "B"); f.color = Color(0.50, 0.50, 0.55); feet.append(f)
result = Compound(children=[body, cover, *seats, ish, osh, gi, go, *ribs, *feet])
"""


def _score(settings: Settings, name: str, code: str) -> dict:
    from app.main import default_project, save_project

    pid = save_project(settings, default_project(name))["id"]
    out = execute_build123d_code(settings, pid, {"code": code, "thumbnail": False})
    if out.get("status") != "ok":
        return {"name": name, "status": out.get("status"), "error": out.get("error") or out.get("message")}
    rev = design_review(settings, pid, {})
    fid = rev.get("fidelity", {})
    return {
        "name": name,
        "status": "ok",
        "part_count": len(out.get("named_parts", [])),
        "fidelity_level": fid.get("level"),
        "fidelity_score": fid.get("score"),
        "signals": fid.get("signals"),
        "findings": [f"{f['rule']}: {f['feature']}" for f in fid.get("findings", [])],
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        settings = Settings(
            platform_root=tmp / "platform", workspace_root=tmp / "ws",
            data_root=tmp / "data", aieng_root=_WS / "aieng", sample_step=tmp / "ws" / "s.step",
        )
        crude = _score(settings, "gearbox-crude", CRUDE)
        designed = _score(settings, "gearbox-designed", DESIGNED)
    print(json.dumps({"crude": crude, "designed": designed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
