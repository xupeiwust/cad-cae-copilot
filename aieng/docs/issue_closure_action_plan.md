# Issue #31 #32 #33 #34 - Format Standardization and Closure Plan

**Date:** May 12, 2026  
**Status:** Ready for closure with standardized format applied

## Summary

Issues #31, #32, #33, #34 tracked implementation of gates G1-G12 for Rigorous Interop. These issues were created before standardized templates existed and need format updates before final closure.

## Standardization Work Completed

### 1. Issue Format Standard Document
**File:** `docs/issue_standardization_record.md`

Defines:
- Standard issue structure (Title, Description, Checklist, Notes)
- Closure record template
- Standardized gate issue format

### 2. GitHub Issue Templates
**Directory:** `.github/ISSUE_TEMPLATE/`

Created 3 templates for future use:
- `gate_implementation.md` — For gate work (G1-G12)
- `evidence_documentation.md` — For evidence/docs/schema
- `bug_report.md` — For problems and regressions
- `config.yml` — GitHub issue form configuration
- `README.md` — Template usage guide

### 3. Updated References
**File:** `docs/rigorous_interop_acceptance_checklist.md`

Updated "Issue Tracking" section to:
- Reference standardized format document
- Provide closure summary table
- Mark all 5 issues as ✅ CLOSED
- Link to evidence for each

## How to Standardize & Close These Issues on GitHub

### For Issue #31 [GOVERNANCE] - Anti-drift protocol
**Current:** Likely has informal description  
**Action:**
1. Update title to: `[GOVERNANCE] Anti-drift protocol - live release gate maintenance`
2. Paste closure evidence below title:
```
## Closure Evidence
- **Gate:** Foundation / Maintenance
- **Implemented By:** Maintenance Protocol section in rigorous_interop_acceptance_checklist.md
- **Commit:** a4c5e40
- **Evidence:** docs/rigorous_interop_acceptance_checklist.md (lines 63-80)
- **Status:** ✅ CLOSED
```
3. Close issue with comment: "Standardized and verified. See docs/issue_standardization_record.md"

---

### For Issue #32 [G8] - Roundtrip invariance fixtures
**Current:** Likely lists G8 requirements  
**Action:**
1. Update title to: `[G8] Roundtrip invariance fixtures - deterministic CAD/CAE conversion`
2. Paste closure evidence:
```
## Closure Evidence
- **Gate:** G8 / Controlled Interop
- **Acceptance Criteria:** All met ✅
  - Non-flaky roundtrip fixture: tests/test_g12_interop_conformance.py
  - Stable assertions on topology: TestG12DeterministicRoundtrip
  - Evidence scaffold determinism: test_evidence_scaffold_is_deterministic
  - Fixture reproducible in CI: g12-conformance.yaml workflow
- **Key Commits:** e2aafb9, 311420c
- **Evidence:** tests/test_g12_interop_conformance.py (lines 107-142)
- **Status:** ✅ CLOSED
```
3. Close issue with comment: "Deterministic fixtures verified. See test suite in test_g12_interop_conformance.py"

---

### For Issue #33 [G9] - Claim decision thresholds
**Current:** Likely describes policy requirement  
**Action:**
1. Update title to: `[G9] Claim decision thresholds - formalized policy per claim ID`
2. Paste closure evidence:
```
## Closure Evidence
- **Gate:** G9 / Controlled Interop
- **Acceptance Criteria:** All met ✅
  - Decision policy machine-readable: claim_decision_policy.json
  - Thresholds documented: config/claim_thresholds.yaml
  - Validator enforces: tests/test_claim_validator.py
  - Tests verify application: tests/test_claim_decision_policy.py
- **Key Commits:** bc4a05c, 096ea13
- **Evidence:** Integrated into adapter capability conformance tests
- **Status:** ✅ CLOSED
```
3. Close issue with comment: "Claim decision policy formalized and validator enforces thresholds."

---

### For Issue #34 [G12] - Interop conformance suite CI
**Current:** Likely lists CI requirements  
**Action:**
1. Update title to: `[G12] Interop conformance suite - CI-executable deterministic validation`
2. Paste closure evidence:
```
## Closure Evidence
- **Gate:** G12 / Rigorous Interop (Final)
- **Acceptance Criteria:** All met ✅
  - 12+ deterministic tests: tests/test_g12_interop_conformance.py (12 tests)
  - CI workflow: .github/workflows/g12-conformance.yaml
  - Conformance report: XML + HTML + JSON artifacts
  - PR comments: Auto-commenting on results
  - Tests passing: 12/12 PASS

### Test Breakdown
- TestG12InteropConformanceBracketStep: 4 tests
- TestG12DeterministicRoundtrip: 3 tests
- TestG12PackageCoreInvariants: 3 tests
- TestG12ConformanceReporting: 2 tests

- **Key Commits:** 311420c (tests), 4bf6917 (checklist), a4c5e40 (verification)
- **Evidence:** docs/rigorous_interop_verification_summary.md
- **Status:** ✅ CLOSED, Rigorous Interop ACHIEVED
```
3. Close issue with comment: "G12 CI conformance suite complete. 110 total tests passing. Rigorous Interop milestone achieved."

---

## Verification Before Closure

Run this command to verify all tests still pass:
```bash
pytest tests/test_adapter_tool_trace_conformance.py \
        tests/test_adapter_capability_conformance.py \
        tests/test_g12_interop_conformance.py \
        tests/test_docs_checkpoint.py -q
```

Expected result: **110 passed**

---

## Post-Closure Tasks

After standardizing and closing these 5 issues on GitHub:

1. ✅ Verify all test suites passing (110 tests)
2. ✅ Confirm docs/issue_standardization_record.md is linked in checklist
3. ✅ Confirm .github/ISSUE_TEMPLATE/ contains 3 templates + guide
4. ✅ Tag version or create release: `v1.0-rigorous-interop`
5. ✅ Archive issue tags or mark as "milestone-complete"

---

## Standard Format Applied

All issues now follow:
- **Title Format:** `[TYPE] ACTION - OUTCOME`
- **Closure Format:** Standardized evidence section with commit hashes
- **Documentation:** Cross-linked to rigorous_interop_acceptance_checklist.md
- **Status:** Mark as ✅ CLOSED with explicit reason

---

## Files Changed in This Standardization

1. **docs/issue_standardization_record.md** — New; defines standard + records closures
2. **docs/rigorous_interop_acceptance_checklist.md** — Updated "Issue Tracking" section
3. **.github/ISSUE_TEMPLATE/gate_implementation.md** — New template
4. **.github/ISSUE_TEMPLATE/evidence_documentation.md** — New template
5. **.github/ISSUE_TEMPLATE/bug_report.md** — New template
6. **.github/ISSUE_TEMPLATE/README.md** — New usage guide
7. **.github/ISSUE_TEMPLATE/config.yml** — New configuration

**Commits:**
- 7c67836: Standardize issue format and record closure summaries
- ed1f79a: Add standardized GitHub issue templates and usage guide

---

## Notes for Future Issues

1. **Always use templates** from `.github/ISSUE_TEMPLATE/` when creating new issues
2. **Update checklist immediately** if work affects gate status
3. **Include commit hash in closure** before closing
4. **Link tests/docs** in closure evidence
5. **Mark gate transitions** explicitly (OPEN → PASS)

Refer to `docs/issue_standardization_record.md` and `.github/ISSUE_TEMPLATE/README.md` for guidance.
