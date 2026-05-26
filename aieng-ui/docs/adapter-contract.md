# AIENG Adapter Contract

Status: **v0.34**
Last updated: **2026-05-19**

This document formalizes the safety contract between AIENG and external CAD/CAE tools. It complements the code in `backend/app/external_adapters.py`.

## Core types

### `ExternalToolCapability`

Static manifest for a single adapter operation. Fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Namespaced ID, e.g. `cad.inspect`, `solver.run` |
| `label` | `str` | Human-readable label |
| `category` | `cad` / `mesh` / `solver` / `postprocess` / `report` | Tool category |
| `mutates_package` | `bool` | Writes to `.aieng` ZIP |
| `mutates_external_model` | `bool` | Changes CAD/CAE model outside package |
| `runs_external_process` | `bool` | Spawns subprocess |
| `expensive` | `bool` | Long-running or resource-heavy |
| `requires_approval` | `bool` | Must await explicit approval |
| `input_artifacts` | `list[str]` | Expected input paths in package |
| `output_artifacts` | `list[str]` | Expected output paths in package |
| `stale_artifacts_on_success` | `list[str]` | Paths to mark stale after success |
| `claim_advancement` | `"none"` | Always `"none"` |

**Invariants (enforced by Pydantic validator):**
- Mutating, expensive, solver, and external-mesh capabilities **must** require approval.
- CAD mutations **must** declare stale artifacts on success.

### `AdapterPreflightResult`

Read-only readiness response before any execution:

| Field | Type | Meaning |
|---|---|---|
| `ok` | `bool` | Preflight parsed successfully |
| `status` | `ready` / `partial` / `unavailable` | Readiness level |
| `adapter_id` | `str` | Adapter identifier |
| `capabilities` | `list[ExternalToolCapability]` | Supported operations |
| `missing_dependencies` | `list[str]` | What's missing |
| `checked_paths` | `list[str]` | Paths inspected |
| `claim_boundary` | `str` | Safety disclaimer |

**Invariants:**
- `unavailable` preflight **must** name missing dependencies.
- `ready` preflight **must not** list missing dependencies.

### `AdapterExecutionResult`

Outcome after an approval-gated operation:

| Field | Type | Meaning |
|---|---|---|
| `ok` | `bool` | Execution succeeded |
| `status` | `completed` / `skipped` / `partial` / `error` | Outcome level |
| `changed_artifacts` | `list[str]` | What was written/modified |
| `stale_artifacts` | `list[str]` | What became stale |
| `warnings` | `list[str]` | Non-fatal issues |
| `errors` | `list[str]` | Fatal issues |
| `evidence_written` | `list[str]` | Evidence artifacts produced |
| `claim_advancement` | `"none"` | Always `"none"` |

**Invariants:**
- `ok` + `error` status is prohibited.
- `error` status **must** include at least one error message.

## Execution rules

1. **Preflight first** — no execution without preflight.
2. **Proposal before approval** — user must see what will change.
3. **Explicit approval** — no implicit or automatic approval.
4. **Atomic writeback** — evidence + stale markers updated together.
5. **Honest failure** — errors are surfaced, never swallowed.

## Prohibited behavior

These are **never** allowed in any adapter:

- Hidden CAD mutation (mutation must be declared in capability manifest).
- Hidden solver run (solver category always requires approval).
- Automatic claim advancement (`claim_advancement` must be `"none"`).
- Certification language in tool output ("design is safe", "certified", etc.).
- Arbitrary code execution without validation.
- Free-form macro execution without intermediate review.

## Evidence writeback rules

After execution, the adapter must write:

1. **Tool output** — structured result (JSON) in `simulation/cae_imports/` or `results/`.
2. **Audit event** — append-only record in `audit/`.
3. **Provenance** — source, bridge, timestamp, claim advancement in every evidence artifact.
4. **Stale markers** — update `revalidation_status.json` for downstream artifacts.

## Cross-references

- Code: `backend/app/external_adapters.py`
- Radar: `docs/external-cad-cae-integration-radar.md`
- Architecture: `docs/developer-architecture.md`
