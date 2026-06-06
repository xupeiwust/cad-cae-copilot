<div align="center">

# aieng

### Give AI agents a real engineering workspace, not just a CAD code generator.

Turn explicit engineering specifications into real CAD geometry, inspect the
result with stable topology references, and preserve every artifact in a
reproducible `.aieng` package.

<a href="docs/assets/images/hero.webp">
  <img src="docs/assets/images/hero.webp" width="100%" alt="A fully specified industrial motor mounting fixture modeled and inspected with aieng"/>
</a>

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/armpro24-blip/workspace_aieng)
![CAD](https://img.shields.io/badge/CAD-build123d%20%2F%20OpenCASCADE-1f6feb)
![FEA](https://img.shields.io/badge/FEA-CalculiX-e36209)
![Agent](https://img.shields.io/badge/agent-MCP%20server-8957e5)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)

[Quick Start](#quick-start) ·
[Industrial CAD Examples](#industrial-cad-examples) ·
[MCP Setup](aieng-ui/backend/MCP_SETUP.md) ·
[Agent Guide](AGENTS.md)

</div>

<div align="center">

**Specification → Real CAD → Verified Geometry → Reproducible Package**

Real STEP/STL/GLB · Editable parameters · Named parts · Stable topology pointers
· Deterministic critique · CAD → CAE artifacts · Approval-gated actions

</div>

## From specification to verified CAD

The hero model was created from an explicit industrial fixture specification:
fixed dimensions, named parts, exact hole and slot locations, required symmetry,
and no permission to invent additional geometry.

<details>
<summary><strong>Copy the motor mounting fixture prompt</strong></summary>

```text
Create a fully specified industrial motor mounting fixture using millimeters.

Coordinate system:
- X is the fixture width, Y is the fixture depth, and Z is vertical.
- Center the complete fixture on X=0.
- Place the bottom face of the base plate at Z=0.

Base plate:
- Create a 180 × 140 × 14 mm base plate.
- Add four Ø11 mm vertical through-holes at X=±70 mm and Y=±50 mm.
- Add an Ø18 mm, 5 mm deep counterbore to the top of every mounting hole.
- Add a 3 mm fillet to the four outside vertical corners.

Motor support:
- Add a centered rear vertical support plate, 130 mm wide, 14 mm thick,
  and 120 mm tall above the base.
- Add a Ø72 mm horizontal locating bore through the plate along Y.
- Position its center at X=0 and Z=78 mm.
- Add four Ø8.5 mm horizontal mounting holes on a Ø100 mm bolt circle.

Reinforcement and rails:
- Add two mirrored 12 mm thick triangular gussets extending 45 mm forward
  and rising 65 mm above the base.
- Add two separate 110 × 12 × 8 mm guide rails centered at X=±38 mm, Y=-12 mm.
- Add one centered 70 × 6 mm longitudinal slot to each rail.

Modeling requirements:
- Create named parts "fixture_body", "guide_rail_left", and "guide_rail_right".
- Color the fixture body dark blue-gray and both guide rails orange.
- Declare all major dimensions as editable UPPER_SNAKE_CASE constants.
- Preserve exact left/right symmetry.
- Verify overall dimensions, named parts, and stable topology pointers.
- Run the deterministic engineering critique after modeling.
- Do not add a motor, fasteners, logos, decorative features, or unspecified geometry.
```

</details>

## Industrial CAD examples

These examples start from explicit dimensions, feature locations, and modeling
constraints. The agent executes and verifies the specification; it does not
silently invent the engineering requirements.

<table>
  <tr>
    <td width="33%" align="center">
      <a href="docs/assets/images/example1.webp">
        <img src="docs/assets/images/example1.webp" width="100%" alt="aieng generating and verifying a fully specified machined bearing support bracket"/>
      </a>
      <br>
      <strong>Machined Bearing Bracket</strong>
      <br>
      <sub>Datums, bore, mounting pattern, gussets, fillets, and critique</sub>
    </td>
    <td width="33%" align="center">
      <a href="docs/assets/images/example2.webp">
        <img src="docs/assets/images/example2.webp" width="100%" alt="aieng generating and auditing a fully specified six-port pneumatic manifold"/>
      </a>
      <br>
      <strong>Six-Port Pneumatic Manifold</strong>
      <br>
      <sub>Exact envelope, port spacing, counterbores, and editable dimensions</sub>
    </td>
    <td width="33%" align="center">
      <a href="docs/assets/images/example3.webp">
        <img src="docs/assets/images/example3.webp" width="100%" alt="aieng generating a named-part industrial junction-box assembly with stable face pointers"/>
      </a>
      <br>
      <strong>Industrial Junction Box</strong>
      <br>
      <sub>Named assembly parts, exported artifacts, and stable face pointers</sub>
    </td>
  </tr>
</table>

<details>
<summary><strong>What these examples verify</strong></summary>

- **Machined bearing support bracket** - one manufacturable solid with a
  specified base envelope, horizontal bearing bore, symmetric mounting pattern,
  mirrored gussets, fillets, and chamfers. The workbench caught and corrected
  construction errors, then verified the final datums, topology, editable
  parameters, and engineering critique.
- **Six-port pneumatic manifold** - a specification-driven manifold with an
  exact `160 × 50 × 40 mm` envelope, six equally spaced outlets, axial inlet
  ports, counterbored mounting holes, edge fillets, opening chamfers, and
  editable dimensions.
- **Industrial junction-box assembly** - a two-part enclosure assembly with
  named base and lid solids, internal mounting bosses, cable-gland openings,
  separated lid placement, generated STEP/STL/GLB artifacts, and a selectable
  stable face pointer for precise follow-up work.

</details>

## Beyond geometry generation

aieng is designed for the engineering work that happens before and after a
model first appears.

| Capability | Typical text-to-CAD demo | aieng |
|------------|:------------------------:|:-----:|
| Generate real CAD exports | Yes | Yes |
| Execute explicit dimensions and datums | Partial | Yes |
| Preserve editable source and parameters | Partial | Yes |
| Name parts and expose stable topology references | Rarely | Yes |
| Verify geometry and run deterministic critique | Rarely | Yes |
| Preserve artifacts and provenance in one package | Rarely | Yes |
| Continue from CAD into CAE workflows | Rarely | Yes |
| Require approval for gated engineering actions | Rarely | Yes |

## Why aieng?

Most AI CAD demos stop when a model appears. aieng treats geometry generation as
one step in a reviewable engineering workflow:

- **Real, exportable CAD** - agent-written build123d / OpenCASCADE geometry
  produces STEP, STL, GLB, topology maps, feature graphs, and review thumbnails.
- **Specification-driven execution** - agents can follow explicit dimensions,
  datums, feature positions, symmetry requirements, and manufacturing
  constraints instead of freely inventing a design.
- **Inspect and correct** - geometry reports, deterministic critiques, named
  parts, and stable `@face:*` pointers support precise verification and
  follow-up edits.
- **Reproducible engineering packages** - `.aieng` packages preserve geometry,
  generated source, analysis state, artifacts, metadata, and provenance.
- **Agent-independent MCP tools** - Claude Code, GitHub Copilot, OpenAI Codex,
  Cursor, and other MCP-capable agents can drive the same backend.
- **CAD to CAE path** - material, boundary conditions, mesh, solver runs, result
  mappings, and evidence can live beside the CAD model.

## How it works

1. Provide a mechanical specification with explicit dimensions and constraints.
2. An MCP-capable agent uses aieng tools to create real CAD geometry.
3. aieng exports the model and records named parts, topology, editable
   parameters, source, and provenance.
4. Inspect the result visually and numerically, then reference exact parts,
   features, or faces for follow-up changes.
5. Continue into CAE setup and solver workflows when the required engineering
   inputs are available.

The workbench UI and
[`aieng-vscode-extension`](aieng-vscode-extension) provide visual inspection for
live backend projects and `.aieng` packages.

## About aieng

aieng is an open-source AI-native CAD/CAE engineering workbench built around
self-describing `.aieng` project packages. It lets AI agents create real CAD
geometry, preserve engineering artifacts, run CAD/CAE workflows, and keep
results reproducible and inspectable.

The VS Code extension is the most visual way to experience aieng: it brings CAD
model inspection and the AI-CAD design loop directly into the editor, so agents
and humans can iterate on mechanical designs in one workspace.

## Highlights

- **AI-native engineering packages** - `.aieng` packages preserve geometry,
  artifacts, analysis data, metadata, and provenance in a reproducible project
  container.
- **Agent-driven CAD/CAE workflows** - Claude Code, GitHub Copilot, OpenAI
  Codex, Cursor, and other MCP-capable agents can drive the same engineering
  backend.
- **Real CAD geometry** - agent-written build123d / OpenCASCADE geometry
  produces STEP, STL, GLB, and 4-view thumbnails.
- **Visual inspection in VS Code** - the VS Code extension lets users inspect
  generated CAD models without leaving their AI coding workspace.
- **CAD to CAE path** - material, boundary conditions, mesh, solver runs, and
  result mappings can be preserved in the same package.
- **Inspectable provenance** - generated code, artifacts, analysis outputs, and
  agent context stay reviewable instead of becoming an opaque AI result.

## Experience aieng in VS Code

The VS Code extension is the fastest way to see what aieng does. It is a visual
front-end for the `.aieng` package format, MCP tools, and CAD/CAE backend.

1. Ask an AI agent to create or modify a mechanical part.
2. aieng stores the design intent, generated geometry, artifacts, and
   provenance in a `.aieng` package.
3. The backend generates real build123d / OpenCASCADE geometry.
4. The VS Code extension visualizes the generated CAD model.
5. The user inspects the result and continues the design loop with the agent.

The extension lives in [`aieng-vscode-extension`](aieng-vscode-extension) and
focuses on package preview, CAD inspection, and stable face-pointer copying.

## Who should try this?

- AI agent and MCP developers who want engineering tools that go beyond text
  and code generation.
- Mechanical engineers curious about AI-assisted CAD/CAE workflows with real
  geometry and explicit artifacts.
- Makers and researchers experimenting with AI-native engineering tools and
  reproducible design loops.
- Open-source contributors interested in CAD, CAE, VS Code extensions, MCP, or
  build123d / OpenCASCADE.

## Try it in one minute

1. Open this repository in GitHub Codespaces.
2. Run `make dev`.
3. Connect an MCP-capable agent using the committed configuration.
4. Copy the motor mounting fixture prompt above, or start with:

```text
Create a 120 × 80 × 12 mm machined bearing support bracket with a centered
Ø42 mm horizontal bearing bore, four Ø10 mm base mounting holes, and two
mirrored gussets. Preserve the exact dimensions, expose editable parameters,
verify the final geometry, and run the deterministic engineering critique.
```

5. Inspect the generated model, named parts, verification results, and stable
   `@face:*` references in the workbench.

## Quick start

### Option 1: GitHub Codespaces (fastest, zero install)

Click the **"Open in GitHub Codespaces"** button at the top of this README.
The environment will be fully set up automatically; just run `make dev` when
it finishes loading. If `make` is unavailable, run `python3 scripts/dev.py`
instead.

### Option 2: Docker all-in-one (recommended local package)

This path packages the backend, built viewer, MCP HTTP server, build123d /
OpenCASCADE dependencies, and CalculiX into one container.

```bash
docker build -t aieng/workbench:local .
docker run --rm -it \
  -p 8000:8000 \
  -p 8765:8765 \
  -v aieng-data:/data \
  aieng/workbench:local
```

Open the viewer at http://localhost:8000/app/. Point an MCP-over-HTTP client at
`http://localhost:8765/sse`. Generated projects and `.aieng` packages are kept
in the `aieng-data` Docker volume.

For the full local viewer experience, the container enables
`AIENG_MCP_MANAGED_APPROVAL=1` by default: approval-gated CAD/CAE tools surface
through the workbench approval UI instead of relying only on the client.

### Option 3: Local developer install

Prerequisites: a conda env named **`aieng311`** (Python >= 3.11) with
**build123d** installed - the MCP config and run scripts assume this name.

```bash
# 1. Create the environment and install the backend (which pulls in build123d)
conda create -n aieng311 python=3.11 -y
conda activate aieng311
pip install build123d
cd aieng-ui/backend && pip install -e .
```

### Start everything (one command)

**Windows PowerShell** (recommended):
```powershell
.\dev.ps1
```

**macOS / Linux / WSL** (recommended):
```bash
make dev
```

**Cross-platform fallback** (any OS):
```bash
python scripts/dev.py
# or on macOS/Linux:
python3 scripts/dev.py
```

This starts both the backend (FastAPI on `http://127.0.0.1:8000`) and the
frontend (Vite on `http://localhost:5173`) in one terminal. Press **Ctrl+C** to
stop both.

Custom ports:
```bash
BACKEND_PORT=8080 FRONTEND_PORT=3000 make dev
```

### Start services individually

**Backend only:**
```bash
make backend
# or manually:
cd aieng-ui/backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Frontend only:**
```bash
make frontend
# or manually:
cd aieng-ui/frontend && npm install && npm run dev
```

Open http://localhost:5173 for the workbench UI.

Run the backend test suite:
```bash
cd aieng-ui/backend && python -m pytest
```

## Using aieng from VS Code

The recommended visual entry point is the VS Code extension in
[`aieng-vscode-extension`](aieng-vscode-extension). It visualizes `.aieng`
project artifacts and generated CAD outputs inside the editor.

Extension-specific setup and development notes live in
[`aieng-vscode-extension/README.md`](aieng-vscode-extension/README.md). The
extension can:

- open a local `.aieng` package as a read-only custom editor,
- connect to a live backend project preview,
- visualize generated GLB/STL CAD outputs,
- and copy stable `@face:id` pointers back into your chat with an agent.

## Using aieng from AI agents via MCP

The backend exposes its tool registry as an **MCP server** (`aieng-workbench`),
so agents can drive the workbench through their own harnesses - no API key
needed on our side.

Connection configs are already committed and load automatically for a fresh
clone, assuming the `aieng311` env exists:

| Agent | Config file |
|-------|-------------|
| Claude Code | `.mcp.json` |
| VS Code / GitHub Copilot / Cursor | `.vscode/mcp.json` |
| OpenAI Codex | add `[mcp_servers.*]` to `~/.codex/config.toml` (see MCP_SETUP) |

**First three calls every session:**
```
1. aieng.agent_readme                  -> compact operational onboarding
2. aieng.list_projects                 -> discover project IDs
3. aieng.agent_context { project_id }  -> geometry state, pointers, next steps
```

Use `aieng.guide { topic }` for task-specific detail, or
`aieng.agent_readme { detail: "full" }` when the complete canonical
[`AGENTS.md`](AGENTS.md) is genuinely required.

**The sustainable modeling loop:**
```
cad.get_source            -> see accumulated source, named parts, has_base
cad.execute_build123d     -> build/extend geometry (mode=replace|append)
                            - set .label on parts -> semantic names you can reference
                            - mode=append builds onto `previous_result`
                            - returns a thumbnail + named_parts / parts_added
(inspect the result, repeat)
```

Full tool details, pointer syntax, and approval-gated operations:
[AGENTS.md](AGENTS.md)

MCP wiring by client:
[aieng-ui/backend/MCP_SETUP.md](aieng-ui/backend/MCP_SETUP.md)

## What this is

aieng combines:

- a self-describing `.aieng` project package format,
- an agent-facing MCP tool layer,
- a Python CAD/CAE backend,
- and a VS Code visualization extension.

The VS Code extension is one layer of the system, not the whole system. The
core of aieng is the package format and engineering backend that let agents and
humans share reproducible CAD/CAE project state.

Main capabilities in this repo:

- real build123d / OpenCASCADE CAD generation with STEP, STL, GLB, and thumbnails,
- CAE setup and result mapping with topology-aware pointers,
- topology optimization and mesh-to-CAD reconstruction workflows,
- assembly-aware proxy analysis and selected-part optimization,
- and explicit agent-guided design studies with baseline preservation.

## Showcase demos

Canonical backend demos:

### 1. CAD Generation -> Structural FEA -> Topology Optimization

Runs the CAD -> FEA -> topology optimization loop and writes back editable
optimized geometry.

<img src="docs/assets/showcase/geometry_cae_flow.svg" width="800" alt="CAD Generation to Structural FEA to Topology Optimization"/>

```bash
pytest aieng/tests/test_topology_optimization.py -q
```

**Key artifacts:** `analysis/topology_optimization.json`, `geometry/shape_ir.json`
**Boundary:** 2D plane-stress; 3D SIMP is experimental/reference only.
[Details ->](aieng/docs/showcase_gallery.md)

### 2. Rebuild CAD from Mesh -> Export STEP

Reconstructs analytic CAD from a mesh and exports STEP when the shell validates.

<img src="docs/assets/showcase/mesh_to_cad_flow.svg" width="880" alt="Mesh to Region Segmentation to Surface Fitting to Face Generation to Sew Shell to Export STEP"/>

```bash
pytest aieng/tests/test_mesh_brep_solidification.py -q
```

**Key artifacts:** `geometry/reconstructed.step` (when valid),
`graph/mesh_brep_stitching_plan.json`
**Boundary:** Mesh-derived/lossy; plane/cylinder dominant; freeform/NURBS
future work; partial shells do not produce STEP.
[Details ->](aieng/docs/showcase_gallery.md)

### 3. Assembly Model -> Selected-Part Optimization

Builds a proxy assembly analysis model and optimizes one selected design part.

<img src="docs/assets/showcase/assembly_optimization_flow.svg" width="880" alt="Assembly Model to Resolve Interfaces to Simplified Analysis to Topopt Problem to Optimized Part"/>

```bash
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q
```

**Key artifacts:** `analysis/assembly_topology_optimization.json`,
`parts/bracket/geometry/optimized_shape_ir.json`
**Boundary:** Proxy connections only; no real contact/friction/bolt preload;
one design part only; not production-certified.
[Details ->](aieng/docs/showcase_gallery.md)

### 4. Design Study: Adjustable Dimensions -> Compare -> Adopt

Validates, executes, compares, and optionally adopts parameterized design
candidates without overwriting the baseline.

<img src="docs/assets/showcase/design_study_flow.svg" width="960" alt="Setup Problem to Propose Candidate to Safety Checks to Build Design Copy to Compare Options to Adopt Best"/>

```bash
pytest aieng-ui/backend/tests/test_design_study_demo.py -q
```

**Key artifacts:** `analysis/design_study_candidate_ranking.json`,
`analysis/design_study_acceptance.json`,
`accepted/candidate_good/geometry/shape_ir.json`
**Boundary:** Static metrics in demo; no autonomous optimization; no baseline
overwrite; ranking is advisory.
[Details ->](aieng/docs/showcase_gallery.md)

## Current limitations

- Not production-certified CAD/CAE. Outputs are review material that still
  require human engineering judgment.
- Assembly contact and bolt preload are proxy-only. Real nonlinear contact is
  future work.
- 3D SIMP is experimental/reference, not production-certified.
- Mesh-to-CAD works best for plane/cylinder-dominant geometry; broader freeform
  and NURBS fitting is future work.
- Design study is agent-guided explicit execution, not autonomous global
  optimization.

## Repository layout

### Active

| Path | Status | What it is |
|------|--------|------------|
| **`aieng-ui/`** | **Active** | FastAPI backend, React workbench, and MCP server |
| `aieng/` | Core library | `.aieng` semantic package format engine, schemas, validation, CLI, Shape IR, and evidence model |
| `aieng-vscode-extension/` | Active | VS Code visualization front-end for `.aieng` packages and live project previews |
| `aieng-agent-skills/` | Active | `SKILL.md` contracts teaching agents how to use the ecosystem |

### Non-active but retained

| Path | Status | What it is |
|------|--------|------------|
| `legacy/aieng-freecad-mcp/` | **Legacy** | Old FreeCAD execution adapter - not used by the active path |
| `archive/CAD-Agent-main/` | Archived | Historical and experimental auxiliary CAD-agent material |

The active CAD engine is `aieng-ui/backend` using **build123d**. `aieng/` is
the core semantic library and the `.aieng` package home.

## Documentation

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](AGENTS.md) | Canonical agent guide - tools, workflows, and conventions |
| [aieng-ui/backend/MCP_SETUP.md](aieng-ui/backend/MCP_SETUP.md) | Per-agent MCP wiring for Claude Code, Copilot, Cursor, and Codex |
| [aieng-vscode-extension/README.md](aieng-vscode-extension/README.md) | VS Code extension usage and development notes |
| [aieng/docs/showcase_gallery.md](aieng/docs/showcase_gallery.md) | Showcase gallery - demo talking points, visual guidance, and honesty boundaries |
| [aieng/docs/demo_catalog.md](aieng/docs/demo_catalog.md) | Backend demo catalog - run commands, expected artifacts, and maturity levels |
| [aieng/docs/backend_capability_matrix.md](aieng/docs/backend_capability_matrix.md) | Capability status snapshot |
| [aieng/docs/roadmap.md](aieng/docs/roadmap.md) | Phase-by-phase development roadmap |
| [CLAUDE.md](CLAUDE.md) | Claude Code entry pointer |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | GitHub Copilot entry pointer |

## Contributing

Contributions are welcome across the package format, backend workflows, MCP
tooling, and VS Code front-end. Work that improves reproducibility, visual
inspection, engineering honesty boundaries, or agent usability is especially in
scope.

## Notes

- Private repo. No secrets are committed; runtime data (`data/projects/`),
  virtual environments, `node_modules`, and embedded conda envs are gitignored.
- If your CAD env is not named `aieng311`, edit the `-n aieng311` argument in
  the MCP configs or point `command` directly at your interpreter. See
  [aieng-ui/backend/MCP_SETUP.md](aieng-ui/backend/MCP_SETUP.md).
- A running backend at `http://127.0.0.1:8000` enables live UI updates when an
  agent drives a build; if it is down, the MCP server falls back to in-process
  execution.
