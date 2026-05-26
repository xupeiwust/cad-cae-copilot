---
name: aieng-closed-loop-copilot
description: closed-loop cad/cae copilot skill that proposes ranked cad modifications, verifies them through the pre-execution gate, applies the surviving change via the workbench runtime, re-runs the solver, and reports whether the design target was met. use when the user asks to improve a design against a stated target (mass reduction, safety factor, etc.) and has an already-solved baseline. do not use for one-off inspection, schema edits, or creating brand-new geometry.
---

# aieng-closed-loop-copilot

Reusable agent workflow that closes the loop on
recommend → verify → execute → re-simulate → compare. Builds on
`aieng-cad-cae-copilot` for the underlying CAE pipeline and adds the
trust-gated proposal/verification layer introduced in Phases 36 and 37.

This skill teaches behavior and order of operations only. It does not
add tools, does not implement ranking heuristics, and does not change
schema contracts.

Skill version: `0.1.0`

## Purpose

- Operate on packages that already have a solved baseline (computed
  metrics + per-feature stress + design targets).
- Use the recommendation primitive to enumerate ranked CAD modification
  candidates.
- Use the verification gate to eliminate candidates whose predicted
  behaviour violates manufacturability, preserved-interface, or
  safety-factor constraints before any CAD execution.
- Apply only one surviving proposal per loop iteration, re-simulate,
  and compare against the design targets.
- Stop on target met, no improvement, or budget exhausted — never
  bypass the verification gate or auto-approve solver runs.

## When To Use / When Not To Use

Use when the user asks to:

- iteratively improve a design against stated targets,
- propose CAD changes grounded in CAE evidence,
- preview what the verification gate would block before execution,
- run a small, bounded number of closed-loop iterations.

Do not use when the user asks to:

- author new geometry from scratch (use `aieng-cad-authoring`),
- only inspect or patch CAE setup (use `aieng-cad-cae-copilot`),
- bypass the verification gate ("just apply this proposal anyway"),
- advance engineering claims based on heuristic predictions.

## System Roles

- **AIENG**: source of truth for evidence, design targets, computed
  metrics, and the ranking/verification logic.
- **Skill**: operation order, stop conditions, claim discipline.
- **Workbench runtime (`aieng-ui`)**: approval-gated execution of
  `cad.edit_parameter`, mesh, solver, post-processing.
- **MCP bridge (`aieng_freecad_mcp`)**: read-only wrappers over the
  recommend + verify CLI plus the existing CAE lifecycle tools.

## Operating Rules

1. **Read evidence before acting.** Confirm the package has design
   targets, computed metrics, and per-feature stress.
2. **Never bypass the verification gate.** Apply only proposals whose
   verdict is `pass` (or `warn` with explicit user acknowledgement of
   the surfaced risk in non-strict mode).
3. **One change per iteration.** Apply a single proposal, re-simulate,
   then compare. Do not chain multiple proposals before re-simulation —
   the gate's predictions are not composable.
4. **Respect approval gates.** Solver runs go through
   `aieng_run_solver`; never auto-approve.
5. **Stop on target met / no improvement / budget exhausted.**
   Loop budget is bounded (default: 3 iterations) and must be declared
   up front.
6. **Report only evidence-backed claims.** A `pass` verdict is a
   prediction, not a guarantee. The target is only met when
   `aieng_read_design_target_comparisons` confirms it after
   re-simulation.

## Canonical Workflow

### 0. Bound the loop

Before any tool call, state:

- The package path.
- The design target(s) being optimised against.
- The iteration budget (default 3).
- The verification strictness (default `default`; `strict` for safety-
  critical work).

### 1. Confirm baseline evidence

1. Call `aieng_get_cae_result_summary` and confirm
   `computed_values.extrema_computed == true`.
2. Call `aieng_read_design_targets` and confirm the relevant targets
   are present.
3. Call `aieng_read_design_target_comparisons` to read the current
   pass/fail state. If the target is already `pass`, report and stop —
   no work needed.

### 2. Recommend candidates

1. Call `aieng_recommend_cad_modifications(package_path)`.
2. Inspect the returned `proposals` block. Each proposal carries
   `rank`, `feature_ref`, `action_type`, `parameter_change`,
   `confidence`, `targets_addressed`, and `risks`.
3. Surface the ranked list to the user with the recommendation's
   `llm_summary.one_line` plus the top three proposals.

### 3. Apply the verification gate

1. Call `aieng_verify_cad_modifications(package_path, strictness=...,`
   `proposals=<the recommendation payload>)`.
