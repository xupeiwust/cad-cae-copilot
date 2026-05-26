# `.aieng` Viewer MVP Proposal

Status: draft for Phase 18B (optional).

Inspired by text-to-cad's CAD Explorer, but **scoped down**: the `.aieng` viewer visualises *the structured package*, not the geometry inside it. Geometry visualisation remains a job for external CAD viewers (FreeCAD, CAD Assistant, KiCad, etc.).

## 1. Identity rules (non-negotiable)

1. **Read-only.** The viewer does not write any file in the package. Not even derived indexes — those are produced by CLI verbs.
2. **Not authoritative.** Every page displays a footer: *"Derived view of `<package>`. Authoritative state lives in the JSON/YAML resources."* Snapshots of viewer screens are explicitly **not** validation evidence.
3. **Semantic-first, not geometric.** It draws the *feature graph*, *adjacency graph*, *interface graph*, *claim status*, *evidence ledger*, *completeness report*. It does not render STEP geometry, mesh, or solver results.
4. **Optional install.** Behind an extra (`pip install aieng[viewer]`). No Node/Vite/web framework in default install.
5. **No telemetry, no network.** Local-only. The viewer runs on `127.0.0.1` and shuts down with the CLI process.
6. **Bounded surface.** A small set of pages, no plugin system, no upload, no editor, no diff-merge UI.

## 2. Implementation shape

Two viable choices; pick one in Phase 18B.

### Option A — Static HTML/JS bundle, served via `python -m http.server`-style helper
- Pure-Python stdlib HTTP server.
- HTML/JS bundle is part of the package and pre-built.
- Reads JSON/YAML resources via fetch from the same origin.
- No Node toolchain. **Recommended.**

### Option B — Streamlit or Flask app
- More dynamic but adds heavy runtime dependency.
- Risk of feature creep. Not recommended for MVP.

## 3. CLI surface

```bash
aieng view <package.aieng>                    # opens default browser at http://127.0.0.1:PORT
aieng view <package.aieng> --port 8765
aieng view <package.aieng> --no-browser       # prints URL only
aieng view <package.aieng> --page claims      # opens specific page
```

If the `[viewer]` extra is not installed, `aieng view` prints an install hint and exits 0. Same pattern as `aieng geometry-backends` reporting OCC availability.

## 4. Pages (MVP)

Each page reads exactly the resources listed and shows the canonical `@aieng[...]` reference for every record.

### 4.1 Overview
- Package name, schema version, source mode (cad/cae/definition), creation timestamp.
- Counts: features, topology faces, interfaces, claims (by status), evidence entries (by producer kind), tool trace entries.
- Completeness snapshot (`available` / `partial` / `missing` / `unknown` / `unsupported` per section).
- Status banner: red if `aieng validate` has reported errors, yellow if completeness has any `missing` items, green otherwise.
- Reads: `manifest.json`, `validation/status.yaml`, `validation/completeness_report.json`, `results/claim_map.json`, `results/evidence_index.json`, `provenance/tool_trace.json`.

### 4.2 Feature graph
- Table of features with `id`, `kind`, `parameter_source`, `editability`, `writeback_strategy`, `confidence`.
- Filter: protected only, executable-by-regeneration only, by kind.
- Click → record detail showing the full JSON plus related refs.
- Reads: `graph/feature_graph.json`, `ai/protected_regions.json`.

### 4.3 Topology and adjacency
- Faces, edges, vertices list with `surface_type`, `extraction_mode`, `runtime_provider`.
- Adjacency graph (AAG) rendered as a node-link diagram using the JSON only — no STEP parsing. Node = face ID, edge = adjacency record. Click a node → its feature membership.
- Banner: "Mock topology" / "OCP-extracted topology" based on `topology_map.extraction_mode`.
- Reads: `geometry/topology_map.json`, `graph/aag.json`.

### 4.4 Interfaces
- Interface table with `iface_id`, `feature_id`, `cae_refs`, `interface_role`.
- Cross-link to mapped CAE entities (`FIXED_HOLES`, `LOAD_FACE`, ...).
- Reads: `objects/interface_graph.json`, `objects/object_registry.json`, `simulation/cae_mapping.json`.

### 4.5 Simulation setup
- Materials, boundary conditions, loads from parsed deck.
- Mapping status per CAE entity (`mapping_method`, `confidence`).
- Imported solver/mesh evidence summary (counts only — numeric values shown inline; no rendering).
- Reads: `simulation/setup.yaml`, `simulation/cae_imports/*`, `simulation/cae_mapping.json`.

