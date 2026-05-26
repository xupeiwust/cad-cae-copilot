# Definition-sourced pipe flange coverage probe

This is a definition-sourced `.aieng` package.

No STEP geometry is present. The package contains structured feature, constraint, material, and coordinate-system definitions only.

The feature graph records semantic design intent. Its geometry references are semantic-only until a downstream geometry generator creates real CAD geometry and validation evidence.

This package must not be treated as solver or geometry validation evidence. No mesh has been generated, no solver has been run, and no manufacturing or stress claim has been validated.

## Design requirements

mass_target:
  objective: reduce_flange_ring_mass_without_changing_interfaces
  target_reduction_percent: 10
  protected_feature_ids:
  - feat_bolt_hole_pattern_001
  - feat_pipe_bore_001
structural_targets:
  max_von_mises_stress_mpa: 120
protected_interfaces:
- feat_bolt_hole_pattern_001
- feat_pipe_bore_001

## Simulation intent

type: static_structural
fixed:
- feat_bolt_hole_pattern_001
loads:
- target: feat_pipe_bore_001
  type: pressure
  value_n: 11781
  direction:
  - 0
  - 0
  - 1
  application: distributed_pressure_1_5_mpa_on_bore_area_7854mm2

## Known limitations

- No imported STEP geometry.

- No solver result evidence attached by default.

- Feature parameters are semantic intent only.


Model ID: `definition_flange_001`
