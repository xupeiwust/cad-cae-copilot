# Acceptance Tests

## Global Acceptance Rules

Every mutating MCP tool must prove:

- input is schema-validated
- unsupported input is rejected explicitly
- source artifacts are not modified in place
- outputs are written to approved package or workspace paths
- evidence is written when artifacts or parsed observations are produced
- tool trace is written for external execution
- claims are not advanced automatically
- failures are visible and auditable

## Required Tests for Every Tool

- valid input
- invalid input
- missing file
- unsupported operation
- path traversal rejection
- deterministic output where possible
- structured error result

## CAD Modification Acceptance Tests

CAD modification tools must test:

- successful executable parameter edit
- semantic-only feature rejection
- missing feature rejection
- missing parameter rejection
- protected-region rejection
- unsupported writeback strategy rejection
- failed FreeCAD recompute
- failed export
- modified artifact written to new path
- source artifact immutability
- evidence entry written
- tool trace entry written
- `claims_advanced=false`

## CAE Acceptance Tests

CAE tools must test:

- missing solver
- missing mesher
- failed mesh generation
- failed solver execution
- deck export success
- result metric extraction success
- result metric `not_found`
- evidence writeback
- tool trace writeback
- no validation claim auto-advance

## Claim Policy Acceptance Tests

Claim update tools must test:

- claim update requires claim ID
- claim update requires evidence IDs
- claim update requires trace ID
- unsupported stays unsupported without evidence
- pass requires decision criteria satisfaction
- fail requires evidence violation
- non-claim tools cannot update claim status

## First Milestone Acceptance Test

Milestone: FreeCAD MCP can safely inspect and regenerate a parametric bracket.

### Automated driver

Run the repeatable acceptance driver:

```bash
python scripts/run_milestone1_acceptance.py
python scripts/run_milestone1_acceptance.py --json > milestone1_report.json
```

#### Dry-run mode

The driver supports `--dry-run` for environments without FreeCAD (e.g., CI):

```bash
python scripts/run_milestone1_acceptance.py --dry-run
python scripts/run_milestone1_acceptance.py --dry-run --json > milestone1_report.json
```

In dry-run mode:
- FreeCAD-dependent checks (2, 3, 5, 6, 7) are **stubbed** with canned success responses.
- Real file I/O is still exercised against a temporary copy of the fixture package.
- Check 5 calls `execute_patch_plan(..., dry_run=True, persist_to_aieng=True)`, so evidence and trace entries are **actually written** to the temp package.
- Check 11 performs a structural package validation instead of invoking the `aieng` CLI.
- All 11 checks report `pass`, producing an overall `pass` status.

This mode validates the acceptance driver's logic, the `.aieng` bridge, persistence, and claim discipline without requiring FreeCAD or the `aieng` CLI.

### Expected output and pass criteria

The driver produces structured JSON with these top-level fields:

| Field | Expected |
|---|---|
| `status` | `pass` when all checks pass; `partial` when some are skipped/unsupported; `fail` when any check fails |
| `checks` | 11 items, one per acceptance criterion below |
| `artifacts_written` | Paths to exported `.FCStd` and `.step` files (only when FreeCAD available) |
| `evidence_ids` | Non-empty list when evidence exists |
| `trace_ids` | Non-empty list when trace exists |
| `claims_advanced` | Must be `false` |
| `warnings` | FreeCAD-absence warnings are expected and acceptable |
| `errors` | Must be empty for a clean pass |

Per-check status semantics:
- `pass` — criterion satisfied for this run
- `skipped` — criterion requires FreeCAD which is not present (acceptable in CI without FreeCAD)
- `unsupported` — criterion cannot be verified in the current environment:
  - checks 8/9 return `unsupported` when no evidence/trace entries were produced in this run
    (e.g. FreeCAD absent so no patch execution occurred)
  - check 11 returns `unsupported` when the `aieng` CLI is not installed
- `fail` — criterion violated (this makes overall status `fail`)

In `--dry-run` mode, no checks are skipped or unsupported; all 11 report `pass` because FreeCAD calls are stubbed and check 11 uses structural validation.

Check-specific constraints:
- check 5 does not count as pass unless the parameter edit was actually executed
  (not merely parsed).
- checks 8/9/10/11 inspect the **temporary run directory** (`tmp_dir/package`),
  never the static fixture path.
- check 8 `pass` requires `evidence_ids` non-empty.
- check 9 `pass` requires `trace_ids` non-empty.

### Acceptance criteria

1. MCP starts and reports FreeCAD capabilities.
2. MCP opens an FCStd fixture in headless FreeCAD.
3. MCP extracts object tree and editable parameters.
4. MCP reads a `.aieng` package feature graph.
5. MCP applies one allowed parameter edit.
6. MCP recomputes the FreeCAD document.
7. MCP exports modified FCStd and STEP artifacts.
8. MCP records an evidence entry.
9. MCP records a tool trace entry.
10. MCP does not advance claims automatically.
11. `aieng validate` passes after writeback.
