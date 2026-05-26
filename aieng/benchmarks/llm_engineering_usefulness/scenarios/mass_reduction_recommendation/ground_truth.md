# Ground truth — mass_reduction_recommendation

## The setup

A steel bracket has been solved under a 5 kN lateral load. Yield strength is
350 MPa. The acceptance criteria live in `task/design_targets.yaml` inside
the package:

| Target id | Target type | Comparator | Threshold | Priority |
|---|---|---|---|---|
| `mass_reduce_10pct` | `mass_reduction_target` | `reduce_by_at_least` | 10.0 percent | high |
| `safety_factor_min` | `minimum_safety_factor` | `>=` | 1.5 | critical |

Equivalently: max von Mises stress ≤ 350 / 1.5 ≈ 233 MPa anywhere in the
kept geometry after the change, AND mass must drop by at least 10 percent
relative to the 2.30 kg baseline.

Both Condition A and Condition B receive the same targets — A through the
raw artifact dump (which now includes `task/design_targets.yaml`), B through
structured package access via the AIENG tool surface.

Per-feature stress, as recorded in `results/stress_by_feature.json`:

| Feature | Max stress | SF | Mass |
|---|---|---|---|
| `back_wall` | 22 MPa | 15.9 | 1.51 kg |
| `central_rib` | 195 MPa | 1.79 | 0.38 kg |
| `mounting_hole` | 195 MPa | 1.79 | -0.012 kg (hole) |
| `mounting_bosses` | 48 MPa | 7.3 | 0.09 kg |
| `flange` | 110 MPa | 3.18 | 0.24 kg |
| `reinforcement_gusset` | 65 MPa | 5.4 | 0.07 kg |

The model is asked to choose one of four proposed changes (presented in
the prompt):

- **A** — Thin `back_wall` from 20 mm to 10 mm
- **B** — Remove `central_rib` entirely
- **C** — Enlarge `mounting_hole` from 10 mm to 15 mm diameter
- **D** — Reduce `mounting_bosses` count from 4 to 2

## The correct answer

**A — thin the `back_wall`.**

The `back_wall` sits at 22 MPa, far from the 233 MPa allowable. Even a
significant thickness reduction leaves an enormous margin. It also has the
single largest mass contribution (1.51 kg of a 2.30 kg total), so the mass
saved is meaningful.

The other three options all fail the safety constraint in obvious ways:

- **B** removes a feature already at SF 1.79 — *barely* meeting the
  constraint with the central_rib carrying load. Remove it and the load
  redistributes to surrounding features, almost certainly violating SF 1.5.
- **C** enlarges a hole that already has a stress concentration at 195 MPa.
  Larger hole → larger stress concentration → almost certainly exceeds the
  233 MPa allowable.
- **D** reduces bosses that contribute little mass (0.09 kg total for the
  group, so removing half saves ~0.045 kg) and compromises the mounting
  interface. Mass saving is negligible compared to A.

## What a correct answer looks like

A correct response must:

1. **Name option A** (or `back_wall`, or "thin the back wall", or
   "Answer: A").
2. **Cite evidence** — reference the 22 MPa stress, the SF 15.9, or the
   "lowest stress" / "highest safety factor" framing.

A response that names A without evidence is partial credit. A response
that names B, C, or D is incorrect — even if it gives plausible-sounding
reasoning, the engineering answer is wrong.

A correct response should also respect `task/design_targets.yaml`:
- The `safety_factor_min` target (≥ 1.5) is the floor B / C would violate.
- The `mass_reduce_10pct` target (≥ 10 percent of 2.30 kg ≈ 0.23 kg) is
  satisfied only by option A in practice — back_wall is 1.51 kg, so thinning
  it to half thickness drops well above the 10 percent floor. Option D
  saves ≈0.045 kg (≈2 percent) and fails the mass-reduction target as well
  as compromising the mounting interface.

The rubric does not currently penalize responses that ignore the explicit
target names; it scores on the engineering answer (option A) and evidence
grounding. Future rubric versions may add a target-citation criterion.

## Anti-hallucinations to watch for

- Claiming the central_rib is over-designed because it carries most of the
  load (wrong — load-carrying does not mean over-designed; SF 1.79 means
  it is *near* the constraint floor).
- Claiming the mounting_hole can be enlarged "to redistribute stress"
  (wrong — enlarging concentrates stress, doesn't redistribute it).
- Citing displacement values as a reason to choose A (the prompt is about
  stress safety factor, not deflection).
- Inventing stress values not in `stress_by_feature.json`.
