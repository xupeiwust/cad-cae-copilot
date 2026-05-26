# MVP Checkpoint: Phase 0 through Phase 15C

This document summarizes the state of the `.aieng` format project at the Phase 15C milestone.
For package and resource compatibility rules, see [Schema versioning policy](schema_versioning.md).

---

## Completed phases

| Phase | Description |
|-------|-------------|
| Phase 0 | Package format, JSON schemas, validator, `aieng init`, `aieng validate` |
| Phase 1 | STEP import as geometry resource copy, `aieng import-step` |
| Phase 2 | Mock topology extraction interface, `aieng extract-topology` |
| Phase 3 | Rule-based feature candidate recognition, `aieng recognize-features` |
| Phase 4 | User engineering context application, `aieng apply-context` |
| Phase 5A | Deterministic AI-readable summary generation, `aieng summarize` |
| Phase 5B | Structured rule-based patch proposal generation, `aieng propose-patch` |
| Phase 5C | AI understanding benchmark scaffold (`benchmarks/`) |
| Phase 5D | Reference demo walkthrough, scripted demo (`scripts/run_reference_demo.py`), and integration tests |
| Phase 6A | Solver deck scaffold export, `aieng export-calculix`, `simulation/solver_deck.inp` |
| Phase 6B | Validation status file, `aieng update-validation-status`, `validation/status.yaml` |
| Phase 7A | Geometry backend interface: `GeometryBackend` Protocol, `MockGeometryBackend`, `OCCGeometryBackend` placeholder, `--backend` CLI flag, topology metadata fields |
| Phase 7A+ | Geometry backend contract documentation (`docs/geometry_backend_contract.md`) |
| Phase 7B.1 | Optional OCC runtime detection: `detect_occ_runtime()`, `aieng geometry-backends`, `[geometry]` extra declared |
| Phase 7B.2 | Experimental OCP/CadQuery-based real STEP topology extraction (spike); `validation/status.yaml` distinguishes mock from experimental OCP extraction |
| Phase 7C | Optional OCP topology demo path: `scripts/run_ocp_topology_demo.py`, `docs/ocp_topology_demo.md` |
| Phase 8A | Visual index scaffold: `aieng build-visual-index`, `visual/annotation_layers.json`, `schemas/visual_annotation_layers.schema.json`, validator checks, summary integration, `visual_status` in `validation/status.yaml` |
| Phase 8B | Visual resource manifest scaffold: `aieng build-visual-manifest`, `visual/model_manifest.json`, `schemas/visual_model_manifest.schema.json`, validator checks, summary + status integration, explicit no-rendering claim policy |
| Phase 9A | Object registry scaffold: `aieng build-object-registry`, `objects/object_registry.json`, `schemas/object_registry.schema.json`, validator checks, summary + status integration, explicit index-not-source-of-truth policy |
| Phase 9B | Interface graph scaffold: `aieng build-interface-graph`, `objects/interface_graph.json`, `schemas/interface_graph.schema.json`, validator checks, summary + status integration, explicit index-not-source-of-truth policy |
| Phase 10A | CAE deck import scaffold: `aieng import-cae-deck`, `simulation/cae_imports/*`, `simulation/cae_mapping.json`, schema + validator checks, summary + status integration, explicit no-solver/no-results policy |
| Phase 10B | Explicit CAE mapping: `aieng apply-cae-mapping`, user-provided mapping YAML to feature/interface IDs via `simulation/cae_mapping.json`, validator checks for explicit references, no auto-inference policy |
| Phase 11A | Real STEP topology hardening scaffold: optional face-edge ownership metadata and explicit adjacency-evidence metadata where backend evidence exists |
| Phase 11B | Attributed adjacency graph: `aieng build-aag`, `graph/aag.json`, schema + validator checks, optional feature-recognition integration |
| Phase 11C | Optional real STEP demo + benchmark scaffold: `scripts/generate_real_bracket_step.py`, `scripts/run_real_step_demo.py`, `scripts/prepare_real_benchmark_pack.py`, `benchmark_runs/real_bracket_001/` |
| Phase 12A | Documentation positioning refinement: `.aieng` clarified as semantic task-understanding layer for AGI-assisted CAX process chains; docs-only update, no runtime changes |
| Phase 13A | Parameterized feature/edit-handle scaffold: guarded `parameter_source`, `editability`, and `writeback_strategy` fields in `graph/feature_graph.json` |
| Phase 13B | Semantic patch execution scaffold: `aieng apply-patch` updates supported feature parameters and records execution metadata |
| Phase 13C | Updated deck scaffold export: `aieng export-updated-deck`, `simulation/updated_deck.inp`, status integration, no solver/mesh execution |
| Phase 13B (MCP) | MCP server: `aieng serve <package.aieng>`, 9 agent-callable tools, claim_policy enforcement, stdio + SSE transports |
| Phase 14A-min | Task specification schema: `aieng write-task-spec`, `task/task_spec.yaml`, `schemas/task_spec.schema.json`, validator checks, MCP `get_task_spec` |
| Phase 14B | External tool handoff contract: `aieng write-external-tool-requirements`, `task/external_tool_requirements.json`, `schemas/external_tool_requirements.schema.json`, validator checks, MCP `get_external_tool_requirements` |
| Phase 14C | Evidence ledger + claim-evidence map: `aieng write-evidence-scaffold`, `results/evidence_index.json`, schemas, validator checks, MCP `get_evidence_index`; claim proposals require human review |
| Phase 14D | Agent handoff benchmark scaffold: `benchmarks/handoff/` with README, questions (10 groups), scoring rubric (8 categories, 0/1/2, max 16), expected observations, input index, result template, results schema |
| Phase 15A | Evidence writeback commands: `aieng record-evidence`, claim proposals reviewed via human review, `record_evidence_package()` |
| Phase 15B | Provenance tool trace: `aieng record-trace`, `provenance/tool_trace.json`, `schemas/tool_trace.schema.json`, MCP `get_tool_trace` |
| Phase 15C | Cross-resource consistency validator: `_validate_cross_resource_consistency()` in `validate.py`; six inter-resource checks across all six Phase 14/15 ledgers |
| Phase 15D | Enhanced AI summary visibility: evidence counts by type/producer, claim status breakdown, tool trace summary |
| Phase 16A | Completeness/missingness report: `aieng write-completeness-report`, `validation/completeness_report.json`, best-effort explicit missingness |
| Phase 16B | CAD/CAE emitter/writeback contract: `docs/cad_cae_emitter_contract.md`, capability levels L0–L5 |
| Phase 16C | AGI handoff worked example: `docs/agi_handoff_walkthrough.md` |
| Phase 16D | Generated model mode completeness integration: `aieng define` writes `completeness_report.json` automatically |
| Phase 16E | Conversion iron rule adoption: no-guess conversion policy in `docs/cad_cae_emitter_contract.md` and `docs/interop_standards_matrix.md` |
| G3 (Rigorous Interop) | Solver numeric evidence extraction: `aieng import-solver-evidence`; `max_von_mises`, `max_displacement`, `max_reaction_force`; explicit `not_found` list |
| G4 (Rigorous Interop) | Mesh evidence extraction: `aieng import-mesh-evidence`; Gmsh v2/v4 node/element counts; explicit `quality_metrics_not_found` |
| G7 (Rigorous Interop) | CAD writeback via CadQuery parametric regeneration: `aieng apply-patch`; `base_plate_candidate`; `geometry/modified_*.step` |
| G8 (Rigorous Interop) | Roundtrip invariance: source STEP immutable; no auto-advance of solver/mesh claims; `test_roundtrip_invariance.py` |
| G9 (Rigorous Interop) | Claim decision thresholds per claim ID: `decision_criteria` with `auto_advance: false`; schema + validator enforcement |
| G10–G12 (Rigorous Interop) | Tool trace metadata contract, adapter capability declaration, CI conformance suite — all PASS |
| Phase 17A | Real STEP stabilization: `extract-topology --backend auto`, OCC preference with mock fallback, `real_geometry_extraction` completeness flag |
| Phase 17B | Mesh handoff completeness: `aieng write-mesh-handoff`, `simulation/mesh_handoff_contract.json`, validator + round-trip tests |

