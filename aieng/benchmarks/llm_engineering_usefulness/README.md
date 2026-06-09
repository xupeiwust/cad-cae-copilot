# Automated LLM engineering usefulness benchmark

A calibrated A/B benchmark that measures whether an LLM equipped with `.aieng`
evidence access produces better engineering proposals than the same LLM
without it, on bounded, repeatable scenarios.

For a concise open-source user-facing result summary, see
[`OPEN_SOURCE_REPORT.md`](OPEN_SOURCE_REPORT.md).

Phase 30 of the LLM-assisted CAD/CAE design roadmap — design context lives in
[issue #54](https://github.com/armpro24-blip/aieng/issues/54); this slice
tracked in [issue #55](https://github.com/armpro24-blip/aieng/issues/55).

## Relationship to `ai_usefulness/`

| `ai_usefulness/` | `llm_engineering_usefulness/` (this directory) |
|---|---|
| Human-conducted | Automated via [`inspect_ai`](https://github.com/UKGovernmentBEIS/inspect_ai) |
| One scenario per directory, broad qualitative + quantitative coverage | Per-scenario inspect_ai `Task` with two-axis rubric |
| 7-dimension rubric, manual scoring | YAML rubric + correctness scorer + token-efficiency scorer |
| Single-shot prompt | Multi-turn agentic Condition B (`use_tools` solver) |
| Source of truth for nuanced judgment | Source of truth for repeatable A/B numbers |

## Two scoring axes

Each trial produces two independent scores:

| Scorer | Measures | Aggregated by |
|---|---|---|
| `diagnose_rubric_scorer` | **Correctness** — verdict in `{C, P, I}` against the substring rubric and hallucination penalties | `accuracy()` |
| `token_efficiency_scorer` | **Cost-efficiency** — `min(1.0, token_budget / total_tokens_used)` | `mean()` |

The axes are intentionally orthogonal. A scenario where Condition A and
Condition B both score `C` on correctness but B costs 6× more tokens
is a finding the benchmark must surface, not collapse — the first
Kimi run on `diagnose_broken_cae_setup` is exactly that case (see
[results/runs/run_20260516T222309Z_kimi-for-coding](results/runs/run_20260516T222309Z_kimi-for-coding/observation_report.md)).
Per-scenario `token_budget` lives in each scenario's `rubric.yaml`.

The two complement, not replace, each other.

## Two conditions

Same prompt template, same model, same temperature, same scoring rubric. The
only independent variable is access to the evidence layer.

- **Condition A** — the LLM receives the raw concatenated contents of the
  package's setup artifacts as one big text blob. No tools.
- **Condition B** — the LLM receives only the package handle and the AIENG
  tool surface (`aieng_inspect_package`, `aieng_read_artifact`,
  `aieng_cae_preprocessing_summary`). Multi-turn execution — the LLM decides
  what to inspect.

Condition B's tools are the in-process Python equivalents of what an MCP-using
agent would call via `aieng_freecad_mcp/tools_runtime/`. That keeps the
eventual multi-agent integration on the critical path.

## Installation

```powershell
cd /path/to/cad-cae-copilot/aieng
pip install -e ".[benchmark]"
```

This adds `inspect-ai`, `anthropic`, and `openai` — kept out of the runtime
package's required dependencies because they only matter for benchmarking.

## Run the harness end-to-end without API keys

```powershell
inspect eval scenarios/diagnose_broken_cae_setup/task.py@diagnose_broken_cae_setup_condition_a `
    --model mockllm/model
inspect eval scenarios/diagnose_broken_cae_setup/task.py@diagnose_broken_cae_setup_condition_b `
    --model mockllm/model
```

The built-in `mockllm/model` provider returns a fixed default response — both
runs will score "I" (incorrect), but the pipeline exercises every component.
This is the smoke path covered by the pytest tests.

## Run a real eval

```powershell
$env:ANTHROPIC_API_KEY = "<your key>"
inspect eval scenarios/diagnose_broken_cae_setup/task.py@diagnose_broken_cae_setup_condition_a `
    --model anthropic/claude-sonnet-4-6 `
    --epochs 5
inspect eval scenarios/diagnose_broken_cae_setup/task.py@diagnose_broken_cae_setup_condition_b `
    --model anthropic/claude-sonnet-4-6 `
    --epochs 5
```

Inspect View renders the run interactively:

```powershell
inspect view
```

## Where runs land

Each real-model run gets a directory under `results/runs/`, named
`run_<UTC-timestamp>_<model-tag>/`:

```
results/runs/run_YYYYMMDDTHHMMSSZ_<model-tag>/
  observation_report.md   ← narrative field notes for this run
```

The inspect_ai per-eval `.eval` log files live in the gitignored
`logs/` directory at the repo root — view them locally with
`inspect view` or `inspect log dump <path>`.

Runs on record (newest first):

1. [run_20260517T154937Z_kimi-for-coding_setup_correction_n10](results/runs/run_20260517T154937Z_kimi-for-coding_setup_correction_n10/observation_report.md)
   — `kimi-for-coding`, **scenario 4 (setup-correction audit)**, n=10,
   T=0. **First measured correctness divergence:** A 3 C / 3 P / 4 I
   (accuracy 0.45); B 9 C / 1 P / 0 I (accuracy 0.95). Dominant A
   failure modes were "ready for solver" overclaims (3) and a phantom
   "mesh is missing" hallucination (1). Token-efficiency comparable.
2. [run_20260517T154655Z_kimi-for-coding_stress_concentrator_n10](results/runs/run_20260517T154655Z_kimi-for-coding_stress_concentrator_n10/observation_report.md)
   — `kimi-for-coding`, scenario 3 (stress-concentrator), n=10, T=0.
   Both 10/10 C. Mean efficiency: A 0.129, B 0.741 (~5.7×).
3. [run_20260516T225920Z_kimi-for-coding_mass_reduction_n5](results/runs/run_20260516T225920Z_kimi-for-coding_mass_reduction_n5/observation_report.md)
   — `kimi-for-coding`, scenario 2 (mass-reduction recommendation), n=5.
   Both 5/5 C. Mean efficiency: A 0.125, B 0.792 (~6.3×).
4. [run_20260516T224856Z_kimi-for-coding_scaled_n5](results/runs/run_20260516T224856Z_kimi-for-coding_scaled_n5/observation_report.md)
   — `kimi-for-coding`, scenario 1 scaled, n=5. Both 5/5 C.
   Mean efficiency: A 0.038, B 0.285 (~7.5×).
5. [run_20260516T224312Z_kimi-for-coding_scaled](results/runs/run_20260516T224312Z_kimi-for-coding_scaled/observation_report.md)
   — scenario 1 scaled, n=1. Both `C`; B ~3× more efficient than A.
6. [run_20260516T222309Z_kimi-for-coding](results/runs/run_20260516T222309Z_kimi-for-coding/observation_report.md)
   — scenario 1 original small (~700 tokens), n=1. Both `C`; B was
   6× *more* expensive than A — overhead dominated.

The six runs together demonstrate three findings:

- **Measured correctness divergence on scenario 4.** Condition A
  fails or overclaims on 7/10 trials; Condition B succeeds on 10/10.
  This is the first scenario where correctness, not just cost,
  distinguishes the two conditions. Single model, single scenario,
  n=10 — not yet a general claim.
- **Token-efficiency advantage on scenarios 1–3.** On scaled
  packages and both task shapes (defect-spotting, recommendation), B
  uses 3.5–7.5× fewer tokens than A while reaching the same
  correctness verdict.
- **Package-size crossover.** Structured access loses to raw dump
  on small packages (B 6× more expensive on the original ~700-token
  fixture), wins on large ones.

## Adding a new scenario

1. Create `scenarios/<scenario_id>/`.
2. Write `build_fixture.py` exposing `build_<verb>_package(target: Path) -> Path` that emits the fixture deterministically. Keep the fixture's defect identifiable in code (no opaque binary).
3. Write `ground_truth.md` explaining the canonical diagnosis or proposal.
4. Write `rubric.yaml` with criteria + patterns + hallucination penalties (deterministic for now).
5. Write `task.py` exposing `<scenario_id>_condition_a` and `<scenario_id>_condition_b` decorated with `@task`.
6. Add a smoke test under `aieng/tests/test_llm_engineering_usefulness.py` that runs both conditions against `mockllm/model`.

The four scenarios on the Phase 30 roadmap:

1. **Mass reduction recommendation** — given a solved CAE result, choose the safest of four proposed mass-reduction changes. The numeric acceptance criteria (mass-reduction floor and minimum safety factor) live in the package's `task/design_targets.yaml`; Condition A receives them through the raw artifact dump, Condition B through structured package access. *(shipped — `scenarios/mass_reduction_recommendation/`)*
2. **Diagnose broken CAE setup** — identify the cross-reference defect in a deliberately-broken package. *(shipped — `scenarios/diagnose_broken_cae_setup/`)*
3. **Stress concentrator recommendation** — identify a high-stress feature and propose a reasonable design response. *(shipped — `scenarios/stress_concentrator_recommendation/`)*
4. **Setup correction / missing items** — audit a CAE setup that is missing required artifacts and contains a dangling load reference. *(shipped — `scenarios/setup_correction_missing_items/`)*

## Honesty boundaries

- This benchmark measures `.aieng`'s contribution under one model and one
  rubric per scenario. It does not prove general utility.
- The deterministic substring scorer is intentionally conservative — it
  rewards specificity but cannot judge novel correct answers that don't
  contain the expected keywords. LLM-graded rubric is a later phase.
- `mockllm/model` is for plumbing only. Real conclusions need real models.
- Aggregate numbers across only a handful of scenarios should not be marketed
  as "AIENG helps engineers" — they should be reported with their
  scenario-specific scope.

## License

Same license as the parent repository.
