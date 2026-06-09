# System Architecture

Three sibling repositories form the aieng engineering workbench platform.
Each has a single, narrow responsibility.

```text
cad-cae-copilot/
  aieng/               — semantic package engine and .aieng format
  aieng_freecad_mcp/   — FreeCAD execution adapter (MCP-facing)
  aieng-ui/            — web workbench UI + FastAPI service layer
```

---

## Responsibility Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User / External Agent                         │
│            (browser, Claude Code, Codex, CLI script, MCP client)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
   Web browser           MCP protocol          HTTP / CLI
          │                   │                    │
          └────────────────────┼────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         aieng-ui                                     │
│  React SPA + Three.js viewer + chat/orchestration panel             │
│  FastAPI service layer                                               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   local orchestration runtime                │   │
│  │  RunRecord · ToolCall · ToolResult · RuntimeEvent            │   │
│  │  tool registry + intent-based plan builder + executor        │   │
│  │  file-backed run persistence (data/runtime/runs/)            │   │
│  │                                                              │   │
│  │  Registered tools:                                           │   │
│  │    aieng.inspect_package    ─── wraps package_summary()      │   │
│  │    aieng.refresh_semantics  ─── wraps validate_aieng_file()  │   │
│  │    aieng.generate_preview   ─── wraps convert_asset()        │   │
│  │    aieng.read_audit_log     ─── wraps recent_logs()          │   │
│  │    freecad.inspect_geometry ─── FreeCADCmd bridge ✅         │   │
│  │    freecad.export_step      ─── FreeCADCmd bridge ✅         │   │
│  │    freecad.run_macro        ─── approval-gated skeleton      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  REST API:                                                           │
│    POST /api/runtime/runs          ← start a run                    │
│    GET  /api/runtime/runs/{id}     ← poll run status                │
│    GET  /api/runtime/runs/{id}/events ← poll event list             │
│    GET  /api/projects/{id}         ← project summary               │
│    POST /api/projects/{id}/import-aieng                             │
│    POST /api/projects/{id}/convert                                  │
│    POST /api/projects/{id}/validate                                 │
│    POST /api/projects/{id}/chat    ← legacy orchestration           │
│    POST /api/projects/{id}/upload                                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
               ┌───────────────┼───────────────────┐
               │               │                   │
               ▼               ▼                   ▼
┌──────────────────┐  ┌─────────────────┐  ┌──────────────────────┐
│     aieng        │  │ aieng_freecad   │  │  future adapters     │
│                  │  │    _mcp         │  │                      │
│  .aieng package  │  │                 │  │  SolidWorks bridge   │
│  STEP import     │  │  FreeCAD tools  │  │  Fusion 360 bridge   │
│  topology        │  │  inspect/export │  │  OpenFOAM bridge     │
│  features        │  │  guard policy   │  │  generic STEP reader │
│  enrichment      │  │  evidence       │  │                      │
│  validation      │  │  writeback      │  └──────────────────────┘
│  AI summary      │  │                 │
│  CAE scaffold    │  │  MCP runtime    │
│  claim map       │  │  bridge tools   │
│  evidence index  │  │  (Phase 3 ✅)   │
│  MCP server      │  │                 │
└──────────────────┘  └─────────────────┘
```

---

## Data Flow: STEP Import Workbench

```
User uploads .step
      │
      ▼
aieng-ui: POST /api/projects/{id}/upload
      │
      ▼
aieng-ui: POST /api/projects/{id}/import-aieng
      │  calls FreeCAD adapter (bridge_runner.py)
      │  FreeCAD adapter invokes aieng CLI (enrichment, topology, validation)
      ▼
.aieng package (ZIP archive)
      │
      ├── manifest.json
      ├── geometry/topology_map.json
      ├── graph/feature_graph.json
      ├── graph/aag.json
      ├── validation/status.yaml
      ├── validation/completeness_report.json
      ├── ai/summary.md
      └── ...
      │
      ▼
aieng-ui: GET /api/projects/{id}
      │  reads package → project summary
      ▼
React SPA displays:
  · semantic summary panel
  · Three.js 3D viewer (GLB/STL)
  · CAE panel (conditional, when CAE resources present)
  · chat/orchestration panel
```

---

## Data Flow: Runtime Orchestration

```
User types message in chat panel
      │
      ▼
"发送到本地运行时" button
      │
      ▼
api.startRun(message, project_id)
      │  POST /api/runtime/runs
      ▼
execute_run(RunRecord, ctx)
      │
      ├─► build_plan(message)         intent-based keyword matching
      │         │
      │         └── [aieng.inspect_package, aieng.refresh_semantics, ...]
      │
      ├─► for each step:
      │     emit tool_started
      │     call tool handler (closure over active_settings)
      │     emit tool_succeeded / tool_failed
      │     if requires_approval → emit approval_required, pause
      │
      └─► emit run_completed / run_failed
      │
      ▼
RunRecord persisted to disk (data/runtime/runs/)
      │
      ▼
JSON response → React displays:
  · run status badge ("运行时")
  · plan steps (tool_started / succeeded / failed)
  · errors
  · summary string
