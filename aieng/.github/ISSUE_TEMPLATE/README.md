# GitHub Issue Templates - Usage Guide

This directory contains standardized templates for issues related to the Rigorous Interop project.

## Available Templates

### 1. **gate_implementation.md**
Use this for implementing acceptance gates (G1-G12).

**When to use:**
- Adding functionality to satisfy a specific gate requirement
- Creating tests to verify gate compliance
- Implementing validator rules or schema changes tied to a gate

**Required fields:**
- Gate reference (e.g., G7)
- Acceptance criteria (checklist)
- Test strategy
- Evidence required before closing

**Closure requirement:**
Must include commit hash(es) and link to passing tests.

---

### 2. **evidence_documentation.md**
Use this for documentation, evidence infrastructure, or schema work.

**When to use:**
- Adding new evidence types or claim definitions
- Enhancing validator or schema
- Creating test fixtures or infrastructure
- Documenting process or governance

**Required fields:**
- Issue type (select from list)
- Requirements (what must be demonstrated)
- Success criteria (checklist)

**Closure requirement:**
Must verify deterministic behavior, no broken references, schema compliance.

---

### 3. **bug_report.md**
Use this for problems, regressions, or gate status drift.

**When to use:**
- Test failures or broken functionality
- Checklist/documentation became inconsistent
- Gate status incorrectly marked
- Data validation issues

**Required fields:**
- Issue type (select from list)
- Steps to reproduce
- Expected vs actual behavior
- Safety flags (breaking change? data loss? safety concern?)

**Closure requirement:**
Must include fix commit and updated gate status if affected.

---

## Issue Format Standard

All issues should follow this structure:

```
## Header Section
- Clear, specific title with [TYPE] prefix
- Description of problem/objective
- Link to relevant gate (G1-G12) if applicable

## Work Section
- Acceptance criteria as checklist
- Test strategy or validation approach
- Related documentation or schemas

## Closure Section
- Commit hash(es)
- Link to evidence (tests, validation, docs)
- Updated checklist reference
```

---

## Guidelines for Issue Authors

1. **Always link to gates:** Include which acceptance gate(s) this relates to.
2. **Checklists are binding:** Once opened, acceptance criteria checklist items are expectations.
3. **Close with evidence:** Do not close without linking to commit(s) and test results.
4. **Update checklist:** If this issue changes gate status, update rigorous_interop_acceptance_checklist.md.
5. **Safety first:** Flag breaking changes, data loss risks, and safety concerns explicitly.
6. **Be specific:** "Fix bug" is not acceptable. "Fix validator not catching missing face_id in topology_map.json" is good.

---

## Issue Lifecycle

```
OPEN (template filled, work starting)
  ↓
IN PROGRESS (actively being worked on)
  ↓
READY FOR REVIEW (tests passing, PR created)
  ↓
CLOSED (merged, evidence recorded in checklist)
```

---

## Typical Issue Closure Record

When closing an issue, update its description or add a comment with:

```
## Closure Evidence
- **Commit:** 7c67836
- **Tests:** All 12 tests passing in CI (link)
- **Documentation:** Updated rigorous_interop_acceptance_checklist.md
- **Impact:** Gate G12 now PASS; Rigorous Interop achieved
```

---

## Labels

Use these labels consistently:

- `gate-implementation` — Implementing a specific gate
- `rigorous-interop` — Related to Rigorous Interop milestone
- `documentation` — Docs, schemas, or governance
- `bug` — Regression or unexpected behavior
- `evidence` — Evidence infrastructure or validation
- `critical` — Blocks milestone or affects safety
- `process` — Development workflow or tooling

---

## Examples

### Example 1: Gate Implementation Issue

```markdown
[G7] Implement CAD writeback executor - enable deterministic geometry updates

**Gate:** G7 - At least one CAD writeback path is executable
**Maturity:** Rigorous Interop
**Acceptance Criteria:**
- [ ] Writeback path implemented for at least STEP
- [ ] Integration tests verify external tool integration
- [ ] Guardrails enforce known-only updates
- [ ] All existing tests passing
- [ ] Docs updated with writeback contract

**Test Strategy:**
- Unit tests for writeback operations
- Integration test with real STEP roundtrip
- Validator checks for semantic drift

**Evidence Required:**
- Commit hash
- Link to integration test (test_cad_writeback_integration.py)
- Updated schema if any changes
```

### Example 2: Documentation Issue

```markdown
[EVIDENCE] Record solver integration policy - define evidence import contract

**Issue Type:** Evidence Documentation

**Purpose:** Document how solver evidence (results/) is imported and validated

**Requirements:**
- Must demonstrate deterministic numeric extraction
- Must document unknown handling policy
- Must test evidence validator

**Success Criteria:**
- [ ] Policy documented in ai/solver_evidence_policy.md
- [ ] Schema validator tests for missing/unknown markers
- [ ] Determinism tests pass
- [ ] Cross-referenced in checklist
```

### Example 3: Bug Report

```markdown
[PROBLEM] Validator not catching missing evidence references - G9 claim links broken

**Issue Type:** Schema/Validator Issue
**Affected Gates:** G9, G5

**Steps to Reproduce:**
1. Create claim with evidence_id: "evidence_x"
2. Do not create evidence_x in results/evidence_index.json
3. Run validator

**Expected:** Validator errors
**Actual:** Validator passes silently

**Safety:** Yes, this allows ghost claims

**Fix:** Add validator rule for claim → evidence cross-ref
```

---

## Maintenance

This template directory and guide are maintained as part of the rigorous interop process. Update these templates if:

1. New gates are added (G13+)
2. Process changes require new issue types
3. Closure evidence requirements change
4. Labels or categories are updated

Always update [issue_standardization_record.md](../../docs/issue_standardization_record.md) when changing issue standards.
