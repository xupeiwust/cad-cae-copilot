# Complex-benchmark baseline (023 gearbox, 024 robot arm)

Reference-build baseline for the two `complex` prompts: build each target with
build123d and score against `COMPLEXITY_RUBRIC.md`. Run:

```bash
conda run -n aieng311 python gearbox_023_reference.py
conda run -n aieng311 python robot_arm_024_reference.py
```

**Scope of this baseline.** This is the *buildability + yardstick* baseline — it
proves the targets are achievable and gives the rubric concrete reference scores.
It is **not** the agent-path score (an external agent driving the live MCP loop,
recorded via `init_run.py` / `record.py`); that run needs the backend up and was
deferred (the dev backend was down from an unrelated `--reload` restart at the
time, and the in-session MCP server predated the new tools).

## Scores

| Signal | 023 gearbox | 024 robot arm |
|--------|-------------|---------------|
| builds | ✅ | ✅ |
| part_count | 6 | 8 |
| expected parts present | ✅ | ✅ |
| structural sanity | walls 5mm ≥ 3mm CNC | links connect end-to-end (FK), no floating |
| dimensional / pose | volumes computed per part | 60° elbow bend, non-collinear, tip (277,0,89) |
| honesty | gear mesh gap **10mm → gears_mesh:false** (prompt's 40mm-vs-50mm inconsistency reported, not "fixed") | editable pose via `SHOULDER_ANGLE_DEG`/`ELBOW_ANGLE_DEG` constants |

## What the baseline confirms

1. **The kernel is not the limit** — both genuinely complex models build cleanly.
   The difficulty is *coordination across parts*, exactly as the gap analysis said.
2. **The new slices are relevant**: the gearbox's 10mm gear gap is precisely the
   kind of mismatch the interface/connection-geometry validation (slice c2) flags
   — define the gears as parts + interfaces + a `contact_proxy` mate and the
   connection geometry comes back `invalid`/`warning` (`far_apart`).
3. **The rubric scores cleanly** and the honesty boundary holds (mismatch surfaced).

## Next gaps surfaced (the point of running it)

- **Domain-aware mate predicates.** Connection-geometry validation judges generic
  plausibility (centroid distance / bbox overlap / normal alignment) but does not
  understand *engineering* mates: `concentric` (shaft-in-bore within clearance),
  `tangent` (gear pitch circles mesh), `coincident` (faces flush). The gearbox
  needs "pitch circles tangent?" and "shaft coaxial with its 2 bores?" — currently
  hand-checked. **Most actionable extension of slice (c2).**
- **Kinematic joints.** The arm's chain is hand-computed forward kinematics baked
  into the script (editing a joint constant re-poses it via re-execution, which
  *works* for v0). The Assembly IR has connections but no joint model (revolute /
  prismatic axis + angle + DOF). A joint type + FK would make pose a first-class,
  validated edit rather than script-encoded.
- **Placement assistance.** The agent hand-computed every part's position (gear on
  shaft, link at the end of the previous link). A minimal placement helper
  (`at_end_of`, `concentric_with`, `on_face`) would cut the coordination burden
  that makes complex one-shot builds fail.

These are the evidence-backed candidates for the slice *after* templates — more
valuable than templates (d), which remain the lowest-leverage item.

## Agent-path run (live MCP, gearbox 023, project 902fd6d7104f)

Ran the gearbox through the live MCP loop (`cad.execute_build123d` →
`cad.design_review` → `cad.edit_parameter`) after the backend restart. Results:

- **Build**: 6/6 named parts, `floating=0`, `viewer_ready_glb`, reads as a
  gearbox in all 4 views. `design_review`: **passes** (0 findings).
- **`regression_diff` fix validated live**: widening `BORE_DIA` 22→26 (an internal
  bearing bore) returned `verdict: clean` + `internal_feature_change: true`
  (`housing` volume +6.38%, bbox Δ 0). Before this turn's fix that read
  "identical / parameter had no effect" — the trust-layer false-negative is gone.
- **`critique_diff`** honestly flagged the 26mm bore as a non-standard drill
  (closest 27mm) — useful DfM feedback on the edit.

Gaps **confirmed on a real complex model** (worse than on the NEMA part):
- *Over-labeling (#289)*: bearing bores → `mounting_hole`, bolt holes →
  `mounting_hole_pattern`, and the housing bottom → `base_plate` (thickness 60mm =
  the whole housing). The mechanical heuristic mis-reads a gearbox housing.
- *Parameter cross-binding (#288)*: `gear_input` AND `gear_output` features each
  carry BOTH `gear_in_pitch_dia` and `gear_out_pitch_dia` (both constants matched
  the "gear" token). Editing "gear_input pitch" is ambiguous — name-only binding
  cross-pollutes.
- *No mate/clearance awareness*: `design_review` passes despite the gears being
  10mm from meshing — confirming **domain-aware mate predicates** as the right
  next slice.

Not yet exercised live: `cad.validate_subpart` / `cad.define_*` — they are on the
backend (84 tools) but this Claude Code session's MCP tool list predates them;
calling them needs an MCP reconnect (not a `dev.py` restart). Already test-validated.

## Modeling-quality demo (crude vs scaffolded gearbox)

`aieng-ui/backend/scripts/gearbox_quality_demo.py` builds the SAME gearbox two
ways through the real pipeline and scores both with the modeling-fidelity check:

| build | parts | fidelity |
|-------|-------|----------|
| crude (`Box - Box` + flat disks) | 4 | **40 / crude** — no edge-breaking, raw primitives |
| scaffolded (`housing()` + `boss()` bearing seats + `rib()` + `mounting_tab()` feet + `rounded_box()` cover) | 16 | **95 / designed** |

This closes the loop on the "gearbox looks bad" report: lever-1 (fidelity) flags
the crude build for the right reason, lever-2 (scaffolds) fixes it, and the score
moves crude→designed. Two heuristic false-positives surfaced by the demo were
fixed in the same pass: parts inside a HOLLOW enclosure (bearing seats/gears in a
housing) are no longer penalised as "hidden" (judged via per-solid volume vs bbox
volume), and a filleted boxy mechanical part is no longer docked hard for lacking
loft/sweep (mild note only). Internal gears/seats are correct engineering, not a
quality defect.
