# AIENG Release Readiness - Decision Review Workbench Demo (v0.28)

> This document is for reviewers and developers who need to verify that the
> AIENG Decision Review Workbench demo is working correctly on their machine.
> It is not a product strategy document.
>
> For the public Copilot MVP release checklist, screenshot/GIF checklist, and
> fresh-clone path, start with
> [v0.28-copilot-mvp-release-checklist.md](v0.28-copilot-mvp-release-checklist.md).

## What the release-ready demo path is

The v0.28 release-ready demo is a deterministic, self-checking walkthrough of
AIENG's Copilot Loop decision review capabilities:

1. Seed a bracket-lightweighting fixture project.
2. Inspect two pre-baked Copilot loops (one rejected, one approved).
3. Compare the loops side-by-side with a Markdown report diff.
4. Review structured "What Changed" highlights.
5. Export a decision review artifact.
6. Run the built-in **Demo Health Check** to verify the chain end-to-end.
7. Run the **Project Health Check** and review **Suggested next actions**.
8. Open the **Design Targets** card and add a measurable target.
9. Open the **Computed Metrics** card and import postprocessed scalar metrics.
10. Re-run the **Project Health Check** and verify the missing-target and
    missing-metrics actions disappear when valid evidence exists.

## What the demo proves

- The backend can seed, persist, list, compare, and export Copilot loops.
- The approval gate distinguishes rejected vs approved decisions.
- Report diffs and structured highlights are generated deterministically.
- The claim boundary (EN + ZH) is present in exports.
- Prohibited certification language is absent.
- The demo health chain can self-verify on a clean machine.

## What the demo does NOT prove

- AIENG does **not** certify a design.
- AIENG does **not** advance engineering claims automatically.
- The demo does **not** run real FreeCAD, Gmsh, or CalculiX.
- The metric numbers are deterministic fixture/mock values, not solver output.
- The demo does **not** compare geometry or meshes visually.
- Only one demo kind (`bracket-lightweighting`) is shipped.

## Required local commands

### Quick gate (mandatory before any demo or release)

```bash
cd aieng-ui/backend
python -m pytest -q -k "smoke_check"
```

Expected: **all passed**.

### Full backend validation

```bash
cd aieng-ui/backend
python -m pytest -q
```

Expected: **all passed, a few skipped** (e.g. OCC-dependent tests when OCC is
unavailable).

### Frontend build

```bash
cd aieng-ui/frontend
npm ci
npm run build
```

Expected: **TypeScript compiles cleanly**, Vite build succeeds. The chunk-size
warning about `> 500 kB` is expected and does not block the build.

## How to run the UI demo

1. **Start the backend**
   ```bash
   cd aieng-ui/backend
   uvicorn app.main:app --reload
   ```

2. **Start the frontend**
   ```bash
   cd aieng-ui/frontend
   npm run dev
   ```

3. **Open the workbench** in your browser at the Vite URL (usually
   `http://localhost:5173`).

4. **Open the Copilot Loop tab**.

5. **Seed the demo**
   - Click **Seed demo project** in the demo card.
   - The project is automatically selected.

6. **Run the demo health check**
   - Click **Run demo health check** in the same card.
   - Wait for the checklist to finish.
   - Expected: all checks **passed**, green banner.

7. **Run the project health check**
   - Click **Run health check** in the Project Health Check card.
   - This performs a read-only inspection of the selected project's `.aieng` package,
     CAD/CAE context, design targets, and Copilot loops.
   - Expected: readiness = **ready** (or **partial** if some inputs are missing),
     no failed checks, no package mutation warnings.

8. **Compare loops**
   - Scroll down to the loop history table.
   - Select the two loops (rejected + approved) and click **Compare**.
   - Review the report diff and the "What Changed" highlights panel.

8. **Export review**
   - In the compare panel, click **Export review**.
   - Verify the export contains the claim boundary in both languages.

## Expected pass criteria

