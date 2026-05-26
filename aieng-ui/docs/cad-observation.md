# CAD Observation v1 (v0.36)

Status: **Implemented (read-only v1)** · MVP · 2026-05-20 ·
extended by [AIENG-wrapped FreeCAD MCP Pilot (v0.37)](./freecad-mcp-wrapper.md),
which ingests FreeCAD/MCP snapshots and exported-geometry registrations
that this observer reads.

## Purpose

v0.35.1 turned natural language into a reviewable
[`IntentPlan`](./intent-planner.md). v0.35.2 closed the loop with an
[`IntentObservation`](./agent-observation-loop.md) per action — *what
happened*, *what changed*, *what's next*. CAD Observation v1 goes one
step further: it starts grounding the loop in **actual engineering
state**, not just runtime state.

After a CAD-related action runs, AIENG now answers:

- Is there CAD state at all?
- Is it real geometry, or metadata only?
- Which engineering inputs are known?
- Which ones are still missing?
- What can we honestly *not* claim from this state?
- What should happen next (CAD-import, semantic labelling, region
  identification, geometry readiness inspection)?

CAD Observation v1 is read-only over the existing `.aieng` package. It
does **not** execute FreeCAD, does **not** generate geometry, and does
**not** make physical claims from metadata.

## Where it plugs in

```
IntentAction (CAD-related)
  ↓
runtime execution / approval                 [v0.35.1]
  ↓
IntentObservation                            [v0.35.2]
  ↳ cad_observation (CADObservation)          ← new in v0.36
  ↳ next_recommended_actions                   includes CAD/CAE advice
```

A CAD observation is attached to the `IntentObservation` only when the
action is CAD-related, gated by
`cad_observation.is_cad_related_action(action)`. The gate matches:

- `engineering_template.generate_cad_fixture`
- `freecad.inspect_geometry`, `freecad.inspect_features`,
  `freecad.export_step`, `freecad.run_macro`
- `cad.edit_parameter`
- Any future `freecad.*` or `cad.source.*` tool (prefix match)
- Any action whose `expected_artifacts` reference `geometry/...` or
  contain `cad`

## Evidence levels

CAD observation classifies geometry evidence on a four-level ladder.
The level is **derived from the actual presence of recognised package
members**, never from intent or template label alone.

| Level | Trigger | What can be claimed |
|---|---|---|
| `none` | No CAD-related artifact found. | Nothing. |
| `metadata` | Only metadata artifacts (`geometry/template_cad_fixture.json`, `task/engineering_setup_draft.json`, descriptor files like `graph/feature_graph.json`). | Intent and parameter context only. No physical / meshability / solver readiness claims. |
| `exported_geometry` | A binary CAD member is present (`.step`, `.stp`, `.fcstd`, `.brep`, `.iges`, `.igs`). | Geometry exists in an external format. Watertightness, units, and topology still need explicit inspection. |
| `live_cad_snapshot` | `geometry/freecad_snapshot.json` is present (forward-compatible path; not yet written by AIENG). | Geometry was directly observed via a future FreeCAD MCP integration. Still no solver claims. |

A future FreeCAD MCP bridge that adds a `freecad_snapshot.json`
artifact will lift this level automatically — no schema change needed.

## CADObservation schema

```jsonc
{
  "schema_version": "0.1",
  "status": "available | metadata_only | missing | invalid | unknown",
  "source_artifacts": [ "geometry/template_cad_fixture.json", ... ],
  "geometry_evidence_level": "none | metadata | exported_geometry | live_cad_snapshot",
  "summary": "<plain-text honest summary>",
  "known_geometry": { "primitive": "box", "dimensions": { ... }, ... },
  "known_parameters": { "length_mm": 200.0, ... },
  "known_materials": { "id": "aluminum_6061_t6", ... },
  "known_load_candidates": [
    { "id": "x_max_face", "role": "load_application", ... }
  ],
  "known_support_candidates": [
    { "id": "x_min_face", "role": "fixed_support", ... }
  ],
  "known_named_regions": [ { "id": "x_min_face", ... } ],
  "semantic_labels": [ "root_support", ... ],
  "topology_references": { "faces": 12, "feature_count": 3, "feature_ids": [ ... ] },
  "missing_information": [ "real geometry (STEP/FCStd) or live FreeCAD snapshot", ... ],
  "cae_readiness_hints": {
    "mesh_evidence": false,
    "solver_input_evidence": false,
    "computed_metrics_evidence": false,
    "has_design_targets": false,
    "present_paths": [ "results" ]
  },
  "warnings": [ "<honest warnings>" ],
  "claim_advancement": "none",
  "claim_boundary": "<full claim boundary text>",
  "next_recommended_actions": [
    {
      "kind": "import_real_geometry",
      "label": "Import or generate real CAD geometry (STEP/FCStd) for this template fixture.",
      "rationale": "Only metadata-level CAD evidence exists ...",
      "reference": "freecad.export_step"
    }
  ]
}
```

## Honesty rules (enforced by the module)

1. **Descriptor ≠ geometry.** `graph/feature_graph.json` or
   `geometry/topology_map.json` alone do not lift evidence to
   `exported_geometry`. A binary CAD member or a live snapshot is required.
2. **Metadata-only summary is explicit.** Every metadata-only
   observation carries a warning:
   *"CAD fixture metadata exists, but no real CAD geometry evidence is
   available. This cannot prove the geometry is valid, watertight,
   meshable, or simulation-ready."*
