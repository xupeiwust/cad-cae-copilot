# Roadmap

This document describes the suggested phases beyond the Phase 5D stabilization checkpoint.

The project thesis is: adapt CAD/CAE data to AI. `.aieng` is primarily a CAD/CAE-side semantic export and evidence package, not an agent tool. Each phase should advance the format's ability to carry real engineering semantics, real geometry/CAE references, or externally produced validation evidence ? not add AI orchestration, specialized training, meshing, solving, or external service integration.

Execution boundary: `.aieng` describes, references, configures, and records. External CAD/CAE software remains responsible for geometry editing, mesh generation, solver execution, result generation, and manufacturing checks. Future `.aieng` work may import or reference mesh/solver evidence, but `.aieng` core is not intended to become a mesher, solver, optimizer, planner, or agent runtime. MCP remains an optional access interface.

---

## Phase 30 — Automated LLM Engineering-Usefulness Benchmark — COMPLETE (2026-05-17)

**Scope:** `aieng` benchmarks

**Goal:** Measure whether an LLM equipped with `.aieng` structured evidence access produces better engineering proposals than the same LLM without it, on bounded, repeatable, A/B scenarios.

**Delivered:**
- Four shipped CAE reasoning scenarios via `inspect_ai`:
  1. **Mass reduction recommendation** — choose safest mass-reduction proposal given stress results.
  2. **Diagnose broken CAE setup** — identify cross-reference defect in deliberately-broken package.
  3. **Stress concentrator recommendation** — identify high-stress feature and propose design response.
  4. **Setup correction / missing items** — audit a CAE setup for missing artifacts and dangling references.
- Two-axis scoring: correctness (`accuracy()`) and token-efficiency (`mean()`).
- Deterministic substring rubric + hallucination-penalty guards.
- Condition A (raw dump) vs Condition B (structured `.aieng` tool access).
- Observation reports per run under `results/runs/`.

**Measured findings (Kimi `kimi-for-coding`, n=10, temperature=0):**
- Scenarios 1–3: both conditions reach full correctness; Condition B is 3.5–7.5× more token-efficient.
- Scenario 4: **first measured correctness divergence** — Condition A 0.450 accuracy (3 C / 3 P / 4 I), Condition B 0.950 accuracy (9 C / 1 P / 0 I). Dominant A failure modes were unsafe "ready for solver" overclaims and phantom artifact hallucinations.
- Package-size crossover: structured access loses on tiny packages (~700 tokens), wins on scaled packages.

**Honest limitations:**
- Single model, single scenario for the correctness divergence — not yet a general claim.
- Deterministic scorer is conservative; novel correct answers that miss keyword patterns are undercounted.
- Benchmark measures understanding and honesty, not whether recommendations would actually fix the design.

**Future benchmark work:**
- Second model evaluation to check cross-model consistency.
- Stochastic trials (temperature > 0) to measure variance.
- More package-size crossover measurements.
- LLM-graded rubric for open-ended reasoning (later phase).

---

## Phase 35 — Design-Target Evidence Resource — COMPLETE (2026-05-17)

**Scope:** `aieng` + `aieng-ui`

**Goal:** Formalize `task/design_targets.yaml` as a first-class package resource so benchmark scenarios and engineering workflows no longer inline design goals only in prompts.

**PR 1 — Schema / docs / examples alignment (done)**
- Extend `schemas/design_targets.schema.json` with richer target types, comparators, scope, and protected-feature semantics.
- Support dual format: legacy `0.1.0` (`id`/`metric`/`operator`/`value`) and modern `0.1.1` (`target_id`/`target_type`/`comparator`/`threshold`/`description`/`priority`).
- Create `schemas/design_target_comparison.schema.json` for the comparison block inside `result_summary.json`.
- Add canonical example: `examples/design_targets/bracket_mass_reduction/design_targets.yaml`.
- Add tracked docs page: `docs/design_targets.md`.
- Tests: schema validation for extended types, invalid comparator rejection, missing `target_id` rejection, objective_priority validation, comparison schema validation.

**PR 2 — Structured comparison logic (done)**
- Extend `_validate_design_targets()` for new comparators and required-field checks.
- Extend `_compare_design_targets()` to emit `design_target_comparisons` block with `unknown`/`not_evaluated` semantics.
- Map new target types (`preserved_interface`, `objective_priority`) to honest comparison behavior.
- Status semantics: `pass`, `fail`, `unknown`, `not_evaluated`.

**PR 3 — CLI command + result_summary writeback (done)**
- Add `aieng compare-design-targets <package>` CLI with `--output json|text` and `--write-summary`.
- Atomic ZIP writeback of comparison block into `results/result_summary.json`.
- Never mutates claim proposals (claim proposals require human review).

**PR 4 — Benchmark Scenario 2 integration (done)**
- Move mass-reduction target and safety-factor floor from prompt-only into `task/design_targets.yaml`.
- Condition A remains fair: raw dump includes `task/design_targets.yaml`.
- Condition B references the structured package resource.
- README measured numbers unchanged; historical observation reports preserved.

**PR 5 — UI display (done in `aieng-ui`)**
- Surface `design_target_comparisons` in project summary API.
- Render pass/fail/unknown badges in the CAE panel.

**Post-PR5 MCP inspection checkpoint (done in `aieng-freecad-mcp`)**
- `aieng_read_design_targets` — read-only MCP tool that reads `task/design_targets.yaml` from `.aieng` packages
- `aieng_read_design_target_comparisons` — read-only MCP tool that reads `results/result_summary.json#design_target_comparisons`
- Both tools work with zip and directory-form packages, return missing-resource states gracefully, and do not mutate packages or advance claims
- Safe for agent preflight / evidence inspection
- Future: use this context to gate/advise CAD mutation proposals

**Stabilization fixes shipped with this phase:**
- Issue #59 — OCC/STEP environment-gated false failure cascade: tests that only need topology setup now explicitly use `--backend mock`; capability probe `has_working_occ_step_backend()` added.
- Issue #60 — Negated ready-for-solver rubric penalty: Scenario 4 scorer no longer penalizes correctly negated statements such as "not ready for solver" or `ready_for_solver: false`.

**Boundary rules preserved:**
- Design targets are requirements, not solver results.
- Claim proposals require human review; comparisons do not advance claims.
- Missing evidence produces `unknown` or `not_evaluated`, never fake pass/fail.

---

## Phase 36 — CAD-modification Recommendation Primitive — COMPLETE (2026-05-19)

**Scope:** `aieng`

**Goal:** First step of the trustworthy CAD/CAE Copilot loop. Given the design targets, computed metrics, and per-feature stress already produced by Phases 19/21/35, emit a ranked list of CAD-modification proposals an agent can reason about. Verification (Phase 37) and execution (Phase 38+) are deliberately out of scope.

**Delivered:**
- `src/aieng/cae_recommendation.py`:
  - `generate_cad_modification_recommendations(package_path)` reads `task/design_targets.yaml`, `results/computed_metrics.json`, `results/stress_by_feature.json`, and `simulation/cae_imports/parsed_features.json`; emits a structured `proposals` block (schema `0.1`) with rank, action_type, parameter_change, rationale, expected_impact, confidence, targets_addressed, and risks.
  - `generate_recommendations_markdown(recommendations)` — human/LLM-readable form.
  - Modification vocabulary: `thin`, `thicken`, `add_fillet`, `resize_hole`, `remove`, `reduce_count`. Deliberately small — broader vocabulary deferred until the verification gate exists.
- Ranking rules:
  - Mass-reduction: rank by `(safety_factor / min_required_sf) * mass_contribution_kg`; refuse features with SF ratio < 1.2; holes excluded (negative mass).
  - Stress-rescue: triggered only when current `minimum_safety_factor < required min_SF`; propose `thicken` for thickness features, `add_fillet` for holes.
  - Preserved-interface targets remove features from the candidate set.
- CLI: `aieng recommend-cad-modifications <package> [--output text|json]`.
- Tests (`tests/test_cae_recommendation.py`, 13 tests): ranking determinism (top pick is `back_wall`), refusal on thin-margin features, preserved-feature skip, stress-rescue trigger, byte-identical package after run, directory-form support, vocabulary closure, honest llm_summary block, missing-input warnings.

**Boundary rules preserved:**
- Proposals are **hypotheses**, not evidence. `claim_policy.proposals_are_hypotheses = true`, `claims_advanced = false`, `requires_verification_simulation = true`.
- The recommender is read-only: no package mutation, no claim advancement, no CAD/CAE execution.
- Numerical impact ("~ 0.755 kg saved") is qualitative scaling, not a solver prediction.

**Validated against benchmark:** Running the CLI on `benchmarks/llm_engineering_usefulness/scenarios/mass_reduction_recommendation/fixture.aieng` returns `back_wall thin 20.0 -> 10.0 (confidence=high)` as proposal #1 — the engineered-correct answer for the scenario.

**Next phases:**
- **Phase 37** — Verification gate (now ✅).
- **Phase 38** — Closed-loop orchestrator (agent skill): recommend -> verify -> execute -> re-simulate -> compare.
- **Phase 39** — Explainability surface in `aieng-ui` (proposal trace + verification verdict).

---

## Phase 37 — Pre-execution Verification Gate — COMPLETE (2026-05-19)

**Scope:** `aieng`

**Goal:** Trust layer between the Phase 36 recommender and the Phase 38 execution adapter. Reject obviously-unsafe CAD modification proposals *before* they touch geometry, surface predicted-risk warnings for human/agent review, and keep re-simulation as the authoritative correctness check.

**Delivered:**
- `src/aieng/cae_verification.py`:
  - `verify_cad_modification_proposal(proposal, package_path, *, strictness)` — single-proposal verifier returning a verdict (`pass` / `warn` / `fail`) plus per-check results (schema 0.1).
  - `verify_recommendations(recommendations, package_path, ...)` — batch verifier consuming the Phase 36 output.
  - `generate_verification_markdown(verification)` — human/LLM-readable form.
- Seven checks across three categories:
  - **schema.proposal_shape**, **schema.action_in_vocabulary**, **schema.feature_exists**, **schema.parameter_change**, **schema.preserved_feature_not_modified** — block on fail.
  - **manufacturability.parameter_floor** — hard floors (`thickness_mm ≥ 1.0`, `diameter_mm ≥ 2.0`, `fillet_radius_mm ≥ 0.2`); block on fail.
  - **regression.thinning_sf_floor** — predicts post-thinning SF using `SF_after ≈ SF_before × (t_after/t_before)^2` (bending heuristic); block in `default`/`strict`, warn in `lenient`.
  - **regression.thicken_when_unnecessary** — warns when a feature already meets SF floor; promoted to fail in `strict`.
- Strictness modes: `lenient` (regression predicted-violations downgraded to warnings), `default`, `strict` (any warning blocks).
- CLI: `aieng verify-cad-modifications <package> [--proposals <json>] [--strictness lenient|default|strict] [--output text|json]`. Exit code 1 if any proposal fails.
- 19 new tests in `tests/test_cae_verification.py`.

**Validated against benchmark + Phase 36 output:** Running the full chain on the `mass_reduction_recommendation` fixture, the gate correctly **passes** the engineered-correct `back_wall thin 20→10` (predicted SF 3.98 >> 1.5) and **blocks** the two over-aggressive proposals `flange thin 12→6` (predicted SF 0.80) and `reinforcement_gusset thin 6→3` (predicted SF 1.34).