| Check | Expected result |
|---|---|
| `seed` | Demo project created or reused |
| `list_loops` | 2 loops found |
| `identify_decisions` | 1 rejected, 1 approved |
| `compare_reports` | Diff generated |
| `highlight_approval_decision` | Status = `changed` |
| `export_review` | Export artifact written |
| `export_artifact_exists` | Artifact found in package/local storage |
| `claim_boundary_en` | English claim boundary present |
| `claim_boundary_zh` | Chinese claim boundary present |
| `no_certification_language` | No prohibited phrases |
| `highlight_critical_severity` | Severity = `critical` |

### Project Health Check items

| Check | Category | Expected result |
|---|---|---|
| `project_exists` | package | Project directory exists |
| `package_file` | package | `.aieng` package exists |
| `package_readable` | package | Package can be opened as ZIP |
| `manifest` | package | `manifest.json` present and valid |
| `evidence_index` | evidence | Evidence index readable |
| `stale_evidence` | evidence | Evidence not older than 7 days |
| `cad_context` | cad | CAD context readable |
| `editable_parameters` | cad | Editable parameters present |
| `cae_artifacts` | cae | CAE artifacts present |
| `design_targets` | targets | Design targets defined |
| `claim_boundary` | claims | Claim boundary present in exports |
| `prohibited_language` | claims | No prohibited certification language |
| `loop_count` | loops | Loop count reported |
| `loop_reports` | loops | Loop reports readable |
| `demo_metadata` | demo | Demo metadata flagged if applicable |

### Health-to-Action Guidance (v0.9)

The Project Health Check now includes **Suggested next actions** derived from
failed, warning, and unknown checks. These actions are:

- **Suggestions only** — they do not automatically modify the project.
- **Read-only** — every action declares `mutates_package=false`, `runs_solver=false`,
  `advances_claim=false`.
- **Sorted by priority** — high → medium → low, with package/manifest first,
  evidence next, CAD/CAE/targets next, loop/report/export next, demo notes last.

| Trigger | Action | Priority | Type |
|---|---|---|---|
| Missing package | Create or upload a valid .aieng package | high | manual |
| Missing manifest | Fix package manifest before running Copilot Loop | high | manual |
| Stale evidence | Review stale evidence before trusting old results | high | navigate |
| Missing design targets | Add measurable design targets | high | navigate |
| Missing claim boundary | Regenerate reports with claim-boundary text before sharing | high | manual |
| Prohibited language | Remove prohibited certification language from reports | high | manual |
| Missing editable parameters | Add or expose editable CAD parameters | medium | manual |
| Missing computed metrics | Import computed metrics or run postprocessing | medium | navigate |
| No loops | Start the first Copilot Loop | medium | navigate |
| Missing loop reports | Generate loop reports before comparing or exporting | medium | navigate |
| One loop only | Run another Copilot Loop to enable comparison | low | navigate |
| Demo project | Use demo to learn workflow; do not treat fixtures as real evidence | low | manual |

### Guided Readiness Workflow (v0.11)

Suggested health actions can now navigate to the relevant workbench section.
For example, **Add measurable design targets** exposes an **Open Design
Targets** button that expands, scrolls to, and briefly highlights the Design
Targets card.

These action buttons are navigation hints only:

- they do **not** mutate the package;
- they do **not** save design targets;
- they do **not** edit CAD;
- they do **not** run mesh generation or a solver;
- they do **not** approve/reject a loop;
- they do **not** advance engineering claims.

Saving design targets remains an explicit metadata edit performed inside the
Design Targets card. After saving, the UI prompts the user to run the
read-only **Project Health Check** again. On the next health check, the
missing-design-target recommended action should disappear if the saved targets
validate successfully.

### Refresh transparency — last-refreshed timestamps (v0.22)

All data-loaded cards now display a "Last refreshed" timestamp so users can tell
when the displayed data was fetched:

- **Design Targets** — shows when targets were last loaded from the package.
- **Computed Metrics** — shows when metrics were last loaded from the package.
- **FreeCAD Inspection** — shows when inspection evidence was last loaded.

Timestamps are purely frontend state; they reset on page reload and update on
every successful refresh. If data has never been loaded, the card shows
"Not loaded yet".

### Unified Health Action Navigation Refresh (v0.21)

All health-action navigation now behaves consistently:

