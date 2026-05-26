---
title: "[Phase 19 C3] Add per-feature allowed-operation catalog"
labels: ["phase-19", "c3", "operations", "implementation-planned"]
status: closed
---

## Problem

LLM workflows can benefit from explicit machine-readable operation admissibility per feature (operation type, required conditions, blocked conditions).

## Goal

Add a first-class structured allowed-operation catalog to improve safe patch planning and pre-checking.

## Scope

1. Define resource schema for per-feature allowed operations and preconditions.
2. Add validator checks for operation references and condition consistency.
3. Integrate with patch proposal generation and policy checks.
4. Surface operation constraints in AI summary and MCP responses.

## Acceptance criteria

- [x] Catalog resource is schema-validated and linked from manifest.
- [x] Patch proposals can reference admissible operations deterministically.
- [x] Validator rejects operation references that violate catalog constraints.
- [x] Documentation includes usage and boundary expectations.

## Boundary

Catalog constrains planning and validation; it does not execute CAD/CAE tools by itself.

## Closure evidence

- Implementation:
	- `schemas/allowed_operations_catalog.schema.json`
	- `src/aieng/operations/allowed_operations_catalog.py`
	- `src/aieng/validate.py` (catalog semantic checks)
	- `src/aieng/ai/patch_proposer.py` (admissibility-aware planning)
	- `src/aieng/ai/summary_writer.py` and `src/aieng/mcp/server.py` (catalog surfacing)
- Tests:
	- `tests/test_allowed_operations_catalog.py`
	- related CLI/docs coverage in `tests/test_docs_checkpoint.py`
- Commit:
	- `acace1a`
