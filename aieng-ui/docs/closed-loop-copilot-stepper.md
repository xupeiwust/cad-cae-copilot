# Closed-loop Copilot Stepper

The Closed-loop Copilot Stepper turns existing AIENG capabilities into a
reviewable CAD/CAE workflow inside the web workbench.

It is a workflow UX and orchestration layer. It does **not** add a new CAD
adapter, solver, generic text-to-CAD system, or autonomous optimizer.

v0.26 note: this is now the closed-loop Copilot MVP demo path. It connects
Project Health Check, read-only FreeCAD inspection, design targets, computed
metrics, recommendation, verification, approval-gated CAD edit fixture, stale
evidence, target comparison, loop report, report comparison, demo smoke check,
and decision review export into one runnable workbench path. For the issue #10
acceptance walkthrough, see
[copilot-loop-v0.26-demo-walkthrough.md](./copilot-loop-v0.26-demo-walkthrough.md).

v0.34 note — **Engineering Template Authoring**. The Copilot Loop Inputs
section also hosts a card that turns a small set of controlled parametric
templates (`cantilever_beam`, `plate_with_hole`) into a reviewable draft
under `task/engineering_setup_draft.json`, with a separate inert
`task/cad_template_preview.py` script, a structured
`task/fea_setup_draft.json` setup, and `task/design_targets_suggestions.yaml`
suggestions.

Safety:

- Templates are controlled — no free-form user Python, no arbitrary
  FreeCAD commands, no text-to-CAD.
- The generated CAD script is **draft only**; AIENG does not execute it.
- The FEA setup is **draft only**; no solver input deck is produced as a
  side effect.
- Saving the draft does **not** modify the user-authored
  `task/design_targets.yaml`; suggested targets land in a separate file
  the comparison engine never reads.
- **No external tool runs** as part of preview or save (`subprocess.run`
  is asserted absent in the test suite).
- After review the user must continue through the existing CAD edit and
  structural solver workflows, which remain approval-gated.
- Claim boundary: the draft does not certify the design and does not
  advance any engineering claim.

v0.35 note - **Template to Design Targets handoff**. After previewing or
saving a controlled engineering template, the workbench can explicitly adopt
its target suggestions into the existing Design Targets artifact
`task/design_targets.yaml`. This closes the metadata handoff from draft setup
to measurable targets without creating a new comparison path.

Safety boundaries for adoption:

- Adoption is a user-clicked write to `task/design_targets.yaml` only.
- It does not execute the generated CAD script, FreeCAD, Gmsh, CalculiX, mesh
  generation, solver runs, or postprocessing.
- It does not modify `task/fea_setup_draft.json` or promote the draft FEA setup
  into a solver deck.
- Duplicate target IDs are skipped unless an explicit overwrite flag is used by
  the backend caller.
- Adopted targets remain review metadata; they do not certify safety and do not
  advance claims.
- The UI prompts the user to rerun the read-only Project Health Check so the
  missing-target guidance can update.


v0.36 note - **Template to safe CAD fixture**. A reviewed controlled template
can now be materialized as deterministic geometry metadata at
`geometry/template_cad_fixture.json`. This is a fixture artifact for AIENG
review and future adapter handoff, not a real CAD/B-rep export.

Safety boundaries for CAD fixture generation:

- The write is explicit and approval-required in the UI.
- It creates `geometry/template_cad_fixture.json` and updates the standard
  stale revalidation marker only.
- It does not execute FreeCAD, CadQuery, Gmsh, CalculiX, Python macros, mesh
  generation, solver runs, or postprocessing.
- It does not create STEP, STL, FCStd, or solver input decks.
- It marks downstream mesh, solver, metrics, and summaries stale so old results
  are not implied to validate the new fixture geometry.
- Claim advancement remains `none`.

