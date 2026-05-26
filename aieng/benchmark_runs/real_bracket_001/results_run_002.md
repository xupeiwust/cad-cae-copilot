# Real Bracket Benchmark Result Record (Run 002)

Recorded during Phase 11D.

## Executive Summary

Phase 11D Run 002 resolves the optional backend blocker from Run 001 by confirming:

1. **Optional backend available**: CadQuery 2.7.0 + cadquery-ocp 7.8.1.1.post1 runtime detected.
2. **Real STEP demo executed**: `scripts/run_real_step_demo.py` completed end-to-end with OCP geometry backend.
3. **Package validation passed**: `aieng validate build/real_bracket_001.aieng` passed all critical checks.
4. **Full test suite passing**: 549/549 tests pass with optional backend available.

## Environment

- Python environment: `aieng311`
- Optional geometry backend status: **available** — CadQuery 2.7.0 + cadquery-ocp 7.8.1.1.post1 installed and runtime-detected
- Package import status: `aieng` available via local editable source install
- Generated STEP fixture: `examples/real_bracket.step` (48 151 bytes)

## Commands Verified

```
conda run -n aieng311 python -m aieng.cli --help
>>> SUCCESS: CLI available

conda run -n aieng311 python -m pytest -q
>>> SUCCESS: 549 passed in 15.31s

conda run -n aieng311 python scripts/run_real_step_demo.py
>>> SUCCESS: all 51 validation checks PASS

conda run -n aieng311 python -m aieng.cli validate build/real_bracket_001.aieng
>>> SUCCESS: critical checks PASS; 16 optional WARNs (expected for Phase 11)
```

## Procedure

1. **Backend check**:
   - `conda run -n aieng311 python -m aieng.cli geometry-backends`
   - Result: `occ: runtime detected (OCP/CadQuery)`

2. **STEP generation**:
   - `conda run -n aieng311 python scripts/generate_real_bracket_step.py`
   - Output: `examples/real_bracket.step` (48 151 bytes)

3. **Real demo execution**:
   - `conda run -n aieng311 python scripts/run_real_step_demo.py`
   - Output package: `build/real_bracket_001.aieng`

4. **Package validation**:
   - `conda run -n aieng311 python -m aieng.cli validate build/real_bracket_001.aieng`
   - All critical checks passed

## Observations

### Backend Status
- OCP/CadQuery runtime available: **YES**
- `_build_entities_ocp` successfully executed: **YES**
- Edge→face adjacency mapping correct: **YES** (12 edges, 6 faces in test box; all edges have `face_ids` populated)

### Generated Package Contents
All required v0.1 resources present and valid:

| Resource | Status | Notes |
|----------|--------|-------|
| `manifest.json` | ✓ | Format v0.1.0, all required fields |
| `geometry/source.step` | ✓ | Original STEP file |
| `geometry/normalized.step` | ✓ | Normalized copy |
| `geometry/topology_map.json` | ✓ | 12 edges, 6 faces, 1 solid; all entity IDs unique |
| `graph/aag.json` | ✓ | Attributed adjacency graph from topology; state policy present |
| `graph/feature_graph.json` | ✓ | Candidate features (base plate, mounting holes, web); geometry refs resolve |
| `graph/constraints.json` | ✓ | User context applied (material, protected features, simulation setup) |
| `simulation/setup.yaml` | ✓ | Static structural setup with loads/BCs from user context |
| `ai/protected_regions.json` | ✓ | Mounting holes marked as protected |
| `ai/summary.md` | ✓ | AI-readable engineering summary |
| `ai/patches/patch_0001.json` | ✓ | Patch proposal (generated, not executed) |
| `validation/status.yaml` | ✓ | Status record; no mesh; no solver; no geometry modification claimed |

### Validation Results

All 51 validation checks **PASS**:
- Resource existence and schema conformance
- Cross-reference resolution (features→geometry, constraints→features)
- Claim policy validation (no unsubstantiated solver/mesh claims)
- Integrity checks (unique IDs, required fields)

Expected WARNs (Phase 11 — not implemented yet):
- `simulation/cae_imports/` — no imported CAE model
- `results/` — no solver results
- `previews/` — no visual preview artifacts
- `visual/` — no visual model manifest
- `objects/` — no object registry

### Test Suite

Full test suite with optional OCP backend available:
- **Result**: 549 passed (15.31s)
- **Improvement**: 25 additional tests now pass (524→549) due to OCP availability
  - 5 pre-existing tests fixed by OCP iterator correction
  - 20 OCP-conditional tests now executable

## Benchmark Interpretation

**Comparison to Run 001**:

| Aspect | Run 001 (Blocked) | Run 002 (Resolved) |
|--------|---|---|
| Backend available | NO | YES |
| Demo executed | NO | YES |
| Package validation | not attempted | PASS (51/51 critical) |
| Test suite | 524 pass (OCP gated) | 549 pass (OCP available) |

**Condition B Readiness**:
- Raw STEP input: Yes (48 KB; base plate + 4 holes + web)
- Topology extraction: Yes (OCP backend, 12 edges, 6 faces)
- AAG generation: Yes (from topology map)
- Feature recognition: Yes (rule-based candidates; accuracy not scored)
- User context application: Yes (protected regions, simulation setup)
- Patch proposal generation: Yes (not executed per Phase 11 scope)
- Validation: Yes (all critical checks pass)

**AI Consumption Readiness**:
- Structured topology map: Yes
- Attributed adjacency graph: Yes
- Feature graph with references: Yes
- Constraints with feature links: Yes
- Protected regions explicit: Yes
- Patch proposal schema: Yes
- Validation status: Yes
- No fabricated claims: Yes

## Conservative Claim Policy

Held throughout Run 002:

- ✓ No mesh was generated (no Gmsh/CalculiX meshing attempted)
- ✓ No solver was run (no CalculiX execution)
- ✓ No solver result was imported (no `.rpt` file)
- ✓ No geometry was modified (no FreeCAD/OCP shape deformation)
- ✓ No manufacturing check performed
- ✓ No external AI scoring session executed
- ✓ No engineering safety claim made beyond "package structure is valid"
- ✓ Feature recognition remains candidate-level (rule-based; not validated)

## Scoring Template (Unfilled)

| Condition | Honesty / Non-hallucination | Engineering Usefulness |
|---|---|---|
| Condition A (raw STEP) | not scored | not scored |
| Condition B (`.aieng`) | not scored | not scored |

No external AI scoring session was run in Phase 11D Run 002; this record captures real backend execution and package validation evidence only.

## Next Steps

- Phase 11D R002 evidence complete
- Optional backend now confirmed available and working
- Repository ready for Phase 12 (mesh generation) or Phase 13 (solver export) if desired
- Do not commit generated STEP or package to repo (both are gitignored and reproducible)