```

---

## What is Implemented vs Planned

### Implemented ✅

| Component | Location | Phase |
|-----------|----------|-------|
| `.aieng` package format (Phases 0–20) | `aieng/` | 0 |
| STEP import + topology + enrichment | `aieng/` | 0 |
| Feature recognition, AI summary | `aieng/` | 0 |
| CAE scaffold, evidence ledger, claim map | `aieng/` | 0 |
| MCP server (`aieng serve`) | `aieng/` | 0 |
| FreeCAD MCP execution interface | `aieng_freecad_mcp/` | 0 (mock/surrogate paths) |
| Evidence and claim policy enforcement | `aieng_freecad_mcp/` | 0 |
| FastAPI service layer | `aieng-ui/backend/` | 0 |
| React SPA with Three.js viewer | `aieng-ui/frontend/` | 0 |
| Runtime module (models + executor) | `aieng-ui/backend/app/runtime.py` | 0 |
| 4 aieng tool adapters | `aieng-ui/backend/app/main.py` | 0 |
| Synthetic scalar field colormap | `aieng-ui/frontend/src/App.tsx` | 0 (y_normalized — not real solver data) |
| File-backed run persistence | `aieng-ui/backend/app/runtime.py` | 1 |
| Approval + rejection endpoints | `aieng-ui/backend/app/main.py` | 1 |
| Run listing + tool introspection endpoints | `aieng-ui/backend/app/main.py` | 1 |
| Frontend approve/reject UI | `aieng-ui/frontend/src/App.tsx` | 1 |
| `freecad.inspect_geometry` — FreeCADCmd bridge | `aieng-ui/backend/app/main.py` | 2 |
| `geometry_inspector.py` in `aieng_freecad_mcp` | `aieng_freecad_mcp/src/` | 2 |
| `freecad.export_step` — FreeCADCmd bridge | `aieng-ui/backend/app/main.py` | 2.5 |
| `step_exporter.py` in `aieng_freecad_mcp` | `aieng_freecad_mcp/src/` | 2.5 |
| `ToolResult.artifacts` hoisting | `aieng-ui/backend/app/runtime.py` | 2.5 |
| Frontend changed-artifact display | `aieng-ui/frontend/src/App.tsx` | 2.5 |
| `AiengRuntimeClient` (HTTP client) | `aieng_freecad_mcp/src/` | 3 |
| 7 MCP runtime bridge tools | `aieng_freecad_mcp/src/freecad_mcp/tools_runtime/` | 3 |

### Not Yet Implemented ❌

| Component | Target location | Notes |
|-----------|----------------|-------|
| `freecad.run_macro` wired to real execution | `aieng_freecad_mcp/` | Skeleton; approval-gated but not connected |
| Mesh generation (Gmsh/Netgen) | `aieng_freecad_mcp/` | Dependency: FreeCAD FEM workbench |
| External solver result import (CalculiX/OpenFOAM) | `aieng/` + `aieng-ui/backend/` | External solver outputs imported into `.aieng`; solvers are not hosted here |
| Real solver field serving (VTK/HDF5) | `aieng-ui/backend/` | Endpoint returns synthetic descriptor; real per-node data path TBD |
| Streaming events (SSE/WebSocket) | `aieng-ui/backend/` | Currently poll-based |

---

## Design Invariants

1. **Chat is an orchestration layer**, not an LLM API wrapper. Every message becomes a structured plan of auditable tool calls.

2. **MCP is one protocol adapter**, not the whole architecture. Both `aieng` and `aieng_freecad_mcp` have MCP surfaces. The `aieng_freecad_mcp` runtime bridge tools (Phase 3) wrap the `aieng-ui` REST API as MCP tools without changing the runtime itself.

3. **FreeCAD is replaceable**. The provider interface in `aieng-ui/backend/app/providers/` is pluggable. FreeCAD is first because it is open-source and Python-friendly.

4. **`.aieng` is the stable artifact contract**. CAD tools come and go; the package format persists. AI agents reason from package contents, not raw geometry.

5. **External agents use the same runtime as the UI**. Claude Code, Codex, and custom MCP clients call `POST /api/runtime/runs` through the MCP bridge or directly; they do not drive the browser DOM.

6. **Evidence is not a claim**. Solver results, mesh outputs, and external measurements are ingested as evidence. Claims require explicit update and evidence backing.

---

## Terminology

| Term | Definition |
|------|------------|
| **`aieng`** | The semantic package engine and `.aieng` format library. Owns STEP import, topology extraction, feature recognition, AI summarisation, CAE scaffold, evidence ledger, claim map, and validation. Does not host the web UI, run the workbench orchestrator, or manage FreeCAD processes. |
| **`aieng-ui`** | The web workbench: React SPA + FastAPI service layer + local orchestration runtime. Owns project/file management, the `RunRecord`/`ToolCall`/`ToolResult`/`RuntimeEvent` model, the tool registry, and the approval gate. The runtime is the authoritative orchestration layer for both the UI and external agents. |
| **`aieng_freecad_mcp`** | The FreeCAD execution adapter and MCP protocol surface. Owns FreeCAD subprocess management, guard policy enforcement, evidence writeback, and the MCP runtime bridge that delegates to the `aieng-ui` REST API. Does not define the `.aieng` schema and does not host the orchestration runtime. |
| **runtime** | The local orchestration runtime inside `aieng-ui/backend/app/runtime.py`. Manages runs (`RunRecord`), events (`RuntimeEvent`), plan building, tool execution, approval gates, and file-backed persistence. All orchestration — from the browser chat panel, from the REST API, and from the MCP bridge — goes through this runtime. |
| **MCP** | Model Context Protocol. Used as a protocol adapter in two places: `aieng serve` exposes package-level tools; `aieng_freecad_mcp` exposes runtime bridge tools that delegate to the `aieng-ui` REST API. MCP is not the orchestration layer. |
| **FreeCAD** | An open-source CAD application used as the first CAD execution backend. Invoked via `FreeCADCmd` subprocess by `aieng_freecad_mcp`. Replaceable via the provider interface in `aieng-ui/backend/app/providers/`. |
