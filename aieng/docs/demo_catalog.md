# Backend Demo Catalog

Canonical backend demos and regression flows for the AI-CAD/CAE workbench.

These are deterministic, backend-only tests that validate platform capabilities without requiring external solvers, UI interaction, or random generation. Each demo exercises a complete workflow end-to-end and records its honesty boundaries explicitly.

For a higher-level showcase with demo talking points and visual guidance, see [`showcase_gallery.md`](showcase_gallery.md).

For the cross-product scenario-pack index used for onboarding, dogfood, and
release planning, see
[`../../docs/canonical_engineering_scenarios.md`](../../docs/canonical_engineering_scenarios.md).

---

## Demo Matrix

| Demo | Capability Area | Fixture / Test Location | Run Command | Main Artifacts | Expected Result | Maturity | Honesty Boundary |
|------|-----------------|------------------------|-------------|----------------|-----------------|----------|------------------|
| Single-part topology optimization | Structural optimization | `aieng/tests/test_topology_optimization.py` | `pytest aieng/tests/test_topology_optimization.py -q` | `analysis/topology_optimization.json`, `geometry/shape_ir.json`, `diagnostics/topology_optimization_problem_derivation.json` | Compliance reduces, volume fraction met, contract fields present | Stable (2D) / Experimental (3D) | 2D plane-stress; 3D SIMP is reference-only |
| Mesh-to-CAD B-Rep reconstruction | Mesh → analytic CAD | `aieng/tests/test_mesh_brep_*.py` | `pytest aieng/tests/test_mesh_brep_solidification.py -q` | `geometry/reconstructed.step`, `diagnostics/mesh_brep_sewing.json`, `graph/mesh_brep_stitching_plan.json` | Closed shell → valid solid → STEP export when possible | Stable | Mesh-derived/lossy; not production CAD; freeform/NURBS future work |
| Assembly-aware topology optimization | Multi-part assembly optimization | `aieng-ui/backend/tests/test_assembly_topopt_demo.py` | `pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q` | `analysis/assembly_topology_optimization.json`, `parts/bracket/geometry/optimized_shape_ir.json`, `diagnostics/assembly_post_optimization_verification.json` | Derived part artifact written, frozen parts untouched, verification passed | Stable | Proxy connections only; no real contact; no bolt preload; one design part only |
| Agent-guided parameter design study | Parameter exploration + evaluation + hints + ranking + acceptance | `aieng-ui/backend/tests/test_design_study_demo.py` | `pytest aieng-ui/backend/tests/test_design_study_demo.py -q` | `candidates/candidate_good/analysis/evaluation.json`, `analysis/design_study_candidate_hints.json`, `analysis/design_study_candidate_ranking.json`, `analysis/design_study_acceptance.json`, `accepted/candidate_good/geometry/shape_ir.json` | Best candidate evaluated, hints generated, ranked, accepted into derived workspace; baseline untouched | Stable | Candidate-local static/neutral evidence only; no autonomous optimization; no baseline overwrite |
| Real CAD->CAE value demo | External-agent CAD->CAE->report chain | `docs/cad-cae-value-demo.md`, `aieng-ui/backend/scripts/value_demo_packet.py`, `aieng-ui/backend/tests/test_cae_solve_integration.py` | `python aieng-ui/backend/scripts/value_demo_packet.py --format markdown`; configured machines may run `pytest aieng-ui/backend/tests/test_cae_solve_integration.py -q` | `simulation/runs/value_demo_run_001/outputs/result.frd`, `results/computed_metrics.json`, engineering report HTML | One single-solid cantilever can be created, solved with real CalculiX, viewed as FRD-derived fields, and summarized with evidence citations | Operator-runbook | Requires Gmsh/CalculiX; linear static, mesh-dependent, not certified; synthetic fallback is a failed demo |
| 2D topology → sizing → CAE | Topology writeback → auto-parameterization → sizing → validation → acceptance | `aieng-ui/backend/tests/test_topology_sizing_backend_demo.py` | `pytest aieng-ui/backend/tests/test_topology_sizing_backend_demo.py -q` | `analysis/design_study_problem.json`, `analysis/optimization_study.json`, `analysis/optimization_decision_log.json`, `analysis/design_study_candidate_ranking.json`, `analysis/design_study_acceptance.json`, `diagnostics/optimization_report.json`, `provenance/tool_trace.json` | Full chain runs, chain preserved, `production_ready:false`, baseline untouched, acceptance approval-gated | Experimental | No external solver; volume/mass analytical only; stress/displacement absent; 3D/non-extruded refused |

