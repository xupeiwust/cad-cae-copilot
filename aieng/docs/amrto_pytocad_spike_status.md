# AMRTO / PYTOCAD spike status (#149)

Follow-up to [`amrto_pytocad_evaluation.md`](amrto_pytocad_evaluation.md), which
concluded "go, but only as a follow-up spike." This note records the executable
spike evidence and the current go/no-go decision.

> Honesty note: no `.json` or `.3dm` reconstruction artifact was produced by this
> run. Nothing here claims mesh-derived NURBS/freeform output is production CAD.

## Verdict: no-go for integration now; conditional-go for a maintainer rerun

The AIENG-side input bridge is ready, but the published AMRTO/PYTOCAD package is
not yet a reliable dependency for the product path. The package was downloaded
and inspected, but the authors' example could not be executed in the current
environment because the pinned Python stack rejects the available interpreter.

Full integration remains deferred. A future attempt should use an isolated
Python 3.8/3.10-style environment on Windows, preserve the third-party toolchain
outside the AIENG runtime, and only proceed to #204 if the external run produces
useful artifacts reproducibly.

## Evidence collected

- Source inspected: Zenodo record `10.5281/zenodo.14381998`, version v3,
  published 2024-12-11.
- Downloaded package: `CODE_AMRTO.zip`, 238,573,730 bytes, md5 published by
  Zenodo as `f8e184854cb109282bd00a26e29c50c7`.
- Not downloaded: `MODEL_AMRTO.zip` (about 1.6 GB). It is not required for the
  first code/package install check.
- Extracted package contents included `Readme.txt`, `requirements.txt`,
  `PYTOCAD_simple.py`, `PYTOCAD_complete.py`, `json2on.exe`, `on2json.exe`, and
  Windows executables under `Instant-Meshes and GMCG_revision/`, including
  `GMCG_revision.exe`.
- The code package also includes example tri/quad OBJ inputs under
  `data/output_tri` and `data/output_quad`.

## Authors' example run

Status: blocked, documented.

The README expects a Windows-style checkout at `D:\CODE_AMRTO`, Python 3.8,
installation from `requirements.txt`, generated sparse quadrilateral layouts
from `GMCG_revision.exe`, then a `PYTOCAD.py` run to produce `.json` and `.3dm`.

The current machine provides Python 3.11.5. Creating a clean Python 3.11 venv and
running `pip install -r requirements.txt` failed before the example could run:

```text
RuntimeError: Cannot install on Python version 3.11.5; only versions >=3.7,<3.11 are supported.
```

The immediate blocker is `numba==0.56.0`, which does not support Python 3.11.
The package also relies on heavy native dependencies (`open3d`, `vtk`, `vispy`)
and Windows executables/path assumptions, so it should not be co-installed into
AIENG's normal runtime or CI environment.

## AIENG mesh input attempt

Status: input bridge ready; external ingestion blocked before execution.

AIENG now emits a neutral OBJ file for topology smooth-mesh output:
`geometry/topology_result_mesh.obj`. The implementation lives in
[`aieng/src/aieng/converters/mesh_obj_export.py`](../src/aieng/converters/mesh_obj_export.py)
and is covered by `aieng/tests/test_mesh_obj_export.py`. This gives PYTOCAD a
file-level surface mesh input without adding Zenodo dependencies to AIENG.

The Zenodo package was not able to ingest that OBJ in this run because dependency
installation failed before `PYTOCAD_simple.py` or `PYTOCAD_complete.py` could be
executed. That is an external-toolchain blocker, not an AIENG exporter blocker.

## Output status

No new `.json` or `.3dm` output was produced by this run.

Even if a future rerun produces `.json` or `.3dm`, the conversion layer into
AIENG Shape IR does not exist yet. That larger follow-up belongs to #204 and must
preserve an explicit reconstructed/lossy/non-production boundary until OCC/STEP
validation proves otherwise.

## Go / no-go recommendation

No-go for product integration now.

Conditional-go only for a bounded maintainer rerun:

1. Create an isolated environment compatible with the published pins.
2. Place or patch the package so the hardcoded `D:\CODE_AMRTO` assumptions are
   satisfied without affecting the AIENG repo.
3. Run the authors' bundled example and capture logs plus generated `.json` /
   `.3dm` artifacts.
4. Feed `geometry/topology_result_mesh.obj` from an AIENG topology result through
   the same path, or record the exact failure point.
5. If both runs succeed, re-open #204 as a narrow Shape-IR reconstruction design
   task with provenance, confidence, and validation gates.

## Product boundary

- Keep AMRTO/PYTOCAD out of the main CAD/CAE runtime for now.
- Do not block alpha release, packaging, Docker, or golden-path CAE reliability
  on this research track.
- Do not claim STEP/B-Rep, editable CAD, or production NURBS output without
  successful OCC validation and explicit artifact provenance.
