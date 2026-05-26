# Observation Report

This report captures qualitative observations about the benchmark run. It supplements
the machine-readable `result.json`. Write it after scoring is complete.

Do not generalize beyond this specific model and scenario run.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | run_20260514T021302Z |
| scenario | `sample_bracket_cad_understanding` (Track A) |
| model | unknown |
| provider | unknown |
| run date | 2026-05-14 |
| scorer | Claude Code (AI evaluator) |
| delta (B − A total) | +5 |

---

## Summary

This run on the sample bracket scenario produced a delta of +5 (Condition B: 9, Condition A: 4), which falls within the expected range of +5 to +7 from `expected_scoring.md`. The `.aieng` package enabled the AI to cite specific feature IDs, coverage category statuses, and missing item records that were inaccessible from raw Document.xml alone.

---

## What Condition A got right

Condition A produced partially correct answers on `geometry_understanding` and `feature_identification`. The AI correctly parsed the XML object list, identified `Part::Box` and `PartDesign::Hole` types, and extracted numeric parameter values (100x50x10 mm plate, 6 mm diameter holes). It also gave a useful FEM readiness assessment, scoring 1 on `task_success`. These results show that raw Document.xml contains enough metadata for basic object inventory and parameter listing.

---

## What Condition B improved

Condition B improved across four dimensions:

- **`geometry_understanding` (+1)**: The AI explicitly cited `coverage_categories` showing `geometry: missing` and `topology: missing`, and distinguished parameter proposals from real geometry — something it could only infer vaguely in Condition A.
- **`feature_identification` (+1)**: The AI cited `feat_*` IDs, `recognition.method: freecad_name_heuristic`, and `uncertainty_note` for each feature, correctly labeling them as heuristic candidates rather than confirmed truth.
- **`referenceability` (+2)**: The AI consistently used structured IDs (`feat_plate`, `feat_mountinghole_1`, etc.) and named specific resource paths (`feature_graph.json`, `conversion_manifest.json`). In Condition A it could only use natural-language names.
- **`missingness_honesty` (+1)**: The AI produced an exhaustive 23-item missingness inventory in Condition B versus a brief "no explicit missingness record" note in Condition A.

---

## Key delta drivers

The largest driver was **`conversion_manifest.json` → `coverage_categories`**, which gave the AI a structured checklist of what was missing. The AI used this to produce the detailed Q4 missingness table and to ground its Q3 geometry assessment.

The second key driver was **`graph/feature_graph.json`**, which provided stable `feat_*` IDs and explicit `recognition.confidence` / `uncertainty_note` fields. This enabled the AI to answer Q1 and Q2 with specific, citable identifiers rather than generic descriptions.

`provenance/completeness_report.json` also contributed by listing specific missing file paths (e.g., `geometry/source.step`, `simulation/setup.yaml`), which the AI incorporated into both Q4 and Q5.

---

## Unexpected behaviors

No unexpected behaviors observed. The AI in both conditions performed as expected: Condition A gave reasonable inferences from limited data, while Condition B leveraged the structured package resources effectively without hallucinating.

---

## Failure modes

No regressions observed in Condition B. The AI did not misinterpret any `.aieng` resources or claim capabilities the package does not have.

---

## Run limitations

- Model, provider, temperature, and system prompt were not recorded by the evaluator. These fields are marked "unknown" in the run record.
- This is a single run on a single minimal scenario (4 objects, no materials, no loads). Results should not be generalized to other model types or complexity levels.

---

## One-scenario limitation

This report covers one run of one scenario with one model. The results should not be
used to claim that `.aieng` generally improves AI performance on engineering tasks.
Multiple scenarios, models, and evaluators are required before drawing broad conclusions.

No additional limitations beyond the standard single-scenario caveat.
