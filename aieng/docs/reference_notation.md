# `.aieng` Reference Notation (Phase 18A)

Status: **implemented for CLI + validator integration.** Canonical `@aieng[...]` strings, `aieng ref-inspect`, `aieng ref-list`, and `aieng ref-check` are available. `aieng validate` includes `ref-check` failures in its output and exit status.

## Purpose

Stable, copy-pasteable AI-facing references to existing structured package records.

Today every `.aieng` resource already uses stable IDs (`feat_*`, `face_*`, `edge_*`, `iface_*`, `claim_*`, `evidence_*`, `trace_*`, `patch_*`, ...). What is missing is a canonical *string form* that:

- can be quoted by an AI in chat, PR descriptions, or benchmark answers,
- can be pasted into a CLI command,
- can be returned by every MCP tool that returns a record,
- can be resolved deterministically against the package,
- never depends on the consumer parsing JSON paths.

The reference notation is a naming convention over IDs that already exist. It is not new data, not source of truth, and not a query language.

## Syntax

```
@aieng[<resource-path>#<id>]
```

- `<resource-path>` is the package-relative POSIX path of a structured resource, e.g. `graph/feature_graph.json`.
- `<id>` is a stable record ID inside that resource.
- Both halves are case-sensitive. Whitespace inside the brackets is invalid.

Grammar:

```
reference     ::= "@aieng[" resource_path "#" id "]"
resource_path ::= relative POSIX path ending in .json | .yaml | .yml
id            ::= [A-Za-z0-9_.-]+
```

An optional package prefix is allowed for multi-package contexts:

```
<package-path>:@aieng[<resource-path>#<id>]
```

Inside a single package the prefix is redundant.

## Examples

```
@aieng[graph/feature_graph.json#feat_base_plate_001]
@aieng[geometry/topology_map.json#face_012]
@aieng[objects/interface_graph.json#iface_feat_hole_pattern_001]
@aieng[results/evidence_index.json#evidence_solver_result_001]
@aieng[results/evidence_index.json#evidence_mesh_001]
@aieng[provenance/tool_trace.json#trace_0007]
```

Additional valid examples spanning all target categories:

```
@aieng[graph/aag.json#face_012]
@aieng[graph/constraints.json#cstr_keep_holes_001]
@aieng[ai/protected_regions.json#feat_hole_pattern_001]
@aieng[ai/patches/patch_0001.json#patch_0001]
@aieng[simulation/setup.yaml#load_case_001]
@aieng[simulation/cae_mapping.json#FIXED_HOLES]
@aieng[validation/completeness_report.json#real_geometry_extraction]
@aieng[task/task_spec.yaml#required_outputs]
@aieng[task/external_tool_requirements.json#capability_meshing]
```

## Valid target categories

Each `.aieng` reference must resolve to a record in one of the following categories. The category is determined by the target resource and the schema-validated record type within it.

- **feature** — entries in `graph/feature_graph.json`.
- **topology** — faces, edges, vertices in `geometry/topology_map.json`; nodes/edges in `graph/aag.json`.
- **interface** — entries in `objects/interface_graph.json` (and indexed entries in `objects/object_registry.json`).
- **claim** — claim proposals are review artifacts requiring human review.
- **evidence** — entries in `results/evidence_index.json`.
- **trace** — entries in `provenance/tool_trace.json`.
- **patch** — entries in `ai/patches/*.json`.
- **constraint** — entries in `graph/constraints.json`.
- **protected region** — entries in `ai/protected_regions.json`.
- **CAE mapping** — entries in `simulation/cae_mapping.json` and parsed CAE resources under `simulation/cae_imports/*`.
- **completeness item** — entries in `validation/completeness_report.json` and `validation/status.yaml`.
- **task spec item** — entries in `task/task_spec.yaml` and `task/external_tool_requirements.json`.

## Commands

### `aieng ref-inspect <package.aieng> '<ref>' --json`

Resolve one reference and print the underlying record. `--json` prints structured output for programmatic use; without it a short text summary is printed.

Output includes:

- the original reference string,
- the package and resolved resource path,
- the record type and the record itself,
- a list of related references derived deterministically from known schema cross-fields (for example, a feature's `topology_refs`, a claim's `supported_by`).

### `aieng ref-list <package.aieng> --type <kind>`

Enumerate references of a given kind. Supported kinds:

```
feature | topology | interface | claim | evidence | trace |
patch | constraint | protected_region | cae_mapping |
completeness_item | task_spec_item | all
```

Output is one reference per line (or a JSON array with `--json`).

### `aieng ref-check <package.aieng>`

Validate cross-resource references in the package. Reports dangling evidence/claim/trace links and forbidden evidence-target patterns. Exits non-zero on failure. `aieng validate` also runs this check internally.

## Non-goals

`@aieng[...]` is **not**:

- **a query language** — no wildcards, filters, ranges, or path traversal,
- **an edit handle** — references do not authorise modification of any record,
- **proof of validation** — resolvability says nothing about whether the referenced state has passed any check,
- **evidence by itself** — references cannot be admitted as `supported_by` entries; only entries in `results/evidence_index.json` may support a claim,
- **a geometry ownership claim** — referencing a face or feature does not assert that the AI or any agent owns or has modified the underlying CAD,
- **a CAD/CAE execution trigger** — resolving a reference never invokes a CAD kernel, mesher, solver, or external tool.

### Guardrail sentence

`.aieng` references identify structured engineering state; they do not imply editability, validation, executable geometry ownership, or evidence unless the referenced resource explicitly says so.

## Validator behaviour

Phase 18A `aieng ref-check` and `aieng validate` detect:

1. **Malformed reference** — does not match the grammar.
2. **Missing resource** — the resource path does not exist in the package.
3. **Missing ID** — the resource exists and parses, but no record with the given ID is present.
4. **Type mismatch** — a cross-field reference points at a record whose type is not admissible for that field (for example, `supported_by` resolves to a feature rather than an evidence entry).
5. **Forbidden use of summaries or snapshots as evidence** — a claim's `supported_by` cannot resolve to a Markdown summary file or to any record carrying `producer_kind` markers that identify it as a derived view or visual snapshot.

## MCP integration

Record-returning MCP tools now include a canonical `ref` field when the resource has a stable root ID, and a read-only `resolve_ref(ref)` tool resolves a quoted handle in one call.

## Implementation note

Phase 18A implementation should be **additive** and should **avoid schema-breaking changes where possible**. The notation is a naming convention over IDs that already exist. The CLI verbs are read-only. Any generated index (for example, `index/references.json`) is a derived artifact, never source of truth.

## Open question

Whether a reference may carry a nested-field fragment (e.g. `#feat_base_plate_001.parameters.thickness`). **Current recommendation: no for Phase 18A.** Resolve nested fields by inspecting the full record returned by `aieng ref-inspect`; keep references anchored at the record level.

## Related documents

- [Lessons from text-to-cad](text_to_cad_lessons.md)
- [Derived artifact discipline](derived_artifact_discipline.md)
- [Roadmap](roadmap.md) (Phase 18A)
- [Command reference](command_reference.md) (proposed Phase 18 commands section)
- Issue draft: `issues/phase_18_reference_system.md`
- Analysis: [aieng_reference_notation_proposal.md](../analysis/aieng_reference_notation_proposal.md)
