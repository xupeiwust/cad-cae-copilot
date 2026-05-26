# Known Limitations

This document lists current limitations so users and integrators can set accurate expectations.

## CAD / Geometry

1. **Topology edits unsupported**
   - Face/edge ID stability is not guaranteed across parametric edits.
   - Adding or removing features may break downstream references.

2. **Parametric regeneration only**
   - The MCP can modify parameters that have executable edit metadata.
   - Semantic-only parameters are rejected for CAD writeback.

3. **No arbitrary Python execution**
   - AI-generated Python is not executed as a normal public path.
   - CAD/CAE operations use bounded, whitelisted tool paths.

## CAE / FEM

4. **Linear static structural only**
   - No contact, buckling, nonlinear, fatigue, CFD, or thermal-fluid coupling.
   - Material assignment is single or simple only.

5. **Mesh quality is best-effort**
   - Deterministic mesh generation is supported but quality is not guaranteed.
   - External meshers must be available in the FreeCAD runtime.

6. **Solver execution is evidence, not validation**
   - Running CalculiX produces evidence.
   - It does NOT automatically pass or fail claims.

## Claims and Evidence

7. **No automatic claim advancement**
   - Only `aieng_update_claim` may advance claims.
   - All other tools return `claims_advanced: false`.

8. **Compound claim logic not implemented**
   - Claims are evaluated individually.
   - No AND/OR/NOT logic across multiple claims.

9. **Engineering validation is explicit**
   - Solver/postprocess tools set `engineering_validation: false`.
   - Validation requires an explicit claim update with evidence IDs.

## Package and Runtime

10. **FreeCAD is optional**
    - The MCP works in standalone mode without FreeCAD.
    - Real CAD/CAE execution requires a FreeCAD runtime with FEM workbench.

11. **Windows path handling**
    - All internal paths use forward slashes.
    - Some FreeCAD external tools may expect native Windows paths.

## Composability

12. **CAD and CAE are independent**
    - CAD modification does NOT automatically trigger CAE execution.
    - Optional orchestration helpers exist but are explicit, not automatic.

13. **No design optimization**
    - No topology optimization, shape optimization, or sizing loops.
    - Future optimizers must be explicitly scoped and added.

## Reporting

14. **Audit reports are deterministic but not exhaustive**
    - `aieng_generate_audit_report` checks claim discipline and evidence presence.
    - It does not perform semantic engineering review.

---

Last updated: v1.0.0-rc1