Status: **v0.5** — Demo Release Candidate. Idempotent + resettable
demo seed (no workspace clutter), export artifacts now carry
workspace-relative report links with capped inline excerpts, end-to-end
demo smoke test, in-app demo landing card with auto-select, and tighter
empty/error states. Builds on v0.4 Decision Review Workbench (highlights
+ demo seed + export), v0.3 report diff, v0.2 multi-loop history, and
v0.1 hardening.

For the 5-minute walkthrough see
[demo-release-walkthrough.md](./demo-release-walkthrough.md).

## What this demo shows

For a selected project with a `.aieng` package, the stepper guides one bounded
loop with 11 steps:

1. Inspect package evidence.
2. Recommend a CAD modification.
3. Verify the proposal before mutation.
4. Submit an approval-gated CAD parameter edit.
5. Show downstream stale evidence.
6. Prepare a mesh/solver preflight.
7. Run mesh/solver only if existing runtime gates and environment allow it.
8. Extract solver results when result files exist.
9. Refresh CAE summaries.
10. Compare before/after metrics and design targets when available.
11. Generate a loop report.

The backend persists loop state under `projects/{id}/copilot_loops/` so a
browser refresh can reload the stepper. The UI calls
`GET /api/projects/{id}/copilot-loops` on mount and silently restores the
most recent loop.

## What this demo does NOT show

- It does not certify a design.
- It does not advance engineering claims automatically.
- It does not hide approval gates.
- It does not fake FreeCAD/Gmsh/CalculiX success when tools are missing.
- It does not perform topology-changing CAD edits.
- It does not run autonomous optimization loops.

## Guided Readiness Workflow

The Project Health Check's suggested actions are connected to the workbench as
safe navigation aids. A health action such as **Add measurable design targets**
can show an **Open Design Targets** button that expands, scrolls to, and
temporarily highlights the relevant card.

This is not an auto-fix workflow. Health action buttons do not mutate the
package, save metadata, edit CAD, run mesh/solver tools, approve loop steps, or
advance engineering claims. They only help the user find the right section.

After the user explicitly saves design targets in the Design Targets card, the
UI prompts them to run the read-only Project Health Check again. If the saved
targets validate, the missing-design-target recommended action disappears on
the next health check.

## Computed Metrics Import

Design targets are only useful for review when matching computed metrics exist.
The **Computed Metrics** card lets users explicitly import postprocessed scalar
metrics without running a solver.

Accepted import formats:

- **JSON full document** with `schema_version`, optional `global_metrics`, and
  `load_cases`.
- **JSON simple object**, for example
  `{"max_von_mises_stress": {"value": 187.4, "unit": "MPa"}}`.
- **CSV text** with required columns `metric,value` and optional
  `unit,load_case_id,source`.

The preview step parses and validates input, counts metrics/load cases, and
shows target mapping:

- `mapped`: target metric is available globally or in the requested load case;
- `missing_metric`: no matching metric is available;
- `ambiguous`: metric exists in multiple load cases and the target has no
  `load_case_id`;
- `unknown`: target does not declare a usable metric.

Preview is read-only. Saving writes only:

```
results/computed_metrics.json
```

Saving computed metrics does **not** edit CAD, generate mesh, run a solver,
refresh claims, or certify design safety. Imported metrics are evidence inputs
for review; target comparison and engineering conclusions still require human
engineering review.

## How to run

```bash
# backend
cd aieng-ui/backend
uvicorn app.main:app --reload

# frontend
cd aieng-ui/frontend
npm run dev
```

Open the workbench, pick a project that ships with a `.aieng` package
containing design targets, parsed features, per-feature stress, and an
editable parameter (the recommendation step requires this evidence). Switch
to the **Copilot Loop** tab and:

1. Click **Start loop**.
2. Click **Advance next step** repeatedly until an approval card appears.
3. Click **Approve & execute** or **Reject**.
4. Continue advancing through stale-evidence display, solver preflight,
   metric comparison, and report generation.

## Approval, rejection, and stale evidence

