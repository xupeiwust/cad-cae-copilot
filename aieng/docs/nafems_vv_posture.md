# V&V posture — NAFEMS-style starter suite

This document describes the verification & validation posture of the
NAFEMS-style starter suite implemented in `aieng/src/aieng/nafems_verification.py`.

## What the starter suite verifies

The suite exercises the AIENG CAE pipeline end-to-end on three simple
linear-static structural cases:

1. **Tension rod** — axial loading of a square rod.
2. **Cantilever, end load** — transverse point load at the free end.
3. **Cantilever, uniformly distributed load** — downward load spread over the top face.

For each case the pipeline:

* Builds a runnable CalculiX `.aieng` fixture (mesh + setup + mapping).
* Generates a solver input deck via `aieng.simulation.deck_generator`.
* Executes CalculiX (`ccx`) when available.
* Extracts `max_displacement` and `max_von_mises_stress` from the `.frd` file
  via `aieng.simulation.frd_result_extractor`.
* Compares the computed metrics to documented analytical reference values and
  records pass/fail + deviation.

The result is a machine-readable verification artifact,
`verification/nafems_vv_report.json`, that a downstream study can cite as:

> "Verified against the NAFEMS-style `case_id` reference value within
> `tolerance_percent` % deviation."

## Reference values and tolerance rationale

Reference values are derived from analytical beam/rod theory for the documented
geometry, material, and loading. See `aieng/docs/nafems_vv_cases.md` for the
full formulas.

The tolerance band is **±10 %** for both displacement and stress on all cases.
This band is intentionally conservative because:

* The mesh is coarse (e.g., `nz = 4` through the beam height) to keep CI runtime
  under one second per case.
* C3D8 solid hexahedral elements are used for problems better described by
  beam/rod theory, so shear locking and coarse through-thickness discretisation
  introduce systematic stiffness.
* Loads are lumped onto NSET nodes rather than applied as continuous pressures
  or consistent nodal forces.

The band can be tightened if the project later adopts a finer mesh, reduced
integration / incompatible-mode elements, or consistent load lumping. Until
that work is done, ±10 % is the honest bound.

## Honest limitations

The following limitations are recorded in every verification report and must be
preserved in any downstream citation:

* **Linear-static verification only.** No nonlinear material, large
deformation, contact, buckling, modal, thermal, or dynamic verification.
* **Analytical reference only.** Comparisons are against closed-form theory, not
physical test data.
* **Coarse mesh.** Results are mesh-dependent and may change if the mesh is
refined.
* **Single solver path.** Verification is performed with CalculiX ccx only;
other solvers may yield different numerical results.
* **Not a certification.** The report claims only that computed metrics fall
within the documented tolerance of the analytical reference. It does **not**
claim ASME V&V 10 compliance, NAFEMS certification, or product certification of
any kind.
* **Not an official NAFEMS benchmark.** These are internally maintained
NAFEMS-style cases for regression testing.

## Honesty guardrails

The implementation enforces these guardrails:

* The verification report includes a `claim_policy` block (reusing
  `aieng.cae_verification._claim_policy`) that marks claims as unadvanced and
  pre-execution where applicable.
* The `limitations` array in the report contains explicit "not a certification"
  and "not ASME V&V 10 certified" language.
* Test `test_report_contains_honest_not_certified_claim` asserts the presence of
  these strings.
* All real-ccx tests skip cleanly via `@pytest.mark.skipif` when `ccx` is not
  available, so the suite does not fail on CI runners without CalculiX.

## How to run the regression

From the `aieng` directory:

```bash
python -m pytest tests/test_nafems_verification.py -q
```

To run the full `aieng` test suite:

```bash
python -m pytest tests/ -q
```

Real solver tests will be collected as skipped if `AIENG_CCX_CMD` is not set and
no `ccx` executable is on `PATH`. To run them locally:

```bash
export AIENG_CCX_CMD="/path/to/ccx"
python -m pytest tests/test_nafems_verification.py -q
```

Or use a conda environment:

```bash
export AIENG_CCX_CMD="conda run -n calculix-env ccx"
python -m pytest tests/test_nafems_verification.py -q
```

## Relationship to ASME V&V 10

This starter suite is a **first step** toward an ASME V&V 10 narrative. It
establishes:

* A reproducible automated regression.
* Documented reference values and tolerance bands.
* A machine-readable evidence artifact.

It does **not** establish:

* Validation against experimental data.
* Code verification beyond these three analytical cases.
* Calculation verification for mesh/time-step independence.
* Formal uncertainty quantification.

Future work may extend the suite to include additional reference cases, mesh
convergence studies, and comparison to experimental or higher-fidelity reference
solutions. Until then, all claims must remain scoped to the documented
linear-static verification cases.
