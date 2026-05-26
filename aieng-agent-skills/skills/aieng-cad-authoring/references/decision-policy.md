# Decision policy

The authoring pipeline is an agent/user/CLI-selected workflow for create-new CAD tasks. It is not automatically triggered for every CAD/CAE request. Apply the rules below before invoking it.

## Use this skill when ALL are true

- The goal is to produce a new CAD part from a description.
- No existing `.step`, `.stp`, `.fcstd`, `.iges`, `.brep`, `.stl`, or `.aieng` file needs to be opened, parsed, or modified.
- The `aieng` CLI is available.

## Do NOT use this skill when ANY is true

- The user provides a path to an existing CAD/CAE/.aieng file and asks to inspect, summarize, import, edit, mesh, simulate, or repair it.
- The user asks for engineering analysis: strength, stiffness, FEA, CFD, thermal, fatigue, tolerance stack-up.
- The user asks to modify a previously generated `.aieng` package. Phase 1 supports create-new only.
- The user asks for drawings, BOM, PDM operations, rendering, or photoreal images.
- The user asks the agent to write FreeCAD or CadQuery Python directly.

## Disambiguation question (when uncertain)

> "Do you want me to create a new CAD part from your description (this produces a STEP and an audit package), or to do something with an existing file you already have?"

Ask at most once. If the user is still ambiguous after the disambiguation, default to *do not use this skill* and explain what each path would produce.

## On disqualifier

State briefly which workflow applies (if a known alternative exists); otherwise say no such skill exists yet in this workspace. Do not silently fall through to `aieng plan`.
