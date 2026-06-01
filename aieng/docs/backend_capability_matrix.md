# Backend Capability Matrix

This document is the current capability snapshot for the reference backend/runtime
used in this workspace. It covers the implemented CAD/CAE/topology-optimization/
mesh-reconstruction/assembly pipeline spread across `aieng/src/aieng/converters/`
and `aieng-ui/backend/`.

Scope note: this is not a claim that the `aieng` core CLI alone performs every
operation below. Some items are shared converter/runtime capabilities surfaced by
the reference workbench. When in doubt, treat this file as the authoritative
"what exists today, with what limits" snapshot.

## Status Legend

| Status | Meaning |
| --- | --- |
| `stable` | Implemented, exercised by focused tests, and intended as a current supported path |
| `experimental` | Implemented but still bounded, reference-grade, or intentionally conservative |
| `diagnostic-only` | Produces analysis/diagnostics/evidence, not editable CAD or direct execution claims |
| `proxy-only` | Uses simplified proxy physics/modeling rather than full production behavior |
| `future` | Not implemented; no current capability claim |

## Geometry Generation And Shape IR

| Capability | Status | Primary artifacts | STEP output | CAD editability | Current boundary |
| --- | --- | --- | --- | --- | --- |
| Shape IR -> build123d B-Rep compile (`brep_build123d`) | `stable` | `geometry/shape_ir.json`, `geometry/source.py`, `geometry/generated.step`, `geometry/topology_map.json`, `graph/feature_graph.json`, `diagnostics/shape_ir_verification.json`, `registry/object_registry.json` | Yes | B-Rep | Default reference runtime path for pickable geometry, feature extraction, and downstream CAE/topopt linkage |
| Shape IR -> OCP NURBS B-Rep compile (`nurbs_brep`) | `experimental` | `geometry/shape_ir.json`, `geometry/generated.step`, `geometry/topology_map.json`, `diagnostics/shape_ir_verification.json` | Yes | B-Rep | Exact per-patch bspline faces are supported, but this is not a general "editable freeform CAD from anything" claim |
| Shape IR -> implicit SDF mesh (`implicit_sdf`) | `experimental` | `geometry/shape_ir.json`, `geometry/sdf_source.py`, mesh/preview artifacts, verification/object-registry outputs where available | No | mesh-only | Produces mesh-style runtime geometry; not analytic CAD |
| Shape IR -> manifold mesh (`manifold_mesh`) | `experimental` | `geometry/shape_ir.json`, `geometry/manifold_source.py`, mesh/preview artifacts, verification/object-registry outputs where available | No | mesh-only | Produces fused mesh geometry with region-level/topology evidence, not analytic CAD |
| Shape IR verification and node/object cross-reference | `stable` | `diagnostics/shape_ir_verification.json`, `registry/object_registry.json` | Not applicable | Not applicable | Verification is evidence about generated geometry linkage; it is not manufacturing or certification approval |

## CAE Result Contracts

| Capability | Status | Primary artifacts | STEP output | CAD editability | Current boundary |
| --- | --- | --- | --- | --- | --- |
| Solver-neutral CAE normalization | `stable` | `analysis/computed_metrics.json`, `analysis/field_regions.json` | Not applicable | Not applicable | Normalizes solver output into a neutral contract; does not prove solver correctness by itself |
| CAE result mapping back to geometry/source nodes | `stable` | `analysis/cae_result_map.json` plus topology/object-registry inputs | Not applicable | Not applicable | Unmapped or weakly mapped regions stay explicit; no silent geometric certainty is invented |
| CalculiX-backed reference runtime loop | `stable` | generated deck/result artifacts plus normalized `analysis/*` outputs in the workbench runtime | Not applicable | Not applicable | Real solver execution exists in the reference runtime, but post-processing remains evidence-oriented rather than certification-oriented |

## Topology Optimization

