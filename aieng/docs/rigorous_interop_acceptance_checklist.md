# Rigorous Interoperability Acceptance Checklist (v1)

This checklist defines the minimum acceptance gates for claiming rigorous CAD/CAE interoperability for `.aieng`.

Rigorous means:

1. No silent semantic drift across conversion boundaries.
2. No implicit claim upgrades from imported artifacts.
3. Deterministic, testable, auditable writeback and validation behavior.

This document is intended as a release gate (DoD), not just guidance.

## Scope

The checklist applies to:

1. CAD to `.aieng` conversion.
2. CAE deck and result import into `.aieng`.
3. `.aieng` to external CAD/CAE writeback handoff.
4. Cross-resource consistency and claim integrity.

## Gate Checklist

Mark each gate as PASS before claiming rigorous interoperability.

| Gate | Requirement | Evidence required | Current state |
|---|---|---|---|
| G1 | Global import policy is evidence-only by default and no import path auto-updates claim status | CLI behavior, command docs, regression tests | PASS |
| G2 | Every claim status change is explicit, traceable, and linked to evidence IDs | `update-claim` usage plus claim/evidence linkage tests | PASS |
| G3 | Solver result intake extracts deterministic numeric observations with explicit unknown handling | importer tests for numeric parse and missing patterns | PASS |
| G4 | Mesh evidence intake records deterministic mesh summary and explicit quality unknowns when not available | mesh importer tests and summary output checks | PASS |
| G5 | Cross-resource validator catches contradictions across status, claims, evidence, and tool trace | validator tests for contradiction cases | PASS |
| G6 | Adapter conversion follows known-only rule with explicit missingness (`missing`, `partial`, `unknown`, `unsupported`) | completeness report + conversion policy checks | PASS |
| G7 | At least one CAD writeback path is executable under explicit guardrails (not semantic-only) | integration test showing external CAD artifact update path | PASS |
| G8 | Roundtrip invariance test exists for core semantics (CAD/CAE -> `.aieng` -> handoff artifacts) | non-flaky roundtrip fixture with stable assertions | PASS |
| G9 | Claim decision thresholds are formalized per claim ID (what is enough for pass/fail/review) | machine-readable decision policy + tests | PASS |
| G10 | Tool trace metadata minimum contract is fixed and validated for all adapters | schema/validator checks + adapter conformance tests | PASS |
| G11 | Adapter capability declaration is required and tested against emitted resources | capability contract conformance tests | PASS |
| G12 | Interop conformance suite runs in CI for representative fixtures | CI job with deterministic fixtures and report artifacts | PASS |

## Issue Tracking

See [issue_standardization_record.md](issue_standardization_record.md) for standard issue format and closure summaries.

Tracked issues for this milestone:

1. **#31** [GOVERNANCE] Anti-drift protocol and maintenance policy → ✅ CLOSED
2. **#4** [G7] CAD writeback executable path → ✅ CLOSED
3. **#32** [G8] Roundtrip invariance fixtures → ✅ CLOSED
4. **#33** [G9] Claim decision thresholds per claim ID → ✅ CLOSED
5. **#34** [G12] Interop conformance suite CI → ✅ CLOSED

### Issue Closure Summary

All 5 tracked issues completed by May 12, 2026:

| Issue | Gate | Status | Closed By | Evidence |
|-------|------|--------|-----------|----------|
| #31 | Found. | ✅ | a4c5e40 | Maintenance protocol in checklist |
| #4 | G7 | ✅ | d19b970 | CAD writeback integration test |
| #32 | G8 | ✅ | 311420c | Deterministic roundtrip fixtures |
| #33 | G9 | ✅ | bc4a05c | Claim decision policy validator |
| #34 | G12 | ✅ | 311420c | CI conformance suite (12 tests) |

Related closed issues: #28, #29 (pre-G1 validation)

## Maturity Bands

Use these bands to communicate progress honestly:

1. Foundation: G1, G2, G5, G6 are PASS.
2. Controlled Interop: Foundation plus G3, G4, G10, G11 are PASS.
3. Rigorous Interop: all gates G1-G12 are PASS.

Current project position (May 2026): **Rigorous Interop ACHIEVED**. All gates G1-G12 are PASS. Foundation, Controlled Interop, and Rigorous Interop bands all complete.

## Maintenance Protocol (Required)

The gate status column is manually maintained and is not fully self-validated by tests.

This means drift can happen unless the team updates the checklist every iteration.

Required maintenance rules:

1. Any change that affects evidence or behavior for G1-G12 must update the corresponding gate state.
2. Any gate state transition (for example FAIL to PARTIAL, PARTIAL to PASS, or PASS to FAIL) must include a one-line rationale in the same PR/commit context.
3. Iteration closeout must include an explicit checklist review step before declaring milestone status.
4. If status is uncertain, set the gate to PARTIAL and document the missing proof.

Drift warning:

1. Without updates, this checklist becomes historical documentation instead of a live release gate.
2. Tests currently validate the presence of maintenance-policy language, not full semantic synchronization of gate states.

## Priority Order to Reach Rigorous Interop

✅ **RIGOROUS INTEROP ACHIEVED (May 12, 2026)**

1. ~~Close CAD writeback executable path (G7).~~ DONE (d19b970, e205997)
2. ~~Add roundtrip invariance fixtures (G8).~~ DONE (e2aafb9)
3. ~~Formalize claim decision policy per claim ID (G9).~~ DONE (bc4a05c)
4. ~~Complete adapter metadata and capability conformance tests (G10, G11).~~ DONE (4447582, 096ea13)
5. ~~Run interop conformance suite in CI (G12).~~ DONE (311420c)

## Next Milestone: Phase 17

Rigorous Interop is complete. The next phases extend the interoperability foundation to real files and mesh handoff:

| Issue | Phase | Goal |
|-------|-------|------|
| #35 | Phase 17A | Stabilize real STEP geometry extraction as default entry path |
| #36 | Phase 17B | Mesh handoff completeness — `aieng write-mesh-handoff` for external Gmsh integration |

These phases do not change the G1–G12 gate states. They extend the pipeline into production-quality file handling and round-trip handoff artifacts.

---

## Non-negotiable Safety Notes

1. Do not claim engineering safety from imported artifacts alone.
2. Do not infer pass/fail status automatically from raw imported files.
3. Unsupported means not yet evidenced, not false.
4. If a gate is not PASS, report it explicitly rather than softening language.
