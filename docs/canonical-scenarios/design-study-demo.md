# Canonical Scenario: Design-Study Candidate Ranking

Status: CI regression pack for `mass_reduction_design_target_comparison`.

This scenario demonstrates an agent-guided parameter design study without
external solver execution. It is useful for onboarding, regression testing, and
showing the `.aieng` package as an evidence container for candidate-local
design decisions.

## Input Package

The test creates a temporary `.aieng` package from deterministic fixtures in:

- `aieng-ui/backend/tests/fixtures/design_study_demo/`
- `aieng-ui/backend/tests/design_study_demo_fixture.py`

The package contains:

- baseline `geometry/shape_ir.json`;
- `analysis/design_study_problem.json`;
- candidate patches under `patches/design_candidates/`;
- candidate-local static metrics injected by the test.

## Design Targets

The scenario asks for lower mass while respecting stress and displacement
constraints. Static metrics are deterministic fixture evidence used only for CI
ranking and acceptance-path regression.

## Workflow

1. Validate the design-study problem.
2. Run candidate patches into derived candidate workspaces.
3. Normalize candidate-local evaluation evidence without running a solver.
4. Rank candidates.
5. Generate advisory hints.
6. Accept the best candidate into a derived accepted workspace.
7. Verify the baseline geometry remains unchanged.

## Verification

```bash
python -m pytest aieng-ui/backend/tests/test_design_study_demo.py -q
```

## Expected Evidence

- `diagnostics/design_study_problem_diagnostics.json`
- `diagnostics/design_study_candidate_validation.json`
- `candidates/<candidate_id>/geometry/shape_ir.json`
- `candidates/<candidate_id>/analysis/evaluation.json`
- `analysis/design_study_candidate_hints.json`
- `analysis/design_study_candidate_ranking.json`
- `analysis/design_study_acceptance.json`
- `accepted/candidate_good/geometry/shape_ir.json`

## Honesty Boundary

- Candidate metrics are static fixture evidence, not real solver evidence.
- Ranking is advisory.
- Acceptance writes a derived accepted artifact; it does not overwrite baseline
  geometry.
- Missing metrics produce insufficient-data states, not guessed pass/fail
  outcomes.
- No production approval or certification is claimed.
