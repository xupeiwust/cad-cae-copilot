# Plate With Pattern Benchmark Run Package (Phase 18C-min)

This directory is a coverage-probe scaffold for semantic benchmark refresh.

It provides two Condition B variants generated from the same deterministic definition fixture:

- rich variant: includes task, evidence, and consolidated validation resources.
- sparse variant: intentionally omits task/evidence resources to test missingness reasoning.

Use this fixture to test calibration behaviors:

- distinguish missing vs unsupported vs available states,
- avoid unsupported solver/safety claims,
- maintain stable ID-grounded reasoning,
- respect external-tool execution boundaries.

Start with instructions.md.