3. **No physical correctness claims.** The summary and warnings never
   use words like `watertight`, `meshable`, `solver-ready`,
   `validated`, `certified`, or `physically correct` unless they are
   explicitly negated.
4. **Mesh, solver, and computed-metrics readiness are flat booleans.**
   They are derived from explicit package paths (`simulation/mesh/*`,
   `.inp` deck, `results/computed_metrics.json`). The module never
   guesses readiness from intent.
5. **Invalid artifacts surface as `status=invalid`.** Unparseable JSON
   in `template_cad_fixture.json` or `freecad_snapshot.json` is
   reported, not silently swallowed. Evidence is never lifted from
   such a corrupt artifact.
6. **`claim_advancement` is always `"none"`.**

## Recommender heuristics

CAD-specific recommendations are derived deterministically:

| Trigger | Recommendation |
|---|---|
| `status = missing` / `evidence = none` | Generate a template CAD fixture or import real CAD geometry. |
| `evidence = metadata` | Import or generate real CAD geometry; if no semantic labels, recommend labelling functional regions; if no load/support candidates, recommend identifying them. |
| `evidence ∈ {exported_geometry, live_cad_snapshot}` and no mesh evidence | Inspect geometry readiness (FreeCAD Inspection card) before approving mesh/solver setup. |

These suggestions are merged into the IntentObservation's
`next_recommended_actions` list and de-duplicated against the v0.35.2
recommender, so the UI renders one unified "Next" block per action plus
a CAD-specific block under `cad_observation.next_recommended_actions`.

## Frontend integration

[`IntentPlannerCard`](../frontend/src/components/panels/IntentPlannerCard.tsx)
now renders a `CadObservationBlock` whenever an
`IntentObservation.cad_observation` is present. It surfaces status,
evidence level, source artifacts, known parameters/geometry/material,
named regions, semantic labels, topology references, missing
information, CAE readiness hints, warnings, and CAD-specific
recommendations. `ChatPanel` is still untouched. There is no
auto-execution — the user still picks each next step manually.

## Safety boundaries (same as v0.35.1 + v0.35.2)

- No real FreeCAD execution.
- No arbitrary Python execution.
- No solver execution.
- No mesh generation.
- No automatic CAD repair.
- No multi-step auto-run.
- No replacement of ChatPanel.
- No expanded controlled templates.
- No new dependencies.

## Limitations (deferred)

- Snapshots from a real FreeCAD MCP bridge are not produced here; v0.36
  reads them if present and supports them in the schema, but writing
  them is a future v0.37+ task.
- The recommender does not yet know about external CAD source
  generation backends. Adding a `cad.source.*` family later only
  requires registering tools — the gate already matches them.
- Topology / interface / object_registry coverage is reported
  coarsely (counts and feature ids only). Deeper structural
  cross-checks belong to a future Verification gate, not the observer.

## Why this is still not generic text-to-CAD

- The CAD observation cannot create geometry. It can only describe
  what is already on disk.
- The Intent Planner still refuses arbitrary text-to-CAD and arbitrary
  solver execution. CAD Observation merely makes the *state* of CAD
  visible — it does not produce CAD.
- The recommendations are *advice* about what a human (or a future
  external agent operating through AIENG) should do next. Nothing
  starts automatically.

## Verification

- Backend: 8 new tests in
  [`tests/test_cad_observation.py`](../backend/tests/test_cad_observation.py)
  cover the five required cases plus an exported-geometry path, an
  invalid-fixture path, and the `is_cad_related_action` gate. Full
  backend suite green at **634 passed / 3 skipped**.
- Frontend: `npm run build` passes. Manual flow:
  1. Load a project, pick "Cantilever beam (full info)".
  2. *Generate plan*, execute *Save template draft* and approve it.
  3. Execute *Generate CAD fixture* and approve it. The action's
     observation now carries a CAD observation block showing
     `metadata_only`, with a recommendation to import real CAD
     geometry and to label functional regions.

## File map

### New

- [`backend/app/cad_observation.py`](../backend/app/cad_observation.py)
- [`backend/tests/test_cad_observation.py`](../backend/tests/test_cad_observation.py)
- [`docs/cad-observation.md`](./cad-observation.md) (this file)

### Edited

- [`backend/app/agent_observation.py`](../backend/app/agent_observation.py)
  — accepts an optional `cad_observation` parameter, merges its
  warnings and recommendations into the IntentObservation.
- [`backend/app/app_factory.py`](../backend/app/app_factory.py) — both
  `execute_intent_action` and `observe_intent_action` build a CAD
  observation for CAD-related actions and pass it into
  `build_observation`.
- [`frontend/src/types.ts`](../frontend/src/types.ts) — `CadObservation`,
  `CadObservationStatus`, `CadGeometryEvidenceLevel`, etc.; added
  `cad_observation` to `IntentObservation`.
- [`frontend/src/components/panels/IntentPlannerCard.tsx`](../frontend/src/components/panels/IntentPlannerCard.tsx)
  — `CadObservationBlock`.
- [`frontend/src/style.css`](../frontend/src/style.css) — CAD
  observation styling.
- [`docs/agent-observation-loop.md`](./agent-observation-loop.md) —
  cross-link.
- [`docs/technical-roadmap.md`](./technical-roadmap.md) — new v0.36 row.
