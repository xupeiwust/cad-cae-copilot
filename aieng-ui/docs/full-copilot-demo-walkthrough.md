# Full Copilot MVP demo walkthrough

This walkthrough exercises the complete v0.34 evidence-grounded CAD/CAE
Copilot loop, end to end. It produces no design certification: every step is
either a read-only inspection, a deliberate import, an approval-gated
mutation, or a controlled template draft. Missing evidence is reported as
missing — never invented.

## Copilot Loop tab layout

Since v0.32 the Copilot Loop tab is organized into six numbered workflow
sections so the page reads as one coherent engineering workflow rather than
a stack of independent cards. Each section has a header band, a one-line
intent, and (for sensitive areas) a small safety pill in the upper-right
corner.

| # | Section | Cards inside | Safety pill |
|---|---|---|---|
| 1 | Readiness & Guidance | Try Copilot Loop demo, Project Health Check | — |
| 2 | Inputs | Design Targets, Computed Metrics (with embedded target-comparison view), **Engineering Template Authoring** | — |
| 3 | CAD Evidence & Change | FreeCAD Inspection (read-only + approval-gated parameter edits) | CAD edit requires approval |
| 4 | Structural CAE | Structural Adapter (preflight, deck import, approval-gated solver run, post-run extraction) | Structural solver run requires approval |
| 5 | Target Comparison | Anchor card pointing at the live comparison rendered inside Computed Metrics | Not certification |
| 6 | Review & Export | Engineering Review Support Packet, Copilot Loop history, Compare loops | Review support only |

The numbered structure mirrors the demo path below: a reviewer can follow
it top-to-bottom, and a returning user can jump straight to the section
they need. Recommended-action buttons surfaced by the Project Health Check
in Section 1 still scroll directly to the relevant card lower down.

## Scope and boundary

This demo intentionally **does**:

- inspect projects, packages, and FreeCAD evidence;
- import design targets and computed metrics;
- evaluate target comparison against existing or solver-generated metrics;
- gate every CAD parameter edit and solver run behind explicit approval;
- run an external CalculiX subprocess (when `ccx` is installed) or report
  honestly that it is unavailable;
- extract FRD/DAT results into `results/computed_metrics.json`;
- generate a Copilot Loop report and an Engineering Review Support Packet.

This demo intentionally **does not**:

- certify design safety;
- advance engineering claims automatically;
- batch-run multiple optimization candidates;
- run CFD or OpenFOAM;
- mutate CAD without explicit user approval;
- fabricate evidence when artifacts are missing.

## Prerequisites

- Backend and frontend installed per the **Fresh-clone Copilot MVP demo path**
  section of [`../README.md`](../README.md).
- Backend running at `http://127.0.0.1:8000`.
- Frontend dev server (or built bundle) reachable in the browser.
- Optional: `ccx` on `PATH` for real solver execution. Without it, the
  structural adapter reports `unavailable` honestly and the closed loop stops
  at preflight.
- Optional: `FreeCADCmd` on `PATH` for real CAD inspection / edits. Without
  it, the FreeCAD inspection card returns the stub/honest-unavailable state.

## End-to-end demo path

Each step is a UI action. Card names are the in-app labels.

1. **Open or seed a demo project.** *Project panel → Seed demo project*.
   The demo seed produces a deterministic `.aieng` package that contains
   design targets and imported computed metrics but no solver output.
2. **Run Project Health Check.** *Copilot Loop → Project Health card → Run*.
   Confirms readiness, surfaces warnings, and recommends next actions. Read-only.
3. **Inspect FreeCAD features.** *FreeCAD Inspection card → Inspect features*.
   Writes `simulation/cae_imports/parsed_features.json` and
   `graph/feature_graph.json`. No CAD edit.
4. **Review design targets.** *Design Targets card → Review*. Add or edit
   targets if needed. Each save is an explicit user write.
5. **Review / import initial computed metrics.** *Computed Metrics card →
   Preview, then Import*. Writes only `results/computed_metrics.json`. Does
   not run a solver.
5b. **(Optional) Author a parametric template draft.** *Engineering Template
    Authoring card → pick `cantilever_beam` or `plate_with_hole` → edit
    parameters → Preview draft → Save draft*. Writes only:
    `task/engineering_setup_draft.json`,
    `task/cad_template_preview.py`,
    `task/fea_setup_draft.json`, and
    `task/design_targets_suggestions.yaml`. The CAD script is **inert text
    with a safety header** — AIENG does not execute it. The suggested
    design targets are written to a separate suggestions file and never
    overwrite the user-authored `task/design_targets.yaml`; to adopt one,
    open Design Targets and add it explicitly.
