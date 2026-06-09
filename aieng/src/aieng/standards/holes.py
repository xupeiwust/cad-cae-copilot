"""Standard hole types — through, blind, countersunk, counterbored, tapped — as Shape IR nodes.

These nodes are intended to be used in ``difference`` operations against a
parent solid (plate, bracket, etc.).  Each function returns a single Shape IR
node that represents the *volume to remove*.
"""
from __future__ import annotations

from typing import Any

import math


def _hole_metadata(
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


# ── generators ──────────────────────────────────────────────────────────────

def through_hole(
    diameter: float = 8.0,
    depth: float = 10.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a through-hole (ISO 273 / DIN 7).

    A simple cylinder oriented along +Z.  Subtract this from a solid to create
    the hole.
    """
    return {
        "id": "through_hole",
        "name": "Through Hole",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": depth,
        "location": [0.0, 0.0, depth / 2.0],
        "parameters": {
            "diameter": diameter,
            "depth": depth,
        },
        "metadata": _hole_metadata(
            standard_name="Through hole",
            standard_reference="ISO 273 / DIN 7",
            part_category="hole",
            editable_parameters=["diameter", "depth"],
        ),
    }


def blind_hole(
    diameter: float = 8.0,
    depth: float = 10.0,
    bottom_angle: float = 118.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a blind hole with a conical bottom (ISO 273).

    Modelled as a cylinder plus a cone tip at the bottom.  The cone angle
    defaults to 118° (standard drill point).
    """
    radius = diameter / 2.0
    cone_height = radius / math.tan(math.radians(bottom_angle / 2.0))
    cylinder = {
        "id": "cylinder",
        "primitive": "cylinder",
        "radius": radius,
        "height": depth - cone_height,
        "location": [0.0, 0.0, (depth - cone_height) / 2.0],
    }
    cone = {
        "id": "cone_tip",
        "primitive": "cone",
        "bottom_radius": radius,
        "top_radius": 0.0,
        "height": cone_height,
        "location": [0.0, 0.0, depth - cone_height + cone_height / 2.0],
    }
    return {
        "id": "blind_hole",
        "name": "Blind Hole",
        "operation": "union",
        "children": [cylinder, cone],
        "parameters": {
            "diameter": diameter,
            "depth": depth,
            "bottom_angle": bottom_angle,
        },
        "metadata": _hole_metadata(
            standard_name="Blind hole",
            standard_reference="ISO 273",
            part_category="hole",
            editable_parameters=["diameter", "depth", "bottom_angle"],
        ),
    }


def countersunk_hole(
    diameter: float = 8.0,
    depth: float = 10.0,
    countersink_diameter: float = 16.0,
    countersink_angle: float = 90.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a countersunk hole (ISO 7721 / DIN 974).

    Modelled as a main cylinder plus a frustum (truncated cone) at the top.
    """
    radius = diameter / 2.0
    cs_radius = countersink_diameter / 2.0
    cs_height = (cs_radius - radius) / math.tan(math.radians(countersink_angle / 2.0))
    cs_height = min(cs_height, depth * 0.5)

    main = {
        "id": "main",
        "primitive": "cylinder",
        "radius": radius,
        "height": depth,
        "location": [0.0, 0.0, depth / 2.0],
    }
    frustum = {
        "id": "countersink",
        "primitive": "cone",
        "bottom_radius": cs_radius,
        "top_radius": radius,
        "height": cs_height,
        "location": [0.0, 0.0, depth - cs_height / 2.0],
    }
    return {
        "id": "countersunk_hole",
        "name": "Countersunk Hole",
        "operation": "union",
        "children": [main, frustum],
        "parameters": {
            "diameter": diameter,
            "depth": depth,
            "countersink_diameter": countersink_diameter,
            "countersink_angle": countersink_angle,
        },
        "metadata": _hole_metadata(
            standard_name="Countersunk hole",
            standard_reference="ISO 7721 / DIN 974",
            part_category="hole",
            editable_parameters=["diameter", "depth", "countersink_diameter", "countersink_angle"],
        ),
    }


def counterbored_hole(
    diameter: float = 8.0,
    depth: float = 10.0,
    counterbore_diameter: float = 16.0,
    counterbore_depth: float = 4.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a counterbored hole (ISO 7379 / DIN 974).

    Modelled as a main cylinder plus a larger shallow cylinder at the top.
    """
    main = {
        "id": "main",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": depth,
        "location": [0.0, 0.0, depth / 2.0],
    }
    bore = {
        "id": "counterbore",
        "primitive": "cylinder",
        "radius": counterbore_diameter / 2.0,
        "height": counterbore_depth,
        "location": [0.0, 0.0, depth - counterbore_depth / 2.0],
    }
    return {
        "id": "counterbored_hole",
        "name": "Counterbored Hole",
        "operation": "union",
        "children": [main, bore],
        "parameters": {
            "diameter": diameter,
            "depth": depth,
            "counterbore_diameter": counterbore_diameter,
            "counterbore_depth": counterbore_depth,
        },
        "metadata": _hole_metadata(
            standard_name="Counterbored hole",
            standard_reference="ISO 7379 / DIN 974",
            part_category="hole",
            editable_parameters=[
                "diameter",
                "depth",
                "counterbore_diameter",
                "counterbore_depth",
            ],
        ),
    }


def tapped_hole(
    diameter: float = 8.0,
    depth: float = 10.0,
    thread_pitch: float = 1.25,
    thread_depth: float | None = None,
) -> dict[str, Any]:
    """Return a Shape IR node for a tapped (threaded) hole (ISO 965 / DIN 13).

    Modelled as a plain cylinder; the thread is represented semantically in
    metadata.  Exact helical thread geometry can be added by a future
    refinement using a swept helix primitive.
    """
    if thread_depth is None:
        thread_depth = depth * 0.8
    return {
        "id": "tapped_hole",
        "name": "Tapped Hole",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": depth,
        "location": [0.0, 0.0, depth / 2.0],
        "parameters": {
            "diameter": diameter,
            "depth": depth,
            "thread_pitch": thread_pitch,
            "thread_depth": thread_depth,
        },
        "metadata": _hole_metadata(
            standard_name="Tapped hole",
            standard_reference="ISO 965 / DIN 13",
            part_category="hole",
            editable_parameters=["diameter", "depth", "thread_pitch", "thread_depth"],
        ),
    }
