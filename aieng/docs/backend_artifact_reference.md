# Backend Artifact Reference

This file lists the current backend/runtime artifacts that matter for geometry,
CAE, topology optimization, mesh reconstruction, and assembly workflows.

Not every package contains every artifact. Many paths are conditional on the
chosen geometry representation, whether CAE/topopt has run, and whether a given
reconstruction or assembly stage succeeded.

## Key Path Conventions

- Current provenance manifest path is `provenance/conversion_manifest.json`.
  The runtime records `geometry_execution`, `mesh_brep_reconstruction`, and
  related provenance blocks there. There is no separate
  `provenance/geometry_execution_manifest.json` today.
- Current Shape IR / CAE mapping path for the object registry is
  `registry/object_registry.json`.
- Older importers/tests may still reference `objects/object_registry.json`.
  Treat that as legacy. The current backend Shape IR registry and CAE result
  mapping path is `registry/object_registry.json`.
- `geometry/reconstructed.step` is always a derived mesh-reconstruction artifact.
  It never replaces `geometry/generated.step` or the original source geometry.

## Geometry, Provenance, And Runtime Outputs

| Path | Producer / stage | Purpose | Boundary |
| --- | --- | --- | --- |
| `geometry/shape_ir.json` | Shape IR conversion / topopt writeback | Source-of-truth geometry IR for runtime compilation | Source resource, not a rendered artifact |
| `geometry/source.py` | build123d Shape IR compile | Executable build123d source for B-Rep generation | Parametric runtime source, not proof of valid output by itself |
| `geometry/sdf_source.py` | SDF Shape IR compile | Executable implicit-mesh source | Mesh-oriented source, not analytic CAD |
| `geometry/manifold_source.py` | manifold Shape IR compile | Executable manifold mesh source | Mesh-oriented source, not analytic CAD |
| `geometry/generated.step` | successful B-Rep compile | Primary generated STEP for build123d / NURBS B-Rep paths | Current runtime-generated CAD artifact |
| `geometry/preview.glb` | preview generation | Viewer-ready preview asset | Visualization only |
| `geometry/preview.stl` | preview generation | Mesh preview / exchange asset | Visualization / downstream mesh preview only |
| `geometry/topology_map.json` | topology extraction / Shape IR compile / reconstruction success | Current active topology map used by downstream feature/CAE mapping | May represent analytic topology or reconstructed topology, depending on current geometry execution |
| `graph/feature_graph.json` | feature extraction / Shape IR compile heuristics | Named features, parameters, and semantic groupings | Semantic layer, not direct CAD truth |
| `graph/brep_graph.json` | B-Rep graph extraction when available | Face/edge/group graph used for pointering and interface reasoning | Read-only topology graph |
| `registry/object_registry.json` | Shape IR object registry | Cross-reference from source nodes to generated geometry/selectable entities | Derived mapping layer |
| `diagnostics/shape_ir_verification.json` | Shape IR verifier | Package/node-level verification of representation/execution linkage | Verification evidence, not certification |
| `provenance/conversion_manifest.json` | conversion/runtime writeback | Main provenance record, including `geometry_execution` and reconstruction blocks | Provenance ledger, not geometry by itself |

## Neutral CAE Result Contract

| Path | Producer / stage | Purpose | Boundary |
| --- | --- | --- | --- |
| `analysis/computed_metrics.json` | solver result normalization | Neutral scalar extrema / metric summaries per load case | Solver-neutral evidence, not solver execution itself |
| `analysis/field_regions.json` | solver result normalization | Neutral spatial hotspot/region summaries | Normalized evidence only |
| `analysis/cae_result_map.json` | CAE result mapper | Maps neutral CAE regions back to topology entities and source nodes | Unmapped/low-confidence regions remain explicit |

## Single-Part Topology Optimization

| Path | Producer / stage | Purpose | Boundary |
| --- | --- | --- | --- |
| `analysis/topology_optimization_problem.json` | topopt setup / derivation | Concrete optimizer input problem | Problem definition only |
| `analysis/topology_optimization.json` | topopt execution | Main optimizer result artifact | Optimization result, not CAD by itself |
| `analysis/topology_optimization_guidance_field.json` | result-guidance derivation | Optional guidance weights derived from prior CAE evidence | Advisory field, not safety proof |
| `diagnostics/smooth_mesh_reconstruction.json` | smooth-mesh writeback | Diagnostics describing smooth mesh proxy generation/fallback | Mesh proxy diagnostics only |

