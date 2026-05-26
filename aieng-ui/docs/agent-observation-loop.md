# Agent Observation Loop (v0.35.2)

Status: **Implemented (heuristic v1)** · MVP · 2026-05-20 ·
extended by [CAD Observation v1 (v0.36)](./cad-observation.md) and the
[AIENG-wrapped FreeCAD MCP Pilot (v0.37)](./freecad-mcp-wrapper.md),
which contribute ingest / inspect / register actions to the loop without
introducing new approval paths.

## Purpose

v0.35.1 shipped the Intent Planner: natural-language request → reviewable
`IntentPlan` → `IntentAction` → approval-gated runtime execution. v0.35.2
closes that loop with a **structured observation** after every action so
the consumer (a human reviewer, or an external agent driving AIENG) can
answer four questions:

1. **What happened?** — status, summary, runtime errors.
2. **What changed?** — artifact_changes, evidence_refs, stale_changes.
3. **What can be claimed now?** — readiness_delta, warnings,
   `claim_boundary`.
4. **What should happen next?** — `next_recommended_actions` (heuristic).

The loop is intentionally one action at a time. There is no
"run the full plan" auto-runner.

## Loop diagram

```
Text request
  ↓
IntentPlan                              [v0.35.1]
  ↓ user picks one action
IntentAction
  ↓
POST /api/intent-planner/actions/{id}/execute
  ↓
Runtime run created
  ├─ approval-gated? → status = "awaiting_approval"   (no package write)
  │      ↓
  │  POST /api/runtime/runs/{run_id}/approve|reject
  │      ↓
  │  POST /api/intent-planner/observe                  [v0.35.2]
  │      ↓
  │  Updated IntentObservation
  └─ otherwise → status = "completed"                  (read-only)
         ↓
       IntentObservation returned with the execute response
```