**Boundary rules preserved (and tested):**
- Verification is pre-execution heuristic only; `claim_policy.verification_does_not_replace_resimulation = true`.
- No geometry-kernel checks (`geometry_kernel_checks_not_performed = true`) — that scope defers to a future `aieng_freecad_mcp` Phase 37b.
- Read-only on the package (`test_package_is_not_mutated`).
- No claim advancement.

**Next phases:**
- **Phase 38** — Closed-loop orchestrator skill in `aieng-agent-skills` chaining recommend → verify → execute → re-simulate → compare, with stop conditions (target met / budget exhausted / no improvement).
- **Phase 39** — Explainability panel in `aieng-ui` surfacing the verification trace.
- **Phase 37b (deferred)** — Geometry-kernel checks in `aieng_freecad_mcp` (does the modified topology remain valid? do face IDs survive?).

---

## Phase 20: General CAD/CAE conversion contract + FreeCAD reference converter — COMPLETE (2026-05-13)

Goal: validate whether `.aieng` can be generated from a real CAD-side source through a capability-based converter interface, while keeping the core boundary intact.

`.aieng` is a CAD/CAE-to-AI semantic conversion and packaging format. It is not an automation runtime, not an agent framework, and it does not execute solvers, meshers, optimizers, or CAD edits. Converters built on this contract obey the same rule.

Delivered:

- `docs/cad_cae_conversion_contract.md` — general contract for any CAD/CAE-to-`.aieng` converter, with capability levels L0–L5 (source metadata, geometry/topology, object registry, feature-aware, editability metadata, roundtrip writeback metadata).
- `schemas/converter_capabilities.schema.json` — static, source-agnostic capability profile.
- `schemas/conversion_manifest.schema.json` — per-package conversion record (`provenance/conversion_manifest.json`).
- `manifest.json` `source_mode` enum extended with `converter`; `completeness_report.json` categories extended with `source_conversion`; `feature_graph.json` `parameter_source` enum extended with `converter_extracted`.
- `src/aieng/converters/` — converter framework: base types, registry, writer (creates the `.aieng`, conversion manifest, optional capabilities snapshot, refreshes completeness), readiness helper.
- `src/aieng/converters/freecad.py` — FreeCAD reference converter. Two modes: **offline** (parses FCStd zip + Document.xml; no FreeCAD installation required; supports L0+L2+L3-candidate+L4 when parameters are present) and **runtime** (detects FreeCAD; still defers topology extraction to `aieng extract-topology --backend occ` on STEP exports).
- CLI: `aieng convert`, `aieng converter-capabilities`, `aieng readiness-report`.
- Validator: schema lookup + semantic checks for both new resources; `source_mode=converter` requires `provenance/conversion_manifest.json`; missing topology in converter-sourced packages downgraded from FAIL to WARN.
- Sample fixture: `examples/sample_bracket.FCStd` generated by `scripts/generate_sample_fcstd.py`.
- Tests: 16 new tests covering the contract, the FreeCAD converter, end-to-end conversion + validate, and the readiness demo. All 1106 existing tests continue to pass.

Boundary preserved:
- Converters do not run solvers, meshers, optimizers, or CAD edits.
- All feature recognition is heuristic and explicitly marked with confidence + uncertainty notes.
- `.aieng` core does not call FreeCAD/Gmsh/CalculiX/optimizers; FreeCAD runtime detection is offline-equivalent until external tools or adapters run.

What this phase explicitly does **not** introduce:
- A universal CAD emitter (the FreeCAD path is one reference implementation).
- A GUI, viewer, or 3D rendering surface.
- An agent runtime, planner, or workflow loop.
- Calls to Gmsh, CalculiX, or other solvers/meshers from inside `.aieng`.
- Optimization loops or automatic design modification.
- Any new engineering claim semantics.

Future converters (NX, SolidWorks, CATIA, Onshape, Abaqus deck parsers, etc.) should follow the same contract in their own modules or external repositories. They are out of scope for Phase 20.

## Phase 23: Experimental 3D SIMP topology optimization — COMPLETE (2026-05-30)

Plugs a self-contained 3D optimizer into the existing topology-optimization
registry and reuses the Shape IR writeback/viewer pipeline. Experimental
structured-voxel reference — NOT production.

- `register_optimizer` gained an optional `capability` block (dimension, method,
  physics, mesh, material, backend, engineering_level, production_ready) echoed
  into the result's `optimizer`. `simp_3d` registers as
  `experimental_reference` / `production_ready:false`.
- `simp_3d`: 8-node hex (H8) SIMP on a structured voxel grid — KE built by 2×2×2
  Gauss integration, dense numpy FE solve on free dofs, classic OC update +
  3D sensitivity filter, pure numpy (no scipy/solver). Explicit 3D `bcs.supports`/
  `bcs.loads` (voxel cells, full 3D force) or a `cantilever_3d` preset; honest
  warnings on weak convergence / coarse grids. Returns `density_3d` ([nz][ny][nx]).
- Contract: `run_topology_optimization` detects 3D and emits `dimension:3d`,
  `density_grid_3d`, `solid_voxel_count`, `objective/compliance_history`, `frame`,
  `bcs_source`, `design_space_node`/`source_ir_node`, `load_case_id`, and 3D
  limitations.
- 3D derivation (`derive_topopt_problem_3d_from_package`): structured voxel grid
  from the design-space bbox (no projection); fixed/support faces → boundary voxel
  layers, load faces → boundary cells with the FULL 3D force vector. If a usable
  support AND load can't be mapped, returns `status:needs_user_input` + diagnostics
  instead of guessing.
- Writeback: `density_voxel_cells` + `topology_result_to_shape_ir` extended to 3D
  density grids — placed in the design-space frame, default runtime `manifold_mesh`,
  tagged `preview/design_suggestion/voxelized/lossy/not_production_cad`. Workbench
  `dimension=3d` routing in derive/run; writeback auto-defaults 3D to mesh; viewer
  asset refreshes.
- **3D smooth mesh proxy (follow-up):** `method=surface` (the 3D writeback default)
  runs marching cubes (`skimage.measure.marching_cubes`, zero-padded) on the density
  grid → a `surface_mesh` node (vertices/faces in the design-space frame, winding
  oriented to a positive signed volume), compiled by the manifold runtime via
  `Manifold(Mesh(...))`. Turns the blocky voxel preview into a smooth watertight mesh
  — still tagged mesh / lossy / not production CAD. Falls back to voxels if no
  isosurface crosses the threshold (or scikit-image is absent). B-Rep/NURBS
  reconstruction of the voxel/mesh body remains a separate future milestone (no
  spline/marching-cubes→CAD here). Tests: surface writeback emits a `surface_mesh`
  with verts/faces; empty field → voxel fallback; manifold compile yields a
  positive-volume watertight body.
- Tests: simp_3d registered w/ capability; 3D cantilever lowers compliance + meets
  volfrac; explicit 3D BCs respected; contract has density_grid_3d/frame; 3D voxel
  placement; manifold compile yields a non-empty body in the frame; 3D derive maps
  supports/loads (full vector) + solves; needs_user_input without BCs; backend 3D
  endpoint (derive→run→writeback→viewer) + needs_user_input. No 2D regression.

## Phase 22: Topology optimization (contract + 2D SIMP) — COMPLETE (2026-05-30)

CAE-driven generative step after analysis, following the same contract-first,
pluggable-backend pattern as solvers.

- `converters/topology_optimization.py`: neutral problem/result contract +
  pluggable optimizer registry (`register_optimizer` / `available_optimizers` /
  `run_topology_optimization`). Built-in `simp_2d` is a self-contained 2D SIMP
  (compliance minimization, OC update + sensitivity filter, **pure numpy** — no
  scipy/CalculiX/external solver), presets cantilever / mbb_beam. `precomputed`
  optimizer ingests a density grid (proves the optimizer layer is neutral).
- Output `analysis/topology_optimization.json`: optimizer provenance
  (name/version/method/dimension/fallback), objective + compliance history,
  achieved volume fraction, density grid, threshold/solid-element count, and a
  `design_space_node` link back to a Shape IR node. Honest `limitations`
  recorded (2D, plane-stress, linear-elastic, single material, coarse —
  observational design aid, not production).
- Workbench `opt.run_topology_optimization` (tool + `POST .../topology-optimization`)
  runs it and writes the artifact. Consumes the design space + (future) loads from
  the solver-neutral CAE map.
- **Writeback (closes the generative loop):** `topology_result_to_shape_ir` /
  `write_shape_ir_from_topology_optimization` author the optimization result back
  into `geometry/shape_ir.json` as ONE `density_voxels` node. A new
  `density_voxels` node kind + compiler support in **both** backends
  (`shape_ir.density_voxel_cells` thresholds the field; the build123d compiler
  emits a labelled `Compound` of extruded boxes, the manifold compiler a CSG union
  loop → watertight mesh) make the optimized field a first-class, re-compilable,
  viewable shape that flows through the same pipeline as any Shape IR (compile →
  mesh/GLB, topology, verification, object_registry) and stays linked to its
  `design_space_node`. Workbench `opt.writeback_to_shape_ir`
  (tool + `POST .../topology-optimization/writeback`) writes + recompiles;
  default representation `manifold_mesh`, `brep_build123d` also supported.
- Tests: SIMP lowers compliance + meets the volume budget (cantilever); contract
  + provenance + design_space_node passthrough; precomputed optimizer neutrality;
  registry + unknown-optimizer fallback; artifact write; backend endpoint;
  density_voxel thresholding/placement; writeback payload + density_voxels
  compiles + executes in both backends (manifold vol>0, build123d labelled
  Compound); writeback into package + recompile via the endpoint.
- **Problem derivation from CAE (closes the input side):**
  `derive_topopt_problem_from_package` builds the optimization `problem` from the
  project's real CAE intent instead of a preset — it reads
  `geometry/topology_map.json` (design-space bbox + face geometry),
  `simulation/cae_mapping.json` (feature→face links) and the CAE setup
  (`simulation/setup.yaml` supports/loads), then PROJECTS the 3D supports/loads
  onto the plane of the two largest design-space dimensions and maps them to grid
  cells. `simp_2d` now consumes explicit cell-based `bcs.supports`/`bcs.loads`
  (via `_resolve_bcs`/`_explicit_bcs`), not just presets. The result carries a
  `derivation` block (projection plane, design-space frame = origin + cell size +
  thickness for a later writeback, source BC links, warnings) and honest 3D→2D
  limitations; out-of-plane force components are dropped (plane-stress) and
  missing/degenerate BCs fall back to a preset with a warning. Workbench
  `opt.derive_problem_from_cae` (read-only, tool + `POST .../topology-optimization/
  derive`) returns the problem; `opt.run_topology_optimization` gained
  `auto_derive` (implied when `problem` is omitted) to derive-then-solve in one
  call.
- Tests (problem derivation): explicit cell-based BCs solve + lower compliance;
  degenerate explicit BCs fall back to preset; derive from a synthetic CAE
  package (plane pick x>y>z, support→left column, load cells, frame, design space
  node); purely-out-of-plane load is dropped + warned; in-plane load yields a
  usable problem that solves; no-BC package falls back to preset; backend derive
  endpoint + auto_derive run path.
