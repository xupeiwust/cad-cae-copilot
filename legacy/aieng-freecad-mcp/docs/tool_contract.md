# MCP Tool Contract

## Principle

Prefer narrow, auditable tools over broad catch-all tools.

Do not expose arbitrary Python/shell execution as normal public tools.

## Required Per-Tool Spec Fields

- tool name and purpose
- input/output schema
- allowed reads/writes
- disallowed side effects
- claim policy
- failure modes
- required tests

## Shared Optional Request Fields

Mutating tools may accept:

```json
{
  "package_path": "/path/to/package.aieng",
  "persist_to_aieng": false,
  "target_feature_id": null
}
```

## Standard Mutating Result Shape

All mutating tools return a structured result including:

- `status`: `success | failed | unsupported | rejected`
- `operation`, `inputs`, `outputs`, `artifacts_written`
- `evidence`, `trace`
- `warnings`, `unsupported`, `errors`
- `claim_policy` with:
  - `claims_advanced: false`
  - `requires_explicit_update_claim: true`

When persistence succeeds, include `persistence` metadata (`evidence_id`, `trace_id`, `paths_written`).

## Operation Preview

Every mutating tool may return an `OperationPreview` in its result (`preview` field).
The preview tells the caller what would happen before anything is actually done.

### OperationPreview fields

| Field | Meaning |
|---|---|
| `operation_name` | Tool being previewed |
| `would_write_artifacts` | Path templates for files that would be written |
| `would_update_evidence` | True if evidence_index.json would be appended |
| `would_update_traces` | True if tool_trace.jsonl would be appended |
| `would_touch_claims` | True only if claim_map.json could be modified |
| `guard_checks_required` | Package/feature/claim checks that would run |
| `unavailable_runtime_blocks` | Missing runtimes that would prevent execution |
| `expected_duration_estimate` | `fast` / `medium` / `slow` / `blocked` |
| `warnings` | Preview-level warnings (e.g. topology change risk) |

### preview_operation tool

Call `preview_operation(operation_name, inputs)` to get an `OperationPreview`
without executing the tool. This is a true dry-run: no files, no CAD, no claims.

```json
{
  "operation_name": "cad_export_step",
  "inputs": {"file_path": "/tmp/out.step"}
}
```

Dry-run support levels declared in the tool registry:
- `full` — preview is fully accurate without side effects
- `partial` — preview can infer most effects, but some depend on runtime state
- `none` — tool cannot meaningfully preview without doing the work

## Failure Mode Taxonomy

All tool errors should map to a standard `FailureMode` so auditors and
orchestrators can reason about failures consistently.

### FailureMode values

| Mode | Meaning |
|---|---|
| `missing_input` | Required parameter missing or empty |
| `missing_artifact` | Expected file, document, or object not found |
| `missing_runtime` | Required runtime (FreeCAD/FEM/mesher/solver) unavailable |
| `solver_unavailable` | Solver backend not installed or unreachable |
| `mesh_failed` | Mesh generation failed or produced invalid output |
| `guard_rejected` | Rejected by `.aieng` guard checks |
| `semantic_only_rejected` | Target feature is semantic-only, not CAD-editable |
| `protected_region_violated` | Operation would modify a protected region |
| `recompute_failed` | FreeCAD document recompute failed after modification |
| `export_failed` | Artifact export (STEP/FCStd/mesh/deck) failed |
| `not_found` | Requested resource not found |
| `ambiguous` | Request matched multiple resources |
| `needs_review` | Result or mapping requires human review |
| `unknown` | Unclassified error |

### Embedding failure_mode in results

`StandardToolResult`, `CadToolResponse`, and `CaeBaseResponse` all carry an
optional `failure_mode: FailureDetail` field with:
- `mode` — one of the `FailureMode` values above
- `message` — human-readable explanation
- `context` — optional key/value context

### primary_error_code for evidence / trace / claim paths

In addition to `failure_mode`, the following result shapes carry an optional
`primary_error_code: string | null` field:

- `ClaimUpdateSummary` — returned by `aieng_update_claim`
- `PatchExecutionSummary` — returned by `aieng_execute_patch`
- `StandardToolResult`, `CadToolResponse`, `CaeBaseResponse` — auto-derived from `failure_mode`
- `persistence` metadata dict — attached to CAD/CAE tool responses when
  evidence/trace writeback fails

