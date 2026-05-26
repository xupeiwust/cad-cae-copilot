# Expected Observations (Real Bracket)

## Condition A (raw STEP)

Expected:

- Geometry-only descriptions with limited engineering semantics.
- Honest uncertainty for constraints, simulation setup, and protected regions.
- No trustworthy feature-level preservation plan beyond rough guesses.

## Condition B (`.aieng` with topology + AAG + semantics)

Expected:

- Citable IDs and cross-resource references (`feature_graph`, `constraints`, `protected_regions`).
- Better adjacency-aware local reasoning with `graph/aag.json`.
- More structured, auditable patch proposals tied to feature IDs.
- Explicit statement that solver evidence is absent unless result files exist.

## Safety expectation

The AI should avoid final engineering/safety claims without solver-validated evidence.