Observation is **never produced** in a way that bypasses the existing
runtime approval gate. The execute endpoint reports
`submitted_for_approval`; the post-approval state is fetched explicitly
via the new `POST /api/intent-planner/observe` endpoint.

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /api/intent-planner/actions/{action_id}/execute` | Creates one runtime run from one action; returns `{plan_id, action, run, observation}`. The observation reflects the run state *immediately after* `execute_run_with_plan`, before any approve/reject. |
| `POST /api/intent-planner/observe` | Recomputes the observation for an already-submitted action. Body: `{plan, action_id, run_id}`. Read-only; never mutates the package. |
| `POST /api/runtime/runs/{id}/approve` · `POST /api/runtime/runs/{id}/reject` | **Unchanged.** The same approval endpoints used by every other AIENG mutation. The frontend now calls `/observe` after them to refresh the observation. |

## IntentObservation schema

```jsonc
{
  "schema_version": "0.1",
  "plan_id": "plan_<hex>",
  "action_id": "action_<hex>",
  "run_id": "<runtime run id>",
  "tool_name": "engineering_template.save_draft",
  "mode": "read_only | metadata_write | mutation | expensive",
  "status":
    "submitted_for_approval | approved_executed | completed | rejected | failed",
  "summary": "<one-paragraph plain summary>",
  "artifact_changes": [
    { "path": "task/cad_template_preview.py", "kind": "package_member", "operation": "write" }
  ],
  "evidence_refs": [ "task/engineering_setup_draft.json", ... ],
  "audit_event_ids": [ "<runtime event id>", ... ],
  "stale_changes": [ "simulation/mesh/*", ... ],
  "readiness_delta": {
    "evaluated": true,
    "before": { "ready_to_run": false, "missing_items": [ ... ] },
    "after":  { "ready_to_run": false, "missing_items": [ ... ] },
    "resolved_items": [ ... ],
    "newly_missing_items": [ ... ]
  },
  "warnings": [ ... ],
  "errors": [ ... ],
  "claim_advancement": "none",
  "claim_boundary": "<full claim boundary text>",
  "next_recommended_actions": [
    {
      "kind": "execute_action | await_approval | regenerate_plan | resolve_readiness_gap | ...",
      "label": "<one-line label>",
      "rationale": "<one-line reason>",
      "reference": "engineering_template.adopt_targets",
      "details": [ ... ]   // optional
    }
  ]
}
```

### Status mapping

| Runtime `run.status` | `observation.status` | Notes |
|---|---|---|
| `awaiting_approval` | `submitted_for_approval` | No package write yet. |
| `completed` + `action.requires_approval=true` | `approved_executed` | Approval succeeded; artifact changes reported. |
| `completed` + `action.requires_approval=false` | `completed` | Read-only or auto-completed action. |
| `rejected` | `rejected` | `artifact_changes=[]`, `evidence_refs=[]`, `stale_changes=[]`. |
| `failed` | `failed` | First runtime error is surfaced in `summary`. |
| `pending`/`running`/`cancelled` | `submitted_for_approval` | Transient; the UI keeps the action in a waiting state. |

### Honesty rules

The observation refuses to claim more than the run actually produced:

- `artifact_changes`, `evidence_refs`, `stale_changes` are **only**
  populated when `status ∈ {approved_executed, completed}`. For
  `submitted_for_approval`, `rejected`, and `failed`, they are empty
  lists with an explicit warning.
- `readiness_delta.evaluated` is `false` whenever no structural
  preflight snapshot was taken. The UI must not assume the run
  improved readiness.
- `claim_advancement` is always `"none"`. Period.
- Solver evidence is only acknowledged when the underlying tool was
  the real solver path (which v0.35.2 still refuses to invoke
  directly from natural language — see v0.35.1 docs).

### Recommender heuristics

`next_recommended_actions` is derived from a small deterministic table
keyed on `(tool_name, status, plan refusals, readiness)`:

| Trigger | Recommendation |
|---|---|
| `status = submitted_for_approval` | `await_approval` — review and approve in the Pilot Console. |
| `status = rejected` | `regenerate_plan` — refine the request before proposing again. |
| `status = failed` | `inspect_failure` — review the runtime error first. |
| Completed `engineering_template.preview` | `execute_action` → `engineering_template.save_draft`. |
| Completed `engineering_template.save_draft` | `execute_action` → adopt_targets and/or generate_cad_fixture. |
| Completed `engineering_template.adopt_targets` | `execute_action` → generate_cad_fixture (if proposed); `inspect_evidence` → target_comparison. |
| Completed `engineering_template.generate_cad_fixture` | `inspect_readiness` — re-check the structural preflight. |
| Completed `cae.prepare_solver_run` (not ready) | `resolve_readiness_gap` — open the Structural Adapter card. |
| Plan refused `cae.run_solver` | `resolve_readiness_gap` — one entry per `solver_run_readiness:*` missing item. |
| Plan has no template match | `request_missing_information` — provide the listed inputs. |

Recommendations are *advice*. They never start an action by themselves.

## Frontend integration

[`IntentPlannerCard.tsx`](../frontend/src/components/panels/IntentPlannerCard.tsx)
now stores an `observation` per action under the existing `runStateById`
map. After approve / reject, the panel calls `/api/intent-planner/observe`
and updates the card in place. The observation block renders
artifact_changes / evidence_refs / stale_changes / readiness / warnings /
errors / next_recommended_actions; it falls back to honest empty-state
hints when fields are absent.

`ChatPanel` is still untouched.

## Safety boundaries (same as v0.35.1, restated)

- No real FreeCAD execution.
- No arbitrary Python execution.
- No new solver execution paths.
- No approval-gate bypass — the new `/observe` endpoint is read-only.
- No LLM-mode planner yet.
- No multi-step auto-run.
- No new dependencies.

## Limitations (deferred to v0.35.3+ or later)

- No persistent observation history yet; observation state lives in
  the frontend's component state and is refetched via `/observe` per
  approve/reject. A future revision can persist it under
  `audit/intent_observation_history.json` if needed.
- No SSE / WebSocket push: the panel re-fetches observation
  explicitly after the approve/reject calls.
- The recommender does not yet propose generic CAD or CAE adapter
  flows (`freecad.inspect_features`, `cae.generate_mesh`, etc.) — it
  only knows the controlled-template path so far.
- Readiness delta is currently structural-static-only because that is
  the only preflight AIENG ships. CFD readiness is intentionally
  absent (see v0.41+ in the roadmap).

## Why this is still not generic text-to-CAD or solver automation

- The planner still refuses arbitrary text-to-CAD. Only the controlled
  cantilever and plate-with-hole templates can match.
- The planner still refuses to invoke `cae.run_solver` from natural
  language. The observation can only surface readiness gaps; the run
  itself must be approved on the dedicated Structural Adapter card.
- The recommender suggests, the user (or external agent) decides. No
  action is queued automatically.

In other words: AIENG remains the **engineering action exoskeleton**
described in the v0.35.1 doc. The observation loop is what makes that
exoskeleton visible — the agent acts, AIENG observes, records,
constrains, and explains every step.

## Verification

- Backend: 7 new tests in
  [`tests/test_agent_observation.py`](../backend/tests/test_agent_observation.py)
  cover the seven required cases from the v0.35.2 brief plus a payload
  validation test. Full backend suite green at **626 passed / 3 skipped**.
- Frontend: `npm run build` passes. Manual flow:
  1. Load a project, pick "Cantilever beam (full info)" sample.
  2. Click *Generate plan*.
  3. Execute *Preview template draft* → observation appears below the card
     with the next-step recommendation.
  4. Execute *Save template draft* → observation shows
     `submitted_for_approval` with a "Approve or reject" recommendation.
  5. Approve the run → observation refreshes to `approved_executed` and
     lists the four written artifacts.

## File map

### New

- [`backend/app/agent_observation.py`](../backend/app/agent_observation.py)
- [`backend/tests/test_agent_observation.py`](../backend/tests/test_agent_observation.py)
- [`docs/agent-observation-loop.md`](./agent-observation-loop.md) (this file)

### Edited

- [`backend/app/app_factory.py`](../backend/app/app_factory.py) — execute
  endpoint now returns `observation`; new
  `POST /api/intent-planner/observe` endpoint.
- [`frontend/src/types.ts`](../frontend/src/types.ts) — `IntentObservation`,
  `IntentObservationStatus`, `IntentObservationRecommendation`, etc.
- [`frontend/src/api.ts`](../frontend/src/api.ts) — `observeIntentAction`
  client; updated `executeIntentAction` response type.
- [`frontend/src/components/panels/IntentPlannerCard.tsx`](../frontend/src/components/panels/IntentPlannerCard.tsx)
  — observation rendering, approve/reject refresh.
- [`frontend/src/style.css`](../frontend/src/style.css) — observation
  block styles.
- [`docs/intent-planner.md`](./intent-planner.md) — cross-link.
- [`docs/technical-roadmap.md`](./technical-roadmap.md) — v0.35.2 row.
