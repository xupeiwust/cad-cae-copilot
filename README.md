# aieng — CAD/CAE Agent Workbench

![CAD](https://img.shields.io/badge/CAD-build123d%20%2F%20OpenCASCADE-1f6feb)
![FEA](https://img.shields.io/badge/FEA-CalculiX-e36209)
![Agent](https://img.shields.io/badge/agent-MCP%20server-8957e5)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)

A co-pilot platform for mechanical engineering. It lets AI agents (Claude Code,
GitHub Copilot, OpenAI Codex, Cursor, …) drive **real 3D CAD modeling** (via
[build123d](https://github.com/gumyr/build123d) / OpenCASCADE) and **structural FEA**
(via CalculiX), with every project stored as a self-describing `.aieng` package.

## What this is

An **AI-CAD/CAE backend prototype** that combines:
- **Shape IR** — a neutral geometry intermediate that compiles to build123d/OCP STEP/B-Rep, NURBS, implicit SDF, or Manifold mesh
- **Real CAD generation** — agent-written build123d code runs deterministically; returns STEP/STL/GLB + 4-view thumbnail
- **CAE result mapping** — CalculiX FRD results mapped back to topology entities with `@face:` pointers
- **Topology optimization** — 2D SIMP (stable) + experimental 3D structured-voxel SIMP
- **Mesh-to-CAD reconstruction** — mesh → analytic surface fitting → OCC face generation → stitching → sewing → STEP export (only when shell validates)
- **Assembly-aware optimization** — multi-part assembly IR with proxy CAE, interface resolution, and selected-part topopt
- **Agent-guided design studies** — explicit candidate validation, execution, ranking, and acceptance with baseline preservation

**Honesty boundaries:**
- Not production-certified CAD/CAE — outputs are review material requiring human judgment
- Assembly contact/bolt preload are proxy-only; real nonlinear contact is future work
- 3D SIMP is experimental/reference, not production-certified
- Mesh-to-CAD works best for plane/cylinder-dominant geometry; freeform/NURBS fitting is future work
- Design study is agent-guided explicit execution, not autonomous global optimization

<img src="docs/assets/showcase/architecture_overview.svg" width="900" alt="AI-CAD/CAE Backend Architecture"/>

## Highlights

- **Real geometry, no API key** — the agent writes build123d code; the backend runs it deterministically and returns STEP/STL/GLB plus a 4-view thumbnail.
- **Incremental modeling** — `append` builds onto the previous result; parts carry semantic `.label` names and colors that persist across steps.
- **Click-to-pick faces** — the 3D viewer maps each GLB primitive to its exact B-Rep face, so you click a face to bind a CAE load or support (`@face:` pointers).
- **CAD → FEA in one package** — material, BCs, mesh, CalculiX run, and results all live in one self-describing `.aieng` file.
- **Discoverable projects** — builds auto-name from their parts; locate any model by a part label via `aieng.find_projects_by_part`.
- **One source, many representations** — a neutral **Shape IR** compiles through a pluggable backend registry: build123d/OCP (exact STEP/B-Rep), **NURBS** B-Rep surfaces (OCP), implicit **SDF** (organic → mesh), or **Manifold** (CSG mesh). B-Rep targets keep analytic per-face topology; mesh targets give fast previews. STEP/GLB are derived evidence at different levels, recorded in provenance.
- **Conservative mesh-to-CAD ladder:** mesh/topology-optimization outputs can be analyzed into analytic face candidates and OCC-sewn shells. `geometry/reconstructed.step` is written only when OCC validates a closed solid and roundtrip checks run; it is a derived artifact and does not overwrite source/generated STEP. Original mesh topology is preserved at `geometry/mesh_topology_map.json`, and partial shells/invalid solids remove stale reconstructed artifacts instead of making production CAD claims.
- **Assembly CAE + topopt v0:** optional Assembly IR packages can produce a solver-neutral simplified proxy CAE model, optional simplified CalculiX deck when real mesh refs exist, honest skipped solver diagnostics, and assembly result maps back to parts/interfaces/connections. Backend-only assembly-aware topology optimization derives a single selected design-part problem, then explicit execution can run the existing SIMP optimizer and write selected-part derived artifacts (`analysis/assembly_topology_optimization.json`, `diagnostics/assembly_topopt_execution.json`, `parts/<part_id>/...`) while preserving interface regions where mapped. It does not model nonlinear contact, bolt preload, or simultaneous multi-part optimization and is not production certified.
- **Driven over MCP** — one tool registry, usable from Claude Code, Copilot, Codex, and Cursor.

---

## Showcase demos

Four canonical backend demos, each deterministic and self-contained (no external solver required).

### 1. CAD Generation → Structural FEA → Topology Optimization

Derives a topology optimization problem from structural analysis, runs SIMP compliance minimization, and writes back optimized geometry as an editable design model.

<img src="docs/assets/showcase/geometry_cae_flow.svg" width="800" alt="CAD Generation → Structural FEA → Topology Optimization"/>

```bash
pytest aieng/tests/test_topology_optimization.py -q
```

**Key artifacts:** `analysis/topology_optimization.json`, `geometry/shape_ir.json`  
**Boundary:** 2D plane-stress; 3D SIMP is experimental/reference only · [Details →](aieng/docs/showcase_gallery.md)

---

### 2. Rebuild CAD from Mesh → Export STEP

Takes a mesh, segments it into regions, fits analytic surfaces, generates validated CAD faces, stitches edges, sews into a closed shell, and exports a STEP file — with honest fallback when the shell is not closed.

<img src="docs/assets/showcase/mesh_to_cad_flow.svg" width="880" alt="Mesh → Region Segmentation → Surface Fitting → Face Generation → Sew Shell → Export STEP"/>

```bash
pytest aieng/tests/test_mesh_brep_solidification.py -q
```

**Key artifacts:** `geometry/reconstructed.step` (when valid), `graph/mesh_brep_stitching_plan.json`  
**Boundary:** Mesh-derived/lossy; plane/cylinder dominant; freeform/NURBS future work; partial shells do NOT produce STEP · [Details →](aieng/docs/showcase_gallery.md)

---

### 3. Assembly Model → Selected-Part Optimization

Represents a multi-part assembly with parts, interfaces, and connections; resolves interface geometry; builds a simplified proxy analysis model; derives a topology optimization problem for one selected design part while preserving mounting and load interfaces.

<img src="docs/assets/showcase/assembly_optimization_flow.svg" width="880" alt="Assembly Model → Resolve Interfaces → Simplified Analysis → Topopt Problem → Optimized Part"/>

```bash
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q
```

**Key artifacts:** `analysis/assembly_topology_optimization.json`, `parts/bracket/geometry/optimized_shape_ir.json`  
**Boundary:** Proxy connections only; no real contact/friction/bolt preload; one design part only; not production-certified · [Details →](aieng/docs/showcase_gallery.md)

---

### 4. Design Study: Adjustable Dimensions → Compare → Adopt

An agent proposes parameter changes; the backend validates each proposal against safety rules, executes valid candidates into isolated design copies, compares them by objective and constraints, and allows explicit adoption of the best safe design — baseline geometry is never modified.

<img src="docs/assets/showcase/design_study_flow.svg" width="960" alt="Setup Problem → Propose Candidate → Safety Checks → Build Design Copy → Compare Options → Adopt Best"/>

```bash
pytest aieng-ui/backend/tests/test_design_study_demo.py -q
```

**Key artifacts:** `analysis/design_study_candidate_ranking.json`, `analysis/design_study_acceptance.json`, `accepted/candidate_good/geometry/shape_ir.json`  
**Boundary:** Static metrics in demo; no autonomous optimization; no baseline overwrite; ranking is advisory · [Details →](aieng/docs/showcase_gallery.md)

---

## Repository layout

### Active

| Path | Status | What it is |
|------|--------|------------|
| **`aieng-ui/`** | **Active** | FastAPI backend + React workbench + MCP server — the product |
| `aieng/` | Core library | `.aieng` semantic package format engine (schemas, validation, CLI, Shape IR, evidence model) |
| `aieng-agent-skills/` | Active | SKILL.md contracts teaching agents how to use the ecosystem |

### Non-active but retained

| Path | Status | What it is |
|------|--------|------------|
| `legacy/aieng-freecad-mcp/` | **Legacy** | Old FreeCAD execution adapter — not used by the active path |
| `archive/CAD-Agent-main/` | Archived | Historical/experimental auxiliary CAD-agent material |

> The active CAD engine is `aieng-ui/backend` using **build123d** — *not* `aieng/`
> (which ships a stub backend for tests) and *not* the legacy FreeCAD adapter.
> `aieng/` is the **core semantic library**; do not treat it as legacy.

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
| [aieng/docs/showcase_gallery.md](aieng/docs/showcase_gallery.md) | **Showcase gallery** — demo talking points, visual guidance, and honesty boundaries |
| [aieng/docs/demo_catalog.md](aieng/docs/demo_catalog.md) | Backend demo catalog — run commands, expected artifacts, maturity levels |
| [aieng/docs/backend_capability_matrix.md](aieng/docs/backend_capability_matrix.md) | Capability status snapshot (stable / experimental / diagnostic-only / proxy-only) |
| [aieng/docs/backend_artifact_reference.md](aieng/docs/backend_artifact_reference.md) | Complete artifact path reference for geometry, CAE, topopt, reconstruction, assembly |
| [aieng/docs/roadmap.md](aieng/docs/roadmap.md) | Phase-by-phase development roadmap |
| [CLAUDE.md](CLAUDE.md) | Claude Code entry pointer |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | GitHub Copilot entry pointer |
| [aieng-ui/backend/MCP_SETUP.md](aieng-ui/backend/MCP_SETUP.md) | Per-agent MCP wiring (Claude Code / Copilot / Codex) |

---

## Smoke tests

Run the canonical backend demos in ~15 seconds:

```bash
# Agent-guided design study (PR1–PR4)
pytest aieng-ui/backend/tests/test_design_study_demo.py -q

# Assembly-aware topology optimization
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q

# Mesh-to-CAD B-Rep reconstruction
pytest aieng/tests/test_mesh_brep_solidification.py -q

# Single-part topology optimization
pytest aieng/tests/test_topology_optimization.py -q
```

---

## Notes

- **Private repo.** No secrets are committed; runtime data (`data/projects/`),
  virtual environments, `node_modules`, and embedded conda envs are gitignored.
- If your CAD env is not named `aieng311`, edit the `-n aieng311` argument in the MCP
  configs (or point `command` directly at your interpreter) — see MCP_SETUP.md.
- A running backend at `http://127.0.0.1:8000` enables live UI updates when an agent
  drives a build; if it's down, the MCP server falls back to in-process execution.