---

## 1. Single-Part Topology Optimization Demo

**Purpose:** Validate SIMP topology optimization (2D and experimental 3D) with deterministic test problems.

**Test file:** `aieng/tests/test_topology_optimization.py` (39 tests)

**Run:**
```bash
pytest aieng/tests/test_topology_optimization.py -q
```

**Expected artifacts:**
- `analysis/topology_optimization_problem.json` — grid + supports + loads + design space
- `analysis/topology_optimization.json` — density field, compliance history, provenance
- `diagnostics/topology_optimization_problem_derivation.json` — projection warnings if any
- `geometry/shape_ir.json` — writeback as `extruded_region`, `density_voxels`, or `smooth_mesh_proxy`

**Expected behavior:**
- Compliance decreases over iterations
- Volume fraction stays within 0.05 of target
- Contract format fields present (`format`, `optimizer`, `limitations`)
- 3D tests assert `production_ready: False` and `engineering_level: experimental_reference`

**Honesty boundaries:**
- 2D SIMP uses plane-stress assumption; out-of-plane loads are dropped with warnings
- 3D SIMP is experimental/structured-voxel, not production-certified
- `smooth_mesh_proxy` outputs are preview-only, not production CAD
- Empty isosurfaces fall back to blocky `density_voxels` with recorded reason
- Single material, linear elastic only

---

## 2. Mesh-to-CAD B-Rep Reconstruction Demo

**Purpose:** Validate mesh-to-analytic-B-Rep reconstruction pipeline: segmentation → surface fitting → freeform fitting evidence → face generation → stitching → sewing → STEP export.

**Test files:**
- `aieng/tests/test_mesh_brep_reconstruction.py` (10 tests)
- `aieng/tests/test_mesh_brep_face_generation.py` (9 tests)
- `aieng/tests/test_mesh_brep_stitching.py` (8 tests)
- `aieng/tests/test_mesh_brep_solidification.py` (11 tests)
- `aieng/tests/test_mesh_freeform_surface_fitting.py` (15 tests)
- `aieng/tests/test_mesh_freeform_surface_readiness.py` (20 tests)
- `aieng/tests/test_mesh_freeform_brep_faces.py` (9 tests)
- `aieng/tests/test_mesh_to_cad_reconstruction_status.py` (23 tests)
- `aieng/tests/test_mesh_segmentation_quality.py` (10 tests)

**Run:**
```bash
pytest aieng/tests/test_mesh_brep_solidification.py -q
pytest aieng/tests/test_mesh_freeform_surface_fitting.py -q
pytest aieng/tests/test_mesh_freeform_surface_readiness.py -q
pytest aieng/tests/test_mesh_freeform_brep_faces.py -q
pytest aieng/tests/test_freeform_face_trimming_readiness.py -q
pytest aieng/tests/test_mesh_to_cad_reconstruction_status.py -q
pytest aieng/tests/test_mesh_segmentation_quality.py -q
```

**Expected artifacts:**
- `graph/mesh_region_graph.json` — segmented mesh regions
- `graph/mesh_surface_fit.json` — fitted plane/cylinder surface parameters
- `graph/mesh_freeform_surface_fit.json` — approximate BSpline-like freeform surface evidence
- `diagnostics/mesh_freeform_surface_fitting.json` — freeform fitting diagnostics
- `diagnostics/mesh_freeform_reconstruction_readiness.json` — freeform readiness/quality scoring and next actions
- `geometry/partial_freeform_brep_faces.json` — validated OCC BSpline face candidates from ready freeform surfaces
- `diagnostics/freeform_brep_face_generation.json` — face generation diagnostics
- `diagnostics/freeform_face_trimming_readiness.json` — boundary/adjacency readiness for future trimming
- `diagnostics/mesh_to_cad_reconstruction_status.json` — aggregated reconstruction status, STEP availability, blockers, next action
- `diagnostics/mesh_segmentation_quality.json` — segmentation quality assessment (fragmentation, undersegmentation, fit coverage, boundary quality)
- `analysis/mesh_resegmentation_hints.json` — conservative re-segmentation strategy recommendations
- `diagnostics/mesh_reconstruction_readiness.json` — readiness gates
- `geometry/partial_brep_surfaces.json` — analytic surface candidates
- `geometry/partial_brep_faces.json` — validated OCC face candidates
- `graph/mesh_brep_stitching_plan.json` — edge-matching plan
- `diagnostics/mesh_brep_sewing.json` — sewing diagnostics
- `geometry/reconstructed.step` — **only when** a valid closed shell is produced
- `diagnostics/mesh_brep_roundtrip_verification.json` — roundtrip check

