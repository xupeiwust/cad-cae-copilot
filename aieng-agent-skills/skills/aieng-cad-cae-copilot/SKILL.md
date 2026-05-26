---
name: aieng-cad-cae-copilot
description: evidence-first cad-cae workflow skill for ai agents operating the aieng workbench runtime and mcp bridge. use when the user asks to inspect cae state, patch setup artifacts, prepare or run external solver workflows, extract frd scalar metrics, and report results with explicit limitations. do not use for creating new solver/cad capabilities, meshing, input-deck generation, schema edits, or field visualization.
---

# aieng-cad-cae-copilot

Reusable agent workflow prototype for the vertical CAE MVP.

This skill teaches behavior and order of operations only. It does not add tools,
does not add solver logic, and does not change schema contracts.

Skill version: `0.1.0`

## Purpose

- Use AIENG evidence as the source of truth.
- Execute only through workbench runtime / MCP tools.
- Preserve approval-gated safety for external solver execution.
- Report only evidence-backed claims and explicit limitations.

## When To Use / When Not To Use

Use when the user asks to:

- inspect CAE readiness or run/result status,
- patch CAE setup artifacts,
- prepare or run a solver workflow,
- extract FRD scalar metrics and review refreshed summaries.

Do not use when the user asks to:

- add new CAD/CAE/solver features,
- generate mesh or input decks,
- perform full-field visualization/postprocessing,
- change AIENG schemas or runtime tool contracts.

## System Roles (must be reflected in responses)

- AIENG: evidence and package semantics.
- Skill: operation order and claim discipline.
- Workbench runtime: safe execution, approvals, artifact write-back.
- MCP bridge: thin agent-facing wrappers around runtime capabilities.
- External CAD/CAE/postprocessors: real modeling, solving, heavy postprocessing.

## Operating Rules

1. Read evidence before acting.
2. Identify exact `project_id`, artifact paths, `run_id`, `load_case_id`, and tool input keys before execution.
3. Use preflight first (`aieng_prepare_solver_run`) before any solver run.
4. Respect approval gates; never bypass approval.
5. Refresh/re-read summaries after mutating actions.
6. Call out `stale_artifacts` explicitly after setup changes.
7. Report only evidence-backed claims.

## Canonical Workflow

### A. Inspect current engineering state

1. Call `aieng_get_cae_preprocessing_summary`.
2. Call `aieng_get_cae_simulation_run_summary`.
3. Call `aieng_get_cae_result_summary`.
4. If summary statements are ambiguous, inspect referenced artifacts by exact path before concluding.
5. State readiness and limitations using evidence text, not assumptions.

### B. Apply CAE setup patch

1. Read preprocessing evidence first to justify the patch.
2. Identify exact target artifact path and JSON pointer.
3. Call `aieng_apply_cae_setup_patch` with explicit patch operations.
4. Review returned `artifact_diffs` / changed artifacts and confirm intended keys changed.
5. Surface `stale_artifacts` as downstream-invalidated evidence.
6. Re-read preprocessing summary (and later result summary) before claiming updated state.

### C. Solver workflow

1. Call `aieng_prepare_solver_run` first.
2. If not ready, list missing evidence/artifacts and stop.
3. If ready, request approval context and call `aieng_run_solver`.
4. If run enters `awaiting_approval`, stop and ask for approval; never auto-approve or bypass.
5. Do not claim solver execution unless solver-run metadata/artifacts exist.
6. Do not claim convergence unless reliable convergence evidence exists.

### D. Result review

1. If computed metrics are missing/outdated, call `aieng_extract_solver_results`.
2. Re-read `aieng_get_cae_result_summary` after extraction/refresh.
3. Report `max_von_mises_stress` and `max_displacement` only when present in evidence.
4. Include source and limitation notes (for example extraction scope, unknown convergence).

### E. Stale evidence handling

1. Any setup patch can stale downstream run/result evidence.
2. Treat old summaries as historical, not current, after setup changes.
3. Require rerun/import evidence before treating old results as valid for changed setup.
4. Explicitly list stale paths and required refresh/rerun actions.

## Honest Reporting Contract

Always run this checklist before final response:

- [ ] AIENG is not a solver.
- [ ] AIENG is not a CAD kernel.
- [ ] Solver execution is external.
- [ ] FRD parsing is scalar extraction, not full field postprocessing.
- [ ] Artifact-based readiness is not physical validation.
- [ ] Metadata-based run summary is not proof of convergence.
- [ ] No physical correctness claim without external validation evidence.

## Response Template (concise)

1. Current evidence state (`project_id`, key artifacts, readiness).
2. Actions taken (tool call order and key inputs).
3. Approval boundary status (`awaiting_approval`, approved, or not requested).
4. Updated evidence (`run_id`, changed artifacts, stale artifacts, refreshed summaries).
5. Evidence-backed results (`max_von_mises_stress`, `max_displacement`) when present.
6. Limitations and unknowns.

## Sample Agent Prompt (MCP tool names)

```text
You are operating the AIENG CAE workflow.

Rules:
1) Read evidence first.
2) Identify exact project_id, artifact paths, run_id, load_case_id, and tool inputs before execution.
3) Use preflight before solver run.
4) Respect approval gates; never bypass.
5) Refresh/re-read summaries after mutating actions.
6) Report only evidence-backed claims.

Primary tools:
- aieng_get_cae_preprocessing_summary
- aieng_get_cae_simulation_run_summary
- aieng_get_cae_result_summary
- aieng_apply_cae_setup_patch
- aieng_prepare_solver_run
- aieng_run_solver
- aieng_extract_solver_results

Workflow:
- Inspect state with the three summary tools.
- If setup changes are needed, patch with aieng_apply_cae_setup_patch and report stale_artifacts.
- Before execution, call aieng_prepare_solver_run.
- Run solver only with approval via aieng_run_solver flow.
- Extract metrics via aieng_extract_solver_results when needed.
- Re-read aieng_get_cae_result_summary and report only present evidence fields.
```

## Source References

- `docs/aieng-agent-workflow.md`
- `docs/demo-vertical-cae-workflow.md`
- `aieng-ui/docs/quickstart-vertical-cae-demo.md`
- `aieng_freecad_mcp/docs/mcp_runtime_tools.md`
