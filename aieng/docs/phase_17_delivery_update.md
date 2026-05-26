# Phase 17 Delivery Update (17A + 17B)

Date: 2026-05-13

This document summarizes the implementation, validation evidence, and boundary confirmations for:

- Issue #35: Phase 17A real STEP geometry extraction stabilization.
- Issue #36: Phase 17B mesh handoff completeness.

## Scope delivered

1. Topology backend default behavior moved to `auto` with runtime selection:
   - Prefer `occ` when OCP runtime is available.
   - Fall back to `mock` otherwise.
2. New command `aieng write-mesh-handoff` writes `simulation/mesh_handoff_contract.json`.
3. New schema `schemas/mesh_handoff_contract.schema.json` with execution-boundary const guards.
4. Validator integration for mesh handoff schema + semantics:
   - geometry source existence,
   - topology face/edge reference validity,
   - target claim ID presence checks against claim map.
5. Completeness report improvements:
   - `real_geometry_extraction` boolean,
   - `mesh_handoff_contract` category.
6. Real OCC integration checks and round-trip tests added.

## Key files changed

- `src/aieng/cli.py`
- `src/aieng/simulation/mesh_handoff_writer.py`
- `schemas/mesh_handoff_contract.schema.json`
- `src/aieng/validate.py`
- `src/aieng/validation/completeness_writer.py`
- `schemas/completeness_report.schema.json`
- `tests/test_geometry_backend_detection.py`
- `tests/test_mesh_handoff_contract.py`
- `tests/test_docs_checkpoint.py`
- `docs/command_reference.md`
- `issues/phase_17a_real_step_stabilization.md`
- `issues/phase_17b_mesh_handoff_completeness.md`

## Test evidence

Focused regression (phase-17 related):

```text
python -m pytest tests/test_geometry_backend_detection.py tests/test_mesh_handoff_contract.py tests/test_import_mesh_evidence.py tests/test_docs_checkpoint.py -q
118 passed
```

Expanded phase-17 bundle:

```text
python -m pytest tests/test_mesh_handoff_contract.py tests/test_geometry_backend_detection.py tests/test_completeness_report.py tests/test_docs_checkpoint.py -q
122 passed
```

## Acceptance mapping

Phase 17A (#35):

1. Real STEP integration test path exists (guarded by OCC runtime).
2. Completeness report explicitly distinguishes real extraction from mock extraction.
3. OCC path recognition asserts core candidate types.
4. Existing mock-path tests remain green.
5. Docs reflect `auto` backend and fallback behavior.

Phase 17B (#36):

1. `write-mesh-handoff` command generates contract and manifest mapping.
2. Schema boundary guards enforce no in-core mesher execution.
3. Validator checks handoff resource semantically.
4. Round-trip compatibility covered (`write-mesh-handoff` -> `import-mesh-evidence` -> `summarize`/`validate`).
5. Existing mesh evidence import behavior remains stable.

## Boundary confirmation

The delivered implementation preserves project boundaries:

1. No in-core mesh generation.
2. No in-core solver execution.
3. No arbitrary CAD/B-rep editing.
4. No claim auto-advance due to imported evidence or handoff generation.
