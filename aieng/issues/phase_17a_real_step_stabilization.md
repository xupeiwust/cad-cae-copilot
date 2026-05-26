---
title: "[Phase 17A] Stabilize real STEP geometry extraction as default entry path"
labels: ["phase-17", "phase-17a", "geometry", "topology", "quality"]
status: closed
---

## Motivation

The project has a strong semantic and evidence pipeline, but default topology extraction is still mock-first. For LLM-facing engineering understanding to be reliable in production scenarios, geometry-present packages should preferentially carry topology and feature candidates derived from real STEP input when a real backend is available.

Phase 17A closes the trust gap between mock determinism and real CAD-derived extraction quality.

## Goal

Stabilize OCC/CadQuery-based real STEP topology extraction so it becomes the recommended default path when runtime dependencies are available, while preserving deterministic mock fallback.

## Scope

1. Run full entry pipeline on at least one real engineering STEP file and record extraction outcomes.
2. Validate topology quality in `geometry/topology_map.json`:
   - face and edge counts are plausible and stable,
   - surface type distribution is reported,
   - core geometric attributes are populated where available.
3. Verify feature recognition on real OCC output:
   - base plate candidate,
   - hole candidates,
   - hole pattern candidates.
4. Add `real_geometry_extraction` status to `validation/completeness_report.json`.
5. Promote OCC backend as recommended default when CadQuery runtime is detected; keep mock backend as explicit fallback.
6. Ensure CLI and summary clearly distinguish real extraction vs mock extraction.

## Non-goals

- No CAD geometry modification.
- No meshing, solver execution, or manufacturing checks.
- No claim auto-advance from extraction alone.
- No requirement to remove the mock backend.

## Acceptance criteria

- [x] At least one real STEP integration test passes end-to-end with OCC backend.
- [x] `validation/completeness_report.json` records whether geometry extraction is real or mock.
- [x] Feature recognition on OCC output yields at least the same candidate classes as mock baseline for reference fixture.
- [x] Existing mock-based tests remain green.
- [x] CLI docs reflect backend recommendation logic and fallback behavior.

## Test plan

- Unit tests for completeness-report flagging and backend selection behavior.
- Integration tests for real STEP extraction path (guarded when OCC runtime unavailable).
- Regression tests to ensure mock fixtures and deterministic baseline remain stable.

## Boundary guardrails

- `.aieng` remains a semantic/evidence layer, not a CAD kernel.
- Real extraction quality improvements do not imply CAD feature truth guarantees.
- Extraction metadata is evidence of conversion state, not evidence of engineering validity.

## Related

- `docs/roadmap.md` (Phase 17A)
- `README.md` (Upcoming Phase 17)
- `docs/mvp_checkpoint.md` (Upcoming section)
- `docs/rigorous_interop_acceptance_checklist.md` (Issue #35 reference)

## Closure evidence

Current implementation evidence (workspace state):
- Commit hash: `acace1a`.
- Tests passing:
   - `python -m pytest tests/test_geometry_backend_detection.py tests/test_mesh_handoff_contract.py tests/test_completeness_report.py tests/test_docs_checkpoint.py -q` -> pass.
   - Includes guarded real OCC integration checks (`importorskip`) and auto-backend selection checks.
- Docs updated:
   - `docs/command_reference.md` (extract-topology default `auto`, `occ` recommendation/fallback behavior).
   - `README.md`, `docs/roadmap.md`, `docs/mvp_checkpoint.md` (Phase 17 framing and milestones).

Issue closure status:
- Local issue doc status set to `closed`.
