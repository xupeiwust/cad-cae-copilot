"""Standard bearings — deep-groove ball, thrust ball — as Shape IR nodes."""
from __future__ import annotations

from typing import Any


def _bearing_metadata(
    standard_name: str,
    standard_reference: str,
    part_category: str,
    editable_parameters: list[str],
) -> dict[str, Any]:
    return {
        "standard_name": standard_name,
        "standard_reference": standard_reference,
        "part_category": part_category,
        "editable_parameters": editable_parameters,
    }


# ── presets ─────────────────────────────────────────────────────────────────

DEEP_GROOVE_BALL_BEARING_PRESETS: dict[str, dict[str, float]] = {
    "6200": {"bore": 10.0, "outer_diameter": 30.0, "width": 9.0},
    "6201": {"bore": 12.0, "outer_diameter": 32.0, "width": 10.0},
    "6202": {"bore": 15.0, "outer_diameter": 35.0, "width": 11.0},
    "6203": {"bore": 17.0, "outer_diameter": 40.0, "width": 12.0},
    "6204": {"bore": 20.0, "outer_diameter": 47.0, "width": 14.0},
    "6205": {"bore": 25.0, "outer_diameter": 52.0, "width": 15.0},
}

THRUST_BALL_BEARING_PRESETS: dict[str, dict[str, float]] = {
    "51100": {"bore": 10.0, "outer_diameter": 24.0, "height": 9.0},
    "51101": {"bore": 12.0, "outer_diameter": 26.0, "height": 9.0},
    "51102": {"bore": 15.0, "outer_diameter": 28.0, "height": 9.0},
    "51103": {"bore": 17.0, "outer_diameter": 30.0, "height": 9.0},
    "51104": {"bore": 20.0, "outer_diameter": 35.0, "height": 10.0},
    "51105": {"bore": 25.0, "outer_diameter": 42.0, "height": 11.0},
}


# ── generators ──────────────────────────────────────────────────────────────

def deep_groove_ball_bearing(
    bore: float = 20.0,
    outer_diameter: float = 47.0,
    width: float = 14.0,
    dynamic_load_rating: float | None = None,
    static_load_rating: float | None = None,
) -> dict[str, Any]:
    """Return a Shape IR node for a deep-groove ball bearing (ISO 15 / DIN 625).

    Modelled as an outer ring (hollow cylinder) plus an inner ring,
    with a spherical ball row represented semantically.  The exact
    raceway geometry is omitted for the primitive-level IR; the
    compiler will produce a torus-section ring if a NURBS backend
    is available.
    """
    outer_radius = outer_diameter / 2.0
    inner_radius = bore / 2.0
    mid_radius = (outer_radius + inner_radius) / 2.0
    ring_thickness = (outer_radius - inner_radius) / 2.0

    outer_ring = {
        "id": "outer_ring",
        "primitive": "cylinder",
        "radius": outer_radius,
        "height": width,
        "location": [0.0, 0.0, 0.0],
    }
    inner_ring_hole = {
        "id": "inner_ring_hole",
        "primitive": "cylinder",
        "radius": mid_radius,
        "height": width + 0.1,
        "location": [0.0, 0.0, -0.05],
    }
    outer_ring_node = {
        "id": "outer_ring_diff",
        "operation": "difference",
        "children": [outer_ring, inner_ring_hole],
    }

    inner_ring = {
        "id": "inner_ring",
        "primitive": "cylinder",
        "radius": mid_radius - 0.5,
        "height": width,
        "location": [0.0, 0.0, 0.0],
    }
    bore_hole = {
        "id": "bore_hole",
        "primitive": "cylinder",
        "radius": inner_radius,
        "height": width + 0.1,
        "location": [0.0, 0.0, -0.05],
    }
    inner_ring_node = {
        "id": "inner_ring_diff",
        "operation": "difference",
        "children": [inner_ring, bore_hole],
    }

    params: dict[str, Any] = {
        "bore": bore,
        "outer_diameter": outer_diameter,
        "width": width,
    }
    if dynamic_load_rating is not None:
        params["dynamic_load_rating"] = dynamic_load_rating
    if static_load_rating is not None:
        params["static_load_rating"] = static_load_rating

    return {
        "id": "deep_groove_ball_bearing",
        "name": "Deep Groove Ball Bearing",
        "operation": "union",
        "children": [outer_ring_node, inner_ring_node],
        "parameters": params,
        "metadata": _bearing_metadata(
            standard_name="Deep groove ball bearing",
            standard_reference="ISO 15 / DIN 625",
            part_category="bearing",
            editable_parameters=["bore", "outer_diameter", "width"],
        ),
    }


def thrust_ball_bearing(
    bore: float = 20.0,
    outer_diameter: float = 35.0,
    height: float = 10.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a thrust ball bearing (ISO 104 / DIN 711).

    Modelled as two washer-like rings (top and bottom) separated by
    the bearing height.  The ball cage is represented semantically.
    """
    outer_radius = outer_diameter / 2.0
    inner_radius = bore / 2.0
    half_height = height / 2.0
    ring_thickness = half_height * 0.4

    bottom_ring = {
        "id": "bottom_ring",
        "primitive": "cylinder",
        "radius": outer_radius,
        "height": ring_thickness,
        "location": [0.0, 0.0, 0.0],
    }
    bottom_hole = {
        "id": "bottom_hole",
        "primitive": "cylinder",
        "radius": inner_radius,
        "height": ring_thickness + 0.1,
        "location": [0.0, 0.0, -0.05],
    }
    bottom = {
        "id": "bottom",
        "operation": "difference",
        "children": [bottom_ring, bottom_hole],
    }

    top_ring = {
        "id": "top_ring",
        "primitive": "cylinder",
        "radius": outer_radius,
        "height": ring_thickness,
        "location": [0.0, 0.0, height - ring_thickness],
    }
    top_hole = {
        "id": "top_hole",
        "primitive": "cylinder",
        "radius": inner_radius,
        "height": ring_thickness + 0.1,
        "location": [0.0, 0.0, height - ring_thickness - 0.05],
    }
    top = {
        "id": "top",
        "operation": "difference",
        "children": [top_ring, top_hole],
    }

    return {
        "id": "thrust_ball_bearing",
        "name": "Thrust Ball Bearing",
        "operation": "union",
        "children": [bottom, top],
        "parameters": {
            "bore": bore,
            "outer_diameter": outer_diameter,
            "height": height,
        },
        "metadata": _bearing_metadata(
            standard_name="Thrust ball bearing",
            standard_reference="ISO 104 / DIN 711",
            part_category="bearing",
            editable_parameters=["bore", "outer_diameter", "height"],
        ),
    }
