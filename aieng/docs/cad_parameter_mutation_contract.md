# CAD Parameter Mutation Contract

This document defines the contract that a CAD adapter (e.g.
`aieng_freecad_mcp`) must satisfy when it implements the
`cad.edit_parameter` runtime tool defined by
[Phase 32 of the LLM-assisted CAD/CAE design roadmap](../issues/phase_36_closed_loop_benchmark.md)
([issue #54](https://github.com/armpro24-blip/aieng/issues/54)).

`cad.edit_parameter` is the **only** Phase 32 generation surface: a single
named-parameter edit on a single CAD feature, with explicit approval.

The contract has three audiences:

- The agent that calls `cad.edit_parameter` and reads back the result.
- The adapter (FreeCAD MCP, NX adapter, …) that performs the edit and writes
  back evidence.
- The `.aieng` evidence layer, which validates the writeback structure and
  marks downstream evidence as stale.

The implementation of the adapter lives outside this repository (in
`aieng_freecad_mcp`). The contract — the schema and rules — lives here so
all participants agree.

## Core positioning

`.aieng` defines **what** a CAD parameter edit looks like as evidence; it
does **not** execute the edit. The adapter executes the edit against an
external CAD kernel and writes back a structured record. AIENG validates
the structure of the record, the approval state, and the staleness
propagation — never the geometric correctness.

```text
Agent calls cad.edit_parameter(feature_id, parameter_name, new_value)
        ↓
Adapter performs preflight (feature exists, parameter editable, bounds, topology-changing?)
        ↓
Approval gate (human or harness): grant | deny
        ↓ (only if granted)
Adapter mutates the CAD model and atomically re-exports STEP
        ↓
Adapter writes back ai/patches/parameter_edits/{edit_id}.json
        ↓
AIENG validates the writeback against schemas/parameter_edit.schema.json
        ↓
Downstream evidence (mesh, solver, field summaries) is marked stale via stale_artifacts
```

## Schema

The writeback artifact is constrained by
[`schemas/parameter_edit.schema.json`](../schemas/parameter_edit.schema.json).
The schema enforces the following structural invariants as const guards:

- `claim_policy.approval_gated` is `true` (the adapter cannot opt out).
- `claim_policy.topology_unchanged` is `true` (Phase 32 only).
- `claim_policy.no_solver_run` is `true`.
- `claim_policy.no_mesh_run` is `true`.

The adapter must always emit these flags; they are not optional.

## Required adapter behavior

### Preflight

Before requesting approval, the adapter must populate the `preflight` block:

| Field | Meaning |
|---|---|
| `feature_exists` | The `feature_id` resolves against `graph/feature_graph.json`. |
| `parameter_exists` | The named parameter exists on that feature. |
| `editable` | The parameter is mutable (not derived/locked). |
| `value_in_bounds` | The new value is inside the adapter-reported `bounds`. |
| `topology_changing` | The edit would add/remove faces or change feature count. **If true, the adapter must refuse.** |

Any negative result must be reported with a `refusal_reason` and the
edit must not be applied. The adapter must not "round" out-of-bounds
values to the nearest legal value silently.

### Approval gate

Parameter edits are always approval-gated:

- `approval.required` is `true` (const).
- `approval.status` walks `pending → granted | denied` (or
  `auto_approved_for_benchmark` inside a benchmark harness).
- An adapter that runs in a closed-loop benchmark with auto-approval
  must still emit `approval.status = "auto_approved_for_benchmark"`
  and record the approver in `approval.approver` so the contract
  surface stays visible in provenance.

Adapters must not apply an edit while `approval.status` is `pending` or
`denied`.

### Atomic STEP re-export

When `execution.status` is `"succeeded"`:

- `execution.step_export.attempted` must be `true`.
- `execution.step_export.atomic` must be `true`. The adapter is required
  to write the new STEP file using a tempfile-and-replace strategy (no
  partial files on disk).
- `execution.step_export.path` must be the in-package relative path of
  the new STEP file, conventionally
  `geometry/modified_{edit_id}.step`.

When `execution.status` is `"failed"` or `"refused"`, the adapter must
populate `execution.failure_reason`.

### Staleness propagation

A parameter edit invalidates downstream evidence. The adapter must
enumerate every affected resource it can detect into
`stale_artifacts`:

| If the edit touches… | The adapter should mark stale… |
|---|---|
| Any geometric parameter | `simulation/cae_imports/source_solver_deck.inp`, `simulation/mesh/*`, `results/field_regions.json`, `results/field_summary.json`, `results/result_summary.json`, `results/computed_metrics.json` |
| Material/property-only parameters (rare for Phase 32) | `results/result_summary.json`, `results/computed_metrics.json` |
| Section/thickness on a structural feature | mesh + solver evidence |

`stale_artifacts` is an honest record of "these resources reference
geometry/state from before this edit and must not be advanced without
re-running their producers." AIENG core does **not** delete the listed
files; downstream tools must observe the staleness and refuse to act on
the old evidence until refreshed.

Tools that produce evidence (meshers, solvers, postprocessors) must
detect the staleness marker before writing new claims; `pass` states
on stale evidence are a contract violation.

## Forbidden adapter behavior

Adapters must not:

- bypass the approval gate;
- apply topology-changing edits via this tool (use a higher-capability
  tool with its own gating instead);
- silently coerce out-of-bounds values to bounds;
- mark `execution.status = "succeeded"` without an atomic STEP export;
- claim solver or mesh evidence as a side-effect of the edit;
- omit `stale_artifacts` when downstream evidence existed prior to the
  edit;
- write an `execution.failure_reason` of "unknown" — the adapter is
  expected to report the actual kernel/runtime error.

## Recommended minimal writeback profile

```text
ai/patches/parameter_edits/{edit_id}.json   ← validated by parameter_edit.schema.json
geometry/modified_{edit_id}.step             ← atomic re-export
provenance/tool_trace.json                   ← adapter records the edit step
validation/completeness_report.json          ← updated if the edit narrows missingness
```

The edit record is the source of truth for the mutation; markdown
summaries are derived.

## Validation expectations

AIENG validates the writeback at three layers:

1. **Schema** — `aieng validate <pkg>.aieng` runs each
   `ai/patches/parameter_edits/*.json` through
   `parameter_edit.schema.json`. Const-guard violations surface as
   schema FAILs.
2. **Reference resolution** — `feature_id` must resolve against
   `graph/feature_graph.json` via `aieng ref-check`.
3. **Cross-resource** — when `execution.status = "succeeded"`, downstream
   evidence advancement is blocked while `stale_artifacts` is non-empty
   and unrefreshed.

If the adapter cannot honestly satisfy any of these layers for a given
edit, it must refuse rather than emit an incomplete record.

## Capability mapping

In the broader
[CAD/CAE Emitter and Writeback Capability Contract](cad_cae_emitter_contract.md),
`cad.edit_parameter` falls under **L5: Roundtrip-aware adapter**: the
adapter reads `.aieng` patch/task resources, executes an external CAD
kernel, and writes back evidence and updated completeness state.

Topology-changing edits, optimizer loops, and batch parameter sweeps
are out of scope for Phase 32 and must be implemented as separate,
explicitly contracted tools when (and if) they are needed.

## Relationship to `patch_proposal`

`schemas/patch_proposal.schema.json` is the broader patch surface and
allows multiple operations of multiple types. A `cad.edit_parameter`
invocation can be modeled as a one-operation `patch_proposal` whose
single operation is `modify_parameter`, but Phase 32 specifically asks
for a focused contract because:

- the approval surface is simpler (single parameter, single feature);
- the staleness rules are narrower (no topology change);
- the writeback structure is simpler and easier to validate.

`parameter_edit.schema.json` is therefore a focused profile, not a
replacement for `patch_proposal.schema.json`. Adapters that operate
through the broader patch surface continue to use the existing
proposal schema and executor.
