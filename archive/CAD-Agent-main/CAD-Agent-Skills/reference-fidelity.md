# Default Modeling Fidelity Gate

Use this gate for every CAD modeling task. Unless the user explicitly asks for a low-detail concept, rough blockout, simplified placeholder, stylized toy, or speed-first draft, the default target is a refined, high-detail, industrial-design-quality model. If the prompt names a real product or implies a reference-recognizable target, the default also includes reference-faithful visual identity even when the user did not provide an image.

Before modeling visible or reference-driven objects, follow [reference-acquisition.md](reference-acquisition.md), [object-agnostic-checklists.md](object-agnostic-checklists.md), and [review-protocol.md](review-protocol.md).

## Default Fidelity Rule

- Do not silently downgrade any requested model to "style", "inspired", "generic", "toy-like", "placeholder", or "simplified".
- Treat missing reference images as a reason to acquire references or enter `reference_limited`, not as permission to make a generic category symbol.
- "Recognizable as a broad category" is not sufficient. The model must include refined silhouette, major part topology, visible construction logic, and appropriate secondary/tertiary details.
- If exact fidelity is not feasible in one pass, continue with scoped proportion, surface, and detail refinement iterations instead of declaring `export_ready`.
- `partial`, `unknown`, `not_inspected`, `reference_limited`, and `inferred_only` are blocking states for `reference_faithful export_ready` unless the user explicitly accepts a lower fidelity target.
- Only use a simplified fidelity level when the user explicitly requests simplification, low-poly, schematic, rough prototype, placeholder geometry, or fast draft output.
- Reviews must challenge the output against the requested object, not the object category. A model that would be called "a robot", "a vehicle", "a chair", or "a gadget" but not the requested target fails `reference_mismatch`.

## Required Artifact

Create `reference_visual_checklist.json` before modeling any visible-design object. Also create `reference_sources.json` and `object_agnostic_checklist.json` when the object is visible or reference-driven. The visual checklist must include:

- `requested_target`: object name, reference identity, or target description.
- `fidelity_level`: `refined_default`, `reference_faithful`, `stylized`, or `simplified`; default is `refined_default`, upgraded to `reference_faithful` for named real products.
- `signature_features`: named visual features that must be present.
- `silhouette_landmarks`: front, side, top, and iso landmarks.
- `detail_hierarchy`: primary, secondary, and tertiary details expected for the object.
- `negative_examples`: shortcuts that must fail review, such as capsule fuselage, cylinder-only motors, box-only camera, generic X-frame, box-on-wheels car, or featureless appliance block.
- `acceptance_criteria`: per-feature pass/fail criteria.
- `blocking_unknowns`: required reference or dimension items that cannot pass until resolved or explicitly accepted.

## Review Requirements

Every visual review must include:

```markdown
## Reference Fidelity Audit
- fidelity_level:
- reference_images_inspected:
- silhouette_match:
- signature_feature_coverage:
- topology_match:
- detail_density:
- craftsmanship_level:
- primitive_symbolization:
- generic_category_fallback:
- missing_reference_features:
- required_refinement:
```

Rows must be recorded in `review_packet.json` and say `pass`, `fail`, `partial`, `unknown`, or `not_applicable` with image evidence. Do not mark `export_ready` if any required row is `fail`, `partial`, `unknown`, or `not_inspected`.

## Export-Ready Blockers

For visible or reference-driven models, do not choose `export_ready` when any of these are true:

- `reference_sources.json` is missing.
- `object_agnostic_checklist.json` is missing.
- `reference_state` is `reference_limited` or `inferred_only` for a `reference_faithful` target.
- Any required row in the Reference Fidelity Audit is `fail`, `partial`, `unknown`, or `not_inspected`.
- Any required dimension in `object_agnostic_checklist.json` remains `unknown` without explicit user acceptance.
- `review_packet.json` contains required tests with `fail`, `partial`, or `unknown`.
- `geometry_quality_metrics.primitive_stack_risk` is `high` for a complex visible model.
- `geometry_quality_metrics.primitive_stack_risk` is `medium` and required signature features remain primitive placeholders.
- Review wording claims only "recognizable", "plausible", "inspired", "style", or "roughly similar" while required reference features remain missing.

## Hard Failures

- The model reads as a generic object category rather than a refined model of the requested object.
- A complex product is represented mainly by capsule bodies, cylinders, boxes, or simple rods after the disposable prototype stage.
- Signature features are represented by labels, colors, or approximate blobs instead of modeled geometry.
- Review language says "style", "inspired", "recognizable", "plausible", or "simplified" while required shape/detail features are still missing.
- The review does not compare generated views against the visual checklist and available reference evidence.
