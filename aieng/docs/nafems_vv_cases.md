# NAFEMS-style V&V starter suite — case catalog

This document catalogs the linear-static and linear-eigenvalue (modal /
buckling) reference cases that seed the automated verification regression in
`aieng/src/aieng/nafems_verification.py`.

These cases are *NAFEMS-style* benchmarks: they use simple geometry, well-known
analytical/closed-form solutions, and documented tolerance bands. They are **not**
official NAFEMS certification benchmarks and do **not** constitute an ASME V&V 10
certification. The intended claim is:

> "Computed results agree with the analytical reference value within the
documented tolerance band."

Never: "certified" or "validated to NAFEMS standards".

---

## Mesh convergence study

The suite supports running the same case at multiple mesh refinements (e.g.
`(nx, ny, nz)` = `(10, 2, 2)`, `(20, 4, 4)`, `(40, 8, 8)`) and recording how the
computed metric deviations trend toward the analytical reference. A decreasing
deviation is a *numerical* indicator that the discretisation error is reducing
for the documented geometry and load case.

This study is **not** a certification of mesh independence for arbitrary
geometries. It only demonstrates convergence behaviour on the specific reference
case under the documented assumptions.

---

## Shared modeling assumptions

All cases use:

* **Material:** Steel
  * Young's modulus `E = 210000 MPa`
  * Poisson's ratio `nu = 0.3`
  * Density `rho = 7850 kg/m³` (included for completeness, not used in linear-static solution)
* **Element type:** C3D8 solid hexahedral elements
* **Units:** mm / N / MPa
* **Geometry convention:** X is the beam/rod axis; the model is fixed at `X = 0`.
* **Boundary condition:** Fixed (`*BOUNDARY`, DOFs 1–3 = 0) on all nodes at `X = 0`.

---

## Case 1: `tension_rod`

### Geometry and mesh

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Cross-section | 10 × 10 mm |
| Mesh divisions | `nx = 20`, `ny = 2`, `nz = 2` |
| Elements | 80 C3D8 |

### Loading

Total tensile force `F = 1000 N` in `+X` applied uniformly to all nodes on the
`X = L` end face.

### Analytical reference

* Cross-sectional area `A = 10 · 10 = 100 mm²`
* Axial stress `σ = F / A = 1000 / 100 = 10 MPa`
* Axial displacement at free end `δ = F·L / (E·A)`
  `δ = 1000 · 100 / (210000 · 100) ≈ 0.00476 mm`

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 0.00476 mm | ±10 % |
| `max_von_mises_stress` | 10 MPa | ±10 % |

### Mesh note

A 2×2 cross-section mesh under-represents the exact uniform stress state, but
C3D8 elements reproduce constant axial stress and strain exactly. Displacement
should be very close to the analytical value; the ±10 % band is deliberately
loose to absorb small end-effects from nodal load lumping.

---

## Case 2: `cantilever_end_load`

### Geometry and mesh

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Loading

Total transverse force `F = 100 N` in `-Z` applied uniformly to all nodes on the
`X = L` end face.

### Analytical reference (Euler-Bernoulli beam theory)

* Second moment of area `I = b·h³ / 12 = 10 · 20³ / 12 ≈ 6666.67 mm⁴`
* Tip deflection `δ = F·L³ / (3·E·I)`
  `δ = 100 · 100³ / (3 · 210000 · 6666.67) ≈ 0.0238 mm`
* Maximum bending moment at fixed end `M = F·L = 100 · 100 = 10000 N·mm`
* Maximum bending stress at fixed end `σ = M·(h/2) / I`
  `σ = 10000 · 10 / 6666.67 ≈ 15 MPa`

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 0.0238 mm | ±10 % |
| `max_von_mises_stress` | 15 MPa | ±10 % |

### Mesh note

Solid C3D8 elements are stiffer than Euler-Bernoulli beam theory predicts, and
coarse through-thickness discretisation (`nz = 4`) introduces shear locking.
Consequently the computed tip deflection is expected to be slightly below the
beam-theory value, and the fixed-end stress peak is mesh-sensitive. The ±10 %
band is honest for this mesh density.