Mutation and expensive operations are routed through the existing runtime
approval gate. At v0.1 the main approval-gated step is `cad.edit_parameter`.

- **Approve** resumes the gated run; the parameter is edited, and downstream
  geometry-dependent artifacts are explicitly marked stale.
- **Reject** marks the step `skipped` (not `error`). The package is left
  **byte-identical**, no stale evidence is introduced, and the loop report
  records the rejection explicitly. Subsequent geometry-dependent steps
  operate on the unchanged baseline or are skipped.

The UI distinguishes `completed`, `partial`, `skipped`, `error`, and
`waiting_for_approval`. Each empty/unavailable case has its own card so the
panel never shows a blank region or `undefined` value:

- No applicable proposal → explicit "No CAD modification proposal" card.
- Failed verification → block notice, mutation step is skipped.
- Solver unavailable → "Mesh/solver not executed" card with reason.
- No metric delta → "No before/after metric delta available" card.
- Report not generated yet → "Report not generated yet" card.
- Loop rejected → top-level "CAD edit was rejected" callout.

## Loop report

The final step writes a markdown report to:

```
reports/copilot_loop/{loop_id}.md
```

It always includes:

- Loop id, project id, package path, generated-at timestamp.
- Step status with warnings/errors per step.
- Selected CAD proposal (if any) and apply decision.
- Rejection notice when applicable.
- Stale downstream artifacts list.
- Mesh/solver readiness (preflight, missing items).
- Before/after metrics and design target comparison when evidence is
  available.
- Explicit claim boundary statement, in English and Chinese:

> This report does not certify the design, does not advance engineering
> claims automatically, and must be reviewed by a qualified engineer.
>
> This report does not certify design safety, does not auto-advance engineering claims, and must be reviewed by a qualified engineer.

- Limitations section reminding readers that a proposal is a hypothesis,
  solver success is not engineering validation, verification is heuristic,
  and claim advancement requires a separate explicit workflow.

## Loop history and comparison

The Copilot Loop panel includes a **history table** listing all loops
persisted for the current project, newest first. Each row shows:

- loop id and "Open" indicator when this loop is currently reopened;
- last-updated timestamp;
- overall loop status badge (and a `waiting` badge if a step is currently
  awaiting approval);
- approval decision: `Approved`, `Rejected`, `Pending approval`,
  `Blocked (verification)`, `Error`, or `No decision`;
- concise proposal summary (feature · action · parameter from→to);
- warning / error counts;
- report path when a report was generated.

### How to reopen an older loop

Click **Reopen** on any row. The full loop document is fetched and replaces
the stepper view. You can still advance, approve, or reject the reopened
loop as long as it has unfinished steps — the runtime persistence contract
is the same as for the most recent loop.

### How to compare two loops

Tick the checkbox on exactly **two** rows, then click **Compare selected**.
A side-by-side table renders both loops on the following dimensions:

- updated timestamp;
- loop status;
- approval decision (with rejected loops clearly marked as decision records,
  not engineering failures);
- proposal summary;
- verification verdict;
- stale artifact count;
- warning / error counts;
- before/after metric delta summary (improved · regressed · unchanged ·
  unknown);
- design target comparison summary (pass · fail · unknown · not_evaluated);
- report path.

### What this comparison means

It is a decision-review aid. It shows what each Copilot loop proposed,
which decision was recorded, and what evidence was available at the time.

### What this comparison does NOT mean

- It does **not** certify either design.
- It does **not** advance engineering claims.
- It does **not** invent or interpolate missing metrics — missing values are
  rendered honestly as `Unknown` or `Not available`.
- It does **not** treat a rejected loop as a failed engineering result. A
  rejection is a legitimate decision record.
- It does **not** compare geometry visually. The comparison operates on the
  summary metadata persisted with each loop.

Claim-boundary reminder: a qualified engineer must review the underlying
reports and evidence before accepting any design conclusion drawn from
this view.

## Report diff in loop comparison

