# Condition B Input Index (Plate With Pattern Probe)

Required input set for benchmark Condition B-rich:

- README_FOR_AI.md
- manifest.json
- graph/feature_graph.json
- graph/constraints.json
- validation/status.yaml
- validation/completeness_report.json

Optional supplementary resources (rich):

- ai/summary.md
- task/task_spec.yaml
- task/external_tool_requirements.json
- results/evidence_index.json
- results/claim_map.json
- validation/evidence_report.json

Sparse variant note:

- condition_b_sparse intentionally excludes task/* and results/* resources.
- this is expected and should lower usefulness while preserving honesty.
