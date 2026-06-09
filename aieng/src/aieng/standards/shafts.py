"""Standard shaft parts — stepped shafts, splined shafts — as Shape IR nodes."""
from __future__ import annotations

from typing import Any


def _shaft_metadata(
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

def stepped_shaft(
    segments: list[dict[str, float]] | None = None,
    keyway_width: float | None = None,
    keyway_depth: float | None = None,
) -> dict[str, Any]:
    """Return a Shape IR node for a stepped shaft (DIN 748 / ISO 4014 shaft extensions).

    Each segment is a dict with ``diameter`` and ``length``.  Segments are
    stacked along the Z axis.  An optional keyway is modelled as a subtracted
    box on the largest-diameter segment.
    """
    if segments is None:
        segments = [
            {"diameter": 20.0, "length": 30.0},
            {"diameter": 25.0, "length": 40.0},
            {"diameter": 20.0, "length": 30.0},
        ]

    z = 0.0
    segment_nodes: list[dict[str, Any]] = []
    max_diameter = max(seg.get("diameter", 0.0) for seg in segments)

    for i, seg in enumerate(segments):
        diameter = float(seg.get("diameter", 20.0))
        length = float(seg.get("length", 30.0))
        segment_nodes.append({
            "id": f"segment_{i}",
            "primitive": "cylinder",
            "radius": diameter / 2.0,
            "height": length,
            "location": [0.0, 0.0, z + length / 2.0],
        })
        z += length

    children: list[dict[str, Any]] = segment_nodes

    if keyway_width is not None and keyway_depth is not None:
        # Place keyway on the segment with the largest diameter
        z_key = 0.0
        key_segment_idx = 0
        for i, seg in enumerate(segments):
            if seg.get("diameter", 0.0) == max_diameter:
                key_segment_idx = i
                break
            z_key += seg.get("length", 0.0)
        key_length = segments[key_segment_idx].get("length", 0.0)
        keyway = {
            "id": "keyway",
            "primitive": "box",
            "dimensions": [keyway_width, keyway_depth, key_length + 0.1],
            "location": [0.0, max_diameter / 2.0 - keyway_depth / 2.0, z_key + key_length / 2.0],
        }
        children = [{
            "id": "shaft_with_keyway",
            "operation": "difference",
            "children": segment_nodes + [keyway],
        }]

    params: dict[str, Any] = {"segments": segments}
    if keyway_width is not None:
        params["keyway_width"] = keyway_width
    if keyway_depth is not None:
        params["keyway_depth"] = keyway_depth

    return {
        "id": "stepped_shaft",
        "name": "Stepped Shaft",
        "operation": "union",
        "children": children,
        "parameters": params,
        "metadata": _shaft_metadata(
            standard_name="Stepped shaft",
            standard_reference="DIN 748 / ISO 4014",
            part_category="shaft",
            editable_parameters=["segments", "keyway_width", "keyway_depth"],
        ),
    }


def splined_shaft(
    diameter: float = 25.0,
    length: float = 60.0,
    spline_count: int = 6,
    spline_width: float = 4.0,
    spline_height: float = 2.0,
) -> dict[str, Any]:
    """Return a Shape IR node for a simplified splined shaft (ISO 14 / DIN 5480).

    The shaft body is a cylinder.  Splines are approximated as radial
    protrusions (small boxes) unioned around the circumference.
    """
    shaft_body = {
        "id": "shaft_body",
        "primitive": "cylinder",
        "radius": diameter / 2.0,
        "height": length,
        "location": [0.0, 0.0, length / 2.0],
    }

    import math
    spline_nodes: list[dict[str, Any]] = []
    for i in range(spline_count):
        angle = 2.0 * math.pi * i / spline_count
        x = math.cos(angle) * (diameter / 2.0 + spline_height / 2.0)
        y = math.sin(angle) * (diameter / 2.0 + spline_height / 2.0)
        spline_nodes.append({
            "id": f"spline_{i}",
            "primitive": "box",
            "dimensions": [spline_width, spline_height, length],
            "location": [x, y, length / 2.0],
            "rotation": [0.0, 0.0, math.degrees(angle)],
        })

    return {
        "id": "splined_shaft",
        "name": "Splined Shaft",
        "operation": "union",
        "children": [shaft_body, *spline_nodes],
        "parameters": {
            "diameter": diameter,
            "length": length,
            "spline_count": spline_count,
            "spline_width": spline_width,
            "spline_height": spline_height,
        },
        "metadata": _shaft_metadata(
            standard_name="Splined shaft",
            standard_reference="ISO 14 / DIN 5480",
            part_category="shaft",
            editable_parameters=[
                "diameter",
                "length",
                "spline_count",
                "spline_width",
                "spline_height",
            ],
        ),
    }
