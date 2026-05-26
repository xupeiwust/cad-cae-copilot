# Flange Benchmark Run Package (Phase 18C-min)

This directory is a coverage-probe scaffold for the flange fixture added in
the Phase 18C-min semantic benchmark refresh.

It provides two Condition B variants generated from `examples/definition_flange_001.yaml`:

- **rich variant**: includes task spec, evidence scaffold, external tool requirements, and
  consolidated validation resources.
- **sparse variant**: intentionally omits task/evidence resources to test missingness reasoning.

The flange fixture differs from the bracket and plate probes in:
- Part family: pipe flange with bolt-hole pattern (PCD-distributed) and pipe bore.
- Protected interfaces: both bolt-hole pattern (`feat_bolt_hole_pattern_001`) and pipe bore
  (`feat_pipe_bore_001`) are protected.
- Material: SS316L (stainless steel) rather than aluminium.
- Load: internal pressure on pipe bore rather than point force.

Use this fixture to test calibration behaviors:

- distinguish missing vs unsupported vs available states,
- avoid unsupported solver/safety claims,
- maintain stable ID-grounded reasoning,
- respect external-tool execution boundaries,
- handle a part with two simultaneously protected interfaces.

Start with [instructions.md](instructions.md).
