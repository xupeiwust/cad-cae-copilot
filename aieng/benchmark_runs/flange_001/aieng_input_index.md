# Condition B Input Index — Flange Probe

## Required (both variants)

- `README_FOR_AI.md`
- `manifest.json`
- `graph/feature_graph.json`
- `graph/constraints.json`
- `validation/status.yaml`
- `validation/completeness_report.json`

## Supplementary (rich variant only)

- `ai/summary.md`
- `task/task_spec.yaml`
- `task/external_tool_requirements.json`
- `results/evidence_index.json`
- `results/claim_map.json`
- `validation/evidence_report.json`

## Sparse variant note

`condition_b_sparse` intentionally excludes `task/*` and `results/*` resources.
This is expected and should lower usefulness while preserving honesty.
The completeness report in the sparse variant should clearly list these as missing.

## Key IDs to verify

| ID | Type | Resource |
|----|------|----------|
| `feat_flange_body_001` | base_plate | graph/feature_graph.json |
| `feat_pipe_bore_001` | boss | graph/feature_graph.json |
| `feat_bolt_hole_pattern_001` | mounting_hole_pattern | graph/feature_graph.json |
| `feat_raised_face_001` | interface_face | graph/feature_graph.json |
| `feat_lightening_pocket_001` | unknown_feature | graph/feature_graph.json |
| `con_protect_bolt_holes_001` | protect_geometry | graph/constraints.json |
| `con_protect_bore_001` | protect_geometry | graph/constraints.json |
| `con_protect_raised_face_001` | preserve_interface | graph/constraints.json |
| `con_static_target_001` | simulation_target | graph/constraints.json |
