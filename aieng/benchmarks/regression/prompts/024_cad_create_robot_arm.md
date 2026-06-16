---
id: 024_cad_create_robot_arm
tags: [complex, cad_create, assembly, mechanical, kinematic]
---

Model a 3-DOF serial robotic arm as a kinematic chain of named links posed in a
single configuration. Requirements:

- `base`: a cylindrical base Ø80 x 20mm tall, sitting on Z=0.
- Joint 1 (revolute about Z) on top of the base, carrying `shoulder_link`:
  a 30mm-wide x 40mm-tall x 160mm-long arm segment rising and reaching outward.
- Joint 2 (revolute, horizontal axis) at the end of the shoulder, carrying
  `elbow_link`: a 24mm x 30mm x 130mm segment.
- Joint 3 (revolute, horizontal axis) at the end of the elbow, carrying
  `wrist`: a short 40mm segment ending in a simple `end_effector` (a 20mm cube
  or two-finger stub).
- Represent each joint as a visible cylindrical hub (Ø30) at the link junction
  so the rotation axis is legible. The links must actually connect end-to-end
  (no floating segments); pose the arm in a bent configuration (e.g. shoulder up
  ~45°, elbow forward ~60°) so the chain is clearly articulated, not collinear.

Name the parts: `base`, `joint1_hub`, `shoulder_link`, `joint2_hub`,
`elbow_link`, `joint3_hub`, `wrist`, `end_effector`. Color the links, the joint
hubs, and the base/end-effector distinctly. Declare link lengths and joint
angles as UPPER_SNAKE_CASE constants so the pose can be edited.

Acceptance signals: all 8 named parts present; links connect end-to-end (no
floating parts in `geometry_report`); the chain is non-collinear (a real bent
pose); changing a joint-angle constant via `cad.edit_parameter` re-poses the
downstream links without detaching them.
