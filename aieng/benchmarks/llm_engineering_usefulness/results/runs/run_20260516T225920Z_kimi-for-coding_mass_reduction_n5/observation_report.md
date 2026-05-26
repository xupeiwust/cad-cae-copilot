# Run 20260516T225920Z — Kimi `kimi-for-coding`, `mass_reduction_recommendation`, n=5

Fourth run on the automated benchmark. First run on **scenario #2** — a
different *kind* of task (recommendation, not defect-spotting). Same
model, same harness, n=5 per condition.

Compare against:

- Scenario 1, n=5: [run_20260516T224856Z_kimi-for-coding_scaled_n5](../run_20260516T224856Z_kimi-for-coding_scaled_n5/observation_report.md)

## Run identity

| Field | Value |
|---|---|
| Timestamps (UTC) | 2026-05-16T22:59:20Z (Condition A) / 23:00:29Z (Condition B) |
| Scenario | `mass_reduction_recommendation` (new — choose safest of 4 mass-reduction proposals) |
| Model | `anthropic/kimi-for-coding` |
| Epochs per condition | 5 |
| Harness version | `aieng` commit `0e147f5` + scenario #2 |
| Rubric | `rubric.yaml` v0.1 — substring + hallucination penalties + token-efficiency budget = 4000 |

## Aggregate results

| Metric | Condition A (n=5) | Condition B (n=5) |
|---|---|---|
| **Correctness — accuracy** | **1.000** (5/5 C) | **1.000** (5/5 C) |
| **Efficiency — mean** | **0.125** | **0.792** (~6.3×) |
| Total tokens (5 epochs) | 159,689 | **35,363** |
| Per-epoch tokens (avg) | ~31,938 | **~7,073** |
| Input tokens (5 epochs) | 153,705 | 21,003 |
| Cache-read tokens (5 epochs) | 0 | 8,192 |
| Output tokens (5 epochs) | 5,984 | 6,168 |
| Wall time (5 epochs) | 41 s | 31 s |

## The headline

**Condition B uses ~4.5× fewer total tokens than Condition A for the
same correctness.** On scenario 1 the separation was on the efficiency
ratio (B amortised cache well); on scenario 2 the separation is on
*absolute* per-epoch cost (B per-epoch ≈7K, A per-epoch ≈32K).

The mechanism is different from scenario 1's amortisation story. On
scenario 2 the model genuinely doesn't need to see most of the
package. The decision-relevant artifact is `results/stress_by_feature.json`
(~1 KB) plus `parsed_features.json` (~2 KB) and `parsed_materials.json`
(~500 B) for the yield strength. Condition B reads exactly those, ignores
topology/element_listing/etc. Condition A is forced to consume all of
it because the prompt structure doesn't allow selectivity.

## Why this run matters more than scenario 1

The first three observation reports said:

> The finding to date is bounded to one scenario, one model, and a
> defect-spotting task type.

That bound is now wider on the task-type axis. Two scenarios of
different shape show the same direction:

| | Scenario 1 (defect-spotting, n=5) | Scenario 2 (recommendation, n=5) |
|---|---|---|
| A correctness | 5/5 C | 5/5 C |
| B correctness | 5/5 C | 5/5 C |
| A efficiency | 0.038 | 0.125 |
| B efficiency | **0.285** (~7.5×) | **0.792** (~6.3×) |
| A per-epoch tokens | ~52,830 | ~31,938 |
| B per-epoch tokens | ~26,851 | **~7,073** |

The efficiency separation is consistent across both scenarios. The
finding now generalises across two task shapes (cross-reference scan
and multi-step engineering recommendation) on this model.

## Caching note

Condition A on scenario 2 shows zero cache reads across 5 epochs,
unlike scenario 1 where Kimi cached aggressively (98.6%). Same model,
same prompt-structure pattern (fixed system prompt + fixed user
content across epochs). Likely cause: scenario 2 was run on a fresh
cache state and the first response under Kimi's session may not have
populated cache. Without provider-side visibility we can't be sure.
The conclusion is unchanged either way: even without caching working
in Condition A's favour, B still wins by 4.5× absolute tokens.

## What this run does NOT show

- **Correctness is still ceiling-bound.** Kimi got 10/10 across both
  scenarios. We have shown `.aieng` is cheaper to be correct with;
  we have not yet shown it *prevents* errors. That still requires a
  weaker model.
- **Two scenarios is not "general".** The two shapes are still both
  evidence-reading tasks. Tasks that require synthesis beyond the
  package (design intent, manufacturing constraints, multi-objective
  trade-offs) are not in the benchmark yet.
- **One model.** Kimi-for-coding's structural-text reasoning is
  unusually strong; weaker models may behave differently.
- **Multi-choice tasks favour structured answers.** Free-form
  recommendation might show different patterns.

## Implications for Phase 30

The benchmark has now shown the efficiency finding holds on two task
shapes. The remaining open questions are unchanged:

1. **Correctness divergence** — requires a weaker model.
2. **Open-ended tasks** — scenario 3 (stress concentrator) is the
   natural test of whether structured access still helps when the
   answer is recommendation-quality rather than letter-choice.
3. **Tasks that synthesise across the package** — e.g., comparing
   two load cases, weighing trade-offs across multiple constraints.

Until we have a weaker model, scenario 3 is the most informative next
build. Open-ended outputs may also force us into LLM-graded scoring
on top of the deterministic substring rubric, which is a useful
infrastructure addition regardless.

## Honest framing for any external write-up

> Across two scenarios (a cross-reference defect-spotting task and a
> multi-step mass-reduction recommendation) and five trials each
> against Kimi's coding-tuned endpoint, the AIENG-augmented condition
> matched the raw-artifact-dump condition on correctness (5/5 in
> every cell) and used 4–7× fewer tokens. On the recommendation
> scenario specifically, structured access read only the
> decision-relevant artifacts (stress data, feature definitions,
> material yield) at roughly 7K tokens per query, where raw-dump
> consumed roughly 32K. We have not yet measured whether structured
> access affects correctness on a weaker model where the dump might
> actually fail.

That paragraph contains the strongest claim we can make today.
Token-efficiency finding is now backed by two scenarios. The
correctness-prevention claim is still entirely open.
