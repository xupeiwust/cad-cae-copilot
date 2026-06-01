# Example v1 Demo Output

This document shows representative output from running the v1 composable demo:

```bash
python scripts/run_v1_demo.py --path all
```

## 1. CAD-Only Path

```
============================================================
V1 COMPOSABLE DEMO — CAD-ONLY PATH
============================================================
Step 1: Inspect CAD model
  -> Object tree: 3 bodies, 12 faces
  -> Parameters: thickness=5.0, hole_diameter=10.0
  -> Status: success

Step 2: Modify parameter (thickness 5.0 -> 6.0)
  -> Modified FCStd: geometry/modified_bracket.fcstd
  -> Modified STEP: geometry/modified_bracket.step
  -> Evidence ID: cad_edit_001
  -> Status: success

Step 3: Export STEP
  -> Output: geometry/modified_bracket.step
  -> Status: success

CAD-Only Path Complete.
  Claims advanced: False
  Artifacts: 2
  Evidence entries: 1
```

## 2. CAE-Only Path

```
============================================================
V1 COMPOSABLE DEMO — CAE-ONLY PATH
============================================================
Step 1: Create static structural analysis
  -> Material: Steel, Young's modulus = 210000 MPa
  -> Constraints: FixedSupport-1
  -> Loads: Force-1 (1000 N)
  -> Status: success

Step 2: Generate mesh
  -> Max element size: 5.0 mm
  -> Nodes: 12,847 | Elements: 71,203
  -> Status: success

Step 3: Export CalculiX deck
  -> Output: simulation/analysis.inp
  -> Status: success

Step 4: Run CalculiX
  -> Exit status: 0
  -> FRD: results/solver_output.frd
  -> DAT: results/solver_output.dat
  -> Status: success

CAE-Only Path Complete.
  Claims advanced: False
  Evidence entries: 4
```

## 3. CAD -> CAE Path (Optional Orchestration)

```
============================================================
V1 COMPOSABLE DEMO — CAD->CAE PATH
============================================================
Step 1: Modify parameter (thickness 5.0 -> 6.0)
  -> Status: success (same as CAD-only)

Step 2: Export STEP
  -> Status: success

Step 3: Create static structural analysis (on modified geometry)
  -> Status: success

Step 4: Generate mesh
  -> Status: success

Step 5: Export CalculiX deck
  -> Status: success

Step 6: Run CalculiX
  -> Status: success

CAD->CAE Path Complete.
  Claims advanced: False
  Evidence entries: 6
```

## 4. Reference Path

```
============================================================
V1 COMPOSABLE DEMO — REFERENCE PATH
============================================================
Step 1: Build reference map
  -> References tracked: 4
  -> Statuses: 2 current, 1 outdated, 1 needs_review
  -> Output: references/reference_map.json
  -> Status: success

Reference Path Complete.
```

## 5. Claim Path

```
============================================================
V1 COMPOSABLE DEMO — CLAIM PATH
============================================================
Step 1: Update claim (max_displacement < 2.0 mm)
  -> Evidence IDs: [cae_evidence_001, cae_evidence_002]
  -> Decision criteria: max_displacement < 2.0
  -> Computed value: 1.73 mm
  -> Status: pass

Step 2: Generate audit report
  -> Violations detected: 0
  -> Output: reports/audit_report.md
  -> Status: success

Claim Path Complete.
  Claims advanced: True (via aieng_update_claim only)
```

---

**Note:** This is representative output. Actual numeric results depend on the
input model, mesh density, and solver configuration.
