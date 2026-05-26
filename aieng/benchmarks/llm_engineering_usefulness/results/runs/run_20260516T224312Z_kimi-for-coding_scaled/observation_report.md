# Run 20260516T224312Z — Kimi `kimi-for-coding`, scaled `diagnose_broken_cae_setup`

Second run of the same scenario after Phase 30's rubric and fixture
adjustments. The first run (small fixture, single-axis rubric) is in
[../run_20260516T222309Z_kimi-for-coding/](../run_20260516T222309Z_kimi-for-coding/observation_report.md);
**this report compares against that one to show the crossover**.

This is field notes for a single trial on a single scenario on a single
model. It is **not** a generalisable claim.

## Run identity

| Field | Value |
|---|---|
| Timestamp (UTC) | 2026-05-16T22:43:12Z (Condition A) / 22:44:03Z (Condition B) |
| Scenario | `diagnose_broken_cae_setup` (scaled — 14 artifacts, ~158 KB uncompressed) |
| Model | `anthropic/kimi-for-coding` |
| Epochs per condition | 1 |
| Harness version | `aieng` commit `a61a49b` (Phase 30 + token-efficiency axis + scaled fixture + stale-fixture fix) |
| Rubric | `rubric.yaml` v0.2 — correctness verdict + token-efficiency axis @ 2,000-token budget |

## Raw results

| Metric | Condition A | Condition B |
|---|---|---|
| **Correctness verdict** | `C` (accuracy 1.000) | `C` (accuracy 1.000) |
| **Efficiency ratio** | 0.038 | **0.114** (~3× better) |
| Total tokens | 52,952 | **38,214** (~28% fewer) |
| Input tokens | 52,070 | 18,171 |
| Output tokens | 882 | 1,355 |
| Cache-read tokens | 0 | 18,688 |
| Wall time | 33 s | 29 s |
| inspect_ai log | `logs/2026-05-16T22-43-12-00-00_diagnose-broken-cae-setup-condition-a_…eval` | `logs/2026-05-16T22-44-03-00-00_diagnose-broken-cae-setup-condition-b_…eval` |

## The crossover

This is the key finding. Same model, same scenario type, same defect — but
the *package size* changed between the two reports:

| | Small fixture (run 1) | Scaled fixture (run 2) |
|---|---|---|
| Condition A total tokens | 1,016 | **52,952** |
| Condition B total tokens | 6,272 | **38,214** |
| Cheaper condition | A wins by 6× | **B wins by 28%** |

On the small fixture, Condition B's tool-call overhead dominated Condition
A's tiny dump — agentic access was pure waste. On the scaled fixture,
Condition A is forced to consume the entire 52K-token dump while Condition
B can read selectively, and **the lines cross**. The structured evidence
layer starts paying for itself somewhere between the two package sizes.

This is the first run where the benchmark has actually measured something
the small scenario could not measure.

## What this run does demonstrate

1. **The benchmark differentiates conditions on the second axis** — token
   efficiency. Correctness is still ceiling-bound (Kimi-for-coding finds
   the Aluminum6061 defect even buried in 52K tokens of noise), but the
   efficiency axis now reports a 3× separation.

2. **There is a package-size crossover.** Below it, raw dump wins on
   tokens. Above it, structured access wins on tokens. The first Kimi
   run found Condition B 6× more expensive; this one finds it ~28%
   cheaper. We do not yet know the precise crossover or how it varies
   by model.

3. **Kimi's Anthropic tool-use adapter handles 18,688 cache-read tokens
   correctly** — the multi-turn prompt-cache plumbing works at scale.

4. **The red herrings did not throw Kimi off.** Three load cases exist;
   only load_case_001 contains the actual defect. The model identified
   the right one in both conditions.

## What this run does NOT demonstrate

- One trial per condition is not statistical evidence. The next step is
  `--epochs 5` to characterise variance.
- This says nothing about other models. Kimi-for-coding is structurally
  excellent at JSON inspection; weaker models might fail Condition A at
  52K tokens of noise and need Condition B to recover correctness.
- Correctness is still ceiling-bound on this scenario for this model.
  We cannot yet measure whether `.aieng` *prevents* errors, only that
  it *costs less* to be correct when correctness is achievable.
- The benchmark scenarios are still narrow. "Diagnose a cross-reference
  inconsistency" is one of many CAD/CAE tasks; nothing here generalises
  to mass reduction, stress reasoning, or design iteration.

## Implications for Phase 30

The scenario design is now sound. The benchmark is measuring what it was
designed to measure. Two follow-on actions:

1. **Run `--epochs 5` against the same scenario on the same model.**
   Cheap and immediately informative — characterises variance and lets
   us state a confidence interval on the 3× efficiency separation.

2. **Run the same scenario against a weaker model.** If `gpt-4o-mini`
   or a similar lower-tier model fails Condition A correctness at 52K
   noisy tokens but succeeds Condition B, the benchmark gains a
   correctness-axis finding too. That converts "evidence layer saves
   tokens" into "evidence layer prevents wrong answers" — a stronger
   product claim.

Scenarios #2–#4 still wait until at least the multi-epoch and
multi-model probes land. Adding more scenarios on a one-trial-per-pair
basis would just collect more single data points.

## Honest framing for any external write-up

> On one trial against Kimi's coding-tuned endpoint, both the
> raw-artifact and AIENG-augmented conditions produced correct
> diagnoses of a deliberately-broken CAE setup at ~158 KB package
> size. The AIENG-augmented condition used roughly 28% fewer tokens
> and scored roughly 3× higher on a token-efficiency rubric. On the
> small version of the same scenario, the relationship was inverted —
> AIENG-augmented used 6× more tokens. The findings to date are that
> a package-size crossover exists, that `.aieng`'s structured access
> pays for itself somewhere between ~700 and ~52,000 input tokens for
> this scenario and this model, and that one trial per condition is
> not enough to characterise variance or generalise beyond this
> specific combination.

That is the most honest paragraph we can write today. It is not
marketable. It is correct, and it now contains a real finding.
