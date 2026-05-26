# AI Usefulness Benchmark Scaffold

**Phase 21 — Status: scaffold only, no runs recorded yet.**

This benchmark evaluates whether `.aieng` packages improve AI understanding and task
preparation for mechanical engineers, compared with providing raw CAD/CAE inputs directly.

---

## The central question

> Given the same engineering model, does an AI system produce better, more grounded,
> more honest answers when given a structured `.aieng` package than when given the
> raw CAD/CAE source directly?

The benchmark uses a **two-condition comparison** for each task:

- **Condition A — without `.aieng`**: the AI receives raw source files only
  (e.g. a STEP file dump, FCStd Document.xml text, or solver deck text).
- **Condition B — with `.aieng`**: the AI receives the full structured `.aieng` package
  contents (feature graph, object registry, coverage categories, readiness report,
  completeness report, README_FOR_AI.md, etc.) but not the raw source file.

The delta between conditions measures the value `.aieng` adds to AI reasoning.

---

## What this benchmark does NOT test

- Whether `.aieng` runs CAD/CAE workflows — it does not.
- Whether `.aieng` runs solvers — it does not.
- Whether `.aieng` generates meshes — it does not.
- Whether `.aieng` optimizes designs — it does not.
- Whether `.aieng` makes engineering decisions — it does not.

The benchmark tests whether `.aieng` **improves AI understanding and task preparation**
compared with raw CAD/CAE inputs. All engineering execution remains external.

---

## Benchmark tracks

| Track | Focus |
|-------|-------|
| **A — CAD Understanding** | Feature identification, geometry reasoning, missingness honesty |
| **B — CAD Reconstruction Assistance** | Drawing description, reconstruction plan, parameter extraction |
| **C — FEM Preprocessing Assistance** | Material/load/BC identification, mesh requirements, missing inputs |
| **D — CAE Deck Understanding** | Load/constraint/material/element explanation, CAD-CAE mapping gaps |

Each track has a question set and a two-condition scoring rubric.

---

## Scoring

Scores are assigned per dimension on a **0–2 scale** (0 = absent/incorrect,
1 = partial/vague, 2 = correct and grounded), plus a **hallucination penalty** (−1 per
fabricated fact) and a **binary task success** (0 or 1).

| Dimension | Tracks |
|-----------|--------|
| `geometry_understanding_score` | A, B, C |
| `feature_identification_score` | A, B, C, D |
| `referenceability_score` | A, B, C, D |
| `missingness_honesty_score` | A, B, C, D |
| `preprocessing_readiness_score` | C only |
| `hallucination_penalty` | all |
| `task_success_score` | all |

Maximum score per task (tracks A, B, D): 4×2 + 1 = **9**.
Maximum score per task (track C): 5×2 + 1 = **11**.

Scores are recorded separately for Condition A and Condition B to compute the delta.

---

## What is excluded

This benchmark intentionally excludes all external augmentation during the AI session:

- MCP tool calls
- RAG or retrieval augmentation
- Skills, plugins, or LLM fine-tuning
- External CAD tool calls (FreeCAD, Gmsh, CATIA, etc.)
- External CAE tool calls (CalculiX, Abaqus, etc.)
- Solver execution or result generation
- LLM API calls beyond prompting with package contents (Condition B) or raw source (Condition A)

---

## Input packages

See [input_index.md](input_index.md) for the full list of input files and how to prepare them.

The primary reference input is `examples/sample_bracket.FCStd` converted via
`aieng convert examples/sample_bracket.FCStd --out sample_bracket.aieng`. The resulting
package includes feature graph, object registry, coverage categories, completeness report,
and README_FOR_AI.md.

---

## Questions

See [questions.md](questions.md) for the full question set across all four tracks.

---

## Scoring rubric

See [scoring_rubric.md](scoring_rubric.md) for the per-dimension 0/1/2 criteria.

---

## Recording results

Use [result_template.md](result_template.md) to record a benchmark run.
Save structured results as JSON under `benchmarks/ai_usefulness/results/` following
the schema in [results.schema.json](results.schema.json).

---

## Files in this directory

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `questions.md` | Full question sets for all four tracks |
| `scoring_rubric.md` | Per-dimension 0/1/2 scoring criteria |
| `expected_observations.md` | Canonical expected behaviors for well-performing AI |
| `input_index.md` | Input files for Conditions A and B, preparation instructions |
| `result_template.md` | Template for recording a benchmark run |
| `results.schema.json` | JSON schema for machine-readable result records |
| `results/` | Recorded benchmark runs (none yet) |

---

## Phase 21B — Recording the first run

The run-record structure for Phase 21B is in place. For complete step-by-step
instructions, see [HOWTO_RUN.md](HOWTO_RUN.md).

**Quick summary:**

1. Copy `results/run_record_template.json` to `results/run_YYYYMMDDTHHMMSSZ.json`.
2. Run Condition A (fresh session, raw source only) and Condition B (fresh session,
   `.aieng` package files) with the same model and settings.
3. Score both sessions using `scoring_rubric.md`.
4. Fill in the result JSON, validate against `results.schema.json`, and commit.

**Important:** One run on one scenario is not sufficient for broad claims. See the
"One-scenario limitation" section in [HOWTO_RUN.md](HOWTO_RUN.md).

---

## Running a benchmark scenario manually

### Phase 21A — Sample bracket CAD understanding

The first complete scenario is in
`benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/`.

**Step 1 — Validate the scenario files**

```bash
python scripts/validate_benchmark_scenario.py \
    benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding
```

All required files should pass. This does not call any AI APIs.

**Step 2 — Generate the Condition B package** (requires the `aieng` CLI)

```bash
aieng convert examples/sample_bracket.FCStd \
    --out benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng
```

Or validate the package once generated:

```bash
python scripts/validate_benchmark_scenario.py \
    benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding \
    --validate-package
```

**Step 3 — Conduct Condition A session**

Open a fresh AI session. Provide the contents of `condition_a.md` as the sole
input. Ask all five questions from `questions.md` in order. Record answers.

**Step 4 — Conduct Condition B session**

Open a second fresh AI session (same model, same version). Extract
`condition_b.aieng` and provide the files listed under "Required" in
`condition_b_index.md`. Ask the same five questions. Record answers.

**Step 5 — Score both sessions**

Use `scoring_rubric.md` and `expected_scoring.md` to score each dimension.
Record structured results as JSON following `results.schema.json` and save
under `results/`. Use `example_result.json` as a formatting reference.

**Step 6 — Compute delta**

```
delta = condition_b_scores.total_score - condition_a_scores.total_score
```

A delta of +5 or higher on this scenario is a strong signal that `.aieng`
meaningfully improves AI performance for this model class. See `expected_scoring.md`
for dimension-by-dimension expected ranges.

---

## Scenarios

| Scenario | Track | Fixture |
|----------|-------|---------|
| [`scenarios/sample_bracket_cad_understanding/`](scenarios/sample_bracket_cad_understanding/) | A — CAD Understanding | `examples/sample_bracket.FCStd` |

---

## Relation to the project thesis

`.aieng` is a **CAD/CAE-to-AI semantic conversion format**. This benchmark tests the
operational claim:

> A general AI given a structured `.aieng` package should produce more accurate,
> more grounded, and more honest engineering understanding than the same AI given
> only the raw CAD/CAE source — without calling any external tools, without
> fabricating engineering evidence, and without inventing missing information.

The benchmark measures whether structured, explicit, auditable engineering state
actually improves AI task performance. It does not test `.aieng` automation
capabilities, because `.aieng` does not have any.
