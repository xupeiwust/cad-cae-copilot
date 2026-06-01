# Review Protocol: Fail-First, Challenge, Compact

Use this protocol for every visible, reference-driven, or quality-critical CAD iteration.

## Fail-First Review

Review starts by assuming the model fails. Before listing improvements, write the strongest objections:

- What makes this output fail the requested object, not just the broad category?
- Does it read as a generic placeholder, primitive stack, icon, toy blockout, or unrelated simplified form?
- Which required signature features are missing, blob-like, decorative-only, or too primitive?
- What would the user most likely challenge if shown only the rendered images?

If any objection is blocking, the iteration status is `fail`, `partial`, or `repair`; it cannot be marked pass by saying the model is "recognizable", "plausible", "inspired", "simplified", or "acceptable".

## Build From Failure

Every next iteration must cite the failure it repairs:

```json
{
  "failure_id": "reference.head_signature_missing",
  "source_feature": "head.primary_identity",
  "repair_strategy": "replace block with section/profile-based geometry",
  "expected_visual_change": "front and iso views show target-specific head silhouette"
}
```

Do not add unrelated features while the cited failure remains unresolved.

## Final Challenge Gate

Before `export_ready`, answer these questions using the actual `front`, `side`, `top`, and `iso` images:

- If filenames, labels, and reports are hidden, can the target object be identified?
- Would a skeptical user reasonably call it a generic placeholder or primitive stack?
- Are all required signature features modeled as geometry and named in `cad_refs.json`?
- Are any required Reference Fidelity Audit rows `partial`, `unknown`, `not_inspected`, or softened by "acceptable" language?
- Does the primitive strategy evidence prove the model is not mainly stacked boxes, cylinders, spheres, or rods?

Any weak answer blocks `export_ready`.

## Compact Review Artifacts

Default to the compact review packet to reduce token and file churn:

```text
exports/pipeline/<iteration>/review_packet.md
exports/pipeline/<iteration>/review_packet.json
```

`review_packet.md` replaces `geometry_review.md`, `functional_review.md`, and `review_report.md` unless the user explicitly asks for expanded reports or a failure needs a long repair narrative.

`review_packet.json` replaces standalone `gate_results.json` in compact mode. It must include:

```json
{
  "iteration": "...",
  "quality_state": "prototype | repair | proportion_refine | surface_refine | detail_add | export_ready",
  "fail_first_objections": [],
  "phase_gate_results": [],
  "visual_defect_audit": {},
  "reference_fidelity_audit": {},
  "functional_audit": {},
  "signature_feature_evidence": [],
  "primitive_strategy_evidence": {},
  "required_next_actions": [],
  "final_challenge": {},
  "export_ready": false
}
```

Keep `phase_gate.json`, `preflight_review.md`, `geometry_facts.json`, `cad_refs.json`, screenshots, and `visual_review.html`; these remain required evidence.

## Expanded Reports

Use expanded reports only when needed:

- `geometry_review.md`: complex geometric failure analysis.
- `functional_review.md`: complex mechanisms, moving parts, or load paths.
- `review_report.md`: human-facing long-form summary.
- `gate_results.json`: compatibility with older workflows.

Expanded reports must not contradict the compact review packet.

## Blocker Clearing Rule

Do not clear an `export_ready_blocker`, `blocking_unknown`, or failed gate by editing a checklist directly. A blocker is cleared only when `review_packet.json` records:

- previous blocker id
- source feature repaired
- evidence files inspected
- before/after result
- final status

If that evidence is missing, the blocker remains active.
