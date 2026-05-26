# Negative Test Fixtures — Phase 18C

These packages are **deliberately broken** to verify that `aieng validate` and
`aieng ref-check` produce the correct FAIL messages.  They should **not** be
used as benchmark inputs for AI evaluation.

| Fixture | Expected tool | Expected FAIL fragment |
|---------|--------------|------------------------|
| `negative_dangling_ref.aieng` | `aieng ref-check` | `references unknown evidence ID 'ev_NONEXISTENT_999'` |
| `negative_auto_advance_true.aieng` | `aieng validate` | `decision_criteria.auto_advance must be false` |
| `negative_pass_no_evidence.aieng` | `aieng validate` | `solver pass claim … must have actual_evidence_ids` |
| `negative_snapshot_as_evidence.aieng` | `aieng ref-check` | `has forbidden evidence target 'ai/summary.md'` |

## Source

All fixtures are generated from `build/plate_with_pattern_001_rich.aieng` by
`scripts/prepare_negative_test_fixtures.py`.

## Regeneration

```powershell
$env:PYTHONPATH='src'
python scripts/prepare_negative_test_fixtures.py
```

## Verification commands

```powershell
$env:PYTHONPATH='src'
# 1 – dangling_ref  → ref-check FAIL
python -m aieng.cli ref-check build/negative_tests/negative_dangling_ref.aieng

# 2 – auto_advance_true  → validate FAIL
python -m aieng.cli validate build/negative_tests/negative_auto_advance_true.aieng

# 3 – pass_no_evidence  → validate FAIL
python -m aieng.cli validate build/negative_tests/negative_pass_no_evidence.aieng

# 4 – snapshot_as_evidence  → ref-check FAIL
python -m aieng.cli ref-check build/negative_tests/negative_snapshot_as_evidence.aieng
```

## Design rationale

| # | Defect class | What it tests |
|---|-------------|---------------|
| 1 | Dangling evidence reference | ref-check cross-resource ID resolution |
| 2 | auto_advance policy violation | Validator enforcement of evidence-only policy |
| 3 | Pass claim without evidence | Validator rule: solver/mesh/geometry claims need real evidence |
| 4 | Snapshot path in evidence slot | ref-check forbidden evidence target detection |
