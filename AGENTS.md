# aieng Workbench — Agent Guide

Canonical onboarding doc for any AI agent (Claude Code, GitHub Copilot, OpenAI
Codex, Cursor, Cline, …) working in this workspace. This is the single source of
truth — `CLAUDE.md`, `.github/copilot-instructions.md`, and the MCP tool
`aieng.agent_readme` all point here.

---

## STOP — read this first

**Do NOT browse `aieng/src/` to understand what this system can do.**
That is a legacy library with a `FakeBackend` stub that produces no real geometry.

**The workbench is driven primarily through the `aieng-workbench` MCP server tools.**
If you see `aieng.*` / `cad.*` / `cae.*` tools in your tool list, use them — they
provide live UI events, topology feedback, and incremental modeling.

**If you do NOT have these MCP tools** (e.g. Kimi Code CLI without MCP
configuration), you are in **fallback mode**. You can still produce geometry by:
1. Writing build123d scripts and running them through the provided runner script.
2. Importing the resulting STEP file into the workbench with the provided importer
   script so it appears in the UI.
See the **Fallback mode** section below for the exact commands.

If the `aieng-workbench` MCP server is not in your tool list, it is configured in
this repo (`.mcp.json` for Claude Code, `.vscode/mcp.json` for VS Code/Copilot,
see MCP_SETUP for Codex, and see **Kimi Code CLI** notes in the Fallback section).

---

## First three calls every session

```
1. aieng.agent_readme                   → this guide, served at runtime
2. aieng.list_projects                  → discover available project IDs
3. aieng.agent_context { project_id }   → geometry state, pointers, next steps
```

Call these **before** reading files or running code. `aieng.agent_context` gives
you the current geometry state, stale-artifact warnings, and the pointer IDs you
need to construct valid tool calls.

---

## Workspace layout

| Path | Status | Purpose |
|------|--------|---------|
| `aieng-ui/backend/` | **Active** | FastAPI backend + MCP server + all tools |
| `aieng-ui/frontend/` | **Active** | React workbench UI |
| `aieng/` | Legacy | Semantic package format library (FakeBackend only — do NOT use as a capability reference) |
| `aieng-freecad-mcp/` | Legacy dead code | Old FreeCAD adapter |
| `aieng-agent-skills/` | Experimental | Agent skill definitions |

---

## What the workbench can actually do

### Real 3D CAD modeling (no API key needed)

`cad.execute_build123d` runs caller-supplied Python code against **build123d**
(the real OpenCASCADE geometry kernel) and produces actual STEP/STL/GLB files.
This is NOT a stub. Supported operations include:

- Primitives: `Box`, `Cylinder`, `Cone`, `Sphere`, `Torus`
- Operations: `extrude`, `revolve`, `loft`, `sweep`
- Modifications: `fillet`, `chamfer`, `shell`, `mirror`
- Boolean: add / `subtract` (`Mode.SUBTRACT`) / intersect
- Patterns: `PolarLocations`, `GridLocations`, `Locations`
- Holes, slots, countersinks

Enough to model most mechanical parts: housings, brackets, enclosures, manifolds,
and simplified consumer-product bodies.

**Code contract:**
- Bind the final model to a variable named **`result`**.
- Do **not** include export calls — the runner adds `export_step` / `export_stl` /
  `export_gltf` (build123d 0.10.0; exports are free functions).
  - If you absolutely must export manually (fallback mode), use `export_gltf(result, path, binary=True)`
    to produce a real binary GLB. Without `binary=True`, build123d writes a JSON
text file that the frontend cannot render.
- A `+` that yields a `ShapeList` is auto-wrapped in a `Compound`, so unions export fine.

**Name your parts.** Set `.label` on shapes and combine them with a `Compound` so
each part gets a semantic ID you can reference later (instead of anonymous
`body_001`). Labels appear as named parts in `topology_map.json` and as
`named_part` features in `feature_graph.json`.
```python
from build123d import *
body = Box(40, 40, 10); body.label = "fuselage"
fl = Cylinder(3, 30); fl.label = "motor_pod_FL"
result = Compound(children=[body, fl])
```

**Incremental modeling (`mode: "append"`).** Instead of resubmitting the whole
script each step, append onto the previous result:
- `mode: "replace"` (default) — the script is the whole model.
- `mode: "append"` — the previously-stored script runs first; its model is exposed
  as **`previous_result`**. Your code adds to it and must still reassign **`result`**.
  Requires an existing model (run once with `replace` first). Labels from earlier
  steps are preserved.
