# Adapter Capability Preflight Contract

Status: first implementation slice for issue #430. This contract describes how
AIENG should explain local CAD/CAE tool availability before an agent or user
attempts a workflow.

## Product Rule

Capabilities are not promises that a workflow has succeeded. A capability
status answers only:

- which workflow can be attempted on this machine,
- which local tools are required,
- which tools are missing,
- whether approval is required,
- which package artifacts may be written or made stale if the workflow later
  succeeds.

It must not imply that a solver has run, that evidence is current, or that an
engineering claim has been accepted.

## Structural Adapter Status

`GET /api/adapters/structural/preflight` returns the existing static
`capabilities` manifest plus a read-only `capability_status` array.

Each status entry includes:

- `capability_id`
- `status`: `ready` or `blocked`
- `required_tools`
- `missing_tools`
- `blocked_reason`
- `requires_approval`
- `mutates_package`
- `runs_external_process`
- `claim_advancement`
- `estimated_outputs`
- `stale_artifacts_on_success`

The first structural mapping is:

- `structural.generate_mesh`: requires `FreeCADCmd` and `gmsh`
- `structural.prepare_solver_run`: requires `ccx`
- `structural.run_solver`: requires `ccx`
- `structural.extract_results`: no local executable required by environment
  preflight, but it still requires explicit approval before package mutation

## Safety Boundary

- Preflight does not run FreeCAD, Gmsh, or CalculiX.
- Preflight does not generate mesh, prepare solver decks, parse FRD, or write
  package evidence.
- A `ready` capability may still be blocked by package-level missing inputs.
- All mutating or external-process capabilities keep `requires_approval: true`.
- `claim_advancement` remains `none`.
