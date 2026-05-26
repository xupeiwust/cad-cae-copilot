# Schema Versioning Policy

This document defines how `.aieng` format versions advance, what external emitters and readers may rely on, and how compatibility should be handled as the package evolves beyond `0.1.0`.

Today, package resources such as `manifest.json` and `task/task_spec.yaml` are effectively pinned to `format_version: "0.1.0"` by the current schemas, for example `schemas/manifest.schema.json` and `schemas/task_spec.schema.json`. This policy explains how that strictness should evolve without silently breaking consumers.

## Versioning Scheme

`.aieng` uses package-level semantic versioning for the format as a whole.

- The package `format_version` is the primary compatibility signal.
- All resource `format_version` values are currently locked to the same package version.
- `0.1.x` is additive-only for consumers already targeting `0.1.0`.
- `0.2.0` is the first allowed boundary for intentional breaking changes.
- Patch releases such as `0.1.1` should be reserved for clarifications, schema bug fixes, and additive changes that do not invalidate previously valid `0.1.x` packages.

In practical terms, external emitters should explicitly pin the exact `format_version` they write, and readers should compare the package version before assuming they can safely interpret the contents.

## What Counts as Breaking

A change is breaking if a package that previously validated or was meaningfully consumable may now fail validation, be misinterpreted, or require different handling by an existing reader.

Breaking changes include:

- removing a field
- renaming a field
- adding a new required field to an existing resource
- narrowing an enum
- narrowing an accepted type, range, or pattern
- tightening a validation rule so previously accepted data now fails
- changing the meaning of an existing field without renaming it
- changing cross-resource reference rules so previously valid references now fail
- moving an existing resource to a different required path without compatibility handling
- changing unknown-field handling from tolerated to rejected for an already extensible object

When in doubt, a change should be treated as breaking if an older reader could silently produce the wrong engineering interpretation.

## What Counts as Additive

A change is additive if an existing compatible reader can continue to process the package correctly without changing the meaning of fields it already knows about.

Additive changes include:

- adding a new optional field
- adding a new optional resource
- widening an enum
- adding new metadata inside an object that is already explicitly extensible
- adding new documented warnings or notes without changing schema behavior
- clarifying documentation or examples without changing validation or semantics

Additive changes must not require old readers to guess. If a new field materially changes interpretation, then the change is not truly additive even if the field is optional in JSON Schema.

## Reader Policy

Readers should be conservative and explicit.

- A `0.1.0` reader encountering a `0.2.0` package should fail fast with a clear unsupported-version error.
- A reader may accept a newer patch version within the same minor line, such as reading `0.1.1` with `0.1.0` support, only if the reader is designed to tolerate additive patch-level changes.
- Unknown fields may be ignored only where the relevant schema or resource policy is intentionally extensible.
- Unknown required semantics must not be silently assumed away.
- If graceful degradation is used, the reader should log or report what was skipped and why.

For `.aieng`, fail-fast is the default for unsupported major or minor versions. Graceful degradation is acceptable only within a declared compatible version line and only for additive content.

## Schema-Level Version vs Resource-Level Version

Each resource currently carries its own `format_version`, but that value is locked to the package-wide format version. This keeps compatibility simple for external emitters and validators during the pre-`1.0` phase.

Current policy:

- the package format version is authoritative
- resource versions must match the package version
- schemas should advance together as one format release

Future independent resource versioning is possible, but only after `.aieng` defines an explicit compatibility matrix and reader behavior for mixed-version packages. Until then, external tools should assume package-wide lockstep versioning.

## Derived-summary artifacts

The lockstep policy above governs *package-format* resources — `manifest.json`, `task_spec.yaml`, the AAG (`graph/`), and other schemas that define the contract between an emitter and a `.aieng` reader.

A separate class of artifacts is *derived*: they are generated from a package's contents by `aieng` itself or by an external post-processor, and have evolved at different rates than the package format. The following are derived summaries and carry their own `schema_version` field:

