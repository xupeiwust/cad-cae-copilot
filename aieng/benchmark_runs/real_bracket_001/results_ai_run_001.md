# Real STEP AI Benchmark Run 001

Recorded during Phase 11E.

## Benchmark purpose

Compare whether raw STEP or .aieng semantic package better supports general AI understanding of a CAX engineering model.

## Inputs

- Condition A: `examples/real_bracket.step`
- Condition B: curated semantic package files only:
  - `README_FOR_AI.md`
  - `manifest.json`
  - `geometry/topology_map.json`
  - `graph/aag.json`
  - `graph/feature_graph.json`
  - `graph/constraints.json`
  - `simulation/setup.yaml`
  - `ai/protected_regions.json`
  - `ai/summary.md`
  - `ai/patches/patch_0001.json`
  - `validation/status.yaml`

## Procedure

1. Two separate AI sessions were used, one for Condition A and one for Condition B.
2. Condition A session was instructed to use only raw STEP input.
3. Condition B session was instructed to use only curated .aieng package files.
4. A third scoring pass compared both outputs using Honesty and Usefulness dimensions.

## Execution basis

- Real demo completed in prior Phase 11D evidence run (`scripts/run_real_step_demo.py`).
- Package validation passed in prior Phase 11D evidence run (`aieng validate build/real_bracket_001.aieng`).

## Scoring table

| Category | A Honesty | A Usefulness | B Honesty | B Usefulness | Notes |
|---|---:|---:|---:|---:|---|
| Object identity | 2 | 1 | 2 | 2 | A identifies a single B-rep part but not semantic model identity; B identifies `real_bracket_001`. |
| Geometry/topology grounding | 2 | 2 | 2 | 2 | Both ground geometry/topology well; A uses STEP entities, B uses stable `.aieng` IDs. |
| Feature grounding with IDs | 2 | 1 | 2 | 2 | A infers features from geometry; B uses feature IDs. |
| AAG/adjacency reasoning | 2 | 0 | 2 | 2 | A has no AAG; B uses `graph/aag.json`. |
| Constraints/protected regions | 2 | 0 | 2 | 2 | A lacks constraints; B identifies protected hole pattern and allowed/forbidden operations. |
| Simulation/context understanding | 2 | 0 | 2 | 2 | A lacks CAE context; B identifies material, load, BC, solver target, and target stress as setup. |
| Validation honesty | 2 | 1 | 2 | 2 | Both avoid false solver/safety claims; B additionally cites validation status. |
| Patch proposal structure | 2 | 1 | 2 | 2 | A gives conceptual proposal; B cites `patch_0001`. |
| Fact/candidate/assumption/result distinction | 2 | 2 | 2 | 2 | Both are careful; B separates topology, AAG, candidates, assumptions, patch, and missing evidence. |

## Totals

| Condition | Honesty Total | Usefulness Total | Max |
|---|---:|---:|---:|
| A Raw STEP | 18 | 8 | 18 |
| B .aieng | 18 | 18 | 18 |

## Interpretation

- Raw STEP did well on direct geometric/topological extraction.
- Raw STEP remained weak for CAX task execution because it lacked design intent, constraints, protected regions, simulation context, validation status, and structured operations.
- .aieng preserved honesty while adding actionable semantic context.
- This supports the refined project positioning: .aieng is a semantic task-understanding layer for AGI-assisted CAX process chains, not a replacement for STEP/CAD/CAE tools.

## Conservative limitations

- Single AI benchmark run.
- Manual scoring.
- No external solver.
- No mesh.
- No geometry modification.
- No manufacturing validation.
- No engineering safety claim.
- Feature labels remain candidate-level unless validated.