- **Frame-aware writeback (input frame → output placement):** the derivation
  `frame` (design-space bbox origin + in-plane axes + cell size + thickness) now
  flows through `run_topology_optimization` into the writeback, so the optimized
  body lands in the design space's own coordinate frame instead of an abstract
  unit grid at the world origin. `density_voxel_cells` was generalized to place
  voxels on an arbitrary plane (the `density_voxels` node carries `u_axis`/
  `v_axis`; the extrusion axis is the remainder), and `topology_result_to_shape_ir`
  reads the frame by default (`use_frame`), with explicit
  `cell_size`/`thickness`/`origin` still overriding. Verified e2e: a derived
  120×80×10 plate writes back a body whose executed mesh bbox is exactly
  `[0,0,0]..[120,80,10]`, not a 12×8 unit grid.
- Tests (frame placement): `density_voxel_cells` honors a non-XY plane (XZ) with
  origin offset; `topology_result_to_shape_ir` uses the frame by default, explicit
  args override, no-frame falls back to a unit grid; full derive→run→writeback
  tiles the design-space extents exactly.
- **Contour-ized writeback (silhouette, not pixels):** the optimized field can be
  written back as a smooth boundary instead of blocky voxels.
  `extract_density_contours` runs marching squares (`skimage.measure.find_contours`
  + `approximate_polygon`, on a zero-padded field) to get the material silhouette +
  internal holes as in-plane polygons; a new `extruded_region` Shape IR node +
  compiler in BOTH backends builds the solid by extruding them — build123d sketches
  the polygons on a placed `Plane` (holes subtracted by even-odd nesting depth),
  manifold builds a `CrossSection` (even-odd) extruded then placed by a single 3×4
  affine. A shared `_plane_basis` (with `sign_v` to keep handedness) means both
  paths reproduce the same world placement on any axis-aligned plane.
  `topology_result_to_shape_ir(method=…)` selects `voxels` (default in the core fn)
  or `contour`; the workbench `opt.writeback_to_shape_ir` defaults to `contour`
  (the design suggestion) and falls back to voxels with a recorded note when no
  contour can be extracted. Verified e2e: a 120×80×10 plate writes back a polygonal
  body (a handful of loops, not hundreds of boxes) that executes in both runtimes
  and lands in the design-space frame.
- Tests (contour): marching-squares returns a closed world-space loop;
  `extruded_region_geometry` bakes the plane basis + even-odd holes and flips v on
  an XZ plane; contour writeback emits a compilable `extruded_region`; empty field
  falls back to voxels; contour executes in manifold within the design space;
  backend writeback default = contour.
- **Spline boundary (curve, not polyline):** a contour loop can be interpreted as a
  closed periodic spline instead of straight segments. `extract_density_contours`
  simplifies more aggressively for splines (sparse, well-placed through-points); the
  `extruded_region` node carries `boundary: spline|polygon`. build123d builds a true
  closed periodic `Spline` per loop (`periodic=True`) → `make_face` (holes subtracted
  by even-odd) → extrude — a CAD-friendly curve / clean NURBS edge in the B-Rep
  runtime; the mesh runtime has no spline primitive, so `sample_periodic_catmull_rom`
  densifies each loop into a smooth polygon before the `CrossSection`. The raw
  polygon path is preserved as a fallback (`boundary=polygon`). `topology_result_to_
  shape_ir`/`write_shape_ir_from_topology_optimization` thread `boundary`; the
  workbench `opt.writeback_to_shape_ir` defaults to `spline`. Verified e2e: a ring
  field writes back outer+inner spline loops that extrude to a curved hollow body in
  both runtimes, placed in the design-space frame.
- Tests (spline): periodic Catmull-Rom densifies + stays closed; spline writeback
  emits a true `Spline(periodic=True)`+`make_face` in B-Rep and a densified
  `CrossSection` in mesh; polygon fallback preserved; ring extracts outer+inner loops
  → ADD/SUBTRACT; spline executes in manifold within the design space.
- Next: 3D SIMP (escape the plane-stress idealization).

## Phase 21: Shape IR converter + topology-first CAD compilation — COMPLETE (2026-05-30)

Goal: support complex/organic models that are awkward to author directly as
CadQuery/build123d code by introducing a structured Shape IR source format.

Implemented:

- `src/aieng/converters/shape_ir.py` — `shape_ir_reference` converter for
  `.shape.json` / `.shape_ir.json` sources.
- Converter writes `geometry/shape_ir.json`, generated build123d
  `geometry/source.py`, projected `geometry/topology_map.json`,
  `graph/feature_graph.json`, `objects/object_registry.json`, README, and
  standard converter provenance/capability manifests.
- Shape IR compiler maps node `type` / `kind` / `operation` values to build123d
  helper targets: `lofted_stack`, `rounded_box`, `capsule`, `swept_tube`,
  `revolved_profile`, `organic_blend`, plus primitive fallbacks.
- Workbench `aieng.convert` executes generated Shape IR `source.py` by default,
  writes `geometry/generated.step`, `geometry/preview.stl`, and
  `geometry/preview.glb`, then publishes the embedded preview to the viewer.
- Free-form topology now preserves richer `surface_type` values (`bspline`,
  `bezier`, `sphere`, `cone`, `torus`, surfaces of revolution/extrusion, or
  `freeform`) plus `freeform`, `uv_bounds`, `proxy_normal`, and
  Shape-IR-origin metadata when available.

Correctness fixes (2026-05-30):

- Transform compilation: a node carrying both `location` and `rotation` now
  compiles to a single `Location(translation, rotation)` (orient-in-place, then
  place). The previous code emitted two `.moved()` calls (translate, then rotate
  about the world origin), which orbited a placed part around the origin.
- Post-execution provenance reconciliation: when the workbench executes the
  generated `source.py`, the projected `topology_map.json` / `feature_graph.json`
  are replaced with REAL build123d geometry. `objects/object_registry.json` is
  now rebuilt against those executed entities and
  `provenance/conversion_manifest.json` is stamped with a `geometry_execution`
  record — so the package no longer carries projected slug ids that dangle
  against the real topology, nor a manifest that understates the geometry.

Boundary: the core converter records/generated source and semantic topology;
CAD-kernel execution happens in the workbench runtime, not inside the converter
framework itself.

Multi-target compilation (2026-05-30):

Shape IR is now a multi-backend source. `compile_shape_ir(payload)` dispatches by
`representation` (default `brep_build123d`) through a pluggable compiler
**registry** (`register_compiler(representation, compiler, source_path, runtime,
aliases)` — mirrors the converter registry; `available_representations()` lists
the canonical targets) and reports `{representation, requested_representation,
source, source_path, runtime, fallback}`; unknown targets fall back to build123d
with `fallback=True`. New backends register as plug-ins — no edits to the dispatcher.

- `brep_build123d` → `geometry/source.py` (existing build123d/OCP → STEP/B-Rep).
- `implicit_sdf` → `geometry/sdf_source.py` (`converters/shape_ir_sdf.py`): emits
  fogleman/sdf source — sphere/box/rounded_box/capped_cylinder/capsule/ellipsoid,
  boolean union/subtract/intersect in IR source order, `organic_blend` → smooth
  `union(k=)`, translate. loft/sweep/revolve stay on build123d; unrepresentable
  kinds degrade to a bbox proxy.
- `manifold_mesh` → `geometry/manifold_source.py` (`converters/shape_ir_manifold.py`):
  emits manifold3d source — guaranteed-manifold mesh CSG with sphere/cube/cylinder/
  cone/ellipsoid, boolean `+`/`-`/`^`, native rotate+translate. No smooth blend
  (use implicit_sdf for that); `organic_blend` degrades to a plain union.
- `nurbs_brep` → `geometry/source.py` (`converters/shape_ir_nurbs.py`): NURBS
  B-Rep surfaces via the already-installed OCP kernel (no new dependency). A
  `nurbs_surface` node's `control_net` (2-D grid of points) is fitted with
  `GeomAPI_PointsToBSplineSurface` → a real OCC B-Rep face wrapped as build123d.
  `runtime=build123d`, so it **reuses the build123d pipeline**: exact STEP, GLB,
  and REAL per-patch B-Rep topology (each NURBS surface is its own pickable face,
  `surface_type=bspline`) — the analytic-face advantage over mesh backends. Other
  node kinds fall back to the build123d primitive compiler, so NURBS patches mix
  with primitives/lofts. (compas_occ was evaluated but is not on PyPI and would
  add a second, conflicting OCCT build alongside OCP; OCP-direct gives the same
  output with zero new deps.)

Workbench runtime (`aieng-ui/backend`):
- `aieng.convert` routes execution by the representation's **runtime**
  (`representation_runtime()`): build123d-runtime reps (`brep_build123d`,
  `nurbs_brep`) execute `geometry/source.py` through the build123d runner (STEP +
  analytic per-face topology); mesh backends
  share one path (`_mesh_feature_graph` / `_write_mesh_artifacts`): `implicit_sdf`
  → `_execute_sdf_code` (marching cubes); `manifold_mesh` → `_execute_manifold_code`
  (manifold3d CSG → trimesh). Both project a region-level mesh topology (one body,
  one region face — honest: not analytic B-Rep faces), rebuild object_registry, and
  stamp `provenance/conversion_manifest.json` `geometry_execution` with
  `backend={sdf|manifold}, geometry_kind=mesh`.
- Honest representation contract: STEP/B-Rep is exact + analytic-face pickable;
  SDF is real mesh evidence but region-level faces only. Both are derived products
  of the same Shape IR source, at different evidence levels.
Unified Shape IR verification:
- `converters/shape_ir_verification.py` audits the final package and writes
  `diagnostics/shape_ir_verification.json`. Per node: kind, representation_kind
  (brep / nurbs_brep / mesh / implicit_field / unknown), compiled?, source_ir_node
  mapped?, expected surface type. Per package: runtime/backend, executed/fallback,
  geometry_kind, lossiness (none/low/medium/high), cad_editable, capability_level
  (L0–L5), artifact existence, and honest integrity checks — notably
  `brep_topology_not_faked` (a mesh result must not present analytic B-Rep face
  types). `aieng.convert` runs it after conversion/execution and returns it as
  `shape_ir_verification`.

Object registry (node ↔ entities):
- `converters/shape_ir_object_registry.py` writes `registry/object_registry.json`
  (distinct from the generic `objects/object_registry.json`). Keyed by Shape IR
  node, each object carries: source JSON pointer, node type, runtime/backend,
  representation_kind, capability_level, lossiness, cad_editable, editable
  parameters, artifact refs, the resolved `topology_entities` /
  `viewer_selectable_ids` / `mesh_entities`, and a `verification_status_ref`.
  Node→entity linkage: `source_ir_node` (projected) → `name_match` (executed
  B-Rep, because the build123d label = node id is recorded as the body name) →
  `fused_mesh` (mesh backends fuse all nodes into one body) → `none`. Built on
  top of the verifier and run by `aieng.convert` after it. This is the bridge
  for viewer selection-by-node (PR3) and CAE result mapping (PR5).

Shape IR patch format + apply:
- `converters/shape_ir_patch.py`: `apply_shape_ir_patch(payload, patch, dry_run)`
  edits a Shape IR surgically instead of rewriting the whole JSON/source.
  Operations: set_parameter, move_control_point, add_node, remove_node,
  replace_node, connect, disconnect, change_representation_backend (each may
  carry `reason`; patch carries `author`/`tool`). **Atomic + validated**: ops run
  on a working copy, every op's outcome is recorded, and if any op fails or the
  result isn't valid Shape IR the original is left untouched (never silently
  overwrite). `build_patch_report` → `diagnostics/shape_ir_patch_report.json`
  (applied/failed ops, validation, provenance, dry-run flag).
