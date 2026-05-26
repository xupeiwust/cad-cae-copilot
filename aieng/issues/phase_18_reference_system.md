---
title: "[Phase 18A] Stable AI-facing reference notation `@aieng[...]` + ref-inspect/list/check CLI"
labels: ["phase-18", "phase-18a", "references", "developer-experience"]
status: closed
---

## Motivation

Agents, MCP clients, CLI users, PR descriptions, and benchmark questions all need a stable, copy-pasteable handle to records inside an `.aieng` package. Today every structured resource already uses stable IDs (`feat_*`, `face_*`, `iface_*`, `claim_*`, `evidence_*`, `trace_*`, `patch_*`, …); what is missing is a canonical *string form* that can be quoted, pasted, and deterministically resolved.

`earthtojake/text-to-cad` demonstrates the value of this addressing pattern (`@cad[path/to/model.step#selector]`). `.aieng` should adopt the addressing pattern over its existing IDs without importing text-to-cad's CAD authoring identity. See [docs/text_to_cad_lessons.md](../docs/text_to_cad_lessons.md).

Without a canonical reference form, AIs reference features by free text ("the hole feature"), invent IDs, or quote JSON paths inconsistently. With it, every quoted handle is mechanically resolvable and benchmark-checkable.

## Scope

1. Adopt the `@aieng[<resource-path>#<id>]` notation defined in [docs/reference_notation.md](../docs/reference_notation.md).
2. Implement three read-only CLI verbs:
   - `aieng ref-inspect <package.aieng> '<ref>' --json`
   - `aieng ref-list <package.aieng> --type <kind>`
   - `aieng ref-check <package.aieng>`
3. Extend `aieng validate` to call `ref-check` internally and surface failures with the same exit code.
4. MCP additions:
   - every record-returning MCP tool returns a canonical `ref` field alongside the existing record fields,
   - optionally add a read-only `resolve_ref(ref)` tool that dereferences a quoted handle in one call.
5. Documentation: update `docs/command_reference.md` (replace the planned section with implemented behaviour); cross-link `docs/reference_notation.md`, `docs/derived_artifact_discipline.md`, `docs/text_to_cad_lessons.md`; update the demo walkthrough where helpful.
6. Optional (low priority within 18A): a generated `index/references.json` produced by an additive verb or as a side-effect of `aieng validate`. Clearly marked `generated_index: true`. Never source of truth.

## Non-goals

- **Not a query language.** No wildcards, filters, ranges, or path traversal.
- **Not an edit handle.** References do not authorise modification of any record.
- **Not proof of validation.** Resolvability says nothing about claim status.
- **Not evidence.** A reference cannot satisfy a claim's `supported_by` on its own.
- **Not a geometry ownership claim.** Referencing a face or feature does not imply the AI or any agent has modified the underlying CAD.
- **Not a CAD/CAE execution trigger.** Resolving a reference never invokes a kernel, mesher, solver, or external tool.
- **Not a schema migration.** No existing resource needs rewriting.

## Proposed syntax

```
@aieng[<resource-path>#<id>]
```

Optional package prefix for multi-package contexts: `<package-path>:@aieng[...]`.

Grammar, valid target categories, and examples: see [docs/reference_notation.md](../docs/reference_notation.md).

## Proposed commands

| Command | Purpose |
|---|---|
| `aieng ref-inspect <package.aieng> '<ref>' --json` | Resolve one reference; print the record plus related refs. |
| `aieng ref-list <package.aieng> --type <kind>` | Enumerate references of a given kind. |
| `aieng ref-check <package.aieng>` | Validate every cross-resource reference; exit non-zero on failure. |

Supported `--type` kinds: `feature`, `topology`, `interface`, `claim`, `evidence`, `trace`, `patch`, `constraint`, `protected_region`, `cae_mapping`, `completeness_item`, `task_spec_item`, `all`.

## MCP addition

- Every existing MCP tool that returns a record should additionally include a `ref` field carrying the canonical `@aieng[...]` string for that record. This is additive and non-breaking.
- Optionally add a new read-only MCP tool `resolve_ref(ref)` that returns the same shape as `aieng ref-inspect --json`. The tool must not write, advance claims, or invoke external tools.

## Validator behavior

The extended `aieng validate` (calling `ref-check`) must detect:

