# Future Package Structure

This document describes future `.aieng` package resources and why they may exist. These resources are not all implemented in Phase 0.

Positioning reminder: `.aieng` is a semantic task-understanding layer for AGI-assisted CAX process chains. It complements STEP/AP242/CAE artifacts and does not replace CAD kernels, CAE preprocessors, meshers, solvers, or manufacturing tools. `.aieng` describes, references, configures, and records; external CAD/CAE software executes geometry editing, meshing, solving, and result generation.

## Future Resources

### `README_FOR_AI.md`

A concise orientation file for general AI systems. It should summarize the model, point to structured resources, explain known limitations, and warn against unsupported engineering claims. It must not replace structured data as the source of truth.

### `objects/`

The object layer for AI-readable model meaning. It may contain an object registry, topology map, feature graph, semantic graph, and stable cross-resource IDs. This layer bridges exact geometry files and engineering concepts such as holes, ribs, flanges, plates, bosses, interfaces, and unknown features.

This layer now includes `objects/object_registry.json` (Phase 9A — implemented), a generated index of object IDs, definition files, and cross-file references.

This layer now also includes `objects/interface_graph.json` (Phase 9B — implemented), a generated index of engineering interfaces (mounting/protected/fixed/load roles), interface references, and preservation-relevant metadata derived from existing structured resources.

`objects/object_registry.json` is not source-of-truth data. It is a generated navigation index. Structured source JSON/YAML files remain authoritative.

`objects/interface_graph.json` is not source-of-truth data. It is a generated interface navigation/index resource. Feature graph, constraints, simulation setup, protected regions, and visual annotations remain authoritative.

### `graph/`

This layer carries generated graph resources derived from topology and feature resources.

Phase 11B adds `graph/aag.json` (implemented), an attributed adjacency graph/index generated from `geometry/topology_map.json`.

`graph/aag.json` is a generated index and not source-of-truth geometry data. `geometry/topology_map.json` remains authoritative for topology entities and references.

`graph/aag.json` does not imply automatic feature truth, mesh generation, solver execution, or geometry modification.

Phase 11A topology hardening allows optional face-to-edge and edge-to-face ownership references in topology extraction output when backend evidence is available. These optional adjacency-evidence fields improve traceability but do not by themselves validate engineering correctness.

### `intent/`

Design intent, assumptions, and tradeoffs. This layer explains why features exist, which design goals matter, and where the package contains inferred or user-provided meaning rather than validated facts.

### `constraints/`

Protected regions, allowed operations, engineering constraints, manufacturing rules, and modification preconditions. This layer tells an AI what must be preserved, what can change, and what validation is required before a change can be trusted.

### `simulation/`

Simulation setup and validation targets. This layer describes intended analyses, materials, assignments, loads, boundary conditions, requested outputs, target criteria, and references to external mesh/solver artifacts when present. It should distinguish intended setup from completed solver evidence and should not imply that `.aieng` core generates meshes or runs solvers.

This layer now also includes a Phase 10A CAE deck import scaffold:
- `simulation/cae_imports/source_solver_deck.inp`
- `simulation/cae_imports/parsed_materials.json`
- `simulation/cae_imports/parsed_boundary_conditions.json`
- `simulation/cae_imports/parsed_loads.json`
- `simulation/cae_mapping.json`

These resources are deterministic parsed-input and mapping scaffolds only. They are not solver execution evidence and do not imply mesh generation or imported results.

Phase 13C adds `simulation/updated_deck.inp` as an updated CAE deck scaffold. It can reflect the current semantic setup for external CAE software, but it still does not contain generated mesh nodes/elements, node sets, element sets, or solver results.

Phase 10B adds explicit user-provided mapping application:
- `aieng apply-cae-mapping <package.aieng> --mapping <mapping.yaml>` updates `simulation/cae_mapping.json`
- CAE target names (for example deck set names) remain distinct from feature/interface IDs unless explicitly mapped by the user
- mapping records are user-provided references, not automatically inferred geometry truth