6. **Run target comparison.** *Computed Metrics card* automatically refreshes
   the target comparison panel; you should see `pass`/`fail`/`unknown` per
   target with reason codes.
7. **Review CAD recommendation.** *Recommendations panel*. Recommendations
   are evidence-grounded suggestions only; they do not auto-apply.
8. **Verify a proposal.** *Recommendations → Verify*. Read-only preflight.
9. **Approve parameter edit.** *Recommendations → Approve → Approve & run*.
   The runtime pauses for explicit approval before executing
   `cad.edit_parameter`. Rejection is a first-class outcome.
10. **Confirm stale downstream evidence.** After a CAD edit, the
    `state/revalidation_status.json` flips `requires_revalidation=true` and
    downstream solver/metric artifacts are listed as stale. The Review
    Support Packet, Copilot Loop report, and Stale Evidence card all surface
    this honestly.
11. **Review structural adapter readiness.** *Structural Adapter card → Run
    structural adapter preflight*. Reports `ready`, `partial`, or
    `unavailable` per environment.
12. **Import / review a solver deck.** *Structural Adapter card → paste an
    `.inp` deck → Import solver input deck*. Writes only
    `simulation/runs/{run_id}/solver_input.inp`.
13. **Run structural preflight.** *Structural Adapter card → Review
    solver-run preflight*. Confirms mesh, settings, load case, deck, and
    `ccx` availability. Lists missing items explicitly.
14. **Approve the solver run.** *Structural Adapter card → Start
    approval-gated solver run*. The runtime pauses; click **Approve & run**
    or **Reject**.
15. **Run solver.** On approval, the runtime invokes `ccx` with `shell=False`
    in a temp dir; captured stdout/stderr/return code are written back into
    the package as `simulation/runs/{run_id}/solver_log.txt` and
    `solver_run.json`. If `ccx` is missing, the result is `unavailable` —
    never fabricated success.
16. **Extract FRD/DAT results.** Triggered automatically by `cae.run_solver`
    when `extract_results=true`. Failure is reported honestly; no metric is
    fabricated. Writes `results/computed_metrics.json` derived from the FRD.
17. **`computed_metrics.json` refresh.** The Computed Metrics card refreshes
    automatically via the `onSolverRunCompleted` callback bumped from the
    Structural Adapter card; no manual reload needed.
18. **Target Comparison refresh.** Re-evaluates the previously imported
    targets against the solver-generated metrics. Statuses move from
    `unknown` to `pass`/`fail`. Read-only.
19. **Generate Copilot Loop report.** *Copilot Loop panel → Export review*.
    Writes `reports/copilot_loop/<loop_id>.md` and a decision-review export.
20. **Export Engineering Review Support Packet.** *Engineering Review Support
    Packet card → Preview packet*, review the section checklist and
    Markdown, then *Export packet*. Writes only
    `reports/review_support/{packet_id}.md` and `.json` into the package.
    Includes header, safety boundary, project health, design targets,
    computed metrics, target comparison, FreeCAD inspection evidence, CAD
    approval records, structural solver run, Copilot loop summary, stale
    evidence, audit trail, and known limitations. Missing sections are
    reported as `missing`; certified language is forbidden.

## What the packet does and does not do

The Engineering Review Support Packet is:

- A reviewable bundle of evidence already in the project package.
- A Markdown summary plus a structured JSON manifest of section statuses
  (`included`, `partial`, `missing`, `error`) and artifact paths.
- An artifact of the workbench — generation has `claim_advancement: "none"`.

The packet is not:

- A certification of design safety.
- A signed engineering claim.
- A pass/fail verdict on the design itself.
- A substitute for qualified engineering review.

## Honest failure paths

- `ccx` not installed → preflight reports `unavailable`; solver run is not
  attempted; packet's structural-solver section reports `missing`.
- FRD missing or corrupt → extraction is not retried with fake values;
  `extracted_metrics` is not set; packet records the honest failure.
- No design targets → target comparison section reports `missing`; the
  packet does not invent targets.
- No computed metrics → packet reports `missing`; comparison section is
  `missing`.
- Package missing → export endpoint returns `ok=false` with an explicit
  error; nothing is written.
- Template parameters invalid → preview returns `ok=false` with structured
  `errors[]` (codes: `missing_required`, `invalid_value`, `out_of_range`,
  `invalid_choice`, `inconsistent_geometry`); save-draft refuses to write
  any artifact until validation passes.
- Template save when project has no package → returns `ok=false` with
  `code=package_not_found`; never writes.

## Verification commands

```bash
cd aieng-ui/backend
python -m pytest -q -k "review_support or target_comparison or structural_adapter or smoke_check"
python -m pytest -q

cd ../frontend
npm run build
```