```python
# step 2, mode=append — keeps the fuselage + motor_pod_FL from step 1
from build123d import *
arm = Cylinder(3, 30); arm.label = "motor_pod_FR"
result = Compound(children=[previous_result, arm])
```

**Visual feedback:** `cad.execute_build123d` returns a rendered PNG thumbnail as an
image content block (disable with `{"thumbnail": false}`). **Look at it** to verify
the shape and feature placement before continuing — don't judge from face counts alone.

**Response summary fields** (text-side feedback, useful when your client drops the image):
`named_parts` (all named parts now in the model), `parts_added` (what this step added),
`mode` (`replace`/`append`), `used_base` (whether an append consumed a prior model).

Example — a simplified coffee-machine body:
```python
from build123d import *
with BuildPart() as bp:
    Cylinder(radius=55, height=200)
    fillet(bp.edges().filter_by(Axis.Z, reverse=True), radius=8)
    with Locations((0, 0, 80)):
        Cylinder(radius=40, height=100, mode=Mode.SUBTRACT)
    with Locations((63, 0, 30)):
        Cylinder(radius=8, height=25, rotation=(0, 90, 0))
result = bp.part
```

### Structural FEA (CalculiX)

Linear static analysis pipeline — see workflow C below.

---

## Pointer syntax — `@kind:id`

Tool responses and `aieng.agent_context` output use pointer tokens to reference
geometry entities precisely. Use them verbatim in tool arguments and in messages
to the user — the UI renders them as clickable chips.

| Prefix | Refers to |
|--------|-----------|
| `@face:id` | A BREP face (loads / supports / fixtures) |
| `@feature:id` | A CAD feature (use in `cad.edit_parameter` featureId) |
| `@edge:id` | A BREP edge |
| `@group:id` | A named face group (load surface, constraint surface, …) |
| `@artifact:id` | A package artifact (step file, mesh, result file, …) |

Example: if `aieng.agent_context` reports `@face:f_top_001` as a flat surface
suitable for a fixed support, pass `"faceId": "f_top_001"` in your CAE setup call.

---

## Tool taxonomy

### Onboarding / discovery (read-only)

| Tool | Purpose |
|------|---------|
| `aieng.agent_readme` | This guide, served at runtime |
| `aieng.list_projects` | All known projects with id, name, status |
| `aieng.agent_context` | Compact context: pointers, stale warnings, next steps |
| `aieng.inspect_package` | Full project summary: geometry, CAE setup, results, verdict |

### Read-only inspection (no approval)

| Tool | Purpose |
|------|---------|
| `aieng.read_audit_log` | Recent agent/user actions on this project |
| `aieng.validate` | Schema + rule validation report (no mutation) |
| `aieng.write_completeness_report` | What is missing before simulation |
| `cae.prepare_solver_run` | Solver preflight — checks readiness, runs nothing |
| `cad.get_source` | Accumulated build123d source + `{named_parts, has_base}` — call before an incremental edit |

### Geometry creation (requires approval — mutates package)

| Tool | Purpose |
|------|---------|
| `cad.execute_build123d` | Run caller-supplied build123d code to create/replace geometry (mode=replace\|append) |
| `cad.edit_parameter` | Parametric edit of an existing feature (currently returns unavailable) |

Before an incremental edit, call **`cad.get_source`** (read-only) to see the current
accumulated script, which named parts already exist, and whether `has_base` (append
is possible).

### CAE setup (no approval)

| Tool | Purpose |
|------|---------|
| `cae.apply_setup_patch` | Patch CAE setup artifacts (materials, BCs, mesh params) |
| `cae.generate_solver_input` | Generate CalculiX `.inp` deck from setup artifacts |
| `cae.write_mesh_handoff` | Write mesh handoff contract for external Gmsh |
| `cae.import_solver_evidence` | Import an external solver result file as evidence |

### Simulation execution (requires approval — runs external CalculiX)

| Tool | Purpose |
|------|---------|
| `cae.run_solver` | Execute CalculiX on the generated input deck |

### Post-processing (no approval)

| Tool | Purpose |
|------|---------|
| `cae.extract_solver_results` | Parse CalculiX FRD → `computed_metrics.json` |
| `cae.extract_field_regions` | Cluster high-stress / high-displacement regions |
| `postprocess.generate_computed_metrics` | Import metrics from CSV/JSON |
| `postprocess.refresh_cae_summary` | Regenerate result summary + evidence markdown |

### Package lifecycle

| Tool | Purpose |
|------|---------|
| `aieng.convert` | Import a STEP file into a new `.aieng` package |
| `aieng.generate_preview` | Regenerate GLB/STL web preview from current STEP |
| `aieng.refresh_semantics` | Re-validate and re-extract semantic labels |
| `aieng.update_validation_status` | Write per-category validation flags |
| `aieng.write_evidence_scaffold` | Initialize `results/evidence_index.json` scaffold |