---

## Case 3: `cantilever_udl`

### Geometry and mesh

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Loading

Uniformly distributed downward load `w = 1 N/mm` along the beam length, total
`F = w·L = 100 N`. The total load is applied in `-Z` and distributed equally
over all nodes on the top face (`Z = h`).

### Analytical reference (Euler-Bernoulli beam theory)

* Second moment of area `I = b·h³ / 12 ≈ 6666.67 mm⁴`
* Tip deflection `δ = w·L⁴ / (8·E·I)`
  `δ = 1 · 100⁴ / (8 · 210000 · 6666.67) ≈ 0.00893 mm`
* Maximum bending moment at fixed end `M = w·L² / 2 = 1 · 100² / 2 = 5000 N·mm`
* Maximum bending stress at fixed end `σ = M·(h/2) / I`
  `σ = 5000 · 10 / 6666.67 ≈ 7.5 MPa`

The original starter-suite proposal stated `σ = w·L²·h / (2·I) ≈ 15 MPa`, which
corresponds to `M = w·L²` rather than the standard cantilever UDL moment
`M = w·L² / 2`. The regression anchors `max_von_mises_stress` to the physically
consistent analytical bending stress of **7.5 MPa** so that the comparison is
honest for the specified total force `F = 100 N`.

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 0.00893 mm | ±10 % |
| `max_von_mises_stress` | 7.5 MPa | ±10 % |

### Mesh note

As with the end-loaded cantilever, the coarse C3D8 mesh is stiffer than the
Euler-Bernoulli analytical deflection. The nodal-force lumping on the top face
approximates a uniform pressure rather than matching it exactly. The ±10 %
tolerance band absorbs discretisation error, shear locking, and load-lumping
effects.

---

## Case 4: `fixed_fixed_udl`

### Geometry and mesh

Same beam as the cantilever cases:

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Loading

Uniformly distributed downward load `w = 1 N/mm`, total `F = 100 N`, applied in
`-Z` and distributed equally over all top-face nodes (`Z = h`).

### Boundary conditions

Both ends (`X = 0` and `X = L`) are fully fixed (DOFs 1–3 = 0).

### Analytical reference (Euler-Bernoulli beam theory)

* Second moment of area `I = b·h³ / 12 ≈ 6666.67 mm⁴`
* Maximum deflection at mid-span `δ = w·L⁴ / (384·E·I)`
  `δ = 1 · 100⁴ / (384 · 210000 · 6666.67) ≈ 1.86 × 10⁻⁴ mm`
* Maximum bending moment at the fixed ends `M = w·L² / 12 = 833.33 N·mm`
* Maximum bending stress at the fixed ends `σ = M·(h/2) / I`
  `σ = 833.33 · 10 / 6666.67 ≈ 1.25 MPa`

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 1.86 × 10⁻⁴ mm | ±10 % |
| `max_von_mises_stress` | 1.25 MPa | ±10 % |

### Mesh note

The mid-span deflection is very small because the fixed-fixed beam is much
stiffer than a cantilever. The coarse mesh may only weakly resolve the central
deflection; the ±10 % band is honest for this discretisation.

---

## Case 5: `fixed_fixed_center_load`

### Geometry and mesh

Same beam as the cantilever cases:

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Loading

A single 100 N point load in `-Z` is applied to the top-center node
(`X = L/2`, `Y = b/2`, `Z = h`).

### Boundary conditions

Both ends (`X = 0` and `X = L`) are fully fixed (DOFs 1–3 = 0).

### Analytical reference (Euler-Bernoulli beam theory)

* Second moment of area `I = b·h³ / 12 ≈ 6666.67 mm⁴`
* Maximum deflection at mid-span `δ = P·L³ / (192·E·I)`
  `δ = 100 · 100³ / (192 · 210000 · 6666.67) ≈ 3.72 × 10⁻⁴ mm`
