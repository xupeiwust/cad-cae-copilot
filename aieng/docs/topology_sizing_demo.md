# 2D Topology → Sizing → CAE End-to-End Demo

This demo proves the Phase 4 bridge on a deterministic plate-with-loads 2D case:

```text
topology optimization result
        ↓
contour writeback (extruded_region)
        ↓
auto-parameterization (extrusion_thickness)
        ↓
sizing study
        ↓
candidate sampling → execution → evaluation → ranking → recommendation
        ↓
approval-gated acceptance → report
```

It is deterministic, requires no external solver, and explicitly marks every
claim as experimental / advisory.

## Quick run

```bash
# Backend integration tests
pytest aieng-ui/backend/tests/test_topology_sizing_backend_demo.py -q

# Standalone scripted demo
python aieng/scripts/run_topology_sizing_demo.py --out build/topology_sizing_demo.aieng
```

## What the script does

1. **Create a seed package** with a 2D topology result and an `extruded_region`
   Shape IR representing a 10×10 mm plate extruded to 5 mm.
2. **`topology_to_sizing`** auto-parameterizes the recovered thickness into the
   sizing variable `extrusion_thickness` and writes the full optimization-study
   envelope.
3. **Sample** thickness candidates on a grid.
4. **Execute** candidates into derived workspaces without recompilation (no
   external CAD).
5. **Inject** deterministic analytical volume/mass metrics per candidate.
6. **Evaluate** constraints and feasibility.
7. **Rank** candidates by volume objective.
8. **Recommend** the best feasible candidate.
9. **Accept** the best candidate through the explicit approval-gated endpoint.
10. **Report** the full study, including the `topology_to_sizing_chain`.

## Honesty boundaries

- **2D only.** 3D topology results, voxel bodies, and non-extruded writebacks are
  refused with `needs_user_input`.
- **Experimental.** `optimization_study.json` records
  `topology_to_sizing_chain.production_ready: false`.
- **No solver.** Volume and mass are computed analytically; stress and
  displacement are absent rather than fabricated.
- **Baseline untouched.** The original `geometry/shape_ir.json` is never
  modified.
- **Approval-gated.** Acceptance requires a ranked, feasible, safe-to-accept
  candidate and produces a derived-only workspace (`accepted/<id>/`).

## Key artifacts

| Path | Purpose |
|------|---------|
| `analysis/topology_optimization.json` | Source 2D topology result |
| `geometry/shape_ir.json` | Baseline contour writeback |
| `analysis/design_study_problem.json` | Sizing problem with baseline metrics |
| `analysis/optimization_variables.json` | Resolved `extrusion_thickness` binding |
| `analysis/optimization_study.json` | Study envelope + chain linkage |
| `analysis/optimization_decision_log.json` | Decision-log entry requiring human review |
| `patches/design_candidates/*.json` | Sampled candidate patches |
| `candidates/<id>/analysis/evaluation.json` | Candidate-local evaluation |
| `analysis/design_study_candidate_ranking.json` | Ranking result |
| `analysis/optimization_recommendation.json` | Advisory recommendation |
| `analysis/design_study_acceptance.json` | Explicit acceptance record |
| `accepted/<id>/geometry/shape_ir.json` | Accepted derived geometry |
| `diagnostics/optimization_report.json` | Aggregated report |
| `provenance/tool_trace.json` | Tool-trace entries for the bridge steps |

## Reconstructing the chain

```python
import json, zipfile

with zipfile.ZipFile("build/topology_sizing_demo.aieng") as zf:
    study = json.loads(zf.read("analysis/optimization_study.json"))
    report = json.loads(zf.read("diagnostics/optimization_report.json"))
    trace = json.loads(zf.read("provenance/tool_trace.json"))

print(study["topology_to_sizing_chain"])
print(report["topology_to_sizing_chain"])
print([e["step"]["name"] for e in trace["entries"]])
```

## Related documentation

- [`demo_catalog.md`](demo_catalog.md) — Canonical backend demos and smoke commands
- [`backend_capability_matrix.md`](backend_capability_matrix.md) — Capability status matrix
- [`roadmap.md`](roadmap.md) — Phase-by-phase development roadmap
