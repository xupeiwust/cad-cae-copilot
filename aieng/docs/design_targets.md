# Design Targets (`task/design_targets.yaml`)

`task/design_targets.yaml` is a **first-class package resource** that encodes engineering requirements and design intent separately from solver results. It lives in the `task/` directory of a `.aieng` package and is consumed by validation, comparison logic, and (in future PRs) the UI.

---

## Format

```yaml
format_version: "0.1.1"   # also accepts legacy "0.1.0"
target_set_id: "bracket_v2_mass_reduction"
source_task_id: "task_bracket_002"          # optional link to task_spec

provenance:
  author: "lead_engineer"
  created_at: "2026-05-17T10:00:00Z"
  source_document: "PRD-2026-047"
  rationale: "Customer requirement from thermal-mechanical review"

claim_policy:
  targets_are_acceptance_criteria: true
  compliance_requires_evidence: true
  physical_correctness_not_claimed: true

targets:
  - id: "stress_limit"
    metric: "max_von_mises_stress"
    operator: "<="
    value: 350.0
    unit: "MPa"
    # modern descriptive fields (optional in schema, recommended for clarity)
    target_id: "stress_limit"
    target_type: "maximum_von_mises_stress"
    description: "Allowable von Mises stress for Al-6061-T6"
    comparator: "<="
    threshold: 350.0
    priority: "high"
    scope: "global"
```

---

## Supported target types

| Target type | Meaning |
|---|---|
| `mass_reduction_target` | Reduce mass by a threshold percentage |
| `absolute_mass_target` | Total mass must meet a bound |
| `minimum_safety_factor` | Safety factor floor |
| `maximum_von_mises_stress` | Stress ceiling |
| `maximum_displacement` | Displacement ceiling |
| `preserved_interface` | Feature or interface must not be removed |
| `objective_priority` | Policy ordering when targets conflict |

---

## Supported comparators

```
<=   <   >=   >   ==   within_range   preserve   reduce_by_at_least   priority
```

---

## Legacy vs modern field compatibility

The schema accepts **both** field styles so existing packages continue to validate.

| Legacy (0.1.0) | Modern (0.1.1) |
|---|---|
| `id` | `target_id` |
| `metric` | `target_type` |
| `operator` | `comparator` |
| `value` | `threshold` |

**Required:** `id`, `metric`, `operator`, `value` (legacy) must be present for backward compatibility.
**Recommended:** also populate `target_id`, `target_type`, `description`, `comparator`, `threshold`, `priority` for clarity.

PR 2 introduces the structured `design_target_comparisons` block (below) that
uses the normalized representation internally. Both field styles continue to
validate; the existing `result["targets"]` flat block is preserved for
backward compatibility with consumers that depend on it.

---

## `design_target_comparisons`

`result_summary.json` always contains a `design_target_comparisons` block
when `task/design_targets.yaml` is present in the package. The block follows
[`schemas/design_target_comparison.schema.json`](../schemas/design_target_comparison.schema.json):

```json
{
  "design_target_comparisons": {
    "present": true,
    "target_set_id": "bracket_v2_mass_reduction",
    "evaluated_at": "2026-05-17T12:00:00Z",
    "summary": {"total": 3, "pass": 2, "fail": 1, "unknown": 0, "not_evaluated": 0},
    "items": [
      {
        "target_id": "stress_limit",
        "target_type": "maximum_von_mises_stress",
        "expected": {"comparator": "<=", "threshold": 350.0},
        "actual": {"value": 298.0, "unit": "MPa", "source_artifact": "results/computed_metrics.json"},
        "comparator": "<=",
        "status": "pass",
        "evidence_refs": ["results/computed_metrics.json"],
        "notes": "Within limit"
      }
    ]
  }
}
```

Allowed statuses: `pass`, `fail`, `unknown`, `not_evaluated`.

### Status semantics

| Status | When emitted |
|---|---|
| `pass` | The actual value exists in evidence and satisfies the comparator. |
| `fail` | The actual value exists in evidence and violates the comparator. |
| `unknown` | The required evidence artifact exists but the field needed to evaluate the target is missing, unreadable, or the comparator's thresholds are incomplete (e.g. `within_range` with only `threshold_min`). |
| `not_evaluated` | No relevant evidence artifact exists, or the target is policy-only (`objective_priority`), or `preserved_interface` has no `graph/feature_graph.json` evidence to check. |

