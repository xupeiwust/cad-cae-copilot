---
title: "[Phase 36] Closed-loop validation benchmark"
labels: ["phase-36", "benchmarks", "closed-loop", "implementation-planned"]
status: open
---

## Motivation

Phase 30 measured whether **read-only** evidence access improved LLM
engineering proposals (Condition A: LLM only, Condition B: LLM + AIENG
read tools). Phases 32–35 added generation and design-target surfaces
to the evidence layer:

- Phase 32 — `cad.edit_parameter` (single named-parameter CAD mutation, approval-gated)
- Phase 33 — `cae.generate_solver_input` (CalculiX deck assembly)
- Phase 34 — `results/field_summary.json` (LLM-facing field-region summary)
- Phase 35 — `task/design_targets.yaml` + `result_summary.targets[*].met`

Phase 36 re-runs the calibrated A/B benchmark with a **third condition**
that exposes those generation surfaces to the agent, and measures
whether closed-loop execution improves target compliance.

See [issue #54](https://github.com/armpro24-blip/aieng/issues/54)
(Phase 36 section) for the roadmap context.

## Goal

Empirically measure whether closed-loop execution helps, hurts, or
does not affect target compliance on the Phase 30 scenarios plus two
new closed-loop-shaped scenarios — and report each per-scenario result
plainly (including regressions).

## Scope

1. Reuse the existing Phase 30 scenario set under `benchmarks/llm_engineering_usefulness/scenarios/`.
2. Add two **closed-loop scenarios** that need at least one generation
   step (`cae.generate_solver_input` and/or `cad.edit_parameter`) to
   satisfy a `task/design_targets.yaml` target:
   - `mass_reduction_closed_loop` — propose a parameter edit + regenerate
     solver input, then re-evaluate `targets.met`.
   - `stress_concentrator_closed_loop` — propose a fillet/radius change
     and a re-solve request, then re-evaluate field-region peak magnitude
     against a `max_von_mises_stress` target.
3. Add a third benchmark condition — **Condition C: LLM + AIENG read +
   closed-loop generation** — that exposes the Phase 32/33 tools in
   addition to the Phase 30 read surface. Approval-gated tools are
   auto-approved within the harness; the approval gate remains a real
   contract surface, not bypassed.
4. Extend `aieng.benchmark.run` to accept `--condition C` and register
   the two new scenarios in `_scenario_registry()`.
5. Run each (scenario × condition) with `--trials >= 5` against at least
   one real model (anthropic or openai). Land the writeups under
   `benchmarks/llm_engineering_usefulness/results/runs/run_*_phase36*/`
   following the existing `observation_report.md` format.
6. Add a per-condition row to the existing two-axis (`correctness`,
   `token_efficiency`) summary; introduce a third orthogonal axis
   **`target_compliance`** that reports `met / not_met / unknown` counts
   sourced from `result_summary.targets[*].met` after the agent's
   final state.

## Acceptance criteria

- [ ] Two closed-loop scenario directories exist with `build_fixture.py`,
      `ground_truth.md`, `rubric.yaml`, `task.py`, registered in
      `src/aieng/benchmark/run.py` and covered by a smoke test under
      `tests/test_llm_engineering_usefulness.py` that runs against
      `mockllm/model`.
- [ ] `aieng.benchmark.run --condition C` works end-to-end against
      `mockllm/model` (smoke path) and records condition-C results
      to JSON output.
- [ ] At least one real-model run (anthropic or openai) per
      (scenario × condition) is captured under `results/runs/` with an
      `observation_report.md`.
- [ ] The final report explicitly states per scenario whether
      Condition C **helps**, **does not help**, or **regresses**
      target compliance versus Condition B, with confidence intervals.
      Negative results are reported plainly.
- [ ] The `target_compliance` axis surfaces `unknown` separately from
      `not_met`. Absence of evidence stays `unknown`; closed-loop
      execution that cannot produce evidence must not silently report
      "met".

## Honesty boundaries

- The benchmark measures Condition C under one set of scenarios and
  rubrics. It does not prove general utility of closed-loop generation.
- `converged: null` remains `null` unless evidence is produced. A
  closed-loop run that generates a deck but does not run the solver
  must not advance convergence state.
- Approval-gated tools must record an approval trace even when auto-
  approved by the harness, so the contract surface stays visible.
- Schema drift in the new closed-loop scenario packages must surface as
  warnings, never silent acceptance.

## Dependencies

- **Phase 30** (already shipped) — original scenario set + CLI + scorers.
- **Phase 32** (`cad.edit_parameter`) — required for closed-loop CAD edits.
  Implementation lives in `aieng_freecad_mcp`; this repo defines the
  shared contract under `docs/cad_parameter_mutation_contract.md` and
  `schemas/parameter_edit.schema.json`.
- **Phase 33** (`cae.generate_solver_input`) — already shipped in
  `src/aieng/simulation/deck_generator.py`.
- **Phase 34** (`results/field_summary.json`) — already shipped in
  `src/aieng/cae_field_summary.py`.
- **Phase 35** (`task/design_targets.yaml`) — already shipped; design
  targets feed the new `target_compliance` axis via
  `result_summary.targets[*].met`.

## Out of scope

- No fine-tuning, RAG, or agent-loop tuning.
- No new generation tools beyond Phases 32/33.
- No marketing claims of "AIENG enables closed-loop CAD/CAE agents".
- No generality claims beyond the explicit scenario set.

## Related documents

- [docs/roadmap.md](../docs/roadmap.md)
- [benchmarks/llm_engineering_usefulness/README.md](../benchmarks/llm_engineering_usefulness/README.md)
- [docs/benchmark_design.md](../docs/benchmark_design.md)
- [docs/benchmark_methodology.md](../docs/benchmark_methodology.md)
