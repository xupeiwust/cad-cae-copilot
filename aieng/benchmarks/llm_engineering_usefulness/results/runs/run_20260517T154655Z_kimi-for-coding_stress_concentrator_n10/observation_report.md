# Run 20260517T154655Z — Kimi `kimi-for-coding`, scenario 3, n=10, T=0

Fifth run on the automated benchmark. First run on **scenario 3**
(stress concentrator recommendation — open-ended engineering judgement).

## Run identity

| Field | Value |
|---|---|
| Timestamps (UTC) | 2026-05-17T15:46:55Z (Condition A) / 15:48:02Z (Condition B) |
| Scenario | `stress_concentrator_recommendation` |
| Model | `anthropic/kimi-for-coding` |
| Epochs per condition | 10 |
| Temperature | 0 |
| Harness version | aieng commit at scenarios 3 + 4 source-add |
| Rubric | `rubric.yaml` v0.1 — 4-criterion substring + hallucination penalties + token-efficiency budget = 4000 |

## Aggregate results

| Metric | Condition A (n=10) | Condition B (n=10) |
|---|---|---|
| **Correctness — accuracy** | **1.000** | **1.000** |
| **Correctness — verdict distribution** | 10 C / 0 P / 0 I | 10 C / 0 P / 0 I |
| **Efficiency — mean** | 0.129 | **0.741** |
| **Efficiency — range** | 0.128 – 0.130 | 0.685 – 0.803 |
| Total tokens (10 epochs) | 309,883 | 87,824 |
| Per-epoch tokens (avg) | ~30,988 | **~8,782** |
| Input tokens | 299,880 | 46,638 |
| Cache-read tokens | 0 | 29,440 |
| Output tokens | 10,003 | 11,746 |
| Wall time | 50 s | 80 s |

## Per-trial verdicts

**Condition A (n=10):** C × 10. Every trial named `fillet_inner_corner`,
cited the 280 MPa / SF 1.25 numbers, proposed a fillet radius increase,
and acknowledged that re-analysis is required.

**Condition B (n=10):** C × 10. Same pattern of hits across trials —
all four criteria triggered in most trials.

## What this run shows

1. **No correctness divergence on this scenario.** Both conditions are at
   ceiling (10/10 C). The benchmark cannot distinguish A from B on
   correctness here.
2. **Efficiency separation persists.** Condition B used ~3.5× fewer
   absolute tokens and scored ~5.7× higher on the efficiency axis. The
   selective tool access reads `stress_by_feature.json` directly
   (~1.5 KB) plus `parsed_features.json` and `parsed_materials.json`,
   ignoring the bulk topology / element listing.
3. **Variance is very small across n=10 at temperature 0.** Efficiency
   ranges are narrow (A: 0.128–0.130; B: 0.685–0.803).

## What this run does NOT show

- **No correctness divergence.** This scenario is well within Kimi's
  capability on either prompt form. The benchmark has demonstrated the
  efficiency claim but not the prevent-errors claim on this scenario.
- One scenario, one model.
- Rubric is substring-based, so a stylistic outlier might score lower
  than its engineering content deserves.

## Honest framing

> On scenario 3 (stress concentrator recommendation), Kimi
> `kimi-for-coding` at n=10, temperature 0 produced correct
> recommendations in every trial in both conditions. The structured-tool
> condition used roughly 3.5× fewer tokens than the raw-dump condition
> while reaching the same verdict. Correctness divergence was **not**
> observed on this scenario.
