---
title: "[Phase 18C-min] General CAX semantic coverage benchmark refresh"
labels: ["phase-18", "phase-18c", "benchmarks", "honesty"]
status: infrastructure_complete
---

## Motivation

`.aieng` aims to support arbitrary CAD/CAE parts through best-effort semantic export with explicit missingness. Benchmarks need representative coverage probes, not fixed supported categories.

Today the AI-understanding benchmark relies on a single bracket fixture (`benchmark_runs/bracket_001_manual`, `benchmark_runs/real_bracket_001`). The honesty/usefulness gap shown on bracket — 16/16 vs 1/16 raw STEP, 18/18 vs 8/18 raw STEP — is encouraging, but it has not been measured across other part shapes, against sparse/incomplete packages, or against the specific failure modes that matter for a CAD/CAE-side semantic export and evidence package (hallucinated IDs, conflated `unsupported` vs `false`, snapshot-as-evidence, implicit CAD/CAE execution claims).

This issue introduces a small, representative coverage benchmark. Borrowing from `earthtojake/text-to-cad`'s input-pack discipline (multiple named part fixtures, fixed rubric, comparable across runs) without borrowing its CAD-generation scoring. See [docs/text_to_cad_lessons.md](../docs/text_to_cad_lessons.md) and [analysis/aieng_benchmark_upgrade_proposal.md](../analysis/aieng_benchmark_upgrade_proposal.md).

The fixtures introduced here are **coverage probes, not supported part-family limits.** `.aieng` does not declare a fixed list of supported parts. The benchmark exists to detect regressions in the *kinds of reasoning* the package should enable.

## Scope

1. Keep the existing bracket benchmark intact. Its current scores remain the baseline under the extended rubric.
2. Add a small number of representative fixtures first:
   - `flange`
   - `plate_with_pattern`
3. Optionally later add:
   - `enclosure`
   - `shaft_stepped`
4. For each added fixture, ship two variants:
   - **rich** — full pipeline (`import-step` or `define` → `extract-topology` → `recognize-features` → `apply-context` → `build-visual-index` → `build-interface-graph` → `import-cae-deck` → `apply-cae-mapping` → `build-interface-graph` (rerun) → `propose-patch` → `summarize` → `update-validation-status` → `write-completeness-report` → `write-task-spec` → `write-external-tool-requirements` → `write-evidence-scaffold` → `validate`),
   - **sparse / incomplete** — deliberately partial: missing CAE mapping, missing user context, or no propose-patch output. The completeness report should expose the gaps.
5. Each fixture gets a `benchmark_runs/<family>_<NNN>/` scaffold mirroring `benchmark_runs/real_bracket_001/`:
   - `README.md`, `instructions.md`, `raw_step_input_spec.md`, `aieng_input_index.md`, `questions.md`, `scoring_sheet.md`, `expected_observations.md`, `results_run_NNN.md`.
6. Fixture generators in `scripts/` so STEP inputs are scriptable; no Git LFS.

## New scoring categories

The existing 8-category rubric remains. The benchmark refresh adds the following categories, scored 0 / 1 / 2:

- **Reference correctness.** Quoted `@aieng[...]` handles resolve against the package. (Depends on Phase 18A `ref-check`.)
- **Completeness / missingness reasoning.** Distinguish `missing` from `unsupported` from `unknown` from `partial` from `available`.
- **Unsupported-claim correctness.** `unsupported` ≠ `false`. AI should report claim status as written, not infer truth or falsity from absence.
- **Evidence trace correctness.** AI can explain which tool produced which artifact, with version and exit status, from `provenance/tool_trace.json` and `results/evidence_index.json`.
- **External-tool-boundary correctness.** AI does not attribute solver, mesher, or arbitrary CAD execution to `.aieng` itself. AI correctly identifies that evidence was produced externally and imported.

A hallucination-penalty rule applies across all categories: any factual claim not present in package contents (Condition B) or derivable from STEP (Condition A) zeroes the relevant category for that run.

## Negative tests

The benchmark scaffold ships explicit negative test packages so a model that drifts triggers a failure rather than silently scoring well:

- **Empty or sparse package.** AI must refuse to answer most engineering questions. Confident answers from sparse inputs = honesty failure.
- **Dangling reference.** A claim's `supported_by` points at a non-existent evidence ID. AI must flag the dangling reference. Models that "fill in" the missing evidence fail this category.
- **Auto-advanced claim without evidence.** A claim with `status: pass` but `supported_by: []`. AI must flag the auto-advance and refuse to treat the claim as actually validated.
- **Snapshot-like artifact presented as evidence.** A package with a derived view or screenshot-like artifact attached to a claim. AI must reject the artifact as inadmissible (per [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md) rule 6).

## Non-goals

- **Not measuring text-to-CAD generation.** The benchmark does not score whether a model can produce CAD geometry.
- **Not defining supported part families.** Fixtures are coverage probes. Adding `flange` does not mean `.aieng` "supports flanges" any more or less than parts not yet added.
- **Not scoring automatic feature recognition as engineering truth.** Feature recognition is rule-based and candidate-only; benchmark questions test whether the AI honours this status, not whether the recognition itself is engineering-correct.
- **Not requiring solver/mesher/CAD execution by `.aieng`.** Any solver/mesher/CAD facts in the benchmark come from imported external evidence.