* Maximum bending moment at the fixed ends and mid-span `M = P·L / 8 = 1250 N·mm`
* Theoretical maximum bending stress `σ = M·(h/2) / I ≈ 1.875 MPa`

Because the load is applied to a single node, the local stress is
mesh-sensitive and not a meaningful convergence target. This case therefore
focuses on displacement.

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 3.72 × 10⁻⁴ mm | ±10 % |

---

## Case 6: `cantilever_midspan_load`

### Geometry and mesh

Same beam as the other cantilever cases:

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

`nx` must be even so a node plane lands exactly on mid-span (`X = L/2`).

### Loading

A total 100 N load in `-Z` distributed over the top-face line of nodes at
mid-span (`X = L/2`, `Z = h`) — a concentrated load at `a = L/2`.

### Boundary conditions

The `X = 0` face is fully fixed (DOFs 1–3 = 0).

### Analytical reference (Euler-Bernoulli beam theory)

* Second moment of area `I = b·h³ / 12 ≈ 6666.67 mm⁴`
* Free-tip deflection for a load `P` at distance `a` from the fixed end:
  `δ_tip = P·a²·(3L − a) / (6·E·I)`, with `a = L/2`
  `δ_tip = 100 · 50² · 250 / (6 · 210000 · 6666.67) ≈ 7.44 × 10⁻³ mm`
* Maximum bending moment at the fixed root `M = P·a = 5000 N·mm`
* Theoretical maximum bending stress `σ = M·(h/2) / I = 7.5 MPa`

Because the load is applied along a mid-span line, the local stress near the
load is mesh-sensitive; the displacement is the primary convergence target and
is the metric asserted in the real-solver regression.

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 7.44 × 10⁻³ mm | ±10 % |
| `max_von_mises_stress` | 7.5 MPa | ±10 % |

---

## Case 7: `cantilever_end_load_lateral`

### Geometry and mesh

Identical geometry to `cantilever_end_load`, but the load bends the beam about
its **weak axis**:

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Loading

A total 100 N load in `-Y` distributed over the `X = L` end face. Bending is now
in the Y direction, so the relevant second moment of area is the weak-axis one.

### Boundary conditions

The `X = 0` face is fully fixed (DOFs 1–3 = 0).

### Analytical reference (Euler-Bernoulli beam theory)

* Weak-axis second moment of area `I = h·b³ / 12 = 20 · 10³ / 12 ≈ 1666.67 mm⁴`
* Free-tip deflection `δ = P·L³ / (3·E·I)`
  `δ = 100 · 100³ / (3 · 210000 · 1666.67) ≈ 9.52 × 10⁻² mm`
* Maximum bending moment at the fixed root `M = P·L = 10000 N·mm`
* Theoretical maximum bending stress `σ = M·(b/2) / I = 30 MPa`

This case exercises a different load direction and moment of inertia than
`cantilever_end_load` through the same pipeline, guarding against axis- or
inertia-specific regressions.

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `max_displacement` | 9.52 × 10⁻² mm | ±10 % |
| `max_von_mises_stress` | 30 MPa | ±10 % |

---

## Case 8: `cantilever_modal` (eigenvalue — natural frequency)

### Geometry and mesh

Same beam as `cantilever_end_load`, but with **no load** and a `*FREQUENCY` step:

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Analysis

`*FREQUENCY` extraction of the lowest natural frequencies (clamped at `X = 0`,
free elsewhere). Results are written to the CalculiX **`.dat`** file (not the
`.frd`) and parsed by `aieng.simulation.dat_result_extractor`.

### Units note (important for eigenvalue cases)

Natural frequency depends on mass, so this case uses a **consistent mm–tonne–s
unit system**: `E = 210000 N/mm²`, density `ρ = 7.85 × 10⁻⁹ tonne/mm³`
(= 7850 kg/m³). The deck generator emits the density value verbatim, so the
eigenvalue cases must supply the consistent value for the reported frequency
(Hz) to be physically meaningful. (Static cases never use density.)

