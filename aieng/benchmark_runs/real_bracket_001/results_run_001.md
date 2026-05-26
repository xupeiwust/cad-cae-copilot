# Real Bracket Benchmark Result Record (Run 001)

Recorded during Phase 11D.

## Environment

- Python environment: `aieng311`
- Optional geometry backend status: **available** — CadQuery 2.7.0 + cadquery-ocp 7.8.1.1.post1 installed via `pip install cadquery`

## Inputs

- Condition A: raw `examples/real_bracket.step`
- Condition B: generated `.aieng` package resources from `build/real_bracket_001.aieng` via `scripts/run_real_step_demo.py`

## Procedure

1. STEP generation command:
   - `conda run -n aieng311 python scripts/generate_real_bracket_step.py`
2. Real demo command:
   - `conda run -n aieng311 python scripts/run_real_step_demo.py`
3. Benchmark pack command:
   - `conda run -n aieng311 python scripts/prepare_real_benchmark_pack.py`
4. Validation command (intended when package exists):
   - `conda run -n aieng311 python -m aieng.cli validate build/real_bracket_001.aieng`

## Observations

- Real STEP fixture generated successfully: `examples/real_bracket.step` (48 151 bytes); model is base plate + 4 through holes + raised web.
- OCC/OCP extraction ran successfully (`--backend occ`) via `aieng extract-topology`.
- `build/real_bracket_001.aieng` was generated and fully populated by `scripts/run_real_step_demo.py`.
- `geometry/topology_map.json`: PASS — present and schema-valid; entity IDs unique; type-specific fields present.
- `graph/aag.json`: PASS — present and schema-valid; node IDs unique; arc IDs unique; policy notes present.
- `graph/feature_graph.json`: PASS — present and schema-valid; feature IDs unique; geometry references resolve.
- `graph/constraints.json`: PASS — present and schema-valid; constraints reference known features.
- `ai/protected_regions.json`: PASS — present and schema-valid.
- `ai/summary.md`: PASS — non-empty.
- `validation/status.yaml`: PASS — all required sections present; forbidden claim policy present; no solver execution claimed; no geometry modification claimed.
- `ai/patches/patch_0001.json`: PASS — schema-valid; references known features; respects protected targets.
- Package validation (`aieng validate build/real_bracket_001.aieng`): all critical checks PASS; 16 optional WARNs (simulation/cae_imports, objects/, visual/, results/, previews/ — expected for Phase 11).

## Benchmark interpretation

- Raw STEP is expected to expose exact CAD exchange content but not explicit AI-oriented design intent, constraints, validation state, or allowed operations.
- `.aieng` is expected to expose stable IDs, topology map, AAG adjacency graph, candidate features, user-provided context, protected regions, patch proposal, and validation status.
- AAG may improve adjacency and feature reasoning, but it is a generated index and not source of truth.

## Conservative claim policy

- No solver result exists.
- No mesh was generated.
- No geometry was modified.
- Feature recognition remains candidate-level unless externally validated.
- No engineering safety claim is made.

## Scoring template (unfilled)

| Condition | Honesty / non-hallucination | Engineering usefulness |
|---|---|---|
| Condition A (raw STEP) | not scored | not scored |
| Condition B (`.aieng`) | not scored | not scored |

No external AI scoring session was run in Phase 11D; this record captures package generation and benchmark-readiness evidence only.
