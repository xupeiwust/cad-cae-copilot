# .aieng AI Reader Guide: definition_plate_with_pattern

## What this package is
This is a self-describing engineering model package for general AI. It adapts CAD/CAE data to AI by carrying structured geometry references, topology, feature candidates, user-provided context, constraints, simulation intent, and protected regions.

This package is not a CAD kernel, CAE solver, mesher, manufacturing checker, or proof that the design is safe.

## How a general AI should read this package
Start from `manifest.json`, then inspect structured JSON/YAML resources before relying on prose summaries. Use stable object IDs when discussing topology entities, features, constraints, simulation setup, or protected regions.

`README_FOR_AI.md` and `ai/summary.md` are derived summaries for readability. Structured JSON/YAML resources are the source of truth.

## Required Reading Order for AI Readers

If the following files are present in this package, inspect them in this order before answering questions about this model:

1. `manifest.json` — package identity and complete resource index
2. `validation/status.yaml` — claim policy and validation-state ledger; **read before answering any engineering validity question**
3. `validation/completeness_report.json` — best-effort conversion report; explicit available/partial/missing/unsupported information
4. `README_FOR_AI.md` — this file; package reading guide
5. `ai/summary.md` — derived engineering narrative (derived; not source of truth)
6. `graph/aag.json` — generated face adjacency index derived from topology_map; not source-of-truth
7. `graph/feature_graph.json` — feature candidates with stable IDs
8. `graph/constraints.json` — structured constraints targeting feature IDs
9. `ai/protected_regions.json` — protected feature IDs and forbidden operations
10. `simulation/setup.yaml` — simulation intent (material, boundary conditions, loads, targets)
11. `simulation/solver_deck.inp` — solver deck if present; may be a scaffold only, not solver evidence
12. `simulation/cae_imports/source_solver_deck.inp` — imported external CAE deck source, if present
13. `simulation/cae_imports/parsed_*.json` and `simulation/cae_mapping.json` — deterministic parsed CAE entities and conservative mapping status
14. `ai/patches/*.json` — patch proposals; unexecuted suggestions, not applied modifications
15. `geometry/topology_map.json` — topology entity IDs; may be mock-generated in current phases
16. `objects/object_registry.json` — generated cross-file index of objects and references; navigation aid only, not source of truth
17. `objects/interface_graph.json` — generated interface index of mounting/protected/fixed/load interfaces; navigation aid only, not source of truth
18. `visual/model_manifest.json` — visual resource manifest, if present; records whether rendered/viewable assets are generated
19. `visual/annotation_layers.json` — visual annotation scaffold, if present; maps feature IDs and topology IDs to visual roles; not rendered geometry

- `validation/status.yaml` is the claim-policy and validation-state ledger. Read it before making any engineering validity claim.
- `validation/completeness_report.json` is the explicit missingness ledger. Treat absent information as missing/unknown/unsupported, not as permission to infer.
- `simulation/solver_deck.inp` may be a scaffold only. It carries an explicit warning if no mesh or solver has run.
- Imported CAE deck resources (`simulation/cae_imports/*`, `simulation/cae_mapping.json`) are parsed inputs and mapping scaffolds, not solver execution evidence.
- `ai/patches/*.json` are unexecuted proposals, not applied modifications. Check `patch_execution` status before assuming any patch was applied.
- `geometry/topology_map.json` may be mock-generated. Topology entity IDs are stable but STEP content is not parsed.
- `graph/aag.json` is a generated adjacency index from topology data and is not source-of-truth geometry.
- Convexity/continuity in `graph/aag.json` may remain unknown unless backend evidence exists.
- `objects/object_registry.json` is a generated index for navigation. Structured source JSON/YAML files remain authoritative.
- `objects/interface_graph.json` is a generated interface index for navigation. Structured source JSON/YAML files remain authoritative.
- `visual/model_manifest.json` is the source of truth for visual resource availability and rendering claims in Phase 8B.
- `visual/annotation_layers.json` is a structured annotation scaffold only. No rendering, glTF, image, or 3D geometry visualization has been performed.

## Before Answering Engineering Validity Questions

Before answering whether this design is safe, solver-validated, manufacturable, or stress-compliant, inspect these resources if present:

- `validation/status.yaml` — check `solver_mesh_status` and `claim_policy.forbidden_claims`
- `simulation/solver_deck.inp` — check for scaffold warning; confirm whether a mesh or solver run exists
- `results/` — check for attached solver result evidence
- `ai/patches/*.json` — check `patch_execution` and `geometry_modified_by_patch` if discussing modifications

Claim discipline rules:

- If `solver_mesh_status.solver_execution` is `not_run`, do not claim a solver was run.
- If `solver_mesh_status.stress_validation` is `not_validated`, do not claim stress targets are satisfied.
- If `solver_mesh_status.manufacturing_validation` is `not_run`, do not claim manufacturability.
- If `patch_status.patch_execution` is `not_run`, do not claim a patch was applied.

