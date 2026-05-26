# AIENG CAE Evidence Understanding Benchmark Report

This benchmark is the current public proof point for the AIENG direction:

> Structured `.aieng` evidence access helps a general LLM review CAE state more
> accurately and more auditably than a raw artifact dump.

AIENG is not evaluated here as a solver, mesher, CAD kernel, or engineering
certification system. The benchmark only measures whether the model can read
engineering evidence, missingness, limitations, and design-target context with
less hallucination and less unnecessary context consumption.

## Conditions

| Condition | What the model gets | Purpose |
|---|---|---|
| A — raw dump | Concatenated package/artifact text, no tools | Baseline: "just paste the files into the prompt" |
| B — `.aieng` evidence access | Package handle plus read-only AIENG tools | Test selective, structured evidence inspection |

Both conditions use the same model, prompt family, temperature, scenario rubric,
and scoring interpretation.

## Scenarios shipped

| Scenario | Task shape | What is tested |
|---|---|---|
| `diagnose_broken_cae_setup` | Defect diagnosis | Cross-reference and setup consistency |
| `mass_reduction_recommendation` | Engineering recommendation | Uses result metrics and design targets |
| `stress_concentrator_recommendation` | Engineering recommendation | Identifies high-stress feature and safe next action |
| `setup_correction_missing_items` | Setup audit | Missing loads/settings and dangling references |

## Results on record

Existing recorded runs use Kimi `kimi-for-coding`, temperature 0.

| Scenario | n | Correctness A | Correctness B | Mean token efficiency A / B | Main finding |
|---|---:|---|---|---|---|
| Diagnose broken CAE setup, scaled | 5 | 5/5 C | 5/5 C | 0.038 / 0.285 | Same correctness; B uses far less context on larger package |
| Mass reduction recommendation | 5 | 5/5 C | 5/5 C | 0.125 / 0.792 | Same correctness; B is more token-efficient |
| Stress concentrator recommendation | 10 | 10/10 C | 10/10 C | 0.129 / 0.741 | Same correctness; B is more token-efficient |
| Setup correction / missing items | 10 | 3 C / 3 P / 4 I | 9 C / 1 P / 0 I | 0.114 / 0.153 | Correctness divergence: raw dump overclaims or misses setup defects |

`C` = correct, `P` = partial, `I` = incorrect under the deterministic rubric.

## How to reproduce the smoke path without API keys

```powershell
cd aieng
pip install -e ".[benchmark]"

inspect eval benchmarks/llm_engineering_usefulness/scenarios/diagnose_broken_cae_setup/task.py@diagnose_broken_cae_setup_condition_a `
  --model mockllm/model
inspect eval benchmarks/llm_engineering_usefulness/scenarios/diagnose_broken_cae_setup/task.py@diagnose_broken_cae_setup_condition_b `
  --model mockllm/model
```

The mock model does not prove benchmark quality; it only proves that the harness,
fixtures, tools, and scorers execute without external credentials.

## How to run a real model

```powershell
$env:ANTHROPIC_API_KEY = "<your key>"
inspect eval benchmarks/llm_engineering_usefulness/scenarios/setup_correction_missing_items/task.py@setup_correction_missing_items_condition_a `
  --model anthropic/claude-sonnet-4-6 `
  --epochs 10
inspect eval benchmarks/llm_engineering_usefulness/scenarios/setup_correction_missing_items/task.py@setup_correction_missing_items_condition_b `
  --model anthropic/claude-sonnet-4-6 `
  --epochs 10
```

## Limits and honesty boundary

- One recorded model family is not a universal claim.
- Four scenarios are useful but not comprehensive CAE coverage.
- Deterministic substring rubrics are reproducible but can miss novel correct
  wording.
- Benchmark correctness is not engineering correctness.
- `.aieng` evidence can support review; it does not certify that a design is
  safe, manufacturable, converged, or valid.

## Why this matters for the product

The benchmark supports the V1 product direction: a web-based CAE review report
assistant that synthesizes setup readiness, missing information, stale evidence,
result metrics, design-target comparisons, and claim boundaries before any LLM
or user makes an engineering conclusion.