- Workbench `aieng.apply_shape_ir_patch` (tool + `POST .../shape-ir-patch`,
  approval-gated): reads geometry/shape_ir.json, applies the patch, and on
  success commits it and calls `recompile_shape_ir_package` — which recompiles
  through runtime routing, regenerates artifacts, reconciles provenance, and
  refreshes verification + object registry. `dry_run` validates + reports only
  (no writes, no recompile).

Solver-neutral CAE result contract (CalculiX = first adapter):
- Three layers: solver runner → result normalizer/adapter → Shape IR mapper. See
  `docs/cae_result_contract.md`. The neutral artifacts are
  `analysis/computed_metrics.json` and `analysis/field_regions.json` (each with a
  `solver` provenance block + `result_type`); `converters/cae_result_contract.py`
  holds the CalculiX adapter (`normalize_calculix_*`, `write_normalized_cae_artifacts`)
  and the loader that prefers `analysis/*`, else normalizes legacy `results/*`.
- `map_cae_results(...)` consumes ONLY neutral computed_metrics + field_regions +
  topology_map + object_registry — no `.frd/.dat/.inp` or CalculiX naming (a
  source-token + behavioral test guard against leaks). Code_Aster / Elmer /
  FEniCSx / remote / mock solvers plug in by emitting the same neutral files; a
  `generic_fake` solver fixture proves the path is solver-neutral.

CAE result mapping (back to Shape IR):
- `converters/cae_result_map.py`: `map_cae_results(...)` correlates the neutral
  computed_metrics (scalar extrema per load case) + field_regions (stress/
  displacement regions) through `geometry/topology_map.json` and
  `registry/object_registry.json` to a `source_ir_node`. Each mapped result carries load_case_id, result_type
  (stress/displacement/deflection/strain), value+unit, affected topology
  entities, source_ir_node, mapping_method (bbox_contains/nearest_center),
  and confidence (high/medium/low). Region location → topology body (bbox
  containment, else nearest centre) → registry node; fused-mesh regions resolve
  to the body but honestly leave source_ir_node null (low confidence). Regions
  with no nearby geometry are reported in `unmapped_regions`. Output:
  `analysis/cae_result_map.json`.
- Workbench `cae.map_results` (tool + `GET .../cae-result-map`, read-only) writes
  it; `cae.extract_field_regions` refreshes it automatically. This map is the
  substrate for topology optimization (loads/hotspots tied to editable nodes) —
  optimization itself is not implemented yet.

- Runtime dependencies (workbench only, not aieng core), in the `aieng311` env:
  `implicit_sdf` needs `sdf` (github.com/fogleman/sdf) + `scikit-image`;
  `manifold_mesh` needs `manifold3d`:
  `pip install "git+https://github.com/fogleman/sdf.git" scikit-image manifold3d`.

---

## Phase 19: Recognition, writeback, and allowed-operation quality — COMPLETE (issues #45–#48)

All four sub-issues closed. Commits: `acace1a`, `6bdbed8`, `a20329d`.

### Phase 19 C1: Improve real CAD feature recognition quality — COMPLETE (issue #45)

Local issue doc: `issues/phase_19_c1_real_feature_recognition_quality.md`

Improved recognition fidelity on real extracted topology; added confidence/uncertainty
annotations per recognized feature; summary output now distinguishes recognized vs uncertain
features. Existing mock-based tests preserved green.

### Phase 19 C2: Expand guarded writeback breadth — COMPLETE (issue #46)

Local issue doc: `issues/phase_19_c2_writeback_breadth_expansion.md`

### Phase 19 C3: Add per-feature allowed-operation catalog — COMPLETE (issue #47)

Local issue doc: `issues/phase_19_c3_allowed_operation_catalog.md`

### Phase 19 C4: Add consolidated validation view — COMPLETE (issue #48)

Local issue doc: `issues/phase_19_c4_consolidated_validation_view.md`

---

## Phase 18: AI-facing reference and semantic coverage ergonomics — IN PROGRESS

**Goal:** Make `.aieng`'s already-stable record IDs easier for AI consumers, MCP clients, CLI users, and benchmarks to address, inspect, and verify. Borrow the addressing and review patterns of `earthtojake/text-to-cad` without importing its CAD authoring identity. See [text_to_cad_lessons.md](text_to_cad_lessons.md).

This phase is documentation + additive CLI and validator surface. It introduces no new source-of-truth data and no schema-breaking change.

### Phase 18A: Stable AI-facing reference notation — COMPLETE (issue #37)

Local issue doc: `issues/phase_18_reference_system.md`

Status: closed and delivered (commit `b828c22`).

**Delivered:**
1. `@aieng[<resource-path>#<id>]` reference notation defined. See [reference_notation.md](reference_notation.md).
2. Three read-only CLI verbs implemented:
   - `aieng ref-inspect <package.aieng> '<ref>' --json`
   - `aieng ref-list <package.aieng> --type feature|topology|interface|claim|evidence|trace|patch|constraint|protected_region|cae_mapping|completeness_item|task_spec_item|all`
   - `aieng ref-check <package.aieng>`
3. MCP additions: every record-returning tool exposes a canonical `ref` field; `resolve_ref` tool added.
4. Validator calls `ref-check` internally; exits non-zero on dangling or forbidden evidence targets.

**Boundary:** Pure naming convention over IDs that already exist. No edit handle, no query language, no CAD/CAE execution trigger.

### Phase 18B: Deferred optional viewer/review surface

**Status: Deferred — not in current Phase 18 implementation. Requires separate approval before any implementation work begins.**

A read-only viewer that visualises the *structured package* (features, claims, evidence, completeness) is conceptually compatible with `.aieng`'s boundary, but it is **not** planned for Phase 18 implementation. The combination of dependency risk, boundary risk (viewer-as-truth, snapshot-as-evidence), and the project's commitment to a lightweight local-first install means a viewer is not justified at this stage.

If a viewer is ever revisited, it must:
- be optional behind an extra (no default install impact),
- remain strictly read-only (no editing, no claim advancement),
- never render 3D geometry from STEP/mesh (semantic visualisation only),
- never produce artifacts admissible as validation evidence.

See `issues/phase_18_optional_viewer.md` for the deferred issue note.

### Phase 18C-min: General CAX semantic coverage benchmark refresh — INFRASTRUCTURE COMPLETE

Local issue doc: `issues/phase_18c_semantic_coverage_benchmark.md`

Status: infrastructure complete (commits `8fedd8e`, `a0bf738`, `d1f869b`); AI evaluation runs pending.

**Delivered:**
1. `plate_with_pattern` and `flange` coverage probes — each with deterministic definition YAML, generator script, rich + sparse `.aieng` packages, and full `benchmark_runs/<family>/` scaffold (README, instructions, questions, scoring sheet, expected observations, input index, condition inputs).
2. Five Phase 18C extension scoring categories added to `benchmarks/scoring_rubric.md`.
3. Four negative test fixtures (`build/negative_tests/`) with confirmed FAIL messages via `aieng validate` / `aieng ref-check`.
4. Cross-family leaderboard scaffold: `benchmark_runs/leaderboard.md`.
5. `aieng ref-check` passes on all generated benchmark packages.
6. No Git LFS used; all fixtures are script-generated from YAML definitions.

**Remaining:** AI evaluation runs against the condition_b_rich / condition_b_sparse inputs for each fixture; fill score tables in leaderboard and results records.

**Boundary:** Benchmarks measure understanding, honesty, evidence-correctness, and boundary-correctness. They do not measure whether a model can generate CAD geometry.

See `issues/phase_18c_semantic_coverage_benchmark.md` for the full issue record.

---

## Phase 17B: Mesh Handoff Completeness — COMPLETE (issue #36)

Local issue doc: `issues/phase_17b_mesh_handoff_completeness.md`

Status: closed and delivered.

**Goal:** Make the handoff from `.aieng` to Gmsh (mesh generation) well-defined and produce a structured handoff artifact that external Gmsh scripts can consume. After Gmsh runs, import mesh quality evidence back into the package.

`.aieng` does not run Gmsh. This phase is about producing a correct handoff artifact on the way out, and importing resulting mesh evidence on the way back in.

**Scope:**
1. Define a `mesh_handoff_contract.json` resource that tells an external Gmsh script: geometry source path, recommended meshing parameters (element size, element type), entity tags from topology, and target claim IDs that mesh evidence should support.
2. `aieng write-mesh-handoff` command writes `simulation/mesh_handoff_contract.json` from current package state.
3. Schema and validator checks for the handoff contract.
4. Document the expected round-trip: `write-mesh-handoff` → external Gmsh execution → `import-mesh-evidence`.
5. Add `mesh_handoff_contract` to `validation/completeness_report.json`.

**Acceptance criteria:**
- `aieng write-mesh-handoff <package.aieng>` writes a valid `simulation/mesh_handoff_contract.json`.
- Schema enforces no-mesher execution boundary (const guards, same pattern as existing schemas).
- Validator checks the handoff contract when present.
- Existing `import-mesh-evidence` tests continue to pass.

**Boundary:** `.aieng` produces the handoff artifact and imports evidence. It does not execute Gmsh, generate meshes, or modify geometry.

---

## Phase 17A: Stabilize Real STEP Geometry Extraction — COMPLETE (issue #35)

Local issue doc: `issues/phase_17a_real_step_stabilization.md`

Status: closed and delivered.

**Goal:** Verify and stabilize the OCC topology extraction pipeline on real engineering STEP files so that geometry-present packages carry real geometric semantics rather than mock data.

This is a file conversion quality gate. The LLM consuming a `.aieng` package must be able to trust that topology IDs, surface types, and feature candidates derive from the actual CAD file, not a deterministic mock.

**Scope:**
1. Run the full entry pipeline on at least one real engineering STEP file and record results.
2. Validate that `topology_map.json` contains correct face/edge counts and surface type distribution.
3. Verify feature recognition on real OCC topology (base plate, holes, hole patterns).
4. Add a `real_geometry_extraction` flag to `validation/completeness_report.json`.
5. Promote OCC as the recommended backend when CadQuery is installed (mock remains fallback).

**Acceptance criteria:**
- At least one real STEP integration test passes end-to-end with OCC backend.
- `completeness_report.json` distinguishes mock topology from real topology.
- Feature recognition on real OCC output produces at least the same candidate types as on mock.
- All existing mock-based tests continue to pass.

**Boundary:** `.aieng` does not modify geometry. This phase is about reading real geometry faithfully, not writing or correcting it.

---

## Phase 16E: Conversion Iron Rule Adoption — COMPLETE (docs)

**Goal:** Make conversion trust boundaries explicit for all future CAD/CAE adapters.

**Implemented:**
- Added a non-negotiable conversion rule to `docs/cad_cae_emitter_contract.md` and `docs/interop_standards_matrix.md`.
- Rule requires adapters to convert only known source information and explicitly mark unknown/unmappable content as `unknown` / `partial` / `missing` / `unsupported`.
- Rule explicitly forbids guessing unknown engineering facts to make packages appear complete.

**Boundary:** Documentation/policy update only. No CAD execution, mesh generation, solver execution, geometry modification, or claim automation changes are introduced.

---

## Phase 16D: Generated Model Mode Completeness Integration ? COMPLETE

**Goal:** Integrate definition-sourced package creation with the completeness/missingness policy and CAD/CAE-side layer positioning.

