"""Standard structural profiles — angle, channel, I-beam, tubes — as Shape IR nodes."""
from __future__ import annotations

from typing import Any


def _profile_metadata(
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

def angle_profile(
    leg_a: float = 50.0,
    leg_b: float = 50.0,
    thickness: float = 5.0,
    length: float = 1000.0,
) -> dict[str, Any]:
    """Return a Shape IR node for an equal-leg angle profile (L-profile, ISO 657-1 / DIN 1028).

    Modelled as the union of two boxes forming an L shape, extruded along Z.
    """
    leg1 = {
        "id": "leg_a",
        "primitive": "box",
        "dimensions": [leg_a, thickness, length],
        "location": [leg_a / 2.0 - thickness / 2.0, 0.0, length / 2.0],
    }
    leg2 = {
        "id": "leg_b",
        "primitive": "box",
        "dimensions": [thickness, leg_b, length],
        "location": [0.0, leg_b / 2.0 - thickness / 2.0, length / 2.0],
    }
    return {
        "id": "angle_profile",
        "name": "Angle Profile",
        "operation": "union",
        "children": [leg1, leg2],
        "parameters": {
            "leg_a": leg_a,
            "leg_b": leg_b,
            "thickness": thickness,
            "length": length,
        },
        "metadata": _profile_metadata(
            standard_name="Equal-leg angle steel",
            standard_reference="ISO 657-1 / DIN 1028",
            part_category="structural_profile",
            editable_parameters=["leg_a", "leg_b", "thickness", "length"],
        ),
    }


def channel_profile(
    height: float = 100.0,
    width: float = 50.0,
    flange_thickness: float = 8.0,
    web_thickness: float = 5.0,
    length: float = 1000.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a U-channel profile (ISO 657-11 / DIN 1026).

    Modelled as a large box minus a smaller box to create the C-shaped cross
    section, extruded along Z.
    """
    outer = {
        "id": "outer",
        "primitive": "box",
        "dimensions": [width, height, length],
        "location": [0.0, 0.0, length / 2.0],
    }
    inner = {
        "id": "inner",
        "primitive": "box",
        "dimensions": [width - 2.0 * web_thickness, height - flange_thickness, length + 0.1],
        "location": [0.0, -flange_thickness / 2.0, length / 2.0],
    }
    return {
        "id": "channel_profile",
        "name": "Channel Profile",
        "operation": "difference",
        "children": [outer, inner],
        "parameters": {
            "height": height,
            "width": width,
            "flange_thickness": flange_thickness,
            "web_thickness": web_thickness,
            "length": length,
        },
        "metadata": _profile_metadata(
            standard_name="U-channel steel",
            standard_reference="ISO 657-11 / DIN 1026",
            part_category="structural_profile",
            editable_parameters=["height", "width", "flange_thickness", "web_thickness", "length"],
        ),
    }


def i_beam_profile(
    height: float = 100.0,
    width: float = 55.0,
    flange_thickness: float = 9.0,
    web_thickness: float = 5.5,
    length: float = 1000.0,
) -> dict[str, Any]:
    """Return a Shape IR node for an I-beam profile (H-beam, ISO 657-14 / DIN 1025).

    Modelled as the union of a vertical web and two horizontal flanges.
    """
    web = {
        "id": "web",
        "primitive": "box",
        "dimensions": [web_thickness, height - 2.0 * flange_thickness, length],
        "location": [0.0, 0.0, length / 2.0],
    }
    top_flange = {
        "id": "top_flange",
        "primitive": "box",
        "dimensions": [width, flange_thickness, length],
        "location": [0.0, height / 2.0 - flange_thickness / 2.0, length / 2.0],
    }
    bottom_flange = {
        "id": "bottom_flange",
        "primitive": "box",
        "dimensions": [width, flange_thickness, length],
        "location": [0.0, -(height / 2.0 - flange_thickness / 2.0), length / 2.0],
    }
    return {
        "id": "i_beam_profile",
        "name": "I-Beam Profile",
        "operation": "union",
        "children": [web, top_flange, bottom_flange],
        "parameters": {
            "height": height,
            "width": width,
            "flange_thickness": flange_thickness,
            "web_thickness": web_thickness,
            "length": length,
        },
        "metadata": _profile_metadata(
            standard_name="I-beam (H-beam) steel",
            standard_reference="ISO 657-14 / DIN 1025",
            part_category="structural_profile",
            editable_parameters=["height", "width", "flange_thickness", "web_thickness", "length"],
        ),
    }


def rectangular_tube(
    width: float = 50.0,
    height: float = 30.0,
    wall_thickness: float = 3.0,
    length: float = 1000.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a rectangular hollow section (RHS, ISO 657-14 / EN 10219).

    Modelled as an outer box minus an inner box.
    """
    outer = {
        "id": "outer",
        "primitive": "box",
        "dimensions": [width, height, length],
        "location": [0.0, 0.0, length / 2.0],
    }
    inner = {
        "id": "inner",
        "primitive": "box",
        "dimensions": [width - 2.0 * wall_thickness, height - 2.0 * wall_thickness, length + 0.1],
        "location": [0.0, 0.0, length / 2.0],
    }
    return {
        "id": "rectangular_tube",
        "name": "Rectangular Tube",
        "operation": "difference",
        "children": [outer, inner],
        "parameters": {
            "width": width,
            "height": height,
            "wall_thickness": wall_thickness,
            "length": length,
        },
        "metadata": _profile_metadata(
            standard_name="Rectangular hollow section (RHS)",
            standard_reference="ISO 657-14 / EN 10219",
            part_category="structural_profile",
            editable_parameters=["width", "height", "wall_thickness", "length"],
        ),
    }


def round_tube(
    outer_diameter: float = 50.0,
    wall_thickness: float = 3.0,
    length: float = 1000.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a round hollow section (CHS, ISO 657-14 / EN 10219).

    Modelled as an outer cylinder minus an inner cylinder.
    """
    outer = {
        "id": "outer",
        "primitive": "cylinder",
        "radius": outer_diameter / 2.0,
        "height": length,
        "location": [0.0, 0.0, length / 2.0],
    }
    inner = {
        "id": "inner",
        "primitive": "cylinder",
        "radius": outer_diameter / 2.0 - wall_thickness,
        "height": length + 0.1,
        "location": [0.0, 0.0, length / 2.0],
    }
    return {
        "id": "round_tube",
        "name": "Round Tube",
        "operation": "difference",
        "children": [outer, inner],
        "parameters": {
            "outer_diameter": outer_diameter,
            "wall_thickness": wall_thickness,
            "length": length,
        },
        "metadata": _profile_metadata(
            standard_name="Circular hollow section (CHS)",
            standard_reference="ISO 657-14 / EN 10219",
            part_category="structural_profile",
            editable_parameters=["outer_diameter", "wall_thickness", "length"],
        ),
    }