| Error code | Meaning |
|---|---|
| `MISSING_PACKAGE_PATH` | package_path does not exist or is not a directory |
| `MISSING_EVIDENCE_IDS` | claim update requires at least one evidence_id |
| `EVIDENCE_NOT_FOUND` | one or more requested evidence_ids were not found in evidence_index.json |
| `CLAIM_NOT_FOUND` | the requested claim_id does not exist in claim_map.json |
| `MISSING_DECISION_CRITERIA` | evaluate mode requires at least one decision_criterion |
| `MISSING_MANUAL_FIELDS` | manual mode requires requested_status and rationale |
| `UNKNOWN_MODE` | the claim update mode is not recognized |
| `PERSISTENCE_FAILED` | writing evidence_index, tool_trace, or claim_map failed (disk, permissions, or corrupt JSON) |
| `POLICY_VIOLATION` | the operation violates a package-level policy (e.g., persist without package_path, guard rejection, protected region, semantic-only) |
| `INVALID_INPUT` | required parameter missing or empty (mapped from `failure_mode.missing_input`) |
| `MISSING_ARTIFACT` | expected file, document, or object not found (mapped from `failure_mode.missing_artifact`) |
| `MISSING_RUNTIME` | required runtime unavailable (mapped from `failure_mode.missing_runtime`) |
| `SOLVER_UNAVAILABLE` | solver backend not installed or reachable (mapped from `failure_mode.solver_unavailable`) |
| `MESH_FAILED` | mesh generation failed (mapped from `failure_mode.mesh_failed`) |
| `EXECUTION_FAILED` | execution failure such as recompute or backend crash (mapped from `failure_mode.recompute_failed`) |
| `EXPORT_FAILED` | artifact export failed (mapped from `failure_mode.export_failed`) |
| `NOT_FOUND` | requested resource not found (mapped from `failure_mode.not_found`) |
| `AMBIGUOUS` | request matched multiple resources (mapped from `failure_mode.ambiguous`) |
| `NEEDS_REVIEW` | result requires human review (mapped from `failure_mode.needs_review`) |
| `unknown` | unclassified error (fallback when no specific code applies) |
| `INTERNAL_ERROR` | internal CAE error (mapped from legacy `error_code="internal_error"`) |

Rules:
- `primary_error_code` is `null` when the operation succeeds.
- It is populated on `rejected` and `failed` statuses.
- It does **not** replace `errors` (human-readable strings); both fields are present.
- Backward compatibility: old consumers that ignore `primary_error_code` continue to work.

### Unified consumer reading strategy

Because the codebase evolved incrementally, different result shapes expose error
codes in slightly different places.  Consumers should use this **stable priority
order** instead of inspecting result types:

1. **Read `primary_error_code`** directly from the result object.
2. **If null**, derive from `failure_mode.mode` using `map_failure_mode_to_error_code`.
3. **If still null**, read `legacy_error_code` (e.g., `persistence.error_code` or CAE `error_code`).
4. **If still null**, there is no machine-decidable error code for this result.

This is encapsulated in `derive_primary_error_code(...)`:

```python
from freecad_mcp.contracts.failure_mode import derive_primary_error_code

code = derive_primary_error_code(
    primary_error_code=response.get("primary_error_code"),
    failure_mode=response.get("failure_mode"),
    legacy_error_code=response.get("persistence", {}).get("error_code"),
)
```

#### Examples

**Example 1 — Claim update rejected for missing evidence:**
```json
{
  "status": "rejected",
  "primary_error_code": "EVIDENCE_NOT_FOUND",
  "errors": ["Evidence IDs not found: ['ev_missing']"]
}
```
Consumer reads `primary_error_code` directly.

**Example 2 — CAD export failed with failure_mode:**
```json
{
  "status": "failed",
  "failure_mode": {"mode": "export_failed", "message": "STEP export failed"},
  "primary_error_code": "EXPORT_FAILED",
  "errors": ["export_failed: STEP export failed"]
}
```
Consumer reads `primary_error_code` (auto-derived from `failure_mode`).

**Example 3 — CAE backend error where failure_mode is "unknown":**
```json
{
  "status": "failed",
  "error_code": "internal_error",
  "failure_mode": {"mode": "unknown", "message": "..."},
  "primary_error_code": "INTERNAL_ERROR",
  "errors": ["..."]
}
```
Consumer reads `primary_error_code`; it was derived from the legacy `error_code`
because `failure_mode` mapped to `"unknown"`.

**Example 4 — CAD persistence failure (operation succeeded, writeback failed):**
```json
{
  "status": "success",
  "persistence": {
    "error_code": "PERSISTENCE_FAILED",
    "persisted": false,
    "error": "disk full"
  }
}
```
Consumer falls back to `persistence.error_code` because `primary_error_code` is
null on the result object itself.

**Example 5 — Success, no error:**
```json
{
  "status": "success",
  "primary_error_code": null,
  "failure_mode": null
}
```
Consumer gets `None` from `derive_primary_error_code`.

