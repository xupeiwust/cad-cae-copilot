# Copilot Loop Demo Scenario — Bracket lightweighting decision review

A 5-minute walkthrough of the AIENG Decision Review Workbench using a
deterministic demo project. No real FreeCAD/Gmsh/CalculiX is required.

## What this demo shows

- A reviewable Copilot loop record for a bracket-lightweighting problem.
- Two outcomes side-by-side: one rejected, one approved with a mock CAD
  edit.
- Loop history table and reopening older loops.
- Side-by-side loop comparison.
- Markdown report diff with structured "What Changed" highlights.
- One-click Markdown decision review export.

## What this demo does NOT show

- It does **not** run real FreeCAD, Gmsh, or CalculiX.
- It does **not** certify either bracket design.
- It does **not** advance engineering claims.
- It does **not** compare raw geometry visually.
- It does **not** invent missing metrics — anything not derivable from
  the fixture data is shown as `Unknown` or `Not available`.

The pre-baked metric numbers are fixture/mock data. They are deterministic
so the demo is reproducible, but they are not the output of any solver
that ran on your machine.

## Prerequisites

- Python and Node already set up for the workbench.

```bash
# backend
cd aieng-ui/backend
uvicorn app.main:app --reload

# frontend (in another shell)
cd aieng-ui/frontend
npm run dev
```

## Step 1 — Seed the demo

In the workbench, open the **Copilot Loop** tab and click **Seed demo
project**. The endpoint `POST /api/demo/copilot-loop/seed` creates:

- A new project (`Demo · Bracket lightweighting`) with a
  `demo-bracket.aieng` package containing design targets, parsed
  features, a feature graph with an editable `back_wall.thickness_mm`
  parameter, per-feature stress, and computed metrics.
- Two pre-baked loops with reports:
  - `demo-rejected1` — back-wall thinning rejected; baseline unchanged.
  - `demo-approved1` — back-wall thinning approved with a mock edit;
    downstream evidence marked stale; mesh/solver remained skipped
    because no real toolchain is available on this host.

Both reports include the EN+ZH claim-boundary statement and explicitly
say the design is not certified.

## Step 2 — Inspect loop history

Open the demo project from the project list. The Copilot Loop tab now
shows the **Loop history** table with both demo loops, newest first.
Each row shows:

- loop id, last update, status, decision badge;
- proposal one-liner (`back_wall · thin · thickness_mm: 20.0 → 10.0`);
- warning / error counts;
- report filename.

Click **Reopen** on `demo-rejected1` to load the full stepper view for
that loop. Notice the rejected approval card and the skipped downstream
steps. Reopen `demo-approved1` to see the completed apply step with
stale-evidence callouts.

## Step 3 — Compare the two loops

In the history table, tick the compare checkbox on both demo loops, then
click **Compare selected (2/2)**. The side-by-side compare panel
renders:

- updated timestamps;
- loop statuses;
- approval decisions (Rejected vs Approved);
- proposals (identical in this demo — only the decision differs);
- verification verdict (`pass` on both);
- stale artifact counts (0 vs 3);
- warning / error counts;
- metric delta summary;
- design target summary;
- report paths.

## Step 4 — Load the report diff and read What Changed

In the compare panel, click **Load report diff**. The endpoint
`GET /api/projects/{id}/copilot-loops/compare-reports` is called.

Above the unified diff, the **What changed** table summarizes the
differences as structured highlights:

- `approval_decision`: **changed** · **critical** · rejected → approved.
- `proposal`: **unchanged** · info.
- `verification_status`: **unchanged** · info.
- `stale_artifacts`: **changed** · warning · 0 → 3.
- `metric_summary`: **changed** · warning (based on the demo fixture
  metric deltas).
- `target_summary`: changes per the demo fixture.
- `warnings_errors`: **changed** · warning.
- `report_availability`: **unchanged** · info (both present).
- `claim_boundary_presence`: **unchanged** · info (both reports include
  the claim-boundary statement).

Below the table, toggle **Show raw reports** to flip from the unified
diff to a side-by-side view of the two Markdown reports.

## Step 5 — Export a decision review

In the same compare panel, scroll to **Export decision review**. Tick
the checkboxes for the slices you want:

- Include What Changed highlights (recommended);
- Include unified report diff (recommended);
- Embed both raw reports (optional — produces a larger artifact).

Click **Export review**. The endpoint
`POST /api/projects/{id}/copilot-loops/export-review` writes a Markdown
artifact to `reports/copilot_loop_review/<utc_timestamp>.md` inside the
project's `.aieng` package and to the local project workspace, then
returns a preview. The preview always carries the explicit claim
boundary in English and Chinese.

You can paste the resulting Markdown into a PR description, an issue
comment, a project journal, or a design review thread.

## How to approve or reject a fresh loop

Beyond the pre-baked loops, you can run a new loop on the same demo
package:

1. Click **Start loop**.
2. Click **Advance next step** repeatedly until an approval card
   appears.
3. Click **Approve & execute** or **Reject**.
4. Continue advancing until the loop reaches `completed`.

Approve will fail in the demo unless a real FreeCAD/Gmsh/CalculiX
toolchain is configured — that is the honest unavailable path. Reject
is always safe: the package remains byte-identical and the loop ends
as a decision record.

## Claim boundary

This demo is a decision-review aid. It does not certify any design and
does not advance engineering claims. All computed numbers shown in the
demo are mock/fixture data. A qualified engineer must review the
underlying evidence before making any acceptance decision.

> 本演示仅用于决策评审。它不认证设计安全，不自动推进工程 claim。
> 所有数值均为演示用 mock/fixture 数据。必须由合格工程师审查底层证据。

## Known limitations

- Mesh/solver execution is honestly reported as unavailable in the
  demo; success is never faked.
- Demo metric deltas are pre-baked. They illustrate the workflow but
  are not the output of a solver that ran on your host.
- The demo seed is idempotent. It reuses an existing demo project by
  default, and **Reset demo project** removes only demo-flagged projects.
- The report diff is line-level; no semantic section-level diff.
- The export is a textual record. It is not a replacement for an
  engineering review of the underlying package, evidence, and audit log.