**Rigorous Interop milestone ACHIEVED (May 12, 2026):** All 12 gates G1–G12 in `docs/rigorous_interop_acceptance_checklist.md` are PASS.

---

## Phase 17 Status

| Phase | Description |
|-------|-------------|
| Phase 17A | Complete — issue #35 |
| Phase 17B | Complete — issue #36 |

---

## Current supported CLI commands

```bash
aieng init --model-id <id> --out <package.aieng>
aieng import-step <step_file> --out <package.aieng>
aieng extract-topology <package.aieng>
aieng build-aag <package.aieng>
aieng recognize-features <package.aieng>
aieng apply-context <package.aieng> --context <context.yaml>
aieng summarize <package.aieng>
aieng propose-patch <package.aieng> --intent "<intent>"
aieng apply-patch <package.aieng> --patch <patch_id>
aieng export-updated-deck <package.aieng> --out <updated_deck.inp>
aieng export-calculix <package.aieng> --out <solver_deck.inp>
aieng update-validation-status <package.aieng>
aieng build-visual-index <package.aieng>
aieng build-visual-manifest <package.aieng>
aieng build-object-registry <package.aieng>
aieng build-interface-graph <package.aieng>
aieng import-cae-deck <package.aieng> --deck <solver_deck.inp> --format calculix
aieng apply-cae-mapping <package.aieng> --mapping <mapping.yaml>
aieng write-task-spec <package.aieng> --intent "<intent>"
aieng write-external-tool-requirements <package.aieng> [--handoff-id <id>]
aieng write-evidence-scaffold <package.aieng>
aieng record-evidence <package.aieng> --evidence-type <type> --producer-kind <kind> --producer-tool <tool> --artifact-kind <kind> --artifact-path <path> --claim-support <id,...> [options]
# Claim status updates require human review (update-claim CLI removed)
aieng record-trace <package.aieng> --tool-id <id> --tool-role <role> --step-name <name> --exit-status <status> [options]
aieng serve <package.aieng> [--port N]
aieng validate <package.aieng>
```

