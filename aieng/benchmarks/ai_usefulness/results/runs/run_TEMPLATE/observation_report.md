# Observation Report

**TEMPLATE — replace all FILL_IN markers with actual observations after the run.**

This report captures qualitative observations about the benchmark run. It supplements
the machine-readable `result.json`. Write it after scoring is complete.

Do not generalize beyond this specific model and scenario run.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | FILL_IN |
| scenario | `sample_bracket_cad_understanding` (Track A) |
| model | FILL_IN |
| provider | FILL_IN |
| run date | FILL_IN |
| scorer | FILL_IN |
| delta (B − A total) | FILL_IN |

---

## Summary

FILL_IN — one to three sentences describing what this run showed. State the delta and
whether it was in the expected range from `expected_scoring.md`. Do not claim general
conclusions.

Example placeholder structure (replace entirely):
> *"Model X on scenario sample_bracket_cad_understanding produced a delta of +N.
> Condition B improved [dimensions] compared with Condition A. [One specific observation
> about what drove the improvement or what was unexpected.]*"

---

## What Condition A got right

FILL_IN — brief notes on dimensions where raw Document.xml input alone was sufficient
for a correct or partially correct answer.

*(If nothing: "Condition A produced no correct answers on this run." — but explain why.)*

---

## What Condition B improved

FILL_IN — which dimensions improved and what specific `.aieng` resources drove the
improvement (e.g. coverage_categories, feature IDs, uncertainty_note).

*(If nothing improved: document that and note possible explanations.)*

---

## Key delta drivers

FILL_IN — which specific package resources (e.g. `conversion_manifest.json`
coverage_categories, `feature_graph.json` feature IDs and confidence values,
`object_registry.json`) contributed most to the improvement or were not used by the AI.

---

## Unexpected behaviors

FILL_IN — any cases where the AI's behavior was surprising in either condition:
- Hallucinations in Condition B despite explicit missingness records
- Condition A outperforming expectations
- Questions where both conditions scored equally (and why)
- AI ignoring specific package resources

*(If none: "No unexpected behaviors observed.")*

---

## Failure modes

FILL_IN — cases where Condition B did not improve or performed worse than Condition A,
with notes on possible causes (e.g. confusing resource structure, over-reliance on
specific field names).

*(If none: "No regressions observed in Condition B.")*

---

## Run limitations

FILL_IN — known limitations of this specific run, such as:
- Temperature setting unavailable
- System prompt differed from intended
- Evaluator uncertainty on specific scoring calls
- Session interruption or restart
- Other caveats

*(If none: "No limitations beyond the standard single-scenario caveat.")*

---

## One-scenario limitation

This report covers one run of one scenario with one model. The results should not be
used to claim that `.aieng` generally improves AI performance on engineering tasks.
Multiple scenarios, models, and evaluators are required before drawing broad conclusions.

FILL_IN — any additional limitations specific to this run.
