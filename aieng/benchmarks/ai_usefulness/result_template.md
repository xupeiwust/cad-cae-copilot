# AI Usefulness Benchmark Result Template

Copy this template to `benchmarks/ai_usefulness/results/run_YYYYMMDDTHHMMSSZ.md`
and fill it in after completing a benchmark run.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | `run_YYYYMMDDTHHMMSSZ` |
| timestamp_utc | `YYYYMMDDTHHMMSSZ` |
| benchmark_scenario | `ai_usefulness_v1` |
| track | (A / B / C / D) |
| question_set_path | `benchmarks/ai_usefulness/questions.md` |
| rubric_path | `benchmarks/ai_usefulness/scoring_rubric.md` |
| evaluator | (name or team) |
| provider | (e.g. Anthropic, OpenAI, Google) |
| model | (e.g. claude-sonnet-4-6, gpt-4o) |
| package_used | (path to `.aieng` package used in Condition B) |
| raw_source_used | (path to raw source file used in Condition A) |

---

## Excluded capabilities (confirm all were excluded in both conditions)

- [ ] MCP tool calls
- [ ] RAG or retrieval augmentation
- [ ] Skills, plugins, or LLM fine-tuning
- [ ] External CAD tool calls
- [ ] External CAE tool calls
- [ ] Solver execution or result generation
- [ ] LLM API calls beyond prompting with designated input files
- [ ] In Condition A: `.aieng` package resources excluded
- [ ] In Condition B: raw source files excluded

---

## Condition A input files provided

- [ ] FCStd Document.xml excerpt / STEP text / solver deck text
- Other (list):

## Condition B input files provided

- [ ] `README_FOR_AI.md`
- [ ] `manifest.json`
- [ ] `provenance/conversion_manifest.json`
- [ ] `validation/completeness_report.json`
- [ ] `graph/feature_graph.json`
- [ ] `objects/object_registry.json`
- [ ] `simulation/setup.yaml`
- [ ] `simulation/cae_mapping.json`
- [ ] `task/external_tool_requirements.json`
- Other (list):

---

## Dimension scores

| Dimension | Condition A | Condition B | Δ (B − A) |
|-----------|:-----------:|:-----------:|:---------:|
| `geometry_understanding_score` (0–2) | | | |
| `feature_identification_score` (0–2) | | | |
| `referenceability_score` (0–2) | | | |
| `missingness_honesty_score` (0–2) | | | |
| `preprocessing_readiness_score` (0–2, Track C only) | | | |
| `hallucination_penalty` (−1/instance) | | | |
| `task_success_score` (0/1) | | | |
| **Total** | | | |

---

## Hallucination instances

### Condition A

| # | Fabricated claim | Category | Score impact |
|---|-----------------|----------|-------------|
| 1 | | | −1 |

### Condition B

| # | Fabricated claim | Category | Score impact |
|---|-----------------|----------|-------------|
| (none expected) | | | |

---

## Per-question notes

### Track _ — Question 1

**Condition A answer summary:**
> *(summarize or quote key claims)*

**Condition B answer summary:**
> *(summarize or quote key claims)*

**Observations:**
- [ ] Condition B cited specific resource paths/IDs
- [ ] Condition B correctly reported missing/unsupported categories
- [ ] Condition B avoided hallucination of missing data
- [ ] Delta positive for this dimension: ___

---

*(Repeat for each question.)*

---

## Summary observations

### What Condition A got right
*(Brief summary — where raw source alone was sufficient for correct reasoning)*

### What Condition B improved
*(Where `.aieng` package structure provided additional grounding or honesty)*

### Key delta drivers
*(Which specific `.aieng` resources — coverage_categories, feature graph, readiness report, etc. — most improved AI responses)*

### Failure modes observed
*(Any cases where Condition B did not improve, or introduced confusion)*

---

## Raw responses

### Condition A

*(Paste the full AI response for Condition A here, or link to a file.)*

---

### Condition B

*(Paste the full AI response for Condition B here, or link to a file.)*

---

## Evaluator notes

*(Any additional notes, anomalies, or follow-up questions)*
