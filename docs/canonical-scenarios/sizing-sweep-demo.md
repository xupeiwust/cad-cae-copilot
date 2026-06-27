# Canonical Scenario: Sizing Sweep Ranked Candidates

Status: CI regression pack for `sizing_sweep_ranked_candidates`.

This scenario demonstrates a bounded sizing sweep over design variables. It
keeps optimization advisory, records candidate evidence in the package, and
prevents accepted candidates from overwriting the baseline model.

## Input Package

The tests create temporary `.aieng` packages with:

- baseline `geometry/shape_ir.json`;
- `analysis/design_study_problem.json`;
- `analysis/optimization_variables.json`;
- deterministic baseline static metrics.

The open-loop pack lives in:

- `aieng-ui/backend/tests/test_optimization_sizing_demo.py`

The iterative pack lives in:

- `aieng-ui/backend/tests/test_iterative_optimization_demo.py`

## Design Targets

The objective is lower mass while satisfying stress and displacement limits.
The metric model is deterministic and solver-neutral: thinner walls reduce mass
but increase stress and displacement.

## Workflow

1. Sample candidate variables.
2. Execute candidates into derived workspaces.
3. Inject deterministic candidate-local static metrics.
4. Evaluate feasibility.
5. Rank candidates and recommend a winner.
6. Accept the winner into a derived accepted workspace.
7. Generate an optimization report.
8. Verify the baseline geometry remains unchanged.

The iterative variant repeats run/evaluate/rank/propose-next until convergence
then accepts the converged incumbent.

## Verification

```bash
python -m pytest aieng-ui/backend/tests/test_optimization_sizing_demo.py aieng-ui/backend/tests/test_iterative_optimization_demo.py -q
```

## Expected Evidence

- `analysis/optimization_study.json`
- `analysis/optimization_decision_log.json`
- `analysis/optimization_iterations.json`
- `analysis/design_study_candidate_ranking.json`
- `analysis/design_study_acceptance.json`
- `diagnostics/optimization_report.json`
- `accepted/<candidate_id>/geometry/shape_ir.json`

## Honesty Boundary

- Static metrics are not solver evidence.
- The optimization loop is advisory and deterministic.
- Acceptance remains explicit and records derived artifacts.
- Baseline geometry remains unchanged.
- No autonomous production design approval or certification is claimed.