The compare panel exposes an on-demand **report diff** that loads the two
Markdown reports referenced by `report_path` and renders a unified diff.

### How to use it

1. In the loop history table, tick the checkbox on exactly two rows.
2. Click **Compare selected**.
3. Inside the compare panel, click **Load report diff**.
4. Toggle **Show raw reports** to see the two reports side-by-side instead
   of the unified diff.

The diff is only fetched when you ask for it — it is never auto-loaded.

### What the diff means

It is a textual delta between two persisted Markdown reports. It tells you
exactly what changed in each loop's documented decision: proposal,
verification result, approval/rejection, stale artifacts, mesh/solver
status, before/after metrics, design target comparison, warnings,
limitations, and claim-boundary section.

### What the diff does NOT mean

- It does **not** certify either design.
- It does **not** advance engineering claims.
- It does **not** compare raw geometry, mesh, or solver outputs.
- It does **not** invent or interpolate missing report content. Missing
  reports are shown as `Not available` and the diff is suppressed.
- A textual difference between two reports is not a substitute for
  engineering review of the underlying evidence.

### Missing-report behavior

If a loop has not yet generated a report (early step, rejected before
report generation, or the loop document predates v0.1), the endpoint
returns a clean unavailable response with a warning per missing side. No
report is auto-generated. The UI surfaces the warning and suppresses the
diff text.

### Safety

- Reports are only read from package members matching
  `reports/copilot_loop/<id>.md`. Tampered persisted state pointing at any
  other path is rejected with a warning, not read.
- Local fallback reads are restricted to the project's own
  `copilot_loops/` directory and never traverse outside it.
- Loops must belong to the requested project; cross-project loop IDs 404.
- Reports above 200 kB are truncated for the diff and a warning is added.

## What Changed highlights (v0.4)

The report diff response now carries a `highlights` array of structured,
severity-tagged comparisons derived from persisted loop state. The
compare panel renders these as a "What changed" table above the unified
diff:

- **approval_decision** — critical when changed (e.g. rejected → approved).
- **proposal** — warning when changed.
- **verification_status** — critical if verdict regresses (pass→warn or
  pass→fail); otherwise warning when changed.
- **stale_artifacts** — warning when the count changes.
- **metric_summary** — warning when the metric-direction histogram
  changes; missing when neither loop has metrics.
- **target_summary** — warning when the design-target status histogram
  changes; missing when neither loop has targets.
- **warnings_errors** — warning when totals change.
- **report_availability** — warning when one or both reports are missing.
- **claim_boundary_left / claim_boundary_right / claim_boundary_presence** —
  critical when a present report does not contain a claim-boundary
  statement; informational when both reports include one.

Highlights are a guide, not a replacement for the unified diff. They do
not interpret missing report content and do not advance engineering
claims.

## Decision review export (v0.4)

The compare panel exposes an **Export review** action. The endpoint:

```
POST /api/projects/{id}/copilot-loops/export-review
```

Request body:

```json
{
  "loop_ids": ["abc123", "def456"],
  "include_reports": false,
  "include_diff": true,
  "include_highlights": true
}
```

Supports one or two loops. The Markdown artifact is written to:

```
reports/copilot_loop_review/{utc_timestamp}.md
```

The export path is constructed server-side from a constant prefix and a
UTC timestamp — client request fields cannot influence the output path.
Loop IDs are regex-validated (`^[A-Za-z0-9_-]{4,64}$`) and resolved
through project-scoped storage, so cross-project access is impossible.

Every export contains:

- Title (single-loop record / two-loop comparison).
- Project id, loop ids, generated timestamp.
- Per-loop decision, verification, proposal, stale count, metrics,
  target, warnings/errors, report path.
- "What changed" highlights table (for two-loop exports with
  `include_highlights`).
- Unified report diff (for two-loop exports with `include_diff`).
- Embedded raw reports (with `include_reports`).
- Warnings collected during export.
- Limitations section.
- Explicit claim-boundary statement, in English and Chinese parallel.

