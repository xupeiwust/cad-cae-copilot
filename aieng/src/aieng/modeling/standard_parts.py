"""Standard mechanical hardware catalog for LLM-assisted CAD generation.

Provides accurate DIN/ISO dimensions for common fasteners and profiles so
the LLM generates correct clearance holes, counterbores, and pocket geometry
without guessing dimensions.  This is our equivalent of the text-to-cad
step.parts skill — self-contained, no external API required.
"""
from __future__ import annotations

from typing import Any

# ── fastener catalog (ISO metric, all dimensions in mm) ───────────────────────

FASTENERS: dict[str, dict[str, Any]] = {
    "M3": {
        "thread_diameter": 3.0,
        "clearance_hole": 3.4,
        "counterbore_diameter": 6.5,
        "counterbore_depth": 3.0,
        "head_diameter": 5.5,
        "head_height": 3.0,
        "standard_lengths": [6, 8, 10, 12, 16, 20, 25],
    },
    "M4": {
        "thread_diameter": 4.0,
        "clearance_hole": 4.5,
        "counterbore_diameter": 8.0,
        "counterbore_depth": 4.0,
        "head_diameter": 7.0,
        "head_height": 4.0,
        "standard_lengths": [8, 10, 12, 16, 20, 25, 30],
    },
    "M5": {
        "thread_diameter": 5.0,
        "clearance_hole": 5.5,
        "counterbore_diameter": 9.5,
        "counterbore_depth": 5.0,
        "head_diameter": 8.5,
        "head_height": 5.0,
        "standard_lengths": [8, 10, 12, 16, 20, 25, 30, 40],
    },
    "M6": {
        "thread_diameter": 6.0,
        "clearance_hole": 6.6,
        "counterbore_diameter": 11.0,
        "counterbore_depth": 6.0,
        "head_diameter": 10.0,
        "head_height": 6.0,
        "standard_lengths": [10, 12, 16, 20, 25, 30, 40, 50],
    },
    "M8": {
        "thread_diameter": 8.0,
        "clearance_hole": 9.0,
        "counterbore_diameter": 14.5,
        "counterbore_depth": 8.0,
        "head_diameter": 13.0,
        "head_height": 8.0,
        "standard_lengths": [12, 16, 20, 25, 30, 40, 50, 60],
    },
    "M10": {
        "thread_diameter": 10.0,
        "clearance_hole": 11.0,
        "counterbore_diameter": 17.5,
        "counterbore_depth": 10.0,
        "head_diameter": 16.0,
        "head_height": 10.0,
        "standard_lengths": [16, 20, 25, 30, 40, 50, 60, 80],
    },
    "M12": {
        "thread_diameter": 12.0,
        "clearance_hole": 13.5,
        "counterbore_diameter": 20.0,
        "counterbore_depth": 12.0,
        "head_diameter": 18.0,
        "head_height": 12.0,
        "standard_lengths": [20, 25, 30, 40, 50, 60, 80, 100],
    },
}

# ── linear profile catalog (aluminum extrusions, all dimensions in mm) ────────

PROFILES: dict[str, dict[str, Any]] = {
    "2020": {"width": 20.0, "height": 20.0, "slot_width": 6.0, "description": "20×20 T-slot aluminum extrusion"},
    "2040": {"width": 20.0, "height": 40.0, "slot_width": 6.0, "description": "20×40 T-slot aluminum extrusion"},
    "3030": {"width": 30.0, "height": 30.0, "slot_width": 8.0, "description": "30×30 T-slot aluminum extrusion"},
    "4040": {"width": 40.0, "height": 40.0, "slot_width": 8.0, "description": "40×40 T-slot aluminum extrusion"},
}

# ── keyword detection ─────────────────────────────────────────────────────────

_FASTENER_KEYWORDS = {
    "M3": ["m3", "m3 bolt", "m3 screw"],
    "M4": ["m4", "m4 bolt", "m4 screw"],
    "M5": ["m5", "m5 bolt", "m5 screw"],
    "M6": ["m6", "m6 bolt", "m6 screw"],
    "M8": ["m8", "m8 bolt", "m8 screw", "螺栓"],
    "M10": ["m10", "m10 bolt"],
    "M12": ["m12", "m12 bolt"],
}

_PROFILE_KEYWORDS = {
    "2020": ["2020", "20x20", "20×20"],
    "2040": ["2040", "20x40", "20×40"],
    "3030": ["3030", "30x30", "30×30"],
    "4040": ["4040", "40x40", "40×40"],
}


def detect_relevant_hardware(description: str) -> dict[str, list[str]]:
    """Return fastener/profile keys referenced in the description."""
    lower = description.lower()
    fasteners = [k for k, keywords in _FASTENER_KEYWORDS.items() if any(kw in lower for kw in keywords)]
    profiles = [k for k, keywords in _PROFILE_KEYWORDS.items() if any(kw in lower for kw in keywords)]
    return {"fasteners": fasteners, "profiles": profiles}


def format_hardware_context(description: str) -> str | None:
    """Return a hardware-dimensions block to inject into the LLM prompt, or None."""
    found = detect_relevant_hardware(description)
    lines: list[str] = []

    if found["fasteners"]:
        lines.append("HARDWARE DIMENSIONS (use these exact values for holes and counterbores):")
        for key in found["fasteners"]:
            f = FASTENERS[key]
            lines.append(
                f"  {key} bolt: thread_ø={f['thread_diameter']}mm, "
                f"clearance_hole_ø={f['clearance_hole']}mm, "
                f"counterbore_ø={f['counterbore_diameter']}mm depth={f['counterbore_depth']}mm, "
                f"head_ø={f['head_diameter']}mm"
            )

    if found["profiles"]:
        if not lines:
            lines.append("HARDWARE DIMENSIONS:")
        for key in found["profiles"]:
            p = PROFILES[key]
            lines.append(f"  {key} profile: {p['width']}×{p['height']}mm, slot_width={p['slot_width']}mm")

    return "\n".join(lines) if lines else None