1. **Malformed reference** — does not match the grammar (`@aieng[<resource-path>#<id>]`).
2. **Missing resource** — the resource path does not exist or does not parse.
3. **Missing ID** — the resource exists but no record with the given ID is present.
4. **Type mismatch** — a cross-field reference resolves to a record whose type is not admissible for that field. Examples:
   - a claim's `supported_by` resolves to a feature instead of an evidence entry,
   - a patch's `applied_to` resolves to a STEP file path on a feature whose `editability` is not `executable_by_regeneration`,
   - an evidence entry's `claims_supported` resolves to a feature instead of a claim.
5. **Forbidden use of summaries or snapshots as evidence** — a claim's `supported_by` cannot resolve to a Markdown summary file or to any record carrying producer markers identifying it as a derived view or visual snapshot (e.g. `producer_kind: "aieng_viewer"`, `not_validation_evidence: true`).

All failure modes report the offending reference, the expected target type, and the actual resolved record type.

## Acceptance criteria

- [x] `docs/reference_notation.md` exists and is cross-linked from `README.md`, `docs/architecture.md`, `docs/core_position.md`, and `docs/command_reference.md`.
- [x] `aieng ref-inspect`, `aieng ref-list`, `aieng ref-check` are implemented and behave as specified.
- [x] `aieng validate` calls `ref-check` internally and exits non-zero on any reference failure.
- [x] MCP record-returning tools include a `ref` field where applicable; behaviour is additive and non-breaking.
- [x] No existing JSON/YAML resource requires migration.
- [x] Default install footprint unchanged.

## Test plan

- **Unit:** grammar validator, resource path traversal, ID lookup, related-ref derivation, type-match rules, forbidden-target rules.
- **Integration:** run the full reference bracket, real bracket, and definition-sourced pipelines; assert `aieng ref-check` returns OK on each.
- **Negative tests:**
  - malformed reference → `aieng ref-check` fails with grammar error,
  - dangling claim → evidence reference → `aieng validate` exits non-zero,
  - type-mismatched reference (claim `supported_by` → feature) → flagged,
  - claim with `supported_by` pointing at a Markdown summary path → flagged as forbidden target.
- **MCP test:** record-returning tools return the canonical `ref` field; `resolve_ref(ref)` (if implemented) returns the same shape as `aieng ref-inspect --json`.

## Boundary guardrails

This issue must satisfy every rule in [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md) and the boundary guardrails in [docs/core_position.md](../docs/core_position.md). In particular:

- **No text-to-CAD drift.** The reference system addresses existing records; it never creates geometry, edits geometry, or implies that any record can be regenerated as CAD.
- **No default heavy dependencies.** The CLI and MCP additions stay pure Python.
- **No claim auto-advance.** References do not change claim status.
- **No reference-as-query.** Grammar fixes one record per reference; no wildcards.
- **No snapshot-as-evidence.** Validator flags any attempt to use a summary or snapshot as evidence support.

Guardrail sentence (from [docs/reference_notation.md](../docs/reference_notation.md)):

> `.aieng` references identify structured engineering state; they do not imply editability, validation, executable geometry ownership, or evidence unless the referenced resource explicitly says so.

## Related documents

- [docs/reference_notation.md](../docs/reference_notation.md)
- [docs/text_to_cad_lessons.md](../docs/text_to_cad_lessons.md)
- [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md)
- [docs/roadmap.md](../docs/roadmap.md) (Phase 18A)
- [docs/command_reference.md](../docs/command_reference.md) (proposed Phase 18 commands section)
- [analysis/aieng_reference_notation_proposal.md](../analysis/aieng_reference_notation_proposal.md)
- [analysis/aieng_borrowing_candidates.md](../analysis/aieng_borrowing_candidates.md) (candidate #1, #10)
- [analysis/risk_register.md](../analysis/risk_register.md) (R9, R12)

## Closure evidence

- Commit hashes:
   - `6bdbed8` (preparatory closure/doc sync)
   - `working tree after 6bdbed8` (Phase 18A implementation in this session)
- Tests passing:
   - `python -m pytest tests/test_reference_system.py tests/test_mcp_server.py tests/test_docs_checkpoint.py -q` -> pass
   - `python -m pytest tests/test_adapter_tool_trace_conformance.py tests/test_tool_trace.py tests/test_evidence_report.py -q` -> pass
- Documentation updated:
   - `docs/reference_notation.md`
   - `docs/command_reference.md`
   - `README.md`
   - `docs/architecture.md`
