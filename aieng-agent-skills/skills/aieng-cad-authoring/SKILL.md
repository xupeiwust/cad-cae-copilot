---
name: aieng-cad-authoring
description: Active MCP-first CAD authoring skill for AIENG Workbench. Use when the user asks to create, design, draft, model, or iteratively build CAD geometry through the active cad.* MCP tools. Do not use for solver/result review, schema/library implementation, or editing legacy IR plans.
---

# aieng-cad-authoring

MCP-first CAD authoring discipline for agents driving the active AIENG Workbench.
The recommended path is the live MCP toolchain and build123d runtime, not the older schema-plan CLI flow.

## Purpose

- Create or extend real CAD geometry through `cad.execute_build123d`.
- Keep generated geometry inspectable with named parts, colors, and editable constants.
- Use the UI as the live 3D viewer and spatial pointer surface.
- Preserve evidence honesty: CAD output is geometry evidence, not engineering validation.

## When to use

Use when the user asks to create, build, design, model, add, or substantially modify CAD geometry.
For pure dimensional tweaks on an existing editable model, prefer `cad.edit_parameter`.
For engineering audit only, use `cad.critique` without mutating geometry.
For solver workflows, use `aieng-cad-cae-copilot`.

## Required workflow

1. Call `aieng.agent_readme`, `aieng.list_projects`, and `aieng.agent_context { project_id }` when project state is not already known.
2. Call `cad.get_source { project_id }` before incremental edits; use `mode="append"` only when `has_base=true`.
3. For new/additive geometry, call `cad.execute_build123d` with build123d Python that:
   - binds the final model to `result`,
   - omits export calls,
   - sets `.label` on every meaningful part,
   - sets `.color = Color(r,g,b)` for readability,
   - declares editable dimensions as `UPPER_SNAKE_CASE` constants.
4. Inspect the returned thumbnail, `named_parts`, `parts_added`, `geometry_report`, symmetry, and gaps before continuing.
5. For pure dimensional changes, use `cad.edit_parameter` and read `regression_diff` before trusting the result.
6. For mechanical parts, call `cad.critique` after creation and fix blocking manufacturability findings.

## Hard rules

- Respect `[APPROVAL REQUIRED]` tools; never bypass or hide approval boundaries.
- If `AIENG_MCP_BLOCK_APPROVAL_TOOLS=1` is active, gated CAD tools will be refused by the MCP server; report that and stop.
- Do not claim strength, safety factor, manufacturability, meshability, or simulation correctness from CAD generation alone.
- Do not read `aieng/src/` to infer live workbench capabilities; use MCP tool returns and `aieng.agent_readme`.
- For visible products/characters/vehicles, prefer loft/sweep/revolve/fillet helpers over primitive box stacking.
- For engineering parts, use canonical labels such as `base_plate`, `mounting_hole`, `rib`, `boss`, `flange`, and `interface_face`.

## Response contract

Report: tool sequence, key assumptions, parts created/changed, approval status, evidence inspected, and remaining limitations.
