# CAE Scope

## Initial CAE Scope

The first CAE implementation should remain conservative.

Supported initial scope:

- linear static structural analysis
- simple material assignment
- fixed support
- force load
- pressure load
- basic tetrahedral mesh
- CalculiX deck export
- optional CalculiX execution when explicitly requested
- deterministic numeric result extraction

## Extended Scope (Scaffolds)

The following are present as **Implemented scaffold** with surrogate backends.
FreeCAD FEM implementations are **Experimental** and not yet proven by integration
tests with a real FreeCAD + CalculiX runtime.

- thermal steady-state analysis (surrogate: 1D conduction)
- modal / natural frequency analysis (surrogate: Euler-Bernoulli cantilever)
- linear buckling analysis (surrogate: Euler column formula)

## Out of Scope Initially

Do not implement or claim support for:

- nonlinear analysis
- contact
- fatigue
- CFD
- thermal-fluid coupling
- topology optimization
- manufacturing certification
- automatic engineering safety decisions

## Evidence Policy

CAE tools may produce artifacts and parsed observations.

Examples:

- mesh file
- node count
- element count
- solver deck
- solver log
- result file
- max displacement
- max von Mises stress
- reaction force

These observations must not automatically advance claims.

## Validation Policy

A model is not validated merely because:

- a mesh exists
- a deck exists
- a solver ran
- result files exist
- result metrics were parsed

Validation claims require explicit evidence linkage and decision criteria.
