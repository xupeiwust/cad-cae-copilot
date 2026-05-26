# Adaptive CadQuery Iteration Contract

Use this contract for iterative CadQuery generation. It requires review after every iteration, but it does not require a fixed sequence such as prototype -> surface -> detail -> finish.

## Core Principle

The next iteration must be chosen from evidence, not from a preset phase list.

**Evidence-driven order is not permission to build everything in one iteration.** Each iteration still implements **one narrow scope** (one pipeline step, one subsystem, or one feature family). See [SKILL.md](SKILL.md) section *Single-focus iteration discipline*.

**A single iteration may not produce the complete requested model.** If one script contains most planned features, final polish, or out-of-scope geometry, the iteration fails the contract even if the script runs and exports valid STEP/STL.

Each iteration should answer one question:

- What did the previous review prove?
- What is the smallest meaningful source change now?
- Why is the next action `brainstorm`, `prototype`, `repair`, `proportion_refine`, `surface_refine`, `detail_add`, `simplify`, or `export_ready`?

Do not advance mechanically. If review exposes bad proportions after details were added, return to proportion repair. If a surface strategy is failing, simplify or re-plan before adding more features.

## Required Artifact Chain

Create or update these artifacts before final STEP/STL export:

```text
design_brief.md
feature_tree.json
iteration_plan.json (must include skill_constraints_handoff, in_scope, out_of_scope, deferred_features)
reference_sources.json (visible / named / reference-driven models)
object_agnostic_checklist.json (visible / reference-driven models)
reference_measurements.json (real products / reference-driven models)
reference_visual_checklist.json (visible models / product references)
required_functional_features.json (functional products / mechanisms)
decision_log.md
exports/pipeline/<iteration>/phase_gate.json
exports/pipeline/<iteration>/preflight_review.md
scripts/iteration_<nn>_<intent>.py
exports/pipeline/<iteration>/geometry_facts.json
exports/pipeline/<iteration>/cad_refs.json
exports/pipeline/<iteration>/render_views/front.png
exports/pipeline/<iteration>/render_views/side.png
exports/pipeline/<iteration>/render_views/top.png
exports/pipeline/<iteration>/render_views/iso.png
exports/pipeline/<iteration>/visual_review.html
exports/pipeline/<iteration>/render_unavailable.json (only if rendering failed)
exports/pipeline/<iteration>/review_packet.json
exports/pipeline/<iteration>/review_packet.md
feature_memory.json
```

`surface_plan.json` is required only when the model depends on lofts, sweeps, guide curves, silhouettes, or industrial-design surfaces.

`reference_measurements.json` and `required_functional_features.json` are required for named real products, reference-driven models, or any request with functional moving parts, load paths, service interfaces, contact surfaces, clearances, or other physical behavior.

`reference_visual_checklist.json` is required for visible CAD models. Follow [reference-fidelity.md](reference-fidelity.md). The default fidelity level is `refined_default`, upgraded to `reference_faithful` for named real products. Do not downgrade to "style", "inspired", "generic", "low-detail", or "simplified" unless the user explicitly asks for that.

`reference_sources.json` is required for visible, named, or reference-driven models. Follow [reference-acquisition.md](reference-acquisition.md). `reference_limited` and `inferred_only` block `reference_faithful export_ready`.

`object_agnostic_checklist.json` is required for visible or reference-driven models. Follow [object-agnostic-checklists.md](object-agnostic-checklists.md). Do not branch the main review logic by fixed object family.

`phase_gate.json` and `preflight_review.md` are required before each iteration script. `review_packet.json`/`.md` are required before any next iteration or `export_ready`. See [review-protocol.md](review-protocol.md).

Do not replace this chain with one `create_model.py` script for complex models.

Screenshots must be generated according to [rendering.md](rendering.md). Try Python offscreen rendering first, then browser-automated Three.js, then an installed external renderer. `render_unavailable.json` is allowed only after the attempted renderer and failure reason are recorded.

