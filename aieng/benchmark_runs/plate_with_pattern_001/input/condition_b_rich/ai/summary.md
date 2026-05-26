# Engineering Summary

This is a derived summary for general AI readability. Structured JSON/YAML resources are the source of truth.

## Model identity
- model_id: `definition_plate_with_pattern`
- format_version: `0.1.0`
- units: `{"force": "N", "length": "mm", "mass": "kg", "stress": "MPa"}`

## Geometry resources
- No geometry resources are indexed.

## Topology summary
- `geometry/topology_map.json` is missing.

## AAG summary
- `graph/aag.json` is missing.

## Feature summary
- `feat_base_plate_001` (base_plate): Probe base plate; candidate recognition `structured_definition` confidence `medium`; editable params (agent_defined): length_mm=140, thickness_mm=10, width_mm=90
- `feat_hole_pattern_001` (mounting_hole_pattern): Protected mounting hole pattern; candidate recognition `structured_definition` confidence `medium`; editable params (agent_defined): count=4, diameter_mm=10, pitch_x_mm=100, pitch_y_mm=50, through=True
- `feat_load_interface_001` (interface_face): Load interface candidate; candidate recognition `structured_definition` confidence `medium`; editable params (agent_defined): nominal_area_mm2=400
- `feat_flange_001` (flange): Side flange candidate; candidate recognition `structured_definition` confidence `medium`; editable params (agent_defined): diameter_mm=42, thickness_mm=8

## Feature recognition quality
- feature_count: 4
- confidence_counts: medium=4
- features_with_explicit_uncertainty_notes: 0/4
- recognition_methods: structured_definition=4
- Recognition output is candidate-level and requires validation before engineering claims.

## Constraints summary
- `con_protect_holes_001` (protect_geometry) targets `feat_hole_pattern_001`: Preserve mounting interface.
- `con_static_target_001` (simulation_target) targets `sim_static_001`: Keep stress below target after modifications.; target metric `max_von_mises_stress_mpa` <= 140

## Protected regions
- `ai/protected_regions.json` is missing.

## Simulation setup
- `simulation/setup.yaml` is missing.

## CAE deck imports
- No imported CAE deck scaffold resources are present.

## CAE interface mappings
- No explicit CAE deck entities are linked to interface graph entries.

## Assumptions
- Plate is represented semantically; no CAD topology exists in this probe.
- Hole pattern is the protected mounting interface.
- Package is definition-sourced and does not contain STEP geometry.
- Feature geometry references are semantic-only until geometry generation is implemented.

## Visual resources
- `objects/object_registry.json` is not present.
- `objects/interface_graph.json` is not present.
- `visual/model_manifest.json` is not present.
- `visual/annotation_layers.json` is not present.

## Active task contract
- `task/task_spec.yaml` is absent.

## External tool handoff contract
- `task/external_tool_requirements.json` is absent.

## Evidence ledger
- `results/evidence_index.json` is absent.

## Claim-evidence map
- `results/claim_map.json` is absent.

## Provenance tool trace
- `provenance/tool_trace.json` is absent; no external tool steps have been recorded.

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
- `validation/evidence_report.json` is absent; consolidated claim/evidence validation view is not available.

## Validation status
- For validation-state questions, inspect `validation/status.yaml` first — it contains `solver_mesh_status` and `claim_policy`.
- Geometry package validation may pass.
- Topology, feature, and context structural validation may pass when their resources are present and referenced.
- No mesh generation has been run.
- No solver result has been attached.
- Imported CAE deck resources do not imply mesh generation, solver execution, or validated results.
- No stress/displacement claim is validated.

## Missing information
- Topology map is missing; topology IDs and surface types are unavailable.
- Simulation setup is missing; no analysis intent is declared.
- Imported CAE deck source is missing; no external CAE deck import has been attached.
- CAE mapping scaffold is missing; imported CAE entities cannot be checked against feature/interface IDs.
- Protected regions are missing; modification restrictions are unavailable.
- Evidence ledger is absent; no external tool evidence has been recorded. Run `aieng write-evidence-scaffold` to generate the scaffold.
- Claim-evidence map is absent; no claim-evidence traceability has been written.
- Consolidated evidence report is absent; claim/evidence read-view synthesis is not available.

## Suggested next structured files to inspect
- `manifest.json`
- `validation/completeness_report.json`
- `graph/feature_graph.json`
- `graph/constraints.json`
