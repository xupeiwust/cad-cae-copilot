# Workflow: Guarded Parametric Edit

## Goal

Apply a parameter edit only when `.aieng` marks the feature as executable by parametric regeneration.

## Flow

1. Read package manifest.
2. Read feature graph.
3. Verify target feature exists.
4. Verify target parameter exists.
5. Verify editability and writeback strategy.
6. Verify task spec allows the operation.
7. Verify protected regions are not violated.
8. Run approved FreeCAD parameter edit script.
9. Recompute FreeCAD document.
10. Export modified FCStd and STEP.
11. Record evidence.
12. Record tool trace.
13. Return `claims_advanced=false`.

## Rejection Cases

Reject when:

- feature is semantic-only
- parameter is missing
- writeback strategy is unsupported
- protected region would be modified
- FreeCAD recompute fails
- export fails