**Implemented:**
- `aieng define` now writes `validation/completeness_report.json` automatically.
- Completeness reports record `source_mode: definition` and mark missing STEP geometry/topology as explicit missingness rather than silent absence.
- Definition-sourced feature graphs are marked available as structured semantic definitions, while geometry references remain semantic-only until external CAD generation/import exists.
- `docs/cad_cae_emitter_contract.md` documents definition-sourced packages as a semantic-definition source, not a CAD geometry generator.

**Boundary:** No CAD generation, topology generation, mesh generation, solver execution, optimization, or manufacturing validation is introduced.

---

## Phase 16C: AGI Handoff Worked Example ? COMPLETE

**Goal:** Provide a concrete narrative walkthrough showing how `.aieng` supports an AI/AGI-assisted CAD/CAE handoff while keeping execution in external tools.

**Implemented:**
- `docs/agi_handoff_walkthrough.md` documents the flow from CAD/CAE emitter to agent read, task spec, patch proposal, external tool handoff, evidence writeback, claim update, tool trace, completeness refresh, summary, and validation.
- The walkthrough explicitly distinguishes `.aieng` as the semantic/evidence record from agent tools and external CAD/CAE execution.
- It includes safe/unsafe agent conclusions and a minimal handoff package checklist.
- It documents how `mechanical_agent` can later act as an L5 adapter without becoming the source of truth.

**Boundary:** Documentation only. No external CAD/CAE execution, plugin integration, geometry modification, mesh generation, solver execution, optimization, or manufacturing check is implemented.

---

## Phase 16B: CAD/CAE Emitter and Writeback Capability Contract ? COMPLETE

**Goal:** Define how external CAD/CAE tools, plugins, scripts, and workflow adapters can emit or write back `.aieng` resources without tying the format to one CAD kernel, CAE solver, or agent framework.

**Implemented:**
- `docs/cad_cae_emitter_contract.md` documents `.aieng` as the CAD/CAE-side semantic/evidence layer and agent tools as optional access interfaces.
- Defines best-effort conversion with explicit missingness as the emitter rule.
- Defines capability levels L0-L5: artifact reference, topology-aware CAD emitter, feature-aware CAD emitter, simulation-aware CAE emitter, evidence-aware writeback, and roundtrip-aware adapter.
- Defines forbidden emitter behavior and recommended minimal profiles.

**Boundary:** Documentation only. No FreeCAD/NX/Abaqus/Ansys plugin, CAD modification, mesh generation, solver execution, optimization, or manufacturing check is implemented.

---

## Phase 16A: Completeness and Missingness Report ? COMPLETE

**Goal:** Make best-effort CAD/CAE semantic conversion explicit. `.aieng` should convert whatever structured information is available and mark missing, partial, unknown, unsupported, conflicting, or not-applicable information instead of guessing.

**Implemented:**
- `schemas/completeness_report.schema.json` with const claim-policy guards for best-effort conversion, explicit missingness, no inferred missing information, unsupported-is-not-false semantics, and external-tool execution boundary.
- `aieng write-completeness-report <package.aieng> [--overwrite]` writes `validation/completeness_report.json` and updates `manifest.json`.
- Validator checks schema conformance, claim-policy flags, unique category names, resource references, and status/resource consistency.
- AI summaries include a "Completeness and missingness" section so agents can quickly see available, partial, missing, and unsupported CAD/CAE information.
- MCP `get_completeness_report` exposes the structured report when present and returns a not-found response when absent.

**Boundary:** This phase does not execute CAD/CAE software, generate meshes, run solvers, infer absent feature truth, or fabricate evidence. It only records package completeness state.

---

## Phase 15C: Cross-Resource Consistency Validator — COMPLETE

**Goal:** Add a cross-resource consistency layer to `aieng validate` that catches contradictions between the six Phase 14/15 ledgers: `validation/status.yaml`, `task/task_spec.yaml`, `task/external_tool_requirements.json`, `results/evidence_index.json`, claim proposals, and `provenance/tool_trace.json`.

**Implemented:**
- `_validate_cross_resource_consistency()` in `src/aieng/validate.py` — six inter-resource checks:
  1. If `validation/status.yaml` `solver_mesh_status.solver_execution == "done"` → solver/result_available claim must be pass with evidence (FAIL)
  2. If any solver/result_available claim is pass → `solver_mesh_status.solver_execution` should be "done" (WARN)
  3. `task_spec.forbidden_claims` vs passing claims in claim proposals (WARN: execution boundary violated; requires human review)
  4. `external_tool_requirements.forbidden_core_actions` contains `"run_solver"` + evidence item with `producer.kind == "aieng_core"` + `evidence_type == "solver_result"` (FAIL: core produced solver evidence in violation of contract)
  5. `tool_trace.claims_advanced` lists claim IDs that require human review for claim status updates (trace says claim advanced but proposal not yet reviewed)
  6. In-package artifact paths in evidence_index not present in ZIP (WARN: dangling reference)
- All six resources captured as data variables in `_validate_zip_members` and passed to the cross-resource validator
- 17 tests in `tests/test_cross_resource_consistency.py`, all passing

**Success criteria:**
- contradictions across ledgers (e.g., claim passed but execution not recorded, core produced solver evidence it forbids) surface as explicit FAIL or WARN
- each check has a test for the triggering case and for the non-triggering (safe) case
- no changes to MCP tools, CLI commands, or schemas
- no external tool execution introduced

**What not to implement:**
- auto-repairing ledger inconsistencies
- inferring execution status from tool output files
- calling external tools to re-run evidence collection

---

## Phase 15B: Provenance Tool Trace — COMPLETE

**Goal:** Add an append-only audit log of external tool invocations (`provenance/tool_trace.json`) so agents can verify what tools ran, what artifacts they produced, and which claims they advanced.

**Implemented (by project contributor):**
- `schemas/tool_trace.schema.json` — strict schema; `const` guards: `external_tools_execute: true`, `aieng_core_executes_external_tools: false`
- `src/aieng/provenance/tool_trace_writer.py` — `record_trace_package()`: append-only write to `provenance/tool_trace.json`; entries include `entry_id`, `timestamp_utc`, `tool` (id + role), `step` (name + inputs + outputs + exit_status), `artifacts_recorded`, `claims_advanced`, `notes`
- `aieng record-trace <package.aieng> --tool-id <id> --tool-role <role> --step-name <name> --exit-status <status> [options]`
- `aieng validate` checks `provenance/tool_trace.json` when present: schema, entry ID uniqueness, known tool roles, known exit statuses, cross-reference artifacts_recorded → evidence_index, cross-reference claims_advanced → claim proposals requiring human review
- MCP `get_tool_trace` returns `provenance/tool_trace.json` when present, `{"status": "not_found"}` when absent; registered in `create_server()`
- AI summary includes tool trace section when present
- 43 tests in `tests/test_tool_trace.py`, all passing

**Success criteria:**
- agents can see what external tools ran, what they produced, and what claims they advanced
- append-only semantics (no overwrite) preserve the full audit trail
- schema const guards enforce the execution boundary
- no CAD execution, mesh generation, solver execution, or geometry modification introduced

---

## Phase 15A: Evidence Writeback Commands — COMPLETE

**Goal:** Allow external tools and adapters to write evidence back into `results/evidence_index.json` after execution. Claim proposals are review artifacts requiring human review.

**Implemented (by project contributor):**
- `record_evidence_package()` in `src/aieng/results/evidence_writer.py` — append evidence items to `results/evidence_index.json`; guards against `aieng_core` producing solver/mesh/geometry evidence
- `aieng record-evidence <package.aieng> --evidence-type <type> --producer-kind <kind> --producer-tool <tool> --artifact-kind <kind> --artifact-path <path> --claim-support <id1,id2,...> [options]`
- Claim status updates require human review (update-claim CLI removed)
- 51 tests in `tests/test_evidence_ledger.py` cover both scaffold and writeback, all passing

**Success criteria:**
- external adapters can report evidence without knowing package internals
- guards prevent `aieng_core` from recording solver/mesh/geometry evidence it does not produce
- claim proposals are review artifacts requiring human review

---

## Phase 14D: Agent Handoff Benchmark Scaffold — COMPLETE (scaffold)

**Goal:** Create a benchmark scaffold that tests whether an AI/agent can correctly understand `.aieng` as a CAD/CAE-side semantic export and evidence package — specifically task intent, CAD/CAE execution boundaries, evidence requirements, claim honesty, unsupported-claim handling, and writeback/provenance expectations.

**Implemented:**
- `benchmarks/handoff/README.md` — benchmark purpose, scope, what is tested, what is excluded
- `benchmarks/handoff/questions.md` — 10 question groups (A–J) covering task intent, execution boundary, protected regions, evidence ledger, claim map, handoff plan, provenance/writeback, unsupported-claim refusal, package positioning, and integrity limits
- `benchmarks/handoff/scoring_rubric.md` — 8 categories scored 0/1/2; max score 16; category scores require resource-specific citations for a 2
- `benchmarks/handoff/expected_observations.md` — canonical expected behaviors: `.aieng` is CAD/CAE-side semantic export and evidence package; MCP is optional; `.aieng` does not modify geometry, generate meshes, run solvers; `unsupported` ≠ false; what agent must NOT say
- `benchmarks/handoff/input_index.md` — list of input files from a Phase 14C-prepared package, exclusion list, input size guidance
- `benchmarks/handoff/result_template.md` — structured template for recording benchmark runs
- `benchmarks/handoff/results.schema.json` — JSON schema with `const` guards: `benchmark_scenario: agent_handoff_v1`, `max_score: 16`; category name enum; 0/1/2 score enum
- `benchmarks/README.md` updated with handoff benchmark section
- 42 new tests in `tests/test_handoff_benchmark.py`

**Success criteria:**
- benchmark doc set describes the right question scope (task spec, handoff contract, evidence index, claim map)
- rubric requires resource-level citations for a score of 2
- expected observations explicitly state execution boundary and unsupported-claim semantics
- benchmark explicitly excludes MCP, RAG, solver execution, external CAD/CAE, and LLM API calls beyond package prompting
- no runtime behavior changed; no external tools called; no LLM API called

**What not to implement:**
- running the benchmark automatically or calling any AI API
- fabricating benchmark scores
- adding AI orchestration or tool execution logic

---

## Phase 14C: Evidence Ledger + Claim-Evidence Map — COMPLETE (scaffold)

**Goal:** Add a structured package resource that records what evidence from external tools is present (`results/evidence_index.json`). Claim proposals are review artifacts requiring human review.

**Implemented:**
- `schemas/evidence_index.schema.json` — strict schema with `const` guards enforcing the execution boundary (`external_tools_execute: true`, `aieng_core_generates_solver_evidence: false`, `aieng_core_generates_mesh_evidence: false`, `aieng_core_modifies_cad_geometry: false`)
- `schemas/claim_map.schema.json` — strict schema with matching `const` guards; claim proposals are review artifacts requiring human review
- `aieng write-evidence-scaffold <package.aieng> [--overwrite]`
- writes `results/evidence_index.json` seeded from current package state (task spec → pass claim; handoff contract → pass claim; solver/mesh/geometry claims → unsupported)
- `manifest.json` updated with `resources.results.evidence_index`
- `aieng validate` checks `results/evidence_index.json` when present: schema conformance, execution-boundary flags, unique evidence IDs, claim proposals require human review
- MCP `get_evidence_index` returns structured content when present, `{"status": "not_found"}` when absent; claim proposals require human review
- AI summary and README_FOR_AI include "Evidence ledger" and "Claim-evidence map" sections when present
- 51 tests, all passing

