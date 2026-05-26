# `@aieng[...]` Reference Notation Proposal

Status: draft for Phase 18A.

## 1. Motivation

text-to-cad uses `@cad[path/to/model.step#selector]` as a stable, copy-pasteable handle. Agents quote it in chat, paste it into CLI commands (`python scripts/inspect refs '@cad[...]'`), and use it to make follow-up edits without re-parsing geometry.

`.aieng` already has stable IDs (`feat_*`, `face_*`, `iface_*`, `claim_*`, `evidence_*`, `trace_*`) inside structured resources. What it lacks is a **canonical string form** that:

- can be quoted by an AI in prose or a chat reply,
- can be pasted into a CLI verb,
- can be returned by every MCP tool that returns a record,
- can be validated and dereferenced deterministically,
- never depends on the consumer parsing JSON paths.

This notation is purely a *naming convention* over already-existing IDs. It is not new data, not source of truth, and not a query language.

## 2. Form

```
@aieng[<resource-path>#<id>]
```

- `<resource-path>` is the canonical relative path of the structured resource inside the package, e.g. `graph/feature_graph.json`.
- `<id>` is the stable record ID inside that resource.

### Examples (all resolvable today against current schemas)

```
@aieng[graph/feature_graph.json#feat_base_plate_001]
@aieng[graph/feature_graph.json#feat_hole_pattern_001]
@aieng[geometry/topology_map.json#face_012]
@aieng[geometry/topology_map.json#edge_004]
@aieng[graph/aag.json#face_012]
@aieng[objects/object_registry.json#feat_base_plate_001]
@aieng[objects/interface_graph.json#iface_feat_hole_pattern_001]
@aieng[ai/protected_regions.json#feat_hole_pattern_001]
@aieng[graph/constraints.json#cstr_keep_holes_001]
@aieng[simulation/setup.yaml#load_case_001]
@aieng[simulation/cae_mapping.json#FIXED_HOLES]
@aieng[ai/patches/patch_0001.json#patch_0001]
@aieng[results/claim_map.json#claim_solver_stress_001]
@aieng[results/evidence_index.json#evidence_mesh_001]
@aieng[provenance/tool_trace.json#trace_0007]
@aieng[validation/status.yaml#claim_policy]
@aieng[validation/completeness_report.json#real_geometry_extraction]
@aieng[task/task_spec.yaml#required_outputs]
@aieng[task/external_tool_requirements.json#capability_meshing]
```

### Grammar

```
reference   ::= "@aieng[" resource_path "#" id "]"
resource_path ::= relative POSIX path with extension .json | .yaml | .yml
id          ::= [A-Za-z0-9_.-]+
```

Both halves are case-sensitive. Whitespace inside brackets is invalid.

## 3. What a reference means

A reference is a *pointer to an existing record*. It does **not**:

- create or mutate the record,
- imply that the record is valid,
- imply that the record passes any claim,
- carry rendering, geometry, or solver semantics on its own.

A reference is valid iff the resource exists, the resource parses, and the ID is present in the resource. A reference is *informative* even if invalid — `aieng ref-check` reports the failure mode (`resource_missing`, `parse_error`, `id_not_found`, `package_missing`).

## 4. CLI

### 4.1 `aieng ref-inspect '<ref>' --json`

Resolve one reference and print the underlying record.

```bash
aieng ref-inspect 'build/bracket_001.aieng:@aieng[graph/feature_graph.json#feat_base_plate_001]' --json
```

Output (JSON):
```json
{
  "ref": "@aieng[graph/feature_graph.json#feat_base_plate_001]",
  "package": "build/bracket_001.aieng",
  "resource_path": "graph/feature_graph.json",
  "id": "feat_base_plate_001",
  "resolved": true,
  "record_type": "feature_candidate",
  "record": { /* the exact record from feature_graph.json */ },
  "related_refs": [
    "@aieng[geometry/topology_map.json#face_001]",
    "@aieng[ai/protected_regions.json#feat_base_plate_001]"
  ]
}
```

`--json` is the default for programmatic use. A short text form (without `--json`) prints a one-line summary plus the record's headline fields.

`related_refs` is derived deterministically by walking known schema cross-fields (topology_refs, feature_id back-references, etc.). It is a *derived index*, not a new edge in the graph.

### 4.2 `aieng ref-list <package.aieng> --type <kind>`

Enumerate references of a given kind. Kinds: `feature`, `topology`, `interface`, `claim`, `evidence`, `trace`, `patch`, `constraint`, `protected_region`, `cae_mapping`, `completeness_item`, `all`.

```bash
aieng ref-list build/bracket_001.aieng --type feature
@aieng[graph/feature_graph.json#feat_base_plate_001]
@aieng[graph/feature_graph.json#feat_hole_pattern_001]
@aieng[graph/feature_graph.json#feat_unknown_001]

aieng ref-list build/bracket_001.aieng --type claim --json
[
  {"ref": "@aieng[results/claim_map.json#claim_solver_stress_001]", "status": "unsupported"},
  {"ref": "@aieng[results/claim_map.json#claim_mesh_quality_001]", "status": "pass"}
]
```

