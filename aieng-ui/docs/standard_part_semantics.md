# Standard Part Semantics

AIENG Workbench treats recognized catalogue parts as semantic CAD objects, not
only anonymous solids. The initial integration focuses on `bd_warehouse`
standard parts authored through `cad.execute_build123d`.

## Recognition

The build123d runner records conservative metadata on topology solids when the
object type comes from `bd_warehouse.*`:

- `standard_part: true`
- `source_library: "bd_warehouse"`
- `source_module` and `source_class`
- `canonical_type`, one of `fastener`, `bearing`, `gear`, `thread`, `flange`,
  `washer`, `nut`, `screw`, `bolt`, or `unknown_standard_part`
- `designation` when safely readable from object attributes or an obvious metric
  label such as `M6-1`
- `object_label`, `original_label`, `detection_method`, and `confidence`

Feature graph generation promotes recognized solids from generic `named_part`
features to `standard_part` features while keeping them in the named-part list
used by lookup, source restore, append diffing, and project discovery.

## Face Pointers

The symbolic B-Rep graph propagates standard-part context from the parent solid
or feature group onto each face. `@face:<id>` and `@group:<id>` entries can expose:

- parent standard-part metadata
- `canonical_type` and `source_library`
- conservative `face_role_hint` values such as `head_top`, `head_side`,
  `shank_side`, `bearing_face`, `washer_face`, or
  `unknown_standard_part_face`

Hints are intentionally modest. The system does not infer thread engagement,
bolt preload, contact state, supplier identity, strength, or simulation validity
from standard-part recognition alone.

## BOM Summary

When standard parts are present, `graph/feature_graph.json` includes a lightweight
`metadata.standard_parts` summary with counts by canonical type and the detected
items. This is a semantic inventory for agent context, not a purchase-ready BOM.
