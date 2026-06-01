# Visual Review

Use this reference for visual checks on iterative CadQuery models. Visual review is mandatory evidence after every iteration, not a prose guess. Preserve a human-readable HTML review page for every iteration.

## Required Views

For every iteration, produce or request these views under `exports/pipeline/<iteration>/render_views/`:

- `front.png`
- `side.png`
- `top.png`
- `iso.png`

Generate these views using [rendering.md](rendering.md). The default automatic path is Python offscreen rendering from the exported STL.

Optional diagnostic views:

- `wire_iso.png` for topology density and primitive-stacking detection.
- `section.png` for wall thickness, internal supports, and clearances.
- `detail_contact_sheet.png` for vents, panel lines, fasteners, seams, and small features.

Use [visual-defects.md](visual-defects.md) during every image inspection. Hard-fail defects block `export_ready`.

For every visible CAD model, also use [reference-fidelity.md](reference-fidelity.md), [reference-acquisition.md](reference-acquisition.md), and [object-agnostic-checklists.md](object-agnostic-checklists.md). The visual review must compare generated views against `reference_visual_checklist.json`, `object_agnostic_checklist.json`, and any available reference evidence, not just judge whether the object category is recognizable.

## Agent Image Inspection Gate

After screenshots are generated, the agent must directly inspect the PNG files as images before writing `review_packet.json` or marking the iteration visual review as passed:

- `exports/pipeline/<iteration>/render_views/front.png`
- `exports/pipeline/<iteration>/render_views/side.png`
- `exports/pipeline/<iteration>/render_views/top.png`
- `exports/pipeline/<iteration>/render_views/iso.png`

Do not infer visual quality from filenames, HTML, JSON, logs, or text summaries. The review must be based on observed image content. If image loading is unavailable, record that as a visual review failure or renderer-unavailable fallback; do not claim visual inspection was performed.

The review must state:

- which image files were inspected
- which reference checklist entries and available reference images were inspected
- which `phase_gate.json` tests were evaluated in `review_packet.json`
- what was observed in each primary view
- which visual defects map to which source feature
- what source change is required

## Review HTML

For every iteration, create or preserve:

- `exports/pipeline/<iteration>/visual_review.html`

Use [visual-review-template.html](visual-review-template.html) as the template. The HTML page must be directly viewable by the user and should include:

- iteration name and quality/action state
- links to `geometry_facts.json`, `cad_refs.json`, and `review_packet.md`
- front, side, top, and iso images
- optional diagnostic images
- pass/fail findings
- source repair actions
- Interactive Three.js STL/GLB viewer for inspection

The HTML review page is a derived review artifact. Do not make it the source of truth. The source of truth remains CadQuery source, pipeline JSON artifacts, and generated STEP/STL files.

Non-negotiable template compliance:

- Do not hand-author a simplified HTML page.
- `visual_review.html` must be generated from `visual-review-template.html` or a byte-for-byte copied template with placeholder replacement.
- The generated HTML must contain `data-template="cadquery-visual-review-v1"`.
- The generated HTML must contain the `Interactive Three.js Viewer` section.
- The generated HTML must contain the `Visual Defect Audit` section.
- The generated HTML must reference `three.module.js` and `STLLoader`.
- The generated HTML must reference `render_views/front.png`, `render_views/side.png`, `render_views/top.png`, and `render_views/iso.png`.
- If any of these markers are missing, visual review fails and the iteration cannot pass review.

## Three.js Review

Three.js is the default interactive review layer, but it is not the default automatic screenshot writer:

- Use STL or GLB as the viewer input; STEP should remain the primary CAD artifact but usually needs STL/GLB conversion for browser review.
- Prefer generated screenshots for agent review evidence because they are stable and easy to cite.
- Include an interactive Three.js section in `visual_review.html` for human inspection.
- If local browser security blocks auto-loading relative STL/GLB files, keep the HTML file usable via file input or by serving the iteration directory with a local static server.
- A static Three.js HTML page can render to a canvas, but it does not reliably write PNG files to disk by itself.
- Three.js counts as screenshot generation only when browser automation, such as Playwright or Puppeteer, saves `front.png`, `side.png`, `top.png`, and `iso.png`.
- Do not mark Three.js unavailable if the HTML template can still offer manual file input inspection, but do not count manual inspection as generated screenshot evidence.

## Review Checklist

For every iteration, check:

