# AIENG Demo Release Walkthrough (v0.26)

A 5-minute walkthrough of the AIENG Decision Review Workbench. Targeted
at a new reviewer or external observer who has not used the workbench
before.

## What this demo shows

AIENG is an evidence-grounded CAD/CAE Copilot **decision review
workbench**. The demo lets you:

- Seed a deterministic bracket-lightweighting fixture project.
- Inspect two Copilot loops: one rejected, one approved.
- Compare them side-by-side.
- Load a Markdown report diff with structured "What Changed" highlights.
- Export a Markdown decision review with workspace-relative report links.
- Reset or reuse the demo project without disturbing real projects.

## What this demo does NOT show

- AIENG is **not** an autonomous engineering agent.
- AIENG does **not** certify a design.
- AIENG does **not** advance engineering claims.
- The demo does **not** run real FreeCAD, Gmsh, or CalculiX.
- The demo does **not** compare geometry or meshes visually.
- The demo's metric numbers are deterministic fixture/mock values, not
  the output of any solver that ran on your host.

## Prerequisites

- Python and Node installed.
- Workspace at `aieng-ui/`.

```bash
# backend (terminal 1)
cd aieng-ui/backend
uvicorn app.main:app --reload

# frontend (terminal 2)
cd aieng-ui/frontend
npm run dev
```

Open the workbench in your browser at the URL printed by Vite.

## Step 1 — Seed (or open) the demo project

Open the **Copilot Loop** tab. You will see the **Try the Copilot Loop
demo** landing card. Click **Seed demo project**.

What happens server-side (`POST /api/demo/copilot-loop/seed`):

- If no demo project exists, a new one is created with a
  `demo-bracket.aieng` package, two persisted loops, and two pre-baked
  reports.
- If a demo project already exists, the same project is reused — the
  workspace never gets cluttered by repeated clicks. The card shows
  `Demo project opened (reused)` instead of `Demo project ready`.
- Either way the project is automatically selected. If you want a
  guaranteed-fresh seed, click **Reset demo project**; only projects
  flagged as Copilot-loop demo are removed — real user projects are
  never touched.

The card surfaces the project id, the project name, and the next
suggested action.

## Step 2 — Inspect loop history

The history table renders below. You should see two rows:

- `demo-rejected1` — Rejected · `back_wall · thin · thickness_mm: 20.0 → 10.0`
- `demo-approved1` — Approved · same proposal, mock CAD edit applied

Each row shows the decision badge, proposal one-liner, warning/error
counts, and the report filename. Click **Reopen** on either row to load
the full stepper view for that loop.

## Step 3 — Compare the two loops

Tick the **Compare** checkbox on both rows, then click
**Compare selected (2/2)**. The side-by-side compare panel renders, with
rows for updated timestamps, statuses, approval decisions (Rejected vs
Approved), proposals, verification verdicts, stale artifact counts,
warning/error counts, metric delta summary, design target summary, and
report paths.

## Step 4 — Load the report diff and read What Changed

Click **Load report diff**. The endpoint
`GET /api/projects/{id}/copilot-loops/compare-reports` is called.

Above the unified diff you'll see the **What changed** table — structured
highlights derived from the loops' persisted state and report presence:

- `approval_decision`: **changed** · **critical** · rejected → approved.
- `proposal`: **unchanged** · info.
- `verification_status`: **unchanged** · info.
- `stale_artifacts`: **changed** · warning · 0 → 3.
- `metric_summary` / `target_summary`: changes per the demo fixture.
- `warnings_errors`: **changed** · warning.
- `report_availability`: **unchanged** · info.
- `claim_boundary_presence`: **unchanged** · info.

Below the table, the unified diff shows exactly which Markdown lines
differ. Toggle **Show raw reports** to flip to a side-by-side raw view.

## Step 5 — Export a decision review

Scroll down to **Export decision review**. Tick the checkboxes for the
slices you want:

- Include **What Changed** highlights (recommended).
- Include **unified report diff** (recommended).
- Embed **both raw reports** (optional — produces a larger artifact,
  excerpts are capped per side with an explicit "see linked full report"
  notice).

Click **Export review**. The endpoint
`POST /api/projects/{id}/copilot-loops/export-review` writes a Markdown
artifact to `reports/copilot_loop_review/<utc_timestamp>.md` inside the
`.aieng` package and to the local project workspace, then returns a
preview.

The export contains:

- Title and per-loop summary.
- Per-loop **relative report links** (`../copilot_loop/<id>.md`) — you
  can paste the export anywhere in the workspace and the links resolve
  to the actual reports.
- Optional What Changed table.
- Optional unified diff (capped with a link-out hint if large).
- Optional capped raw report excerpts.
- Collected warnings.
- Limitations.
- Explicit claim boundary in English and Chinese.

