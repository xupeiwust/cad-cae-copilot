# CAD Fidelity Benchmark Scorecard v0

This scorecard is a deterministic regression layer for CAD authoring quality. It
checks explicit spatial and semantic criteria from `topology_map`,
`feature_graph`, and optional `geometry_report` artifacts.

It is not a visual-equivalence metric, not manufacturing certification, and not a
substitute for human review. It answers a narrower question: did a generated CAD
model include the measurable parts, features, proportions, and assembly signals
that the prompt required?

## Built-in Cases

The v0 portfolio lives in `app/cad_fidelity_benchmark.py` and contains at least
eight AIENG-authored prompts:

- `flange_m6_four_hole_pattern`
- `ribbed_mounting_plate`
- `open_top_housing_shell`
- `slotted_adjustment_bracket`
- `threaded_boss_plate`
- `clevis_pin_bracket`
- `two_plate_bolted_stack`
- `robot_joint_yoke`

Each case records:

- prompt text;
- source/provenance note;
- required named parts;
- required feature types and minimum counts;
- optional bounding-box proportion tolerance;
- optional floating-part or symmetry limits;
- explicit failure conditions.

## Machine-Readable API

```python
from app.cad_fidelity_benchmark import score_cad_fidelity_case

result = score_cad_fidelity_case(
    "flange_m6_four_hole_pattern",
    topology_map=topology_map,
    feature_graph=feature_graph,
    geometry_report=geometry_report,
)
```

The result uses format `aieng.cad_fidelity.scorecard.v0` and contains per-check
pass/fail records plus an honesty boundary. A block that exports successfully but
lacks semantic hole/bore features will fail the flange case.
