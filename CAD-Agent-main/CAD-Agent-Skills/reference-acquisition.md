# Reference Acquisition and Calibration

Use this gate before modeling any visible, reference-driven, named, or user-recognizable target. References may be user-supplied or agent-searched. Missing references are not permission to invent a generic model.

## Reference States

Every run must record one state in `reference_sources.json`:

- `user_supplied`: user provided images, drawings, CAD, dimensions, or written references.
- `agent_searched`: the agent found public reference evidence and recorded sources.
- `inferred_only`: no images or measured references were available; only prompt text and general knowledge were used.
- `reference_limited`: references are insufficient for the requested fidelity.

`reference_limited` and `inferred_only` may support `brainstorm`, `prototype`, `proportion_refine`, or `surface_refine`, but they block `reference_faithful export_ready` unless the user explicitly accepts the limitation.

## Required Artifacts

Before modeling a visible or reference-driven object, write:

```text
exports/pipeline/reference_sources.json
exports/pipeline/reference_measurements.json
exports/pipeline/reference_visual_checklist.json
exports/pipeline/object_agnostic_checklist.json
```

If reference images or web results are used, also write:

```text
exports/pipeline/reference_image_notes.md
```

## reference_sources.json

Minimum schema:

```json
{
  "reference_state": "user_supplied | agent_searched | inferred_only | reference_limited",
  "sources": [
    {
      "id": "ref_01",
      "type": "user_image | web_image | web_page | drawing | text | measurement",
      "path_or_url": "...",
      "view": "front | side | top | rear | iso | detail | unknown",
      "trust": "high | medium | low",
      "used_for": ["silhouette", "proportion", "surface_language", "signature_features"],
      "limitations": []
    }
  ],
  "insufficient_reference_reasons": [],
  "user_accepts_reference_limitations": false
}
```

## Calibration Rules

- Prefer user references over searched references.
- If the user does not provide references and web access is available, the agent may search for public references.
- Record source URL/path, view type, trust level, and what each source supports.
- Do not claim exact fidelity from a single weak or unknown-view reference.
- If sources conflict, choose conservative common features and record uncertainty.
- If no reference images are available, `reference_visual_checklist.json` must mark view-specific tests as `unknown` or `reference_limited`, not `pass`.

## Export-Ready Blockers

Do not choose `export_ready` when:

- `reference_state` is `reference_limited` or `inferred_only` and requested fidelity is `reference_faithful`.
- Required reference views are missing and the missing views affect silhouette, topology, or signature features.
- Any required reference-derived test in `phase_gate.json` or `review_packet.json` is `fail`, `partial`, or `unknown`.
- The review only says the object is recognizable as a broad category instead of matching recorded reference dimensions and features.
