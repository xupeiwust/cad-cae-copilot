from __future__ import annotations

import re
import uuid
from typing import Any

from ..schema_versions import MODELING_PLAN_SCHEMA


DEFAULTS: dict[str, float] = {
    "length": 100.0,
    "width": 60.0,
    "height": 10.0,
    "hole_radius": 3.0,
    "hole_margin_ratio": 0.15,
}

_UNITS_PATTERN = re.compile(r"\b(mm|cm|m|in)\b", re.IGNORECASE)
_DIMENSIONS_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)"
)
_DIMENSIONS_BY_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_HOLES_PATTERN = re.compile(r"\b(\d+)\s+(?:mounting\s+)?holes?\b", re.IGNORECASE)

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


class RuleBasedModelingPlanner:
    """Regex-based planner that emits primitive-only modeling plans.

    Phase 1 scope:
      - create_box
      - create_cylindrical_cut
    """

    def plan(
        self,
        intent: str,
        *,
        defaults: dict[str, Any] | None = None,
        units: dict[str, str] | None = None,
        context_package_path: str | None = None,
    ) -> dict[str, Any]:
        """Parse natural language intent and return a schema-valid modeling_plan dict."""
        effective_defaults = dict(DEFAULTS)
        if defaults:
            effective_defaults.update({k: float(v) for k, v in defaults.items() if k in DEFAULTS})

        # Parse units
        length_unit = self._parse_length_unit(intent)
        if length_unit is None:
            length_unit = "mm"

        effective_units = {"length": length_unit, "angle": "deg"}
        if units:
            effective_units.update(units)

        # Parse dimensions
        dims = self._parse_dimensions(intent)
        if dims is None:
            dims = (
                effective_defaults["length"],
                effective_defaults["width"],
                effective_defaults["height"],
            )

        length, width, height = dims

        # Parse hole count
        hole_count = self._parse_hole_count(intent)

        # Build steps
        steps: list[dict[str, Any]] = []
        assumptions: list[dict[str, Any]] = []
        missing_info: list[dict[str, Any]] = []

        # Step 1: create_box
        box_step_id = "step_001"
        box_name = "body_001"
        steps.append(
            {
                "step_id": box_step_id,
                "operation": "create_box",
                "creates": box_name,
                "parameters": {
                    "length": float(length),
                    "width": float(width),
                    "height": float(height),
                    "origin": [0.0, 0.0, 0.0],
                    "origin_mode": "corner",
                    "name": box_name,
                },
                "confidence": "certain" if self._has_explicit_dimensions(intent) else "inferred",
            }
        )

        if not self._has_explicit_dimensions(intent):
            assumptions.append(
                {
                    "id": "assumption_default_dimensions",
                    "text": (
                        f"No explicit dimensions found in intent. "
                        f"Using defaults: {length} x {width} x {height} {length_unit}."
                    ),
                    "risk": "Geometry may not match user expectation.",
                    "requires_user_confirmation": True,
                }
            )

        if length_unit == "mm" and not _UNITS_PATTERN.search(intent):
            assumptions.append(
                {
                    "id": "assumption_default_unit_mm",
                    "text": "No length unit specified; defaulting to mm.",
                    "risk": "low",
                    "requires_user_confirmation": False,
                }
            )

        # Steps 2+: create_cylindrical_cut
        if hole_count is None and _HOLES_PATTERN.search(intent) is not None:
            # User mentioned holes but no explicit count
            hole_count = 4
            missing_info.append(
                {
                    "id": "missing_hole_count",
                    "text": "Hole count not specified; defaulting to 4.",
                    "severity": "warning",
                }
            )

        if hole_count:
            margin = min(length, width) * effective_defaults["hole_margin_ratio"]
            hole_depth = float(height) + 2.0
            hole_radius = effective_defaults["hole_radius"]

            positions = [
                [margin, margin, -1.0],
                [float(length) - margin, margin, -1.0],
                [margin, float(width) - margin, -1.0],
                [float(length) - margin, float(width) - margin, -1.0],
            ]

            for i in range(hole_count):
                pos = positions[i % len(positions)]
                step_num = i + 2
                step_id = f"step_{step_num:03d}"
                cut_name = f"hole_{i + 1:02d}"
                steps.append(
                    {
                        "step_id": step_id,
                        "operation": "create_cylindrical_cut",
                        "creates": cut_name,
                        "target": box_step_id,
                        "parameters": {
                            "radius": float(hole_radius),
                            "depth": float(hole_depth),
                            "position": pos,
                            "axis": [0.0, 0.0, 1.0],
                            "name": cut_name,
                        },
                        "confidence": "certain",
                    }
                )

            if hole_count > len(positions):
                assumptions.append(
                    {
                        "id": "assumption_hole_positions_reused",
                        "text": (
                            f"More holes ({hole_count}) than predefined corner positions ({len(positions)}). "
                            "Positions cycle; overlaps possible."
                        ),
                        "risk": "medium",
                        "requires_user_confirmation": True,
                    }
                )

        # Checks
        checks: list[dict[str, Any]] = []
        op_counts: dict[str, int] = {}
        for step in steps:
            op = step["operation"]
            op_counts[op] = op_counts.get(op, 0) + 1

        checks.append(
            {
                "check_type": "operation_count",
                "parameters": {"by_operation": op_counts},
            }
        )

        return {
            "plan_id": f"plan_{uuid.uuid4().hex[:8]}",
            "plan_schema_version": MODELING_PLAN_SCHEMA,
            "intent": {
                "original_text": intent,
                "interpreted_goal": self._generate_interpreted_goal(steps),
            },
            "units": effective_units,
            "assumptions": assumptions,
            "missing_information": missing_info,
            "steps": steps,
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_length_unit(self, intent: str) -> str | None:
        match = _UNITS_PATTERN.search(intent)
        if match:
            return match.group(1).lower()
        return None

    def _parse_dimensions(self, intent: str) -> tuple[float, float, float] | None:
        match = _DIMENSIONS_PATTERN.search(intent)
        if match:
            return (float(match.group(1)), float(match.group(2)), float(match.group(3)))
        match = _DIMENSIONS_BY_PATTERN.search(intent)
        if match:
            return (float(match.group(1)), float(match.group(2)), float(match.group(3)))
        return None

    def _has_explicit_dimensions(self, intent: str) -> bool:
        return _DIMENSIONS_PATTERN.search(intent) is not None or _DIMENSIONS_BY_PATTERN.search(intent) is not None

    def _parse_hole_count(self, intent: str) -> int | None:
        match = _HOLES_PATTERN.search(intent)
        if match:
            return int(match.group(1))
        # Try number words
        lowered = intent.lower()
        for word, num in _NUMBER_WORDS.items():
            if re.search(rf"\b{word}\b(?:\s+(?:mounting\s+)?holes?)?", lowered):
                return num
        return None

    def _generate_interpreted_goal(self, steps: list[dict[str, Any]]) -> str:
        box_count = sum(1 for s in steps if s["operation"] == "create_box")
        cut_count = sum(1 for s in steps if s["operation"] == "create_cylindrical_cut")
        parts = []
        if box_count:
            parts.append(f"Create {box_count} rectangular box-like solid(s).")
        if cut_count:
            parts.append(f"Apply {cut_count} cylindrical through-cut(s).")
        return " ".join(parts) if parts else "Execute primitive modeling operations."
