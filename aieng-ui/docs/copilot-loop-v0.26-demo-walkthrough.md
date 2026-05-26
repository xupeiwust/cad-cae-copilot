# v0.26 Closed-loop Copilot Demo Walkthrough

This walkthrough is the issue #10 acceptance path for the first runnable
closed-loop Copilot MVP demo. It connects existing workbench capabilities into
one reviewable CAD/CAE decision flow:

Project Health Check -> FreeCAD feature inspection -> design targets ->
computed metrics -> recommendation -> verification -> human approval ->
FreeCAD parameter edit fixture -> stale evidence -> metrics update ->
target comparison -> loop report -> decision review export.

The demo is deterministic and safe to run on a laptop without FreeCAD, Gmsh,
or CalculiX. Fixture values illustrate the workflow; they are not solver
results and do not certify a design.

## Preconditions

Start both services:

```powershell
# terminal 1
cd G:\Code\aieng-workspace\aieng-ui\backend
python -m uvicorn app.main:app --reload

# terminal 2
cd G:\Code\aieng-workspace\aieng-ui\frontend
npm run dev
```

Open the Vite URL, then switch to the **Copilot Loop** tab.

## Acceptance Path

1. **Seed the fixture**

   Click **Seed demo project** in the **Try the Copilot Loop demo** card.
   The backend creates or reuses a demo-flagged bracket-lightweighting project
   with two persisted loops:

   - `demo-rejected1`: mutation rejected, baseline evidence unchanged.
   - `demo-approved1`: mutation approved, mock CAD edit recorded, downstream
     evidence marked stale.

   Repeated seed clicks reuse the same demo project. **Reset demo project**
   deletes only projects tagged as Copilot-loop demo fixtures.

2. **Run Project Health Check**

   Click **Run health check**. Confirm the response shows readiness,
   recommended safe next actions, and the claim boundary. The check is
   read-only and does not mutate the `.aieng` package.

3. **Inspect CAD features**

   Open **FreeCAD Inspection** from the health action or scroll to the card.
   Use the read-only inspection evidence to confirm parsed features and
   editable parameters are visible. The demo fixture includes the
   `back_wall.thickness_mm` parameter used by the loop.

4. **Confirm design targets**

   Open **Design Targets**. Confirm the fixture contains measurable targets,
   including mass/stress/displacement-style thresholds used by the comparison
   step. Saving targets is explicit and writes only `task/design_targets.yaml`.

5. **Confirm computed metrics**

   Open **Computed Metrics**. Confirm `results/computed_metrics.json` is
   available and target mapping is shown. Import/preview/save operations are
   explicit; they do not edit CAD or run a solver.

6. **Inspect recommendation and verification**

   Reopen `demo-approved1` or start a fresh loop and advance through:

   - **Recommend CAD modification**
   - **Verify proposal**

   The selected proposal and verification verdict are displayed as evidence
   cards. A failed verification blocks the mutation step.

7. **Exercise the approval gate**

   In a fresh loop, advance until **Approve/apply CAD parameter edit** waits
   for approval. Choose **Reject** to prove rejection is a valid decision
   record and leaves the package unchanged, or **Approve & execute** to run
   the approval-gated edit path when the runtime can execute it.

   The pre-baked approved fixture demonstrates the successful edit path
   without requiring a local CAD installation.

8. **Review stale evidence**

   In the approved loop, inspect **Mark stale downstream artifacts**. Confirm
   geometry-dependent artifacts are listed as stale and the UI explains that
   they remain in the package for audit but must not be cited for the modified
   geometry until regenerated.

9. **Compare targets**

   Inspect **Compare design targets** in the approved loop. The report shows
   before/after metric deltas and design-target status when available. Missing
   metrics remain unknown; the UI does not fabricate success.

10. **Generate and inspect loop report**

    Reopen either pre-baked loop and inspect the **Loop report** card, or run a
    fresh loop through **Generate loop report**. Confirm the report contains:

    - selected proposal and approval/rejection decision;
    - stale evidence section for the approved path;
    - before/after metrics and design target comparison when evidence exists;
    - explicit claim boundary and limitations.

11. **Compare rejected vs approved loops**

    In **Loop history**, select the rejected and approved demo loops and click
    **Compare selected**. Load the report diff. Confirm **What changed**
    highlights include:

    - approval decision changed with critical severity;
    - stale artifact count changed;
    - metric/target summaries are surfaced;
    - claim boundary presence is checked.

12. **Export decision review**

    In the comparison panel, click **Export review** with highlights and diff
    enabled. The export is written under:

    ```text
    reports/copilot_loop_review/<utc_timestamp>.md
    ```

    Confirm the export contains workspace-relative report links, the structured
    highlights, optional diff, warnings, limitations, and the claim boundary.

## Built-in Health Check

For a fast local verification, run either path:

```powershell
cd G:\Code\aieng-workspace\aieng-ui\backend
python -m pytest tests/test_api.py -q -k "demo_smoke_check or v05_demo_smoke"
```

or in the UI:

```text
Copilot Loop -> Try the Copilot Loop demo -> Run demo health check
```

The smoke check verifies seed, loop listing, rejected/approved decisions,
report comparison, critical highlight severity, export artifact presence,
claim-boundary text, and absence of prohibited certification language.

## Safety Boundaries

- Every mutation or expensive step goes through explicit approval.
- Project Health Check, report comparison, and export are read-only except for
  the deliberate export artifact write.
- Stale evidence remains visible after CAD edits.
- Reports and exports state that they do not certify the design or advance
  engineering claims.
- The demo does not run hidden solver/CAD operations and does not claim
  physical correctness.

## Verification Commands

```powershell
cd G:\Code\aieng-workspace\aieng-ui\backend
python -m pytest tests/test_api.py -q -k "demo_smoke_check or v05_demo_smoke or demo_seed or compare_reports or export_review"
python -m pytest tests/test_target_comparison.py tests/test_project_health.py -q

cd G:\Code\aieng-workspace\aieng-ui\frontend
npm run build
```