The audit report includes a **failure mode taxonomy coverage** section that
counts how many evidence/trace entries carry a standard `failure_mode`.

### Usage example

```python
from freecad_mcp.contracts.failure_mode import classify_exception, FailureDetail

try:
    ...
except Exception as exc:
    failure = classify_exception(exc)
    response = CadToolResponse(
        status="failed",
        operation="cad_export_step",
        failure_mode=failure,
        errors=[failure.message],
    )
```

## Boundary Rules Across Tools

- Evidence is not a claim.
- Only explicit claim update may modify `claim_map.json`.
- Capability inspection remains read-only and planning-neutral.
- CAD->CAE orchestration is optional and explicit.
- Unsupported/missing/not_found/needs_review states must stay explicit.

## Tool Families

### Read-Only Context and Inspection

- `aieng_inspect_context`: package presence/resources; no writes.
- `aieng_inspect_capabilities`: read-only, planning-neutral capability/gap report.
- `aieng_plan_capabilities`: deprecated alias of `aieng_inspect_capabilities`.
- `freecad_runtime_capabilities`: read-only runtime detection for FreeCAD/FEM/meshers/solver.

### Patch and Optional Orchestration

- `aieng_parse_patch`: validate patch only; no execution.
- `aieng_execute_patch`: guarded execution, optional artifact export/persistence, never claim-map mutation.
- `aieng_run_cad_to_cae_workflow`: optional explicit orchestrator; not default; no auto-claim advancement.

Required patch/orchestration evidence discipline:

- include artifact metadata (`modified_step`/`modified_fcstd`, source preserved)
- include producer kind (`freecad`, `freecad_fem`, `surrogate`)
- include `claims_advanced: false`
- include `engineering_validation: false` unless explicit real validation path is established
- surrogate results include warning that they are not solver validation evidence

### Post-Processing

- `aieng_postprocess_results`: deterministic metric extraction + artifact export.
- Does not validate claims.
- Missing fields are reported as `not_found`.
- VTK without field data is `unsupported` (not hidden failure).

### Claim Update

- `aieng_update_claim` is the only claim-map mutator.
- Supports evaluate/manual modes and dry-run.
- Requires evidence IDs and valid claim target.
- Preserves non-target claims.

Claim status semantics:

- `unsupported`: insufficient evidence (not false)
- `fail`: evidence contradicts criteria
- `pass`: evidence satisfies criteria

### Reference and Audit

- `aieng_get_reference_map`: read-only retrieval.
- `aieng_build_reference_map`: build/persist mapping; no claim advancement.
- `aieng_mark_references_needing_review`: marks affected refs; no claim advancement.
- `aieng_generate_audit_report`: deterministic report writer; must not mutate claim/evidence/trace source files.

## Example Guarded Mutation Expectations

A guarded parameter edit tool must:

- verify feature/parameter/executable metadata
- enforce package guards (including semantic-only/protected restrictions)
- recompute/export safely
- preserve source artifacts
- emit evidence and trace
- keep `claims_advanced: false`

Required tests include valid path, invalid path, guard rejection, recompute/export failure, writeback, and claim immutability.

## Tool Transparency Registry

All MCP tools are catalogued in a machine-readable registry (`freecad_mcp.tool_registry`).
Each entry declares:

| Field | Meaning |
|---|---|
| `tool_name` | Exact MCP tool name |
| `category` | `cad` / `cae` / `reference` / `evidence` / `claim` / `runtime` / `audit` / `orchestration` |
| `purpose` | One-sentence description |
| `required_inputs` / `optional_inputs` | Parameter names |
| `side_effects` | Files written, indices updated, recomputes triggered |
| `mutates_cad` | True if the tool may change the CAD model |
| `mutates_package` | True if the tool may write into the `.aieng` package |
| `may_update_claim_map` | True **only** for `aieng_update_claim` |
| `runtime_requirements` | `freecad`, `fem`, `mesher`, `solver`, `none` |
| `dry_run_support` | `full` / `partial` / `none` |
| `claim_policy` | Default `claims_advanced` and `requires_explicit_update_claim` |

### Querying the registry

Use the read-only MCP tool `aieng_tool_registry_query`:

```json
{
  "category": "cad",
  "keyword": "export",
  "mutability": "none"
}
```

`mutability` filter values:
- `cad` → tools that mutate CAD
- `package` → tools that mutate the `.aieng` package
- `claim_map` → tools that may update `claim_map.json`
- `none` → read-only tools
- `any` → any mutating tool

The registry is the source of truth for `aieng_inspect_capabilities`, audit reports,
and any future orchestration planners. When a new tool is added, its registry entry
must be added to `src/freecad_mcp/tool_registry.py` before the tool is considered
fully integrated.