### 4.3 `aieng ref-check <package.aieng>`

Validate every cross-resource reference in the package. Reports dangling refs, type mismatches, and forbidden-target violations (e.g. an `evidence_index` entry pointing at a `feature_graph` ID instead of a claim ID).

```bash
aieng ref-check build/bracket_001.aieng
OK: 47 references checked, 0 errors
```

Failure example:
```
ERROR @aieng[results/claim_map.json#claim_solver_stress_001].supported_by
  → @aieng[results/evidence_index.json#evidence_mesh_001]: target exists but record_type=mesh, expected solver
```

`aieng validate` should call `ref-check` internally and surface failures with the same exit code.

### 4.4 Package-prefixed form

For multi-package contexts (CI logs, MCP responses), a package prefix is accepted:

```
<package-path>:<reference>
build/bracket_001.aieng:@aieng[graph/feature_graph.json#feat_base_plate_001]
```

The prefix is optional in single-package CLI use.

## 5. MCP integration

Every MCP tool that returns a record SHOULD return a `ref` field carrying the canonical `@aieng[...]` form.

Example: `get_feature_graph` returns:
```json
{
  "features": [
    {
      "ref": "@aieng[graph/feature_graph.json#feat_base_plate_001]",
      "id": "feat_base_plate_001",
      "kind": "base_plate_candidate",
      ...
    }
  ]
}
```

A new MCP tool `resolve_ref(ref)` lets agents dereference a quoted handle in one call without knowing the resource layout. The tool is read-only; it does not edit, advance claims, or write evidence.

## 6. Schema implications

No breaking schema changes. Additive only.

- A small `references.schema.json` defines the string-form grammar for documentation and validator use.
- `aieng validate` extends to check that **every** schema field whose name ends in `_ref`, `_refs`, `supported_by`, `claims_advanced`, `topology_refs`, `feature_id`, or `interface_id` resolves to an existing record. This already partly works via cross-resource integrity checks; the new piece is exposing the canonical string form in error messages and ref-list output.
- Optional generated index: `index/references.json`, written by a new `aieng build-reference-index` or as a side-effect of `aieng validate`. The index is *derived* (clearly marked `generated_index: true`), never source of truth.

## 7. Validator rules added

1. `ref_grammar_valid`: every `@aieng[...]` string in package text resources matches the grammar.
2. `ref_resource_exists`: the resource path resolves inside the package.
3. `ref_id_exists`: the ID exists in the resource.
4. `ref_type_correct`: cross-field references obey the expected target type (claims point at evidence, evidence points at producer tools, etc.).
5. `ref_no_forbidden_target`: e.g. a claim cannot be `supported_by` a `summary.md` record; only structured evidence is admissible.
6. `ref_no_geometry_modification_target`: a patch's `applied_to` cannot point at a STEP file path; semantic targets only unless `editability=executable_by_regeneration`.

## 8. What `@aieng[...]` is NOT

- Not a query language. It addresses a single record, not a filter.
- Not a way to create records. `aieng ref-inspect` is read-only; record creation goes through the existing build/import/record verbs.
- Not a substitute for IDs. Internal JSON cross-references continue to use raw IDs; the `@aieng[...]` form is for surfaces where a *string handle* is more useful than a JSON pointer (chat, CLI, MCP tool replies, PR descriptions, benchmark questions).
- Not a versioned identifier. Snapshots/versioning belong to git and to `provenance/tool_trace.json`. `@aieng[...]` always means "the current value of this record in this package."
- Not authoritative when it conflicts with the resource. If a reference resolves successfully, the *resource* is the truth, not the reference text.

## 9. Migration / rollout

- Add to docs first (`docs/reference_notation.md`).
- Implement `aieng ref-inspect`, `aieng ref-list`, `aieng ref-check`.
- Extend `aieng validate` to call `ref-check`.
- Extend MCP tool responses to include `ref` fields.
- Update existing benchmark questions and walkthrough docs to quote `@aieng[...]` forms where they currently use raw IDs.

No existing data needs rewriting.

## 10. Open questions

- Should `@aieng[...]` allow a fragment for nested fields inside a record (e.g. `@aieng[graph/feature_graph.json#feat_base_plate_001.parameters.thickness]`)? **Recommendation: no for Phase 18A.** Resolve nested fields by extending `ref-inspect` output with the full record; keep the reference itself anchored at the record level for simplicity.
- Should the prefix include the package name? **Recommendation: optional prefix.** Inside a package the prefix is redundant; in cross-package logs it is required.
- Reference equality across `--overwrite` runs: an ID is stable across overwrites by construction (we use deterministic ID schemes), but a regenerated `aag.json` may renumber IDs if topology changes. Document this.
