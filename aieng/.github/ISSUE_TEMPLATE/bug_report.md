---
name: Problem or Bug Report
description: Report unexpected behavior, broken functionality, or gate status drift
title: "[PROBLEM] SYMPTOM - EXPECTED BEHAVIOR"
labels: ["bug", "rigorous-interop"]
---

## Issue Type
- [ ] Gate Status Drift (checklist/status became inconsistent)
- [ ] Test Failure (test that was passing now fails)
- [ ] Schema/Validator Issue (data doesn't match schema or validation is wrong)
- [ ] Documentation Bug (docs are unclear/incorrect)
- [ ] Process Break (something in the development workflow is broken)

## Description
Clearly describe the problem and expected behavior.

## Affected Gates
List which gates (G1-G12) are impacted, if any.

## Steps to Reproduce
1. [Step 1]
2. [Step 2]
3. [Step 3]

## Expected Behavior
What should happen instead.

## Actual Behavior
What actually happens.

## Environment
- Python version: [e.g., 3.11]
- OS: [e.g., Windows, Linux]
- Relevant tool/adapter: [if applicable]

## Evidence
- Error message (if any): [paste full error]
- Test output: [paste failing test output]
- Related commit/PR: [if applicable]

## Safety Notes
- [ ] This is a breaking change (affects gate status or validation rules)
- [ ] This is a data loss risk (affects existing .aieng packages)
- [ ] This affects AI safety (claim validation, evidence integrity)

## Resolution
(Filled in when fixed)
- Fixed by commit: [xxxxx]
- Related issue(s): [if any]
- Updated gate status in: [checklist ref]