See [docs/command_reference.md](command_reference.md) for full details on each command.

Development setup note:

```bash
conda run -n aieng311 python -m pip install -e .
```

---

## Generated `.aieng` resources

A complete Phase 5D package contains:

| Path | Generated by |
|------|-------------|
| `manifest.json` | `init` or `import-step` |
| `geometry/source.step` | `import-step` |
| `geometry/normalized.step` | `import-step` |
| `geometry/topology_map.json` | `extract-topology` |
| `graph/aag.json` | `build-aag` |
| `graph/feature_graph.json` | `recognize-features` |
| `graph/constraints.json` | `apply-context` |
| `simulation/setup.yaml` | `apply-context` |
| `ai/protected_regions.json` | `apply-context` |
| `README_FOR_AI.md` | `summarize` |
| `ai/summary.md` | `summarize` |
| `ai/patches/patch_NNNN.json` | `propose-patch` |
| `simulation/updated_deck.inp` | `export-updated-deck` |
| `simulation/solver_deck.inp` | `export-calculix` |
| `validation/status.yaml` | `update-validation-status` |
| `visual/annotation_layers.json` | `build-visual-index` |
| `visual/model_manifest.json` | `build-visual-manifest` |
| `objects/object_registry.json` | `build-object-registry` |
| `objects/interface_graph.json` | `build-interface-graph` |
| `simulation/cae_imports/source_solver_deck.inp` | `import-cae-deck` |
| `simulation/cae_imports/parsed_materials.json` | `import-cae-deck` |
| `simulation/cae_imports/parsed_boundary_conditions.json` | `import-cae-deck` |
| `simulation/cae_imports/parsed_loads.json` | `import-cae-deck` |
| `simulation/cae_mapping.json` | `import-cae-deck` |
| `task/task_spec.yaml` | `write-task-spec` |
| `task/external_tool_requirements.json` | `write-external-tool-requirements` |
| `results/evidence_index.json` | `write-evidence-scaffold`, `record-evidence` |
| `results/claim_map.json` | Claim proposals are review artifacts requiring human review |
| `provenance/tool_trace.json` | `record-trace` |

---

## What is real structured data

The following are real, schema-validated, ID-stable structured resources:

- `manifest.json` — package identity, units, provenance, and indexed resource paths
- `geometry/topology_map.json` — stable face/edge/body IDs referenced across the package
- `graph/feature_graph.json` — feature objects with stable IDs referencing topology IDs
- `graph/constraints.json` — structured constraints targeting feature IDs
- `simulation/setup.yaml` — static structural setup with materials, loads, and boundary conditions
- `ai/protected_regions.json` — structured protected feature IDs and allowed/forbidden operations
- `visual/annotation_layers.json` — structured visual annotation metadata scaffold (not rendered geometry)
- `visual/model_manifest.json` — structured visual resource claim manifest (Phase 8B scaffold; no rendering)
- `objects/object_registry.json` — generated cross-file object index (Phase 9A scaffold; not source-of-truth)
- `objects/interface_graph.json` — generated interface index (Phase 9B scaffold; not source-of-truth)
- `ai/patches/patch_NNNN.json` — structured patch proposals with operations, target IDs, and validation requirements
- `task/task_spec.yaml` — structured agent task contract with intent, mode, forbidden claims, and claim policy
- `task/external_tool_requirements.json` — structured external tool handoff contract with required capabilities, candidate tools, handoff policy, writeback requirements, and forbidden core actions
- `results/evidence_index.json` — structured evidence ledger recording what artifacts exist, who produced them, and what claims they support
- `results/claim_map.json` — claim proposals are review artifacts requiring human review; no longer automatically generated
- `provenance/tool_trace.json` — append-only audit log of external tool invocations: what ran, what it produced, what claims it advanced
- JSON schemas in `schemas/` — validate all structured resources
- Cross-resource ID validation in `aieng validate`, including six inter-resource consistency checks across all Phase 14/15 ledgers