Future roundtrip/write-back resources may also include cautiously-scoped modified geometry or regeneration artifacts, but only when backed by explicit executable parametric sources. These future resources must not imply arbitrary STEP/B-rep editing.

### `validation/`

Validation status and evidence. This layer records which checks have passed, failed, or remain unrun. Evidence may include validator output, imported geometry checks, external mesh checks, external solver summaries, manufacturing checks, and provenance for deterministic tools. Mesh and solver evidence should be produced by external CAE software and referenced or imported into `.aieng`; `.aieng` core should not be presented as the mesher or solver.

Current resources: `validation/status.yaml` (Phase 6B), `validation/completeness_report.json` (Phase 16A).

Planned resource: `validation/evidence_report.json` — a consolidated derived-view resource that presents claim pass/fail/unsupported status alongside linked evidence pointers from `results/claim_map.json` and `results/evidence_index.json`. This follows the existing `<noun>_report.json` convention in this directory and is a derived view only; the three underlying source-of-truth resources remain authoritative. Do not use `results/validation_report.json` as a name — `results/` contains source-of-truth records, not derived views, and `validation_report` already names a producer `--kind` in `aieng record-evidence`. See `docs/issue_coverage_inventory.md` (C4) for the full naming decision.

### `visual/`

Visual annotation layers and previews. This layer includes `visual/annotation_layers.json` (Phase 8A — implemented), a structured scaffold that maps feature IDs and topology IDs to visual roles (candidate_feature, protected_region, simulation_context, unclassified_geometry).

This layer also includes `visual/model_manifest.json` (Phase 8B — implemented), a structured visual resource manifest that distinguishes annotation metadata from rendered/viewable assets and records explicit no-rendering claim policy for the current phase.

Future additions may include GLB previews, feature snapshots, and mapping files that connect visual selections back to topology IDs, feature IDs, and constraints.

`visual/annotation_layers.json` is annotation metadata only — no rendering, glTF, image, or 3D geometry visualization is generated.

`visual/model_manifest.json` is a claim/availability scaffold only in Phase 8B. It does not generate `model.glb`, screenshots, or rendered geometry.

### `history/`

Decision and patch history. This layer may include design decisions, change logs, structured patch records, validation outcomes, and rationale over time.

### `engineering_logic/`

Reusable engineering rules, formulas, derivations, or lightweight deterministic checks that explain relationships between design variables, constraints, and validation targets. This should not replace solvers where solvers are required, but it can document transparent engineering logic.

### `manufacturing/`

Manufacturing process assumptions, constraints, inspection requirements, tolerances, material/process compatibility, and manufacturability checks. This layer should distinguish rules encoded in the package from checks actually validated by manufacturing tools or experts.

## Engineering Model Repository Analogy

`.aieng` should eventually behave more like a software repository than a single CAD file.

A software repository commonly contains:

- source code;
- README files;
- tests;
- dependencies;
- CI status;
- commit history;
- documentation.

An engineering model package should analogously contain:

- geometry;
- object registry;
- feature graph;
- design intent;
- constraints;
- simulation setup;
- validation status;
- visual mappings;
- patch history;
- decisions.

The key idea is that the package should preserve not only the model geometry, but also the engineering context needed to understand, modify, validate, and audit the model. A general AI should be able to inspect the repository-like package and know where meaning, evidence, assumptions, and allowable changes are stored.

## Phase 0 Compatibility

This document is future-facing guidance only. It does not change the current Phase 0 package structure, CLI commands, schemas, or validator behavior.


## CAE-to-Interface Traceability

Future `.aieng` packages may use `objects/interface_graph.json` as a navigation index that includes optional `cae_refs` derived from explicit CAE mapping resources. These links show which CAE deck entities target which engineering interfaces or features, while `simulation/cae_mapping.json` remains the source of truth. This traceability does not imply automatic inference, meshing, solver execution, or result validation.
