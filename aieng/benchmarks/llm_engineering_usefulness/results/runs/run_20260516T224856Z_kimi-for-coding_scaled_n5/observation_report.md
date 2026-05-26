# Run 20260516T224856Z — Kimi `kimi-for-coding`, scaled scenario, 5 epochs

Third run on `diagnose_broken_cae_setup`. Multi-epoch variance probe on the
scaled scenario. Compare against:

- [run_20260516T222309Z_kimi-for-coding](../run_20260516T222309Z_kimi-for-coding/observation_report.md) — single-epoch, small fixture (run 1)
- [run_20260516T224312Z_kimi-for-coding_scaled](../run_20260516T224312Z_kimi-for-coding_scaled/observation_report.md) — single-epoch, scaled fixture (run 2)

Still one *model* and one *scenario*. n=5 per condition, not statistical
infinity. Treat as field notes with light variance evidence, not as
generalised claims.

## Run identity

| Field | Value |
|---|---|
| Timestamps (UTC) | 2026-05-16T22:48:56Z (Condition A) / 22:49:39Z (Condition B) |
| Scenario | `diagnose_broken_cae_setup` (scaled — 14 artifacts, ~158 KB) |
| Model | `anthropic/kimi-for-coding` |
| Epochs per condition | 5 |
| Harness version | `aieng` commit `3188c20` (Phase 30 with both rubric axes, scaled fixture, stale-fixture fix) |
| Rubric | `rubric.yaml` v0.2 — correctness verdict + token-efficiency axis @ 2,000-token budget |

## Aggregate results

| Metric | Condition A (n=5) | Condition B (n=5) |
|---|---|---|
| **Correctness — accuracy** | **1.000** (5/5 C) | **1.000** (5/5 C) |
| **Efficiency — mean** | **0.038** | **0.285** |
| Total tokens (5 epochs) | 264,150 | 134,257 |
| Per-epoch tokens (avg) | ~52,830 | ~26,851 |
| Input tokens (5 epochs) | 0 | 50,829 |
| Cache-read tokens (5 epochs) | 260,350 | 76,707 |
| Output tokens (5 epochs) | 3,800 | 6,721 |
| Wall time (5 epochs) | 19 s | 34 s |

## What this multi-epoch run shows

1. **Correctness variance is zero on this scenario for this model.** 5/5
   trials produced `C` in both conditions. Kimi-for-coding's haystack-needle
   ability on 52K tokens of structured-JSON noise is highly reliable.

2. **The efficiency separation is wider with more trials.** Single-trial
   showed B 3× better than A (0.114 vs 0.038). Five-trial mean shows
   B ~7.5× better (0.285 vs 0.038). Two effects compound:

   - Inspect_ai's prompt caching is highly effective on Condition A's
     fixed-prompt structure: 260,350 of 264,150 tokens (98.6%) were
     cache reads. That doesn't help Condition A's efficiency *ratio*
     (the rubric sums all tokens including cache reads) but it does
     keep cost predictable.
   - Condition B's per-epoch token use *drops* across epochs as the
     cache warms up, since system prompt + tool descriptions + early
     tool-call patterns get cached. The agentic loop is amortising
     its overhead across epochs in a way Condition A's monolithic
     prompt does not.

3. **The wider implication.** Condition A's cost is essentially fixed
   per query — you pay for the dump every time. Condition B's cost
   has a one-time setup component (system prompt, tool descriptions)
   amortised across queries plus a per-query variable component
   (which artifacts the model decides to read). On any workload with
   repeated queries against the same package, B's amortisation
   compounds. This is a property worth surfacing in product framing.

## What this run does NOT show

- **Still no correctness differentiation.** The benchmark cannot say
  whether `.aieng` *prevents* errors — only that it *costs less* when
  errors are already absent. The next experiment must use a model that
  actually fails Condition A.
- **Still one model.** Kimi-for-coding's structural-text reasoning is
  unusually strong; weaker models likely show different shapes.
- **Caching effects entangle the variance estimate.** The first sample
  of a 5-epoch run differs in cost from the fifth because of cache
  warmup. The reported mean is a fair aggregate measurement but the
  per-sample distribution is not uniform.

## Confidence interval (informal)

With n=5, Condition A's efficiency mean (0.038) sits within a tight
band — the per-sample tokens were all near 52,830, ratios near 0.038.
Condition B's mean (0.285) reflects more spread because some epochs
benefited from cache warmup. A safe statement: **on this model and
this scenario, structured access uses substantially fewer tokens than
raw dump (rough lower bound: 5× separation; observed: 7.5×; the upper
bound depends on cache warmup behaviour the rubric does not control
for).**

We will not improve confidence further by spending more epochs on the
same scenario × model combination. The variance is small enough that
the finding is real. What we *don't* know about generalisation will
not be reduced by more Kimi runs.

## What this run changes about Phase 30

Two follow-ups remain. In order:

1. **Multi-model probe — same scenario, weaker model.** Pick a smaller
   model (`anthropic/claude-haiku-4-5`, `openai/gpt-4o-mini` if you
   have the keys, or a smaller Kimi tier) and run both conditions.
   The interesting outcome is **correctness divergence** — if the
   weaker model fails Condition A on the 52K-token dump but succeeds
   Condition B with selective reads, the benchmark gains a
   correctness-axis finding. That converts "evidence layer saves
   tokens" into "evidence layer prevents wrong answers" — the much
   stronger product claim.

2. **Then scenario #2 (mass reduction).** A more open-ended task whose
   ground truth is a recommendation rather than a defect name. Tests
   whether the benchmark generalises beyond defect-spotting.

Scenarios #3 and #4 keep waiting.

## Honest framing for any external write-up

> Across five trials per condition against Kimi's coding-tuned
> endpoint, both raw-artifact and AIENG-augmented conditions produced
> correct diagnoses on every trial of a deliberately-broken CAE setup
> (~158 KB package). Aggregate token-efficiency was roughly 7.5×
> higher for the AIENG condition (mean 0.285 vs 0.038 against a
> 2,000-token budget). Some of this advantage is amortisation across
> epochs from inspect_ai's prompt caching; per-query cost reflects
> both structural selectivity and cache warmup. The findings to date
> remain bounded to one scenario, one model, and a defect-spotting
> task type; we have not yet measured whether `.aieng` access affects
> correctness when correctness is not already saturated.

That is the most honest paragraph we can write today. The finding is
real and now backed by variance. The generalisation question is open.
