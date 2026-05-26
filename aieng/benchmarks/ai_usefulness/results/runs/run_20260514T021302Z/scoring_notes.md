# Scoring Notes

Score Condition A completely before looking at Condition B answers, and vice versa.
Use `scoring_rubric.md` for the 0/1/2 criteria. Use `expected_scoring.md` for
dimension-by-dimension expected ranges.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | run_20260514T021302Z |
| scorer | Claude Code (AI evaluator) |
| scoring date | 2026-05-14 |
| answers source | `condition_a_answers.md` and `condition_b_answers.md` in this directory |

---

## Condition A scoring

*Score Condition A before reading Condition B answers.*

### Q1 — Feature inventory

**Dimension: `feature_identification_score`**
- Evidence cited by AI: Cited XML `Object` elements with `type`, `name`, and `id` attributes; also cited `Float` property values for dimensions.
- Cited specific IDs or confidence values: no — Document.xml has no `recognition.confidence` or `uncertainty_note` fields.
- Score awarded: 1
- Rationale: AI correctly identified all 4 objects and their FreeCAD types from the raw XML. It did not invent feature classifications, but it also could not cite structured feature IDs or confidence values because those do not exist in the raw source. This matches the rubric's "1 = lists features from the input without citing specific IDs, types, recognition confidence, or uncertainty notes."

**Hallucination check:**
- Fabricated claims: None observed.

---

### Q2 — Mounting holes

**Dimension: `feature_identification_score`** (continuation)
- Evidence cited by AI: Cited `PartDesign::Hole` type strings and `Diameter`/`Depth` property values from the XML.
- Score contribution noted: Already counted in Q1; no additional feature identification score change.
- Additional hallucination check: AI correctly noted uncertainty about location, orientation, and whether holes actually cut through the plate. No fabricated claims.

---

### Q3 — Available geometry

**Dimension: `geometry_understanding_score`**
- What AI said about geometry availability: Correctly listed available numeric parameters (Length, Width, Height, Diameter, Depth) and noted that placement, orientation, sketch references, B-rep data, and STEP geometry are missing.
- Cited coverage_categories or parameter_source: no — Document.xml does not contain `coverage_categories` or `parameter_source` fields.
- Score awarded: 1
- Rationale: AI correctly distinguished available numeric properties from missing geometric information, but could not cite structured coverage status because none exists in the raw XML. It did not explicitly distinguish "parameter values" from "real geometry," which is the ceiling for Condition A per `expected_scoring.md`.

---

### Q4 — Explicit missingness

**Dimension: `missingness_honesty_score`**
- What AI reported as missing: Noted that `<Missing>`, `<Unsupported>`, and `<Uncertain>` tags in the XML are empty. Stated "no explicit missingness record in the input." Also listed implicitly missing items (placements, units, material, constraints, full geometry).
- Cited coverage_categories status values: N/A in Cond A
- Cited specific missing_items text: N/A in Cond A
- Score awarded: 1
- Rationale: The AI was unusually explicit for Condition A — it not only stated that no explicit missingness record exists, but also enumerated implicitly missing items. This exceeds the expected range of 0 for Condition A, but the rubric rewards honest, grounded reporting. A score of 1 reflects that the AI spontaneously noted missing information even without structured prompts.

---

### Q5 — FEM preprocessing readiness

**Dimension: `task_success_score`** (primary) + **`missingness_honesty_score`** (secondary)
- Did AI enumerate available vs. missing inputs: yes — produced detailed tables of present and missing FEM-relevant information.
- Did AI correctly state that mesh/solver require external tools: yes — stated "not ready for FEM solving" and listed 12 external steps.
- Score awarded (task_success): 1
- Score contribution to missingness: Already counted in Q4.

---

### Condition A — dimension summary

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| `geometry_understanding_score` | 1 | Correctly listed available parameters and missing geometry, but could not cite structured coverage status. |
| `feature_identification_score` | 1 | Correctly identified 4 objects and FreeCAD types from XML; no IDs or confidence values available to cite. |
| `referenceability_score` | 0 | Used natural-language names only; Document.xml has no stable `@aieng[...]`-resolvable IDs. |
| `missingness_honesty_score` | 1 | Explicitly stated no missingness record exists and enumerated implicitly missing items. |
| `hallucination_penalty` | 0 | No fabricated claims observed. |
| `task_success_score` | 1 | Produced a useful, substantively correct FEM readiness assessment. |
| **Total** | **4** | |

### Condition A — hallucination instances

None observed.

---

## Condition B scoring

*Score Condition B independently — do not adjust based on Condition A scores.*

### Q1 — Feature inventory

