# Issue Standardization Record

This document standardizes the format for all tracked issues and provides closure templates.

## Issue Format Standard

All issues must follow this structure:

```
## Title
[Gate reference] [Concise action] - [Measurable outcome]
Example: [G7] Implement CAD writeback path - executable handoff to external tools

## Description
- **Gate:** Which acceptance gate this implements
- **Acceptance Criteria:** Specific, measurable requirements
- **Evidence Required:** What must be present to close
- **Related Issues:** Cross-references
- **Status:** OPEN, IN PROGRESS, READY FOR REVIEW, CLOSED

## Checklist
- [ ] Acceptance criteria 1
- [ ] Acceptance criteria 2
- [ ] Tests passing
- [ ] Documentation complete
- [ ] Commit hash recorded

## Notes
- Any relevant context or constraints
```

## Standardized Gate Issues

### Issue #31: [GOVERNANCE] Anti-drift protocol and maintenance policy

**Gate:** Foundation / Maintenance protocol
**Purpose:** Define governance for gate status maintenance and drift prevention
**Evidence Required:** 
- Maintenance protocol documented in checklist
- Clear rules for gate transitions
- Examples of how to handle failures

**Status:** ✅ CLOSED
**Closed By:** Maintenance protocol section in rigorous_interop_acceptance_checklist.md
**Key Commit:** a4c5e40

---

### Issue #32: [G8] Roundtrip invariance fixtures - deterministic CAD/CAE conversion

**Gate:** G8 / Controlled Interop
**Purpose:** Verify core semantics preservation across roundtrip (CAD → .aieng → handoff)
**Acceptance Criteria:**
- [ ] Non-flaky roundtrip fixture for bracket reference model
- [ ] Stable assertions on topology preservation
- [ ] Evidence scaffold determinism verified
- [ ] Fixture reproducible in CI

**Status:** ✅ CLOSED
**Closed By:** test_g12_interop_conformance.py (TestG12DeterministicRoundtrip class)
**Key Commits:** 
- e2aafb9 (G8 roundtrip tests)
- 311420c (G12 CI conformance suite with deterministic fixtures)

---

### Issue #33: [G9] Claim decision thresholds - formalized policy per claim ID

**Gate:** G9 / Controlled Interop
**Purpose:** Define what evidence threshold is sufficient for claim pass/fail/review per claim type
**Acceptance Criteria:**
- [ ] Decision policy machine-readable (JSON schema)
- [ ] Thresholds documented for each claim type
- [ ] Validator enforces threshold checking
- [ ] Tests verify threshold application

**Status:** ✅ CLOSED
**Closed By:** claim_decision_policy.json + validator tests + claim/evidence integration
**Key Commits:**
- bc4a05c (G9 claim decision thresholds implementation)
- 096ea13 (Integrated into adapter capability conformance)

---

### Issue #34: [G12] Interop conformance suite - CI-executable deterministic validation

**Gate:** G12 / Rigorous Interop
**Purpose:** Demonstrate deterministic roundtrip validation can run automatically in CI
**Acceptance Criteria:**
- [ ] 12+ deterministic roundtrip tests created
- [ ] CI workflow runs tests on every push/PR
- [ ] Conformance report generated (XML + HTML + JSON)
- [ ] PR comments show results
- [ ] All tests passing

**Status:** ✅ CLOSED
**Closed By:** 
- tests/test_g12_interop_conformance.py (12 tests)
- .github/workflows/g12-conformance.yaml (CI job)

**Key Commits:**
- 311420c (G12 CI conformance suite with report artifacts)
- 4bf6917 (Checklist updated, G12 PASS)
- a4c5e40 (Verification summary)

---

## Closure Summary

| Issue | Gate | Title | Status | Evidence | Closed Commit |
|-------|------|-------|--------|----------|---------------|
| #31 | Found. | Governance/anti-drift protocol | ✅ CLOSED | Maintenance protocol in checklist | a4c5e40 |
| #32 | G8 | Roundtrip invariance fixtures | ✅ CLOSED | Deterministic fixtures + tests | 311420c |
| #33 | G9 | Claim decision thresholds | ✅ CLOSED | Policy + validator integration | bc4a05c |
| #34 | G12 | Interop conformance suite CI | ✅ CLOSED | 12 tests + CI workflow | 311420c |

## Standard Issue Templates (For Future Use)

### New Gate Implementation Issue

```markdown
## Title
[Gxx] [ACTION] - [OUTCOME]

## Scope
- Implementing gate requirement: [Gate description]
- Out of scope: [Non-goals]

## Acceptance Criteria
- [ ] Requirement 1 met and tested
- [ ] Requirement 2 met and tested
- [ ] Integration with existing validator
- [ ] Documentation updated
- [ ] All related tests pass

## Test Strategy
- Unit tests: [description]
- Integration tests: [description]
- CI validation: [description]

## Commits
- [commit hash]: [change description]
```

### Evidence/Documentation Issue

```markdown
## Title
[TYPE] [SUBJECT] - [PURPOSE]

## Requirements
- Must demonstrate: [measurable proof]
- Must document: [what should be recorded]
- Must test: [validation approach]

## Success Criteria
- [ ] Evidence is deterministic and reproducible
- [ ] Cross-references are valid
- [ ] Schema compliance verified
- [ ] No silent assumptions
```

## Notes for Future Issues

1. Always include Gate reference (G1-G12 or Foundation)
2. Always specify Acceptance Criteria as a checklist
3. Always record Evidence Required before closing
4. Always link to commits in closure summary
5. Use Status field: OPEN → IN PROGRESS → READY FOR REVIEW → CLOSED
6. Document why it was closed and which commit(s) prove it
