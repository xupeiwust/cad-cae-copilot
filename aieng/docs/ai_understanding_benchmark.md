# AI Understanding Benchmark

This document defines a future benchmark for testing whether `.aieng` improves AI understanding of engineering models without relying on specialized external enhancement.

For the current runnable benchmark procedure, inputs, scoring flow, and result format, see `docs/benchmark_methodology.md`.

## Goal

Measure whether a general AI can understand an engineering model better from a self-describing `.aieng` package than from raw CAD/CAE files alone.

The benchmark compares:

A. Raw STEP, B-rep, and CAE files.

B. A `.aieng` package containing structured geometry references, object IDs, feature semantics, design intent, constraints, simulation context, validation state, visual mappings, allowed operations, and assumptions.

## Restrictions

The benchmark should evaluate file-native understanding. During the understanding phase, the AI should not rely on:

- external RAG;
- skills;
- MCP tools;
- specialized training;
- CAD plugins;
- geometry kernels;
- meshers;
- solvers.

Deterministic tools may be used only in a separate execution or validation phase after the AI has produced an answer or structured proposal from the available files.

## Example Questions

The benchmark should ask questions such as:

1. What is this part?
2. What are the main engineering features?
3. Which regions are mounting interfaces?
4. Which features should not be modified?
5. What are the design intents of ribs, holes, flanges, and plates?
6. What material is assigned?
7. What simulation setup is intended?
8. Which claims are validated and which are assumptions?
9. What modifications are allowed?
10. Propose a mass reduction patch while preserving protected interfaces.
11. Which CAE deck entities were imported?
12. Which CAE targets map to which feature/interface IDs?
13. Were CAE mappings user-provided or automatically inferred?
14. Does imported CAE setup prove that a solver was run?

## Expected `.aieng` Advantages

A successful `.aieng` package should improve answers by making the AI:

- cite object IDs, feature IDs, topology IDs, and constraint IDs;
- distinguish structured facts from assumptions, unvalidated suggestions, and solver-validated results;
- identify protected regions and preserved interfaces;
- avoid hallucinating solver results that are not present in validation evidence;
- explain simulation intent without claiming completed analysis;
- generate structured patch proposals instead of only prose;
- list required deterministic validation steps for proposed modifications;
- connect visual references back to engineering objects when visual mappings exist;
- inspect CAE import and mapping resources while distinguishing CAE target names from feature/interface IDs;
- identify user-provided CAE mappings and avoid claiming solver results exist when only CAE setup/mapping resources are present.

## Evaluation Criteria

Candidate metrics include:

- object-reference precision: whether answers cite valid IDs;
- protected-region recall: whether protected targets are identified;
- validation honesty: whether the answer avoids unsupported stress, safety, or manufacturability claims;
- assumption separation: whether assumptions are labeled separately from facts;
- patch structure quality: whether proposed modifications use allowed operations and target IDs;
- tool-independence: whether the answer can be produced before calling external tools;
- traceability: whether each important claim points back to a package resource.

## Benchmark Output

Each model response should be scored against a rubric and stored with:

- input condition: raw CAD/CAE files or `.aieng` package;
- question set version;
- allowed context;
- whether external tools were disabled during understanding;
- answer text;
- cited IDs;
- detected hallucinations or unsupported claims;
- structured patch validity, when applicable.

The benchmark should not treat `.aieng` as solver evidence by default. A package improves understanding only when it helps the AI correctly identify what is known, what is assumed, and what still requires deterministic validation.

## Phase 18C Semantic Coverage Probe Scaffold

Phase 18C-min adds a coverage-probe scaffold at `benchmark_runs/plate_with_pattern_001/`.

The probe uses two Condition B variants generated from the same deterministic definition fixture:

- rich variant: includes task and evidence resources for traceability-focused questions.
- sparse variant: intentionally omits task/evidence resources to stress missingness reasoning and honesty calibration.

Preparation script:

- `scripts/prepare_plate_with_pattern_benchmark_pack.py`

Probe intent:

- measure reference correctness for quoted `@aieng[...]` handles,
- measure missing vs partial vs unsupported reasoning,
- verify unsupported-claim calibration,
- verify evidence-trace correctness,
- verify external-tool-boundary correctness.

## Phase 11C Real-Geometry Scaffold

Phase 11C adds an optional real-geometry benchmark run scaffold at `benchmark_runs/real_bracket_001/`.

The scaffold keeps the same benchmark principle while using a real STEP fixture path:

- Condition A: raw `examples/real_bracket.step` only
- Condition B: generated `build/real_bracket_001.aieng` resources, including `geometry/topology_map.json`, `graph/aag.json`, `graph/feature_graph.json`, `graph/constraints.json`, `simulation/setup.yaml`, `ai/protected_regions.json`, `ai/summary.md`, and `validation/status.yaml`

Preparation scripts:

- `scripts/generate_real_bracket_step.py`
- `scripts/run_real_step_demo.py`
- `scripts/prepare_real_benchmark_pack.py`

This scaffold remains optional. Default tests and the default reference pipeline still run without CAD dependencies.