## Atomic Iteration Loop

This contract is an execution loop, not a batch-generation plan.

- Generate and run only the next iteration script.
- Do not prewrite, scaffold, or queue later `scripts/iteration_<nn>_*.py` files before the current iteration's Universal Review Gate passes.
- At any time there may be only one unreviewed iteration source file. If multiple new iteration scripts exist without intervening review artifacts, stop, mark the run invalid, and ask whether to delete or ignore the speculative scripts.
- The next iteration number, scope, and source target must be chosen after the previous review report is written.
- Every artifact that references a source file must point to a file that exists in the workspace. Missing source files, missing review artifacts, or stale `cad_refs.json` paths are hard failures.

## Phase Gate Contract

Each iteration is test-first. Write `exports/pipeline/<iteration>/phase_gate.json` before writing or widening the CadQuery source for that iteration.

`phase_gate.json` must include:

```json
{
  "iteration": "iteration_02_surface_refine",
  "phase_goal": "specific final-target gap this iteration reduces",
  "in_scope": [],
  "out_of_scope": [],
  "acceptance_tests": [],
  "reference_tests": [],
  "geometry_tests": [],
  "visual_tests": [],
  "functional_tests": [],
  "regression_tests": [],
  "remaining_gap": [],
  "exit_criteria": []
}
```

Each test must have:

```json
{
  "test_id": "dimension.feature.requirement",
  "dimension": "silhouette_axes | mass_distribution | part_topology | surface_language | signature_features | functional_interfaces | detail_hierarchy | manufacturing_logic | reference_alignment",
  "requirement": "measurable requirement",
  "evidence_required": [],
  "source_target": "planned source feature or file",
  "blocking_before_next_phase": true,
  "blocking_before_export_ready": true
}
```

Write `preflight_review.md` before modeling. It must confirm:

- every required test is measurable from geometry facts, references, screenshots, or direct source review.
- the phase goal reduces a named final-target gap rather than only making the current scope look acceptable.
- in-scope and out-of-scope boundaries are narrow enough for single-focus iteration.
- unresolved required or unknown dimensions from `object_agnostic_checklist.json` are carried into `remaining_gap`.

After modeling and review evidence generation, write `review_packet.json`. It includes gate results and the fail-first challenge review:

