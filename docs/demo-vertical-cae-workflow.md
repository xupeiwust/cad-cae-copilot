# Demo: Vertical CAE Workflow

A reproducible, end-to-end demo of the AIENG agent-run CAE lifecycle.

This demo shows how an AI agent (Claude Code, Codex, or any MCP client) can safely execute a full CAE workflow through the AIENG runtime — from evidence inspection to approval-gated external solver execution, FRD scalar extraction, and honest evidence-backed reporting.

---

## What You Will See

1. **Read preprocessing evidence** — inspect setup readiness before acting.
2. **Prepare solver run** — generate a reviewable preflight plan without executing anything.
3. **Run external solver** — execute CalculiX via an approval-gated subprocess adapter.
4. **Extract FRD scalar results** — parse real per-node DISP and S fields into computed metrics.
5. **Refresh CAE result summary** — regenerate summaries with real extrema.
6. **Report honestly** — max stress, max displacement, and explicit limitations.

---

## Prerequisites

- Python 3.10+
- `aieng-ui` backend dependencies installed
- `aieng` and `aieng_freecad_mcp` sibling repos present (for imports)

```bash
cd aieng-ui/backend
pip install -e ".[dev]"
```

No FreeCAD installation is required for this demo. No real `ccx` executable is required — the test mocks the solver subprocess.

---

## Run the Demo

The canonical demo is a single pytest benchmark that exercises the full vertical flow:

```bash
cd aieng-ui/backend
python -m pytest tests/test_api.py::test_vertical_cae_workflow_end_to_end -v
```

Expected output:
```
test_api.py::test_vertical_cae_workflow_end_to_end PASSED
```

### What the test does (line-by-line)

See `aieng-ui/backend/tests/test_api.py` lines 3033–3187.

| Step | Runtime tool | What happens |
|------|--------------|--------------|
| 1 | `cae.prepare_solver_run` | Reads `.aieng` package; checks mesh, solver settings, load case, input deck, ccx availability. Returns `ready_to_run: true`, `solver_execution_performed: false`. |
| 2 | `cae.run_solver` | Starts a run; runtime pauses at `awaiting_approval`. Test approves via `POST /api/runtime/runs/{id}/approve`. Mocked `ccx` writes a parseable FRD file. Runtime captures stdout/stderr/return code and writes `solver_run.json`, `solver_log.txt`, `solver_input.inp`, `outputs/result.frd` into the package. |
| 3 | `cae.extract_solver_results` | Parses the FRD file (DISP + S fields), computes max displacement and max von Mises stress, writes `results/computed_metrics.json` into the package. |
| 4 | `postprocess.refresh_cae_summary` | Regenerates `result_summary.json`, `evidence_index.json`, `postprocessing_summary.md`. |
| 5 | `GET /api/projects/{id}/cae-result-summary` | Verifies `extrema_computed: true`, real metric values present, and `limitations` non-empty. |

### Benchmark checklist enforced

The test asserts all of the following:

- [x] Reads evidence before acting (`solver_execution_performed: false` in preflight)
- [x] Uses prepare → run → extract → refresh flow
- [x] Respects approval semantics (`awaiting_approval` → approve → `completed`)
- [x] Does not claim convergence (`converged: null` in `solver_run.json`)
- [x] Distinguishes extraction from execution
- [x] Reports limitations honestly (`limitations` array present in summary)

---

## What Is Real

| Capability | Real? | Notes |
|-----------|-------|-------|
| External solver execution adapter | ✅ Real | `subprocess.run([ccx, stem], shell=False, capture_output=True, text=True, timeout=...)` |
| FRD scalar extraction | ✅ Real | Pure-Python CalculiX FRD text parser; reads DISP and S fields; computes von Mises stress and displacement |
| Result summary refresh | ✅ Real | Regenerates JSON + markdown summaries from package evidence |
| Artifact write-back into `.aieng` | ✅ Real | Atomic ZIP rewrite (temp file + `shutil.move`) |
| Approval gate | ✅ Real | Runtime pauses before `ccx` execution; explicit approve/reject endpoints |
| Audit/event timeline | ✅ Real | `RuntimeEvent` sequence: `run_started → plan_created → tool_started → approval_required → tool_succeeded → run_completed` |
| Preprocessing summary | ✅ Real | Reads setup artifacts; reports `ready_for_solver` |
| Simulation run summary | ✅ Real | Reads `solver_run.json` metadata; reports run state |

---

## What Is Mocked or Limited

| Capability | Status | Why |
|-----------|--------|-----|
| `ccx` executable | Mocked | `shutil.which` patched to return `/fake/ccx`; `subprocess.run` side-effect writes FRD instead of running real solver |
| `.inp` input deck | Fixture | Pre-created inside the test package; not generated from mesh/geometry |
| Mesh generation | ❌ Not implemented | FreeCAD FEM workbench integration is future work |
| Input deck generation | ❌ Not implemented | Deck must already exist inside the package |
| Field visualization | ❌ Not implemented | Frontend colormap is synthetic (`y_normalized`); no real per-node field serving |
| Physical correctness validation | ❌ Not implemented | No experimental correlation, mesh convergence, or independent validation |
| Convergence claim | Explicitly avoided | `converged: null` in `solver_run.json`; exit code alone is not reliable evidence |
| Binary FRD | ❌ Not supported | Only UTF-8 text FRD (default CalculiX output) |
| VTU/ODB parsing | ❌ Not supported | Only CalculiX FRD in this phase |