---

## What is mock-based

- **Topology extraction** (`geometry/topology_map.json`) is produced by `MockGeometryBackend` (the default backend). It generates a deterministic fixed topology for tests and the reference demo; it does not parse STEP content or call any CAD kernel. The mock backend remains the default for all commands including the reference demo and benchmark scenario unless `--backend occ` is explicitly passed.

---

## What is user-provided

- **Engineering context** (`examples/bracket_user_context.yaml`) supplies all engineering assumptions: material, protected features, fixed supports, force loads, and target constraints. The pipeline does not infer these from geometry.

---

## What is rule-based

- **Feature recognition** (`graph/feature_graph.json`) applies deterministic heuristic rules to the mock topology map: largest planar face becomes the base plate candidate, cylindrical faces become hole candidates, cylindrical hole groups become hole pattern candidates, remaining topology is classified as unknown.
- **Summaries** (`ai/summary.md`, `README_FOR_AI.md`) are generated from structured JSON/YAML resources using deterministic templates.
- **Patch proposals** (`ai/patches/patch_NNNN.json`) are generated from structured resources and the user intent string using deterministic rule-based logic. No LLM is called.
- **Semantic patch execution** (`aieng apply-patch`) updates supported feature parameters in structured resources and records execution metadata. For mock/OCP-extracted features this remains semantic-only unless an explicit future regeneration-backed source exists.

---

## What is experimental (Phase 7B.2)

- **OCP-based STEP topology extraction** (`--backend occ`) is available when OCP/CadQuery is installed (`pip install cadquery`). It performs real STEP parsing using `STEPControl_Reader` and `TopExp_Explorer`, populating topology entities with bounding boxes, face areas, surface types, normals, and cylinder radii where available. This is an experimental spike. Geometry validity is not certified. Feature recognition remains separate and rule-based. IDs are deterministic by traversal order only. `validation/status.yaml` records `status: experimental_real_extraction` and `real_step_parsing: true` when the OCP backend was used.

## What is not implemented

The following are explicitly not implemented at this milestone:

- Real CAD feature recognition (no kernel geometry queries)
- Arbitrary STEP/B-rep direct editing
- Real CAD geometry modification from semantic edits unless a future explicit regeneration-backed path exists
- Mesh generation by `.aieng` (mesh generation remains an external CAE responsibility)
- Solver execution by `.aieng` (solving remains an external CAE responsibility)
- Solver result generation by `.aieng`; future packages may reference or import externally produced solver evidence
- Manufacturing checks
- LLM, RAG, MCP, plugin, or skill calls in any command
- Visual preview rendering or glTF export generation
- Consolidated validation-state evidence report (`validation/evidence_report.json`) — see C4 in `docs/issue_coverage_inventory.md` and `docs/future_package_structure.md` for naming rationale
- Allowed-operation catalogs

---

## Current test count

946 tests across 22+ test files, plus 1 integration test module (skipped when OCP is absent). All tests pass using only the standard library and lightweight dependencies (pyyaml, jsonschema).

Test files cover: package creation, manifest validation, STEP import, topology map, geometry backend interface, feature graph, context application, AI summary, patch proposal, reference demo integration, benchmark scaffold, solver deck export, validation status, geometry backend detection, OCP integration (guarded by `pytest.importorskip`), evidence ledger and writeback, agent handoff benchmark, tool trace provenance, and cross-resource consistency.

---

## Why this checkpoint demonstrates the project thesis

The project thesis is:

> Adapt CAD/CAE data to AI. The file should carry enough engineering semantics that a general AI can understand the model before calling any tools.

Refined positioning at Phase 12A:

> `.aieng` is primarily a CAD/CAE-side semantic export and evidence package for AI-readable engineering state. It can carry semantic task-understanding layer metadata for AGI-assisted CAX process chains, and it complements STEP/AP242/CAE execution artifacts rather than replacing deterministic CAD/CAE tools.