```json
{
  "iteration": "iteration_02_surface_refine",
  "quality_state": "repair",
  "fail_first_objections": [],
  "phase_gate_results": [
    {
      "test_id": "dimension.feature.requirement",
      "status": "pass | fail | partial | unknown | not_applicable",
      "evidence": [],
      "source_feature": "FeatureName",
      "repair_action": "specific source change or null",
      "remaining_gap": []
    }
  ],
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

Required `fail`, `partial`, or `unknown` results block the next phase unless the phase is explicitly exploratory and the unresolved item is moved to `remaining_gap`. Before `export_ready`, required `fail`, `partial`, `unknown`, and `not_inspected` are all failures.

## Iteration Loop

Every iteration follows this loop:

1. Perform iteration boundary rehydration: reread `SKILL.md`, this contract, `review-protocol.md`, the design brief, feature memory, latest geometry facts, latest CAD refs, latest review packet, the plan's `skill_constraints_handoff`, references, and object-agnostic checklist. Reread only applicable one-level reference files unless context was compacted, mode changed, or the task resumed; then reread every file listed in `skill_constraints_handoff`.
2. Brainstorm the next smallest useful action and record why that action was chosen.
3. Write `phase_gate.json` for the next iteration before modeling.
4. Write `preflight_review.md` proving the gate is measurable, single-focus, and converges toward the final target.
5. Implement one focused source change in a new or revised iteration script that respects **single-focus scope** (see [Single-focus scope](#single-focus-scope)); do not fold later pipeline stages into the same file.
6. Export STEP/STL for the iteration.
7. Generate `geometry_facts.json` and `cad_refs.json`, including source-file existence checks, disconnected-component evidence, and geometry quality metrics.
8. Generate or attempt screenshots.
9. Create template-compliant `visual_review.html`.
10. Directly inspect `front.png`, `side.png`, `top.png`, and `iso.png` as images when screenshots exist.
11. Write compact `review_packet.json` by comparing evidence against every `phase_gate.json` test and applying [review-protocol.md](review-protocol.md).
12. Write compact `review_packet.md` as a short human-readable summary. Expanded `geometry_review.md`, `functional_review.md`, `gate_results.json`, and `review_report.md` are optional compatibility reports only when explicitly needed.
13. Confirm the packet includes fail-first objections and, for final export, the Final Challenge Gate.
14. Decide the next action from gate and review evidence.
15. If the next action is not `export_ready` and the task should continue, **return to step 1** for the next single-focus iteration. The **agent** performs all review steps above; **human approval between iterations is not required** unless the user explicitly asked for manual gates. If intent is ambiguous or geometry is blocked, stop and ask the user.

The next action must be one of:

- `brainstorm`: requirements, strategy, or geometry is still ambiguous.
- `prototype`: build a first testable form or subsystem.
- `repair`: fix invalid geometry, failed booleans, missing refs, or broken exports.
- `proportion_refine`: improve silhouette, scale, landmarks, or massing.
- `surface_refine`: improve lofts, sweeps, transitions, curvature, or shell strategy.
- `detail_add`: add panels, seams, vents, bosses, ribs, fasteners, interfaces, or tertiary details.
- `simplify`: reduce fragile geometry or replace a failing strategy with a more stable one.
- `export_ready`: all required checks pass and remaining limitations are acceptable.

These are quality/action states, not mandatory phases and not a fixed order.

## Plan-mode constraint handoff

The planning artifact must carry the skill constraints into implementation. `iteration_plan.json` must include:

```json
{
  "skill_constraints_handoff": {
    "loaded_skill_files": [
      "CAD-Agent-Skills/SKILL.md",
      "CAD-Agent-Skills/pipeline-contract.md"
    ],
    "applicable_modes": [],
    "non_negotiable_gates": [],
    "iteration_scope_contract": {
      "in_scope": [],
      "out_of_scope": [],
      "deferred_features": []
    }
  }
}
```

If `skill_constraints_handoff` is missing or contradicts the skill files, stop and regenerate the plan before implementation. The handoff summarizes constraints for continuity across Plan and Agent modes; it never overrides `SKILL.md` or this contract.

## Single-focus scope

- Every iteration script must state **primary scope** and **explicitly out-of-scope** items at the top (docstring or comment block), so reviewers can reject “accidental full models.”
- `iteration_plan.json` must list `skill_constraints_handoff`, `in_scope`, `out_of_scope`, and `deferred_features`; these lists are hard boundaries for the script.
- **Partial exports are valid:** STEP/STL may represent only the scoped fragment (for example one part, one subsystem, or a minimal construction solid sufficient for the current review question).
- **Agent-driven continuation:** after the Universal Review Gate passes for iteration `nn`, the agent may immediately plan and implement iteration `nn+1` when evidence calls for it—**after** completing self-review for `nn`, not instead of it.
- **Full-model guard:** if an iteration output visually or structurally appears to be the whole requested model before `export_ready`, mark scope compliance as `fail`, remove extra features from source, and regenerate the iteration.

## Universal Review Gate

An iteration passes only when:

- `geometry_facts.json` exists and describes the current output.
- `phase_gate.json` exists and was written before the iteration script was implemented or widened.
- `preflight_review.md` exists and confirms all required phase tests are measurable and convergent.
- `review_packet.json` exists and evaluates every required phase-gate test.
- Required phase-gate tests have evidence; `fail`, `partial`, or `unknown` force `repair`, `refine`, `replan`, or `simplify` unless explicitly recorded as exploratory `remaining_gap`.
- For visible CAD models, `reference_visual_checklist.json` exists and the review includes a Reference Fidelity Audit.
- For visible or reference-driven models, `reference_sources.json` and `object_agnostic_checklist.json` exist.
- The output is not merely recognizable as a generic category; it meets the requested or inferred fidelity level.
- `geometry_facts.json` includes disconnected-component evidence: component count, per-component bbox/volume where available, largest-component volume ratio, and a list of unclassified small solids or shells.
- Every disconnected component is either intentionally classified in `cad_refs.json` with an attachment/load-path explanation or the review fails as `floating_geometry`.
- `cad_refs.json` names the major iteration features.
- Every source file path named in `geometry_facts.json`, `cad_refs.json`, `feature_tree.json`, or `review_packet.json` exists.
- `visual_review.html` exists and is template-compliant.
- Either required screenshots exist under `render_views/`, or `render_unavailable.json` explains the attempted renderer, command/import failure, reason, and fallback mode.
- If screenshots exist, the agent has directly inspected each primary PNG image and recorded per-view observations.
- The visual review includes the hard-fail defect audit from `visual-defects.md`.
- When functional checks apply, `review_packet.json` includes the audit from `functional-defects.md`.
- `review_packet.json` maps failed checks to source file, source feature, and targeted repair action.
- `review_packet.md` records the selected next action and why, citing `review_packet.json`.

Do not begin the next iteration until this gate passes. Do not choose `export_ready` if any required gate result, fail-first objection, reference row, or functional row is `fail`, `partial`, `unknown`, or `not_inspected`.

## Compact Review Packet Template

Each iteration writes `review_packet.json` plus a short `review_packet.md`. Use expanded reports only when requested or when a failure needs long-form diagnosis.

```markdown
# [Iteration Name] Review Packet

