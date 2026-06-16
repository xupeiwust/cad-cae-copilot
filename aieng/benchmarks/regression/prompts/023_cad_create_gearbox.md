---
id: 023_cad_create_gearbox
tags: [complex, cad_create, assembly, mechanical]
---

Model a single-stage spur gearbox as a multi-part assembly. Requirements:

- A rectangular housing 120mm (X) x 80mm (Y) x 60mm (Z), wall thickness 5mm,
  open at the top with a removable cover plate (5mm thick) that matches the
  housing footprint.
- An input shaft and an output shaft, both 12mm diameter, running along X,
  their axes 50mm apart in Y and centered in Z. Each shaft is supported by a
  bearing bore (Ø22, one in each end wall) — so 4 bearing bores total, coaxial
  in pairs.
- A small spur gear on the input shaft (pitch Ø30) and a larger spur gear on the
  output shaft (pitch Ø50); model them as simple toothless disks of those
  diameters and 8mm width for this benchmark, positioned so their pitch circles
  are tangent (center distance = 40mm, matching the 50mm shaft spacing minus
  overlap — use the 40mm pitch tangency to place them and report any mismatch).
- A 4-bolt pattern (Ø5 clearance) joining the cover to the housing, one near
  each corner, ≥ 2× radius from the edges.

Name the parts: `housing`, `cover`, `input_shaft`, `output_shaft`,
`gear_input`, `gear_output`, and the bearing bores / bolt holes as feature
groups. Color the housing/cover, shafts, and gears in three distinct colors.
Declare key dimensions (wall thickness, shaft diameter, bore diameter, gear
diameters, center distance) as UPPER_SNAKE_CASE constants so they can be edited.

Acceptance signals: all 6 named parts present; shafts coaxial with their bearing
bore pairs; the two gears tangent at the stated center distance (report the
actual gap); cover footprint matches the housing; no floating parts.
