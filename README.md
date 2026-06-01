# aieng — CAD/CAE Agent Workbench

![CAD](https://img.shields.io/badge/CAD-build123d%20%2F%20OpenCASCADE-1f6feb)
![FEA](https://img.shields.io/badge/FEA-CalculiX-e36209)
![Agent](https://img.shields.io/badge/agent-MCP%20server-8957e5)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)

A co-pilot platform for mechanical engineering. It lets AI agents (Claude Code,
GitHub Copilot, OpenAI Codex, Cursor, …) drive **real 3D CAD modeling** (via
[build123d](https://github.com/gumyr/build123d) / OpenCASCADE) and **structural FEA**
(via CalculiX), with every project stored as a self-describing `.aieng` package.

## Highlights

- **Real geometry, no API key** — the agent writes build123d code; the backend runs it deterministically and returns STEP/STL/GLB plus a 4-view thumbnail.
- **Incremental modeling** — `append` builds onto the previous result; parts carry semantic `.label` names and colors that persist across steps.
- **Click-to-pick faces** — the 3D viewer maps each GLB primitive to its exact B-Rep face, so you click a face to bind a CAE load or support (`@face:` pointers).
- **CAD → FEA in one package** — material, BCs, mesh, CalculiX run, and results all live in one self-describing `.aieng` file.
- **Discoverable projects** — builds auto-name from their parts; locate any model by a part label via `aieng.find_projects_by_part`.
- **One source, many representations** — a neutral **Shape IR** compiles through a pluggable backend registry: build123d/OCP (exact STEP/B-Rep), **NURBS** B-Rep surfaces (OCP), implicit **SDF** (organic → mesh), or **Manifold** (CSG mesh). B-Rep targets keep analytic per-face topology; mesh targets give fast previews. STEP/GLB are derived evidence at different levels, recorded in provenance.
- **Conservative mesh-to-CAD ladder:** mesh/topology-optimization outputs can be analyzed into analytic face candidates and OCC-sewn shells. `geometry/reconstructed.step` is written only when OCC validates a closed solid and roundtrip checks run; it is a derived artifact and does not overwrite source/generated STEP. Original mesh topology is preserved at `geometry/mesh_topology_map.json`, and partial shells/invalid solids remove stale reconstructed artifacts instead of making production CAD claims.
- **Assembly CAE v0:** optional Assembly IR packages can produce a solver-neutral simplified proxy CAE model, optional simplified CalculiX deck when real mesh refs exist, honest skipped solver diagnostics, and assembly result maps back to parts/interfaces/connections. It does not model nonlinear contact or bolt preload and is not production certified.
- **Driven over MCP** — one tool registry, usable from Claude Code, Copilot, Codex, and Cursor.

---

## Repository layout

| Path | Status | What it is |
|------|--------|------------|
| **`aieng-ui/`** | **Active** | FastAPI backend + React workbench + MCP server — the product |
| `aieng/` | Library | `.aieng` semantic package format engine (schemas, validation, CLI) |
| `aieng-agent-skills/` | Active | SKILL.md contracts teaching agents how to use the ecosystem |
| `aieng-freecad-mcp/` | **Legacy** | Old FreeCAD execution adapter — not used by the active path |
| `CAD-Agent-main/` | Reference | Experimental/auxiliary CAD-agent material |
| `docs/` | — | Workspace-level roadmap & planning |

> The active CAD engine is `aieng-ui/backend` using **build123d** — *not* `aieng/`
> (which ships a stub backend) and *not* the legacy FreeCAD adapter.

---

## Quick start

Prerequisites: a conda env named **`aieng311`** (Python ≥ 3.11) with **build123d**
installed — the MCP config and run scripts assume this name.

```bash
# 1. Create the environment and install the backend (which pulls in build123d)
conda create -n aieng311 python=3.11 -y
conda activate aieng311
pip install build123d
cd aieng-ui/backend && pip install -e .

# 2. Run the backend (FastAPI on http://127.0.0.1:8000)
#    Windows helper handles interpreter selection + port guard:
#      ../scripts/backend.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. Run the frontend (Vite dev server on http://localhost:5173)
cd ../frontend && npm install && npm run dev
#    Windows helper: aieng-ui/scripts/frontend.ps1
```

Open http://localhost:5173 for the workbench UI.

Run the backend test suite:
```bash
cd aieng-ui/backend && python -m pytest
```

---

## Using it from an AI agent (MCP)

The backend exposes its tool registry as an **MCP server** (`aieng-workbench`), so an
agent drives the workbench through its own harness — no API key needed on our side.

Connection configs are **already committed** and load automatically for a fresh clone
(assuming the `aieng311` env exists):

| Agent | Config file |
|-------|-------------|
| Claude Code | `.mcp.json` |
| VS Code / GitHub Copilot / Cursor | `.vscode/mcp.json` |
| OpenAI Codex | add `[mcp_servers.*]` to `~/.codex/config.toml` (see MCP_SETUP) |

**First three calls every session:**
```
1. aieng.agent_readme                  → full agent guide (AGENTS.md, in-band)
2. aieng.list_projects                 → discover project IDs
3. aieng.agent_context { project_id }  → geometry state, pointers, next steps
```

**The sustainable modeling loop:**
```
cad.get_source            → see accumulated source, named parts, has_base
cad.execute_build123d     → build/extend geometry (mode=replace|append)
                            • set .label on parts → semantic names you can reference
                            • mode=append builds onto `previous_result`
                            • returns a thumbnail + named_parts / parts_added
(inspect the result, repeat)
```

Full details, tool taxonomy, pointer syntax, and approval-gated tools:
**[AGENTS.md](AGENTS.md)** · MCP wiring: **[aieng-ui/backend/MCP_SETUP.md](aieng-ui/backend/MCP_SETUP.md)**

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](AGENTS.md) | Canonical agent guide — tools, workflows, conventions (also served by `aieng.agent_readme`) |
| [CLAUDE.md](CLAUDE.md) | Claude Code entry pointer |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | GitHub Copilot entry pointer |
| [aieng-ui/backend/MCP_SETUP.md](aieng-ui/backend/MCP_SETUP.md) | Per-agent MCP wiring (Claude Code / Copilot / Codex) |

---

## Notes

- **Private repo.** No secrets are committed; runtime data (`data/projects/`),
  virtual environments, `node_modules`, and embedded conda envs are gitignored.
- If your CAD env is not named `aieng311`, edit the `-n aieng311` argument in the MCP
  configs (or point `command` directly at your interpreter) — see MCP_SETUP.md.
- A running backend at `http://127.0.0.1:8000` enables live UI updates when an agent
  drives a build; if it's down, the MCP server falls back to in-process execution.
