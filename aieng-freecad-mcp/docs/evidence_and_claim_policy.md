# Evidence and Claim Policy

## Core Rule

Execution/import pathways default to evidence/artifact ingestion.

Evidence does not auto-advance claims.

## Modes

Standalone:

- evidence/trace/claim policy may be returned in tool responses
- no `.aieng` persistence

`.aieng`-enhanced (`persist_to_aieng=true`):

- appends to `results/evidence_index.json` and `provenance/tool_trace.json`
- does not modify `results/claim_map.json`

### Evidence / trace persistence failure handling

When evidence or trace writeback fails (disk full, permissions denied, corrupt
JSON), the failure is surfaced as structured metadata rather than swallowed:

- CAD/CAE tools: `persistence` dict contains `error_code: "PERSISTENCE_FAILED"`,
  `persisted: false`, and `error` with the human-readable message.
- Patch execution: `PatchExecutionSummary.primary_error_code` is set to
  `"PERSISTENCE_FAILED"` and the error is appended to `summary.errors`.
- The tool response `status` remains what the underlying operation produced
  (e.g., `"success"`), because the CAD/CAE operation itself succeeded; only
  the writeback failed. This preserves the separation between execution and
  persistence layers.

## Four Layers (must stay separate)

1. Artifact presence
2. Parsed deterministic facts
3. Claim linkage (possibly relevant evidence)
4. Explicit claim status update

Examples of non-implication:

- mesh exists != mesh accepted
- solver ran != design validated
- metric exists != claim passed
- modified geometry exists != safe design

## Claim Status Semantics

- `unsupported`: not enough evidence (not false)
- `fail`: evidence contradicts criteria
- `pass`: evidence satisfies criteria

## Global Tool Result Requirement

All non-claim-update mutating tools must return:

```json
{
  "claim_policy": {
    "claims_advanced": false,
    "requires_explicit_update_claim": true
  }
}
```

## Patch Evidence (`aieng_execute_patch`)

- records execution evidence, not engineering validation
- preserves source artifacts
- records patch/step metadata and artifact metadata
- sets `claims_advanced: false`

## Optional CAD->CAE Orchestration Evidence

`aieng_run_cad_to_cae_workflow` is optional and explicit.

- CAD and CAE remain independent first-class capabilities.
- no automatic chaining from CAD to CAE to claims.
- default solver behavior remains conservative.

Required workflow metadata includes workflow id, patch id, analysis type, artifact path, step flags, producer kind, `engineering_validation: false`, and `claims_advanced: false`.

Surrogate evidence must explicitly warn that it is not solver validation evidence.

## Post-Processing Evidence (`aieng_postprocess_results`)

- extracts deterministic metrics and exports artifacts
- does not validate claims
- records missing metrics as `not_found`
- may return `unsupported` (for example VTK without field data)

## Explicit Claim Update (`aieng_update_claim`)

Only this tool may modify `claim_map.json`.

- evaluate mode: deterministic criteria evaluation
- manual mode: explicit status + rationale
- dry-run: no writes
- trace appended on successful non-dry-run updates

All other tools remain claim-map immutable.

### Machine-decidable claim update failures

When claim update is rejected or fails, the response includes `primary_error_code`:

| Code | Layer | When it occurs |
|---|---|---|
| `MISSING_PACKAGE_PATH` | prerequisite | package_path not a directory |
| `CLAIM_NOT_FOUND` | prerequisite | claim_id not in claim_map.json |
| `MISSING_EVIDENCE_IDS` | input validation | evidence_ids is empty |
| `EVIDENCE_NOT_FOUND` | prerequisite | evidence_ids not in evidence_index.json |
| `MISSING_DECISION_CRITERIA` | input validation | evaluate mode without criteria |
| `MISSING_MANUAL_FIELDS` | input validation | manual mode without rationale or requested_status |
| `UNKNOWN_MODE` | input validation | mode is neither evaluate nor manual |
| `PERSISTENCE_FAILED` | persistence | atomic write to claim_map.json or tool_trace.json failed |

Claim evaluation outcomes (`pass`, `fail`, `unsupported`) are **not** error codes.
They are normal status values returned with `status="success"`.

### Unified error code consumption (cross-layer)

Different result shapes expose error semantics in different fields:
- Claim/patch summaries expose `primary_error_code` directly.
- CAD/CAE tool results expose `failure_mode` (structured) and may auto-derive `primary_error_code`.
- CAE legacy errors expose `error_code` in addition to `failure_mode`.
- Persistence failures expose `error_code` inside the `persistence` dict.

Consumers should not hard-code per-tool field lookups. Use the unified resolution
function `derive_primary_error_code(...)` which implements the stable priority:

1. `primary_error_code` if present
2. `failure_mode.mode` mapped to a normalized code
3. Legacy `error_code` mapped to a normalized code
4. `None` if no error

This keeps claim policy, evidence, and execution failure handling consistent
without requiring consumers to know which tool family produced the result.

## Reference Mapping

Reference mapping is traceability evidence, not validation.

After geometry changes, affected references/targets are marked `needs_review`. No auto-transfer guarantees and no claim advancement.

## Audit

`aieng_generate_audit_report` writes audit outputs and does not mutate claim/evidence/trace source files.

It summarizes evidence/trace/reference/claim state and flags claim-discipline violations.