- `results/result_summary.json` (CAE post-processing summary)
- `results/evidence_index.json`
- `results/computed_metrics.json`
- `simulation/preprocessing_summary.json`
- `simulation/simulation_run_summary.json`
- `modeling_plan/*.json` (uses the field name `plan_schema_version`)

The canonical value for each derived-summary `schema_version` lives as a named constant in [`aieng/src/aieng/schema_versions.py`](../src/aieng/schema_versions.py). Every emitter inside `aieng` imports from that module rather than hardcoding a literal; external emitters and the cross-repo `aieng_freecad_mcp` exporter mirror the constant value (a contract test keeps them in lockstep).

Bumping a derived summary's `schema_version` is a contract event but does **not** require a package `format_version` bump. The opposite is also true: a package-format `format_version` bump does not automatically advance any derived summary's `schema_version`. The two version axes are independent until the next major package release.

Readers of derived summaries should compare the on-disk `schema_version` against the constant they were compiled against, and surface a "regenerate" warning on mismatch rather than silently displaying stale-schema data.

## Deprecation Policy

Deprecation must be explicit, documented, and time-bounded.

- A deprecated field must be marked in the relevant schema comments and documentation.
- A deprecated field must remain valid for at least one minor version after the deprecation is introduced.
- Removal of a deprecated field must wait for the next breaking version boundary.
- Readers should continue accepting deprecated fields during the supported deprecation window.
- Writers should stop emitting deprecated fields as soon as a replacement exists.

For example, if a field is deprecated in `0.1.1`, it should remain valid through the `0.1.x` line and should not be removed until `0.2.0` or later.

## Const Guards and Breaking Changes

Some `.aieng` schemas intentionally use strict `const` guards to preserve safety boundaries and execution claims. For example, `schemas/task_spec.schema.json` requires specific claim-policy booleans to remain fixed so readers and external tools can rely on `.aieng` not over-claiming execution behavior.

Those guards are intentionally strict:

- changing `const: true` to allow `false`
- changing `const: false` to allow `true`
- removing a `const` guard entirely
- changing the meaning of a guarded field

All of the above are breaking changes. Even a loosening change is breaking here, because older consumers may rely on strict rejection to preserve safety, trust boundaries, or workflow routing.

## Pre-1.0 Expectations

`.aieng` is still pre-`1.0`, so the format may evolve more freely than a stable `1.x` standard. External tools should therefore be cautious:

- pin the exact `format_version` when emitting packages
- validate emitted packages against the matching schemas
- reject unsupported future versions rather than guessing
- treat minor-version upgrades as an intentional adoption step, not an automatic assumption

Pre-`1.0` does not mean arbitrary drift is acceptable. Changes should still follow the additive-versus-breaking rules in this document so that external emitters and readers can plan migrations cleanly.

## Worked Examples

### Additive change example

Suppose `task/task_spec.yaml` gains a new optional field:

```yaml
task_id: bracket_mass_reduction
format_version: "0.1.1"
intent: Reduce mass by 15% while keeping mounting holes unchanged.
mode: proposal_only
required_outputs:
  - patch_proposal
forbidden_claims:
  - solved_structural_performance
claim_policy:
  no_solver_run_claim: true
  no_mesh_generation_claim: true
  no_geometry_modification_claim: true
  external_tools_execute: true
review_notes: Human review required before external execution.
```

If `review_notes` is optional and does not change the meaning of existing fields, this is additive. A compatible `0.1.x` reader may ignore it, ideally with a warning or trace message if that reader reports skipped fields.

### Breaking change example

Suppose a later schema narrows an enum in `schemas/task_spec.schema.json` by removing a previously valid `mode` value or removing a previously valid entry from `required_outputs`.

That is breaking because:

- packages that previously validated would now fail
- emitters targeting the old enum set would need code changes
- readers that assume the old value set could reject or mis-handle existing packages

Enum narrowing is therefore a breaking change and must wait for a breaking version boundary such as `0.2.0`.
