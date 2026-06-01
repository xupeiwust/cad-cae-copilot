# Parametric Bracket — Composable CAD/CAE Execution Reference

This is a lightweight reference fixture demonstrating five **independent composable workflows**:

1. **CAD-only** — patch execution without CAE
2. **CAE-only** — post-processing without a preceding patch
3. **Optional CAD→CAE** — explicit orchestration of CAD + CAE
4. **Reference** — traceability metadata and `needs_review` markers
5. **Claim** — explicit evidence-backed claim update

CAD and CAE are independent first-class capabilities. The orchestration helper is optional and explicit.

## Structure

```
package/
  manifest.json              — package identity
  graph/feature_graph.json   — executable, protected, and semantic-only features
  graph/constraints.json     — protected regions and design rules
  task/task_spec.yaml        — allowed operations and forbidden claims
  results/claim_map.json     — engineering claims (not auto-advanced)
  results/evidence_index.json — evidence entries (append-only)
  provenance/tool_trace.json  — provenance trace (append-only)
patches/
  reduce_base_plate_thickness.json   — valid executable patch
  reject_protected_hole_edit.json    — should be rejected (protected region)
  reject_semantic_only_edit.json     — should be rejected (semantic-only)
```

## Features

### Executable Feature

- `feat_base_plate_001` → FreeCAD object `BasePlate`
- Parameter `thickness_mm` → FreeCAD parameter `Thickness`
- Editability: `executable_by_regeneration`

### Protected Feature

- `feat_mounting_holes_001` → FreeCAD object `MountingHoles`
- Protected by `mounting_zone` constraint
- Any modification patch targeting this feature should be rejected

### Semantic-Only Feature

- `feat_semantic_rib_001` → FreeCAD object `Rib`
- Editability: `semantic_only`
- Any modification patch targeting this feature should be rejected

## Running the Composable Demos

### v1.0 Composable Demo (all paths)

```bash
python scripts/run_v1_demo.py --path all
```

### Individual Composable Paths

```bash
# 1. CAD-only path
python scripts/run_v1_demo.py --path cad-only

# 2. CAE-only path
python scripts/run_v1_demo.py --path cae-only

# 3. Optional CAD→CAE path
python scripts/run_v1_demo.py --path cad-cae

# 4. Reference path
python scripts/run_v1_demo.py --path reference

# 5. Claim path
python scripts/run_v1_demo.py --path claim
```

### Legacy Individual Demos

```bash
# Patch execution demo (CAD-only)
python scripts/run_aieng_patch_demo.py

# Optional CAD/CAE orchestration demo
python scripts/run_cad_to_cae_demo.py

# Post-processing demo (CAE-only)
python scripts/run_postprocessing_demo.py

# Claim update demo
python scripts/run_claim_update_demo.py

# Reference mapping demo
python scripts/run_reference_mapping_demo.py
```

### Real FreeCAD Mode (requires FreeCAD)

```bash
python scripts/create_parametric_bracket_fcstd.py
python scripts/run_real_freecad_patch_demo.py
```

## What Each Path Demonstrates

### CAD-only (`run_aieng_patch_demo.py`)
1. Loads the `.aieng` context from `package/`
2. Parses `patches/reduce_base_plate_thickness.json`
3. Dry-runs the patch
4. Executes the patch with persistence enabled
5. Verifies evidence and trace were appended
6. Verifies `claim_map.json` was **not** modified
7. **Does not invoke CAE**

### CAE-only (`run_postprocessing_demo.py`)
1. Creates or uses mock CAE result data
2. Runs `aieng_postprocess_results`
3. Extracts result metrics
4. Exports a CSV artifact
5. Records post-processing evidence with `engineering_validation: false`
6. **Does not require a preceding CAD patch**

### Optional CAD→CAE (`run_cad_to_cae_demo.py`)
1. Explicitly invokes the optional orchestration helper
2. Runs CAD patch edit independently
3. Explicitly composes CAE mesh/deck/post-process
4. Marks surrogate results as estimates, not validation
5. Verifies orchestration metadata includes `solver_executed: false`

### Reference (`run_reference_mapping_demo.py`)
1. Builds a reference map from fixture resources
2. Shows geometry references (feature → FreeCAD object) and CAE targets
3. Persists the reference map to `objects/reference_map.json`
4. Executes a valid patch
5. Verifies affected references are marked `needs_review`
6. Verifies linked CAE targets are also marked `needs_review`
7. Verifies `claim_map.json` remains unchanged

### Claim (`run_claim_update_demo.py`)
1. Creates mock evidence with a known metric value
2. Runs `aieng_update_claim` in dry-run mode first
3. Verifies dry-run does not modify `claim_map.json`
4. Runs `aieng_update_claim` for real
5. Verifies only the target claim changes
6. Verifies trace is appended
7. Demonstrates deterministic criteria evaluation

## Design Principles Demonstrated

- **CAD and CAE are independent** — patch execution does not automatically trigger CAE; CAE can run without a patch
- **Orchestration is optional and explicit** — `aieng_run_cad_to_cae_workflow` is a convenience helper, not a default
- **Source artifacts are immutable** — modified artifacts are written to `geometry/modified/`
- **Execution is not validation** — a successful patch execution does not advance claims
- **Honest rejection** — unsupported/protected/semantic-only patches are rejected with clear reasons
- **Auditability** — every execution step is recorded in evidence and trace
- **Artifact metadata discipline** — evidence records `source_artifact_preserved: true` and does not claim geometry validity
- **CAE conservatism** — solver is disabled by default; surrogate results are marked as estimates
- **Explicit claim updates** — claims change only through `aieng_update_claim` with evidence and criteria
