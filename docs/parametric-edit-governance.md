# Parametric Edit Governance

AIENG should treat CAD edits as reviewable engineering changes, not arbitrary
agent text that happens to produce a new shape. This document defines the safe
path for parameter edits and the boundaries contributors must preserve.

## Preferred Edit Path

Use parametric edits when a model exposes editable parameters in
`graph/feature_graph.json`:

1. Inspect the current model with `cad.get_source`, `cad.design_review`,
   `cad.critique`, or `cad.list_editable_parameters`.
2. Build a structured edit proposal with:
   - target `featureId`;
   - target `parameterName`;
   - editable CAD constant (`cad_parameter_name`) when available;
   - old value and proposed new value;
   - unit, reason, and expected impact;
   - scope (`local`, `global`, or `unscoped`);
   - protected-feature or design-target risk notes.
3. Ask for explicit user confirmation at the modeling-plan or proposal boundary
   before mutating CAD.
4. Apply the edit with `cad.edit_parameter` only after the target parameter is
   known and the user has accepted the intended scope.
5. Inspect the returned `regression_diff`, `critique_diff`,
   `topology_change`, and persisted last-edit diff before presenting success.

For shared/global parameters, the edit must not be applied silently. The current
backend requires explicit scope-risk confirmation before a global parameter edit
can proceed.

## Audit and Restore Expectations

Accepted parameter edits must leave an audit trail:

- the tool response includes previous value, new value, topology change, and
  regression/critique diff information;
- the package records `state/last_edit_diff.json` for the UI/reporting layer;
- the runtime records a package snapshot after successful CAD mutations where
  snapshot capture is available;
- downstream CAE/revalidation artifacts are marked stale when geometry changes
  make prior evidence unsafe to reuse;
- `cad.restore_snapshot` provides the approval-gated restore path.

Rejected or failed parameter edits must preserve the previous package state.
Examples include invalid expressions, invalid geometry after regeneration, and
global/shared parameters without explicit scope confirmation.

## What Not to Claim

Do not claim parametric edit support when a project has no editable feature
graph parameter. Imported STEP geometry, mesh-only packages, or opaque B-Rep
state may be inspectable, but they are not automatically editable through
`cad.edit_parameter`.

Do not make arbitrary Python macro generation the default modification path for
dimensional changes. Free-form build scripts are still useful for new geometry
or topology-changing work, but dimensional edits should prefer structured
parameter targets whenever the model exposes them.

Do not treat a proposal as evidence. A proposal is a hypothesis until the edit
is accepted, regenerated, diffed, and inspected. A cleaner CAD diff is still not
solver evidence, production sign-off, or certification.

## Contributor Checklist

When adding or changing parametric-edit behavior:

1. Preserve the `cad.list_editable_parameters` discovery path.
2. Keep rejected edits non-mutating.
3. Record old/new values and target feature/parameter identifiers.
4. Preserve scope-risk confirmation for global/shared parameters.
5. Keep downstream CAE evidence stale after accepted geometry changes.
6. Keep restore-path documentation and tests up to date.
7. Avoid approval, certification, or automatic-acceptance claim language.

Useful regression commands:

```bash
python -m pytest aieng-ui/backend/tests/test_cad_generation.py -q -k "edit_build123d_parameter or last_edit_diff"
python -m pytest aieng-ui/backend/tests/test_api.py -q -k "revalidation or evidence_lifecycle or stale"
```
