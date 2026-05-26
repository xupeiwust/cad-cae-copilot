# Definition-sourced plate with hole-pattern probe

This is a definition-sourced `.aieng` package.

No STEP geometry is present. The package contains structured feature, constraint, material, and coordinate-system definitions only.

The feature graph records semantic design intent. Its geometry references are semantic-only until a downstream geometry generator creates real CAD geometry and validation evidence.

This package must not be treated as solver or geometry validation evidence. No mesh has been generated, no solver has been run, and no manufacturing or stress claim has been validated.

## Design requirements

mass_target:
  objective: reduce_mass_without_changing_mounting_interface
  target_reduction_percent: 12
  protected_feature_ids:
  - feat_hole_pattern_001
structural_targets:
  max_von_mises_stress_mpa: 140
protected_interfaces:
- feat_hole_pattern_001

## Simulation intent

type: static_structural
fixed:
- feat_hole_pattern_001
loads:
- target: feat_load_interface_001
  type: force
  value_n: 350
  direction:
  - 1
  - 0
  - 0

## Known limitations

- No imported STEP geometry.

- No solver result evidence attached by default.

- Feature parameters are semantic intent only.


Model ID: `definition_plate_with_pattern`
