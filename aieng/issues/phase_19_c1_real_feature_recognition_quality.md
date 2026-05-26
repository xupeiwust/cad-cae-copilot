---
title: "[Phase 19 C1] Improve real CAD feature recognition quality on extracted topology"
labels: ["phase-19", "c1", "feature-recognition", "implementation-planned"]
status: closed
---

## Problem

Current feature recognition is deterministic and useful, but still heuristic/candidate-level. After real extraction stabilization, recognition quality on real topology needs a dedicated upgrade path.

## Goal

Improve recognition fidelity on real extracted topology while preserving explicit uncertainty and deterministic behavior.

## Scope

1. Define quality targets for real-topology feature recognition.
2. Expand rules/signals using extracted geometry attributes and adjacency evidence.
3. Add confidence/uncertainty annotations per recognized feature.
4. Preserve stable IDs and schema compatibility.

## Acceptance criteria

- [x] Real-topology fixtures show measurable recognition improvement versus current baseline.
- [x] Unknown/uncertain cases remain explicit (no silent guess completion).
- [x] Existing mock-based regression tests stay green.
- [x] Summary output distinguishes recognized vs uncertain features clearly.

## Boundary

No CAD geometry modification, no solver execution, no claim auto-advance.

## Closure evidence

- Implementation:
	- `src/aieng/graph/feature_recognition.py` (real-topology signals, uncertainty notes, confidence upgrade logic)
	- `src/aieng/ai/summary_writer.py` (feature recognition quality section)
- Tests:
	- `tests/test_feature_graph.py` (real-vs-mock measurable confidence uplift)
	- `tests/test_summary.py` (recognition quality reporting)
- Validation run:
	- `python -m pytest tests/test_feature_graph.py tests/test_summary.py -q` -> pass (`78 passed`)
- Commits:
	- `acace1a`
	- `a20329d` (doc closure sync)