## Mesh Reconstruction Ladder

| Path | Producer / stage | Purpose | Boundary |
| --- | --- | --- | --- |
| `graph/mesh_region_graph.json` | mesh region segmentation | Region graph over a mesh/smooth-mesh body | Diagnostic mesh evidence |
| `diagnostics/mesh_region_segmentation.json` | mesh region segmentation | Segmentation diagnostics and degraded paths | Diagnostic only |
| `graph/mesh_surface_fit.json` | analytic fit stage | Best-fit plane/cylinder evidence over segmented regions | Fit evidence, not CAD |
| `diagnostics/mesh_surface_fitting.json` | analytic fit stage | Fit quality / failures / skipped regions | Diagnostic only |
| `graph/mesh_freeform_surface_fit.json` | freeform fit stage v0 | Approximate BSpline-like surface evidence for freeform mesh regions | Evidence-only; not B-Rep, not STEP, not CAD-editable |
| `diagnostics/mesh_freeform_surface_fitting.json` | freeform fit stage v0 | Freeform fitting diagnostics: counts, skipped reasons, confidence distribution | Diagnostic only |
| `diagnostics/mesh_freeform_reconstruction_readiness.json` | freeform readiness stage v0 | Quality/readiness scoring and recommended next actions per freeform surface | Advisory/readiness-only; does not generate B-Rep faces or export STEP |
| `diagnostics/mesh_reconstruction_readiness.json` | readiness analysis | Honest readiness classification for future reconstruction | Does not reconstruct geometry |
| `graph/mesh_reconstruction_plan.json` | readiness analysis | Per-region readiness/recommended-next-action plan | Planning evidence only |
| `graph/mesh_brep_reconstruction_plan.json` | partial B-Rep planning | Conservative reconstruction plan for analytic regions | Planning evidence only |
| `geometry/partial_brep_surfaces.json` | partial B-Rep reconstruction | Candidate analytic surfaces before face generation | Intermediate candidate artifact |
| `diagnostics/partial_brep_reconstruction.json` | partial B-Rep reconstruction | Reconstruction diagnostics and limitations | Diagnostic only |
| `geometry/partial_brep_faces.json` | OCC face generation | Validated candidate faces generated from analytic surface candidates | Candidate faces only, not a watertight solid |
| `diagnostics/partial_brep_face_generation.json` | OCC face generation | Face-generation diagnostics | Diagnostic only |
| `graph/mesh_brep_stitching_plan.json` | stitching planner | Face adjacency / stitchability plan | Planning evidence only |
| `diagnostics/mesh_brep_stitching_readiness.json` | stitching planner | Readiness blockers before sewing | Diagnostic only |
| `diagnostics/mesh_brep_sewing.json` | OCC sewing / solidification | Sewing and solidification outcome details | Diagnostic unless a validated solid is exported |
| `diagnostics/mesh_brep_step_export.json` | STEP export gate | Records whether reconstructed STEP export was allowed | Export blocked unless a closed OCC-valid solid exists |
| `diagnostics/mesh_brep_roundtrip_verification.json` | roundtrip verification | Verifies exported reconstructed STEP could be re-read/validated | Verification evidence only |
| `geometry/reconstructed.step` | validated reconstruction export | Derived STEP from successful mesh reconstruction | Mesh-derived/lossy; not production CAD certified |
| `geometry/reconstructed_topology_map.json` | successful reconstruction export | Topology extracted from the reconstructed STEP | Derived topology for the reconstructed artifact |
| `geometry/mesh_topology_map.json` | reconstruction success/failure bookkeeping | Preserved original mesh topology when reconstructed topology becomes active | Original mesh evidence is retained rather than overwritten |

## Assembly CAE And Assembly-Aware Optimization

