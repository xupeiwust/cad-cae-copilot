# Run 20260517T154937Z — Kimi `kimi-for-coding`, scenario 4, n=10, T=0

Sixth run on the automated benchmark. First run on **scenario 4**
(setup correction / missing items audit).

**This is the first run on record where the benchmark measured a
correctness divergence between the two conditions.**

## Run identity

| Field | Value |
|---|---|
| Timestamps (UTC) | 2026-05-17T15:49:37Z (Condition A) / 15:51:19Z (Condition B) |
| Scenario | `setup_correction_missing_items` |
| Model | `anthropic/kimi-for-coding` |
| Epochs per condition | 10 |
| Temperature | 0 |
| Harness version | aieng commit at scenarios 3 + 4 source-add |
| Rubric | `rubric.yaml` v0.1 — 4-criterion substring + hallucination penalties + token-efficiency budget = 3000 |

## Aggregate results

| Metric | Condition A (n=10) | Condition B (n=10) |
|---|---|---|
| **Correctness — accuracy** | **0.450** | **0.950** |
| **Correctness — verdict distribution** | **3 C / 3 P / 4 I** | **9 C / 1 P / 0 I** |
| **Efficiency — mean** | 0.114 | 0.153 |
| Total tokens (10 epochs) | 262,495 | 298,773 |
| Per-epoch tokens (avg) | ~26,250 | ~29,877 |
| Input tokens | 242,640 | 182,415 |
| Cache-read tokens | 0 | 95,240 |
| Output tokens | 19,855 | 21,118 |
| Wall time | 82 s | 106 s |

## Headline: measured correctness divergence

Condition A misses at least one of the three required gaps in **7 of
10 trials** (3 partial + 4 incorrect). Condition B identifies **all
three required gaps in all 10 trials** (9 fully correct; 1 partial only
because the model added a stylistic "ready for solver: false" line that
the rubric's hallucination-penalty pattern matched verbatim despite the
correct identification of every gap).

This is the first run in the benchmark series where the structured
tool access produced materially better engineering audits, not merely
cheaper ones.

## Per-trial verdicts — Condition A (n=10)

| Trial | Verdict | Hits | Penalties |
|---|---|---|---|
| 1 | P | solver_settings + dangling | — |
| 2 | C | loads + solver_settings + dangling | — |
| 3 | I | solver_settings + dangling | "the setup is complete" (penalty 0.5) |
| 4 | P | loads + dangling | — |
| 5 | I | solver_settings + dangling | **"mesh is missing"** (penalty 0.4) |
| 6 | C | loads + solver_settings + dangling | — |
| 7 | I | loads + dangling | "ready for solver" (penalty 0.3) |
| 8 | C | solver_settings + dangling + plan | — |
| 9 | P | solver_settings + dangling | — |
| 10 | I | solver_settings + dangling | "ready for solver" (penalty 0.3) |

**Failure mode breakdown for Condition A:**

| Failure mode | Trials |
|---|---|
| Missed `parsed_loads.json` as missing | 5 (trials 1, 3, 5, 9, 10) |
| Missed `solver_settings.json` as missing | 2 (trials 4, 7) |
| Overclaimed "ready for solver" / "setup is complete" | 3 (trials 3, 7, 10) |
| Phantom artifact ("mesh is missing") | 1 (trial 5) |
| Hit all three required items | 3 (trials 2, 6, 8) |

The dominant Condition A failure is missing one of the two absent
artifacts (most often `parsed_loads.json`) while listing the other gaps
correctly. Three trials *additionally* overclaimed setup completeness,
which is the worst failure mode for an engineering audit task.

## Per-trial verdicts — Condition B (n=10)

| Trial | Verdict | Hits | Penalties |
|---|---|---|---|
| 1 | C | loads + solver_settings + dangling | — |
| 2 | C | loads + solver_settings + dangling + plan | — |
| 3 | C | loads + solver_settings + dangling | — |
| 4 | C | loads + solver_settings + dangling | — |
| 5 | C | loads + solver_settings + dangling + plan | — |
| 6 | P | loads + solver_settings + dangling | "ready for solver" (penalty 0.3) |
| 7 | C | loads + solver_settings + dangling + plan | — |
| 8 | C | loads + solver_settings + dangling | — |
| 9 | C | loads + solver_settings + dangling + plan | — |
| 10 | C | loads + solver_settings + dangling | — |

All 10 trials triggered every required-content criterion. The single
"P" verdict is a rubric penalty quirk — trial 6 hit all three required
items but used the phrase "ready_for_solver: false" verbatim in
reporting the preprocessing summary's output, which the
hallucination-penalty pattern matched literally without context.

## Token-efficiency note

Despite the dramatic correctness divergence, the **efficiency ratios are
close** (0.114 vs 0.153). Both conditions ran 10 epochs over comparable
total token volumes (262K vs 299K). Condition B's edge on tokens is
modest on this scenario because the model still calls multiple tools
(inspect package, then read at least 2–3 artifacts) before the
preprocessing summary is fetched.

The efficiency story is therefore narrower here than on scenarios 1–3:
Condition B does not save many tokens. It earns its place by **being
correct more reliably**, not by being cheaper.

## What this run shows

1. **Correctness divergence under Kimi is real on at least one
   scenario.** On the audit / find-missing-items task,
   Condition A misses gaps or invents false ones in 70% of trials;
   Condition B identifies all gaps in 100% of trials.
2. **The mechanism is interpretable.** `aieng_cae_preprocessing_summary`
   surfaces `missing_items` explicitly. Condition B can read the answer
   directly; Condition A must infer from absence in a 26K-token dump,
   which it does inconsistently.
3. **Failure modes are concrete.** Three of the four Condition A
   incorrect trials produce the *most dangerous* failure for an
   engineering audit: claiming the setup is complete or ready to run
   despite gaps.
4. **Efficiency advantage shrinks when both conditions need to read
   multiple artifacts.** Condition B's structural access does not save
   many tokens here; its value is correctness, not cost.

## What this run does NOT show

- **The correctness divergence is single-model, single-scenario, n=10.**
  We cannot generalise to other models. A more capable model than
  Kimi-for-coding might close the gap on Condition A.
- **The rubric is substring-based.** A model that names every gap in
  prose but never matches the exact pattern strings would be undercounted.
  This is a known limit of the deterministic scoring approach.
- **`.aieng` does not "prove" engineering validity.** The benchmark
  measured that structured access helps Kimi answer this specific
  audit-style question correctly. It did not measure whether the model's
  *recommendations* would actually fix the package — the rubric tests
  identification, not synthesis.

## Honest framing for any external write-up

> On scenario 4 (setup-correction audit), Kimi `kimi-for-coding` at
> n=10, temperature 0 identified all three required gaps in 100% of
> trials when given `.aieng` tool access (Condition B), and in 30% of
> trials when given the raw artifact dump (Condition A). Four of the
> ten raw-dump trials produced engineering-unsafe outputs: three
> overclaimed that the setup was ready for the solver, and one invented
> a phantom missing artifact ("mesh is missing"). The structured-tool
> condition produced none of those failures. Token-efficiency was
> comparable across conditions on this scenario; the value of `.aieng`
> access here is correctness, not cost.

This is the strongest sentence the benchmark currently supports.
