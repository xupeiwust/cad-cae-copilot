---
title: "[Phase 19 C2] Expand guarded executable CAD writeback breadth"
labels: ["phase-19", "c2", "cad-writeback", "implementation-planned"]
status: closed
---

## Problem

Executable writeback exists (G7) but currently covers limited feature classes. The gap is breadth, not absence.

## Goal

Extend guarded regeneration-backed writeback to additional feature families while preserving strict boundary controls.

## Scope

1. Enumerate candidate feature families for regeneration-backed writeback.
2. Define per-family parameter contracts and preconditions.
3. Extend `aieng apply-patch` execution path where contracts are satisfiable.
4. Keep semantic-only fallback for unsupported feature families.

## Acceptance criteria

- [x] At least one additional feature family gains executable writeback support.
- [x] Unsupported families fail safely with explicit reasons.
- [x] Roundtrip invariance constraints remain satisfied.
- [x] Tests cover success and guarded refusal paths.

## Boundary

No arbitrary STEP/B-rep editing. Only explicit regeneration-backed paths are in scope.

## Closure evidence

- Implementation:
	- `src/aieng/patch/executor.py` (`flange` and `flange_candidate` guarded regeneration support)
- Tests:
	- `tests/test_patch_executor.py` (flange writeback success path + guarded refusal coverage)
	- `tests/test_roundtrip_invariance.py`
- Commit:
	- `acace1a`
