# text-to-cad / cadpy / step.parts integration spike

Status: complete for issue #295. This is a bounded interop decision, not a
production import.

## Sources checked

- `earthtojake/text-to-cad` README and skill tree, 2026-06-19.
- `skills/cad/SKILL.md` in that repo, especially the STEP-first workflow,
  source-level joints, `cadpy.assembly.AssemblyHelper`, and positioning reference.
- `skills/step-parts/SKILL.md` in that repo, especially the hosted
  `https://api.step.parts` workflow and checksum/provenance guidance.
- AIENG local implementation: `aieng-ui/backend/app/cad_generation.py`,
  `aieng-ui/backend/tests/test_cad_generation.py`,
  `aieng-agent-skills/skills/aieng-cad-authoring/SKILL.md`, Assembly IR/mate
  predicate converters, and bd_warehouse standard-part tests.

## What text-to-cad does that improves modeling quality

1. It treats STEP as the primary generated artifact, but keeps authored Python
   source as the thing the agent edits.
2. It makes assembly positioning explicit in source: part-local frames, named
   mating datums, source-level joints, and an `AssemblyHelper` wrapper.
3. It validates generated geometry after creation with selector refs, facts,
   measurements, alignment deltas, and snapshots.
4. It searches off-the-shelf components through `step.parts` before drawing
   simplified placeholders for named purchasable parts.

The important mechanism is not a specific dependency. It is the discipline that
parts are positioned from named relationships and then checked, instead of being
placed by guessed `Location(x, y, z)` coordinates.

## Current AIENG coverage

AIENG already has the safer core of this pattern:

- `cad.execute_build123d` keeps generated Python source, topology, feature graph,
  geometry report, and snapshots inside the approval-gated MCP/package loop.
- The runner pre-binds relative positioning helpers:
  `centered_on`, `offset_from`, `coaxial`, and `stack_on`.
- `test_positioning_helpers_place_parts_relative` verifies those helpers in a real
  build123d/OCP run: `stack_on` puts a pin on a plate top face, and `coaxial`
  aligns a shaft's cross-axis center to a reference body.
- `cad.author_brief` plus `cad.validate_targets` gives a machine-checkable target
  contract for part counts, overall dimensions, named part sizes, no-floating,
  no-deep-overlap, coaxial, flush, and clearance checks.
- `cad.define_part`, `cad.define_interface`, and `cad.define_mate` let the agent
  record Assembly IR relationships after geometry exists. Mate predicates
  (`concentric`, `tangent`, `coincident`, `clearance`) are resolved through
  connection-geometry diagnostics instead of being trusted from prose.
- `geometry_report`, `cad.design_review`, and `cad.diagnose` flag floating parts,
  broken symmetry, deep overlaps, containments, and crude fidelity before a model
  is presented as done.
- Standard fasteners and similar components are already handled through
  `bd_warehouse` with feature-graph/BOM provenance. The runner records
  `standard_part`, `source_library`, canonical type, designation, and detection
  method where available.

This means our weak point is mostly agent adoption and enforcement: the available
contracts exist, but an external agent can still ignore them unless prompts,
tool schemas, and benchmarks make the safe path the obvious path.

## cadpy AssemblyHelper decision

Recommendation: do not add `cadpy` as a production dependency now.

Reasons:

- We already have a minimal internal equivalent for the common static placement
  cases (`stack_on`, `coaxial`, `centered_on`, `offset_from`) with tests.
- AIENG's Assembly IR and mate predicates are closer to our safety model than a
  general authoring helper: they separate "build placed geometry" from "record and
  validate engineering relationship".
- A new CAD authoring dependency would enlarge the packaged/runtime surface before
  we know which relationship vocabulary is missing.
- The immediate failure mode users see is not "missing cadpy"; it is agents
  skipping the existing brief -> relative placement -> validate -> diagnose loop.

Adopt the concept internally:

- Keep the current helpers in the runner.
- Add more relationship helpers only when a benchmark or dogfood failure proves a
  repeated need, for example `face_to_face`, `axis_offset`, or `bolt_pattern_on`.
- Treat helper output as geometry placement only. Engineering validity still
  requires `cad.validate_targets`, `cad.define_mate`, and `cad.diagnose`.

## step.parts decision

Recommendation: defer direct `step.parts` production integration; keep
bd_warehouse as the default standard-part path and create a separate optional
provenance/download task when packaged networking, caching, and checksum policy
are ready.

Reason to defer:

- AIENG currently needs reproducible local tests. A hosted catalog lookup is a
  network-dependent operation and should not become part of the default CAD build
  path or CI.
- `bd_warehouse` gives parametric standards for many fasteners/bearings/gears and
  can participate in feature graph, topology, BOM, and editable-source semantics.
- `step.parts` is most useful for named purchased components that are not
  parametric standards, such as servos, motors, connectors, boards, and vendor
  assemblies. Those imported STEP files need provenance, checksum, local cache,
  orientation inspection, and explicit envelope/mate validation before use.

Future safe integration shape:

1. Add a read-only MCP/catalog tool such as `aieng.search_catalog_parts`.
2. Return candidates with id, name, standard/family, attributes, source URL,
   checksum if present, and explicit `network_source`.
3. Download only after approval or explicit user request.
4. Store imported STEP under package provenance or a local cache with checksum.
5. Require geometry inspection before mating imported parts, because their origin
   and orientation are external facts.
6. Never execute external scripts from the catalog.

## Minimal prototype status

The local prototype is the existing internal relative-placement runner helper set
plus its build123d test:

- Helper implementation: `aieng-ui/backend/app/cad_generation.py`.
- Verification: `aieng-ui/backend/tests/test_cad_generation.py`,
  `test_positioning_helpers_place_parts_relative`.

That prototype covers the most common assembly-quality failure:

```python
plate = Box(80, 60, 10)
pin = stack_on(Cylinder(5, 20), plate, label="pin")
ref = Box(20, 20, 40).moved(Location((10, 20, 0)))
shaft = coaxial(Cylinder(3, 60), ref, axis="Z", label="shaft")
```

This is intentionally smaller than `AssemblyHelper`. It is easier to audit,
pre-bound inside the MCP runner, and compatible with approval-gated CAD mutation.

## Resulting recommendation

Adopt concepts, not dependencies:

- Adopt STEP/source discipline, source-level relationship naming, imported-part
  provenance, and post-generation measurement checks.
- Reimplement only the subset that improves benchmark/dogfood failures.
- Decline a production `cadpy` dependency until a specific relationship helper is
  missing from our internal runner and cannot be implemented cleanly.
- Defer `step.parts` to an optional catalog/download tool with cache/checksum and
  approval boundaries.

## Follow-up issues worth splitting later

- Add `face_to_face` / `axis_to_axis` internal positioning helpers with build123d
  tests.
- Add an assembly-positioning benchmark case that fails raw coordinate placement
  but passes helper + validate-target workflow.
- Add an optional catalog search/download tool for imported purchased components
  with checksum and package provenance.
- Make `cad.plan_build123d_skill` include `cad.author_brief` and
  `cad.validate_targets` instructions for any assembly-like starter.

## Honesty boundary

This spike does not claim parity with text-to-cad and does not certify CAD
quality. It records that AIENG already has the safer core mechanism for relative
positioning and should improve agent routing/benchmarks before importing new
authoring dependencies.