**Expected behavior:**
- Cube produces 6 face candidates, 12 matched edge pairs, closed shell
- Cylinder produces cylinder face candidate
- Freeform patches (saddle, sphere-like) produce BSpline surface evidence with control net and error metrics
- Freeform readiness scoring classifies surfaces as ready/partial/not_ready with quality scores
- Poor/high-error/missing-boundary fits are explicitly not_ready with recommended next actions
- Ready freeform surfaces produce validated OCC BSpline face candidates when OCP is available
- Generated freeform face candidates remain candidate-only: not stitched, not a shell, not STEP-exported
- Trimming readiness assesses boundary and adjacency for future trimming; does not generate trimmed faces
- Reconstruction status aggregator summarizes all pipeline diagnostics into one report; does not create geometry or export STEP
- Segmentation quality assesses fragmentation/undersegmentation/fit-coverage/boundary quality; advisory-only, does not rerun segmentation
- OCP-unavailable environments skip honestly with clear diagnostics
- Freeform evidence does NOT trigger analytic STEP export or interfere with plane/cylinder reconstruction
- Missing/degenerate faces are skipped honestly (no false STEP)
- Only closed OCC-valid solids write STEP; partial shells do not
- Roundtrip verification checks STEP re-imports correctly

**Honesty boundaries:**
- Reconstruction is mesh-derived and lossy; not original design history
- Dominant surface classes: plane, cylinder, sphere, cone, torus
- Freeform/BSpline fitting is evidence-only v0; NOT B-Rep faces, NOT STEP, NOT CAD-editable
- Freeform readiness scoring is advisory/readiness-only; does NOT generate B-Rep faces or export STEP
- Freeform face candidates are candidate-only; NOT stitched, NOT a solid, NOT STEP-exported
- Freeform trimming readiness is diagnostic-only; does NOT generate trimmed faces, stitch, or export STEP
- Reconstruction status aggregator is diagnostic-only summary; does NOT create geometry, stitch, sew, or export STEP
- Segmentation quality and re-segmentation hints are advisory-only; do NOT rerun segmentation or modify geometry
- `geometry/reconstructed.step` never overwrites the source STEP
- Failed reconstruction removes stale artifacts and restores mesh topology

---

## 3. Assembly-Aware Topology Optimization Demo

**Purpose:** Validate the full assembly-aware topopt pipeline: assembly IR → interface resolution → CAE proxy model → topopt problem derivation → optimization → post-verification → design recommendations.

**Test file:** `aieng-ui/backend/tests/test_assembly_topopt_demo.py` (2 tests)

**Fixture:** `aieng-ui/backend/tests/fixtures/assembly_topopt_demo/`

**Run:**
```bash
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q
```

**Expected artifacts:**
- `assembly/assembly_ir.json` — 3-part assembly (bracket=design, wall/load_jig=frozen)
- `assembly/part_registry.json` — part roles and placements
- `assembly/connection_graph.json` — rigid_tie + bolted_proxy connections
- `assembly/interface_resolution.json` — resolved interface geometry
- `simulation/assembly_cae_model.json` — solver-neutral proxy model
- `analysis/assembly_topopt_problem.json` — derived topopt problem
- `analysis/assembly_topology_optimization.json` — optimization result
- `parts/bracket/geometry/optimized_shape_ir.json` — derived design-part Shape IR
- `diagnostics/assembly_post_optimization_verification.json` — scope verification
- `analysis/assembly_design_recommendations.json` — advisory recommendations
- `analysis/assembly_next_actions.json` — suggested next steps

