# AIENG Agent Workflow Pattern

A reusable, evidence-backed workflow for AI agents operating the AIENG engineering workbench.

---

## What AIENG Is (and Is Not)

| AIENG is | AIENG is not |
|----------|--------------|
| An **evidence/grounding layer** — every claim is backed by artifacts inside a versioned `.aieng` package | A **solver** — solvers run externally; AIENG only ingests their outputs |
| A **semantic package engine** — STEP import, topology, features, enrichment, validation, claim maps | A **CAD kernel** — geometry execution is delegated to FreeCAD or future adapters |
| A **runtime orchestrator** — safe, approval-gated, auditable tool execution with artifact write-back | **Only a UI** — the web app is one client; agents, CLI scripts, and MCP clients use the same runtime |
| An **honest broker** — limitations are explicit, convergence is never claimed without evidence, downstream evidence is marked stale after setup changes | An **autonomous designer** — all edits are explicit, reviewable, and logged |

---

## Component Roles

### 1. AIENG (`.aieng` package engine)

- Owns the **artifact contract**: `manifest.json`, topology, features, CAE scaffold, evidence ledger, claim map.
- Reads and writes `.aieng` ZIP packages atomically (temp file + `shutil.move`).
- Produces **honest summaries**: preprocessing summary, simulation run summary, result summary — all with explicit `limitations` fields.
- Does **not** execute FreeCAD, run solvers, or host the web server.

### 2. Workbench Runtime (`aieng-ui` backend)

The runtime is the **authoritative execution layer** for both the web UI and external agents.

- **Safe execution**: every tool call is a declared, auditable step inside a `RunRecord`.
- **Approval gates**: tools like `cae.run_solver` and `freecad.run_macro` pause with `awaiting_approval` until a human (or explicit agent approval) resumes them.
- **Audit/events**: every run produces an ordered `RuntimeEvent` timeline (`run_started → plan_created → tool_started → tool_succeeded → run_completed`).
- **Artifact write-back**: changed artifacts are written into the `.aieng` package atomically; loose files are not the source of truth.
- **Stale evidence tracking**: after setup patches, downstream summaries are marked stale until explicitly refreshed.

### 3. MCP Adapter (`aieng_freecad_mcp`)

- MCP is a **protocol adapter**, not the orchestration layer.
- Exposes runtime tools as MCP tools (`aieng_start_runtime_run`, `aieng_run_solver`, etc.) that delegate 1:1 to the `aieng-ui` REST API.
- No business logic is reimplemented in the MCP layer; it is a thin HTTP wrapper.

### 4. Future Skill (agent teaching layer)

A Skill (e.g. for Claude Code / Codex) will teach the LLM:

- The **correct order of operations** for CAE workflows.
- To **read evidence before acting** — inspect the package, then decide.
- To **respect approval gates** — never bypass `requires_approval` tools.
- To **report limitations honestly** — never claim convergence or physical correctness without explicit evidence.
- To **mark stale evidence** — after setup changes, refresh dependent summaries before reporting results.

---

## Vertical CAE Workflow Sequence

The canonical agent-run CAE lifecycle, demonstrated end-to-end in `aieng-ui/backend/tests/test_api.py::test_vertical_cae_workflow_end_to_end`.

```text
1. Read preprocessing summary
   └─► GET /api/projects/{id}/cae-preprocessing-summary
   └─► Understand setup state: materials, loads, BCs, mesh, solver settings
   └─► Check ready_for_solver

2. Prepare solver run
   └─► cae.prepare_solver_run
   └─► Reads .aieng evidence; returns preflight plan
   └─► ready_to_run, ccx_available, planned_artifacts
   └─► solver_execution_performed = false

3. Run external solver (approval-gated)
   └─► cae.run_solver
   └─► Requires explicit approval (requires_approval=True)
   └─► Runtime pauses at approval_required event
   └─► Upon approval: executes ccx subprocess (shell=False), captures stdout/stderr/return code
   └─► Writes artifacts: solver_run.json, solver_log.txt, solver_input.inp, outputs/result.frd
   └─► converged = null (honest — exit code alone is not reliable evidence)

4. Extract FRD scalar results
   └─► cae.extract_solver_results
   └─► Parses CalculiX FRD text format (DISP + S fields)
   └─► Computes max von Mises stress and max displacement
   └─► Writes results/computed_metrics.json into .aieng package

5. Refresh CAE result summary
   └─► postprocess.refresh_cae_summary
   └─► Regenerates result_summary.json, evidence_index.json, postprocessing_summary.md
   └─► computed_values.extrema_computed = true

6. Report evidence-backed result
   └─► Read GET /api/projects/{id}/cae-result-summary
   └─► Report max stress / max displacement with units and locations
   └─► Include limitations: imported/external metrics, no convergence claim
```

