# How to Run an AI Usefulness Benchmark

This document gives step-by-step instructions for conducting a Phase 21 two-condition
benchmark run. Read it entirely before starting.

---

## What this benchmark is (and is not)

This benchmark measures whether a `.aieng` package improves AI understanding of
engineering models compared with providing raw CAD/CAE input. It is a **manual, human-
evaluated comparison**. The evaluator runs two AI sessions, scores both, and records the
delta.

**This benchmark does not:**

- Execute solvers, meshers, optimizers, or CAD edits.
- run automatically against a model.
- Prove general conclusions from a single scenario.
- Call any tools beyond prompting an AI with the designated input files.

A single benchmark run on a single scenario is **not sufficient for broad claims**. One
scenario + one model run = one data point. Conclusions about `.aieng`'s general utility
require multiple scenarios, multiple models, and multiple evaluators.

---

## Prerequisites

Before starting, confirm you have:

- [ ] The scenario directory (e.g. `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/`)
- [ ] A generated `condition_b.aieng` package for the scenario, or the ability to generate one
- [ ] Access to the AI model you will benchmark (same model for both conditions)
- [ ] The scenario's `questions.md` open for reference
- [ ] The `scoring_rubric.md` open for reference
- [ ] A copy of `benchmarks/ai_usefulness/results/run_record_template.json` renamed to
  `benchmarks/ai_usefulness/results/run_YYYYMMDDTHHMMSSZ.json` (fill in the actual UTC datetime)

**Validate the scenario first:**

```bash
python scripts/validate_benchmark_scenario.py \
    benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding \
    --validate-package
```

---

## Step 1 — Record model and session settings

Before either condition, record:

| Field | Value |
|-------|-------|
| Model | (e.g. `claude-sonnet-4-6`, `gpt-4o-2024-05-13`) |
| Provider | (e.g. Anthropic, OpenAI, Google) |
| API version or UI version | (e.g. API v1, Claude.ai web, 2026-04-15) |
| Temperature | (e.g. `1.0` / `default` / `unknown`) |
| Max tokens | (e.g. `4096` / `default` / `unknown`) |
| System prompt | (e.g. `none` / `"You are a helpful engineering assistant."` / paste verbatim) |
| Prompt version | (e.g. `questions.md @ git SHA abc1234`) |

If you cannot access temperature or sampling settings, record `unknown`. Do not omit
this field — it is required for run reproducibility.

---

## Step 2 — Prepare input files

### Condition A input

Condition A uses only the raw source input. For the sample bracket scenario:

- Use `condition_a.md` as the sole input.
- Do **not** provide any `.aieng` package resources.
- Do **not** mention that a `.aieng` package exists.

### Condition B input

Condition B uses the `.aieng` package contents listed in `condition_b_index.md`.

1. Generate the package if it does not exist:

   ```bash
   aieng convert examples/sample_bracket.FCStd \
       --out benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng
   ```

2. Extract the required files:

   ```bash
   python -c "
   import zipfile
   with zipfile.ZipFile('benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng') as z:
       z.extractall('benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b_contents/')
   print('Done')
   "
   ```

3. Provide **only** the files listed under "Required" in `condition_b_index.md`.
   Do **not** provide the raw FCStd, STEP, or `condition_a.md`.

---

## Step 3 — Prevent cross-condition leakage

**This is the most important protocol step.** Cross-condition leakage means information
from one condition appearing in the other, which invalidates the comparison.

Rules:

1. **Use a completely fresh AI session for each condition.** Start a new conversation
   thread with no prior context. If using an API, send no prior messages in the thread.
2. **Do not tell the AI it is being benchmarked** or that there is a second condition.
3. **Do not mention the other condition's input format** (e.g. do not say "you may also
   have a structured package" in Condition A, or "you previously saw only raw XML" in B).
4. **Do not reuse a chat thread.** Even summarizing or clearing the context is
   insufficient — start a new thread.
5. **Run Condition A first.** If you run Condition B first, you may unconsciously adjust
   your framing when you switch to Condition A. Order does not affect the AI (different
   sessions) but helps evaluator consistency.

---

## Step 4 — Conduct Condition A session

1. Open a fresh AI session with the target model.
2. Apply the same system prompt (or none) that you will use in Condition B.
3. Set temperature and max tokens to the same values you recorded in Step 1.
4. Provide `condition_a.md` as the **entire input** — either paste it into the user
   turn or attach it as a file, depending on the model's interface.
5. Ask each question from `questions.md` in order, in separate user turns.
   Ask them **verbatim** — do not paraphrase, reorder, or combine questions.
6. After each answer, move to the next question without offering hints, corrections,
   or rephrasing.
7. After all questions are asked, end the session. Save the full transcript.

---

## Step 5 — Conduct Condition B session

1. Open a **new**, completely separate AI session with the same model.
2. Apply the same system prompt and settings as Condition A.
3. Provide the Condition B files listed in `condition_b_index.md` (Required section) as
   the **entire input**. Do not include `condition_a.md`.
4. Ask the **same questions** from `questions.md` in the same order, verbatim.
5. After all questions are asked, end the session. Save the full transcript.

---

## Step 6 — Score both sessions

Open `scoring_rubric.md` and `expected_scoring.md` for the scenario.

For **each** of the seven dimensions, assign an integer score (0, 1, or 2 for most;
0 or 1 for `task_success_score`; ≤0 for `hallucination_penalty`) to **both conditions
independently**. Do not be influenced by the other condition's score when scoring either.

**Scoring process:**

1. Read the full transcript for Condition A without referring to the Condition B
   transcript. Score all dimensions for Condition A.