- Clicking a suggested action opens the relevant card.
- The card refreshes its current data automatically.
- The user decides what to do next — nothing is auto-fixed, auto-imported,
  auto-inspected, or auto-saved.

Cards that support refresh:

- **Design Targets** — refreshes existing targets from the package.
- **Computed Metrics** — refreshes existing metrics from the package.
- **FreeCAD Inspection** — refreshes existing inspection evidence from the
  package (v0.20).

This is strictly read-only navigation. No package mutation, no solver run, no
CAD inspection, no claim advancement.

### Computed Metrics Import (v0.12)

The Computed Metrics card lets users view and explicitly import postprocessed
scalar metrics into the package. This closes the workflow where design targets
exist but target mapping remains unavailable because computed metrics are
missing.

- **Path inside package**: `results/computed_metrics.json`
- **Preview**: parses JSON or CSV, validates metric names and numeric values,
  and shows target mapping without writing to the package.
- **Save**: writes only `results/computed_metrics.json` after explicit user
  action.
- **JSON accepted**: a full computed-metrics document or a simple metric object
  like `{"mass": {"value": 1.24, "unit": "kg"}}`.
- **CSV accepted**: required columns `metric,value`; optional columns
  `unit,load_case_id,source`.
- **Target mapping**: reports `mapped`, `missing_metric`, `ambiguous`, or
  `unknown` based on metric name and optional load-case ID.

Safety boundaries:

- preview and GET are read-only;
- save does not edit CAD, generate mesh, run a solver, or refresh claims;
- imported metrics do not certify the design;
- target mapping is evidence availability only, not pass/fail claim approval.

### Design Targets Authoring

The Design Targets card lets users view, add, edit, delete, and import design
targets directly into the `.aieng` package.

- **Path inside package**: `task/design_targets.yaml`
- **Schema**: `schema_version`, `targets[]` with `target_id`, `label`, `metric`,
  `operator`, `value`, optional `unit`, `scope`, `load_case_id`, `priority`, `rationale`
- **Validation**: duplicate IDs, unsupported operators, non-numeric values, and
  >100 targets are rejected with structured errors.
- **Safety**: saving targets is explicit metadata editing only. No CAD edit,
  no solver run, no claim advancement.

## Known limitations

- **Fixture data only**: The demo uses pre-baked mock values, not real solver
  output.
- **No real solver**: FreeCAD, Gmsh, and CalculiX are not executed.
- **No geometry diff**: The demo does not visually compare CAD geometry.
- **No certification**: The export and reports explicitly state they do not
  certify the design.
- **One demo kind**: Only `bracket-lightweighting` is available.
- **Bundle size warning**: The frontend build warns about a `> 500 kB` chunk.
  This is a known Vite advisory, not a build failure.

## Claim boundary reminder

Every demo loop report and every export contains an explicit claim boundary:

> This decision review export is a reviewable record of one or two Copilot
> loops. It does not certify either design, does not advance engineering
> claims, and must be reviewed by a qualified engineer before being cited in
> any acceptance decision.
>
> This review export does not certify design safety, does not auto-advance engineering claims, and must be reviewed by a qualified engineer.

## Troubleshooting

### Missing dependencies

If `pip install -e ".[dev]"` fails, ensure Python >= 3.11 is active:

```bash
python --version
```

If `npm run build` fails, ensure Node >= 18 is active:

```bash
node --version
```

### Failed smoke check

Run with reset to rule out stale demo state:

```bash
cd aieng-ui/backend
python -c "
from app.app_factory import create_app
from app.config import default_settings
from fastapi.testclient import TestClient
app = create_app(default_settings())
client = TestClient(app)
resp = client.post('/api/demo/copilot-loop/smoke-check', json={'reset': True})
print(resp.json())
"
```

Common causes:
- A previous agent/session deleted or corrupted demo loop files.
- The claim-boundary export note was accidentally modified.

### Stale demo project

Click **Reset demo project** in the UI, or call:

```bash
curl -X POST http://127.0.0.1:8000/api/demo/copilot-loop/reset
```

This only deletes demo-flagged projects.

### Frontend build warning about bundle size

The `(!) Some chunks are larger than 500 kB` message is a Vite performance
hint, not an error. It does not block the build or the demo.