---

## Claim Boundaries

Agents must never make claims that exceed the available evidence.

| Claim | Required Evidence | What to Say If Missing |
|-------|-------------------|------------------------|
| "Solver executed" | `solver_run.json` exists with `solver_execution_performed=true` and matching `run_id` | "No solver execution metadata found." |
| "Converged" | Reliable convergence evidence (e.g. residual history, energy norm) in solver output | `converged=null`; state: "Convergence status is unknown." |
| "Physical correctness" | Independent validation run, mesh convergence study, experimental correlation | Never claim this. State: "Physical correctness has not been validated." |
| "Max stress is X" | `computed_metrics.json` with `max_von_mises_stress.value`, `unit`, `location` | "No computed metrics available." |
| "Setup is complete" | `preprocessing_summary.json` with `ready_for_solver=true` | List `missing_items` from preprocessing summary. |

### Stale Evidence Rule

After any setup change (patch, load case edit, material update, mesh regeneration), downstream evidence becomes stale:

- `result_summary.json` must be regenerated before reporting new results.
- `simulation_run_summary.json` remains valid for old runs, but a new run supersedes it.
- Always refresh summaries after setup patches before making new claims.

---

## Sample Agent Prompt

Use this prompt template when configuring an agent (Claude Code, Codex, etc.) to operate the AIENG workbench:

```
You are an engineering assistant operating the AIENG workbench.

Rules:
1. Always read evidence before acting. Start by inspecting the .aieng package or calling the relevant summary endpoint.
2. Use the runtime tools in the correct order:
   - Preprocessing → prepare solver run → run solver (approve) → extract results → refresh summary → report.
3. Respect approval gates. If a tool returns awaiting_approval, stop and ask the user for approval. Do not auto-approve.
4. Never claim convergence unless solver_run.json contains reliable convergence evidence (it usually won't; converged will be null).
5. Never claim physical correctness. Solver execution does not mean the result is physically correct.
6. Report limitations explicitly: state whether metrics are imported, whether convergence is unknown, and what setup items are missing.
7. After any setup change, refresh dependent summaries before reporting results.

Available MCP/runtime tools:
- aieng.inspect_package — read full project state
- cae.prepare_solver_run — preflight, no execution
- cae.run_solver — approval-gated external CalculiX execution
- cae.extract_solver_results — FRD scalar extraction
- postprocess.refresh_cae_summary — regenerate summaries
- cae.apply_setup_patch — controlled setup edits

Honesty checklist before answering:
- [ ] Did I read the latest evidence?
- [ ] Did I respect the approval gate?
- [ ] Did I avoid claiming convergence without evidence?
- [ ] Did I avoid claiming physical correctness?
- [ ] Did I list limitations?
- [ ] Did I refresh stale summaries after setup changes?
```

---

## Reference

- **Phase 22 benchmark**: `aieng-ui/backend/tests/test_api.py::test_vertical_cae_workflow_end_to_end` — full 4-step vertical flow with mocked ccx, FRD extraction, and honest limitations enforcement.
- **Runtime docs**: [`runtime_and_agents.md`](runtime_and_agents.md) — REST API, event model, approval gates.
- **System architecture**: [`system_architecture.md`](system_architecture.md) — three-repo responsibility map.
- **Repo boundaries**: [`repo_boundaries.md`](repo_boundaries.md) — what each repo owns and does not own.