### Comparator semantics

| Comparator | Quantitative? | Notes |
|---|---|---|
| `<=`, `<`, `>=`, `>`, `==` | Yes | Requires `threshold` (or legacy `value`). |
| `within_range` | Yes | Requires both `threshold_min` and `threshold_max`. |
| `reduce_by_at_least` | Yes | Threshold is the required reduction percentage; pass when `actual ≥ threshold`. |
| `preserve` | No | Policy-only. Returns `unknown` when `graph/feature_graph.json` is present, `not_evaluated` otherwise. Geometry-shape validation is **not** performed in this phase. |
| `priority` | No | Policy-only. Always returns `not_evaluated` — comparison logic for objective ordering is deferred to a later phase. |

---

## CLI

`aieng compare-design-targets <package>` evaluates `task/design_targets.yaml`
against available evidence in the package and prints the
`design_target_comparisons` block. Read-only by default; claim proposals require human review.

```bash
# Text output (default): summary counts + one line per target
aieng compare-design-targets path/to/model.aieng

# Machine-readable JSON output of the block
aieng compare-design-targets path/to/model.aieng --output json

# Atomically inject the block into results/result_summary.json
# (preserves all existing summary fields; claim proposals require human review)
aieng compare-design-targets path/to/model.aieng --write-summary
```

Exit codes:

- `0` on a successful comparison (regardless of whether targets pass or fail).
- `2` when `task/design_targets.yaml` is absent or the package is unreadable.

`--write-summary` accepts an optional `--summary-path` override (defaults to
`results/result_summary.json`).

---

## MCP inspection

MCP agents can inspect design targets through read-only tools in `aieng-freecad-mcp`:

- `aieng_read_design_targets` — returns the full `task/design_targets.yaml` content:
  - `target_set_id`, `format_version`, `targets`, `claim_policy`
  - graceful `has_design_targets: false` when the file is absent

- `aieng_read_design_target_comparisons` — returns the comparison block from `results/result_summary.json`:
  - `has_comparisons`, `design_target_comparisons`, `summary`
  - graceful `has_comparisons: false` when the block is absent

Both tools:
- Are **read-only context** — they do not validate, mutate, or advance anything
- Should be used **before** CAD/CAE proposal tools so the agent knows requirements and current comparison status
- Do **not** validate geometry preservation (that remains future work)
- Do **not** auto-advance claims (claim proposals require human review)

---

## Current implementation status

| Capability | Status |
|---|---|
| Schema (`schemas/design_targets.schema.json`) | **Implemented** — dual format 0.1.0/0.1.1 |
| Comparison schema (`schemas/design_target_comparison.schema.json`) | **Implemented** |
| Comparison logic (`_compare_design_targets`) | **Implemented** — `pass`/`fail`/`unknown`/`not_evaluated` |
| CLI (`aieng compare-design-targets`) | **Implemented** — read-only by default; `--write-summary` for atomic ZIP writeback |
| Claim map mutation | **Intentionally not implemented** — claim proposals require human review |
| UI display (pass/fail/unknown badges) | **Not implemented** — deferred to PR 5 |
| True geometry-diff preservation checking | **Not implemented** — `preserve` only checks feature graph presence |
| Objective priority resolution | **Policy-only** — returns `not_evaluated`; ordering logic deferred |

## Boundary rules

1. **Design targets are requirements, not solver results.** They live in `task/`, not `results/`.
2. **Comparison results are not engineering certification.** `status: "pass"` means "available evidence meets the stated threshold," not "safe to fly."
3. **Claim proposals are review artifacts requiring human review.** Comparisons do not automatically advance claims.
4. **Actual values must come from evidence / result artifacts.** No hallucinated metrics.
5. **Missing evidence produces `unknown` or `not_evaluated`.**
   - `unknown` = evidence file exists but required field is absent.
   - `not_evaluated` = no evidence artifact exists to evaluate this target.
6. **Protected-feature checks do not imply geometry mutation was valid.** `preserve` only checks that a feature still exists in the graph; it does not validate shape, position, or tolerance.
