# Evaluation: AMRTO / PYTOCAD for topology-optimization → editable NURBS CAD

Status: **research/spike (#130).** No production code is committed from this issue.
This document records a feasibility assessment of Tsinghua's open-source
AMRTO/PYTOCAD framework as a possible deeper topology-to-CAD path for the
AIENG workbench.

Relates to Epic #99 (Phase 4 — topology-to-sizing) and the deep-research
direction report (`deepresearch_result/cad_copilot_direction.agent.final.md`,
§3.5/§7.1).

---

## 1. What AMRTO / PYTOCAD claims to do

AMRTO (**A**utomated **M**odel **R**econstruction for **T**opology
**O**ptimization) is a research framework published in *Computer Methods in
Applied Mechanics and Engineering* (CMAME, 2024) by Ren et al. at Tsinghua
University. Its Python implementation is referred to as **PYTOCAD**.

The pipeline is:

1. Take a topology-optimization result (typically a dense triangle mesh or
   voxel density field).
2. Smooth the surface and remesh it with
   [Instant Meshes](https://github.com/wjakob/instant-meshes)-style
   quadrangulation via generalized motorcycle graphs.
3. Fit NURBS patches to the quad layouts using improved harmonic mapping and
   adaptive sampling.
4. Output a smooth, explicit boundary-representation (B-Rep) CAD model.

Public claims (from the paper and announcement posts):

- Produces **editable NURBS B-Rep** rather than a voxel/mesh proxy.
- Reduces NURBS patch count, control-point count, and file size vs.
  nTopology 5.3.2, Geomagic Design X 2022, HyperMesh 2021, Abaqus 6.14, etc.
- Handles complex 3D topology-optimization results, including metamaterials.

---

## 2. License and availability

| Item | Finding |
|---|---|
| **GitHub repository** | https://github.com/rhy-thu/AMRTO |
| **License** | **MIT** (confirmed via GitHub API: `spdx_id: MIT`). Compatible with our MIT/Open-Core posture. |
| **Completeness** | The GitHub repository is **incomplete**; the README states full code and test models are on Zenodo: https://zenodo.org/records/14381998 |
| **Language / runtime** | Python 3.8 (per README). |
| **Maintenance** | Updated as of 2026-02-12 (GitHub API). 34 stars, 6 forks, 7 open issues. Research-code maturity: bug fixes and documentation may be sparse. |

---

## 3. Dependencies

The published `requirements.txt` (from the GitHub repo) is:

```text
geomdl==5.3.1
joblib==1.4.2
matplotlib==3.5.1
numba==0.56.0
numpy==1.22.2
open3d==0.17.0
pyinstrument==4.5.3
scipy==1.13.1
vispy==0.14.2
vtk==9.3.0
```

Notes for integration:

- **VTK 9.3 + Open3D 0.17** are heavy native dependencies. They complicate
  CI and Windows deployment compared with our current pure-Python + optional-OCP
  stack.
- **Numba 0.56** and **NumPy 1.22** are pinned to older versions. Our current
  environment uses newer NumPy/SciPy; mixing these may require a separate
  isolated environment or dependency reconciliation.
- **geomdl** is the NURBS library; it is lightweight and already useful for
  our own freeform/NURBS experiments.
- The README also references a Windows executable `GMCG_revision.exe` for the
  generalized-motorcycle-graph quadrangulation step. This implies the current
  release is **not fully cross-platform** without additional work.

---

## 4. I/O mapping to AIENG

### 4.1 Input side — what we would feed AMRTO

Our current `topology_optimization.py` produces one of three writeback shapes:

- `extruded_region` (2D contour → already editable B-Rep)
- `density_voxels` (voxel grid)
- `smooth_mesh_proxy` (triangle mesh, e.g., from marching cubes)

AMRTO expects a **surface triangle mesh** as its starting point. The natural
integration path is:

```
topology_optimization.py result
    → density_voxels / smooth_mesh_proxy (triangle mesh)
    → AMRTO smoothing + quadrangulation + NURBS fitting
    → NURBS B-Rep
```

This would let us upgrade a `smooth_mesh_proxy` result into a true analytic
B-Rep, which is stronger than the current voxel proxy but more complex than the
2D contour B-Rep path planned in #106.

### 4.2 Output side — what we would get back

The README says PYTOCAD generates:

- `.json` file (likely NURBS patch/control-point data)
- `.3dm` file (Rhino 3DM format)

To become an AIENG Shape IR node we would need to convert the `.3dm`/JSON into
one of our supported representations:

- **analytic B-Rep** (STEP/OCC face list) — preferred; requires converting
  NURBS patches to analytic/OCC faces.
- **freeform B-Rep evidence** — if only patch data is available, we already
  have a "freeform candidate-only" path; we would need to promote it to a
  stitched, solid B-Rep.

This conversion layer does **not** exist today and is non-trivial.

---

## 5. Comparison with planned Phase-4 contour path (#106)

| Capability | #106 2D contour writeback | AMRTO / PYTOCAD |
|---|---|---|
| Input | 2D/extrudable SIMP density field | 3D triangle mesh / voxel proxy |
| Output | Analytic B-Rep (extrusion) | NURBS B-Rep from fitted patches |
| Editable parameters | Easy: perimeter contour → few dims | Hard: many NURBS control points |
| Dependency weight | Low (existing OCC/CadQuery optional) | High (VTK, Open3D, Numba, geomdl) |
| Cross-platform | Yes | Partial (Windows .exe step noted) |
| Honesty posture | Clear: 2D/extrudable only | Clear: mesh-derived, 3D experimental |
| Maturity | In-house, controllable | Research code, external maintenance |

Verdict: AMRTO is a **deeper but heavier capability** than the contour path.
It is not a replacement for #106; it is a future 3D-mesh-to-CAD enhancement
that could sit behind the same topology-optimization writeback switch.

---

## 6. Risks and blockers

1. **Incomplete GitHub repo.** Full code and models are on Zenodo only. We
   cannot evaluate the actual API or robustness without downloading the Zenodo
   archive (~several GB likely, given the README's "file memory size" note).
2. **Windows-only preprocessing step.** The `GMCG_revision.exe` dependency
   suggests the authors' workflow is Windows-centric. A Linux/CI-friendly
   path would require porting or replacing that step.
3. **Heavy dependency stack.** VTK + Open3D add significant install and
   licensing surface. Open3D is Apache 2.0; VTK is BSD; geomdl is MIT — all
   permissive, but the binary wheels are large.
4. **Output → Shape IR gap.** Getting from `.3dm`/NURBS JSON to a
   re-compilable, parameter-pickable Shape IR node is a separate integration
   project comparable in size to our existing mesh-to-CAD reconstruction work.
5. **Research-code quality.** Publication code often prioritizes reproducing
   paper figures over API stability, error handling, and documentation.
   Expect glue code and edge-case fragility.
6. **No demonstrated parameter optimization downstream.** The output is
   editable in Rhino, but it is not obvious how to turn fillet radius / hole
   diameter into the kind of named, stable parameters Phase-3/4 design studies
   require.

---

## 7. Honesty boundary

If integrated, the resulting artifact must carry the same caveats as our other
mesh-derived reconstruction paths:

- `production_ready: false`
- `engineering_level: experimental_reference`
- Output is **mesh-derived and lossy**, not original design history.
- Claims are limited to "reconstructed CAD geometry available for inspection",
  never "certified" or "manufacturing-ready".
- Linear-static validation only until a V&V case is run.

These are consistent with the existing `mesh_brep_*` and `freeform_surface_*`
honesty patterns in the codebase.

---

## 8. Integration cost estimate

Rough sizing for a future implementation spike:

| Task | Estimate |
|---|---|
| Download Zenodo archive, install deps, run authors' examples | 0.5–1 person-day |
| Wrap PYTOCAD in an isolated environment / CLI | 1–2 person-days |
| Convert `.3dm`/JSON output to OCC B-Rep or freeform evidence | 3–5 person-days |
| Wire into `topology_optimization.py` writeback switch | 1 person-day |
| Add one deterministic regression test (no external solver) | 1–2 person-days |
| Documentation + honesty claims + schema updates | 1 person-day |
| **Total spike to first merged feature** | **~1–2 person-weeks** |

This assumes the authors' code runs without major porting work. If the
`GMCG_revision.exe` step cannot be avoided on Linux/CI, the cost rises
significantly.

---

## 9. Recommendation: **Go — but only as a follow-up spike, not as the primary Phase-4 path**

1. **Keep #106 (2D contour B-Rep writeback) as the primary Phase-4
   deliverable.** It is lighter, cross-platform, and directly produces
   editable parameters.
2. **Open a follow-up spike issue under Epic #99** to evaluate the actual
   Zenodo/PYTOCAD package against one of our topology-optimization fixtures.
   Acceptance: run the authors' code end-to-end and produce a `.3dm`/JSON from
   our `smooth_mesh_proxy` output.
3. If the spike succeeds, open implementation sub-issues for:
   - dependency isolation (optional Docker/venv wrapper),
   - `.3dm`/NURBS → Shape IR conversion,
   - topology-optimization writeback integration,
   - regression test + honesty claims.
4. If the spike fails (e.g., Windows-only tooling, unacceptable robustness,
   or conversion cost), document the blocker and deprioritize.

---

## 10. Acceptance criteria for the follow-up spike

- [ ] Download and run the complete Zenodo PYTOCAD package on at least one
      provided example.
- [ ] Produce the same output format (`.json` + `.3dm`) that a downstream
      converter would consume.
- [ ] Attempt to feed AIENG's `smooth_mesh_proxy` topology result as input and
      record success/failure.
- [ ] Document actual dependency install experience on Linux and Windows.
- [ ] Decide go/no-go on a full integration issue.