### 4.6 Claims
- Claim table: `id`, `status` (pass / fail / unsupported), `decision_criteria`, `pass_requires`, `unsupported_if`, `supported_by` (list of evidence refs), `auto_advance` (always false; shown as a guard, not a control).
- Filter: unsupported only, fail only.
- Click claim → full record + linked evidence with full `@aieng[...]` refs.
- Reads: `results/claim_map.json`, `results/evidence_index.json`.

### 4.7 Evidence ledger
- Evidence table: `id`, `producer_kind`, `producer_tool`, `producer_version`, `artifact_paths`, `numeric_values`, `claims_supported`.
- Banner if any artifact path is dangling.
- Reads: `results/evidence_index.json`, plus existence-check of `artifact_paths`.

### 4.8 Tool trace
- Chronological trace: tool, version, exit status, timestamps, `claims_advanced`.
- Warning row if any entry has exit_status != 0.
- Reads: `provenance/tool_trace.json`.

### 4.9 Completeness / missingness
- Per-section grid with status chips (`available`, `partial`, `missing`, `unknown`, `unsupported`).
- Sortable, filterable.
- Reads: `validation/completeness_report.json`.

### 4.10 Patches
- Patch list with `id`, `intent`, `operations`, `applied`, `no_geometry_modified` flag, `execution_record`.
- Reads: `ai/patches/*.json`.

### 4.11 Task spec & external-tool requirements
- Renders `task/task_spec.yaml`, `task/external_tool_requirements.json` as labelled cards. Highlights forbidden claims and execution boundary const guards.
- Reads: `task/*`.

## 5. Pages explicitly **not** in MVP

- No 3D STEP viewer.
- No mesh viewer.
- No solver-result colour map.
- No "click to edit" anywhere.
- No "approve claim" button (auto-advance is structurally forbidden; the viewer must not invite it).
- No "apply patch" button (CLI verb only).
- No diff between packages (separate `aieng diff` verb, future).
- No upload, sharing, or export-to-cloud.

## 6. Visual snapshot policy

If a future feature lets users export a viewer page as PNG/PDF, the resulting file:

- is written under `visual/snapshots/<page>_<timestamp>.png`,
- carries a sidecar `<page>_<timestamp>.json` with `producer_kind: "aieng_viewer"`, `not_validation_evidence: true`, source page name, and snapshot timestamp,
- is **forbidden** from appearing in `results/evidence_index.json` by schema const guard,
- is excluded from `aieng record-evidence` by the writeback verb (which rejects `producer_kind=aieng_viewer`).

This explicitly closes the "screenshot looks fine → claim passes" failure mode.

## 7. Boundary risks and mitigations

| Risk | Mitigation |
|---|---|
| Viewer becomes source of truth | Footer banner on every page; no write paths; documented invariant in `core_position.md`. |
| Heavy deps in default install | Behind `[viewer]` extra; no Node toolchain. |
| 3D rendering of STEP creeps in | Schema const guard: viewer is forbidden from rendering geometry. Code review check: no `cadquery`/`OCP`/`build123d`/`trimesh` imports inside viewer package. |
| Snapshots mistaken for evidence | Schema guard (see §6) + writeback rejects `producer_kind=aieng_viewer`. |
| Mutating UI (approve, edit) added later | Viewer codebase is read-only by construction: no Python writer modules imported. Lint rule. |
| Performance on large packages | Page-by-page lazy load; no whole-package parse on launch. |

## 8. Acceptance criteria for MVP

- `pip install aieng[viewer]` succeeds with no Node dependency.
- `aieng view <package>` opens the overview page in default browser.
- Without `[viewer]` extra, `aieng view` prints install hint and exits 0.
- All 11 MVP pages render against the existing reference bracket package, the real-bracket package, and a definition-sourced package.
- No file in the package is modified by viewer execution (tested by hashing before/after).
- Page footer "Derived view ..." is present on all pages.
- `evidence_index.json` cannot accept a viewer-snapshot entry (validator test).
- No 3D geometry rendering, no editing controls.

## 9. Cost estimate

Static HTML/JS option (recommended): ~1–2 weeks engineering for MVP, mostly in laying out the 11 pages and wiring resource loaders. Schema changes: zero. Validator additions: one guard for `producer_kind=aieng_viewer`.

If cost exceeds 2 weeks, MVP scope should shrink to overview + claims + evidence + completeness (4 pages); the rest can land in 18B.1.