**Success criteria:**
- agents can read which evidence items exist before making engineering validity statements
- schema const constraints make it impossible for the writer to claim .aieng core generates solver/mesh evidence
- `unsupported` clearly means "no evidence attached yet" — not false or violated
- claim proposals are review artifacts requiring human review
- validators reject execution-boundary violations
- no CAD execution, meshing, solver execution, or geometry modification introduced

**What not to implement:**
- running external solvers or meshers to populate evidence
- importing solver result files
- auto-inferring claim status from arbitrary package contents

---

## Phase 14B: External Tool Handoff Contract — COMPLETE (scaffold)

**Goal:** Add a structured package resource that tells an agent which external CAD/CAE/runtime capabilities are required, what candidate tools may provide them, and what evidence must be written back after execution.

**Implemented:**
- `schemas/external_tool_requirements.schema.json` — strict schema with `const` guards enforcing the execution boundary (`external_tools_execute: true`, `aieng_core_executes_external_tools: false`, and five required-true policy flags)
- `aieng write-external-tool-requirements <package.aieng> [--handoff-id <id>] [--overwrite]`
- writes `task/external_tool_requirements.json` with `handoff_id`, optional `source_task_id` (from `task/task_spec.yaml` if present), `required_capabilities`, `candidate_tools`, `handoff_policy`, `writeback_requirements`, and `forbidden_core_actions`
- `manifest.json` updated with `resources.task.external_tool_requirements`
- `aieng validate` checks `task/external_tool_requirements.json` when present: schema conformance, execution-boundary policy flags, known tool roles and statuses, non-empty forbidden_core_actions, WARN if source_task_id references an absent task spec
- MCP `get_external_tool_requirements` returns structured content when present, `{"status": "not_found"}` when absent
- AI summary and README_FOR_AI include "External tool handoff contract" section when present
- 40 tests, all passing

**Success criteria:**
- agents can read which capabilities require external tool execution before instructing tool calls
- schema const constraints make it impossible for the writer to produce a document implying .aieng core executes CAD/CAE tools
- validators reject execution-boundary violations and flag orphaned source_task_id references
- no CAD execution, meshing, solver execution, or geometry modification introduced

**What not to implement:**
- calling FreeCAD, Gmsh, CalculiX, sim-cli, or mechanical_agent
- treating candidate tools as installed or available
- arbitrary STEP/B-rep editing

---

## Phase 14A-min: Task Specification Schema — COMPLETE (scaffold)

**Goal:** Add a structured task/work-order resource so agents can understand what task they are supposed to perform before proposing CAD/CAE actions. First step of the Agent Task Contract / External Tool Handoff layer.

**Implemented:**
- `schemas/task_spec.schema.json` — strict schema with `const: true` guards on all no-execution claim flags
- `aieng write-task-spec <package.aieng> --intent "<intent>" [--task-id <id>] [--mode <mode>] [--overwrite]`
- writes `task/task_spec.yaml` with `task_id`, `intent`, `mode`, `required_outputs`, `forbidden_claims`, `allowed_external_tools`, `evidence_required_before_acceptance`, and `claim_policy`
- `manifest.json` updated with `resources.task.task_spec`
- `aieng validate` checks `task/task_spec.yaml` when present: schema conformance, recognized mode, recognized required outputs, non-empty forbidden_claims, and claim_policy flags all true
- MCP `get_task_spec` returns the structured task spec content when present
- 37 tests, all passing

**Success criteria:**
- agents can read a structured task contract from the package before proposing changes
- forbidden_claims and claim_policy make explicit what the agent must not claim
- validators reject invalid modes, empty forbidden_claims, and false no-execution flags
- no CAD execution, meshing, solver execution, or geometry modification introduced

**What not to implement:**
- CAD execution or STEP modification
- mesh generation
- solver execution
- manufacturing feasibility validation
- LLM/RAG task assignment

---

## Phase 13A: Parameterized Feature Edit Handles — COMPLETE (scaffold)

**Goal:** Add guarded semantic edit handles to feature graph records so patches can update structured parameters without implying arbitrary CAD write-back.

**Implemented:**
- `graph/feature_graph.json` now carries guarded edit metadata such as `parameter_source`, `editability`, and `writeback_strategy`
- validator checks reject inconsistent combinations such as semantic-only sources claiming executable CAD regeneration
- mock/OCP-extracted parameters remain semantic-only by default

**Success criteria:**
- feature graph records can express semantic parameter provenance and editability
- docs and validation make clear that semantic edit handles are not arbitrary STEP/B-rep direct editing

**Risks:**
- overclaiming CAD write-back capability; mitigated by explicit guardrail validation and docs

**What not to implement:**
- arbitrary STEP direct editing
- arbitrary B-rep editing
- solver or mesh execution

---

## Phase 13B: Semantic Patch Execution — COMPLETE (scaffold)

**Goal:** Execute accepted patch proposals as semantic parameter updates with traceable execution records.

**Implemented:**
- `aieng apply-patch <package.aieng> --patch <patch_id>`
- supported `modify_parameter` operations update `graph/feature_graph.json`
- patch execution records are written back to patch files
- default execution mode is semantic parameter update only

**Success criteria:**
- accepted semantic parameter patches can be applied deterministically
- execution records clearly distinguish semantic-only updates from future executable regeneration paths

**Risks:**
- confusing semantic updates with geometry modification; mitigated by explicit no-geometry-modified claims for semantic-only sources

**What not to implement:**
- arbitrary STEP/B-rep editing
- solver or mesh execution
- engineering safety claims from patch application alone

---

## Phase 13C: Updated Deck Export — COMPLETE (scaffold)

**Goal:** Export an updated CalculiX deck scaffold reflecting the current semantic simulation state after semantic edits, for use or inspection by external CAE software.

**Implemented:**
- `aieng export-updated-deck <package.aieng> [--out <deck.inp>]`
- writes `simulation/updated_deck.inp`
- status reporting records updated deck export when validation status exists

**Success criteria:**
- updated deck scaffold reflects current `simulation/setup.yaml`
- docs and validation make clear the updated deck is still scaffold only

**Risks:**
- overstating CAE maturity; mitigated by explicit no mesh/no node sets/no element sets/no solver run wording and by keeping solver execution outside `.aieng`

**What not to implement:**
- mesh generation by `.aieng`
- node/element set generation
- solver execution by `.aieng`
- solver results import beyond explicit future evidence/reference resources

---

## Phase 12A: CAX Process-Chain Positioning Refinement — COMPLETE (docs only)

**Goal:** Clarify project positioning based on Phase 11E benchmark evidence: `.aieng` is a semantic task-understanding layer for AGI-assisted CAX process chains.

**Implemented:**
- Updated core docs (`README.md`, `docs/core_position.md`, `docs/architecture.md`, `docs/mvp_checkpoint.md`) to explicitly state non-replacement positioning
- Added explicit process-chain framing: deterministic CAX artifacts -> `.aieng` semantic layer -> AI/AGI proposal/configuration -> external CAD/CAE execution/validation -> evidence back into `.aieng`
- Recorded benchmark-aligned language: raw real STEP remained honest and partially useful; `.aieng` preserved honesty and improved CAX task usefulness
- Preserved conservative claim policy (no solver/mesh/safety/manufacturing validation claims without evidence)

**Success criteria:**
- Positioning text is consistent across core docs
- Docs explicitly state `.aieng` complements STEP/CAD/CAE artifacts rather than replacing them
- No CLI, schema, package-structure, or runtime behavior changes

**Risks:**
- Overstating replacement claims; mitigated by explicit non-replacement language
- Overstating validation maturity; mitigated by explicit no-solver/no-mesh/no-safety-claim policy

**What not to implement:**
- Any runtime feature changes
- Any schema or package structure changes
- Any new dependencies

---

## Phase 6A: Solver Deck Export Scaffold — COMPLETE

**Goal:** Produce a structured solver deck scaffold from the `.aieng` simulation setup, without executing a solver.

**Implemented:**
- `aieng export-calculix <package.aieng> --out <deck.inp>` CLI command
- Reads `simulation/setup.yaml` and generates a CalculiX `.inp` scaffold with material block (`*MATERIAL`, `*ELASTIC`, `*DENSITY`), boundary condition intent comments, load intent comments, validation targets, and protected-region notes
- Always writes `simulation/solver_deck.inp` inside the package and updates `manifest.json`
- `--out` also writes/copies to an external filesystem path
- Validator checks the solver deck when manifest references it: non-empty, contains scaffold warning, no false solver-completion claim
- 30 tests cover all specified behavior

**Not implemented (confirmed out of scope for Phase 6A):**
- Real meshing (no Gmsh)
- Real FEM node/element generation
- Active `*NODE`, `*ELEMENT`, `*NSET`, `*ELSET`, `*BOUNDARY`, `*CLOAD`, `*STEP` sections
- Solver execution or result parsing

---

## Phase 6B: Validation Status File — COMPLETE

**Goal:** Introduce a machine-readable validation state record so the package can carry explicit evidence of what has and has not been validated.

**Implemented:**
- `aieng update-validation-status <package.aieng> [--overwrite]` CLI command
- Generates `validation/status.yaml` with 8 structured sections: `package_validation`, `geometry_status`, `topology_status`, `feature_status`, `engineering_context_status`, `solver_mesh_status`, `patch_status`, and `claim_policy`
- Presence flags are derived from actual package contents (e.g. whether topology_map.json, feature_graph.json, patches are present)
- `claim_policy` section carries explicit `allowed_claims` and `forbidden_claims` lists so AI consumers know what the package can and cannot assert
- `aieng validate` checks the status file when manifest references it: valid YAML, all required sections present, claim policy non-empty, solver/mesh status makes no false claims, patch status correctly records no geometry modification
- Updates `manifest.json` with `resources.validation.status`
- 35 tests cover all specified behavior

**Not implemented (confirmed out of scope for Phase 6B):**
- Actual solver execution or mesh generation
- Automated population of evidence fields from solver results
- `validation/state.json` schema file (status is YAML, not JSON)

---

## Phase 7A: Geometry Backend Interface — COMPLETE

**Goal:** Introduce a clean pluggable backend abstraction so that topology extraction is selectable at call time, with a declared-but-unimplemented OCC placeholder.

**Implemented:**
- `src/aieng/geometry/backend.py` — `GeometryBackend` Protocol, `MockGeometryBackend`, `OCCGeometryBackend` (placeholder), `SUPPORTED_BACKENDS`, `get_backend()`
- `MockGeometryBackend` returns topology map with Phase 7A metadata fields: `extraction_backend`, `extraction_mode`, `real_step_parsing`, `source_geometry`
- `OCCGeometryBackend.extract_topology()` raises `NotImplementedError` with placeholder message
- `MockTopologyExtractor` and `OCCBasedTopologyExtractor` refactored to thin wrappers delegating to the backend
- `extract_topology_package()` gains `backend: str | None` parameter (resolution order: backend > extractor > MockGeometryBackend default)
- `aieng extract-topology --backend <name>` CLI flag (default: `mock`; OCC returns exit code 2 with error message)
- `aieng validate` soft-checks `metadata.extraction_backend` and `metadata.real_step_parsing` fields (WARN level)
- 27 new tests in `tests/test_topology_extractor.py`; all 258 tests pass

