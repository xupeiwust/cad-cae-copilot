# PR Description (Phase 17A + 17B)

## Summary

This PR delivers the current implementation slice for:

- Phase 17A (#35): stabilize real STEP extraction as the recommended default path when OCC runtime is available.
- Phase 17B (#36): add mesh handoff contract generation and validation-complete round-trip support.

It also updates issue/docs/changelog artifacts so implementation status, acceptance mapping, and evidence are synchronized.

## What Changed

### 1) CLI and runtime behavior

- `aieng extract-topology` default backend switched to `auto`:
  - prefers `occ` when OCP runtime is available,
  - falls back to `mock` otherwise.
- new command: `aieng write-mesh-handoff`.

Primary file:

- `src/aieng/cli.py`

### 2) Mesh handoff resource + schema

- added writer for `simulation/mesh_handoff_contract.json`.
- added schema with execution-boundary const guards:
  - `external_tools_execute: true`
  - `aieng_core_executes_mesher: false`

Primary files:

- `src/aieng/simulation/mesh_handoff_writer.py`
- `schemas/mesh_handoff_contract.schema.json`

### 3) Validator integration

- validator now checks mesh handoff resource when present:
  - geometry source path exists,
  - topology face/edge IDs are valid,
  - target claim IDs are checked against claim map entries.
- claim mapping logic aligned to claim-map schema (`claim_id` primary, `id` fallback for compatibility).

Primary file:

- `src/aieng/validate.py`

### 4) Completeness report enhancements

- added `real_geometry_extraction` boolean to completeness report.
- added `mesh_handoff_contract` completeness category.

Primary files:

- `src/aieng/validation/completeness_writer.py`
- `schemas/completeness_report.schema.json`

### 5) Tests and docs

- added/extended tests for:
  - `auto` backend routing,
  - guarded OCC real STEP extraction to completeness report,
  - guarded OCC feature recognition candidate-type presence,
  - mesh handoff claim ID mapping,
  - mesh handoff round-trip compatibility (`write-mesh-handoff` -> `import-mesh-evidence` -> `summarize` -> `validate`).
- updated command documentation and phase tracking docs.
- added delivery summary doc for issue/PR tracking.

Primary files:

- `tests/test_geometry_backend_detection.py`
- `tests/test_mesh_handoff_contract.py`
- `tests/test_docs_checkpoint.py`
- `docs/command_reference.md`
- `docs/phase_17_delivery_update.md`
- `issues/phase_17a_real_step_stabilization.md`
- `issues/phase_17b_mesh_handoff_completeness.md`
- `CHANGELOG.md`

## Acceptance Mapping

### #35 (Phase 17A)

- [x] Real STEP integration test path with OCC backend exists (guarded by runtime availability).
- [x] Completeness report distinguishes real extraction vs mock extraction.
- [x] OCC path feature recognition asserts core candidate classes.
- [x] Existing mock-path regressions remain green.
- [x] CLI/docs reflect recommended backend behavior.

### #36 (Phase 17B)

- [x] `aieng write-mesh-handoff` writes valid contract resource.
- [x] Schema enforces execution-boundary policy.
- [x] Validator checks contract semantics when present.
- [x] Existing mesh evidence import tests remain passing.
- [x] Round-trip compatibility is tested and documented.

## Test Evidence

Executed locally in conda env `aieng311`.

```text
python -m pytest tests/test_geometry_backend_detection.py tests/test_mesh_handoff_contract.py tests/test_import_mesh_evidence.py tests/test_docs_checkpoint.py -q
118 passed
```

```text
python -m pytest tests/test_mesh_handoff_contract.py tests/test_geometry_backend_detection.py tests/test_completeness_report.py tests/test_docs_checkpoint.py -q
122 passed
```

## Boundary and Safety Statement

This PR preserves project boundaries:

1. No in-core meshing execution.
2. No in-core solver execution.
3. No arbitrary STEP/B-rep editing.
4. No claim auto-advance from handoff generation or evidence import.

## Risks / Notes

1. OCC integration tests are runtime-guarded (`importorskip`) and will skip where OCP is unavailable.
2. Claim ID compatibility uses `claim_id` first, `id` fallback in validator/writer paths for robustness.

## Related Issues

- #35
- #36
