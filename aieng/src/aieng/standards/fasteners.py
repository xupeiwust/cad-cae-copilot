"""Standard fasteners — bolts, nuts, washers, screws — as Shape IR nodes.

Each function returns a Shape IR node dictionary that can be compiled to
build123d / OpenCASCADE B-Rep via the existing Shape IR compilers.
"""
from __future__ import annotations

from typing import Any

# ── common metadata helpers ────────────────────────────────────────────────

def _fastener_metadata(
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

METRIC_BOLT_PRESETS: dict[str, dict[str, float]] = {
    "M6": {
        "diameter": 6.0,
        "length": 20.0,
        "thread_pitch": 1.0,
        "head_diameter": 10.0,
        "head_height": 4.0,
    },
    "M8": {
        "diameter": 8.0,
        "length": 25.0,
        "thread_pitch": 1.25,
        "head_diameter": 13.0,
        "head_height": 5.3,
    },
    "M10": {
        "diameter": 10.0,
        "length": 30.0,
        "thread_pitch": 1.5,
        "head_diameter": 16.0,
        "head_height": 6.4,
    },
    "M12": {
        "diameter": 12.0,
        "length": 35.0,
        "thread_pitch": 1.75,
        "head_diameter": 18.0,
        "head_height": 7.5,
    },
}

METRIC_NUT_PRESETS: dict[str, dict[str, float]] = {
    "M6": {"diameter": 6.0, "pitch": 1.0, "width_across_flats": 10.0, "height": 5.0},
    "M8": {"diameter": 8.0, "pitch": 1.25, "width_across_flats": 13.0, "height": 6.5},
    "M10": {"diameter": 10.0, "pitch": 1.5, "width_across_flats": 16.0, "height": 8.0},
    "M12": {"diameter": 12.0, "pitch": 1.75, "width_across_flats": 18.0, "height": 10.0},
}

METRIC_WASHER_PRESETS: dict[str, dict[str, float]] = {
    "M6": {"inner_diameter": 6.2, "outer_diameter": 12.0, "thickness": 1.6},
    "M8": {"inner_diameter": 8.2, "outer_diameter": 16.0, "thickness": 1.6},
    "M10": {"inner_diameter": 10.2, "outer_diameter": 20.0, "thickness": 2.0},
    "M12": {"inner_diameter": 12.2, "outer_diameter": 24.0, "thickness": 2.5},
}

METRIC_SOCKET_HEAD_PRESETS: dict[str, dict[str, float]] = {
    "M6": {
        "diameter": 6.0,
        "length": 20.0,
        "head_diameter": 10.0,
        "head_height": 6.0,
        "socket_size": 5.0,
    },
    "M8": {
        "diameter": 8.0,
        "length": 25.0,
        "head_diameter": 13.0,
        "head_height": 8.0,
        "socket_size": 6.0,
    },
    "M10": {
        "diameter": 10.0,
        "length": 30.0,
        "head_diameter": 16.0,
        "head_height": 10.0,
        "socket_size": 8.0,
    },
    "M12": {
        "diameter": 12.0,
        "length": 35.0,
        "head_diameter": 18.0,
        "head_height": 12.0,
        "socket_size": 10.0,
    },
}

METRIC_SET_SCREW_PRESETS: dict[str, dict[str, float]] = {
    "M6": {"diameter": 6.0, "length": 10.0},
    "M8": {"diameter": 8.0, "length": 12.0},
    "M10": {"diameter": 10.0, "length": 16.0},
    "M12": {"diameter": 12.0, "length": 20.0},
}


# ── generators ──────────────────────────────────────────────────────────────

def hex_bolt(
    diameter: float = 8.0,
    length: float = 25.0,
    thread_pitch: float = 1.25,
    head_diameter: float = 13.0,
    head_height: float = 5.3,
    drive_type: str = "external_hex",
) -> dict[str, Any]:
    """Return a Shape IR node for a hex-head bolt (ISO 4014 / DIN 933).

    The bolt is modelled as a union of a cylindrical shank and a hex-prism head.
    For simplicity the hex head is approximated by a cylinder of the same
    head_diameter; a future refinement can switch to an extruded hexagon.
    """
    shank = {
        "id": "shank",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": length,
        "location": [0.0, 0.0, 0.0],
    }
    head = {
        "id": "head",
        "primitive": "cylinder",
        "radius": head_diameter / 2.0,
        "height": head_height,
        "location": [0.0, 0.0, length],
    }
    return {
        "id": "hex_bolt",
        "name": "Hex Bolt",
        "operation": "union",
        "children": [shank, head],
        "parameters": {
            "diameter": diameter,
            "length": length,
            "thread_pitch": thread_pitch,
            "head_diameter": head_diameter,
            "head_height": head_height,
            "drive_type": drive_type,
        },
        "metadata": _fastener_metadata(
            standard_name="Hexagon head bolt",
            standard_reference="ISO 4014 / DIN 933",
            part_category="fastener",
            editable_parameters=[
                "diameter",
                "length",
                "thread_pitch",
                "head_diameter",
                "head_height",
                "drive_type",
            ],
        ),
    }


def hex_nut(
    diameter: float = 8.0,
    pitch: float = 1.25,
    width_across_flats: float = 13.0,
    height: float = 6.5,
) -> dict[str, Any]:
    """Return a Shape IR node for a hex nut (ISO 4032 / DIN 934).

    The nut is modelled as a hollow cylinder (outer = width_across_flats,
    inner = diameter) with a cylindrical hole subtracted.
    """
    outer_radius = width_across_flats / 2.0
    inner_radius = diameter / 2.0
    body = {
        "id": "nut_body",
        "primitive": "cylinder",
        "radius": outer_radius,
        "height": height,
        "location": [0.0, 0.0, 0.0],
    }
    hole = {
        "id": "nut_hole",
        "primitive": "cylinder",
        "radius": inner_radius,
        "height": height + 0.1,
        "location": [0.0, 0.0, -0.05],
    }
    return {
        "id": "hex_nut",
        "name": "Hex Nut",
        "operation": "difference",
        "children": [body, hole],
        "parameters": {
            "diameter": diameter,
            "pitch": pitch,
            "width_across_flats": width_across_flats,
            "height": height,
        },
        "metadata": _fastener_metadata(
            standard_name="Hexagon nut",
            standard_reference="ISO 4032 / DIN 934",
            part_category="fastener",
            editable_parameters=["diameter", "pitch", "width_across_flats", "height"],
        ),
    }


def washer(
    inner_diameter: float = 8.2,
    outer_diameter: float = 16.0,
    thickness: float = 1.6,
) -> dict[str, Any]:
    """Return a Shape IR node for a flat washer (ISO 7089 / DIN 125).

    Modelled as a large cylinder with a smaller cylinder subtracted.
    """
    body = {
        "id": "washer_body",
        "primitive": "cylinder",
        "radius": outer_diameter / 2.0,
        "height": thickness,
        "location": [0.0, 0.0, 0.0],
    }
    hole = {
        "id": "washer_hole",
        "primitive": "cylinder",
        "radius": inner_diameter / 2.0,
        "height": thickness + 0.1,
        "location": [0.0, 0.0, -0.05],
    }
    return {
        "id": "washer",
        "name": "Flat Washer",
        "operation": "difference",
        "children": [body, hole],
        "parameters": {
            "inner_diameter": inner_diameter,
            "outer_diameter": outer_diameter,
            "thickness": thickness,
        },
        "metadata": _fastener_metadata(
            standard_name="Flat washer",
            standard_reference="ISO 7089 / DIN 125",
            part_category="fastener",
            editable_parameters=["inner_diameter", "outer_diameter", "thickness"],
        ),
    }


def socket_head_cap_screw(
    diameter: float = 8.0,
    length: float = 25.0,
    head_diameter: float = 13.0,
    head_height: float = 8.0,
    socket_size: float = 6.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a socket-head cap screw (ISO 4762 / DIN 912).

    Modelled as a cylindrical shank plus a larger cylindrical head.
    The socket drive is represented semantically in metadata; exact
    geometry would require an extruded hexagon subtraction.
    """
    shank = {
        "id": "shank",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": length,
        "location": [0.0, 0.0, 0.0],
    }
    head = {
        "id": "head",
        "primitive": "cylinder",
        "radius": head_diameter / 2.0,
        "height": head_height,
        "location": [0.0, 0.0, length],
    }
    return {
        "id": "socket_head_cap_screw",
        "name": "Socket Head Cap Screw",
        "operation": "union",
        "children": [shank, head],
        "parameters": {
            "diameter": diameter,
            "length": length,
            "head_diameter": head_diameter,
            "head_height": head_height,
            "socket_size": socket_size,
        },
        "metadata": _fastener_metadata(
            standard_name="Socket head cap screw",
            standard_reference="ISO 4762 / DIN 912",
            part_category="fastener",
            editable_parameters=[
                "diameter",
                "length",
                "head_diameter",
                "head_height",
                "socket_size",
            ],
        ),
    }


def set_screw(
    diameter: float = 6.0,
    length: float = 10.0,
    drive_type: str = "hex_socket",
) -> dict[str, Any]:
    """Return a Shape IR node for a set screw (grub screw, ISO 4026 / DIN 913).

    Modelled as a plain cylinder; the drive end is represented semantically.
    """
    return {
        "id": "set_screw",
        "name": "Set Screw",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": length,
        "location": [0.0, 0.0, 0.0],
        "parameters": {
            "diameter": diameter,
            "length": length,
            "drive_type": drive_type,
        },
        "metadata": _fastener_metadata(
            standard_name="Set screw (grub screw)",
            standard_reference="ISO 4026 / DIN 913",
            part_category="fastener",
            editable_parameters=["diameter", "length", "drive_type"],
        ),
    }