**Not implemented (Phase 7B):**
- Real STEP parsing via pythonocc-core or CadQuery
- `[geometry]` optional extra in `pyproject.toml`
- Real OCC topology extraction producing stable IDs
- CI matrix entry for geometry tests

---

## Phase 7A+: Geometry Backend Contract Documentation — COMPLETE

**Goal:** Define the contract that all future geometry backends must satisfy before Phase 7B real-backend work begins.

**Implemented:**
- `docs/geometry_backend_contract.md` — comprehensive contract document covering backend interface, required metadata fields, entity requirements, stable ID expectations, geometry reference rules, mock backend limitations, OCC future expectations, error handling rules, testing requirements, and what a backend must not do
- Lightweight contract existence tests added to `tests/test_docs_checkpoint.py`

**Rationale:** Defining the contract before implementing Phase 7B prevents the real backend from making architecture decisions that conflict with the existing pipeline's expectations.

---

## Phase 7B.1: Optional Dependency Detection — COMPLETE

**Goal:** Detect whether an optional OCC geometry runtime is installed and give a clear, actionable message, without adding a heavy dependency to the core install.

**Implemented:**
- `detect_occ_runtime()` in `src/aieng/geometry/backend.py` — uses `importlib.util.find_spec` (no actual import) to detect pythonocc-core (`OCC`) or OCP (`OCP`) availability; returns `{available, provider, message}` dict
- `OCCGeometryBackend.extract_topology()` updated: raises `NotImplementedError` with a clear install hint when no runtime is found; raises `NotImplementedError` citing Phase 7B.2 when a runtime is detected but STEP parsing is not yet implemented
- `aieng geometry-backends` new CLI command — lists mock (always available) and occ (runtime status) with human-readable output
- `pyproject.toml` gains `geometry = []` optional extra as a declared but unpopulated install target for Phase 7B.2
- 26 new tests in `tests/test_geometry_backend_detection.py`; all 291 tests pass

**Not implemented:**
- Real STEP parsing (Phase 7B.2)
- Actual packages added to the `geometry` extra — held until installation reliability is confirmed across platforms

---

## Phase 7B.2: Real OCC Geometry Backend — COMPLETE (experimental spike)

**Goal:** Replace the `OCCGeometryBackend` placeholder with a real implementation backed by OCP/CadQuery.

**Implemented:**
- `_extract_topology_ocp()` — lazy-import OCP STEP reader; writes bytes to a temp file, reads with `STEPControl_Reader`, traverses solids, faces, and edges with `TopExp_Explorer`
- `_build_entities_ocp()` — builds entity list with `id`, `type`, `bounding_box`, `area`, `surface_type`, `normal`/`radius`/`axis` for planes and cylinders; omits unavailable properties rather than inventing them
- `OCCGeometryBackend.extract_topology()` updated: no runtime → clear install hint; pythonocc-core detected → NotImplementedError (OCP required); OCP detected → calls `_extract_topology_ocp()`
- `detect_occ_runtime()` now checks OCP before pythonocc-core (Phase 7B.2 supports OCP)
- Deterministic IDs: `body_001`, `body_002`, ..., `face_001`, `face_002`, ..., `edge_001`, ...
- Metadata: `extraction_backend: "occ"`, `runtime_provider: "OCP"`, `extraction_mode: "parsed_from_step"`, `real_step_parsing: true`, `phase: "7B.2"`, `limitations: [...]`
- `aieng geometry-backends` updated to report OCP as experimental extraction available
- `aieng extract-topology --backend occ` success message is now backend-aware (`"PASS extracted occ topology"`)
- `tests/test_ocp_integration.py` — 23 integration tests guarded by `pytest.importorskip("OCP.STEPControl")`; skipped cleanly when OCP is absent
- `tests/test_geometry_backend_detection.py` — updated for new detection order and Phase 7B.2 error messages; 5 new tests added
- Schema unchanged; OCP metadata fields (`runtime_provider`, `phase`, `limitations`) pass schema validation via `additionalProperties: true`
- 296 core tests pass without OCP installed

**Confirmed out of scope for Phase 7B.2:**
- pythonocc-core real extraction (raises `NotImplementedError` with explanation)
- `[geometry]` extra populated (cadquery install reliability on Windows requires conda; documented as manual install only)
- CI matrix entry (not added until install reliability is confirmed cross-platform)
- Persistent naming across geometry edits
- Real CAD feature recognition from geometry queries (Phase 8)
- Meshing or solving

---

## Phase 7C: Optional OCP Topology Demo — COMPLETE

**Goal:** Make the experimental OCP real STEP extraction path user-discoverable with a convenience script, documentation, and tests — without changing the mock reference demo or adding dependencies.

**Implemented:**
- `docs/ocp_topology_demo.md` — full walkthrough: requirements, `aieng geometry-backends` check, four-step demo chain, field-by-field inspection guide, limitations table, comparison table vs mock reference demo
- `scripts/run_ocp_topology_demo.py` — convenience script; accepts a real STEP file positional argument; exits cleanly with skip message if OCP is unavailable or no file is provided; runs `import-step`, `extract-topology --backend occ`, `update-validation-status`, `validate` when OCP is available; output to `build/ocp_topology_demo.aieng`
- `tests/test_docs_checkpoint.py` — new doc/script existence and content tests (no OCP required)
- `README.md` — "Optional OCP topology demo" section with link to `docs/ocp_topology_demo.md`
- `docs/command_reference.md` — updated to show current Phase 7B.2 `geometry-backends` output for all three OCC states and link to `ocp_topology_demo.md`
- `docs/roadmap.md` — this entry

**Confirmed out of scope for Phase 7C:**
- Changes to the mock reference demo
- Any new dependencies
- Changes to the core pipeline or validation logic

---

## Phase 8A: Visual Index Scaffold — COMPLETE

**Goal:** Add a lightweight structured annotation scaffold that maps topology IDs and feature IDs to visual roles, without any rendering or geometry dependency.

**Implemented:**
- `src/aieng/visual/annotation_writer.py` — `build_visual_index_package()`; reads feature graph (required), topology map, protected regions, and simulation setup; builds four annotation layers
- `aieng build-visual-index <package.aieng> [--overwrite]` CLI command
- `visual/annotation_layers.json` — structured annotation layers: `features`, `protected_regions`, `simulation_targets`, `unknown_or_unclassified`; each item carries `feature_id`, `topology_refs`, `visual_role`, `status`, and layer-specific fields
- `schemas/visual_annotation_layers.schema.json` — JSON Schema for the annotation layers file
- `src/aieng/validate.py` — validates schema conformance, unique layer/item IDs, feature_id references against feature graph, and topology refs against topology map
- `src/aieng/ai/summary_writer.py` — reading order entry 12 and "Visual annotation scaffold" section in README_FOR_AI.md and ai/summary.md when present
- `src/aieng/validation/status_writer.py` — `visual_status` section in `validation/status.yaml`: `visual_index_present`, `annotation_layers_present`, `visual_rendering: not_generated`
- `src/aieng/package.py` — `visual/` added to `PACKAGE_DIRECTORIES`
- `docs/future_package_structure.md` — updated `visual/` section to describe Phase 8A implementation
- `tests/test_visual_annotation.py` — comprehensive tests covering happy path, all four layers, annotation content, overwrite behavior, error paths, validator integration, summary mentions, and validation status

**Confirmed out of scope for Phase 8A:**
- glTF, model.glb, or any 3D preview
- Rendering, images, thumbnails
- Three.js, Blender, mesh, CAD kernel, or visualization dependencies
- Changes to feature recognition logic

---

## Phase 8B: Visual Resource Manifest Scaffold — COMPLETE

**Goal:** Add a structured visual resource manifest so AI readers can distinguish annotation metadata from rendered/viewable assets and avoid false visual claims.

**Implemented:**
- `src/aieng/visual/model_manifest_writer.py` — `build_visual_manifest_package()`
- `aieng build-visual-manifest <package.aieng> [--overwrite]` CLI command
- `visual/model_manifest.json` scaffold with `visual_resources`, `rendering_status`, and `claim_policy`
- `schemas/visual_model_manifest.schema.json`
- `src/aieng/validate.py` checks for visual model manifest schema + semantics:
	- `status: present` requires the referenced path to exist
	- `rendering_status.rendered_geometry_present` must be `false`
	- `rendering_status.viewer_ready` must be `false`
	- forbidden visual claims must include rendered 3D/model.glb-not-present language
- `src/aieng/validation/status_writer.py` `visual_status` now records `visual_manifest_present`, `rendered_geometry_present`, and `visual_rendering: not_generated`
- `src/aieng/ai/summary_writer.py` now mentions `visual/model_manifest.json` when present and treats it as visual claim source-of-truth

**Confirmed out of scope for Phase 8B:**
- glTF/model export
- screenshots or feature snapshots
- rendering, viewer output, or visual UI
- geometry extraction changes
- visualization dependencies

**Success criteria achieved:**
- `build-visual-manifest` creates `visual/model_manifest.json`
- `manifest.json` references `resources.visual.model_manifest`
- validator checks pass for generated scaffold and fail on invalid `status: present` path claims
- visual rendering claims remain explicitly `not_generated`

---

## Phase 9A: Object Registry Scaffold — COMPLETE

**Goal:** Add a unified cross-resource object index so AI readers and deterministic tools can discover object IDs, definitions, and references quickly without replacing source-of-truth resources.

**Implemented:**
- `src/aieng/objects/registry_writer.py` — `build_object_registry_package()`
- `aieng build-object-registry <package.aieng> [--overwrite]` CLI command
- `objects/object_registry.json` scaffold with `objects`, `relationships`, and unresolved reference handling
- `schemas/object_registry.schema.json`
- `src/aieng/validate.py` checks for object registry schema + semantics:
	- object IDs must be unique
	- relationship endpoints must resolve to known or unresolved-reference objects
	- `defined_in` and `referenced_by` files must exist in package
	- notes must explicitly state registry is not source-of-truth
- `src/aieng/ai/summary_writer.py` now mentions object registry and clarifies index-only semantics
- `src/aieng/validation/status_writer.py` now records `object_registry_status.object_registry_present` and `registry_is_source_of_truth: false`

**Confirmed out of scope for Phase 9A:**
- persistent naming
- graph database storage
- assembly graph
- patch execution
- solver/mesher execution
- CAD/CAE/visualization/AI dependencies

**Success criteria achieved:**
- `build-object-registry` creates `objects/object_registry.json`
- `manifest.json` references `resources.objects.object_registry`
- validator checks pass for generated registry and fail for duplicate IDs or unknown relationship endpoints
- summaries and status output treat registry as generated index only

---

## Phase 9B: Interface Graph Scaffold — COMPLETE

**Goal:** Add a generated interface graph so AI readers and deterministic tools can identify interface-related features and preservation-relevant interface properties from existing structured context.

**Implemented:**
- `src/aieng/objects/interface_graph_writer.py` — `build_interface_graph_package()`
- `aieng build-interface-graph <package.aieng> [--overwrite]` CLI command
- `objects/interface_graph.json` scaffold with deterministic interface entries and cross-resource refs
- `schemas/interface_graph.schema.json`
- `src/aieng/validate.py` checks for interface graph schema + semantics:
	- interface IDs must be unique
	- `feature_ids` must resolve to feature graph IDs
	- topology refs must resolve when topology map exists
	- constraint refs, simulation refs, and visual refs must resolve when corresponding resources exist
	- protected interfaces must include forbidden operations or link to protected-region features
	- notes must explicitly state generated-index and not-source-of-truth policy
