# Active Paths Architecture

This document maps every top-level path in this repository to its status, role,
and guidance for contributors and AI agents.

---

## Path inventory

| Path | Status | Role | Guidance |
|---|---|---|---|
| `aieng-ui/backend` | Active runtime | FastAPI, MCP tools, build123d/OCP CAD execution, CAE orchestration | New runtime/API/tool execution work starts here |
| `aieng/` | Core semantic library | `.aieng` package engine, Shape IR, schemas, validation, CLI, artifact/evidence model | Reuse or extend for IR, schema, validation, transformations, package semantics |
| `aieng-ui/frontend` | Active UI | React workbench and review interface | New product UI work starts here |
| `aieng-agent-skills/` | Active agent contracts | Agent-facing usage instructions | Update when workflow/tool contracts change |
| `legacy/aieng-freecad-mcp` | Legacy adapter | Old FreeCAD MCP adapter, compatibility/reference only | Do not use as default runtime |
| `archive/CAD-Agent-main` | Archived reference | Historical/experimental auxiliary CAD-agent material | Do not add production features here |

---

## Rules for development

- **Default do not develop in `archive/` or `legacy/`**. These areas are
  preserved for reference and compatibility only.
- **CAD/CAE execution work** starts from `aieng-ui/backend`. That is where
  build123d/OCP runs, MCP tools are registered, and the active runtime lives.
- **Shape IR, schema, validation, `.aieng` package/evidence model** work starts
  from `aieng/`. This is the core semantic library; it is **not** legacy.
- **If you genuinely need to migrate logic** from `archive/` or `legacy/` into
  an active path, explicitly state: (1) what you are migrating, (2) why it is
  needed in an active path, and (3) the target active path.

---

## Notes

- `aieng/` carries a `FakeBackend` stub for offline testing, but its real value
  is the schema, validation, CLI, and package semantics — treat it as a core
  library, not a dead end.
- `legacy/aieng-freecad-mcp` is retained for future FreeCAD compatibility and
  as a reference MCP adapter implementation. It is not wired into the default
  build123d workflow.
- `archive/CAD-Agent-main` preserves a CadQuery-first agent skill experiment.
  Nothing in it is on the active execution path.

## Local development startup

The cross-platform launcher lives at `scripts/dev.py`. It starts both the active
backend (`aieng-ui/backend`) and frontend (`aieng-ui/frontend`) concurrently.

| Platform | Command |
|---|---|
| Windows PowerShell | `.\dev.ps1` |
| macOS / Linux / WSL | `make dev` or `./scripts/dev.sh` |
| Any (fallback) | `python scripts/dev.py` |

Individual services:
- Backend only: `make backend` (or `cd aieng-ui/backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`)
- Frontend only: `make frontend` (or `cd aieng-ui/frontend && npm run dev`)

Environment variables: `BACKEND_PORT`, `FRONTEND_PORT`, `AIENG_PYTHON`.