## State
- quality_state:
- export_ready: true | false
- next_action:

## Fail-First Objections
- blocker_id:
- objection:
- evidence:
- required_repair:

## Evidence Summary
- phase_gate:
- inspected_images:
- visual_defect_audit:
- reference_fidelity_audit:
- functional_audit:
- primitive_strategy_evidence:

## Required Next Actions
1. ...
```

## Geometry Review Gate

Each iteration review must be evidence-based:

- Compare `geometry_facts.json` against expected bbox, proportions, feature counts, and validity.
- Compare `review_packet.json` against `phase_gate.json`; every required test must have status, evidence, source feature, and repair action for failures.
- Verify the iteration reduced the `phase_goal` gap. If not, the next action must be `repair`, `replan`, or `simplify`.
- For visible CAD models, compare generated front/side/top/iso views against `reference_visual_checklist.json` and any inspected reference images; missing signature features, weak craftsmanship, generic-category fallback, or primitive symbolization is a failed check.
- For visible or reference-driven models, compare `reference_sources.json`, `object_agnostic_checklist.json`, and `reference_visual_checklist.json`; missing required dimensions or `reference_limited` state must remain visible in `remaining_gap`.
- Compare disconnected-component evidence against `cad_refs.json`; unexplained isolated solids, tiny remote shells, orphan detail pieces, or components with no plausible contact/load path are hard-fail `floating_geometry`.
- Treat unusually high `solid_count` or `shell_count` as suspicious until each disconnected component is named, classified, or proven attached within tolerance.
- Verify `iteration_plan.json` includes `skill_constraints_handoff` and that the implementation followed the listed non-negotiable gates.
- Compare `cad_refs.json` against `feature_tree.json` to find missing planned features.
- Compare the script, `cad_refs.json`, and screenshots against `iteration_plan.json` `in_scope`, `out_of_scope`, and `deferred_features`; any out-of-scope feature is a failed check.
- For real products or functional assemblies, compare `reference_measurements.json`, `required_functional_features.json`, `feature_tree.json`, `cad_refs.json`, and screenshots against [functional-defects.md](functional-defects.md); any missing required functional ref or failed functional audit row is a failed check.
- Compare visual review artifacts against silhouette, detail hierarchy, and industrial-design requirements.
- Directly inspect `front.png`, `side.png`, `top.png`, and `iso.png` as images before writing visual findings.
- Audit hard-fail visual defects from [visual-defects.md](visual-defects.md); each defect row must say `pass`, `fail`, or `not_applicable` with image evidence.
- Preserve `visual_review.html` as the human-readable review page for the iteration.
- Verify `visual_review.html` is generated from `visual-review-template.html` and contains `data-template="cadquery-visual-review-v1"`, `Interactive Three.js Viewer`, `Visual Defect Audit`, `three.module.js`, and `STLLoader`.
- If screenshots are missing, require `render_unavailable.json` with attempted renderer, command/import failure, reason, and fallback mode.
- Record failed checks in `review_packet.json` with source iteration, source feature, and targeted repair action.

If render views are unavailable, the review must explicitly say so, write `render_unavailable.json`, and rely on geometry facts plus the template-based Three.js/manual review path; do not claim screenshot inspection.

## Hard Stop Conditions

Stop and iterate instead of exporting when:

- The model is only recognizable because of labels or colors.
- The model is only recognizable as a generic category instead of a refined model of the requested object.
- A visible model lacks `reference_visual_checklist.json` or a Reference Fidelity Audit.
- A visible or reference-driven model lacks `reference_sources.json` or `object_agnostic_checklist.json`.
- `reference_sources.json` reports `reference_limited` or `inferred_only` while the target requires `reference_faithful export_ready`.
- Review language downgrades the target to "style", "inspired", "simplified", "low-detail", or "plausible" without explicit user approval.
- Required signature features from the reference checklist are absent, represented by blobs, or represented by primitive placeholders after the disposable prototype stage.
- The plan or `iteration_plan.json` lacks `skill_constraints_handoff`, or implementation proceeds from a plan that did not restate the skill constraints.
- `phase_gate.json` was not written before the iteration source change.
- `preflight_review.md` does not prove tests are measurable or convergent.
- `review_packet.json` is missing, incomplete, or does not evaluate every required phase-gate test.
- Any required gate result is `fail`, `partial`, `unknown`, or `not_inspected` before `export_ready`.
- The iteration does not reduce the `phase_goal` gap and the next action is not `repair`, `replan`, or `simplify`.
- The exterior is built from stacked primitives beyond a disposable prototype.
- Key silhouettes are wrong from any primary view.
- Visible surfaces are lumpy, faceted, or joined with hard boolean seams.
- Required visual features are missing from `cad_refs.json`.
- Required functional features, moving axes, clearances, load paths, or service interfaces are missing from `feature_tree.json`, `cad_refs.json`, or `review_packet.json`.
- A required functional feature is only decorative, such as a fixed camera where the reference implies a gimbal, or propeller marks that do not have plausible diameter, axis, and clearance.
- `review_packet.json` has unresolved failed checks.
- Functional checks apply but `review_packet.json`, `reference_measurements.json`, or `required_functional_features.json` is missing.
- `visual_review.html` is hand-authored or missing template compliance markers.
- Required screenshots are missing and `render_unavailable.json` is absent.
- Any iteration attempts to proceed without a completed visual review gate.
- A single `iteration_<nn>_*.py` implements multiple major pipeline stages, out-of-scope features, final polish, or most of the planned feature tree.
- A single iteration visually or structurally appears to be the complete requested model before `export_ready`.
- Visual findings are written from file paths, HTML, JSON, or logs without direct image inspection.
- The next iteration is chosen without citing review evidence.
- Any hard-fail visual defect is present, including interpenetration, floating geometry, misalignment, bad contact, coplanar overlap, impossible assembly, occluded feature, scale mismatch, or view inconsistency.
- Any unclassified disconnected component, orphan shell, remote tiny solid, or missing source file exists in the artifact chain.