This checkpoint demonstrates that thesis through:

1. **A working format pipeline.** Eleven CLI commands produce a structured, schema-validated, cross-referenced `.aieng` package from a STEP-like input and a user context YAML.

2. **Real structured data, not just prose.** Every important fact is stored as JSON/YAML with stable IDs and validated against schemas. Markdown summaries are derived, not authoritative.

3. **Cross-resource integrity.** `aieng validate` checks that feature IDs reference topology IDs, constraints reference feature IDs, simulation setup references feature IDs, and protected features are not violated by patch proposals.

4. **Clear maturity labeling.** The format explicitly distinguishes mock-based topology, rule-based feature candidates, user-provided engineering assumptions, and deterministic rule-based summaries from validated solver evidence. No engineering safety claim is made without evidence.

5. **Benchmark scaffold.** The `benchmarks/` directory provides a structured methodology to evaluate whether `.aieng` improves general AI understanding of engineering models without specialized external augmentation.

6. **No heavy dependencies.** The full pipeline runs with only Python, pyyaml, jsonschema, and pydantic. No CAD kernel, mesher, solver, or LLM dependency is required.

7. **Real benchmark evidence aligns with positioning.** In the real STEP benchmark (Phase 11E), raw STEP remained honest (18/18) but had partial usefulness (8/18), while `.aieng` preserved honesty (18/18) and achieved full usefulness (18/18) for structured CAX task understanding.

## Phase 14C checkpoint note

Phase 14C adds the evidence ledger and claim-evidence map scaffolds. `aieng write-evidence-scaffold` writes `results/evidence_index.json` seeded from current package state. Claim proposals are review artifacts requiring human review.

Claims that lack evidence are marked `unsupported` — not false or violated. This is a deliberate design choice: the absence of solver/mesh/geometry evidence means `.aieng` cannot yet assert those claims, but it does not mean the claims are incorrect.

All execution-boundary guards remain in force: `.aieng` core does not run solvers, generate meshes, or directly modify CAD geometry. External tool evidence must be provided by external tools and recorded in `results/evidence_index.json`.


## Phase 12A checkpoint note

Phase 12A is a documentation and positioning refinement only. It does not change CLI behavior, schemas, package structure, or runtime execution paths.

All maturity limits remain in force: `.aieng` does not generate meshes, run solvers, directly modify arbitrary CAD geometry, perform manufacturing validation, or make engineering safety claims without external deterministic evidence.

Agent-facing interfaces such as MCP are optional access layers over the package. They must not be treated as the core product, and future work should prioritize CAD/CAE-side semantic export, artifact provenance, and evidence write-back over agent orchestration.


## Phase 13 checkpoint note

Phase 13 adds semantic edit scaffolds, not arbitrary CAD write-back. `aieng apply-patch` updates structured feature parameters by default, and `aieng export-updated-deck` exports a current-state deck scaffold from `simulation/setup.yaml` for external CAE tools.

These additions do not imply arbitrary STEP editing, B-rep editing, mesh generation by `.aieng`, solver execution by `.aieng`, solver validation, or engineering safety.


## Phase 10C checkpoint note

Phase 10C enriches `objects/interface_graph.json` from explicit `simulation/cae_mapping.json` entries. Rerunning `aieng build-interface-graph` after `aieng apply-cae-mapping` adds `cae_refs` that link CAE deck entities such as `FIXED_HOLES` and `LOAD_FACE` to generated interface/feature IDs. This improves traceability only: it does not infer mappings automatically, run a solver, import solver results, generate a mesh, or modify geometry.


## Phase 15B checkpoint note

Phase 15B adds `provenance/tool_trace.json` and `aieng record-trace`.

`record-trace` records external tool execution steps as provenance/audit entries. It does not run tools. It complements `record-evidence` and human review of claim proposals (Phase 15A).

Tool trace is audit/provenance, not engineering validation by itself. Evidence and claim proposals remain separate; claim proposals are review artifacts requiring human review.

All maturity limits remain in force: `.aieng` does not generate meshes, run solvers, execute CAD kernels, perform manufacturing checks, or make engineering safety claims without external deterministic evidence.


## Phase 16A Completeness and Missingness Report

Phase 16A adds `validation/completeness_report.json` via `aieng write-completeness-report`. The report formalizes best-effort semantic conversion: `.aieng` records which CAD/CAE information is available, partial, missing, unknown, unsupported, conflicting, or not applicable. Missing information is explicit and must not be inferred or fabricated. This keeps the package useful for agents even when CAD/CAE emitters provide incomplete data.