| Path | Producer / stage | Purpose | Boundary |
| --- | --- | --- | --- |
| `assembly/assembly_ir.json` | assembly authoring/import | Source assembly structure | Source resource |
| `assembly/part_registry.json` | assembly processing | Registry of parts/roles/material/placement data | Derived assembly index |
| `assembly/interface_resolution.json` | assembly processing | Interface geometry resolved into world-space/package-space references | Best-effort resolution only |
| `assembly/connection_graph.json` | assembly processing | Simplified assembly connectivity graph | Proxy/semantic graph |
| `diagnostics/assembly_validation.json` | assembly processing | Structural/schema validation of assembly IR | Validation evidence |
| `diagnostics/assembly_connection_geometry.json` | assembly processing | Geometry plausibility diagnostics for assembly connections | Proxy geometry reasoning only |
| `simulation/assembly_cae_model.json` | assembly CAE drafting | Simplified solver-neutral proxy CAE model | Proxy-only assembly CAE |
| `diagnostics/assembly_cae_model_diagnostics.json` | assembly CAE drafting | Diagnostics for proxy CAE model generation | Diagnostic only |
| `simulation/assembly_calculix.inp` | assembly deck generation | Optional CalculiX deck for proxy assembly model | Only present when prerequisites are satisfied |
| `diagnostics/assembly_solver_deck_generation.json` | assembly deck generation | Records whether deck generation ran or was skipped | Diagnostic only |
| `diagnostics/assembly_solver_execution.json` | assembly execution | Records proxy solver execution outcome or skip | Diagnostic only |
| `analysis/assembly_computed_metrics.json` | assembly result normalization | Neutral scalar results for the proxy assembly model | Proxy-result evidence |
| `analysis/assembly_field_regions.json` | assembly result normalization | Neutral field-region summaries for the proxy assembly model | Proxy-result evidence |
| `analysis/assembly_result_map.json` | assembly result mapping | Maps proxy result regions back to assembly entities/interfaces/source nodes | Proxy mapping only |
| `diagnostics/assembly_result_mapping.json` | assembly result mapping | Diagnostics for assembly result mapping confidence and gaps | Diagnostic only |
| `analysis/assembly_topology_optimization_problem.json` | assembly topopt derivation | Selected design-part optimization problem derived from assembly data | Setup artifact only |
| `diagnostics/assembly_topopt_derivation.json` | assembly topopt derivation | Honest derivation diagnostics, including `needs_user_input` paths | Diagnostic only |
| `analysis/topology_optimization_problem.json` | assembly topopt bridge | Standard single-part topopt problem emitted when derivation is safe enough | Conditional bridge artifact |
| `analysis/assembly_topology_optimization.json` | assembly topopt execution | Main assembly-aware optimization execution/result record | Explicit selected-part-only run |
| `diagnostics/assembly_topopt_execution.json` | assembly topopt execution | Execution diagnostics and provenance for the assembly-aware run | Diagnostic only |
| `diagnostics/assembly_post_optimization_verification.json` | post-opt verification | Checks selected-part-only writeback, preserve-region traceability, and proxy-honesty fields | Verification, not physical certification |
| `analysis/assembly_optimization_summary.json` | post-opt verification | Condensed summary of verification/writeback scope outcomes | Summary artifact |
| `analysis/assembly_design_recommendations.json` | recommendation postprocess | Rule-based advisory recommendations after assembly-aware optimization | Advisory only |
| `diagnostics/assembly_postprocess_report.json` | recommendation postprocess | Structured status report for recommendation generation | Diagnostic only |
| `analysis/assembly_next_actions.json` | recommendation postprocess | Machine-readable next-step actions for the user/agent | Advisory only |
| `parts/<selected_part_id>/analysis/topology_optimization.json` | selected-part writeback | Per-part copied optimization result under the chosen design part | Selected-part derived artifact |
| `parts/<selected_part_id>/geometry/optimized_shape_ir.json` | selected-part writeback | Conditional writeback geometry for the chosen design part | Written only when selected-part writeback is safe |

## Agent-Guided Design Studies