2. Read the full transcript for Condition B without referring to your Condition A scores
   (score it fresh). Score all dimensions for Condition B.
3. Compute `total_score` for each condition:
   ```
   total = geometry_understanding + feature_identification + referenceability
           + missingness_honesty + [preprocessing_readiness if Track C]
           + hallucination_penalty + task_success
   ```
4. Compute `delta = condition_b_scores.total_score - condition_a_scores.total_score`.

**For each hallucination instance**, record the fabricated claim, the dimension it
affects, and the score impact (−1). Be conservative — one coherent invented claim is
one instance, even if it contains multiple sub-values.

---

## Step 7 — Record results in a run directory

Each run is stored as a self-contained subdirectory under `results/runs/`. Copy the
template directory, rename it, then fill in each file.

**7a. Copy the template directory:**

```bash
cp -r benchmarks/ai_usefulness/results/runs/run_TEMPLATE \
      benchmarks/ai_usefulness/results/runs/run_YYYYMMDDTHHMMSSZ
```

Replace `YYYYMMDDTHHMMSSZ` with the UTC datetime of your run (e.g. `20260601T143022Z`).

**7b. Paste raw answers** into `condition_a_answers.md` and `condition_b_answers.md`.
Paste verbatim — do not summarize or correct. Replace all `FILL_IN` markers in the
metadata tables.

**7c. Fill in `scoring_notes.md`.** Record per-question scoring rationale, dimension
scores, and any hallucination instances. Score Condition A before looking at Condition B.

**7d. Fill in `result.json`.** Replace:

- `"run_00000000T000000Z"` with the actual `run_id` (matching the directory name)
- `"00000000T000000Z"` with the actual `timestamp_utc`
- All `"FILL_IN"` strings with actual values
- All zero scores with actual scored values
- Template warnings with any real run caveats

**7e. Validate `result.json`:**

```bash
python -c "
import json, sys
try:
    import jsonschema
    schema = json.loads(open('benchmarks/ai_usefulness/results.schema.json').read())
    result = json.loads(open('benchmarks/ai_usefulness/results/runs/run_YYYYMMDDTHHMMSSZ/result.json').read())
    v = jsonschema.Draft202012Validator(schema)
    errs = list(v.iter_errors(result))
    if errs:
        for e in errs: print('FAIL', e.message)
        sys.exit(1)
    print('PASS  schema valid')
except ImportError:
    print('WARN  jsonschema not installed — skipping schema check')
"
```

**7f. Write `observation_report.md`.** One to three paragraphs. State the delta and any
qualitative observations. Do not generalize beyond this model and scenario.

**7g. Commit the entire run directory.**

The run directory structure:

```
results/runs/run_YYYYMMDDTHHMMSSZ/
  condition_a_answers.md   ← verbatim AI responses from Condition A
  condition_b_answers.md   ← verbatim AI responses from Condition B
  scoring_notes.md         ← per-dimension scoring rationale
  result.json              ← machine-readable result (schema-validated)
  observation_report.md    ← narrative observations
```

---

## Step 8 — Interpret and document

After recording the result:

1. **Compute the delta** per dimension and in total (Condition B − Condition A).
2. **Check against expected ranges** in `expected_scoring.md` to see whether your
   run is in the expected range or if something unexpected occurred.
3. **Do not draw broad conclusions from one run.** A single run on the sample bracket
   scenario measures one AI model's response to one scenario once. It says nothing
   reliable about:
   - Other AI models
   - Other scenario types (assemblies, solver decks, large FEM models)
   - Different converter runs of the same part
   - Evaluator-independent reproducibility

4. Record your summary in the `summary` field and any limitations in `warnings`.
5. If you observed hallucinations in Condition B, note them specifically — they may
   indicate areas where the `.aieng` package was confusing rather than helpful.

---

## Session integrity checklist

Before submitting a result, confirm all of the following:

- [ ] Condition A and Condition B used completely separate AI sessions
- [ ] The same model, version, temperature, and system prompt were used in both
- [ ] No information from Condition B appeared in the Condition A session
- [ ] No information from Condition A appeared in the Condition B session
- [ ] All questions were asked verbatim from `questions.md`
- [ ] All questions were asked in both sessions
- [ ] Each condition was scored independently before comparing scores
- [ ] Hallucination instances are documented with the fabricated claim
- [ ] All `"FILL_IN"` placeholders have been replaced
- [ ] The result file validates against `results.schema.json`
- [ ] `warnings` records any known limitations of this run

---

## One-scenario limitation

**Read before drawing conclusions.**

The sample bracket scenario is a minimal fixture: 4 objects, no materials, no loads, no
simulation setup. It is designed to test the most basic `.aieng` coverage — object
registry, feature identification, and missingness reporting. It does not test:

- Assembly-level reasoning (multiple parts, mates, constraints)
- Material and load annotation extraction
- Solver deck understanding
- Large-model comprehension (hundreds of features)
- Reconstruction or parametric editing

A positive delta on the sample bracket means `.aieng` helped the AI understand a simple
bracket better than raw XML. It does **not** mean `.aieng` improves AI performance on
engineering tasks in general. One scenario is not enough for that claim.

Multiple scenarios covering different fixture types, tracks, and model complexity are
required before drawing conclusions about `.aieng`'s general utility.

---

## File naming convention

Result files use the run datetime (UTC) as the filename:

```
benchmarks/ai_usefulness/results/run_20260601T143022Z.json
```

The `run_id` field inside the file must match the filename:

```json
{
  "run_id": "run_20260601T143022Z",
  "timestamp_utc": "20260601T143022Z",
  ...
}
```