## Step 6 — Read the claim boundary

Both the in-app preview and the exported Markdown carry the same
parallel claim boundary:

> This decision review export is a reviewable record of one or two
> Copilot loops. It does not certify either design, does not advance
> engineering claims, and must be reviewed by a qualified engineer
> before being cited in any acceptance decision.
>
> This review export does not certify design safety, does not auto-advance engineering claims, and must be reviewed by a qualified engineer.

The export is a **textual record** — it is not a substitute for an
engineering review of the underlying package, evidence, and audit log.

## Known limitations

- Mesh/solver execution is honestly reported as unavailable in the
  demo; success is never faked.
- Demo metric deltas are pre-baked. They illustrate the workflow but
  are not the output of a solver that ran on your host.
- Report diff is line-level; no semantic section-level diff.
- The export is line-oriented Markdown; no images, no in-app deep links
  beyond the workspace-relative paths.
- Demo seed is idempotent at the kind level (`bracket-lightweighting`);
  a single workspace currently supports one Copilot-loop demo project at
  a time.

## Test commands

```bash
# Headline end-to-end smoke test
cd aieng-ui/backend
python -m pytest tests/test_api.py -q -k "demo_smoke_check or v05_demo_smoke"

# Full Copilot-loop test selection
python -m pytest tests/test_api.py -q -k copilot_loop

# Full backend
python -m pytest tests/test_api.py -q   # 411 passed, 3 skipped

# Frontend build
cd ../frontend
npm run build
```

## REST surface in 30 seconds

| Method | Path                                                                      |
|--------|---------------------------------------------------------------------------|
| POST   | `/api/demo/copilot-loop/seed`                                             |
| POST   | `/api/demo/copilot-loop/reset`                                            |
| POST   | `/api/demo/copilot-loop/smoke-check`                                      |
| GET    | `/api/projects/{id}/copilot-loops`                                        |
| GET    | `/api/projects/{id}/copilot-loops/compare-reports?left=...&right=...`     |
| POST   | `/api/projects/{id}/copilot-loops/export-review`                          |
| GET    | `/api/projects/{id}/copilot-loop/{loop_id}`                               |
| POST   | `/api/projects/{id}/copilot-loop/{loop_id}/advance`                       |
| POST   | `/api/projects/{id}/copilot-loop/{loop_id}/approve`                       |
| POST   | `/api/projects/{id}/copilot-loop/{loop_id}/reject`                        |
| GET    | `/api/projects/{id}/copilot-loop/{loop_id}/report`                        |

For the full feature reference see
[closed-loop-copilot-stepper.md](./closed-loop-copilot-stepper.md). For
the step-by-step demo script see
[copilot-loop-demo-scenario.md](./copilot-loop-demo-scenario.md).


## Step 6 — Demo health check (v0.6)

The workbench includes a built-in **Demo health check** that runs the
deterministic demo chain against your local backend and reports a
structured pass/fail checklist. This is useful for:

- Verifying the demo works on your machine before showing it to a reviewer.
- Catching configuration drift or broken fixtures after code changes.
- Giving external reviewers confidence that the local stack is healthy.

### How to run it

1. Open the **Copilot Loop** tab.
2. In the **Try the Copilot Loop demo** card, click **Run demo health check**.
3. Optional: click **Reset & check** to recreate the demo project from
   scratch before running the checks.

### What it checks

The health check performs the following steps automatically:

1. **Seed or reuse** the bracket-lightweighting demo project.
2. **List loops** and verify two loops exist.
3. **Identify decisions**: one rejected loop and one approved loop.
4. **Compare reports** and verify a diff is generated.
5. **Verify highlights** include `approval_decision` with `changed` status.
6. **Export review** as a two-loop Markdown artifact with highlights and diff.
7. **Verify export artifact** exists in the `.aieng` package or project-local
   storage.
8. **Verify claim boundary** in English and Chinese is present in the export.
9. **Verify no prohibited certification language** appears (e.g.
   "design is certified", "claim accepted", "certified safe").
10. **Verify severity** of the approval-decision highlight is `critical`.

### Interpreting results

- **Green / passed**: every check passed. The demo chain is healthy.
- **Red / failed**: one or more checks failed. Review the checklist rows for
  details. Common causes:
  - A demo loop file was deleted or corrupted.
  - The claim-boundary text was accidentally modified.
  - A prohibited certification phrase leaked into an export template.
- **Warnings**: non-critical issues (e.g. package writeback failed but local
  export succeeded). Warnings do not cause a failure.

### Safety boundaries

- The health check only operates on **demo-flagged projects**.
- It never reads, modifies, or deletes **real user projects**.
- It does not run FreeCAD, Gmsh, CalculiX, or any real solver.
- It does not certify the design or advance engineering claims.