- Silhouette: front, side, and top views match the design brief.
- Reference fidelity: visible models match the required signature features, topology, craftsmanship level, and detail hierarchy from `reference_visual_checklist.json`.
- Proportion: major dimensions and mass distribution are plausible.
- Surface continuity: visible transitions are intentional, not lumpy primitive intersections.
- Detail hierarchy: primary, secondary, and tertiary details are distinct.
- Symmetry: mirrored or repeated features align consistently.
- Realism: part gaps, panel seams, bevels, vents, bosses, and edge breaks have realistic scale.
- Manufacturing plausibility: shell thickness, ribs, holes, and service gaps make sense.
- Defect audit: check interpenetration, floating geometry, misalignment, bad contact, coplanar overlap, impossible assembly, occluded features, scale mismatch, and view inconsistency.
- Generic fallback: fail the review if the output reads as a generic object category, simplified icon, or low-detail placeholder when the user did not explicitly request that fidelity level.
- Gate results: fail the review if required `phase_gate.json` tests are missing from `review_packet.json` or are marked `fail`, `partial`, or `unknown` without a repair/refine action.
- Primitive strategy: fail `export_ready` if `geometry_quality_metrics.primitive_stack_risk` is `high` for a complex visible model.

## Adaptive Quality Cues

- `prototype`: silhouettes and landmarks should become testable; details can be absent.
- `proportion_refine`: front, side, and top views should improve scale, massing, and landmark placement.
- `surface_refine`: primary exterior surfaces should replace rough primitive stacking where visible quality matters.
- `detail_add`: panel lines, vents, bosses, seams, sockets, and repeated details should become visible where required.
- `repair` or `simplify`: the review should prove that the targeted defect or fragile strategy improved.
- `export_ready`: final edge breaks, materials metadata, and limitations must be documented.
- `export_ready`: all hard-fail visual defects must be `pass` or `not_applicable`.
- `export_ready`: Reference Fidelity Audit rows must pass; `partial`, `unknown`, and `not_inspected` block final export.
- `export_ready`: "recognizable", "plausible", "style", "inspired", or "simplified" is insufficient unless explicitly requested by the user.
- `export_ready`: `reference_limited`, unresolved required object-agnostic dimensions, unresolved gate tests, and high primitive-stack risk block final export.

## Visual Review Packet

Add visual findings to `review_packet.md` and structured rows to `review_packet.json`:

```markdown
## Visual Review
- html: exports/pipeline/iteration_02_surface_refine/visual_review.html
- front: exports/pipeline/iteration_02_surface_refine/render_views/front.png
- side: exports/pipeline/iteration_02_surface_refine/render_views/side.png
- top: exports/pipeline/iteration_02_surface_refine/render_views/top.png
- iso: exports/pipeline/iteration_02_surface_refine/render_views/iso.png

## Inspected Images
- front: observed ...
- side: observed ...
- top: observed ...
- iso: observed ...

## Visual Findings
- Fail:
- Partial/Unknown:
- Pass:

## Phase Gate Results
- phase_gate: exports/pipeline/iteration_02_surface_refine/phase_gate.json
- review_packet: exports/pipeline/iteration_02_surface_refine/review_packet.json
- required_tests_failed:
- required_tests_partial_or_unknown:
- remaining_gap:

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

## Visual Defect Audit
- interpenetration:
- floating_geometry:
- misalignment:
- bad_contact:
- coplanar_overlap:
- impossible_assembly:
- occluded_feature:
- scale_mismatch:
- view_inconsistency:
- reference_mismatch:
- unresolved_gate:
- primitive_stack_overuse:

## Visual Repair Actions
1. Source file:
   Source feature:
   Action:
```

## Renderer Unavailable

If no screenshot render tool is available:

- Write `visual_review_unavailable: true` in the iteration review.
- State which methods were attempted, for example `pyvista import failed` or `threejs-playwright unavailable`.
- Write `exports/pipeline/<iteration>/render_unavailable.json` with attempted renderer, reason, and fallback mode.
- Do not claim visual inspection was performed.
- Continue with geometry facts, CAD refs, template-based Three.js/manual review, and conservative repair actions.
- Still create `visual_review.html` from the template with unavailable status and links to geometry facts.
- Do not proceed to the next iteration unless `visual_review.html` is template-compliant and `render_unavailable.json` exists.
- Do not mark any model `export_ready` if visual confidence is essential and no screenshot review was possible.
