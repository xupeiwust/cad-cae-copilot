# Object-Agnostic CAD Checklists

Use this reference to build checklists without relying on fixed object categories such as robot, vehicle, drone, appliance, or furniture. Extract review dimensions from the prompt, references, and geometry intent.

## Core Principle

Do not start with an object-family template. Start with dimensions that any object can have:

- shape and silhouette
- massing and scale
- part topology
- surface language
- signature features
- functional interfaces
- detail hierarchy
- manufacturing logic
- reference alignment

For each dimension, mark it as `required`, `optional`, `not_applicable`, or `unknown`. Required and unknown dimensions must be tracked in phase gates. Unknown dimensions cannot silently pass before `export_ready`.

## Required Artifact

Write `exports/pipeline/object_agnostic_checklist.json` before the first modeling iteration for visible or reference-driven models.

Minimum schema:

```json
{
  "target": "requested object name or description",
  "dimension_states": {
    "silhouette_axes": "required",
    "mass_distribution": "required",
    "part_topology": "required",
    "surface_language": "required",
    "signature_features": "required",
    "functional_interfaces": "unknown",
    "detail_hierarchy": "required",
    "manufacturing_logic": "optional",
    "reference_alignment": "required"
  },
  "dimensions": {
    "silhouette_axes": {
      "tests": [],
      "unknowns": [],
      "acceptance": []
    },
    "mass_distribution": {
      "tests": [],
      "unknowns": [],
      "acceptance": []
    }
  },
  "export_ready_blockers": []
}
```

## Dimension Definitions

### silhouette_axes

Primary views, centerlines, axes, width/height/depth ratios, negative spaces, outer contour landmarks, and view-specific read.

### mass_distribution

Primary, secondary, and support volumes; visual weight; balance; symmetry or intentional asymmetry; scale relationships between major masses.

### part_topology

Named parts, nesting, repeated arrays, connections, separations, interfaces, exposed vs hidden components, and dependency graph.

### surface_language

Flat, curved, faceted, lofted, swept, revolved, organic, industrial, soft, hard, edge breaks, transitions, curvature continuity, and primitive-stack risk.

### signature_features

Local features that make the requested target itself, not just its broad category. These may come from user text, references, brand/product identity, mechanism requirements, or visible design cues.

### functional_interfaces

Contact surfaces, support points, moving axes, sockets, latches, service seams, openings, airflow paths, handles, load paths, clearances, and assembly logic.

### detail_hierarchy

Primary forms, secondary panels/interfaces, tertiary seams/vents/fasteners/edge breaks, with scale rules for each level.

### manufacturing_logic

Wall thickness, split lines, draft-like bevels, assembly direction, fasteners, clearances, printable or machinable constraints, and service access when relevant.

### reference_alignment

Mapping between reference evidence and geometry: proportions, topology, silhouette landmarks, signature feature coverage, and uncertainty notes.

## Phase Gate Usage

Every `phase_gate.json` must include only dimensions relevant to that phase, but must carry forward unresolved required or unknown dimensions in `remaining_gap`. `review_packet.json` must record whether each carried dimension was repaired, deferred, or still blocking.

Example test entry:

```json
{
  "test_id": "silhouette.front.primary_width_ratio",
  "dimension": "silhouette_axes",
  "requirement": "front-view primary width ratio matches reference_measurements within tolerance",
  "status_before_modeling": "not_run",
  "evidence_required": ["front.png", "geometry_facts.geometry.dimensions"],
  "blocking_before_export_ready": true
}
```

## Export-Ready Rules

Do not choose `export_ready` when:

- any required dimension has `fail`, `partial`, or `unknown` results in `review_packet.json`.
- `signature_features` are represented by labels, colors, blobs, or primitive placeholders instead of modeled geometry.
- `surface_language` required a refined or reference-faithful result but `primitive_stack_risk` remains `high`.
- `reference_alignment` is required but references are missing, uninspected, or not mapped to geometry.
- a required functional interface has no named CAD reference or plausible load/contact/clearance evidence.
- a blocker was removed from `export_ready_blockers` without before/after evidence in `review_packet.json`.
