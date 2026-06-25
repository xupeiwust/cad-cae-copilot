# Simulation runner sync/SSE consolidation audit (#183, #365)

Audit of the duplicated simulation / solver run-event paths after the MCP-first
cutover. The goal is one clear product contract for solver readiness, approval,
run events, and result reporting while preserving approval gating and
solver-result honesty.

## Paths that exist

| Path | Entry point | Role | Status |
|---|---|---|---|
| MCP `cae.prepare_solver_run` | `app/runtime_registry/cae.py` | Read-only preflight: checks readiness, records `recommended_next_calls`, runs no solver. | Canonical preflight |
| MCP `cae.run_solver` | `app/runtime_registry/cae.py` | Agent-driven solver execution on a pre-generated deck. `requires_approval=True`; enforces stale-topology hash checks; writes `simulation/runs/{run_id}/...` evidence. | Canonical execution |
| REST `POST /api/projects/{id}/run-simulation` | `app/routers/project_workflows.py` -> `simulation_runner.run_simulation` | Legacy all-in-one path: mesh, deck, solve, parse in one confirmed request. | Legacy API, retained |
| REST `POST /api/projects/{id}/run-simulation-stream` | `app/routers/project_workflows.py` -> `simulation_runner.run_simulation_stream` | SSE variant of the legacy all-in-one path. | Legacy API/test fixture, retained |

## Current verdict

- The user-facing and agent-facing CAE path is the MCP-first chain:
  `cae.prepare_solver_run` -> approval-gated `cae.run_solver`.
- The legacy REST sync/SSE paths are still registered because they have tests and
  some helper behavior remains useful for compatibility and migration. They are
  not the canonical product path.
- The frontend no longer has a live `runSimulationStream`, `executeSimulation`,
  or `simulationProgress` consumer.
- The deterministic `engineering_action_plan` no longer recommends
  `/run-simulation-stream`; simulation intents now point to the MCP tool chain.

## Finding 1: sync/SSE duplication and stale-topology honesty drift - fixed

`run_simulation` and `run_simulation_stream` used to duplicate the same pipeline
and had drifted: the sync path enforced `validate_cae_topology_references()`, but
the streaming path did not. A stale streaming run could therefore solve against
old face references and stream a wrong result as success.

Both entry points now delegate to `_run_simulation_core`, so the stale-topology
guard is shared. The sync wrapper drains core events and raises the historical
HTTP errors; the SSE wrapper formats the same events. Approval gating is
unchanged: the REST core still requires `confirmed=true`, and MCP
`cae.run_solver` still requires approval.

## Finding 2: dead frontend SSE consumer - fixed for the frontend/action-plan path

The embedded-chat-era frontend consumer for `/run-simulation-stream` has been
removed. Current frontend search shows no `runSimulationStream`,
`executeSimulation`, `simulationProgress`, or `run-simulation-stream` reference.

The remaining backend references are intentionally legacy/test coverage:

- `project_workflows.py` keeps the route registered.
- `simulation_runner.py` keeps the shared legacy implementation.
- `test_simulation_runner.py` / `test_simulation_stream.py` pin the compatibility
  behavior and stale-topology guard.

Issue #365 also removed the stale recommendation from
`engineering_action_plan.py`; simulation and mesh-refinement action candidates
now describe MCP tool chains instead of the REST stream endpoint.

## Finding 3: result-shape divergence between REST and MCP - follow-up

The REST path writes the older flat `simulation/results_summary.json` shape. The
MCP path writes `simulation/runs/{run_id}/solver_run.json` plus result artifacts
and imported evidence such as `results/computed_metrics.json`.

This is not changed here. A separate contract issue should decide whether to
normalize those summaries or keep both shapes documented with explicit readers.
Until then, new product surfaces should consume the MCP evidence path when they
need solver execution proof.

## Tests

Relevant existing coverage:

- `tests/test_simulation_runner.py`
- `tests/test_simulation_stream.py`
- `tests/test_agent_observation.py`

Added/updated for #365:

- `tests/test_engineering_action_plan.py` verifies simulation intents use
  `["cae.prepare_solver_run", "cae.run_solver"]` and never mention
  `/run-simulation-stream`.
- `tests/test_engineering_action_plan.py` verifies mesh-refinement intents use
  `["cae.generate_mesh", "cae.prepare_solver_run"]` and never mention
  `/run-simulation-stream`.

## Product boundary

- Do not make new frontend UX depend on the legacy REST stream endpoint.
- Do not auto-run solvers from action-plan hints.
- Keep solver success claims tied to actual `cae.run_solver` evidence.
- Keep the legacy endpoint only as compatibility/tested migration surface unless
  a future issue explicitly deprecates or removes it.
