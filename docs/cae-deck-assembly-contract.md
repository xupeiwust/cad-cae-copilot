# CAE Deck Assembly Contract

This note pins the current CalculiX deck-generation boundary so REST, MCP, and
future optimization flows do not drift into different solver semantics.

## Canonical Path

The canonical full solver-input assembler is
`aieng.simulation.deck_generator.generate_solver_input_package`.

The active workbench path is:

1. `aieng-ui/backend/app/simulation_runner.py::ensure_source_deck_from_mesh`
   creates or preserves `simulation/cae_imports/source_solver_deck.inp`.
2. The source deck contains the solid-only mesh, `EALL`, `NALL`, named NSETs, and
   `*SOLID SECTION`.
3. `aieng.simulation.deck_generator` adds material cards, boundary conditions,
   load cards, and the analysis step.
4. `cae.run_solver` remains approval-gated and is the only step that may execute
   CalculiX.

The older `_build_calculix_deck` helper is a compatibility path for legacy REST
simulation and sizing/mesh utilities. Any behavior that affects solver results
must stay aligned with the canonical path and have a parity regression test.

## `simulation/setup.yaml` Semantics

Material fields in setup are authored in engineer-friendly SI or MPa terms:

- `youngs_modulus_mpa`: MPa, emitted directly into `*ELASTIC`.
- `poisson_ratio`: dimensionless.
- `density_kg_m3`: kg/m^3, converted to tonne/mm^3 before `*DENSITY`.

Static force loads use:

- `value_n`: total force magnitude in newtons on the target feature/NSET.
- `direction`: signed vector components in CalculiX DOFs 1, 2, 3.

The deck assembler emits one `*CLOAD` row per non-zero direction component and
divides each total component by the number of nodes in the target NSET. This
prevents the common error where a face load is multiplied by node count.

For solid elements, fixed structural boundary conditions constrain translational
DOFs 1..3. Rotational DOFs 4..6 are not emitted for the solid-only mesh path.

## Drift Guards

Changes to either deck path should update or add tests that compare at least:

- material density unit conversion;
- fixed-BC DOF range;
- signed load direction and per-node force distribution;
- solid-only mesh preservation and named NSET preservation.

The generator must never claim solver convergence. Solver evidence starts only
after an approved `cae.run_solver` creates result artifacts.
