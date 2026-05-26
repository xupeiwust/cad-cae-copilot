# Modeling plan rules

## What the IR is

- JSON document conforming to `modeling_plan.schema.json` in the `aieng/` repo.
- Operations are primitive-first. Phase 1 operations: `create_box`, `create_cylindrical_cut`.

## Forbidden in v0.1.0

- Family operations are rejected by the schema enum. Examples: `create_plate`, `create_bracket`, `create_enclosure`, `create_housing`. Do not emit them; compose primitives instead.
- Hand-editing `modeling_plan.schema.json`. Schema changes belong in `aieng/` core.
- Direct CAD-kernel Python (FreeCAD, CadQuery, others). Execution flows through a registered backend adapter only.

## Required fields the agent reads

- `intent.original_text` — preserved verbatim.
- `units.length`, `units.angle`.
- `assumptions[]` — each entry has `id`, `text`, `risk`, `requires_user_confirmation`.
- `missing_information[]` — each entry has `id`, `text`, `severity`.
- `steps[]` — each step has `step_id`, `operation`, optional `target`, `parameters`, and step-level `confidence`.
- `checks[]` — post-execution predicates.

## Field constraints

- `target` references a prior `step_id`. Example:

  ```json
  {
    "step_id": "step_002",
    "operation": "create_cylindrical_cut",
    "target": "step_001"
  }
  ```

- `target` lives at the step level, never inside `parameters`.
- `confidence` is a **step-level** enum: `certain | inferred | guessed`. It is not a float and is not attached to assumption entries.
- `step_id` values must be unique across the plan.
- `target` must refer to a `step_id` that appears earlier in `steps[]`.

## Composition guidance

- Recognized intents that map to allowed primitives → emit the composition (for example "plate with 4 holes" → `create_box` + 4 × `create_cylindrical_cut`).
- Unrecognized intents → emit a `missing_information[]` entry rather than inventing an operation or emitting a family op.

## On schema rejection

If the planner emits something the validator rejects, **fix the plan to obey the schema**. Do not propose changing the schema from within this skill; schema evolution is a separate workflow in `aieng/`.