### Analytical reference (Euler-Bernoulli beam theory)

* Fundamental mode = **weak-axis** bending; `I = L_z·L_y³ / 12 = 1666.67 mm⁴`
* Cross-sectional area `A = L_y·L_z = 200 mm²`
* First natural frequency
  `f₁ = (1.875104² / 2π) · √(E·I / (ρ·A·L⁴)) ≈ 835.5 Hz`

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `first_natural_frequency_hz` | ≈ 835.5 Hz | ±20 % |

### Mesh note

The band is wider (±20 %) than the static cases: coarse C3D8 elements
shear-stiffen in bending (raising the frequency), and Euler-Bernoulli theory
omits shear/rotary-inertia effects present in the 3D solid. The reference is a
*linear undamped* natural frequency — no damping, prestress, or modal
participation claims.

---

## Case 9: `column_buckling` (eigenvalue — Euler buckling)

### Geometry and mesh

A slender column, same section as the cantilever cases:

| Parameter | Value |
|-----------|-------|
| Length `L` | 100 mm |
| Width `b` (Y) | 10 mm |
| Height `h` (Z) | 20 mm |
| Mesh divisions | `nx = 20`, `ny = 4`, `nz = 4` |
| Elements | 320 C3D8 |

### Loading and analysis

A `*BUCKLE` step with a **1000 N axial compressive reference load** (`-X`) on the
free `X = L` end face; clamped at `X = 0`. CalculiX returns load **factors** in
the `.dat` file; the reported buckling factor `λ₁ = P_cr / 1000 N`.

### Analytical reference (Euler critical load)

* Lowest mode buckles about the **weak axis**; `I = 1666.67 mm⁴`
* Fixed-free effective-length factor `K = 2`
* `P_cr = π²·E·I / (K·L)² = π² · 210000 · 1666.67 / (2·100)² ≈ 86 360 N`
* Buckling factor `λ₁ = P_cr / 1000 ≈ 86.4`

### Verified metrics and tolerance

| Metric | Reference | Tolerance |
|--------|-----------|-----------|
| `lowest_buckling_factor` | ≈ 86.4 | ±20 % |

### Mesh note

±20 % band: the coarse C3D8 mesh stiffens the column (raising `P_cr`), and the
slenderness (`KL/r ≈ 69`) is at the upper-elastic Euler range. This is a
**linear (eigenvalue) buckling** factor — no imperfection sensitivity,
post-buckling, or material-nonlinear collapse is modeled.

---

## Tolerance rationale

A ±10 % tolerance band was chosen because:

1. **Mesh density is intentionally coarse.** Each case is designed to run in
   well under one second per case on a typical CI runner.
2. **C3D8 solid elements** used for what are essentially 1-D/beam problems
   introduce shear locking and coarse through-thickness resolution.
3. **Load lumping** onto NSET nodes is not identical to the continuous
   analytical load.
4. The band is **honest**: it does not overclaim accuracy and makes it easy to
   tighten later if a finer mesh or incompatible-mode elements are adopted.

The tolerance applies independently to each metric. A case passes only when
both `max_displacement` and `max_von_mises_stress` fall within the band.

---

## Honest limitations

* **Linear static + linear eigenvalue only.** Static stress/displacement, modal
  natural frequency, and Euler buckling factors. No geometric or material
  nonlinearity, contact, damping, prestress, post-buckling, or transient
  dynamics.
* **Analytical reference, not experimental.** Comparisons are against
  closed-form beam/rod theory, not measured physical data.
* **Coarse mesh.** Results are mesh-dependent; finer meshes would tighten the
  deviation.
* **Not official NAFEMS certification.** These are in-house NAFEMS-style
  benchmarks for regression testing, not a NAFEMS-published validation case.
* **Not ASME V&V 10 certified.** The suite is a first step toward a V&V 10
  narrative; it does not satisfy ASME V&V 10 requirements.
* **Single software path.** Verification is performed with CalculiX ccx only.
