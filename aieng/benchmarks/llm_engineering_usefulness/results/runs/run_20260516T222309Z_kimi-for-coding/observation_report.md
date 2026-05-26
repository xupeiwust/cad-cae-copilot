# Run 20260516T222309Z — Kimi `kimi-for-coding`, scenario `diagnose_broken_cae_setup`

First real model run on the automated A/B benchmark. One epoch per condition.
This is field notes for a single trial on a single scenario on a single
model — it is **not** a generalisable claim about `.aieng`.

## Run identity

| Field | Value |
|---|---|
| Timestamp (UTC) | 2026-05-16T22:23:09Z |
| Scenario | `diagnose_broken_cae_setup` |
| Model | `anthropic/kimi-for-coding` (Kimi K2 series, Anthropic-compatible adapter) |
| Provider base URL | `https://api.kimi.com/coding/` |
| Epochs per condition | 1 |
| Conditions run | A (raw artifact dump, no tools), B (package handle + AIENG tools, multi-turn) |
| Harness version | `aieng` commit `5082d3c` (Phase 30 first slice + CLI loader fix) |
| inspect_ai version | 0.3.222 |
| Rubric | `rubric.yaml` v0.1 — deterministic substring + hallucination penalties |

## Raw results

| Metric | Condition A | Condition B |
|---|---|---|
| Verdict | `C` (correct) | `C` (correct) |
| Accuracy (inspect_ai aggregate) | 1.000 | 1.000 |
| Total tokens | 1,016 | 6,272 |
| Input tokens | 708 | 3,566 |
| Output tokens | 308 | 914 |
| Cache-read tokens | 0 | 1,792 |
| Wall time | 7 s | 33 s |
| inspect_ai log | `logs/2026-05-16T22-23-09-00-00_diagnose-broken-cae-setup-condition-a_93GF2Hp25emT9EYVxMgpSz.eval` | `logs/2026-05-16T22-24-39-00-00_diagnose-broken-cae-setup-condition-b_HB3nxBYcxF4pFrzEQzk8Q7.eval` |

Eval logs are local artifacts (gitignored). Use `inspect view` to render
them interactively, or `inspect log dump <path>` for the raw JSON.

## What this run actually demonstrates

1. **The harness is empirically ready.** Both conditions executed end-to-end
   against a real (non-Anthropic) Anthropic-compatible endpoint; both
   produced rubric-scored verdicts; both completed in under a minute.

2. **Kimi's Anthropic adapter handles tool-use faithfully.** Condition B's
   1,792 cache-read tokens are the trace of inspect_ai re-feeding tool
   calls and tool results back into the conversation across multiple
   turns. The Messages-API `tool_use` / `tool_result` content block
   schema works against this endpoint without modification. This was
   the single biggest compatibility risk going into the run and it is
   resolved.

3. **For this scenario, structured access costs more than raw dump.**
   Same verdict, ~6× the tokens, ~5× the wall time. Condition B made the
   tool calls — inspected the package, read artifacts — and arrived at
   the same correct diagnosis Condition A reached from the prompt alone.

## What this run does NOT demonstrate

- This says **nothing** about whether `.aieng` helps in general.
- This says nothing about other models. Kimi-for-coding is tuned for
  code/structured-text reasoning; weaker or non-coding-tuned models
  might fail Condition A and need Condition B's structure to succeed.
- This says nothing about scenarios where the package is larger than
  the prompt can comfortably hold, or where the defect is buried among
  many plausible-looking artifacts.
- One trial per condition is not enough for statistical claims.

## The ceiling diagnosis

The scenario as currently authored is too easy. Eight small JSON
artifacts with a single, obvious cross-reference inconsistency, all
fitting in a ~700-token prompt window, do not put Condition A at a
disadvantage that the structured tool access can compensate for. Both
conditions saturate at correctness; there is no headroom for a delta.

This is a **scenario-design** finding, not a finding about `.aieng`,
the harness, or Kimi. The Phase 30 plan correctly identified this
risk in advance — the design issue says "run the benchmark first
because we don't know where the bottleneck is". The bottleneck on
this scenario is "the rubric only measures correctness, and the
correctness ceiling is too low for B to differentiate".

## What this run changes about Phase 30

Three concrete adjustments before more scenarios:

1. **Extend the rubric to a second axis: efficiency / cost.** Add a
   `token_budget_score` or `cost_efficiency_score` alongside the
   existing correctness verdict. With a token budget of ~2,000,
   Condition A passes and Condition B fails on *this* scenario — and
   that's the honest measurement. The benchmark should be able to
   say "B is more correct but more expensive" or "A wins on small
   tasks", not just "both correct".

2. **Scale up the existing scenario.** Modify `build_fixture.py` so
   the broken package includes plausible-looking bulk artifacts
   (parsed_topology with hundreds of entries, mesh metadata with
   element listings, etc.) — ~50–100 KB total. The defect stays the
   same; only the haystack grows. Re-run on the same model and look
   for whether Condition A's correctness or efficiency degrades.

3. **Defer scenarios #2–#4 until the rubric and the scenario-size
   pattern are tested.** Building three more scenarios on the current
   ceiling-prone design just adds three more ceiling runs.

## Honest framing for any external write-up

> On a small (one-trial) run against Kimi's coding-tuned endpoint,
> both raw-dump and AIENG-augmented conditions produced correct
> diagnoses of a deliberately-broken CAE setup. The structured access
> condition used roughly six times more tokens and five times more
> wall time for the same answer. The benchmark is functioning
> end-to-end; the scenario does not yet distinguish the two
> conditions in any meaningful way.

That is the most honest sentence we can write today. It is not
marketable. It is correct.