| Capability | Status | Primary artifacts | STEP output | CAD editability | Current boundary |
| --- | --- | --- | --- | --- | --- |
| 2D SIMP topology optimization | `stable` | `analysis/topology_optimization_problem.json`, `analysis/topology_optimization.json` | No direct STEP | Not applicable | Current mainline optimizer path |
| Result-guided optimization field | `stable` | `analysis/topology_optimization_guidance_field.json` | No | Not applicable | Guidance is advisory weighting from prior CAE evidence, not a proof that the new design is safe |
| 2D contour writeback (`extruded_region` / `density_contour`) | `stable` | updated `geometry/shape_ir.json`, `diagnostics/shape_ir_verification.json`, `registry/object_registry.json`, derived geometry artifacts | Yes | B-Rep | Best current path for CAD-friendly optimized geometry when the design is fundamentally 2D/extrudable |
| Voxel writeback (`density_voxels`) | `stable` | updated `geometry/shape_ir.json`, verification/object-registry outputs | Conditional | candidate-only | Honest discrete proxy of the thresholded field; useful for review and some downstream compilation paths, but not smooth CAD |
| 3D SIMP structured-voxel optimization | `experimental` | `analysis/topology_optimization.json` with `dimension=3d` and honest capability block | No direct STEP | Not applicable | Reference implementation only; `production_ready:false` remains the intended claim |
| 3D smooth mesh writeback (`smooth_mesh_proxy`) | `experimental` | updated `geometry/shape_ir.json`, `diagnostics/smooth_mesh_reconstruction.json` | No | mesh-only | Mesh proxy is review/output geometry, not reconstructed B-Rep; STEP only exists after a separate validated reconstruction ladder |

## Mesh-To-CAD Reconstruction

| Capability | Status | Primary artifacts | STEP output | CAD editability | Current boundary |
| --- | --- | --- | --- | --- | --- |
| Mesh region segmentation + analytic candidate detection | `stable` | `graph/mesh_region_graph.json`, `diagnostics/mesh_region_segmentation.json` | No | Not applicable | Diagnostic analysis of mesh evidence only |
| Plane/cylinder fitting over segmented mesh regions | `stable` | `graph/mesh_surface_fit.json`, `diagnostics/mesh_surface_fitting.json` | No | Not applicable | Fit evidence is not CAD; freeform/noisy areas remain explicit |
| Reconstruction readiness scoring | `stable` | `diagnostics/mesh_reconstruction_readiness.json`, `graph/mesh_reconstruction_plan.json` | No | Not applicable | Readiness is an evidence report only; it does not reconstruct geometry |
| Partial B-Rep surface candidate generation | `experimental` | `graph/mesh_brep_reconstruction_plan.json`, `geometry/partial_brep_surfaces.json`, `diagnostics/partial_brep_reconstruction.json` | No | candidate-only | Plane/cylinder surface candidates are intermediate reconstruction evidence |
| OCC face generation from analytic candidates | `experimental` | `geometry/partial_brep_faces.json`, `diagnostics/partial_brep_face_generation.json` | No | candidate-only | Validated candidate faces exist in memory/JSON evidence only; they are not yet a closed solid |
| Stitching planning and readiness | `experimental` | `graph/mesh_brep_stitching_plan.json`, `diagnostics/mesh_brep_stitching_readiness.json` | No | candidate-only | Planning/readiness never implies sewing/export success |
| OCC sewing / solidification diagnostics | `experimental` | `diagnostics/mesh_brep_sewing.json`, `diagnostics/mesh_brep_step_export.json`, `diagnostics/mesh_brep_roundtrip_verification.json` | Conditional | candidate-only until exported | Diagnostics are always written; STEP export is blocked unless a closed OCC-valid solid exists |
| Reconstructed STEP export | `experimental` | `geometry/reconstructed.step`, `geometry/reconstructed_topology_map.json`, preserved `geometry/mesh_topology_map.json`, updated `provenance/conversion_manifest.json` | Conditional validated-only | B-Rep | Reconstructed STEP is mesh-derived/lossy, never overwrites source/generated STEP, and is not production CAD certified |

## Assembly And Assembly-Aware Optimization

