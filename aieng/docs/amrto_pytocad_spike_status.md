# AMRTO / PYTOCAD spike — status & blocker (#149)

Follow-up to [`amrto_pytocad_evaluation.md`](amrto_pytocad_evaluation.md) (which
concluded *"go, but only as a follow-up spike"*). That desk evaluation stands;
this note records the **executable** spike outcome and a go/no-go.

> **Honesty note.** The external AMRTO/PYTOCAD Zenodo package was **not run** as
> part of this note — see the blocker below. No `.3dm`/NURBS output was produced;
> nothing here claims mesh-derived NURBS is production CAD.

## Verdict: **defer full integration — external run is a maintainer task, not runnable in this environment**

The spike's core acceptance (download + run the Zenodo package, feed an AIENG
mesh, produce `.json`/`.3dm`) requires an environment this work did not have. The
AIENG **input side is structurally ready**; the **external toolchain run** and the
**`.3dm`→Shape-IR conversion layer** are the open work, and both are gated on a
maintainer-run of third-party research code.

## 1. Authors' example run — **blocked (documented)**

Could not be executed here:
- **No network fetch** of the Zenodo archive (offline build/CI-like environment).
- **No `.3dm` / rhino3dm runtime**, and no Windows `GMCG_revision.exe` (the
  generalized-motorcycle-graph quadrangulation step the README requires) — so the
  package is **not fully cross-platform** even where it can be fetched.
- Heavy native deps (`VTK 9.3.0`, `Open3D 0.17.0`) plus **old pins** (`numba
  0.56`, `numpy 1.22.2`) that conflict with AIENG's newer NumPy/SciPy stack — a
  separate isolated environment is required (see eval §3).

**To unblock:** a maintainer runs the Zenodo package on a machine with network +
the pinned isolated env (+ Windows for the GMCG exe), then shares the example
output and logs. The integration analysis can resume from there.

## 2. AIENG mesh input — **attempted at the AIENG boundary; ready, with one gap**

What AIENG produces today as the candidate input (confirmed in code):
- `topology_optimization` writeback emits `extruded_region` (2D B-Rep),
  `density_voxels`, or a **`smooth_mesh_proxy`** (triangle mesh) — and Shape IR
  recognises the surface-mesh kinds `{surface_mesh, smooth_mesh_proxy, mesh_proxy,
  triangle_mesh}` (`shape_ir.py` `_SURFACE_MESH_KINDS`).
- PYTOCAD expects exactly a **surface triangle mesh** as its starting point
  (eval §4.1), so the AIENG output *kind* is the right input.

**Gap:** there is no neutral **mesh-file exporter** (e.g. OBJ/PLY/STL) for the
`smooth_mesh_proxy` on `main` today — the proxy is an in-package Shape-IR/runtime
mesh, not yet written to a standalone file PYTOCAD can read. That small, fully
in-repo exporter is the cheapest concrete enabler and is the recommended first
implementation slice (it needs no external package and is unit-testable).

## 3. `.json` / `.3dm` output — **not produced (blocked upstream)**

Blocked by §1 (the package did not run). Even given output, the `.3dm`/JSON
NURBS-patch → AIENG Shape-IR conversion layer **does not exist** and is non-trivial
(eval §4.2): NURBS patches → analytic/OCC faces → stitched solid B-Rep, or a
freeform-evidence path. This conversion is the larger half of #204.

## 4. Dependency / install experience — **documented**

From the published `requirements.txt` (eval §3): `geomdl 5.3.1`, `joblib`,
`matplotlib 3.5.1`, `numba 0.56.0`, `numpy 1.22.2`, `open3d 0.17.0`, `pyinstrument`,
`scipy 1.13.1`, `vispy 0.14.2`, `vtk 9.3.0`, plus a Windows `GMCG_revision.exe`.
Expected install reality:
- **Isolated env required** — the `numpy 1.22 / numba 0.56` pins are incompatible
  with AIENG's current stack; do not co-install.
- **Heavy native wheels** (VTK, Open3D) complicate Linux CI and Windows deploy.
- **Windows-only step** (`GMCG_revision.exe`) blocks a clean Linux-only run.
- Net: a dedicated, throwaway environment per platform; not a casual `pip install`.

## 5. Go / no-go

**No-go for integration now; conditional-go for a maintainer-run spike, in this order:**
1. **In-repo (no external dep):** add a tested neutral-mesh exporter (OBJ) for the
   AIENG `smooth_mesh_proxy` so the AIENG input is file-ready. *(Recommended next
   slice for #204; unit-testable, no Zenodo dependency.)*
2. **Maintainer-run:** run the Zenodo PYTOCAD package in an isolated pinned env
   (+ Windows GMCG exe) on its own example, then on the AIENG OBJ; capture
   `.json`/`.3dm` + logs.
3. **Only if (2) succeeds reliably:** build the `.3dm`/JSON → Shape-IR conversion
   layer (the bulk of #204), gated so mesh-derived NURBS is recorded as
   reconstructed/lossy evidence — **never** as production CAD.

## Honesty / non-goals
- No production integration; the external package was not run here.
- Mesh-derived NURBS output is reconstructed/lossy, **not production CAD**.