**Expected behavior:**
- `test_canonical_demo_package_runs_full_loop_and_preserves_scope`
  - Assembly validation passes
  - Standard topopt problem emitted
  - Optimization runs on selected design part (`bracket`)
  - Frozen parts (`wall`, `load_jig`) are NOT modified
  - Package-level `geometry/shape_ir.json` is NOT overwritten
  - Preserve regions (mounting + load interfaces) stay traceable
  - Post-verification passes; recommendations written
- `test_canonical_demo_package_unsafe_data_stays_needs_input_and_does_not_overwrite`
  - Missing load data → `status: needs_user_input`
  - No geometry overwritten; no false artifacts created

**Honesty boundaries:**
- Connections are **proxies only**: rigid_tie, bonded, bolted_proxy, welded_proxy, contact_proxy, spring_proxy
- **No real nonlinear contact physics** — no friction, no real contact forces
- **No bolt preload** modeled
- Optimizes **one selected design part only**; simultaneous multi-part optimization is future work
- `production_ready: False`, `contact_physics_modeled: False`, `bolt_preload_modeled: False`

---

## 4. Agent-Guided Parameter Design Study Demo

**Purpose:** Validate the full PR1–PR6 design-study pipeline: problem contract → candidate validation → execution → candidate-local evaluation → advisory candidate hints → ranking → explicit acceptance.

**Test file:** `aieng-ui/backend/tests/test_design_study_demo.py` (6 tests)

**Fixture:** `aieng-ui/backend/tests/fixtures/design_study_demo/`

**Run:**
```bash
pytest aieng-ui/backend/tests/test_design_study_demo.py -q
```

**Expected artifacts:**
- `analysis/design_study_problem.json` — problem with 4 variables, constraints, objective
- `diagnostics/design_study_problem_diagnostics.json` — problem validation
- `diagnostics/design_study_candidate_validation.json` — per-candidate validation
- `patches/design_candidates/<candidate_id>.json` — 5 candidate patches
- `candidates/<candidate_id>/geometry/shape_ir.json` — derived Shape IR (valid candidates)
- `candidates/<candidate_id>/analysis/static_metrics.json` — deterministic demo evidence (no solver)
- `candidates/<candidate_id>/analysis/cae_evaluation_request.json` — explicit CAE evaluation request
- `candidates/<candidate_id>/diagnostics/cae_evaluation_request.json` — CAE evaluation diagnostics
- `candidates/<candidate_id>/simulation/setup.yaml` — candidate-local CAE setup derived from baseline
- `candidates/<candidate_id>/analysis/evaluation.json` — normalized candidate-local evaluation
- `candidates/<candidate_id>/diagnostics/evaluation_report.json` — evaluation missingness/constraint diagnostics
- `analysis/design_study_candidate_hints.json` — advisory next-candidate parameter hints
- `diagnostics/design_study_candidate_hints_report.json` — hint diagnostics and evidence coverage
- `analysis/design_study_iterations.json` — execution history
- `diagnostics/design_study_report.json` — aggregated report
- `analysis/design_study_candidate_ranking.json` — ranked candidates
- `diagnostics/design_study_scoring_report.json` — scoring diagnostics
- `analysis/design_study_acceptance.json` — acceptance record
- `diagnostics/design_study_acceptance_report.json` — acceptance diagnostics
- `accepted/candidate_good/geometry/shape_ir.json` — accepted derived geometry
- `accepted/candidate_good/provenance/acceptance.json` — acceptance provenance

**Expected behavior:**
- `test_canonical_demo_package_full_flow`
  - Validate: 5 candidates checked, problem passes
  - `candidate_bad_bounds` → rejected (out of bounds)
  - `candidate_protected` → rejected (tries to change protected `bolt_dia`)
  - `candidate_good`, `candidate_unknown`, `candidate_infeasible` → patch applied
  - Inject deterministic static metrics into candidate workspaces
  - Explicit candidate-local CAE evaluation request (`normalize_existing` mode) for all valid candidates
  - `candidate_good` → feasible, score > 0, **best_candidate_id**
  - `candidate_infeasible` → infeasible (stress 250 > limit 200)
  - `candidate_unknown` → insufficient_data / unknown (no metrics)
  - Rank → explicit hints → accept `candidate_good` → `accepted: True`, `promotion_mode: derived_only`
  - Baseline Shape IR **never modified**
