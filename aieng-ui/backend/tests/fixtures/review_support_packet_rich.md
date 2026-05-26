# Engineering Review Support Packet

## Header

| Field | Value |
|---|---|
| Packet id | <PACKET_ID> |
| Project id | <PROJECT_ID> |
| Project name | snap |
| Generated at | <ISO> |
| Packet schema | 0.1 |
| Source package | p.aieng |
| Claim advancement | none |

> This packet supports engineering review. It does not certify design safety, validate the design, or advance engineering claims automatically. All results require qualified engineering review.

## Safety boundary

This packet supports engineering review.

- It does not certify design safety.
- It does not advance engineering claims automatically.
- All results require qualified engineering review.

## Project Health summary

**Readiness:** `partial`

| Status | Count |
|---|---|
| passed | 10 |
| warning | 4 |
| failed | 0 |
| unknown | 3 |

**Open items**

| Check | Status | Summary |
|---|---|---|
| evidence_index | warning | results/evidence_index.json missing. |
| stale_evidence | warning | 1 artifact(s) marked stale. |
| editable_parameters | warning | No editable parameters detected. |
| loop_count | warning | No Copilot loops yet. |

**Recommended actions**

- Review stale evidence before trusting old results
- Add or expose editable CAD parameters before CAD modification proposals
- Start the first Copilot Loop after required package inputs are ready

**Limitations**

- Health check is read-only and heuristic only.
- It does not prove physical correctness, convergence, or design safety.
- It does not run solvers, meshers, or CAD kernels.

## Design Targets

| Target id | Label | Metric | Operator | Value | Unit | Load case | Priority |
|---|---|---|---|---|---|---|---|
| stress_pass | Stress pass | max_von_mises_stress | <= | 200 | MPa | lc1 | high |
| stress_fail | Stress fail | max_von_mises_stress | <= | 1.0 | MPa | lc1 |  |

**Rationale**

- `stress_pass`: Below yield with safety margin.

## Engineering Setup Draft

No engineering setup draft was found in the package. Template authoring is optional — a project can proceed entirely through manually authored design targets, CAD, and solver evidence.

## Computed Metrics

**Global metrics**

| Metric | Value |
|---|---|
| mass | 1.2 kg |

**Load-case metrics**

| Load case | Metric | Value |
|---|---|---|
| lc1 | max_von_mises_stress | 187.4 MPa |


_Source:_ tool=`test` format=`json` imported_by=`fixture`

_Artifact:_ `results/computed_metrics.json`

## Target Comparison

**Status summary**

| Status | Count |
|---|---|
| pass | 1 |
| fail | 1 |
| unknown | 0 |
| not_evaluated | 0 |

**Per-target comparison**

| Target id | Label | Metric | Status | Reason |
|---|---|---|---|---|
| stress_pass | Stress pass | max_von_mises_stress | pass | passed_threshold |
| stress_fail | Stress fail | max_von_mises_stress | fail | failed_threshold |

> Target comparison is a deterministic read-only check against imported computed metrics. It does not certify the design, run a solver, mutate CAD, or advance engineering claims.

## Geometry Inspection Evidence

| Field | Value |
|---|---|
| Parsed features artifact | present |
| Feature graph artifact | present |
| Feature count | 2 |
| Editable-parameter features | 1 |
| Bridge provider | freecad_mcp |
| Generated at | <ISO> |

## CAD Parameter Edit / Approval Records

| Timestamp | Status | Proposal | Parameter | Old | New |
|---|---|---|---|---|---|
| <ISO> | approved | p1 | Pad.Length | 8.0 | 10.0 |

## Structural CAE Execution / Result Extraction

| Field | Value |
|---|---|
| Solver run records | 1 |
| Solver decks (.inp) | 1 |
| Result files (.frd) | 1 |
| Result files (.dat) | 0 |
| Computed metrics from solver | present |

**Solver runs**

| Path | Status | Solved | Return code | Started | Finished |
|---|---|---|---|---|---|
| `simulation/runs/run_001/solver_run.json` | completed | True | 0 | <ISO> | <ISO> |

## Copilot Loop Summary

No Copilot Loops have been started for this project.

## Stale Evidence

| Field | Value |
|---|---|
| Requires revalidation | True |
| Current geometry revision | rev_2 |
| Last validated geometry revision | rev_1 |
| Stale artifact count | 1 |

**Stale artifacts**

- `results/computed_metrics.json`

## Audit / Tool Calls

| Timestamp | Tool | Status | Artifacts written |
|---|---|---|---|
| <ISO> | cae.run_solver | solver_run_completed | 1 |
| <ISO> | cad.edit_parameter | approved | 0 |

## Known Limitations

**Boundary**

- This packet is a review support artifact only — it does not certify the design.
- Engineering claims are not advanced by generating this packet.
- Unit conversions are not normalized; values appear in the units they were imported with.
- Comparator semantics use exact-equality for `==`/`!=` operators; consider tolerances during review.
- Long content (tables, audit events, embedded reports) is capped — see the Audit section if entries appear truncated.

**Missing evidence sections**

- Engineering Setup Draft
- Copilot Loop Summary
