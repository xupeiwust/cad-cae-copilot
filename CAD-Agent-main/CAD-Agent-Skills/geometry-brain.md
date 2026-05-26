# Geometry Brain

Use this reference for iterative CadQuery models that need evidence-based review and repair. The goal is to make every iteration observable, measurable, referable, and repairable from source.

## Required Evidence Loop

```text
iteration source
  -> STEP/STL export
  -> geometry_facts.json
  -> cad_refs.json
  -> visual review evidence
  -> review_packet.json / review_packet.md
  -> targeted source repair
```

Never advance to the next iteration, or mark a model `export_ready`, from text self-review alone.

## geometry_facts.json

Write one facts file per iteration under `exports/pipeline/<iteration>/geometry_facts.json`.

Minimum schema:

```json
{
  "iteration": "iteration_02_surface_refine",
  "quality_level": "surface_refine",
  "source_file": "scripts/iteration_02_surface_refine.py",
  "exports": {
    "step": "exports/pipeline/iteration_02_surface_refine/iteration_02_surface_refine.step",
    "stl": "exports/pipeline/iteration_02_surface_refine/iteration_02_surface_refine.stl"
  },
  "geometry": {
    "bbox": [-120, 120, -80, 80, -20, 55],
    "dimensions": [240, 160, 75],
    "volume": 123456.7,
    "solid_count": 1,
    "face_count": 64,
    "edge_count": 192,
    "shell_count": 1,
    "valid": true
  },
  "detected_features": [
    {
      "ref": "body.main_shell",
      "type": "primary_body",
      "intent": "main visible exterior shell",
      "bbox": [-100, 100, -55, 55, -15, 45],
      "evidence": "largest valid solid"
    }
  ],
  "checks": {
    "bbox_within_expected": true,
    "volume_positive": true,
    "feature_tree_coverage": "partial",
    "primitive_stacking_detected": false
  }
}
```

Use facts to compare the generated geometry against the design brief, feature tree, surface plan, and expected proportions.

## cad_refs.json

Write stable references under `exports/pipeline/<iteration>/cad_refs.json`.

Minimum schema:

```json
{
  "iteration": "iteration_03_detail_add",
  "refs": {
    "body.main_shell": {
      "kind": "solid",
      "intent": "primary exterior housing",
      "source_feature": "SurfaceEnvelope",
      "source_file": "scripts/iteration_02_surface_refine.py",
      "bbox": [-100, 100, -55, 55, -15, 45]
    },
    "panel.top_seam": {
      "kind": "cosmetic_feature",
      "intent": "service split line around top cover",
      "source_feature": "TopPanelSeam",
      "source_file": "scripts/iteration_03_detail_add.py",
      "depends_on": ["body.main_shell"]
    }
  }
}
```

Reference naming rules:

- Use stable semantic names, not generated object indices.
- Prefer `system.subsystem.feature`: `body.main_shell`, `rotor.front_left_guard`, `vent.side_array`.
- Include source file and source feature so repairs target the right iteration.
- Preserve existing refs across iterations unless a feature is intentionally replaced.

## Geometry Review Packet

Write `exports/pipeline/<iteration>/review_packet.json` and `review_packet.md` after every iteration.

The review must cite evidence:

- Geometry facts: bbox, dimensions, volume, counts, detected features.
- CAD refs: which planned features are present or missing.
- Visual review: template-compliant `visual_review.html`, directly inspected view files, or explicit `render_unavailable.json`.
- Visual defect audit: hard-fail defects from `visual-defects.md`, each with pass/fail/not_applicable and image evidence.
- Repair mapping: failed check -> source file -> source feature -> next action.

Compact Markdown template:

```markdown
# iteration_02_surface_refine Review Packet

## State
- quality_state:
- export_ready:
- next_action:

## Fail-First Objections
- blocker_id:
- objection:
- evidence:
- required_repair:

## Evidence
- geometry_facts: exports/pipeline/iteration_02_surface_refine/geometry_facts.json
- cad_refs: exports/pipeline/iteration_02_surface_refine/cad_refs.json
- visual_review: exports/pipeline/iteration_02_surface_refine/render_views/

## Inspected Images
- front: observed ...
- side: observed ...
- top: observed ...
- iso: observed ...

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

## Required Next Actions
1. Failed check / defect class / source iteration / source feature / repair action
```

## Repair Rules

- Repair source first: edit the responsible `iteration_XX_*.py` or shared helper, then regenerate explicit targets.
- Do not patch derived STEP/STL files.
- Do not restart the entire model unless the base proportions are invalid.
- If a visual feature is missing from `cad_refs.json`, add or rename the source feature instead of relying on comments.
- If geometry facts disagree with the design brief, change parameters or section profiles before adding detail.
- If an iteration remains rough, choose another evidence-driven iteration and keep quality below `export_ready`.
- If any hard-fail visual defect is visible, choose `repair` or `simplify`; do not choose `export_ready`.
