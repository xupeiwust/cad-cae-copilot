# Ground truth — diagnose_broken_cae_setup

## The defect

The package's load case (`simulation/load_cases/load_case_001.json`) references
material `Aluminum6061`, but `simulation/cae_imports/parsed_materials.json`
defines only one material: `Steel`.

A solver run would fail because the load case's material reference does not
resolve. The defect is detectable without running anything — it is a pure
cross-reference inconsistency between two setup artifacts.

## What a correct answer looks like

A correct diagnosis must include both of:

1. **The specific undefined material name**: `Aluminum6061`.
2. **The recognition that this is a reference vs. definition mismatch**
   (one artifact references it, another does not define it).

A response naming the material but not the mismatch is partial credit.
A response that names neither is incorrect.

## What a correct answer does NOT need

- The corrective action (the rubric scores diagnosis, not remediation).
- Anything about the geometry, mesh, or solver settings — those are
  intentionally fine in this fixture.
- A scoped physical claim (no convergence, no stress estimate — the package
  has not been run and the defect prevents running).

## Anti-hallucinations to watch for

A response should not:

- Invent additional defects that are not present.
- Claim the mesh is missing (it is present).
- Claim solver settings are missing (they are present).
- Speculate about why the part was designed in Aluminum (irrelevant to the
  diagnosis).