Missing reports are noted as `_Report not available._`; nothing is
auto-generated.

## Demo scenario (v0.4)

A deterministic demo can be seeded with:

```
POST /api/demo/copilot-loop/seed
```

The endpoint creates a new project with a bracket-lightweighting
`.aieng` package and two pre-baked Copilot loops:

- `demo-rejected1` — back-wall thinning rejected; baseline unchanged.
- `demo-approved1` — back-wall thinning approved with a mock CAD edit;
  downstream evidence marked stale; mesh/solver remained skipped because
  no real toolchain is available.

Both loops have generated reports. The UI's **Seed demo project** button
calls this endpoint and surfaces the new project id.

All demo data is clearly labelled as `mock/fixture` and the pre-baked
reports include the same EN+ZH claim-boundary statement as live reports.
Demo data does not represent real simulation; it is a deterministic
decision record suitable for product demos and reviewer onboarding.

See [copilot-loop-demo-scenario.md](./copilot-loop-demo-scenario.md) for
the step-by-step demo script.

## Demo release UX (v0.5)

The Copilot Loop panel now opens with a **"Try the Copilot Loop demo"**
landing card. It explains in three bullets what the demo creates and what
it does *not* claim, then offers **Seed demo project**. After seeding:

- The card auto-selects the new project (the panel calls the parent
  `onSelectProject` callback, which routes through the same project
  refresh path as manual selection).
- A success block shows the project id, project name, loop count
  (`2 pre-baked — one rejected, one approved`), and the suggested
  next action.
- On subsequent clicks the same demo project is returned with
  `reused=true`, so repeated clicks do not pollute the workspace.
- A **Reset demo project** button appears once a demo exists; it removes
  only projects flagged as Copilot-loop demo and then re-seeds. Real
  user projects are never touched.

The history table also gains friendlier empty/single-loop hints — when
only one loop exists, the comparison action is disabled and an inline
hint explains why.

## Idempotent demo seed and reset (v0.5)

Demo projects now carry explicit metadata:

```json
{
  "demo": true,
  "demo_copilot_loop": true,
  "demo_kind": "bracket-lightweighting",
  "demo_notice": "Demo fixture data. Computed values are mock/fixture inputs, not real simulation results."
}
```

`POST /api/demo/copilot-loop/seed` is idempotent at the
`demo_kind` level: a subsequent call returns the existing demo project
unchanged (`reused: true`). To force a clean re-seed, pass
`{"reset": true}` in the payload — that deletes existing demo projects
first. The dedicated `POST /api/demo/copilot-loop/reset` endpoint
removes all demo projects without re-seeding.

Both paths only touch projects whose metadata flags them as Copilot-loop
demo fixtures. Real user projects are never modified.

## Export link-outs and caps (v0.5)

The decision review export now uses workspace-relative report links:

```markdown
- Report: [`reports/copilot_loop/<id>.md`](../copilot_loop/<id>.md)
```

