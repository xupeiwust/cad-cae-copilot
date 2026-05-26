# Functional Defect Taxonomy

Use this reference for any model with required moving parts, load paths, contact surfaces, service interfaces, clearances, or other physical behavior. Derive required functions from the prompt, references, and `object_agnostic_checklist.json`, not from fixed object-family templates.

## Required Functional Artifacts

For real-product or function-bearing requests, create these artifacts before `export_ready`:

- `reference_measurements.json`: target dimensions, proportions, measured or estimated ratios, and uncertainty notes.
- `required_functional_features.json`: required moving parts, load paths, clearances, interfaces, and feature-specific acceptance criteria.
- `review_packet.json`: evidence-based audit of the functional checks below under `functional_audit`. Write `functional_review.md` only as an expanded compatibility report when needed.

## Hard-Fail Functional Defects

- `missing_required_function`: a requested or reference-critical function is absent.
- `decorative_required_feature`: a required functional feature exists only as a cosmetic shape and has no plausible mechanism, interface, clearance, or load path.
- `missing_kinematic_axis`: a moving part has no visible or named pivot, hinge, slider, or rotation axis.
- `impossible_motion_clearance`: a moving part has no clearance envelope for its expected motion.
- `scale_ratio_mismatch`: feature ratios are implausible against reference measurements, adjacent geometry, or functional clearance requirements.
- `axis_misalignment`: functional axes do not align with their supports, clearances, or motion paths.
- `missing_load_path`: a loaded or supported feature has no plausible structural path back to its support body.
- `missing_service_interface`: a serviceable, removable, or accessible part lacks rails, latch, seam, screws, socket, opening, or other access cue when required.
- `unsafe_or_impossible_clearance`: parts that need airflow, rotation, heat, user access, or assembly clearance collide or are visibly blocked.

## Required Functional Audit

Every functional review must include:

```markdown
## Functional Plausibility Audit
- missing_required_function:
- decorative_required_feature:
- missing_kinematic_axis:
- impossible_motion_clearance:
- scale_ratio_mismatch:
- axis_misalignment:
- missing_load_path:
- missing_service_interface:
- unsafe_or_impossible_clearance:
```

Each row must say `pass`, `fail`, or `not_applicable`, followed by evidence from `reference_measurements.json`, `required_functional_features.json`, `cad_refs.json`, `geometry_facts.json`, and inspected images when available.

## Dimension-Based Functional Checks

For any function-bearing object, generate required checks from these dimensions:

- Motion: named axis, travel direction, clearance envelope, stops, and support relationship.
- Contact: mating faces, support surfaces, grips, feet, seats, sockets, or contact patches.
- Load path: how force moves from functional feature to support body.
- Flow or access: openings, vents, channels, service gaps, removal paths, and blocked-clearance risks.
- Ratio: functional feature size compared with nearby clearance, support, or reference measurements.
- Assembly: split lines, fasteners, tabs, rails, hinges, bosses, or other plausible connection cues.

## Export-Ready Rule

Do not mark `export_ready` while any required functional feature is missing, decorative-only, unreferenced in `cad_refs.json`, or failing its scale, axis, clearance, or load-path check.
