# Benchmark Run Records

Each completed benchmark run lives in its own subdirectory named after the `run_id`:

```
runs/
  run_TEMPLATE/              ← copy this directory to start a new run
    condition_a_answers.md   ← paste raw AI responses from Condition A
    condition_b_answers.md   ← paste raw AI responses from Condition B
    scoring_notes.md         ← per-question and per-dimension scoring rationale
    observation_report.md    ← narrative observations and delta analysis
    result.json              ← machine-readable result (validates against results.schema.json)

  run_20260601T143022Z/      ← example of a completed run
    ...
```

No real runs have been recorded yet. `run_TEMPLATE/` is the template to copy.

---

## Workflow

This directory captures a manually-executed two-condition benchmark run. No automation
executes the AI sessions — a human evaluator conducts them and pastes results here.

**Step-by-step:**

1. **Run the benchmark sessions** following [`../../HOWTO_RUN.md`](../../HOWTO_RUN.md).
   Complete both Condition A and Condition B before filling in any files here.

2. **Copy the template directory:**

   ```bash
   cp -r benchmarks/ai_usefulness/results/runs/run_TEMPLATE \
         benchmarks/ai_usefulness/results/runs/run_YYYYMMDDTHHMMSSZ
   ```

   Replace `YYYYMMDDTHHMMSSZ` with the UTC datetime of your run.

3. **Paste raw answers** into `condition_a_answers.md` and `condition_b_answers.md`.
   Do not edit the AI's words — paste verbatim. Do not score while pasting.

4. **Score independently.** Fill in `scoring_notes.md` for Condition A first, then
   Condition B. Do not look at the other condition's scores while scoring either.

5. **Fill in `result.json`.** Replace every `FILL_IN` placeholder and zero-score
   sentinel with actual values. Validate:

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
       print('WARN  jsonschema not installed')
   "
   ```

6. **Write `observation_report.md`.** One to two paragraphs summarizing what the run
   showed. Do not generalize beyond this scenario and model.

7. **Commit the entire run subdirectory.**

---

## What does NOT belong here

- AI-generated answers that were not obtained from a real benchmark session
- Fabricated or estimated scores
- Conclusions that generalize beyond the specific model and scenario run
- Files from automated API calls (there should be none)

---

## One-scenario limitation

A single run on the sample bracket scenario is **one data point**. It tells you how
one specific AI model responded to one scenario once. It does not support claims about
`.aieng`'s general utility across models, scenario types, or evaluators.

See the "One-scenario limitation" section in [`../../HOWTO_RUN.md`](../../HOWTO_RUN.md).