When `include_reports=true`, the export embeds a capped excerpt per side
(`_EMBEDDED_REPORT_CAP = 4_000` chars) with an explicit
`[…truncated at 4000 chars — see linked full report above]` notice. The
linked-out URL points to the full report in the same workspace. The
unified diff, when included, is capped at 4× that (so the diff can be
larger than a single side's report excerpt) with its own truncation
notice and warning.

Result: the export remains small and reviewable, the audit chain
remains intact, and missing reports are still surfaced as
`- Report: Not available` without any fabricated link.

## REST endpoints

| Method | Path                                                                      |
|--------|---------------------------------------------------------------------------|
| GET    | `/api/projects/{id}/copilot-loops`                                        |
| GET    | `/api/projects/{id}/copilot-loops/compare-reports?left=...&right=...`     |
| POST   | `/api/projects/{id}/copilot-loops/export-review`                          |
| POST   | `/api/projects/{id}/copilot-loop/start`                                   |
| GET    | `/api/projects/{id}/copilot-loop/{loop_id}`                               |
| POST   | `/api/projects/{id}/copilot-loop/{loop_id}/advance`                       |
| POST   | `/api/projects/{id}/copilot-loop/{loop_id}/approve`                       |
| POST   | `/api/projects/{id}/copilot-loop/{loop_id}/reject`                        |
| GET    | `/api/projects/{id}/copilot-loop/{loop_id}/report`                        |
| POST   | `/api/demo/copilot-loop/seed`                                             |
| POST   | `/api/demo/copilot-loop/reset`                                            |
| POST   | `/api/demo/copilot-loop/smoke-check`                                      |

## Test commands

```bash
# focused
cd aieng-ui/backend
python -m pytest tests/test_api.py -q -k "copilot_loop"

# full backend (now 411 passed, 3 skipped)
python -m pytest tests/test_api.py -q

# headline end-to-end smoke test
python -m pytest tests/test_api.py -q -k v05_demo_smoke

# frontend build
cd ../frontend
npm run build
```

## Known limitations

- One step at a time; there is no "run all safe steps" mode.
- Recovery restores only the most recent loop per project; older loops are
  reachable via the list endpoint but not surfaced as a switcher in the UI.
- Metric comparison depends on `results/computed_metrics.json` and/or
  `results/result_summary.json` being present.
- Geometry-kernel validity checks are still outside the verifier.
- Real solver execution still requires FreeCAD/Gmsh/CalculiX on the host and
  a prepared input deck; the stepper reports the honest blocker but does not
  install or configure them.

## Safety boundaries (v0.1 + v0.2 test coverage)

v0.1:

- Reject → package is byte-identical, no stale-evidence marker introduced.
- Mutation step truly waits for approval; package bytes unchanged before
  approve.
- Handler exception → step becomes `error`, never leaks `running` state.
- Solver unavailable → step is `skipped`/`partial`/`error`, never
  `completed`.
- Loop state persists across server restart and is recoverable via the
  list endpoint.
- Report contains the claim-boundary statement (EN + ZH) and explicit
  rejection notice when applicable.

v0.2:

- Rejected loops summarize as `decision = "rejected"`, never `error`.
- Approved loops summarize as `decision = "approved"`.
- Pending-approval loops summarize as `decision = "pending"`.
- Legacy on-disk loops without v0.2 fields list safely; derived fields are
  `None` rather than `undefined`.
- Report path is exposed in the summary once a report exists.
- Warning and error counts are derived from persisted state, not invented.
- Multiple loops list newest-first with the full v0.2 summary contract.

v0.3:

- Report diff is on-demand only; reports are never auto-generated.
- Missing reports → clean unavailable response with warnings, not 500.
- Tampered `report_path` (traversal / absolute / non-report prefix) is
  rejected at the safe-member layer; suspicious paths are never read.
- Cross-project loop IDs cannot escape the requested project (404).
- Oversized reports are truncated with a warning before diffing.
- Diff response always carries an explicit claim-boundary statement.

v0.4:

- Highlights are derived deterministically from persisted loop state;
  no values are fabricated.
- Claim-boundary absence in a present report is surfaced as a
  **critical** highlight, never silently passed.
- Export path is server-generated from a constant prefix +
  timestamp — client cannot influence the output path.
- Loop IDs in the export request are regex-validated and resolved
  through project-scoped storage (cross-project export rejected 404).
- Empty or oversized `loop_ids` payload → 400, not silent default.
- Missing reports during export produce explicit warnings and
  `_Report not available._` in the artifact; nothing is auto-generated.
- Demo seed creates fixture data clearly labelled mock/fixture; demo
  reports contain the EN+ZH claim boundary and explicitly do not claim
  certification.

v0.5:

- Demo seed is idempotent at the `demo_kind` level and reuses an
  existing demo project by default — repeated clicks cannot clutter the
  workspace.
- The reset endpoint only deletes projects flagged as Copilot-loop demo;
  real user projects are never modified.
- Project deletion is bounded with a `relative_to` containment check
  against `settings.projects_root`, so a malformed project id cannot
  escape the workspace root.
- Exports now use **workspace-relative** report links instead of
  inlining whole reports by default; embedded raw reports are capped per
  side with an explicit "see linked full report" notice and warning.
- The unified diff in the export is similarly capped with a link-out
  hint when oversized; the warning is recorded in the export response.
- Missing-report exports still produce `- Report: Not available` rather
  than fabricated links.
- All v0.4 export safety boundaries (server-generated path, regex-bounded
  loop ids, cross-project rejection, no auto-generation) are preserved.
- A new end-to-end smoke test (`test_v05_demo_smoke_seed_list_compare_export`)
  exercises the full seed → list → compare → highlights → export chain
  deterministically.

## Project Health Check (v0.8)

A read-only inspection endpoint `GET /api/projects/{project_id}/health-check` and
corresponding UI card let users verify a project's readiness before starting a
Copilot Loop.

### What it checks

- **Package**: `.aieng` file exists, is readable as ZIP, and contains a valid
  `manifest.json`.
- **Evidence**: evidence index is readable and not older than 7 days.
- **CAD context**: CAD context document readable, editable parameters present.
- **CAE artifacts**: CAE result artifacts present (if applicable).
- **Design targets**: design targets defined.
- **Claims**: claim boundary present in exports; no prohibited certification
  language.
- **Loops**: existing loop count and reports readable.
- **Demo metadata**: flagged if the project is a deterministic demo fixture.

### What it does NOT do

- It does **not** write to the `.aieng` package.
- It does **not** run solvers or subprocesses.
- It does **not** advance engineering claims.
- It does **not** create or delete loops.

### Readiness levels

| Level | Meaning |
|---|---|
| `ready` | Package readable + enough CAD/CAE/target evidence + no failed safety checks |
| `partial` | Package readable but key inputs missing or stale evidence |
| `not_ready` | Package missing, unreadable, or manifest missing |
| `unknown` | Insufficient information to determine readiness |

### Mutation guard

The health check computes a SHA-256 digest of the `.aieng` package before and
after inspection. If the digest changes, a warning is appended to the response.
This guarantees read-only behavior even if future refactors accidentally add
side effects.

### UI integration

The Copilot Loop panel includes a **Project Health Check** card with:
- A **Run health check** button (disabled when no project is selected).
- A color-coded readiness banner (green = ready, yellow = partial, red = not_ready).
- A checklist of individual checks with status badges and next-action hints.

## Health-to-Action Guidance (v0.9)

The Project Health Check response now includes `recommended_actions`: a list of
safe, read-only next-action suggestions derived from failed, warning, and
unknown checks.

### What actions are

- **Deterministic**: generated from check state, not from LLM or heuristics.
- **Read-only**: every action declares `mutates_package=false`,
  `runs_solver=false`, `advances_claim=false`.
- **Guidance only**: they do not modify the project, run solvers, or advance
  claims automatically.
- **Sorted by priority**: high → medium → low, with package/manifest first,
  evidence next, CAD/CAE/targets next, loop/report/export next, demo notes last.

### Action types

| Type | Meaning |
|---|---|
| `manual` | User must perform the step outside the workbench (e.g., edit YAML, re-export package) |
| `navigate` | User can navigate to a relevant UI section (e.g., Copilot Loop tab) |
| `run_read_only_tool` | Run a read-only inspection tool (reserved for future use) |
| `start_loop` | Start a new Copilot Loop (reserved for future use) |
| `compare_loops` | Open the loop comparison panel (reserved for future use) |
| `export_review` | Open the export review flow (reserved for future use) |

### UI rendering

The Project Health Check card renders actions grouped by priority:
- Each action shows a priority badge, label, summary, action type, and safety badges.
- Source check IDs are visible in small text so users understand why the action was suggested.
- If no actions exist, the UI shows: "No suggested actions. This project appears ready for the current Copilot Loop review workflow."
- There are **no auto-fix buttons**.

### Safety boundaries preserved

- No automatic engineering claim advancement.
- No design certification.
- No CAD edits.
- No solver execution.
- No package mutation.
- No one-click auto-fix.
- No fabricated metrics.
- No guessed evidence.
- Missing data remains missing/unknown.
- Actions are guidance only; users remain responsible for engineering judgment.

### Refresh transparency — last-refreshed timestamps (v0.22)

Every card that loads data from the package now shows when that data was last
fetched:

- **Design Targets** — `Last refreshed: 5/19/2026, 1:05:15 PM` (or "Not loaded yet").
- **Computed Metrics** — same pattern.
- **FreeCAD Inspection** — same pattern.

Timestamps are local frontend state; they update on every successful GET and
clear on full page reload. They help users distinguish stale cached data from a
fresh load.

### Health action navigation refresh (v0.21)

Clicking a `navigate`-type health action now performs three consistent steps:

1. **Open/focus** the relevant card (expand if collapsed, scroll into view,
   briefly highlight).
2. **Refresh** the card's current data from the package via a read-only GET.
3. **Wait** for the user to decide what to do next.

Cards that support this:

- **Design Targets** — refreshes existing targets.
- **Computed Metrics** — refreshes existing metrics.
- **FreeCAD Inspection** — refreshes existing inspection evidence.

This is strictly read-only. No package mutation, no solver run, no CAD
inspection, no metrics import, no target save, no claim advancement.

## Design Targets Authoring & Import (v0.10)

A user-driven workflow for adding measurable design targets to a project so that
the Copilot Loop can compare metrics against explicit goals.

### Endpoints

- `GET /api/projects/{project_id}/design-targets` — read targets from the package.
- `PUT /api/projects/{project_id}/design-targets` — validate and save targets into
the package.

### Package artifact path

`task/design_targets.yaml`

This matches the existing convention used by the health check, copilot loop
evidence inspection, and demo fixtures.

### Target schema

```yaml
schema_version: "0.1"
targets:
  - target_id: mass_reduce_10pct
    label: Mass reduction
    metric: mass_kg
    operator: reduce_by_at_least
    value: 10
    unit: "%"
    priority: required
    rationale: Reduce bracket mass by 10% while maintaining safety factor.
```

Supported operators: `<=`, `>=`, `<`, `>`, `==`, `reduce_by_at_least`,
`increase_by_at_least`, `reduce_by_percent`, `increase_by_percent`.

Supported priorities: `required`, `preferred`, `informational`, `high`, `medium`,
`low`, `critical`.

### Validation

- `target_id` is required, alphanumeric/underscore/hyphen only, max 128 chars.
- `label` and `metric` are required, max 500 chars.
- `operator` must be in the supported set.
- `value` must be numeric (not NaN).
- No duplicate `target_id` values within the same document.
- Maximum 100 targets per document.
- Payload can be an array of targets or a document object with a `targets` array.

### UI

The **Design Targets** card in the Copilot Loop panel provides:
- A table of existing targets with ID, label, metric, operator, value, priority.
- **Add target** form with all fields.
- **Edit** and **Delete** per target.
- **Import JSON** textarea for bulk import.
- **Refresh** button to reload from the package.
- Success / error messages after save.

### What saving targets does NOT do

- It does **not** edit CAD geometry.
- It does **not** run a solver or mesher.
- It does **not** advance engineering claims.
- It does **not** create `ai/claim_map.json` or claim proposals.
- It does **not** auto-start a Copilot Loop.
- It writes **only** the `task/design_targets.yaml` artifact.

### Health check integration

After saving valid targets:
- The `design_targets` health check changes from `warning` to `passed`.
- The `add_design_targets` recommended action disappears.
- The target count is reflected in the health check summary.
