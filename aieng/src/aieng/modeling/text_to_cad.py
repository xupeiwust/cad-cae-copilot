"""Text-to-CAD protocol, result types, and prompt builders.

This module contains only interfaces and prompt logic — no CAD library
imports.  Concrete backends (build123d, FreeCAD scripting, NX journaling,
etc.) live outside this package and implement TextToCadBackend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ── result types ──────────────────────────────────────────────────────────────

@dataclass
class TextToCadHints:
    material: str | None = None
    dimensions_mm: dict[str, float] | None = None
    style: str | None = None        # "minimal" | "lightweight" | "reinforced"
    symmetry: str | None = None     # "x" | "y" | "xy"


@dataclass
class TextToCadResult:
    backend: str
    description: str
    generated_code: str
    step_bytes: bytes | None
    stl_bytes: bytes | None
    topology_map: dict[str, Any]
    feature_graph: dict[str, Any]
    warnings: list[str]
    metadata: dict[str, Any]
    glb_bytes: bytes | None = None
    error: str | None = None


# ── protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class TextToCadBackend(Protocol):
    @property
    def name(self) -> str: ...

    def can_generate(self) -> bool: ...

    def generate(
        self,
        description: str,
        hints: dict[str, Any] | None = None,
    ) -> TextToCadResult: ...


# ── build123d prompt templates ─────────────────────────────────────────────────

BUILD123D_SYSTEM_PROMPT = """\
You are a parametric CAD engineer using the build123d Python library (built on OpenCascade).
Generate Python code that creates a 3D mechanical part from a natural-language description.

Rules:
1. build123d is already imported: `from build123d import *`
2. Do NOT add any import statements.
3. All dimensions are in millimeters.
4. If using BuildPart context manager, the last line MUST be: result = bp.part
   If using direct construction, the last line MUST be: result = <your_shape>
5. Do NOT call show_all(), show(), export_step(), or any visualization/export function.
6. Respond with ONLY the Python code — no markdown fences, no explanation.
7. When the model has multiple distinct parts, label and color each one:
   set `.label = "name"` so it appears as a named part in topology, and set
   `.color = Color(r, g, b)` (RGB in 0..1) so the part is visually distinguishable
   in the rendered thumbnail and the GLB viewer. Combine parts with
   `Compound(children=[part1, part2, ...])`.
"""


def build_build123d_refine_prompt(existing_code: str, feedback: str) -> str:
    return (
        "Here is the existing build123d code:\n\n"
        f"```python\n{existing_code}\n```\n\n"
        f"Engineer feedback: {feedback}\n\n"
        "Generate updated build123d code that incorporates the feedback. "
        "The last line MUST assign the final Part to `result`."
    )


def build_build123d_user_prompt(
    description: str,
    hints: TextToCadHints | None = None,
) -> str:
    from .standard_parts import format_hardware_context

    parts = [f'DESIGN DESCRIPTION: "{description}"']
    hardware_context = format_hardware_context(description)
    if hardware_context:
        parts.append(hardware_context)
    if hints:
        if hints.material:
            parts.append(
                f"MATERIAL CONTEXT: {hints.material} "
                f"— let this inform wall thickness and structural decisions"
            )
        if hints.dimensions_mm:
            dims = ", ".join(f"{k}={v}mm" for k, v in hints.dimensions_mm.items())
            parts.append(f"TARGET DIMENSIONS: {dims}")
        if hints.style:
            parts.append(f"STYLE: {hints.style}")
        if hints.symmetry:
            parts.append(f"SYMMETRY: {hints.symmetry}")
    parts.append("")
    parts.append(
        "Generate the build123d Python code. "
        "The last line MUST assign the final Part to `result`."
    )
    return "\n".join(parts)
