# CAD Adapter Strategy

The system is designed to be CAD-agnostic from the start. FreeCAD is the
first and currently only connected CAD backend, chosen because it is
open-source and Python-friendly. The architecture ensures no other component
depends on FreeCAD-specific behaviour.

---

## Why CAD-Agnostic

1. **FreeCAD is not universally available.** Many engineering organisations
   run SolidWorks, CATIA, NX, or Fusion 360. A platform locked to FreeCAD
   cannot serve them.

2. **CAD tools evolve and break.** Isolating CAD I/O behind a stable interface
   means the rest of the system (package format, UI, orchestration runtime,
   AI agents) survives CAD version changes.

3. **The `.aieng` package is the stable artifact.** Once a STEP file has been
   imported and enriched, downstream consumers (AI agents, validation,
   visualisation) operate on the package, not on live CAD state.

---

## Provider Interface (conceptual CadAdapter)

The `aieng-ui` backend defines a provider protocol in
`backend/app/providers/protocols.py`. Any CAD backend must satisfy this interface.

```python
class CadProvider(Protocol):
    provider: str                              # e.g. "freecad"

    def import_step_to_package(
        self, *, step_path: Path, out_path: Path
    ) -> dict[str, Any]:
        """Import a STEP file; return package metadata."""

    def enrich_package(
        self, *, package_path: Path, topology_backend: str
    ) -> dict[str, Any]:
        """Run topology, feature, and semantic enrichment."""

    def validate_package(
        self, *, package_path: Path
    ) -> dict[str, Any]:
        """Validate the package; return ok/counts/messages."""

    def export_step_preview_to_stl(
        self, *, step_path: Path, stl_path: Path
    ) -> dict[str, Any]:
        """Produce an STL mesh for web preview."""

    def package_summary_snapshot(
        self, *, package_path: Path
    ) -> dict[str, Any]:
        """Return a structured snapshot of the package contents."""

    def probe_capabilities(
        self, *, whitelisted_tools: list[str]
    ) -> dict[str, Any]:
        """Report runtime readiness and available capabilities."""

    def check_mcp_operation(
        self, *, package_path: str | None, payload: dict, whitelisted_tools: list[str]
    ) -> dict[str, Any]: ...

    def parse_patch_proposal(self, *, patch_json: dict) -> dict[str, Any]: ...

    def prepare_patch_preflight(
        self, *, package_path: str | None, payload: dict
    ) -> dict[str, Any]: ...
```

---

## Current Provider: FreeCAD

```
aieng-ui/backend/app/providers/
    protocols.py         ← abstract interface
    registry.py          ← "freecad" → FreeCADAdapter
    freecad/
        adapter.py       ← FreeCADAdapter: delegates to bridge_runner and preview
        bridge_runner.py ← spawns FreeCADCmd subprocess; calls aieng CLI
        preview.py       ← STL export via FreeCAD, GLB conversion via trimesh
```

**FreeCAD adapter status (aieng-ui):**

| Capability | Status |
|------------|--------|
| `import_step_to_package` | ✅ Calls aieng CLI via bridge_runner |
| `enrich_package` | ✅ Calls aieng CLI enrichment commands |
| `validate_package` | ✅ Calls aieng CLI validate |
| `export_step_preview_to_stl` | ✅ FreeCADCmd subprocess |
| `package_summary_snapshot` | ✅ Reads ZIP package members |
| `probe_capabilities` | ✅ Checks paths, FreeCADCmd existence |
| `check_mcp_operation` | ✅ Guard policy checks |
| Topology backends | ✅ `mock` always; `occ` experimental |

**FreeCAD execution status (aieng_freecad_mcp):**

| Capability | Status |
|------------|--------|
| CAD patch parse/execute | ✅ Implemented |
| Evidence writeback | ✅ Implemented |
| Tool trace recording | ✅ Implemented |
| CAD→CAE workflow helper | ✅ Implemented |
| Claim update enforcement | ✅ Implemented |
| Real FreeCAD subprocess | Optional (mock/surrogate paths work without it) |
| Mesh generation (Gmsh/Netgen) | Planned |
| CalculiX execution | Planned |

**FreeCAD bridge in aieng-ui runtime (freecad.inspect_geometry, freecad.run_macro):**

Both are registered as skeletons. `freecad.inspect_geometry` returns
`{"status": "not_implemented"}`. `freecad.run_macro` is approval-gated and
never reaches execution. Four connection paths are documented in
`aieng-ui/docs/runtime_architecture.md`:

| Path | Description |
|------|-------------|
| A | FreeCAD Python API via FreeCAD-hosted subprocess |
| B | Headless `FreeCADCmd --run script.py` |
| C | Local socket/HTTP bridge (connect to running `aieng_freecad_mcp`) |
| D | Workbench extension with named pipe |

Path C (connect to `aieng_freecad_mcp` running locally) is the recommended
first step since that adapter already exists.

---

## Adding a Future CAD Backend

To add SolidWorks, Fusion 360, Onshape, NX, or a generic STEP-only adapter:

1. Create `backend/app/providers/solidworks/` (or equivalent).
2. Implement the `CadProvider` protocol in `adapter.py`.
3. Register in `registry.py`: `"solidworks": SolidWorksAdapter`.
4. The rest of the service layer, runtime, and frontend require no changes.
5. Expose any new capabilities via `probe_capabilities()`.

---

## Capability-Aware UI Behaviour

The frontend reads capabilities from the project summary and adjusts its
behaviour accordingly. Current examples:

| Capability signal | UI behaviour |
|------------------|--------------|
| `summary.cae.present == true` | Show CAE panel |
| `summary.cae.results_available == true` | Show "results available" badge |
| `summary.cae.available_fields` non-empty | Show scalar field selector dropdown |
| `summary.cae.solver_fields` present | Show real descriptor URL, fetch field metadata |
| `summary.viewer.asset_exists == true` | Load Three.js viewer with GLB/STL |
| FreeCAD tools `not_implemented` | Do not surface FreeCAD actions as primary CTA |
| `runtime.probe.ready == false` | Show "CAD runtime needs configuration" banner |

The pattern: **UI degrades cleanly when backend capabilities are absent**. It
does not fabricate capabilities or show non-functional controls.

---

## What Must Stay CAD-Agnostic

The following must never contain FreeCAD-specific code:

- `.aieng` package format (`aieng/`)
- Package validation and claim logic (`aieng/`)
- Runtime orchestration models (`aieng-ui/backend/app/runtime.py`)
- Frontend React components (`aieng-ui/frontend/`)
- The `chat_orchestrator` and plan builder in `main.py`

FreeCAD-specific code belongs only in:
- `aieng-ui/backend/app/providers/freecad/`
- `aieng_freecad_mcp/`
