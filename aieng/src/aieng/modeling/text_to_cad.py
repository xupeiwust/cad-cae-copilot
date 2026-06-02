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
8. INDUSTRIAL DESIGN MODE — when the description names a real product,
   character, or vehicle, or asks for something "designed/smooth/rounded":
   - Do NOT stack `Box(...)` to imitate curves on visible exterior forms.
   - Build tapered/curved bodies with `loft` between two sketches at
     different Z (e.g. truck cab, helmet, fuselage).
   - Use `revolve` for axisymmetric bodies (bottles, bell housings).
   - Use `sweep` along a `BuildLine` path for pipes, handles, exhausts.
   - Apply `fillet` aggressively (radius 5-20mm) on visible edges, LAST.
   - Mirror symmetric parts with `mirror(part, about=Plane.YZ)`.
   For purely mechanical brackets/fixtures/prototypes, primitive stacking
   is fine — this rule is for visible exterior forms only.

   HARD RULE: If your iteration script is mostly `Box(...) + .moved(...)` for a
   visible character/vehicle/product, STOP and replace the major exterior masses
   with ONE of: loft between sketches, revolved profile, or swept profile.
   Stacked boxes cap the result at "high-quality pixel art" — it will not read
   as designed.

   Named landmarks (mm) — define proportions ONCE as named constants so the
   whole body re-proportions when a value changes:
   ```python
   HIP_Z, SHOULDER_Z = 232, 392
   HIP_HALF, SHOULDER_HALF = 55, 150
   with BuildPart() as bp:
       with BuildSketch(Plane.XY.offset(HIP_Z + 30)) as base:
           RectangleRounded(HIP_HALF * 2 + 20, 90)
       with BuildSketch(Plane.XY.offset(SHOULDER_Z)) as top:
           RectangleRounded(SHOULDER_HALF * 2, 80)
       loft()
   ```
9. ENGINEERING MODE — when the description names a mechanical part like
   bracket, housing, enclosure, manifold, fixture, frame, mount, flange,
   or chassis (parts that downstream tools will manufacture or simulate):
   - Use canonical .label names so the feature_graph tags them with
     semantic intent: `base_plate`, `mounting_hole`, `mounting_hole_pattern`,
     `rib`, `boss`, `flange`, `interface_face`, `wall`, `cover`.
   - Honour manufacturing rules: minimum wall ≥ 3mm (CNC), hole-edge
     distance ≥ 2 × hole radius, internal corner radius ≥ 2mm (use
     `fillet`), no sharp internal corners, no undercuts unless asked.
   - Preserve mounting interfaces — once you commit to a hole pattern,
     don't shift it on later iterations.
   - Pick standard hole diameters (3, 4, 5, 6, 8, 10, 12, 16, 20 mm)
     and place holes ≥ 2× radius from any edge.
10. PARAMETRIC DESIGN — declare every key dimension as a named UPPER_SNAKE_CASE
    constant BEFORE the geometry that uses it. This enables downstream parametric
    editing without re-running the LLM.

    BAD:
      body = Box(120, 80, 8)
      with Locations((45, 25, 0)):
          Hole(radius=5, depth=8)

    GOOD:
      BODY_LENGTH = 120
      BODY_WIDTH = 80
      BODY_THICKNESS = 8
      HOLE_RADIUS = 5
      body = Box(BODY_LENGTH, BODY_WIDTH, BODY_THICKNESS)
      with Locations((45, 25, 0)):
          Hole(radius=HOLE_RADIUS, depth=BODY_THICKNESS)

    For each named part, prefix the constant with the part name:
      MOTOR_POD_RADIUS = 3
      MOTOR_POD_HEIGHT = 30
      fl = Cylinder(MOTOR_POD_RADIUS, MOTOR_POD_HEIGHT)
      fl.label = "motor_pod_FL"
      fl.color = Color(0.20, 0.30, 0.65)

    Use named constants for ALL dimensions: Box sizes, Cylinder radii/heights,
    Hole radii, fillet radii, placement offsets, and loft sketch sizes.
11. HIGH-LEVEL HELPERS — these functions are pre-injected into your namespace
    (do NOT define or import them). Prefer them over hand-writing
    BuildSketch/Plane/loft/sweep boilerplate — they produce smoother forms AND
    are far less error-prone. Each accepts label= and color= and returns a Part.
    - lofted_stack(sections) — loft through Z-stacked cross-sections. Each section
      is (z, radius) for a circle, (z, w, d) for a rounded rect, or (z, w, d, r).
      USE THIS instead of stacking boxes for torsos, cabs, fuselages, bodies.
        result = lofted_stack([(0,120,80),(200,150,90),(392,60)], label="torso")
    - rounded_box(length, width, height, radius, edges="all"|"vertical") — a
      filleted box; the default block for designed enclosures (not a hard Box).
    - capsule(radius, length, axis="Z") — cylinder with hemispherical caps; the
      go-to for arms, legs, limbs, rounded pins.
    - tapered_cylinder(bottom_radius, top_radius, height) — truncated cone for
      necks, nozzles, tapered legs.
    - swept_tube(path_points, radius) — sweep a circle along a spline through
      (x,y,z) points; pipes, handles, exhausts, cable runs.
    - revolved_profile(profile_points) — revolve a list of (r, z) points around Z
      (auto-closed to the axis); bottles, vases, bell housings, wheels.
    - organic_blend(solids, radius) — fuse solids and fillet the joins so they
      read as ONE smooth body instead of glued primitives. Use to merge a head
      into a neck, a handle into a body, etc.
12. QUANTITATIVE SELF-REVIEW — after each build, the tool returns a
    `geometry_report` with exact numbers. Judge proportions from these numbers,
    NOT only from the blurry thumbnail:
    - `overall_proportions` — normalized H:W:D of the whole model.
    - `parts[].ratio_to_largest` — each part's size relative to the biggest part.
    - `symmetry[]` — for left/right name pairs (e.g. arm_L/arm_R, motor_pod_FL/FR):
      `ok: false` means the pair is NOT symmetric — fix the offending coordinates.
      `status: missing_partner` means you named one side but not the other.
    - `gaps[]` — `status: floating` means a part is detached (likely a coordinate
      typo); `touching` means parts connect as intended.
    Cite specific numbers when iterating, e.g. "arm ratio_to_largest=0.5 but the
    reference arm reaches mid-thigh → lengthen to ~0.7". This is far more reliable
    than eyeballing the render.
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


def build_system_prompt(extra_context: str | None = None) -> str:
    """Return the build123d system prompt, optionally augmented with extra context.

    When ``extra_context`` is provided (e.g. the contents of AGENTS.md), it is
    appended after the base prompt so the LLM receives the full capability guide
    as its single source of truth.
    """
    prompt = BUILD123D_SYSTEM_PROMPT
    if extra_context:
        prompt = (
            prompt.rstrip()
            + "\n\n--- AGENTS.md capability guide (single source of truth) ---\n\n"
            + extra_context.lstrip()
        )
    return prompt
