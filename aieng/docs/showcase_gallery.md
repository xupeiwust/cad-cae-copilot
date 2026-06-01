# Showcase Gallery

Reproducible backend demos for AI-CAD/CAE capabilities. Each entry includes how to run it, what to show, and where the honesty boundaries are.

---

## 1. Single-part topology optimization

**Why it is impressive:** Derives a topology optimization problem from CAE setup, runs SIMP compliance minimization, and writes back optimized geometry as editable Shape IR — all without external solvers for 2D, with structured-voxel experimental support for 3D.

**What it demonstrates:**
- Deriving topopt problem from supports/loads/design-space
- 2D SIMP with density field and compliance history
- Experimental 3D structured-voxel SIMP
- Shape IR writeback as `extruded_region`, `density_voxels`, or `smooth_mesh_proxy`
- Deterministic contract with limitations and provenance

**How to run:**
```bash
pytest aieng/tests/test_topology_optimization.py -q
```

**Expected artifacts:**
- `analysis/topology_optimization.json` — density field, compliance history, provenance
- `analysis/topology_optimization_problem.json` — grid, supports, loads, design space
- `diagnostics/topology_optimization_problem_derivation.json` — projection warnings
- `geometry/shape_ir.json` — writeback as editable Shape IR

**What to show in a demo:**
- The density field evolution — white=material, black=void
- Compliance decreasing over iterations
- Writeback preserving the design-space frame
- The `limitations` block: this is reference, not certified CAE

**Honesty boundary:**
- 2D SIMP is plane-stress; out-of-plane loads are dropped with warnings
- 3D SIMP is experimental/structured-voxel, not production-certified
- `smooth_mesh_proxy` is preview-only, not production CAD
- Single material, linear elastic only
- No manufacturing constraint modeling

**Known limitations:**
- Coarse grids for speed; fine grids need more memory
- 3D writeback produces watertight mesh proxies, not analytic B-Rep
- No stress-constrained topopt (compliance minimization only)

---

## 2. Mesh-to-CAD B-Rep STEP reconstruction

**Why it is impressive:** Takes a mesh (e.g. from topology optimization or scanned data), segments it into regions, fits analytic surfaces (plane, cylinder, sphere, cone, torus), generates OCC faces, stitches edges, sews into a closed shell, and exports a valid STEP file — with honest fallback when the shell is not closed.

**What it demonstrates:**
- Mesh region segmentation
- Analytic surface fitting (plane/cylinder dominant)
- OCC face generation and validation
- Edge matching and stitching plan
- OCC sewing into closed shell
- STEP export **only when** solid validates
- Roundtrip verification (re-import STEP and check)
- Honest cleanup of stale artifacts on re-run

**How to run:**
```bash
pytest aieng/tests/test_mesh_brep_solidification.py -q
```

**Expected artifacts:**
- `graph/mesh_region_graph.json` — segmented mesh regions
- `graph/mesh_surface_fit.json` — fitted surface parameters
- `diagnostics/mesh_reconstruction_readiness.json` — readiness gates
- `geometry/partial_brep_surfaces.json` — analytic surface candidates
- `geometry/partial_brep_faces.json` — validated OCC face candidates
- `graph/mesh_brep_stitching_plan.json` — edge-matching plan
- `diagnostics/mesh_brep_sewing.json` — sewing diagnostics
- `geometry/reconstructed.step` — **only when** valid closed solid
- `diagnostics/mesh_brep_roundtrip_verification.json` — roundtrip check

**What to show in a demo:**
- Region graph: how the mesh is segmented
- Fitted surfaces: "this is a real cylinder, that is a real plane"
- Stitching plan: matched edges vs gaps
- **Emphasize:** STEP only appears when shell actually closes — no fake exports
- Roundtrip diagnostics: re-imported and checked

**Honesty boundary:**
- Mesh-derived and lossy; not original design history
- Analytic-first: plane, cylinder, sphere, cone, torus dominant
- Freeform/NURBS fitting is future work
- `geometry/reconstructed.step` never overwrites source STEP
- Partial shells do NOT produce STEP; reason recorded in diagnostics

**Known limitations:**
- Requires clean, watertight-ish input mesh
- Small regions or noisy boundaries may be skipped
- Roundtrip verification can fail on complex geometry; STEP kept but marked unverified
- Not a replacement for native CAD history

---

## 3. Assembly-aware topology optimization

**Why it is impressive:** Represents a multi-part assembly with parts, interfaces, and connections; resolves interface geometry; builds a simplified proxy CAE model; derives a topology optimization problem for one selected design part while preserving mounting/load interfaces; runs SIMP; writes back an optimized Shape IR for the selected part only.

**What it demonstrates:**
- Assembly IR with parts, interfaces, and connections
- Interface resolution (bbox, centroid, normal, area)
- Connection geometry validation
- Solver-neutral assembly CAE proxy model
- Assembly-aware topopt problem derivation
- Preserve masks for mounting/load interfaces during optimization
- Selected-part Shape IR writeback
- Post-optimization verification and design recommendations

**How to run:**
```bash
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q
```