- `test_unsafe_data_rejects_acceptance`
  - Only bad candidates executed → no viable candidate → acceptance blocked
- `test_non_best_candidate_needs_override`
  - Non-best candidate requires `override_unsafe`; unknown always rejected
- `test_missing_ranking_blocks_acceptance`
  - Acceptance without prior ranking → `needs_user_input`
- `test_hints_after_acceptance_are_conservative`
  - After acceptance, hints become stop-style / conservative
- `test_cae_evaluate_endpoint_normalize_existing`
  - `/cae-evaluate` endpoint produces candidate-local artifacts, skips solver, leaves baseline untouched

**Honesty boundaries:**
- Uses **static/solver-neutral candidate-local metrics only** — no external solver is executed
- **No autonomous optimization** — candidates are explicitly proposed and executed one at a time
- **No baseline overwrite** — accepted candidate is a derived artifact only
- **No production approval** claimed
- Ranking is advisory; `safe_to_accept` is conservative
- Candidate hints are advisory; they never create patches, execute candidates, or mutate geometry
- Missing metrics produce `needs_more_evaluation`, not overconfident acceptance
- Candidate CAE evaluation request is explicit and candidate-local; solver execution is disabled by default

---

## 5. 2D Topology → Sizing → CAE End-to-End Demo

**Purpose:** Validate the full Phase 4 bridge on a plate-with-loads 2D case: topology optimization result → contour writeback → auto-parameterization → sizing study → candidate sampling → CAE validation → ranking → recommendation → approval-gated acceptance.

**Test files:**
- `aieng-ui/backend/tests/test_topology_sizing_backend_demo.py` (3 tests)
- `aieng/scripts/run_topology_sizing_demo.py` (scripted demo)

**Run:**
```bash
pytest aieng-ui/backend/tests/test_topology_sizing_backend_demo.py -q
python aieng/scripts/run_topology_sizing_demo.py --out build/topology_sizing_demo.aieng
```

**Expected artifacts:**
- `analysis/topology_optimization.json` — source topology result (2D, `dimension: 2d`)
- `geometry/shape_ir.json` — baseline contour writeback as `extruded_region`
- `analysis/design_study_problem.json` — sizing problem with `extrusion_thickness` variable
- `analysis/optimization_variables.json` — resolved variable binding to `parts/0/thickness`
- `analysis/optimization_objectives.json`, `analysis/optimization_constraints.json`, `analysis/optimization_study.json` — sizing-study envelope
- `analysis/optimization_decision_log.json` — chain-linkage entry with `production_ready=false`
- `patches/design_candidates/*.json` — sampled thickness candidates
- `candidates/<id>/geometry/shape_ir.json` — derived candidate geometry
- `candidates/<id>/analysis/evaluation.json` — candidate-local feasibility evaluation
- `analysis/design_study_candidate_ranking.json` — ranked candidates
- `analysis/optimization_recommendation.json` — advisory recommendation
- `analysis/design_study_acceptance.json` — explicit acceptance record
- `accepted/<id>/geometry/shape_ir.json` — accepted derived geometry
- `diagnostics/optimization_report.json` — aggregated report with `topology_to_sizing_chain`
- `provenance/tool_trace.json` — tool-trace entries for `parameterize_topology_writeback` and `topology_to_sizing`

**Expected behavior:**
- `test_topology_sizing_backend_demo_end_to_end`
  - `POST /api/projects/{id}/topology-optimization/sizing` returns `status: ok`
  - Sampler produces candidates from `extrusion_thickness`
  - Candidates execute without external CAD (`compile: false`)
  - Deterministic analytical volume/mass metrics injected per candidate
  - Ranking finds a feasible best candidate with `safe_to_accept: true`
  - Recommendation is advisory-only
  - Acceptance closes the loop on the best candidate; baseline geometry untouched
  - Report aggregates the full chain and surfaces `topology_to_sizing_chain`
  - Tool trace records both parameterization and sizing steps
- `test_topology_sizing_refuses_3d_honestly`
  - 3D topology result returns `status: needs_user_input`, `code: 3d_or_non_2d_not_supported`
  - No sizing artifacts are written
- `test_topology_sizing_refuses_non_extruded_body_honestly`
  - Non-extruded writeback returns `status: needs_user_input`, `code: no_stable_parameter`
  - No sizing artifacts are written