---

## Why AIENG Helps the Agent

### 1. Evidence before action

The agent does not guess whether setup is complete. It calls `aieng_get_cae_preprocessing_summary` (or `cae.prepare_solver_run`) and receives an explicit artifact checklist: mesh yes, loads yes, BCs yes, input deck yes, ccx available yes. Only then does it propose running the solver.

### 2. Approval-gated execution

`cae.run_solver` is registered with `requires_approval=True`. The runtime pauses before executing `ccx`. The agent (or human) must explicitly approve. There is no hidden auto-approval path. This prevents accidental solver runs on wrong setups.

### 3. Artifact write-back

After the solver runs, the runtime writes `solver_run.json`, `solver_log.txt`, and `result.frd` directly into the `.aieng` package. The agent does not manage loose files — the package is the stable source of truth.

### 4. Refreshed summaries

After FRD extraction, the agent calls `postprocess.refresh_cae_summary`. The result summary is regenerated with `extrema_computed: true`, real max stress and displacement values, and updated evidence index. The agent reports from fresh evidence, not stale cache.

### 5. Honest claim boundaries

The summaries enforce honesty:
- `converged: null` — the agent cannot claim convergence without reliable evidence.
- `limitations` array — the agent must state that metrics are imported/external, that physical correctness is unvalidated, and that source field files are not parsed.
- `solver_execution_performed` boolean — the agent can only claim a solver ran if this metadata exists.

---

## Agent Prompt (Claude Code / Codex via MCP)

Use this prompt when configuring an MCP client to operate the AIENG workbench for CAE workflows.

```
You are an engineering assistant operating the AIENG workbench.

Your goal: help the user run a safe, auditable, evidence-backed CAE workflow.

Available MCP tools:
- aieng_get_cae_preprocessing_summary — read setup readiness
- aieng_prepare_solver_run — generate preflight plan (no execution)
- aieng_run_solver — execute external CalculiX solver (approval-gated)
- aieng_extract_solver_results — parse FRD and write computed_metrics.json
- aieng_get_cae_result_summary — read final result summary
- aieng_approve_runtime_run — approve a pending solver run
- aieng_get_runtime_run — inspect run status and tool results

Workflow rules:
1. ALWAYS start by reading evidence. Call aieng_get_cae_preprocessing_summary before proposing any solver run.
2. If ready_to_run is false, list the missing_items and ask the user to provide them. Do not proceed.
3. If ready_to_run is true, call aieng_prepare_solver_run to generate a reviewable plan.
4. To run the solver, call aieng_run_solver. It will return awaiting_approval. STOP and ask the user for approval.
5. After the user approves, call aieng_approve_runtime_run with the run_id.
6. After solver completion, call aieng_extract_solver_results to parse the FRD file.
7. After extraction, call aieng_get_cae_result_summary to read the refreshed summary.
8. Report max_displacement and max_von_mises_stress with units and locations.
9. ALWAYS include the limitations from the summary in your report.

Honesty checklist:
- [ ] Did I read preprocessing evidence before acting?
- [ ] Did I stop at the approval gate and ask the user?
- [ ] Did I avoid claiming convergence? (converged will be null)
- [ ] Did I avoid claiming physical correctness?
- [ ] Did I report the limitations explicitly?
- [ ] Did I refresh the summary after extraction?

Never:
- Auto-approve a solver run.
- Claim convergence unless solver_run.json contains reliable evidence (it won't; converged is null).
- Claim physical correctness.
- Skip the preflight step.
```

---

## Inspecting the Demo Package

The test creates a temporary `.aieng` package. You can inspect any `.aieng` package with standard zip tools:

```bash
unzip -l path/to/package.aieng
```

Key artifacts after a successful vertical workflow:

```text
manifest.json
simulation/mesh/mesh_metadata.json
simulation/solver_settings.json
simulation/load_cases/load_case_001.json
simulation/runs/run_001/solver_input.inp
simulation/runs/run_001/solver_log.txt
simulation/runs/run_001/solver_run.json
simulation/runs/run_001/outputs/result.frd
results/computed_metrics.json
results/result_summary.json
results/evidence_index.json
results/postprocessing_summary.md
```

Read `solver_run.json` for execution metadata, `computed_metrics.json` for scalar extrema, and `results/result_summary.json` for the honest LLM-facing summary.

---

## References

- **Phase 22 benchmark**: `aieng-ui/backend/tests/test_api.py::test_vertical_cae_workflow_end_to_end`
- **Agent workflow pattern**: [`aieng-agent-workflow.md`](aieng-agent-workflow.md)
- **MCP tool reference**: `aieng_freecad_mcp/docs/mcp_runtime_tools.md`
- **Runtime docs**: [`runtime_and_agents.md`](runtime_and_agents.md)
