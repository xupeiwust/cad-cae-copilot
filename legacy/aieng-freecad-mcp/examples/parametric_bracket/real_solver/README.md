# Real Solver Fixture

This directory documents the real FreeCAD FEM / CalculiX solver path for the parametric bracket.

## Prerequisites

- FreeCAD with FEM workbench
- Gmsh or Netgen for meshing
- CalculiX (ccx) binary

## Static Structural Spec

- **Material**: Aluminum 6061-T6
  - Elastic modulus: 68,900 MPa
  - Poisson ratio: 0.33
  - Density: 2,700 kg/m³
  - Yield strength: 276 MPa
- **Fixed support**: mounting holes (four-hole pattern)
- **Load**: 500 N force on load face, -Z direction
- **Mesh**: tet4 elements, target size 2 mm
- **Solver**: CalculiX static structural

## Expected Metrics

| Metric | Expected | Notes |
|---|---|---|
| max_displacement_mm | positive value or not_found | Solver-dependent |
| max_von_mises_mpa | positive value or not_found | Solver-dependent |
| node_count | positive integer | Mesh-dependent |
| element_count | positive integer | Mesh-dependent |

Exact values are not asserted due to solver/mesh variability. Only presence and sanity checks are used.

## Running the Demo

```bash
# Requires FreeCAD + FEM + CalculiX
python scripts/run_real_static_solver_demo.py
```

The demo will:
1. Detect runtime capabilities
2. Build or load a simple model
3. Create static structural analysis
4. Mesh (if mesher available)
5. Export CalculiX deck
6. Run solver (if CalculiX available)
7. Extract metrics
8. Write evidence and trace

If FreeCAD or CalculiX is unavailable, the demo exits cleanly with a skip message.
