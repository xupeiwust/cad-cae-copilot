# `.aieng` Benchmark Upgrade Proposal

Status: draft for Phase 18C.

What text-to-cad does well, in benchmark terms: it has a small, named portfolio of representative parts (bracket, flange, enclosure, clevis, impeller, staircase, planetary gear, …) and treats benchmark inputs as a fixed scaffold so different agents can be compared.

`.aieng` already has:
- `benchmarks/handoff/` (Phase 14D, 10 question groups, 8-category 0/1/2 rubric, max 16).
- `benchmark_runs/bracket_001_manual/` (16/16 vs 1/16 raw STEP).
- `benchmark_runs/real_bracket_001/` (18/18 vs 8/18 raw STEP).

Gap: only one part family. The honesty/usefulness gap shown on bracket may or may not generalise.

This proposal upgrades benchmarks by borrowing the *input-pack discipline*, not the agent-authoring identity.

## 1. Goals (do these)

- Measure whether a general AI reading an `.aieng` package can correctly reason about:
  - feature semantics and protected regions
  - simulation context and validation state
  - external tool boundary (what `.aieng` may and may not claim)
  - claim status semantics (`unsupported` ≠ `false`)
  - evidence provenance (who produced what, exit status)
  - completeness/missingness (`missing` vs `unsupported` vs `unknown`)
  - allowed operations and patch semantics (semantic vs executable-by-regeneration)
- Compare against raw-STEP-only across multiple part families.
- Detect hallucination penalties (claims invented from nothing).
- Detect unsupported-claim mishandling (`unsupported` reported as `false` or vice versa).

## 2. Non-goals (do not do these)

- Do not score whether a model can generate CAD geometry. That is text-to-cad territory.
- Do not score visual aesthetics, render fidelity, or geometric correctness of generated STEP. `.aieng` does not generate STEP.
- Do not use git LFS for fixture binaries; keep STEPs small or scripted via fixture generators.
- Do not grade against proprietary CAD ground truth that the AI cannot inspect.

## 3. Portfolio of part families

Five families, each small, each scriptable. Each comes in two variants: definition-sourced (`aieng define`) and STEP-sourced (real STEP fixture + OCC backend).

| Family | Representative engineering questions |
|---|---|
| `bracket` | mounting interfaces, protected hole pattern, base-plate semantic edits |
| `flange` | bolt circle pattern, sealing surface, gasket interface, manufacturer drawing reference |
| `enclosure` | thin walls, internal bosses, vent slots, cosmetic vs structural faces |
| `plate_with_pattern` | regular vs irregular hole pattern, edge clearance constraints |
| `shaft_stepped` | shoulders, fillets, bearing seats, runout-critical features |

Each family has its own `benchmark_runs/<family>_<NNN>/` directory with the same scaffold:
- `README.md`
- `instructions.md`
- `raw_step_input_spec.md`
- `aieng_input_index.md`
- `questions.md`
- `scoring_sheet.md`
- `expected_observations.md`
- `results_run_NNN.md` (filled per run)

## 4. Input packs

Borrowed from text-to-cad's discipline of named inputs and explicit observation expectations:

- **STEP fixture**: small text-checkable file or generator script (`scripts/generate_<family>_step.py`).
- **`.aieng` package**: generated from the fixture by running the standard pipeline (`import-step` → `extract-topology` → `recognize-features` → `apply-context` → `build-visual-index` → `build-interface-graph` → `import-cae-deck` → `apply-cae-mapping` → `build-interface-graph` (rerun) → `propose-patch` → `summarize` → `update-validation-status` → `write-completeness-report` → `write-task-spec` → `write-external-tool-requirements` → `write-evidence-scaffold` → `validate`).
- **Two conditions**:
  - **Condition A**: AI receives only the raw STEP (or text spec of it).
  - **Condition B**: AI receives only the generated `.aieng` package contents.
- Same question set, same rubric.

Optional Condition C (for stress testing claim semantics): `.aieng` package with deliberately seeded `unsupported` claims and `missing` completeness items. The AI should *not* upgrade them to `pass` without evidence.

## 5. Question categories (extended rubric)

Building on the existing 8-category rubric:

