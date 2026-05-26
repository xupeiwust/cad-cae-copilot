# AIENG Developer Architecture

Status: **v0.34**
Last updated: **2026-05-19**

## High-level components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend Workbench                             │
│  (React 18 + Vite + TypeScript)                                         │
│  Cards: ProjectHealth, DesignTargets, ComputedMetrics, TargetComparison, │
│         FreeCadInspection, StructuralAdapter, CopilotLoop,              │
│         EngineeringReviewPacket, TemplateAuthoring, IntentPlanner        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         UI Backend (FastAPI)                             │
│  Routers: project, health, design-targets, computed-metrics,            │
│           target-comparison, freecad, structural, runtime,              │
│           copilot-loop, review-packet, template-authoring, intent       │
│  Core modules: external_adapters, package_inspection, project_io        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         .aieng Package (ZIP)                             │
│  manifest.json, task/design_targets.yaml, results/computed_metrics.json, │
│  graph/feature_graph.json, simulation/*, results/evidence_index.json,   │
│  audit/*.json, claims/proposals/*.json                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │ freecad_mcp│   │ Gmsh/CCX  │   │  OpenFOAM │
            │ (sibling)  │   │ (runtime) │   │  (future) │
            └───────────┘   └───────────┘   └───────────┘
```

## Data flow

### Template draft → CAD → FEA → Review

```
1. Engineer intent → controlled parametric template draft
2. Template draft → design target suggestions (v0.35)
3. User reviews + adopts targets → task/design_targets.yaml
4. Template draft → CAD script/artifact generation (v0.36)
   → writes geometry/* → marks mesh/solver/results stale
5. Template FEA setup → solver deck draft (v0.37)
   → writes simulation/runs/{run_id}/solver_input.inp
6. Approval-gated solver run → FRD/DAT extraction (v0.29–v0.30)
   → writes results/computed_metrics.json
7. Target comparison refresh (v0.23 + v0.38)
   → per-load-case pass/fail/unknown
8. Copilot Loop report + Engineering Review Packet (v0.31 + v0.40)
   → evidence trace, audit excerpt, comparison summary
```

### Read-only vs mutation boundaries

| Flow | Read-only | Mutation | Approval required |
|---|---|---|---|
| Project Health Check | ✅ | ❌ | ❌ |
| FreeCAD Inspection | ✅ | ❌ | ❌ |
| Target Comparison | ✅ | ❌ | ❌ |
| Template draft review | ✅ | ❌ | ❌ |
| CAD parameter edit | ❌ | ✅ | ✅ |
| Solver run | ❌ | ✅ | ✅ |
| CAD generation from template | ❌ | ✅ | ✅ |
| Deck generation from template | ❌ | ✅ | ✅ |
| Metrics import | ❌ | ✅ | ✅ (explicit save) |

## Approval gates

All mutation paths share the same runtime contract:

1. **Preflight** — read-only readiness check.
2. **Proposal** — show what will change.
3. **Await approval** — user must explicitly approve.
4. **Execute** — run the tool.
5. **Evidence writeback** — record what happened.
6. **Stale propagation** — mark downstream artifacts stale.

## Natural Language Intent Planner (v0.35.1)

A new planning layer that translates plain-language requests into structured AIENG workflow plans.

### Data flow

```
Plain language request
  → Intent extraction (supported intents only)
  → Slot filling / missing information detection
  → Structured plan generation
  → Safety policy annotation (read-only vs mutating vs approval-required)
  → Plan preview (read-only)
  → User confirmation
  → Routing to existing cards/actions
```

### Supported intents (initial)

- `project_health_check`
- `design_target_draft`
- `computed_metrics_import_guidance`
- `target_comparison`
- `freecad_inspect_features`
- `cad_parameter_edit_proposal`
- `structural_solver_run_request`
- `review_support_packet_export`
- `engineering_template_draft`

### Safety model

- **Preview only by default** — the planner never executes.
- **Schema validation** — every plan step must match a known action.
- **Confirmation required** — user reviews before any execution.
- **Approval gates preserved** — mutating/expensive steps still require explicit approval.
- **Claim advancement = none** — always.

### Non-goals

- Arbitrary text-to-CAD.
- Arbitrary preprocessing.
- Automatic solver execution.
- Autonomous optimization.

## Stale evidence propagation

When a mutation succeeds, downstream artifacts are marked stale:

- CAD edit → mesh, solver runs, computed metrics, result summaries, loop reports
- Mesh regen → solver runs, computed metrics, result summaries
- Solver run → computed metrics, result summaries (until extraction refreshes)
- Target save → loop reports, comparison summaries

Stale markers are surfaced in Project Health Check and Copilot Loop UI.

## Claim advancement

**Always `none`.** AIENG never advances claims automatically. Proposals remain `draft` until human review. Evidence supports review; it does not validate or certify.