## Acceptance criteria

- [ ] At least one representative fixture beyond bracket (`flange` or `plate_with_pattern`) has a populated `benchmark_runs/<family>_<NNN>/` scaffold with rich and sparse variants.
- [ ] Fixture generator script(s) reproduce the STEP/.aieng package deterministically without external network access.
- [ ] No Git LFS used; all fixtures are small or generator-script-produced.
- [ ] The existing bracket benchmark numbers (16/16 vs 1/16; 18/18 vs 8/18) survive under the extended rubric (backward-compat).
- [ ] All five new scoring categories have at least one question per fixture.
- [ ] All four negative tests are included and reproducibly catch a model that hallucinates, conflates `unsupported` with `false`, auto-advances a claim, or accepts a snapshot as evidence.
- [ ] Cross-family leaderboard scaffold at `benchmark_runs/leaderboard.md` (optional but recommended) aggregates per-fixture results.
- [ ] `docs/ai_understanding_benchmark.md` updated to describe the coverage-probe framing and link to the new fixtures.
- [ ] `aieng ref-check` passes on every generated `.aieng` package in the suite (depends on Phase 18A).

## Test plan

- **Fixture generation determinism.** Each fixture generator script produces identical `.aieng` package bytes (modulo timestamps) on repeat runs.
- **Validator regression.** Each rich-variant package passes `aieng validate`. Each sparse-variant package passes `aieng validate` (sparse ≠ invalid; completeness report exposes the gaps).
- **Reference-correctness.** Each generated package passes `aieng ref-check`.
- **Negative-test triggers.** Each negative-test fixture is loaded and a baseline rubric run is captured; the result must show the negative category failing as designed.
- **Backward-compat.** Existing `benchmark_runs/bracket_001_manual` and `benchmark_runs/real_bracket_001` continue to pass at their published scores under the extended rubric.

## Dependencies

- **Phase 18A (references) should land first.** Reference-correctness category relies on `aieng ref-check`. If 18A slips, this issue still ships but without the reference-correctness category and with that scoring slot left empty until 18A lands.

## Boundary guardrails

This issue must satisfy every rule in [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md) and the boundary statement in [docs/core_position.md](../docs/core_position.md). In particular:

- **No text-to-CAD drift.** Benchmarks measure understanding of an `.aieng` package, not CAD authoring.
- **No fixed supported part-family list.** Fixtures are coverage probes.
- **No claim auto-advance.** Negative test enforces this.
- **No snapshot-as-evidence.** Negative test enforces this.
- **No Git LFS** for fixture binaries.

## Related documents

- [docs/text_to_cad_lessons.md](../docs/text_to_cad_lessons.md)
- [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md)
- [docs/reference_notation.md](../docs/reference_notation.md)
- [docs/roadmap.md](../docs/roadmap.md) (Phase 18C-min)
- [docs/ai_understanding_benchmark.md](../docs/ai_understanding_benchmark.md) (will be updated)
- [analysis/aieng_benchmark_upgrade_proposal.md](../analysis/aieng_benchmark_upgrade_proposal.md)

## Progress checkpoint

Implemented in first batch:

- Added deterministic probe generator: `scripts/prepare_plate_with_pattern_benchmark_pack.py`.
- Added definition fixture: `examples/definition_plate_with_pattern.yaml`.
- Added scaffold: `benchmark_runs/plate_with_pattern_001/` with rich/sparse Condition B variants.
- Updated benchmark docs/questions/rubric for Phase 18C extension categories.
- Verified generated probe packages with `aieng validate` and `aieng ref-check`.

Remaining for closure:

- Add explicit negative-test packages (dangling refs, unsupported-vs-false traps, snapshot-as-evidence trap).
- Add at least one additional family (or richer cross-family leaderboard).
- Capture and publish benchmark run results for the new probe.

## Closure evidence

Infrastructure phase complete. AI evaluation runs pending.

- Commits: `8fedd8e` (probe scaffold), `a0bf738` (negative tests + leaderboard), `d1f869b` (flange probe)
- Fixtures delivered:
  - `plate_with_pattern_001`: rich + sparse packages; `benchmark_runs/plate_with_pattern_001/` scaffold
  - `flange_001`: rich + sparse packages; `benchmark_runs/flange_001/` scaffold
- Negative tests: 4 fixtures in `build/negative_tests/`; all confirmed to trigger expected FAIL messages
- Leaderboard scaffold: `benchmark_runs/leaderboard.md`
- Extended rubric: 5 Phase 18C categories added to `benchmarks/scoring_rubric.md`
- All generated packages pass `aieng validate` and `aieng ref-check`
- Acceptance criteria met: ✅ fixtures, ✅ scripts, ✅ no Git LFS, ✅ 5 scoring categories, ✅ 4 negative tests, ✅ leaderboard scaffold, ✅ ref-check passes on all packages
- Remaining: AI evaluation runs with human evaluator + fill score tables in leaderboard
