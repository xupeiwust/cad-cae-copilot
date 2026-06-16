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
