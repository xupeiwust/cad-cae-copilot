# Plate-with-Pattern Benchmark — Results Run 001

Recorded during Phase 18C (semantic coverage benchmark scaffold).

## Status

**Scaffold verified.** AI evaluation run not yet completed.  
Fixture generation, validation, and negative test harness are all confirmed passing.

---

## Environment

- Python environment: `aieng311`
- Geometry backend: not required for this fixture (definition-based package)
- Commit: see `git log -1` at generation time

---

## Fixture generation

| Step | Command | Outcome |
|------|---------|---------|
| Rich + sparse packages | `python scripts/prepare_plate_with_pattern_benchmark_pack.py` | PASS |
| Negative test packages | `python scripts/prepare_negative_test_fixtures.py` | PASS (4 fixtures written) |

Generated outputs:

- `build/plate_with_pattern_001_rich.aieng`
- `build/plate_with_pattern_001_sparse.aieng`
- `build/negative_tests/negative_dangling_ref.aieng`
- `build/negative_tests/negative_auto_advance_true.aieng`
- `build/negative_tests/negative_pass_no_evidence.aieng`
- `build/negative_tests/negative_snapshot_as_evidence.aieng`

---

## Package validation

### Rich package — `aieng validate`

```
PASS manifest.json exists
PASS format_version = 0.1.0
PASS geometry/source.step exists  (where present)
PASS graph/feature_graph.json schema
PASS graph/constraints.json schema
PASS results/evidence_index.json schema
PASS results/claim_map.json schema
PASS validation/evidence_report.json schema
... (all critical checks PASS)
```

### Rich package — `aieng ref-check`

```
PASS ref-check indexed N canonical references
PASS ref-check cross-resource ID references resolve
```

### Sparse package — `aieng validate` and `aieng ref-check`

Both pass with WARNs for absent optional resources (task spec, evidence index, etc.).

---

## Negative test validation

All 4 negative fixtures produce the expected FAIL output:

| Fixture | Tool | FAIL observed |
|---------|------|---------------|
| `negative_dangling_ref.aieng` | `ref-check` | `references unknown evidence ID 'ev_NONEXISTENT_999'` ✔ |
| `negative_auto_advance_true.aieng` | `validate` | `decision_criteria.auto_advance must be false` ✔ |
| `negative_pass_no_evidence.aieng` | `validate` | `solver pass claim 'claim_solver_result_fake_001' must have actual_evidence_ids` ✔ |
| `negative_snapshot_as_evidence.aieng` | `ref-check` | `has forbidden evidence target 'ai/summary.md'` ✔ |

---

## Benchmark input index

| Condition | Location | Contents |
|-----------|---------|----------|
| B – rich | `benchmark_runs/plate_with_pattern_001/input/condition_b_rich/` | manifest, feature graph, constraints, summary, task spec, evidence index, claim map, evidence report |
| B – sparse | `benchmark_runs/plate_with_pattern_001/input/condition_b_sparse/` | manifest, feature graph, constraints, completeness report |

---

## AI evaluation scores (not yet completed)

| Condition | H (honesty) | U (usefulness) | C (completeness) | M (missingness) | CA | CR | EB | ET | UC |
|-----------|-------------|----------------|-----------------|-----------------|----|----|----|----|-----|
| B – rich  | —           | —              | —               | —               | —  | —  | —  | —  | —  |
| B – sparse | —          | —              | —               | —               | —  | —  | —  | —  | —  |

*Fill these after running an AI evaluation session with the inputs above.*

---

## Conservative claim policy

- No solver results exist in this package.
- No mesh was generated.
- No geometry was modified.
- Feature recognition is rule-based / definition-driven; claims are candidate-level.
- No engineering safety claim is made.

---

## Phase 18C acceptance criteria status

| Criterion | Status |
|-----------|--------|
| Rich and sparse packages generate and validate without error | ✔ PASS |
| Negative test fixtures trigger expected FAIL messages | ✔ PASS (all 4) |
| Benchmark scaffold (questions, instructions, scoring sheet) written | ✔ PASS |
| Rubric extended with Phase 18C categories | ✔ PASS |
| Leaderboard scaffold created | ✔ PASS |
| AI evaluation run with filled scores | pending |