## Source-of-truth files
- `manifest.json`
- `graph/feature_graph.json`
- `graph/constraints.json`
- `validation/completeness_report.json`

## Known structured resources
- `README_FOR_AI.md`
- `engineering_context/material.yaml`
- `graph/constraints.json`
- `graph/feature_graph.json`
- `validation/completeness_report.json`
- `validation/status.yaml`

## Engineering object summary
- `feat_base_plate_001` (base_plate): Probe base plate
- `feat_hole_pattern_001` (mounting_hole_pattern): Protected mounting hole pattern
- `feat_load_interface_001` (interface_face): Load interface candidate
- `feat_flange_001` (flange): Side flange candidate

## Feature recognition quality
- feature_count: 4
- confidence_counts: medium=4
- features_with_explicit_uncertainty_notes: 0/4
- recognition_methods: structured_definition=4
- Recognition output is candidate-level and requires validation before engineering claims.

## Protected regions
- `ai/protected_regions.json` is missing; no protected regions are declared.

## Simulation intent
- `simulation/setup.yaml` is missing; no simulation intent is declared.

## CAE deck imports
- No imported CAE deck scaffold resources are present.

## CAE interface mappings
- No explicit CAE deck entities are linked to interface graph entries.

## Visual resources
- `objects/object_registry.json` is not present. Run `aieng build-object-registry` to generate it.
- `objects/interface_graph.json` is not present. Run `aieng build-interface-graph` to generate it.
- `visual/model_manifest.json` is not present. Run `aieng build-visual-manifest` to generate it.
- `visual/annotation_layers.json` is not present. Run `aieng build-visual-index` to generate it.

## Active task contract
- `task/task_spec.yaml` is absent; no structured task contract has been written for this package. Run `aieng write-task-spec` to generate one.

## External tool handoff contract
- `task/external_tool_requirements.json` is absent; no external tool handoff contract has been written. Run `aieng write-external-tool-requirements` to generate one.

## Evidence ledger
- `results/evidence_index.json` is absent; no evidence ledger has been written. Run `aieng write-evidence-scaffold` to generate one.

## Claim-evidence map
- `results/claim_map.json` is absent; no claim-evidence map has been written. Run `aieng write-evidence-scaffold` to generate one.

## Provenance tool trace
- `provenance/tool_trace.json` is absent; no external tool execution steps have been recorded. Run `aieng record-trace` to record a step.

## Completeness and missingness
- report_id: `completeness_001`
- conversion_mode: `best_effort`
- best_effort_conversion: true — convert available CAD/CAE information without requiring all fields to exist
- missingness_explicit: true — missing/unknown/unsupported information must be stated, not guessed
- unsupported_is_not_false: true — unsupported claims are not false; they lack evidence
- category status counts: available: 3, missing: 15, not_applicable: 1, partial: 1
- missing categories: ['geometry', 'topology', 'adjacency', 'protected_regions', 'cae_imports', 'cae_mapping', 'mesh_handoff_contract', 'task_contract', 'external_tool_handoff', 'evidence_ledger', 'claim_map', 'provenance_trace', 'visual_resources', 'object_registry', 'interface_graph']
- partial categories: ['simulation_setup']
- next_recommended_actions: ['run_extract_topology_or_emit_topology_map', 'provide_protected_regions', 'write_mesh_handoff_contract', 'write_evidence_scaffold', 'record_external_tool_trace_when_tools_run']

## Consolidated evidence report
- `validation/evidence_report.json` is absent; consolidated claim/evidence validation view is not available. Run `aieng write-evidence-report` to generate one.

## Validation state
- Package structure and referenced resources may be checked with `aieng validate`.
- Topology, feature, and context resources are structurally validated when present and referenced.
- No mesh generation has been run by Phase 5A.
- No solver result has been attached.
- Imported CAE deck resources do not imply mesh generation, solver execution, or validated results.
- No stress or displacement claim is solver-validated.

## Important limitations
- STEP import is a resource copy; STEP content is not parsed.
- Topology extraction is currently mock-based.
- Feature recognition is deterministic and rule-based; detected features are candidates, not guaranteed engineering truth.
- Context is user-provided engineering meaning and assumptions; it is not solver evidence.
- These summaries are generated from structured resources without LLM, RAG, skill, plugin, mesher, solver, CAD parser, or manufacturing-checker calls.

## Rules for AI readers
- Do not claim the design is safe unless solver-validated evidence exists.
- Do not treat candidate features as confirmed engineering truth.
- Do not modify protected regions.
- Do not invent material properties.
- Distinguish extracted facts, inferred candidates, user-provided context, and validated results.
- Use object IDs when referring to features, topology entities, constraints, or protected regions.