- `src/aieng/ai/summary_writer.py` now mentions interface graph and clarifies index-only semantics
- `src/aieng/validation/status_writer.py` now records `interface_graph_status.interface_graph_present` and `interface_graph_source_of_truth: false`
- Optional integration: `src/aieng/objects/registry_writer.py` includes interface objects when `objects/interface_graph.json` exists

**Confirmed out of scope for Phase 9B:**
- assembly graph
- mating constraints
- CAD interface inference beyond existing structured rules
- patch execution
- geometry modification
- mesher/solver execution
- CAD/CAE/visualization/AI dependencies

**Success criteria achieved:**
- `build-interface-graph` creates `objects/interface_graph.json`
- `manifest.json` references `resources.objects.interface_graph`
- validator checks pass for generated interface graph and fail for unresolved feature/topology refs
- summaries and status output treat interface graph as generated index only

---

## Phase 9C: AI Understanding Benchmark Execution

**Goal:** Run the benchmark scaffold defined in `benchmarks/` against a real general AI model and record scored results.

**What to implement:**
- Benchmark runner script that presents raw STEP input and `.aieng` package contents to a general AI using the API
- Structured scoring output in `benchmarks/results/`
- Comparison table: raw STEP score vs. `.aieng` score per question category
- At minimum: one scored run on the reference bracket scenario

**What not to implement yet:**
- Automated regression CI on every PR (too costly)
- RAG, MCP tools, skills, or plugins in the benchmark (explicitly excluded by benchmark design)
- Fine-tuned model comparisons

**Risks:**
- API costs for large topology/feature context
- Scoring subjectivity; rubric may need refinement after first run
- Results are evidence for the thesis, not a product feature

**Success criteria:**
- At least one complete scored benchmark run recorded in `benchmarks/results/`
- `.aieng` package input shows measurably higher scores than raw STEP input on structured-fact questions
- Results document which question categories show the largest gap

---

## Phase 10A: CAE Deck Import Scaffold — COMPLETE

**Goal:** Import a CAE deck into structured scaffold resources so AI readers and deterministic validators can inspect materials, boundary conditions, loads, and conservative mapping status before any solver execution.

**Implemented:**
- `aieng import-cae-deck <package.aieng> --deck <solver_deck.inp> --format calculix [--overwrite]`
- Writes `simulation/cae_imports/source_solver_deck.inp`
- Parses minimal cards into:
	- `simulation/cae_imports/parsed_materials.json`
	- `simulation/cae_imports/parsed_boundary_conditions.json`
	- `simulation/cae_imports/parsed_loads.json`
- Writes conservative `simulation/cae_mapping.json` with exact-name matching only; unmapped by default otherwise
- `manifest.json` simulation resources updated for all generated paths
- New schemas and validator checks:
	- parsed CAE materials, boundary conditions, loads, and mapping schema validation
	- semantic checks for unique parsed IDs/material names
	- mapped feature/interface ID resolution checks
	- explicit Phase 10A no-auto-mapping notes policy checks
- Summary and validation status integration:
	- summaries now mention imported CAE resources and that they are not solver evidence
	- `validation/status.yaml` now includes `cae_import_status` with not-run/result-not-imported fields
- Optional object registry integration for parsed CAE objects and CAE mapping objects

**Confirmed out of scope for Phase 10A:**
- solver execution
- result import
- mesh generation by `.aieng`
- automatic inference-based mapping
- CAD kernel changes

**Success criteria achieved:**
- Command creates deterministic CAE scaffold resources and updates manifest
- Validator checks pass for generated resources and fail on invalid CAE semantic tampering
- Status and summary outputs distinguish imported CAE scaffold from validated solver evidence

---

## Phase 11A + 11B: Topology Hardening + Attributed Adjacency Graph — COMPLETE

**Goal:** Improve real STEP topology adjacency evidence where available and add a deterministic attributed adjacency graph (`graph/aag.json`) generated from topology data.

**Implemented:**
- `aieng build-aag <package.aieng> [--overwrite]`
- `src/aieng/graph/aag.py` deterministic AAG builder
- `schemas/aag.schema.json`
- Validator support for optional `graph/aag.json` (warning when missing, schema + semantic checks when present)
- Cross-reference validation for AAG node face refs, arc node refs, and shared edge refs
- Feature recognition optional AAG consumption (adds conservative adjacency metadata when available)
- Topology hardening scaffold: optional `edge_ids` on faces and `face_ids` on edges when backend evidence is available
- Topology metadata now carries explicit adjacency evidence classification (`real`, `mock`, `inferred`, or `unavailable`)
- Summary/status integration marks AAG as generated index only and not source-of-truth

**Confirmed out of scope for Phase 11A/11B:**
- Mesh generation
- Solver execution
- Geometry modification or patch execution
- Treating AAG as authoritative feature truth

**Success criteria achieved:**
- `graph/aag.json` generated deterministically from topology map
- Missing AAG is warning-only
- Present AAG is schema-validated and cross-reference validated
- Mock backend remains lightweight and deterministic
- Optional OCP path remains guarded by dependency checks

---

## Phase 11C: Real STEP Demo + Real-Geometry Benchmark Scaffold — COMPLETE

**Goal:** Add an optional real-geometry scripted demo path and a manual benchmark scaffold that compares raw real STEP input (Condition A) vs generated `.aieng` semantic resources (Condition B).

**Implemented:**
- `scripts/generate_real_bracket_step.py` (optional CadQuery-based deterministic fixture generator for `examples/real_bracket.step`)
- `scripts/run_real_step_demo.py` full chain:
	- `import-step`
	- `extract-topology --backend occ`
	- `build-aag`
	- `recognize-features`
	- `apply-context` (with conservative fallback context generation when feature IDs differ)
	- `summarize`
	- `propose-patch`
	- `update-validation-status`
	- `validate`
- `examples/real_bracket_user_context.yaml` default context fixture for real demo runs
- `scripts/prepare_real_benchmark_pack.py` helper to copy Condition A and Condition B benchmark input sets into `benchmark_runs/real_bracket_001/input/`
- `benchmark_runs/real_bracket_001/` scaffold:
	- `README.md`
	- `instructions.md`
	- `raw_step_input_spec.md`
	- `aieng_input_index.md`
	- `questions.md`
	- `scoring_sheet.md`
	- `expected_observations.md`

**Confirmed out of scope for Phase 11C:**
- Any requirement that default install must include heavy CAD dependencies
- Automatic solver execution or results import
- Treating real topology extraction as validated engineering evidence by itself

**Success criteria achieved:**
- Optional real STEP fixture generation path is scripted
- Optional real STEP end-to-end package generation path is scripted
- Benchmark run scaffold explicitly includes Condition A vs Condition B comparison for real geometry
- AAG is included in the Condition B indexed input set

---

## Phase 10B: Explicit CAE Mapping — COMPLETE

**Goal:** Apply explicit user-provided mappings from imported CAE target names to `.aieng` feature/interface IDs without automatic inference.

**Implemented:**
- `aieng apply-cae-mapping <package.aieng> --mapping <mapping.yaml> [--overwrite]`
- Mapping YAML validation:
	- `mappings` list required
	- each mapping requires `cae_entity` and `maps_to` with `feature_id` and/or `interface_id`
	- `mapping_method` must be `user_provided`
	- `confidence` must be `high|medium|low`
- Reference validation during apply:
	- mapped `feature_id` must exist in `graph/feature_graph.json`
	- mapped `interface_id` must exist in `objects/interface_graph.json`
	- clear failures when required source graph is missing
- `simulation/cae_mapping.json` updates:
	- preserves unmentioned entries
	- writes explicit mapped entries with `mapping_method: user_provided`
	- tracks source mapping file metadata
	- deterministic overwrite behavior (`--overwrite` required for remapping already mapped entries)
- Validator enhancements for CAE mapping semantics:
	- status enum: `unmapped|mapped|partially_mapped|unresolved`
	- method enum: `not_inferred_phase_10a|user_provided`
	- confidence enum: `none|low|medium|high`
	- mapped entries cannot use `confidence: none`
	- unmapped entries require null/empty `maps_to`
	- mapped feature/interface references must resolve
- Summary/status updates:
	- summaries mention user-provided CAE mappings when present
	- `validation/status.yaml` reports mapped state and CAE mapping method
- Optional object registry relationship enrichment:
	- `cae_entity_to_feature`
	- `cae_entity_to_interface`

**Confirmed out of scope for Phase 10B:**
- automatic CAE-to-geometry inference
- solver execution
- result import
- mesh generation by `.aieng`
- geometry modification

**Success criteria achieved:**
- explicit mapping command exists and updates `simulation/cae_mapping.json`
- reference validation is enforced
- unmapped entries are preserved when not explicitly mapped
- validator and summaries distinguish user-provided mappings from automatic inference

---

## Phase 10: Generated Model Mode Exploration

**Goal:** Explore whether `.aieng` packages can be generated for models that have no pre-existing STEP file, using purely structured definition as the geometry source.

**What to implement:**
- A new `aieng model` or `aieng define` command that accepts a structured model definition (JSON or YAML) and produces an initial `.aieng` package with a defined feature graph but no imported STEP file
- Schema for structured model definition input
- Validator path for packages without a STEP source

**What not to implement yet:**
- Parametric geometry kernel from scratch
- Full constraint solver
- Export to STEP from a generated definition

**Risks:**
- Structured model definition scope can expand unboundedly
- Without a geometry kernel, generated packages cannot be used with downstream CAE tools
- May be better scoped as a separate project or tool

**Success criteria:**
- Can create a minimal `.aieng` package from a structured JSON definition with no STEP file
- Package passes `aieng validate` with appropriate warnings for missing geometry resources
- Feature graph and constraints are populated from the definition
- At least one example structured definition is included in `examples/`


## Phase 10C: CAE Mapping Enriches Interface Graph (completed scaffold)

- **Goal:** improve traceability from imported CAE deck targets to `.aieng` interface/feature IDs.
- **Implemented:** `build-interface-graph` reads explicit `simulation/cae_mapping.json` mappings and writes optional interface `cae_refs`.
- **Not implemented:** automatic CAE-to-feature inference, meshing, solving, result import, geometry modification, or patch execution.
- **Risk:** users may mistake mapping traceability for solver evidence; summaries/status must continue to state that no solver result exists.
- **Success criteria:** mapped entities such as `FIXED_HOLES` and `LOAD_FACE` appear on relevant interfaces with `mapping_method: user_provided` and validate successfully.


## Phase 15B: Provenance Tool Trace (completed)

- **Goal:** add `provenance/tool_trace.json` so external CAD/CAE tools, adapters, or agent runtimes can record what they did during handoff execution.
- **Implemented:** `schemas/tool_trace.schema.json`, `src/aieng/provenance/tool_trace_writer.py`, `aieng record-trace` CLI command, validator checks, summary writer integration.
- **Not implemented:** actual CAD modification, mesh generation, solver execution, post-processing, optimization, manufacturing check, or geometry modification. This phase only records externally executed steps.
- **Boundary:** `.aieng` does not execute external tools. `record-trace` records what the caller reports.
- **Success criteria:** `aieng record-trace` creates and appends `provenance/tool_trace.json`, validator checks claim_policy flags and cross-references, summary mentions trace entries and tools involved, all tests pass.
