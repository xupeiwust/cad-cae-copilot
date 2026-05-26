# Clarification policy

Minimum questions, maximum recorded assumptions.

## Ask the user when

- `missing_information[]` contains an entry with `severity: blocking`.
- An assumption has `requires_user_confirmation: true` AND materially affects geometry (overall size, hole pitch, primary feature placement, wall thickness, principal axes).
- The user has requested engineering claims (strength, safety factor, manufacturability, mass, simulation validity) without supplying required evidence. In that case explain that this skill cannot validate those claims and that a CAE / readiness workflow is needed. Do not silently proceed and do not author CAD as a substitute for validation.

## Proceed with recorded assumptions when

- Missing dimensions can be defaulted by the planner.
- Units are omitted and defaulted to `mm`.
- Hole count or placement can be inferred as a conceptual model.
- The user asked for a quick conceptual CAD package.

In each of these cases the planner's `assumptions[]` (and any non-blocking `missing_information[]`) become the audit record; surface them in the final response rather than interrogating the user.

## When to apply

Run `aieng plan` first whenever possible. The planner surfaces `assumptions[]` and `missing_information[]`; use those as the source of truth. Do not pre-empt with questions when the planner can answer.

## Question budget

- Default: at most 2 batched questions per session.
- The user may invite more — honor that.
- If more than 2 things are unclear, prefer recording assumptions and surfacing them in the response over interrogating the user.

## Geometry-impacting unknowns

If geometry is materially undefined (no shape concept, no recognizable feature pattern) and the planner emits `severity: blocking`, ask. Otherwise proceed and record.

## Engineering-claim disqualifiers

For pure geometry authoring, material / load / manufacturing detail is out of scope and need not be asked. If the user *explicitly* asks for engineering validation, stop and route them to the appropriate CAE / readiness workflow.
