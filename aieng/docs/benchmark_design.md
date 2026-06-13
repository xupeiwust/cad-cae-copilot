# `.aieng` AI Usefulness Benchmark — Design Groundwork

**Status**: Design only — not yet implemented.
**Phase**: 20 (groundwork); full implementation deferred.

---

## Purpose

A benchmark suite for evaluating how well an AI system uses a `.aieng` package to perform
tasks that matter to mechanical engineers. The benchmark measures whether the structured,
AI-readable output of a converter is actually *useful* — not just whether it validates.

`.aieng` does not execute solvers, meshers, optimizers, or CAD edits. The benchmark
likewise does not measure any of those. It measures whether the AI can correctly interpret
what the package *records* about the engineering artifact.

---

## Benchmark Tracks

### Track A — CAD Understanding

The AI receives a `.aieng` package (converter-produced or definition-sourced) and must
answer questions about the model's structure without running any CAD tool.

Example questions:
- How many distinct feature types are present?
- Which objects are candidate mounting holes?
- What parameters were extracted and what are their values?
- Which features have low-confidence recognition?
- What information is explicitly recorded as missing or unsupported?

**Target behaviour**: Accurate, grounded answers; explicit acknowledgement of uncertainty;
no hallucination of missing information as present.

### Track B — CAD Reconstruction Assistance

The AI receives a partially described model (feature graph + object registry, no STEP
geometry) and must produce a CadQuery or structured script that reconstructs the model
from the recorded parameters.

The benchmark does **not** execute the script automatically. A human or external tool
evaluates geometric correspondence against a reference STEP file.

**Target behaviour**: Syntactically valid reconstruction script; parameters match the
package record; no invented parameters; explicit TODO for missing dimensions.

### Track C — FEM Preprocessing Readiness

The AI receives a converter-produced package (with mesh handoff contract and/or
external tool requirements) and must produce a structured preprocessing plan:
- which external tools to invoke and in what order
- which named selections to define
- which boundary conditions to apply
- what solver settings to configure

The plan is *structured* and *auditable*. It does not execute any tool.

**Target behaviour**: Plan addresses all external_tool_requirements entries; references
only IDs that exist in the package; flags gaps; does not hallucinate solver capabilities.

### Track D — CAE Deck Understanding

The AI receives a `.aieng` package with an imported solver deck (`simulation/setup.yaml`,
`simulation/solver_deck.inp`) and must answer questions:
- What solver type is configured?
- What boundary conditions are defined?
- Which material cards are present?
- What is the load magnitude on named selections X and Y?

**Target behaviour**: Accurate extraction; no invention; explicit uncertainty for fields
not present in the deck.

---

## Evaluation Dimensions

Each benchmark question/task is scored across these dimensions:

| Dimension | Description | Scale |
|-----------|-------------|-------|
| `geometry_understanding_score` | Correct identification of geometric features and their properties | 0–2 |
| `feature_identification_score` | Correct classification and enumeration of named features | 0–2 |
| `referenceability_score` | Correct use of stable IDs and resource paths from the package | 0–2 |
| `missingness_honesty_score` | Explicit, accurate reporting of missing/unsupported/uncertain information | 0–2 |
| `preprocessing_readiness_score` | Quality and correctness of the preprocessing plan (Track C only) | 0–2 |
| `hallucination_penalty` | Deduction for invented facts not present or implied by the package | −1 per instance |
| `task_success_score` | Binary: did the AI accomplish the stated task goal? | 0 or 1 |

Maximum score per task: 11 (6 dimensions × 2 − 1) + 1 task success.
`hallucination_penalty` is unbounded below.

---

## Scoring Notes

- **Missingness honesty is first-class.** A response that says "X is not recorded in this
  package" scores higher than one that guesses or invents X.
- **Hallucination is penalised, not just unscored.** The package's explicit
  `coverage_categories`, `unsupported_or_missing`, and `uncertainty_notes` define the
  ground truth for what *should* be unknown.
- **Levels L0–L5 are not directly tested.** The benchmark tests semantic usefulness, not
  level attainment. A package at L2 can produce a perfect missingness_honesty score.

---

## Input Package Requirements

Each benchmark scenario requires a reference package with:

1. A valid `.aieng` package (passes `aieng validate`)
2. A `provenance/conversion_manifest.json` with `coverage_categories` populated
3. A `validation/completeness_report.json`
4. Ground-truth answers for each question (human-curated)

The `examples/sample_bracket.FCStd` fixture converted via `aieng convert` is the
reference input for Track A and B scenarios.

---

## Non-Goals

This benchmark does **not**:

- Execute any CAD, CAE, mesh, or solver operation
- Generate geometry
- Evaluate model *quality* (that is an engineering judgement)
- Measure runtime performance
- Replace engineer review of any output

---

## Future Work

- Implement a `benchmarks/ai_usefulness/` directory with scenario files, scoring rubric,
  and result templates (analogous to `benchmarks/handoff/`)
- Integrate with the converter pipeline: `aieng convert` → benchmark run → structured results
- Extend Track C to use the mesh handoff contract (`simulation/mesh_handoff_contract.json`)
  once more packages exercise that path

---

*This document describes the benchmark design only. No benchmark runner has been
implemented as part of Phase 20. Implementation is deferred to a future phase.*
