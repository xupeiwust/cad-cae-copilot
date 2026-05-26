# Roadmap

## Milestones

### Milestone 1 — FreeCAD MCP can safely inspect and regenerate a parametric bracket

Status: **Complete** (dry-run gate)

All 11 acceptance criteria from AGENTS.md pass under `scripts/run_milestone1_acceptance.py --dry-run`. Real FreeCAD execution is gated on environment availability.

## Version Roadmap

| Version | Theme | Status |
|---|---|---|
| v0.3.0 | End-to-end `.aieng` patch execution demo | **Implemented scaffold** |
| v0.4.0 | Real FreeCAD fixture + actual FCStd / STEP export integration tests | **Implemented scaffold** |
| v0.5.0 | Optional CAD/CAE evidence orchestration helper | **Implemented scaffold** |
| v0.6.0 | Post-processing evidence: result fields / VTK / CSV / visual index linkage | **Implemented scaffold** |
| v0.7.0 | Claim update tool: explicit evidence-backed claim transitions only | **Implemented scaffold** |
| v0.8.0 | Geometry reference and CAE target mapping scaffold | **Implemented scaffold** |
| v0.9.0 | Real solver integration hardening: runtime detection, skip-based tests, demo | **Implemented scaffold** |
| v1.0.0-rc1 | Release candidate: composable architecture, planner, CI, docs hardening | **Implemented** |
| v1.0.0 | Public composable `.aieng`-enhanced CAD/CAE execution demo | **Planned** (pending RC feedback) |
| v1.1 | Tool transparency and inspection hardening | **Implemented** |
| v1.2 | Visual and field evidence planning | **Planned** |
| v1.3 | Adapter research (post-processing and regeneration) | **Planned** |

## Implemented Highlights (v0.3.0 to v0.9.0)

Status: **Implemented scaffold**

Completed themes:

- patch bridge with guarded parametric edits and dry-run
- optional artifact export and evidence/trace writeback
- real FreeCAD fixture generation and skip/fail integration tests
- optional explicit CAD->CAE orchestration helper (not automatic)
- post-processing evidence path (CSV + VTK unsupported path handling)
- explicit deterministic claim update flow (`aieng_update_claim` only)
- reference mapping with `needs_review` marking after geometry changes
- runtime capability detection for FreeCAD/FEM/meshers/CalculiX

Boundary preserved across implemented milestones:

- composable execution interface, not autonomous planning
- `.aieng` optional
- CAD and CAE independent
- evidence not equal to claim
- no automatic claim advancement

## v1.1 — Tool Transparency and Inspection

Status: **Implemented**

Completed goals:

- Added machine-readable tool side-effect catalog (`tool_registry.py`) with `aieng_tool_registry_query` MCP tool
- Strengthened read-only CAD feature and parameter inspection summaries (existing tools hardened)
- Expanded runtime capability reporting with graceful optional dependency handling (existing tools hardened)
- Normalized stricter error taxonomy (`failure_mode.py`) with `FailureMode`, `FailureDetail`, and `classify_exception`
- Added dry-run preview metadata contract (`operation_preview.py`) with `preview_operation` MCP tool
- Audit report now includes failure-mode taxonomy coverage statistics

Boundary and policy constraints:

- Remains a composable execution interface, not an autonomous workflow planner
- `.aieng` remains optional
- CAD and CAE remain independent first-class capabilities
- Claim updates remain explicit and evidence-backed

## aieng-ui Phase 2.5 — FreeCAD Export and Artifact Loop

Status: **Implemented**

Completed goals (implemented in `aieng-ui` integration, not a standalone release):

- `step_exporter.py`: `FREECAD_EXPORT_SCRIPT` embedded script + `run_step_export()` launcher; produces `artifacts` list with `{path, kind, role}` entries
- `freecad_bridge.export_step()`: thin wrapper in `aieng-ui/backend/app/freecad_bridge.py`
- `freecad.export_step` runtime tool: registered in `main.py`; resolves input from `project_id → metadata.json → source_step`; auto-generates `_export.step` output path; writes per-project audit log
- Artifact hoisting: `_execute_steps()` extracts `artifacts` from tool output and populates `ToolResult.artifacts`
- Frontend: `formatArtifactChanges()` helper + `变更文件:` display block in chat history

Boundary preserved:
- FreeCAD-specific logic stays in `aieng_freecad_mcp`; bridge stays thin
- Approval gates unchanged; `freecad.run_macro` still requires explicit approval
- No full MCP, no arbitrary macro editing, no overclaimed CAE solver integration

---

## v1.2 — Visual and Field Evidence

Status: **Planned**

Planned goals:

- Add optional CAD visual preview artifacts for review and traceability
- Plan field-oriented post-processing artifact pathways for evidence portability
- Improve evidence packaging for visual and field outputs while preserving current claim policy discipline

Boundary and policy constraints:

- Visual artifacts are evidence artifacts only
- Visual success is not engineering validation
- Solver execution success is not claim pass
- No automatic claim advancement

## Phase 7 — Computed Metrics Exporter

Status: **Implemented**

Delivered:
- `freecad_mcp.computed_metrics_exporter` module with `export_computed_metrics()`
- CLI: `python -m freecad_mcp.computed_metrics_exporter --input <path> --output <path>`
- Supports flat JSON, CSV (`name,value,unit`), and Phase-6-schema JSON inputs
- Normalizes to canonical `results/computed_metrics.json` (schema `"0.1"`)
- Maps common flat keys (`max_von_mises_stress_mpa`, `max_displacement_mm`, `factor_of_safety`) to canonical metric keys
- Preserves metric objects with `location`, `field`, `basis` when present
- Warnings for unrecognized keys and empty inputs
- Structured error taxonomy (`ComputedMetricsExportError`)
- Machine-readable JSON stdout; stderr for errors
- No FreeCAD dependency; no solver execution; no VTU/FRD/ODB parsing

## v1.3 — Adapter Research

Status: **Planned**

Planned goals:

- Run VTK or ParaView or PyVista post-processing adapter research spike
- Run CadQuery regeneration adapter research spike
- Define adapter boundary contracts that preserve core execution and auditability discipline

Boundary and policy constraints:

- Research-first scope; no implied implementation in this milestone
- No arbitrary Python or shell execution tools
- No hidden mutation and no autonomous CAD to CAE to claim orchestration
- `.aieng` source-of-truth semantics remain host-agnostic and optional for standalone usage

## v1.0.0 RC Snapshot

Status: **Implemented** (RC)

Current release-candidate scope:

- public composable demo with five independent paths
- audit reporting
- read-only planning-neutral capability inspection
- CI/test hardening with optional-runtime behavior
- explicit claim discipline and claim-map immutability outside `aieng_update_claim`

## Legacy Milestones

Legacy pre-version milestones are retained in commit history and release notes; this roadmap now tracks versioned scope.
