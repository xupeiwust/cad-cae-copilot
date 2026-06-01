# Visual Defect Taxonomy

Use this reference during every visual review. These defects are hard review failures unless the design brief explicitly requires them.

## Hard-Fail Defects

- `interpenetration`: parts visibly pass through each other without an intentional joint, cut, socket, or overlap.
- `floating_geometry`: a part appears suspended without support, attachment, fastener, hinge, bracket, or contact surface.
- `disconnected_components`: the exported shape contains isolated solids, shells, or tiny remote fragments that are not intentionally classified, attached, or supported by a named load path.
- `misalignment`: circles, axes, arrays, mirrored parts, rails, seams, buttons, ports, or repeated details are visibly offset from their intended centerline or symmetry.
- `bad_contact`: parts that should touch have an unintended gap, or parts that should have clearance collide.
- `coplanar_overlap`: thin plates, panels, seams, decals, or detail strips overlap on the same plane in a way that causes z-fighting or ambiguous surfaces.
- `impossible_assembly`: handles, pipes, trays, buttons, hinges, sockets, bosses, ribs, or covers do not connect in a mechanically plausible way.
- `occluded_feature`: a required feature is hidden, buried, clipped, or counted as present even though it cannot be visually inspected.
- `scale_mismatch`: small features have visibly implausible size, for example oversized buttons, too-thin rods, unusable slots, or tiny structural supports.
- `view_inconsistency`: a feature looks plausible in one view but is misplaced, floating, or intersecting in another primary view.
- `decorative_required_feature`: a required functional feature is represented only by a cosmetic cue, for example propeller spokes without plausible blade diameter/clearance or a fixed camera where a gimbal is required.
- `reference_mismatch`: the output reads as a generic category, simplified icon, low-detail placeholder, or "style" approximation instead of matching the requested/default fidelity level, signature silhouette, topology, craftsmanship, and detail hierarchy.
- `unresolved_gate`: a required `phase_gate.json` test is `fail`, `partial`, `unknown`, or lacks evidence in `review_packet.json`.
- `primitive_stack_overuse`: a complex visible model still relies on high-risk primitive stacking after the disposable prototype stage, or cannot prove the visible identity is driven by profiles, surfaces, proportions, and named signature geometry.

## Required Defect Audit

Every visual review must include a defect audit with these rows:

```markdown
## Visual Defect Audit
- interpenetration:
- floating_geometry:
- disconnected_components:
- misalignment:
- bad_contact:
- coplanar_overlap:
- impossible_assembly:
- occluded_feature:
- scale_mismatch:
- view_inconsistency:
- decorative_required_feature:
- reference_mismatch:
- unresolved_gate:
- primitive_stack_overuse:
```

Each row must say `pass`, `fail`, or `not_applicable`, followed by observed evidence from inspected images, `geometry_facts.json`, `phase_gate.json`, or `review_packet.json`.

`reference_mismatch` must be audited with [reference-fidelity.md](reference-fidelity.md) for visible CAD models. Do not mark it `pass` because the object is recognizable as the broad category.

`unresolved_gate` must be audited with `review_packet.json`. Required tests marked `partial` or `unknown` are failures before `export_ready`.

`primitive_stack_overuse` must be audited with `geometry_facts.json` `geometry_quality_metrics` and `review_packet.json` `primitive_strategy_evidence`. A complex visible model with `primitive_stack_risk: high` cannot be `export_ready`; a `medium` risk also blocks export if required signature features are still box/cylinder/sphere/rod placeholders.

`floating_geometry` cannot be judged from screenshots alone. The review must also use `geometry_facts.json` disconnected-component evidence: component count, per-component bbox/volume when available, largest-component volume ratio, and any unclassified small solids or shells. If a component is disconnected and not explicitly named in `cad_refs.json` with an attachment or load-path explanation, mark `floating_geometry` and `disconnected_components` as `fail`.

## Export-Ready Rule

Do not mark an iteration `export_ready` if any hard-fail defect is visible in `front.png`, `side.png`, `top.png`, `iso.png`, or required diagnostic views.

Do not mark an iteration `export_ready` if geometry facts show unexplained disconnected solids/shells, orphan detail pieces, or remote tiny components, even when the primary screenshots look recognizable.

Do not mark an iteration `export_ready` if `reference_mismatch` fails for any visible CAD model.

Do not mark an iteration `export_ready` if `unresolved_gate` or `primitive_stack_overuse` fails.

Do not clear `reference_mismatch` or `primitive_stack_overuse` with positive adjectives such as "recognizable", "plausible", "clean", "acceptable", or "stylized". The pass requires named geometry evidence in `cad_refs.json` and inspected view evidence in `review_packet.json`.

When a hard-fail defect is found:

1. Set the next action to `repair` or `simplify`.
2. Map the defect to source file, source feature, and likely parameter or transform.
3. Regenerate the responsible iteration.
4. Re-render and directly inspect the affected views again.

Do not downgrade a hard-fail defect to "acceptable" because the overall silhouette is recognizable.

For models with moving or functional parts, also run [functional-defects.md](functional-defects.md). A visually recognizable feature is not sufficient when the requested object requires mechanism, clearance, load path, or service access.