### MCP introspection

| Tool | Purpose |
|------|---------|
| `mcp.check` | Guardrails, capability gaps, operation policy for this project |
| `mcp.parse_patch` | Validate a patch proposal without applying it |
| `mcp.prepare_execution` | Dry-run a patch proposal and return preflight side effects |

---

## Recommended workflows

### A — Inspect and understand a project
```
aieng.agent_context { project_id }
```
Read the geometry summary, note any `@artifact:` tokens marked stale, check
`suggested_next_steps`.

### B — CAD generation from scratch
```
1. cad.get_source         { project_id }                (is there already a base?)
2. cad.execute_build123d  { project_id, code }          [APPROVAL REQUIRED] (mode=replace, default)
3. (inspect the returned thumbnail + named_parts to confirm the shape is right)
```
Set `.label` on each part in your build123d code and combine with `Compound` so the
result carries semantic names (see the build123d section above). After step 2 the
project is `viewer_ready_glb` and the web preview is current — no separate
`generate_preview` call needed for agent-built geometry.

### B2 — Incremental modeling (the sustainable loop)
```
1. cad.get_source         { project_id }                (source, named_parts, has_base)
2. cad.execute_build123d  { project_id, code, mode: "append" }   [APPROVAL REQUIRED]
3. (check response parts_added / named_parts and the thumbnail; repeat from 1)
```
In append mode the previous model is exposed as `previous_result`; your code adds to
it and must still reassign `result`. The response's `parts_added`, `named_parts`,
`mode`, and `used_base` tell you exactly what this step did — use them to decide the
next step instead of guessing or re-deriving state. Prefer this over resubmitting the
whole script each time.

### C — CAD → CAE simulation pipeline
```
1. aieng.agent_context        { project_id }
2. cae.apply_setup_patch      { project_id, patch }      (material, BCs, mesh)
3. cae.prepare_solver_run     { project_id }             (preflight, no execution)
4. cae.generate_solver_input  { project_id }             (write CalculiX .inp deck)
5. cae.run_solver             { project_id }             [APPROVAL REQUIRED]
6. cae.extract_solver_results { project_id }
7. cae.extract_field_regions  { project_id }
8. postprocess.refresh_cae_summary { project_id }
```

### D — Inspect results and explain findings
```
1. aieng.agent_context        { project_id }
2. cae.extract_field_regions  { project_id, field: "stress" }
```
Summarize the high-stress clusters; reference faces with `@face:id` so the user
can click to highlight them.

### E — Parametric modification (design iteration)
```
1. aieng.agent_context     { project_id }
2. cad.edit_parameter      { project_id, featureId, parameterName, newValue }  [APPROVAL]
3. aieng.refresh_semantics { project_id }
4. (re-run the CAE pipeline if geometry changed)
```

---

## Approval-gated tools

Tools marked `[APPROVAL REQUIRED]` mutate the package or execute an external
process. Always: (1) explain the side effects to the user, (2) wait for explicit
confirmation, (3) report the outcome after the call.

Currently approval-gated: `cad.execute_build123d`, `cad.edit_parameter`, `cae.run_solver`.

---

## Stale-artifact warnings

After a geometry edit, `aieng.agent_context` includes an **EDIT IMPACT** section
listing `@artifact:` references needing revalidation. Treat these as hard blockers
before running a simulation. Typical fix:
```
1. aieng.refresh_semantics   { project_id }
2. cae.generate_solver_input { project_id }
3. cae.run_solver            { project_id }   [APPROVAL REQUIRED]
```
(A fresh `cad.execute_build123d` automatically clears stale state.)

---

## If the backend (port 8000) is unreachable

You may see `{"status": "error", "code": "connection_refused"}` or timeouts when
`AIENG_BACKEND_URL` is set — the FastAPI backend is not running.

**Do NOT restart processes yourself.** Tell the user and ask them to start it:
```powershell
conda activate aieng311
cd aieng-ui/backend
uvicorn app.main:app --reload --port 8000
```
Verify with `aieng.list_projects`. Note: if the backend is down, the MCP server
**falls back to in-process execution automatically** — tools still work (no live
UI), so you can usually continue regardless.

---

## .aieng package structure (reference)