**Dimension: `feature_identification_score`**
- Cited feature IDs (feat_plate, feat_mountinghole_1, etc.): yes — referenced `feat_plate`, `feat_mountinghole_1`, `feat_mountinghole_2`, and `feat_flange_top`.
- Cited recognition.confidence or uncertainty_note: yes — cited `freecad_name_heuristic`, `medium confidence`, and uncertainty notes for each feature candidate.
- Score awarded: 2
- Rationale: AI cited specific feature IDs, their inferred types, the recognition method (`freecad_name_heuristic`), confidence level, and explicit uncertainty notes. Correctly labeled all types as heuristic candidates rather than confirmed truth.

**Dimension: `referenceability_score`** (assessed across all answers)
- Consistently used feat_* and obj_* IDs: yes — used `feat_plate`, `feat_mountinghole_1`, `feat_mountinghole_2`, `feat_flange_top`.
- Cited resource paths by name: yes — referenced `feature_graph.json`, `conversion_manifest.json`, `object_registry.json`, and `completeness_report.json`.

---

### Q2 — Mounting holes

**Dimension: `feature_identification_score`** (continuation)
- Evidence cited (feat_mountinghole_1, feat_mountinghole_2, recognition.method): yes — cited feature graph classifications and conversion manifest uncertainty notes.
- Score contribution noted: Already counted in Q1.

---

### Q3 — Available geometry

**Dimension: `geometry_understanding_score`**
- Cited coverage_categories geometry/topology: yes — explicitly referenced `geometry: missing` and `topology: missing` from the conversion manifest.
- Cited specific status values (missing / partial): yes — cited `real_geometry_extraction: false`, missing `geometry/source.step`, missing `geometry/normalized.step`, missing `geometry/topology_map.json`, missing `graph/aag.json`.
- Score awarded: 2
- Rationale: AI directly cited `coverage_categories` and the completeness report, distinguishing available parameter proposals from missing geometry and topology. No unsupported claims.

---

### Q4 — Explicit missingness

**Dimension: `missingness_honesty_score`**
- Cited coverage_categories entries with status: yes — listed 23 distinct missing/unsupported categories with their explicit records from the conversion manifest and completeness report.
- Listed specific missing_items text: yes — quoted specific missing file paths (`geometry/source.step`, `simulation/setup.yaml`, `results/evidence_index.json`, etc.) and uncertainty notes for each feature.
- Avoided fabricating missing data: yes — did not invent any missing items; all entries are traceable to the provided resources.
- Score awarded: 2
- Rationale: AI produced an exhaustive, structured missingness inventory grounded in specific resource paths and field names. This is the benchmark's highest-impact dimension and Condition B scored perfectly on it.

---

### Q5 — FEM preprocessing readiness

**Dimension: `task_success_score`** + **`missingness_honesty_score`**
- Enumerated available vs. missing inputs from coverage_categories: yes — tables explicitly map FEM-relevant items to their availability status, citing `completeness_report.json` and `conversion_manifest.json`.
- Correctly named external steps (mesh generation, solver execution): yes — listed 12 external steps including STEP export, topology extraction, mesh generation, solver deck creation, and evidence recording.
- Avoided claiming .aieng runs the solver: yes — explicitly stated "the converter itself cannot regenerate geometry" and "no solver, mesher, optimizer, or CAD edit was executed."
- Score awarded (task_success): 1

---

### Condition B — dimension summary

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| `geometry_understanding_score` | 2 | Cited `coverage_categories` geometry/topology status and specific missing file paths. |
| `feature_identification_score` | 2 | Cited `feat_*` IDs, `recognition.method`, `confidence`, and `uncertainty_note` for each feature. |
| `referenceability_score` | 2 | Consistently used `feat_*` IDs and named resource paths (`feature_graph.json`, `conversion_manifest.json`). |
| `missingness_honesty_score` | 2 | Exhaustively listed 23 missing/unsupported categories with specific source citations. |
| `hallucination_penalty` | 0 | No fabricated claims observed. |
| `task_success_score` | 1 | Produced a complete, bounded FEM readiness assessment with all missing inputs enumerated. |
| **Total** | **9** | |

### Condition B — hallucination instances

None observed.

---

## Delta summary

| Dimension | Cond A | Cond B | Δ (B − A) |
|-----------|:------:|:------:|:---------:|
| `geometry_understanding_score` | 1 | 2 | +1 |
| `feature_identification_score` | 1 | 2 | +1 |
| `referenceability_score` | 0 | 2 | +2 |
| `missingness_honesty_score` | 1 | 2 | +1 |
| `hallucination_penalty` | 0 | 0 | 0 |
| `task_success_score` | 1 | 1 | 0 |
| **Total** | **4** | **9** | **+5** |
