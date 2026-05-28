---
name: aieng-cad-authoring
description: create-new cad/cae authoring workflow for generating a new .aieng package from natural-language design intent. use when the user asks to create, design, draft, model, or generate a new cad part using a schema-valid modeling_plan, backend adapter execution, evidence, trace, and validation status. do not use for analyzing, importing, summarizing, repairing, meshing, simulating, or modifying existing cad/cae/.aieng files; use import/analysis workflows instead.
---

# aieng-cad-authoring

> **Pipeline note (2026-05):** This skill drives the legacy
> `aieng plan` / `aieng validate-plan` / `aieng init-from-plan` CLI flow
> that emits a primitive-first `modeling_plan.json` (create_box /
> create_cylindrical_cut) for execution through a backend adapter.
> The **active, recommended path** for new CAD work in this workspace
> is the MCP tool `cad.execute_build123d` — the agent writes full
> build123d Python directly and the workbench runs it. See the project
> root `AGENTS.md` (sections "Industrial Design Mode" and
> "Engineering Mode") for that workflow, plus the per-part `.color` /
> `.label` conventions, the multi-view contact-sheet thumbnail, the
> `cad.set_reference_image` calibration tool, and the `cad.critique`
> manufacturability audit. Prefer that path unless you specifically
> need the schema-bound IR pipeline this skill orchestrates.

Control plane for the `.aieng` Phase 1 authoring pipeline. Translates natural-language design intent into a schema-valid `modeling_plan.json`, executes it through a backend adapter, and produces an audit-grade `.aieng` package. This skill orchestrates three CLI commands; it does not generate CAD code and does not call CAD APIs directly.

Skill version: `0.1.0`. Requires an `aieng` CLI build that supports `aieng plan`, `aieng validate-plan`, `aieng init-from-plan`, `init-from-plan --no-postprocess`, and `init-from-plan --postprocess-strict`. See `references/workflow.md`.

The authoring pipeline is an agent/user/CLI-selected workflow for create-new CAD tasks. It is not automatically triggered for every CAD/CAE request.

## What this skill does

- Decides whether the user's request is a create-new CAD authoring task.
- Asks the minimum useful clarification questions; records assumptions otherwise.
- Drives `aieng plan`, `aieng validate-plan`, and `aieng init-from-plan`.
- Reads the resulting `.aieng` package and reports findings in a standard format without inventing claims.

## When to use / when not to use

Trigger conditions and disqualifiers are stated in the frontmatter `description`. Before any tool call, apply `references/decision-policy.md`. If the decision says "wrong skill," stop and explain which workflow is needed.

## Control flow

1. **Decide** — apply `references/decision-policy.md`. Stop on disqualifier.
2. **Clarify or assume** — apply `references/clarification-policy.md`. Record every assumption.
3. **Plan** — `aieng plan --intent "<intent>" --out modeling_plan.json`. Inspect output.
4. **Validate** — `aieng validate-plan modeling_plan.json`. On failure, follow `references/failure-recovery.md`.
5. **Choose backend** — apply `references/backend-policy.md`.
6. **Execute** — `aieng init-from-plan modeling_plan.json --out generated.aieng --backend <backend>`. On non-success, follow `references/failure-recovery.md`.
7. **Inspect package** — open `validation/status.yaml`, `authoring/modeling_plan.json`, `authoring/construction_history.json`, `results/evidence_index.json`.
8. **Respond** — use `references/output-format.md`.

## Hard rules

- Never execute arbitrary CAD Python (FreeCAD, CadQuery, or other CAD-kernel APIs). Execution flows through `aieng init-from-plan` and a registered backend adapter only.
- Never run `aieng init-from-plan` before `aieng validate-plan` exits 0.
- Never emit family operations (for example `create_plate`, `create_bracket`, `create_enclosure`). The schema enum forbids them. Compose primitives instead.
- Never claim engineering validity (strength, safety factor, manufacturability, simulation correctness) on the basis of generated geometry or recorded evidence. See `references/evidence-claim-policy.md`.
- Never use this skill to inspect, summarize, import, repair, mesh, simulate, or modify an existing CAD/CAE/.aieng file.
- Never silently switch from a real backend to `fake` to make a run appear to succeed. If the user requested real geometry and no real backend is reachable, ask or label the result explicitly as a skeleton / dry run. Surface failures per `references/failure-recovery.md`.

## Reference loading

Always read first:

- `references/decision-policy.md`
- `references/workflow.md`

Read when applicable:

- `references/clarification-policy.md` — when intent is ambiguous or incomplete
- `references/modeling-plan-rules.md` — when constructing or fixing a plan
- `references/backend-policy.md` — at backend selection
- `references/failure-recovery.md` — on any non-zero exit, `partial`, or `failed` status
- `references/evidence-claim-policy.md` — before drafting the response
- `references/output-format.md` — when drafting the response
