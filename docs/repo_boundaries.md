# Repository Boundaries

---

## Ownership Table

| Repo | Owns | Does Not Own | Public Interfaces |
|------|------|--------------|-------------------|
| **`aieng`** | `.aieng` package format and schema; STEP import pipeline; topology extraction; feature recognition; constraint parsing; AI summarisation; validation; evidence ledger; claim map; CAE scaffold (CalculiX deck export); MCP server (`aieng serve`) | CAD geometry execution; FreeCAD process management; solver execution; UI rendering; run orchestration | Python API (`from aieng import ...`); CLI (`aieng import-step`, `aieng validate`, `aieng summarize`, ...); MCP tools via `aieng serve`; ZIP package artifacts |
| **`aieng_freecad_mcp`** | FreeCAD execution surface; MCP-facing tool contract; guard policy enforcement; evidence writeback; tool trace recording; milestone acceptance scripts | Package format definition; topology schema; AI summarisation; UI; run orchestration; solver selection | MCP tool handlers (`aieng_parse_patch`, `aieng_execute_patch`, `aieng_run_cad_to_cae_workflow`, `aieng_update_claim`, ...); composable demo scripts |
| **`aieng-ui`** | Web workbench UI; FastAPI service layer; local orchestration runtime; project/file management; preview asset generation; chat interface; audit log display; CAD provider registry | Package format definition; FreeCAD internals; solver choice; agent/MCP protocol decisions | REST API (`/api/projects/...`, `/api/runtime/runs`, `/api/runtime/runs/{id}`, `/api/runtime/runs/{id}/events`); built frontend SPA at `/` |

---

## Logic That Must Not Cross Boundaries

### aieng should not contain:
- HTTP server code for the workbench UI
- FreeCAD subprocess management
- Three.js or any frontend rendering logic
- Run orchestration state machines (RunRecord, RuntimeEvent, ToolCall)
- Project-level file management (uploading STEP files, project metadata JSON)

### aieng_freecad_mcp should not contain:
- `.aieng` schema definitions or package ZIP I/O (reads and writes via the `aieng` API)
- Semantic claim logic — the MCP adapter enforces that claim updates are explicit and evidence-backed, but the claim format belongs to `aieng`
- UI components or web server routes
- Run orchestration or runtime event models

### aieng-ui should not contain:
- Business logic that duplicates `aieng` (topology parsing, feature recognition, AI summary generation)
- Direct FreeCAD Python API calls in the web backend (the provider interface delegates to `aieng_freecad_mcp` or an equivalent adapter)
- `.aieng` schema definitions (reads the package but does not define its shape)
- Claim advancement logic (reads evidence/claims from the package, but never writes claims directly)

---

## Current Coupling Points

These are the places where the repos intentionally touch each other. They are the designed integration surface, not leakage.

```
aieng-ui/backend
    │
    │  bridge_runner.py invokes aieng CLI via subprocess
    │  (import-step, enrich, validate commands)
    │
    └──► aieng/   (aieng CLI on PATH or AIENG_ROOT)

aieng-ui/backend
    │
    │  freecad_bridge.py injects aieng_freecad_mcp/src into sys.path
    │  and calls run_geometry_inspection() / run_step_export() directly
    │
    └──► aieng_freecad_mcp/src/   (sibling path; no package install required)

aieng_freecad_mcp
    │
    │  AiengRuntimeClient calls aieng-ui REST API over HTTP
    │  (AIENG_RUNTIME_BASE_URL, default http://localhost:8000)
    │
    └──► aieng-ui/backend/   (HTTP; runtime bridge tools in tools_runtime/)

aieng_freecad_mcp
    │
    │  reads/writes .aieng packages using the aieng Python API
    │
    └──► aieng/   (import as dependency)
```

---

## Provider Pluggability in aieng-ui

The `aieng-ui` backend uses a provider interface to isolate CAD-backend concerns:

```
backend/app/providers/
    protocols.py       ← abstract interface (import_step_to_package,
                                             enrich_package,
                                             validate_package,
                                             export_step_preview_to_stl,
                                             package_summary_snapshot,
                                             probe_capabilities, ...)
    registry.py        ← maps "freecad" → FreeCADAdapter
    freecad/
        adapter.py     ← FreeCADAdapter: implements protocols.py
        bridge_runner.py ← calls aieng CLI + FreeCADCmd
        preview.py     ← STL/GLB preview generation
```

A second CAD backend (SolidWorks, Fusion, generic STEP) would add a new directory under `providers/` and register in `registry.py`. The rest of the service layer does not change.

---

## What External Agents Should Call

External agents (Claude Code, Codex, custom MCP clients) should use the **same runtime layer as the UI**, not drive the browser directly.

```
Preferred entry points:
  POST /api/runtime/runs           — start a structured run
  GET  /api/runtime/runs/{id}      — poll run status
  GET  /api/runtime/runs/{id}/events — poll event list
  GET  /api/projects/{id}          — read project semantic state

Do not:
  Scrape or automate the browser DOM
  Call /api/projects/{id}/chat as an agent loop without the runtime model
  Bypass the approval gate for freecad.run_macro or any requires_approval tool
```

The MCP runtime bridge in `aieng_freecad_mcp` (`tools_runtime/`) wraps these same endpoints, presenting them as MCP tools. No special code path is needed on the runtime side.
