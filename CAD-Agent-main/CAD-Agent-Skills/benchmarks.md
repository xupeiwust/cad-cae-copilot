# CadQuery Modeling Benchmarks

Use these benchmarks as sanity checks after substantial skill, pattern, or pipeline changes. They are not exhaustive tests; they keep the agent from regressing to rough one-shot geometry.

## Benchmark Rules

- Run at least one benchmark after major workflow changes when time allows.
- Use the same adaptive iteration contract as real work: brief, feature tree, iteration scripts, facts, refs, review, and next-action decisions.
- Do not judge success from export existence alone.
- Prefer the smallest benchmark that exercises the changed rule.

## Benchmark Set

### 1. Drone Body With Rotor Guards

Prompt:

```text
Create a compact cinewhoop-style drone body with a smooth central camera pod, four circular duct guards, motor hubs, battery hump, front camera opening, side vents, and small screw bosses. Use adaptive CadQuery iterations and avoid final primitive stacking.
```

Required features:

- `body.main_shell`
- `rotor.front_left_guard`, `rotor.front_right_guard`, `rotor.rear_left_guard`, `rotor.rear_right_guard`
- `camera.front_opening`
- `vent.side_array`
- `boss.mounting_points`

Failure conditions:

- Ducts are only flat torus-like rings with no body integration.
- Main body is a simple box or sphere stack.
- No side/top silhouette review exists.

### 2. Consumer Coffee Machine

Prompt:

```text
Create a compact espresso machine with a softened rectangular body, rounded top, front control panel, portafilter group head, drip tray, side seams, vents, buttons, and realistic panel gaps.
```

Required features:

- `body.main_housing`
- `panel.front_controls`
- `brew.group_head`
- `tray.drip_plate`
- `seam.side_split`
- `vent.side_slots`

Failure conditions:

- Front face lacks control/detail hierarchy.
- Tray and group head are not distinguishable.
- Edge breaks and panel gaps are missing.

### 3. Open Electronics Enclosure

Prompt:

```text
Create an open-top electronics enclosure with 2.5 mm walls, rounded exterior corners, four internal screw bosses, lid lip, side cable cutout, vent slots, and standoff holes.
```

Required features:

- `body.enclosure_shell`
- `lip.lid_interface`
- `boss.internal_standoffs`
- `cutout.cable_port`
- `vent.slot_array`

Failure conditions:

- Wall thickness is not represented.
- Bosses have no holes.
- Interior is not open.

### 4. Robot Joint Module

Prompt:

```text
Create a compact humanoid robot elbow joint module with two rounded link housings, central bearing cylinder, cable channel, bolt circle, split line, and rounded protective covers.
```

Required features:

- `joint.central_bearing`
- `link.upper_housing`
- `link.lower_housing`
- `bolt.bolt_circle`
- `channel.cable_path`
- `seam.cover_split`

Failure conditions:

- Joint axis is ambiguous.
- Bolt circle is not evenly distributed.
- Housings are blocky without rounded protective form.

### 5. Handheld Product Shell

Prompt:

```text
Create a handheld scanner shell with ergonomic tapered body, trigger recess, display window, grip seams, speaker holes, charging port, and soft bevels.
```

Required features:

- `body.ergonomic_shell`
- `recess.trigger`
- `window.display`
- `port.charging`
- `holes.speaker_array`
- `seam.grip_split`

Failure conditions:

- Ergonomic taper is absent.
- Trigger/window/port details are not visible.
- Shell has sharp raw edges.

## Benchmark Report Template

```markdown
# Benchmark Report

## Benchmark
Name:

## Generated Artifacts
- design_brief:
- feature_tree:
- geometry_facts:
- cad_refs:
- visual_review:
- exports:

## Pass
- ...

## Fail
- ...

## Regression Notes
- Did the model use focused iteration scripts?
- Did geometry facts cover required features?
- Did refs cover required features?
- Did review trigger source repair when needed?
```
