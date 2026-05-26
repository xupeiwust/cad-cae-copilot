# aieng-ui

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![AIENG Demo Health](https://github.com/armpro24-blip/aieng-ui/actions/workflows/demo-health.yml/badge.svg)](https://github.com/armpro24-blip/aieng-ui/actions/workflows/demo-health.yml)

Web workbench and FastAPI service for the `.aieng` engineering platform.

**Keywords:** CAD · CAE · FEA · workbench · FastAPI · React · Three.js · LLM agent · MCP · CalculiX · FreeCAD · approval gate · audit · evidence review · design automation

## What This Is

`aieng-ui` provides:

`aieng-ui` is the reference runtime/workbench; package semantics are delegated to the `aieng` core repo, which remains the semantic source of truth.

- **FastAPI service layer** — project/file management, preview generation, semantic package inspection, CAE artifact detection (`GET /api/projects/{project_id}/cae-artifacts`)
- **React SPA** — STEP upload, Three.js viewer (GLB/STL), semantic summary panel, honest CAE lifecycle panel (setup / simulation runs / results) with one-click refresh and external metrics import, CAE Review Report Assistant, Closed-loop Copilot Stepper, artifact inspector (read-only JSON/text evidence review), chat/orchestration panel, audit log, settings drawer, stress-heatmap visualization
- **Local orchestration runtime** — `RunRecord`, `ToolCall`, `ToolResult`, `RuntimeEvent` types; intent-based plan builder; synchronous executor with approval gate
- **CAD provider registry** — pluggable `CadProvider` interface; FreeCAD is the first implementation
- **B-Rep graph engine** — symbolic face/edge/group pointer index (`@face:`, `@edge:`, `@group:`) derived from topology maps; deterministic, CAD-neutral, read-only
- **Engineering action planner** — typed intent classification for chat-first CAD/CAE workflows (generate, refine, preprocess, simulate, change-material, refine-mesh, set-target)
- **Simulation runner** — Gmsh meshing → CalculiX solve → FRD parse → atomic write-back, with SSE streaming progress and post-processing verdict vs. design targets
- **Stress heatmap generator** — per-node Von Mises stress colormap as binary GLB from CalculiX FRD results
- **Contextual engineering chat** — Claude-powered chat grounded in live project state (geometry, FEA setup, simulation results, design targets)

## Role in the vertical CAE MVP

`aieng-ui` is the **workbench**: the local FastAPI runtime + React SPA where the vertical CAE MVP actually executes. It owns the moving parts that `aieng` deliberately does not:

- The runtime tool registry (table below) and the `POST /api/runtime/runs` orchestration entry point.
- The **approval gate** — `cae.run_solver`, `cae.generate_mesh`, `cad.edit_parameter`, and `freecad.run_macro` are `requires_approval=True`; the runtime pauses before mutation or subprocess execution and exposes explicit `approve`/`reject` REST endpoints.
- The **external CalculiX subprocess adapter** — `subprocess.run([ccx, …], shell=False)` with timeout, captured stdout/stderr/return code, and honest `converged: null` semantics. AIENG does not host a solver.
- **Artifact write-back** into the `.aieng` package (atomic ZIP rewrite via temp file + `shutil.move`).
- The **audit/event timeline** (`RuntimeEvent` sequence).
- The schema-version drift warning surfaced through the `aieng_bridge` to the chat panel.

External agents (Claude Code, Codex, MCP clients) reach the workbench through `aieng_freecad_mcp`. For the reproducible end-to-end demo see [`docs/quickstart-vertical-cae-demo.md`](docs/quickstart-vertical-cae-demo.md).

For the step-by-step evidence-grounded CAD/CAE Copilot loop, see
[`docs/closed-loop-copilot-stepper.md`](docs/closed-loop-copilot-stepper.md).
For the issue #10 v0.26 demo acceptance path, see
[`docs/copilot-loop-v0.26-demo-walkthrough.md`](docs/copilot-loop-v0.26-demo-walkthrough.md).

27 registered runtime tools (mutation / expensive operations are approval-gated).
Honest status semantics: `skipped`, `partial`, `error`, and `completed` are never
conflated. Key tools listed below; full registry available via `GET /api/runtime/tools`.

| Tool | Status |
|------|--------|
| `aieng.inspect_package` | Working |
| `aieng.refresh_semantics` | Working |
| `aieng.generate_preview` | Working |
| `aieng.read_audit_log` | Working |
| `freecad.inspect_geometry` | Working — FreeCADCmd bridge |
| `freecad.export_step` | Working — FreeCADCmd bridge; writes `{stem}_export.step` |
| `postprocess.generate_computed_metrics` | Working — normalizes external metrics into `computed_metrics.json` and writes it back into the `.aieng` package |
| `postprocess.refresh_cae_summary` | Working — regenerates CAE result summary, evidence index, and markdown |
| `mcp.check` | Working — checks MCP guardrails, capability gaps, operation policy |
| `mcp.parse_patch` | Working — parses an `.aieng` patch proposal without executing |
| `mcp.prepare_execution` | Working — dry-run `.aieng` patch proposal; returns preflight side effects |
| `cae.apply_setup_patch` | Working — controlled patches to CAE setup artifacts |
| `cae.extract_solver_results` | Working — parses CalculiX FRD and writes `computed_metrics.json` |
| `cae.prepare_solver_run` | Working — preflight inspection, no solver execution |
| `cae.run_solver` | Working — external CalculiX execution adapter MVP, approval-gated |
| `cad.edit_parameter` | Working — FreeCAD parameter edit with honest executor selection (`auto`\|stub\|`macro`\|`rpc`). Stub mode returns `source="stub_mock"`, `status="partial"`. Approval-gated. |
| `cae.generate_mesh` | Working — geometry ZIP unpack → FreeCAD/Gmsh mesh → `.inp` → atomic write-back. Returns `error/freecad_unavailable` when FreeCAD missing. Approval-gated. |
| `freecad.run_macro` | Skeleton, approval-gated |

External agents (Claude Code, Codex, custom MCP clients) can access all runtime tools via the MCP bridge in `aieng_freecad_mcp`. See [`../docs/runtime_and_agents.md`](../docs/runtime_and_agents.md).

## Evidence review API

Read-only endpoints for human review of artifacts inside a project's `.aieng`
package. These do NOT execute solvers, mutate packages, or advance claims —
they exist so a reviewer (or agent) can inspect what the runtime wrote.

| Endpoint | Purpose |
|---|---|
| `GET /api/projects/{project_id}/cae-review-report` | Generate a read-only CAE review report from existing lifecycle summaries: setup readiness, missing information, stale evidence, result metrics, design-target comparisons, and claim boundaries. Does not execute solvers, mutate packages, or advance claims. |
| `GET /api/projects/{project_id}/artifact?path=...` | Read a single artifact from the project's `.aieng` package. Returns `{path, exists, media_type, size_bytes?, parsed_json?, text?, warnings}`. JSON files are parsed when ≤ 2 MB; text files are inlined when ≤ 256 KB. Missing artifacts return `exists: false` with 200. Path traversal, absolute paths, and backslashes are rejected with 400. |
| `POST /api/projects/{project_id}/artifact/diff` | Compute RFC-6901 JSON Pointer paths for differences between two JSON values supplied in the body as `{before, after}`. Returns `{changed_paths, added_paths, removed_paths}`. Pure computation; no package access. |
| `POST /api/projects/{project_id}/solver-input` | Import a CalculiX `.inp` solver input deck into the package. Body: `{text, run_id?, overwrite?}`. Writes to `simulation/runs/{run_id}/solver_input.inp` (default `run_id` `"run_001"`). Minimal CalculiX keyword scan rejects obvious non-decks; missing `*NODE` / `*STEP` blocks are accepted with warnings. Import only — no mesh generation, no deck generation, no physical correctness validation. 10 MB cap. |
| `POST /api/llm/test` | Test LLM provider configuration (`config_ready`) and optionally verify real API connectivity (`connection_verified`). Body: `{llm_config, verify_connection?}`. Never returns the API key. |
| `POST /api/projects/{project_id}/engineering-action-plan` | Typed, read-only action candidate for a chat prompt. Classifies intent (generate, refine, preprocess, simulate, change-material, refine-mesh, set-target) and returns confidence, extracted inputs, and execution policy. Does not execute tools or mutate the package. |
| `POST /api/projects/{project_id}/brep-graph/build` | Build symbolic B-Rep graph, entity pointer index, and markdown digest from `geometry/topology_map.json`. Writes `graph/brep_graph.json`, `graph/entity_index.json`, and `ai/brep_digest.md` into the package atomically. No CAD kernel or LLM involved. |
| `GET /api/projects/{project_id}/brep-graph` | Read existing B-Rep graph artifacts from the project package. |
| `POST /api/projects/{project_id}/run-simulation` | Mesh with Gmsh + solve with CalculiX from AI preprocessing output. Requires `confirmed=true` (approval gate). Returns gracefully if tools are not installed. Writes `simulation/solver_log.txt`, `simulation/result.frd`, `simulation/mesh.inp`, and `simulation/results_summary.json` atomically. |
| `POST /api/projects/{project_id}/run-simulation-stream` | Streaming SSE variant of `run-simulation`. Events: checking_tools → meshing → building_nsets → solving → parsing → done \| error. |
| `GET /api/simulation/tools` | Check whether Gmsh and CalculiX are available on this host. |
| `GET /api/projects/{project_id}/stress-heatmap` | Return a colored GLB with per-node Von Mises stress heatmap. Requires `simulation/mesh.inp` and `simulation/result.frd` in the package. Returns `X-Stress-Min-Mpa` and `X-Stress-Max-Mpa` headers. |
| `POST /api/projects/{project_id}/chat-set-target` | Parse a natural-language message and upsert a design target into `design_targets.yaml`. Body: `{ message: str }`. |
| `POST /api/projects/{project_id}/contextual-chat` | Context-aware engineering chat grounded in the current project state. Injects geometry summary, simulation results, verdict, and design targets into the system prompt. Body: `{ message: str, history?: [...], api_key?: str }` |

Pair the two reads: capture a JSON artifact before an action, capture it again
after, then POST both to `/artifact/diff` to surface the structural delta.

The solver-input importer closes the biggest functional gap in the vertical
CAE MVP — `cae.run_solver` previously assumed the deck was already present
inside the package. Pair this endpoint with `aieng_get_cae_preprocessing_summary`
(or `cae.prepare_solver_run`) before approving execution.

The artifact inspector is exposed in the CAE panel of the React SPA: enter an
artifact path (e.g. `results/computed_metrics.json`) to view parsed JSON or
text inline. Clickable artifact paths appear in the CAE artifact grid and in
runtime chat history for low-risk file types (`.json`, `.txt`, `.md`, `.yaml`,
`.yml`, `.inp`, `.csv`, `.log`).

When `cae.apply_setup_patch` changes setup artifacts, the runtime chat bubble
shows an **artifact diff** panel: path, operation, JSON pointer, changed/added/
removed RFC-6901 paths, and compact before/after values. This is evidence review
metadata only — it does not prove physical correctness or mean the solver was
rerun. Stale-artifact warnings remain visible.

## Fresh-clone Copilot MVP demo path

Use this path for the v0.28 public-facing Copilot MVP demo. The demo is deterministic and works without FreeCAD, Gmsh, or CalculiX.

1. Clone the three sibling repos into one workspace.

   ```bash
   mkdir aieng-workspace
   cd aieng-workspace
   git clone https://github.com/armpro24-blip/aieng-ui.git
   git clone https://github.com/armpro24-blip/aieng.git
   git clone https://github.com/armpro24-blip/aieng-freecad-mcp.git
   ```

2. Install backend dependencies.

   ```bash
   cd aieng-ui/backend
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -e ".[dev]"
   pip install -e ../../aieng
   pip install -e ../../aieng-freecad-mcp
   ```

   On Windows PowerShell:

   ```powershell
   cd aieng-ui\backend
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -e ".[dev]"
   pip install -e ..\..\aieng
   pip install -e ..\..\aieng-freecad-mcp
   ```

3. Install frontend dependencies.

   ```bash
   cd ../frontend
   npm ci
   ```

4. Run the quick demo health gate from the `aieng-ui` repo root.

   ```bash
   cd ..
   ./scripts/check_demo_health.sh
   ```

   On Windows PowerShell:

   ```powershell
   cd ..
   .\scripts\check_demo_health.ps1
   ```

5. Start the backend and frontend in two terminals.

   ```bash
   # terminal 1
   cd aieng-ui/backend
   source .venv/bin/activate
   uvicorn app.main:app --reload

   # terminal 2
   cd aieng-ui/frontend
   npm run dev
   ```

   On Windows PowerShell, activate `backend\.venv` before running `uvicorn`.

6. Open the Vite URL, usually `http://localhost:5173`, then open **Copilot Loop** and run:

   **Try the Copilot Loop demo -> Seed demo project -> Run demo health check -> Compare selected loops -> Load report diff -> Export review**

The expected demo shows one rejected loop, one approved loop, loop comparison, structured "What Changed" highlights, report diff, and a decision-review export with claim-boundary text.

The demo uses **deterministic fixture data**. It does **not** run FreeCAD/Gmsh/CalculiX, does **not** certify design safety, and does **not** advance engineering claims automatically. Imported metrics and real solver outputs are separate evidence categories; the UI and reports must not treat them as accepted engineering claims.

For the release checklist, screenshot/GIF checklist, and known limitations, see [`docs/v0.28-copilot-mvp-release-checklist.md`](docs/v0.28-copilot-mvp-release-checklist.md). For the detailed walkthrough, see [`docs/demo-release-walkthrough.md`](docs/demo-release-walkthrough.md).

### Run the full Copilot MVP demo

The full end-to-end Copilot loop — health check → FreeCAD inspection → design
targets → computed metrics → target comparison → approval-gated CAD edit →
stale-evidence tracking → structural preflight → approval-gated solver run →
FRD extraction → Copilot Loop report → **Engineering Review Support Packet
export** — is documented step-by-step in
[`docs/full-copilot-demo-walkthrough.md`](docs/full-copilot-demo-walkthrough.md).
Missing tools and missing evidence are reported honestly; the demo does not
certify design safety or advance engineering claims.

## Local validation and CI

Run the local release gate:

```bash
./scripts/check_demo_health.sh --full
```

On Windows PowerShell:

```powershell
.\scripts\check_demo_health.ps1 -Full -Frontend
```

Manual commands:

```bash
cd backend
python -m pytest -q -k "smoke_check"
python -m pytest -q

cd ../frontend
npm run build
```

Optional real-environment checks:

```bash
cd backend
python -m pytest tests/test_api.py::test_run_solver_real_ccx_skipped_if_unavailable -v

# Requires AIENG_TEST_REAL_FREECAD=1 and FreeCADCmd.
python -m pytest tests/test_api.py::test_cae_generate_mesh_real_freecad_integration -v
```

CI is defined in [`.github/workflows/demo-health.yml`](.github/workflows/demo-health.yml). It runs a smoke-check gate on push and pull request, plus full backend tests and frontend build. Real FreeCAD/CalculiX integration checks are optional local gates and are expected to skip cleanly when binaries are unavailable.

## Tests

```bash
cd backend
python -m pytest -c NUL tests/test_api.py -v
```

A generic end-to-end post-processing smoke test (`test_postprocessing_smoke_metrics_import_and_summary_refresh`) validates the full metrics-import → summary-refresh workflow without solver execution or part-family fixtures.

A vertical CAE workflow benchmark (`test_vertical_cae_workflow_end_to_end`) demonstrates the full agent-run lifecycle through the runtime REST API: preflight → approval-gated external solver execution (mocked ccx) → FRD scalar extraction → computed metrics write-back → result summary refresh, with honest limitations enforced (`converged=null`, explicit warnings, no physical correctness claim). See [`../docs/aieng-agent-workflow.md`](../docs/aieng-agent-workflow.md) for the reusable agent workflow pattern, and [`../docs/demo-vertical-cae-workflow.md`](../docs/demo-vertical-cae-workflow.md) for a step-by-step walkthrough with agent prompt.

If you have CalculiX installed, you can run a real-environment smoke test: [`docs/quickstart-real-ccx.md`](docs/quickstart-real-ccx.md).
For a step-by-step explanation of the full real-binary pipeline (FreeCAD → mesh → ccx → FRD → evidence index), see [`docs/walkthrough-real-cae-pipeline.md`](docs/walkthrough-real-cae-pipeline.md).

Before demoing, use the [`docs/demo-readiness-checklist.md`](docs/demo-readiness-checklist.md). If something breaks during setup or runtime, see [`docs/troubleshooting-vertical-cae-mvp.md`](docs/troubleshooting-vertical-cae-mvp.md).

## Documentation

Repo-level docs:

- [Package semantics](docs/package_semantics.md) — canonical concept definitions (artifact, evidence, claim, proposal, support packet, review readiness, etc.) and six core principles
- [Runtime architecture](docs/runtime_architecture.md) — orchestration layer, tool adapters, FreeCAD bridge paths
- [Real CAE pipeline walkthrough](docs/walkthrough-real-cae-pipeline.md) — real-binary end-to-end: STEP → mesh → ccx → FRD → evidence index; evidence vs. claim discipline; manual validation checklist
- [Vertical CAE MVP milestone](docs/milestone-vertical-cae-mvp.md) — current MVP positioning, real capabilities, boundaries, and check commands

Workspace-level docs (covers all three repos):

- [System architecture](../docs/system_architecture.md) — three-repo overview and data flow
- [Repo boundaries](../docs/repo_boundaries.md) — ownership, coupling points, what must not cross
- [Runtime and agents](../docs/runtime_and_agents.md) — run lifecycle, REST API, future MCP integration
- [CAD adapter strategy](../docs/cad_adapter_strategy.md) — provider interface, adding new backends
- [Package contract](../docs/package_contract.md) — `.aieng` ZIP format and package states
- [Roadmap](../docs/roadmap.md) — phases 1–5
