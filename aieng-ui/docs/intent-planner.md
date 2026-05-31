# Natural Language Intent Planner (v0.35.1)

Status: **Implemented (heuristic v1)** · MVP · 2026-05-20 ·
extended by [Agent Observation Loop (v0.35.2)](./agent-observation-loop.md).

## Purpose

The Intent Planner is a thin, reviewable layer between natural-language
engineering requests and the existing approval-gated AIENG runtime. It
turns a plain-language request into a structured **IntentPlan** that a
reviewer can read, edit, or reject — and that the runtime can execute
one action at a time through the same approval gate that every other
AIENG mutation goes through.

It is **not** a text-to-CAD tool. It does not generate free-form
geometry, it does not run solvers, and it does not advance engineering
claims. The planner exists so that external agents (Claude, ChatGPT,
FreeCAD-MCP, future in-house agents) operate AIENG **with** engineering
context, evidence boundaries, approvals, and audit traces — not in
spite of them.

## Capabilities in v0.35.1

- One backend endpoint `POST /api/intent-planner/plan` returning a
  rich [`IntentPlan`](#intentplan-schema) (heuristic only — no LLM call).
- One backend endpoint `POST /api/intent-planner/actions/{action_id}/execute`
  that creates a runtime run for a single proposed action; mutating
  actions still pause on the standard `/api/runtime/runs/{id}/approve`
  gate.
- Four `engineering_template.*` operations are now registered as
  runtime tools (preview / save_draft / adopt_targets / generate_cad_fixture),
  reusing the existing module functions in
  [`engineering_templates.py`](../backend/app/engineering_templates.py).
- One frontend panel `IntentPlannerCard` mounted as the `pilot` tab in
  the control pane. Renders the plan, the constraints, the missing
  information, the assumptions, the evidence scope, the refusals, and
  the proposed actions with explicit `mode` / approval badges.
- Three demo prompts wired into the panel (cantilever / drone-arm /
  premature solver).

## Capabilities **not** in v0.35.1

- No LLM-mode planning. The schema accepts a future LLM path, but the
  v1 implementation is heuristic-only.
- No replacement of the existing chat / agent flow — `ChatPanel` is
  untouched. The Intent Planner is a separate tab.
- No free-form CAD generation. Only the controlled cantilever and
  plate-with-hole templates can match a natural-language request.
- No automatic solver execution. Requests like "run the simulation
  now" are rewritten to readiness gaps; the planner never proposes
  `cae.run_solver`.
- No autonomous re-planning, batch approval, or multi-action chaining.
  Each action is reviewed and executed individually.

## IntentPlan schema

```jsonc
{
  "schema_version": "0.1",
  "plan_id": "plan_<hex>",
  "planner_mode": "heuristic",
  "message": "<verbatim user request>",
  "project_id": "<id or null>",
  "task_summary": "<one-sentence rephrasing>",
  "inferred_engineering_domain":
    "structural_static_linear | structural_unspecified | cfd_unsupported | unclassified",
  "inferred_template_id": "cantilever_beam | plate_with_hole | null",
  "extracted_constraints": [
    { "kind": "material" | "geometry" | "load" | "design_target" | "template_match", ... }
  ],
  "extracted_parameters": { "length_mm": 200.0, ... },
  "missing_information": [ "material", "primary_dimensions", ... ],
  "assumptions": [ "Lengths interpreted in millimetres ...", ... ],
  "actions": [
    {
      "id": "action_<hex>",
      "label": "<human label>",
      "description": "<one-line description>",
      "tool_name": "engineering_template.save_draft",
      "tool_args": { "project_id": "...", "template_id": "...", "parameters": {...} },
      "mode": "read_only | metadata_write | mutation | expensive",
      "requires_approval": true,
      "expected_artifacts": [ "task/fea_setup_draft.json", ... ],
      "stale_impacts": [ "simulation/mesh/*", ... ],
      "risk_notes": [ "Never overwrites task/design_targets.yaml.", ... ]
    }
  ],
  "required_approvals": [ "action_<hex>", ... ],
  "evidence_scope": [ "<one-line scope statement>", ... ],
  "refusals": [ { "tool_name": "cae.run_solver", "reason": "..." } ],
  "warnings": [ "...", ... ],
  "claim_advancement": "none",
  "claim_boundary": "<full claim boundary text>"
}
```

## Action modes

| Mode | Meaning | Approval-gated? |
|---|---|---|
| `read_only` | Inspection / preview. No package write. | No |
| `metadata_write` | Writes only AIENG metadata or draft state (`task/`, `validation/`, `geometry/template_*`). | Yes |
| `mutation` | Modifies engineering artifacts (CAD parameters, geometry sources). | Yes |
| `expensive` | Long-running external tool (solver, mesh generation). | Yes |

The mode is derived from a deterministic table plus the capability
metadata exposed by `agent_workbench.list_capabilities` (`mutates_cad`,
`mutates_package`, `may_update_claim_map`). Approval-required is a
separate boolean carried directly from the runtime registry; the UI
must respect both.

## Safety model

1. **Preview only by default.** `POST /api/intent-planner/plan` never
   executes a tool. The plan is a JSON document; nothing on disk
   changes until the user explicitly clicks an action.
2. **Schema-validated actions.** Every action must reference a tool
   currently registered in `runtime.registered_tools_info()`. Unknown
   tools are rejected with HTTP 400.
3. **Confirmation required.** Mutating, expensive, or
   approval-required actions go through `RunRecord` and pause at
   `awaiting_approval`. The same `/api/runtime/runs/{id}/approve`
   gate that already protects `cae.run_solver`, `cad.edit_parameter`,
   etc. is reused — no new approval path is introduced.
4. **No silent solver execution.** Requests containing run /
   simulate / solve / simulation are matched against the structural
   preflight (`structural_adapter.prepare_structural_run_preview`)
   and the planner emits the missing readiness items instead of
   proposing `cae.run_solver`. The refusal is explicit in
   `plan.refusals`.
5. **Honest missing information.** Requests that do not match a
   supported controlled template (drone arms, gear boxes, anything
   free-form) get a `missing_information` list and only safe
   inspection actions. The planner never invents a template match
   it cannot back up.
6. **Claim advancement: `none`.** Always. The planner never sets
   `claim_advancement` to anything else and refuses to acknowledge
   simulation-based claims it cannot back with solver evidence.

## Non-goals

- Arbitrary text-to-CAD. v0.36 will add controlled CAD generation
  from templates; free-form is out of MVP scope.
- Arbitrary CAE preprocessing.
- Automatic solver execution from natural language.
- LLM-driven autonomous optimisation loops.
- Replacing the existing `ChatPanel` agent flow (still useful for
  developer / debugging workflows).

## How it slots into the broader Copilot direction

The Intent Planner is the first user-visible piece of AIENG-as-an-
**engineering action exoskeleton** for external agents. The schema
is intentionally identical whether the planner is heuristic or
LLM-driven, so a future LLM planner (or an external MCP agent
posting `IntentPlan` objects directly) does not require any change
in the runtime, the approval gate, or the UI. The same is true for
future action sources: FreeCAD-MCP-generated geometry actions,
external CAE setup actions, or generated CAD source — they will
arrive as `IntentAction` records carrying the same `mode` /
`requires_approval` / `stale_impacts` / `risk_notes` fields, and go
through the same runtime gate.

## Verification

- Backend: 6 new tests in
  [`tests/test_intent_planner.py`](../backend/tests/test_intent_planner.py)
  cover the four required demos (complete cantilever / incomplete
  drone arm / premature solver / approval-required action cannot
  execute silently) plus two negative cases. Full suite remains
  green at 619 passed / 3 skipped.
- Frontend: `npm run build` passes; the panel mounts under the new
  "Intent Planner" control-pane tab.

## File map

### New

- [`backend/app/intent_planner.py`](../backend/app/intent_planner.py)
- [`backend/tests/test_intent_planner.py`](../backend/tests/test_intent_planner.py)
- [`frontend/src/components/panels/IntentPlannerCard.tsx`](../frontend/src/components/panels/IntentPlannerCard.tsx)
- [`docs/intent-planner.md`](./intent-planner.md) (this file)

### Edited

- [`backend/app/app_factory.py`](../backend/app/app_factory.py) — registers four
  `engineering_template.*` runtime tools; adds the two intent-planner endpoints.
- [`frontend/src/types.ts`](../frontend/src/types.ts) — `IntentPlan`,
  `IntentAction`, `IntentActionMode`, `IntentActionExecuteResponse`.
- [`frontend/src/api.ts`](../frontend/src/api.ts) — `planIntent`,
  `executeIntentAction`.
- [`frontend/src/appConstants.ts`](../frontend/src/appConstants.ts),
  [`frontend/src/appTypes.ts`](../frontend/src/appTypes.ts) — new `pilot`
  control-pane tab.
- [`frontend/src/App.tsx`](../frontend/src/App.tsx) — mounts the panel.
- [`frontend/src/style.css`](../frontend/src/style.css) — pilot-panel
  styles.