The backend manages all package I/O; never read it directly. Structure:
```
<project_id>.aieng   (ZIP)
├── metadata.json            project name, status, timestamps
├── geometry/                source.py, generated.step, preview.stl/.glb, topology_map.json
├── graph/                   aag.json, feature_graph.json, interface_graph.json
├── state/                   revalidation_status.json (stale-artifact flags)
├── cae/                     setup.json, mesh_params.json, simulation/ (CalculiX .inp/.frd)
├── results/                 computed_metrics.json, field_regions.json, evidence_index.json
└── audit_log.jsonl          append-only action history
```

---

## Fallback mode — when you do not have MCP tools

Some agent clients (notably **Kimi Code CLI** in its default configuration) do not
automatically load user-defined MCP servers. If `aieng.list_projects` is not in
your tool list, follow this fallback path.

### Environment topology (know where things are)

| Service | Address | Purpose |
|---------|---------|---------|
| React UI | `http://localhost:5173` | The workbench front-end |
| FastAPI backend | `http://localhost:8000` | API + MCP bridge + static assets |
| Platform data | `aieng-ui/data/` | Projects, runtime config, logs |
| Projects root | `aieng-ui/data/projects/` | One folder per project |
| Conda env | `aieng311` | Where build123d / OCP live |

### Running build123d without MCP

Use the provided runner so exports are handled exactly like the backend does
(including `binary=True` for GLB):

```bash
conda activate aieng311
cd aieng-ui/backend/scripts
python agent_build123d_runner.py my_model.py --out-dir ./output
```

Output files:
- `output/result.step` — AP214 STEP
- `output/result.stl` — binary STL
- `output/result.glb` — **binary** GLB (if export succeeded)
- `output/topology.json` — face / solid entities with labels

### Registering the model in the UI without MCP

After you have a STEP file (and optional preview GLB/STL), import it as a proper
project so the React UI can display it:

```bash
conda activate aieng311
cd aieng-ui/backend/scripts
python agent_import_project.py ../../output/result.step \
    --name "My Model" \
    --preview ../../output/result.stl \
    --project-id my_model_001
```

This atomically:
1. Creates the `.aieng` package.
2. Runs topology + feature-graph enrichment.
3. Creates the project directory + `metadata.json`.
4. Copies the preview into `viewer/`.
5. Updates the project status to `viewer_ready_*`.

Refresh the UI (`http://localhost:5173`) and the project will appear.

### Kimi Code CLI specific notes

Kimi Code CLI does **not** read `.mcp.json` automatically (unlike Claude Code).
To give Kimi the workbench MCP tools, you must either:
- Use Kimi's settings UI to add the MCP server defined in `.mcp.json`.
- Or accept fallback mode and use the scripts above.

### Direct REST API (last resort)

If you need to trigger backend actions without MCP, the backend exposes standard
HTTP endpoints. The most useful ones for agents:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Backend status, tool count |
| `/api/projects` | GET | List projects |
| `/api/projects` | POST | Create empty project |
| `/api/projects/{id}/upload` | POST | Upload STEP or `.aieng` |
| `/api/projects/{id}/cad-preview` | GET | Stream GLB/STL preview |
| `/api/projects/{id}/agent-context` | GET | Full geometry + CAE context |
| `/api/agent/invoke-tool` | POST | Run any MCP tool by name (emits UI events) |

Example — invoke a tool directly:
```bash
curl -X POST http://localhost:8000/api/agent/invoke-tool \
  -H "Content-Type: application/json" \
  -d '{"tool": "cad.execute_build123d", "input": {"project_id": "...", "code": "..."}}'
```

---

## Common mistakes to avoid

| Mistake | Correct approach |
|---------|-----------------|
| Reading `aieng/src/` to learn capabilities | Call `aieng.agent_readme`; real engine is `aieng-ui/backend` |
| Running code to diagnose the backend | Use MCP tools; if backend down, ask user to start it |
| Including `export_step(...)` in build123d code | Omit exports — the runner adds them |
| `result.export_step(path)` (build123d <0.9 API) | Use `export_step(result, path)`, or just omit |
| `cae.run_solver` without preflight | Call `cae.prepare_solver_run` first |
| Referencing stale artifacts after an edit | `aieng.refresh_semantics` then regenerate |
| Raw face indices instead of `@face:id` | Use pointer IDs from `aieng.agent_context` |

---

## Environment variables (for MCP server operators)

| Variable | Purpose |
|----------|---------|
| `AIENG_PLATFORM_DATA` | Override the data directory (default `aieng-ui/data`) |
| `AIENG_BACKEND_URL` | When set, forward tool calls to the running backend for live UI |
| `AIENG_MCP_BLOCK_APPROVAL_TOOLS` | Set to `1` to hard-block approval-gated tools at the server level |

Full wiring (Claude Code / Copilot / Codex): `aieng-ui/backend/MCP_SETUP.md`.