**Honesty boundaries:**
- Only 2D contour `extruded_region` writebacks are supported; 3D/voxel/non-extruded bodies are refused
- `production_ready: false` and `human_approval_required_for_acceptance: true` are explicit
- No external solver is executed; metrics are analytical stand-ins
- Volume/mass are present; stress/displacement are absent (not fabricated)
- Baseline `geometry/shape_ir.json` is never overwritten
- Acceptance is approval-gated and produces a derived-only workspace

---

## Suggested Smoke Commands

Run all canonical demos:

```bash
# Topology optimization (2D + experimental 3D)
pytest aieng/tests/test_topology_optimization.py -q

# Mesh-to-CAD reconstruction (segmentation → fitting → stitching → solidification)
pytest aieng/tests/test_mesh_brep_solidification.py -q

# Assembly-aware topology optimization
pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q

# Agent-guided parameter design study (PR1–PR6)
pytest aieng-ui/backend/tests/test_design_study_demo.py -q

# 2D topology → sizing → CAE end-to-end
pytest aieng-ui/backend/tests/test_topology_sizing_backend_demo.py -q
```

Run the full backend design-study suite:

```bash
pytest aieng/tests/test_design_study*.py aieng-ui/backend/tests/test_design_study_demo.py aieng-ui/backend/tests/test_topology_sizing_backend_demo.py -q
```

---

## Known Limitations

| Capability | Limitation | Status |
|------------|-----------|--------|
| 3D SIMP topology optimization | Experimental/structured-voxel; not production-certified | `production_ready: False` |
| Assembly CAE | Proxy connections only; no real contact/friction | `contact_physics_modeled: False` |
| Assembly CAE | No bolt preload modeled | `bolt_preload_modeled: False` |
| Mesh-to-CAD reconstruction | Freeform/NURBS fitting is future work | Plane/cylinder/sphere/cone/torus dominant |
| Design study | No autonomous optimization or Pareto search | Explicit single-shot execution only |
| Design study | Candidate evaluation reads existing static/neutral/proxy artifacts only | No solver/recompile/promotion during evaluation |
| Design study | Candidate hints are advisory only | No patch generation, execution, CAE, ranking, acceptance, or geometry mutation |
| Design study | Candidate CAE evaluation request is explicit and candidate-local | Solver execution disabled by default; baseline artifacts never overwritten |
| Topology → sizing | 2D contour extrusions only; 3D/voxel/non-extruded refused | `production_ready: False`; human approval required |
| Topology → sizing | Analytical volume/mass only; no stress/displacement | Static/neutral evidence; external solver not executed |

---

## Backend stability gate

A lightweight smoke-test gate validates that canonical demos, key artifacts, and honesty boundaries remain consistent. It does **not** run heavy subprocess tests; it checks file existence, doc alignment, and honesty-boundary coverage.

**What it checks:**
- Canonical demo/test files exist (`test_topology_optimization.py`, `test_mesh_brep_solidification.py`, `test_assembly_topopt_demo.py`, `test_design_study_demo.py`, `test_showcase_gallery_docs.py`)
- Key artifact names are referenced in docs
- Honesty boundary text is present in canonical docs
- Showcase gallery JSON and markdown stay aligned

**How to run:**
```bash
pytest aieng/tests/test_backend_stability_gate.py -q
```

**Why it exists:**
Long-term reliability depends on docs, tests, and artifact contracts staying in sync. The gate catches renames, deletions, and drift before they confuse users or downstream tooling.

**What it is not:**
This is a consistency smoke test, not a full production certification suite. It does not replace the focused demo tests above, nor does it validate runtime correctness.

---

## Related Documentation

- [`showcase_gallery.md`](showcase_gallery.md) — Showcase with demo talking points and visual guidance
- [`showcase_gallery.json`](showcase_gallery.json) — Machine-readable gallery manifest
- [`backend_capability_matrix.md`](backend_capability_matrix.md) — Capability status matrix
- [`backend_artifact_reference.md`](backend_artifact_reference.md) — Complete artifact path reference
- [`roadmap.md`](roadmap.md) — Phase-by-phase development roadmap
- [`AGENTS.md`](../../AGENTS.md) — Agent guide with workflow examples