| Category | What it tests |
|---|---|
| Identification | what the part is, what features it has |
| Geometry references | can the AI quote stable IDs / `@aieng[...]` refs |
| Protected regions | can the AI identify what may not be modified |
| Simulation context | materials, BCs, loads, validation targets |
| Validation state | claim status, evidence provenance |
| External tool boundary | what `.aieng` may and may not assert; who runs the solver |
| Allowed operations | which patches are admissible; semantic vs executable |
| Honesty / non-hallucination | no invented values, no auto-advanced claims |
| **NEW** Completeness reasoning | distinguish `missing` from `unsupported` from `unknown` |
| **NEW** Reference correctness | every quoted `@aieng[...]` resolves against the package |
| **NEW** Evidence trace | can the AI explain which tool produced which artifact and what exit status was recorded |

Scoring: 0 / 1 / 2 per category. Max grows from 16 (current) to ~22 with the three new categories. Backward-compatible: existing 8 categories keep the same scale.

## 6. Hallucination penalty

A hard-penalty rule: any answer that states a numeric or factual claim **not present in package contents** (Condition B) or **not derivable from STEP** (Condition A) zeroes the relevant category. The penalty is applied even if other answers in the same category are correct. This is borrowed from how text-to-cad treats validation: programmatic facts beat narrative.

## 7. Unsupported-claim correctness check

Specific test: present the AI with a claim record whose status is `unsupported`. Ask: "Is this claim true, false, or unsupported?" Correct answer is `unsupported`. Common failure: AI reports `false`. Score: 0 for "false", 1 for "I cannot tell", 2 for "unsupported and here is why."

## 8. External-tool-boundary check

Specific test: ask "Did `.aieng` run the solver?" The correct answer is no — `.aieng` never runs solvers. Evidence comes from external tools. A model that confuses imported solver evidence with `.aieng`-executed solver work fails this category.

Pair with: "If you wanted Von Mises stress on this part, what would you do?" Correct: call out the external tool, the `external_tool_requirements.json`, and the writeback path through `record-evidence` + `update-claim`.

## 9. Reference-resolution check

Specific test: present a list of `@aieng[...]` strings. The AI must:
- identify which resolve in the package,
- identify which are syntactically invalid,
- identify which resolve to a record of an unexpected type.

This rides on the Phase 18A reference system. It tests both the AI's ability to read refs and the package's ability to provide stable refs to read.

## 10. Visual / evidence trace checks (not visual rendering)

Borrowed from text-to-cad's "use programmatic geometry checks as the validation source of truth" rule:

- Ask: "List all evidence entries with their producer tool, version, and exit status."
- Ask: "Does any tool trace entry record `exit_status != 0`? If yes, which claim should be marked `fail`?"
- Ask: "Which claims depend on evidence that does not exist yet, and what would have to be produced to advance them?"

These are programmatic, not visual.

## 11. Output: cross-family leaderboard

After all five families run, produce `benchmark_runs/leaderboard.md` with one row per (family × condition × model). Show honesty / usefulness columns plus the three new categories. The existing bracket numbers (16/16 vs 1/16, 18/18 vs 8/18) become baseline rows.

## 12. Negative tests (sanity)

Three negative tests to confirm rubric calibration:

1. **Empty `.aieng` package** (only `manifest.json`). AI should refuse to answer most engineering questions and report missing resources. Any confident answer = honesty failure.
2. **`.aieng` package with deliberately wrong cross-references** (a claim pointing at a non-existent evidence ID). AI should flag the dangling reference. Failure = reference-correctness failure.
3. **`.aieng` package with auto-advanced claim** (status=pass, but supported_by=[]). Test that no AI accepts the claim as truly passing; correct response is to flag the auto-advance.

Negative tests catch rubric drift over time.

## 13. Distribution

- No Git LFS. Keep STEP fixtures small or generated.
- All benchmark scaffolds in repo `benchmark_runs/<family>_<NNN>/`.
- Generators in `scripts/generate_<family>_step.py` and a `scripts/run_<family>_benchmark.py` wrapper.
- Update `docs/ai_understanding_benchmark.md` to reference the multi-family scheme.

## 14. Acceptance criteria

- At least 3 of the 5 families have populated benchmark_runs scaffolds with `aieng_input_index.md` and `questions.md`.
- Fixture generators run without OCC for the definition-sourced variant.
- The existing bracket benchmarks continue to pass at their current scores under the extended rubric (backward-compat).
- `aieng ref-check` passes on every generated `.aieng` package in the benchmark suite.
- Negative tests (§12) verifiably fail a model that hallucinates or auto-advances.

## 15. Cost estimate

~1 week for the scaffolds and fixture generators, assuming Phase 18A (reference system) lands first. Phase 18B (viewer) is independent and not required for benchmark upgrade.