| Path | Producer / stage | Purpose | Boundary |
| --- | --- | --- | --- |
| `analysis/design_study_problem.json` | design-study authoring | Design variables, objective, constraints, and settings for a parameter study | Problem contract only |
| `patches/design_candidates/<candidate_id>.json` | candidate proposal | Proposed parameter changes against the problem variables | Candidate proposal; not applied by validation |
| `diagnostics/design_study_problem_diagnostics.json` | design-study validation | Problem contract validation findings | Diagnostics only |
| `diagnostics/design_study_candidate_validation.json` | design-study validation | Per-candidate validation/normalization results | Diagnostics only |
| `analysis/design_study_iterations.json` | candidate execution | Deterministic log of explicit candidate runs | Baseline modification remains false |
| `diagnostics/design_study_report.json` | candidate execution | Iteration/recommendation summary | Summary only |
| `candidates/<candidate_id>/patch.json` | candidate execution | Candidate patch copied into its derived workspace | Candidate-local copy |
| `candidates/<candidate_id>/geometry/shape_ir.json` | candidate execution | Derived Shape IR after applying the patch to a deep copy | Candidate-only geometry; not package baseline |
| `candidates/<candidate_id>/provenance/candidate.json` | candidate execution | Provenance for patch application and baseline reference | Provenance only |
| `candidates/<candidate_id>/analysis/evaluation.json` | candidate evaluation | Normalized candidate metrics, units/source paths, confidence, and constraint evidence | Reads local evidence only; no solver/recompile/promotion |
| `candidates/<candidate_id>/diagnostics/evaluation_report.json` | candidate evaluation | Missingness and constraint-evaluation diagnostics | Diagnostic only |
| `analysis/design_study_candidate_hints.json` | candidate hint generation | Advisory variable-scoped parameter hints with evidence links, direction/magnitude, priority, confidence, and safety notes | Does not create candidate patches or mutate geometry |
| `diagnostics/design_study_candidate_hints_report.json` | candidate hint generation | Input evidence presence/missingness, rules triggered, hint counts, confidence distribution, warnings/errors | Diagnostic only |
| `analysis/design_study_candidate_ranking.json` | candidate ranking | Advisory feasibility/score/order for executed candidates | Ranking only; no search or auto-accept |
| `diagnostics/design_study_scoring_report.json` | candidate ranking | Ranking diagnostics, missing metrics, confidence distribution | Diagnostic only |
| `analysis/design_study_acceptance.json` | explicit acceptance | Records an accepted/rejected derived candidate decision | Does not promote into baseline geometry |
| `diagnostics/design_study_acceptance_report.json` | explicit acceptance | Acceptance eligibility and artifact checks | Diagnostic only |
| `accepted/<candidate_id>/geometry/shape_ir.json` | explicit acceptance | Derived Shape IR copied into accepted workspace | Accepted artifact only; not production approval |
| `candidates/<candidate_id>/analysis/cae_evaluation_request.json` | candidate CAE evaluation request | Explicit request artifact recording mode, permissions, and source references | Request-only; does not auto-execute or auto-accept |
| `candidates/<candidate_id>/diagnostics/cae_evaluation_request.json` | candidate CAE evaluation request | Diagnostics covering setup derivation, deck/solver/normalization/ranking status | Diagnostic only |
| `candidates/<candidate_id>/simulation/setup.yaml` | candidate CAE evaluation request | Candidate-local CAE setup derived from baseline (copied + warned) | May need re-verification if candidate geometry changed topology refs |
| `candidates/<candidate_id>/simulation/cae_mapping.json` | candidate CAE evaluation request | Candidate-local CAE mapping derived from baseline | May need re-verification if candidate geometry changed topology refs |

## Honesty Rules Worth Repeating

- `smooth_mesh_proxy` and mesh-fit artifacts are not B-Rep.
- Plane/cylinder fits, candidate faces, and stitching plans are evidence toward
  reconstruction, not CAD-editable geometry.
- `geometry/reconstructed.step` is only written for validated closed OCC solids.
- Assembly CAE artifacts remain simplified proxies; no current artifact implies
  real contact, friction, or bolt preload modeling.
- Assembly recommendations are advisory. They do not rerun topology optimization,
  mutate geometry, or certify safety/manufacturability.
- Design-study evaluation/ranking is advisory and candidate-local. It never runs
  a solver, recompiles geometry, searches candidates, or promotes a baseline.
- Design-study hints are advisory decision support. They never create candidate
  patches, execute candidates, run optimization/CAE, rank/accept candidates, or
  mutate baseline geometry.