2. Discard every proposal whose `verdict == "fail"`. For each
   discarded proposal, surface the failing check IDs so the user can
   see the trust-layer reasoning (e.g.
   `regression.thinning_sf_floor`, `manufacturability.parameter_floor`,
   `schema.preserved_feature_not_modified`).
3. From the surviving proposals (`verdict in {"pass", "warn"}`),
   choose the highest-ranked candidate (lowest `rank` integer).
4. If no proposals survive, report the trust-layer rejection and stop.

### 4. Execute the surviving proposal

1. Confirm the chosen proposal with the user before execution.
2. Start a runtime run that calls `cad.edit_parameter` with the
   selected `feature_ref` and `parameter_change`. Approval-gated.
3. After execution, refresh artifact state by calling
   `postprocess.refresh_cae_summary` and re-reading
   `aieng_get_cae_preprocessing_summary`. Treat all downstream solver
   results as stale until re-simulated.

### 5. Re-simulate

1. Call `aieng_prepare_solver_run` to confirm readiness.
2. If `ready_to_run`, request approval and call `aieng_run_solver`.
3. After approval and run completion, call
   `aieng_extract_solver_results` to refresh computed metrics.
4. Call `aieng_get_cae_result_summary` to confirm
   `extrema_computed: true` with the new values.

### 6. Compare and decide

1. Use the `aieng compare-design-targets` workflow (or
   `aieng_read_design_target_comparisons` after a
   `compare-design-targets --write-summary` step) to evaluate the
   target state post-change.
2. If every relevant target is now `pass`, **stop and report success**.
3. If any target is still `fail`, decide whether to continue:
   - If iteration budget remaining > 0 and the failing target's gap
     has shrunk, **return to step 2**.
   - If the gap did not shrink (or got worse), **stop**. Report the
     regression honestly; do not advance claims and recommend a manual
     review.

## Stop Conditions

The loop terminates on any of:

1. **Target met** — every relevant target is `pass` in the post-change
   comparison.
2. **No surviving proposal** — the verification gate rejected all
   candidates. Report each rejection with its failing check IDs.
3. **No improvement** — a completed iteration did not reduce the gap
   on the failing target.
4. **Budget exhausted** — iteration counter reached its bound.
5. **Approval denied** — the runtime user rejected the solver run or
   the CAD edit. Do not retry without explicit re-authorisation.

## Honest Reporting Contract

Before each final response, walk through this checklist:

- [ ] Phase 36 produced hypotheses; predictions are not solver
  evidence.
- [ ] Phase 37 verdicts are heuristic; a `pass` verdict is a prediction,
  not a certification.
- [ ] Geometry-kernel validity is not checked by the current verifier
  (`geometry_kernel_checks_not_performed: true`).
- [ ] Only re-simulated, evidence-backed comparisons can be reported
  as outcomes.
- [ ] No claim was advanced. `claim_map.json` is unchanged.
- [ ] Solver execution remained approval-gated.

## Response Template

1. Loop setup (package, target, budget, strictness).
2. Iteration log: per-iteration recommendation top-3, verification
   verdicts (with blocker reasons for failures), chosen proposal,
   solver run id, post-change comparison.
3. Termination reason (one of the five above).
4. Evidence-backed final state (target pass/fail with cited values).
5. Limitations and unknowns.

## Tool Inventory

Primary new tools (Phases 36, 37, 38):

- `aieng_recommend_cad_modifications(package_path)`
- `aieng_verify_cad_modifications(package_path, strictness, proposals)`

Existing tools used by this skill (already taught by
`aieng-cad-cae-copilot`):

- `aieng_get_cae_preprocessing_summary`
- `aieng_get_cae_simulation_run_summary`
- `aieng_get_cae_result_summary`
- `aieng_read_design_targets`
- `aieng_read_design_target_comparisons`
- `aieng_prepare_solver_run`
- `aieng_run_solver` (approval-gated)
- `aieng_extract_solver_results`
- `cad.edit_parameter` (via `aieng-ui` runtime; approval-gated)

## Source References

- `aieng/docs/roadmap.md` — Phases 36 and 37 entries.
- `aieng/docs/workspace-roadmap.md` — system-level Phase 36 + 37 notes.
- `aieng_freecad_mcp/docs/mcp_runtime_tools.md` — MCP tool reference.
- `skills/aieng-cad-cae-copilot/SKILL.md` — the CAE lifecycle skill
  this skill builds on.
