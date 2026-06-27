# Mesh Diagnostics: Failure and Recovery

This canonical scenario demonstrates how AIENG should fail honestly before a
solver claim is made. It starts from missing or incomplete CAE setup evidence,
shows the readiness/preflight blockers, then documents the recovery path toward
a prepared solver deck.

## Scenario Intent

The target workflow checks that an agent or operator can distinguish:

- no simulation setup;
- partial setup with missing required material, loads, or constraints;
- setup with defaultable mesh/solver fields;
- explicit mesh or solver unavailability;
- prepared solver deck evidence;
- approved solver execution and result artifacts.

The important product behavior is the stop sign: missing mesh/deck/setup
evidence should block or warn before anyone claims solver success.

## Entrypoints

- `aieng-ui/backend/tests/test_simulation_readiness.py`
- `aieng-ui/backend/tests/test_simulation_runner.py`
- `aieng-ui/docs/troubleshooting-vertical-cae-mvp.md`

## Lightweight Verification

```bash
python -m pytest aieng-ui/backend/tests/test_simulation_readiness.py -q
python -m pytest aieng-ui/backend/tests/test_simulation_runner.py -q -k "mesh or deck or unresolved or run_solver"
```

These checks exercise deterministic readiness classification, missing required
inputs, blocked-reason codes, mesh preview availability, deck generation, unsafe
path rejection, and solver-run bookkeeping. Real CalculiX/Gmsh availability is
not required for the lightweight scenario path.

## Expected Artifacts

- `simulation/setup.yaml`
- `simulation/cae_mapping.json`
- `simulation/mesh/mesh.inp`
- `simulation/runs/<run_id>/solver_input.inp`
- `simulation/runs/<run_id>/solver_run.json`
- `diagnostics/*`

Artifacts may be absent in the intentional failure stage. That absence is part
of the scenario: it should appear as missing evidence or a blocker, not as a
silent success.

## Recovery Path

1. Run simulation readiness on a project with no setup and confirm material,
   loads, and constraints are missing.
2. Add explicit material, load, and constraint setup and confirm the required
   inputs become present.
3. Add or generate mesh/deck artifacts and confirm preflight can identify them.
4. Only after an approved solver execution may a report claim result artifacts.

## Honesty Boundaries

- Preflight success is not solver success.
- A prepared deck is not solver evidence.
- Synthetic fields or fixture metrics must not be counted as real solver
  evidence.
- `converged: null` means convergence is unknown unless independent evidence is
  added.
- Stale artifacts after setup changes must trigger warnings or rerun guidance.
