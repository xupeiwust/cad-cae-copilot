# Workflow: Static Structural Analysis

## Goal

Create a conservative linear static structural analysis through FreeCAD/CalculiX and write artifacts and evidence back into `.aieng`.

## Initial Scope

- linear static
- simple material
- fixed support
- force or pressure load
- basic mesh
- CalculiX deck
- optional CalculiX execution

## Flow

1. Read `.aieng` simulation setup and task spec.
2. Verify CAE operation is allowed.
3. Create FreeCAD FEM analysis.
4. Assign material.
5. Apply boundary conditions and loads.
6. Generate mesh where supported.
7. Export CalculiX deck.
8. Optionally run CalculiX when explicitly requested.
9. Capture logs and result files.
10. Extract deterministic metrics.
11. Record evidence and trace.
12. Do not automatically advance validation claims.