| Capability | Status | Primary artifacts | STEP output | CAD editability | Current boundary |
| --- | --- | --- | --- | --- | --- |
| Assembly IR processing + interface/connection resolution | `stable` | `assembly/assembly_ir.json`, `assembly/part_registry.json`, `assembly/interface_resolution.json`, `assembly/connection_graph.json`, `diagnostics/assembly_validation.json`, `diagnostics/assembly_connection_geometry.json` | No | Not applicable | Geometric plausibility/resolution is explicit; unresolved interfaces stay unresolved |
| Assembly CAE model drafting | `proxy-only` | `simulation/assembly_cae_model.json`, `diagnostics/assembly_cae_model_diagnostics.json` | No | Not applicable | Simplified connection proxies only; not nonlinear assembly contact |
| Optional assembly CalculiX deck generation / execution diagnostics | `proxy-only` | `simulation/assembly_calculix.inp`, `diagnostics/assembly_solver_deck_generation.json`, `diagnostics/assembly_solver_execution.json` | No | Not applicable | Deck generation and solver execution are best-effort/conditional on prerequisites |
| Assembly result normalization and mapping | `proxy-only` | `analysis/assembly_computed_metrics.json`, `analysis/assembly_field_regions.json`, `analysis/assembly_result_map.json`, `diagnostics/assembly_result_mapping.json` | No | Not applicable | Results remain tied to the simplified proxy model |
| Assembly-aware topology optimization setup | `experimental` | `analysis/assembly_topology_optimization_problem.json`, `diagnostics/assembly_topopt_derivation.json`, conditional `analysis/topology_optimization_problem.json` | No | Not applicable | Explicit selected design-part only; may return `needs_user_input` instead of guessing unsafe mappings |
| Assembly-aware topology optimization execution | `experimental` | `analysis/assembly_topology_optimization.json`, `diagnostics/assembly_topopt_execution.json`, selected-part `parts/<selected_part_id>/analysis/topology_optimization.json` and conditional `parts/<selected_part_id>/geometry/optimized_shape_ir.json` | Conditional on writeback path | selected-part only | Does not overwrite package-level geometry or frozen/reference parts |
| Post-optimization verification | `stable` | `diagnostics/assembly_post_optimization_verification.json`, `analysis/assembly_optimization_summary.json` | No | Not applicable | Verifies scope/preserve traceability/proxy honesty; does not certify physical equivalence |
| Recommendation and next-action postprocess | `diagnostic-only` | `analysis/assembly_design_recommendations.json`, `diagnostics/assembly_postprocess_report.json`, `analysis/assembly_next_actions.json` | No | Not applicable | Advisory only; never reruns optimization or mutates geometry automatically |

## Not Currently Claimed

| Capability | Status | Reason no stronger claim is made |
| --- | --- | --- |
| Nonlinear contact / friction modeling in assembly CAE | `future` | Current assembly CAE remains simplified proxy modeling |
| Bolt preload modeling | `future` | Explicitly not modeled in current assembly CAE/topopt outputs |
| Simultaneous multi-part assembly optimization | `future` | Current execution targets one selected design part only |
| General freeform mesh -> production NURBS/B-Rep reconstruction | `future` | Current reconstruction ladder is conservative and analytic-first (plane/cylinder oriented) |
| Automatic recommendation execution | `future` | Recommendations are intentionally advisory only |
| Manufacturing signoff / production certification | `future` | No current artifact or validation layer claims this |

## Focused Validation Coverage

The current snapshot is grounded in focused suites that cover the slices above:

- `aieng/tests/test_topology_optimization.py`
- `aieng/tests/test_topopt_result_guidance.py`
- `aieng/tests/test_mesh_reconstruction_readiness.py`
- `aieng/tests/test_mesh_brep_reconstruction.py`
- `aieng/tests/test_mesh_brep_stitching.py`
- `aieng/tests/test_mesh_brep_face_generation.py`
- `aieng/tests/test_mesh_brep_solidification.py`
- `aieng/tests/test_assembly_topopt.py`
- `aieng-ui/backend/tests/test_assembly_topopt_demo.py`
- `aieng-ui/backend/tests/test_api.py -k assembly_topology_optimization_run_endpoint_is_explicit_and_part_scoped`

This file is intentionally not a claim that every workspace-wide test suite is green.
Broader backend/API/runtime suites remain outside this snapshot and can be sensitive
to current working directory, optional dependencies, or unrelated in-progress areas.