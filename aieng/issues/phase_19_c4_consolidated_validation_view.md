---
title: "[Phase 19 C4] Add consolidated validation-state view resource"
labels: ["phase-19", "c4", "validation", "implementation-planned"]
status: closed
---

## Problem

Validation state is currently distributed across multiple authoritative resources. A consolidated read model would improve AI and tooling consumption.

## Goal

Provide a generated consolidated validation-state view that summarizes claim status and evidence links without replacing authoritative ledgers.

## Scope

1. Define generated read-view resource shape (name to be finalized).
2. Aggregate from `validation/status.yaml`, `results/claim_map.json`, and `results/evidence_index.json`.
3. Add validator consistency checks between consolidated view and sources.
4. Surface summary counts and pointers for agent consumption.

## Acceptance criteria

- [x] Consolidated view can be generated deterministically.
- [x] Conflicts between consolidated view and source ledgers are detected.
- [x] Source resources remain the authoritative truth.
- [x] Docs clarify this is a derived view, not source-of-truth.

## Boundary

No claim auto-advance; no solver/mesher/CAD execution implied.

## Closure evidence

- Implementation:
	- `src/aieng/validation/evidence_report_writer.py`
	- `schemas/evidence_report.schema.json`
	- `src/aieng/validate.py` (cross-ledger consistency checks)
	- `src/aieng/cli.py` (`aieng write-evidence-report`)
	- `src/aieng/ai/summary_writer.py` (consolidated report visibility)
	- `src/aieng/mcp/server.py` (`get_evidence_report`)
- Tests:
	- `tests/test_evidence_report.py`
	- related command coverage in `tests/test_docs_checkpoint.py`
- Commit:
	- `acace1a`
