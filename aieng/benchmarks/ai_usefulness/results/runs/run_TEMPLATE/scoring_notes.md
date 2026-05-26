# Scoring Notes

**TEMPLATE — replace all FILL_IN markers. Score each condition independently.**

Score Condition A completely before looking at Condition B answers, and vice versa.
Use `scoring_rubric.md` for the 0/1/2 criteria. Use `expected_scoring.md` for
dimension-by-dimension expected ranges.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | FILL_IN |
| scorer | FILL_IN (name or initials) |
| scoring date | FILL_IN |
| answers source | `condition_a_answers.md` and `condition_b_answers.md` in this directory |

---

## Condition A scoring

*Score Condition A before reading Condition B answers.*

### Q1 — Feature inventory

**Dimension: `feature_identification_score`**
- Evidence cited by AI: FILL_IN
- Cited specific IDs or confidence values: FILL_IN (yes / no)
- Score awarded: FILL_IN (0 / 1 / 2)
- Rationale: FILL_IN

**Hallucination check:**
- Fabricated claims: FILL_IN (none / list each)

---

### Q2 — Mounting holes

**Dimension: `feature_identification_score`** (continuation)
- Evidence cited by AI: FILL_IN
- Score contribution noted: FILL_IN
- Additional hallucination check: FILL_IN

---

### Q3 — Available geometry

**Dimension: `geometry_understanding_score`**
- What AI said about geometry availability: FILL_IN
- Cited coverage_categories or parameter_source: FILL_IN (yes / no)
- Score awarded: FILL_IN (0 / 1 / 2)
- Rationale: FILL_IN

---

### Q4 — Explicit missingness

**Dimension: `missingness_honesty_score`**
- What AI reported as missing: FILL_IN
- Cited coverage_categories status values: FILL_IN (yes / no / N/A in Cond A)
- Cited specific missing_items text: FILL_IN (yes / no / N/A in Cond A)
- Score awarded: FILL_IN (0 / 1 / 2)
- Rationale: FILL_IN

---

### Q5 — FEM preprocessing readiness

**Dimension: `task_success_score`** (primary) + **`missingness_honesty_score`** (secondary)
- Did AI enumerate available vs. missing inputs: FILL_IN (yes / partial / no)
- Did AI correctly state that mesh/solver require external tools: FILL_IN
- Score awarded (task_success): FILL_IN (0 / 1)
- Score contribution to missingness: FILL_IN

---

### Condition A — dimension summary

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| `geometry_understanding_score` | FILL_IN | FILL_IN |
| `feature_identification_score` | FILL_IN | FILL_IN |
| `referenceability_score` | FILL_IN | FILL_IN |
| `missingness_honesty_score` | FILL_IN | FILL_IN |
| `hallucination_penalty` | FILL_IN | FILL_IN |
| `task_success_score` | FILL_IN | FILL_IN |
| **Total** | **FILL_IN** | |

### Condition A — hallucination instances

| # | Fabricated claim (verbatim or paraphrase) | Dimension | Impact |
|---|------------------------------------------|-----------|--------|
| FILL_IN | FILL_IN | FILL_IN | −1 |

*(If none: write "None observed.")*

---

## Condition B scoring

*Score Condition B independently — do not adjust based on Condition A scores.*

### Q1 — Feature inventory

**Dimension: `feature_identification_score`**
- Cited feature IDs (feat_plate, feat_mountinghole_1, etc.): FILL_IN (yes / no / partial)
- Cited recognition.confidence or uncertainty_note: FILL_IN (yes / no)
- Score awarded: FILL_IN (0 / 1 / 2)
- Rationale: FILL_IN

**Dimension: `referenceability_score`** (assessed across all answers)
- Consistently used feat_* and obj_* IDs: FILL_IN (yes / partial / no)
- Cited resource paths by name: FILL_IN (yes / no)

---

### Q2 — Mounting holes

**Dimension: `feature_identification_score`** (continuation)
- Evidence cited (feat_mountinghole_1, feat_mountinghole_2, recognition.method): FILL_IN
- Score contribution noted: FILL_IN

---

### Q3 — Available geometry

**Dimension: `geometry_understanding_score`**
- Cited coverage_categories geometry/topology: FILL_IN (yes / no)
- Cited specific status values (missing / partial): FILL_IN
- Score awarded: FILL_IN (0 / 1 / 2)
- Rationale: FILL_IN

---

### Q4 — Explicit missingness

**Dimension: `missingness_honesty_score`**
- Cited coverage_categories entries with status: FILL_IN (yes / partial / no)
- Listed specific missing_items text: FILL_IN (yes / no)
- Avoided fabricating missing data: FILL_IN (yes / no)
- Score awarded: FILL_IN (0 / 1 / 2)
- Rationale: FILL_IN

---

### Q5 — FEM preprocessing readiness

**Dimension: `task_success_score`** + **`missingness_honesty_score`**
- Enumerated available vs. missing inputs from coverage_categories: FILL_IN
- Correctly named external steps (mesh generation, solver execution): FILL_IN
- Avoided claiming .aieng runs the solver: FILL_IN (yes / no)
- Score awarded (task_success): FILL_IN (0 / 1)

---

### Condition B — dimension summary

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| `geometry_understanding_score` | FILL_IN | FILL_IN |
| `feature_identification_score` | FILL_IN | FILL_IN |
| `referenceability_score` | FILL_IN | FILL_IN |
| `missingness_honesty_score` | FILL_IN | FILL_IN |
| `hallucination_penalty` | FILL_IN | FILL_IN |
| `task_success_score` | FILL_IN | FILL_IN |
| **Total** | **FILL_IN** | |

### Condition B — hallucination instances

| # | Fabricated claim (verbatim or paraphrase) | Dimension | Impact |
|---|------------------------------------------|-----------|--------|
| FILL_IN | FILL_IN | FILL_IN | −1 |

*(If none: write "None observed.")*

---

## Delta summary

| Dimension | Cond A | Cond B | Δ (B − A) |
|-----------|:------:|:------:|:---------:|
| `geometry_understanding_score` | FILL_IN | FILL_IN | FILL_IN |
| `feature_identification_score` | FILL_IN | FILL_IN | FILL_IN |
| `referenceability_score` | FILL_IN | FILL_IN | FILL_IN |
| `missingness_honesty_score` | FILL_IN | FILL_IN | FILL_IN |
| `hallucination_penalty` | FILL_IN | FILL_IN | FILL_IN |
| `task_success_score` | FILL_IN | FILL_IN | FILL_IN |
| **Total** | **FILL_IN** | **FILL_IN** | **FILL_IN** |