**Expected artifacts:**
- `assembly/assembly_ir.json` — 3-part assembly
- `assembly/part_registry.json` — part roles and placements
- `assembly/connection_graph.json` — rigid_tie + bolted_proxy
- `assembly/interface_resolution.json` — resolved geometry
- `simulation/assembly_cae_model.json` — proxy CAE model
- `analysis/assembly_topopt_problem.json` — derived problem
- `analysis/assembly_topology_optimization.json` — optimization result
- `parts/bracket/geometry/optimized_shape_ir.json` — derived design part
- `diagnostics/assembly_post_optimization_verification.json` — scope verification
- `analysis/assembly_design_recommendations.json` — advisory recommendations
- `analysis/assembly_next_actions.json` — suggested next steps

**What to show in a demo:**
- Assembly IR: 3 parts, 2 connections, 4 interfaces
- Interface resolution: real geometry extracted from topology
- Preserve regions: mounting holes and load faces stay intact
- Frozen parts (`wall`, `load_jig`) are untouched
- Design recommendations: actionable but advisory

**Honesty boundary:**
- Connections are **proxies only**: rigid_tie, bonded, bolted_proxy, welded_proxy, contact_proxy, spring_proxy
- **No real nonlinear contact physics** — no friction, no real contact forces
- **No bolt preload** modeled
- Optimizes **one selected design part only**
- `production_ready: False`, `contact_physics_modeled: False`, `bolt_preload_modeled: False`

**Known limitations:**
- Proxy CAE model is simplified; full nonlinear FEA is future work
- Assembly meshing and per-part mesh coupling are best-effort
- Design recommendations are rule-based, not from real solver feedback

---

## 4. Agent-guided parameter design study

**Why it is impressive:** An agent proposes parameter changes to a design; the backend validates each proposal against safety rules (bounds, protected variables), executes valid candidates into isolated derived workspaces, ranks them by objective and constraints using deterministic metrics, and allows explicit acceptance of the best safe candidate — all without ever modifying baseline geometry.

**What it demonstrates:**
- Design study problem contract with variables, bounds, constraints, objective
- Candidate patch validation (bounds, protected variables, assembly scope)
- Explicit candidate execution into derived workspace
- Static metric injection for deterministic evaluation
- Feasibility classification (`feasible` / `infeasible` / `unknown` / `failed`)
- Conservative deterministic scoring by objective
- Best-candidate selection with `safe_to_accept` gating
- Explicit acceptance into `accepted/` workspace
- Baseline geometry preserved throughout

**How to run:**
```bash
pytest aieng-ui/backend/tests/test_design_study_demo.py -q
```

**Expected artifacts:**
- `analysis/design_study_problem.json` — problem definition
- `diagnostics/design_study_candidate_validation.json` — validation results
- `patches/design_candidates/candidate_good.json` — proposed patch
- `candidates/candidate_good/geometry/shape_ir.json` — derived geometry
- `candidates/candidate_good/analysis/evaluation.json` — evaluation metrics
- `analysis/design_study_iterations.json` — execution history
- `analysis/design_study_candidate_ranking.json` — ranked candidates
- `diagnostics/design_study_scoring_report.json` — scoring diagnostics
- `analysis/design_study_acceptance.json` — acceptance record
- `accepted/candidate_good/geometry/shape_ir.json` — accepted geometry
- `accepted/candidate_good/provenance/acceptance.json` — acceptance provenance

**What to show in a demo:**
- Validation: protected `bolt_dia` rejected, out-of-bounds rejected
- Execution: each candidate gets its own isolated workspace
- Ranking: feasible good candidate scores highest, infeasible flagged
- Acceptance: explicit, gated, baseline untouched
- The accepted Shape IR: derived, traceable, with full provenance

**Honesty boundary:**
- Static metrics only in demo; real CAE evaluation is future work
- No autonomous optimization — candidates explicitly proposed and executed one at a time
- No baseline overwrite — accepted candidate is derived artifact only
- No production approval claimed
- Ranking is advisory; `safe_to_accept` is conservative
- Missing metrics produce `needs_more_evaluation`, not overconfident acceptance

**Known limitations:**
- Only single-objective deterministic scoring (not Pareto)
- No search/grid/random exploration loop
- No automatic promotion to baseline
- Real CAE evaluation would require external solver integration

---

## Quick smoke commands

Run all canonical demos:

```bash
# Topology optimization
pytest aieng/tests/test_topology_optimization.py -q

# Mesh-to-CAD reconstruction
pytest aieng/tests/test_mesh_brep_solidification.py -q

# Assembly-aware topopt
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q

# Design study
pytest aieng-ui/backend/tests/test_design_study_demo.py -q
```

Run the full backend design-study suite:

```bash
pytest aieng/tests/test_design_study*.py aieng-ui/backend/tests/test_design_study_demo.py -q
```

---

## Related documentation

- [`demo_catalog.md`](demo_catalog.md) — Backend demo catalog with artifact paths and maturity
- [`backend_capability_matrix.md`](backend_capability_matrix.md) — Capability status snapshot
- [`backend_artifact_reference.md`](backend_artifact_reference.md) — Complete artifact path reference
- [`roadmap.md`](roadmap.md) — Development roadmap
- [`AGENTS.md`](../../AGENTS.md) — Agent guide with workflow examples
