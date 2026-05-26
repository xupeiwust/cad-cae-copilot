# CAD/CAE Emitter and Writeback Capability Contract

This document defines how external CAD/CAE software, plugins, scripts, and workflow adapters can emit or write back `.aieng` resources.

The goal is tool-agnostic interoperability. `.aieng` should not be tied to one CAD kernel, CAE solver, agent framework, or workflow runtime. FreeCAD, Siemens NX, CATIA, SolidWorks, Onshape, Abaqus, Ansys, Gmsh, CalculiX, Simcenter, mechanical_agent, or future tools can participate by mapping their own data into the same structured package resources.

## Core positioning

`.aieng` is primarily a CAD/CAE-side semantic export and evidence layer.

Agent-facing tools such as CLI commands, MCP tools, and workflow adapters are access interfaces. They are windows into the package, not the core product. The core product is the structured `.aieng` package and the contract that CAD/CAE-side tools use to emit semantic state and write back evidence.

The intended direction is:

```text
CAD/CAE tools emit or write back structured resources
        ?
.aieng package is the source-of-truth semantic/evidence layer
        ?
AI/agent tools inspect the package and propose/request actions
        ?
External CAD/CAE tools execute geometry, mesh, solver, or manufacturing work
        ?
.aieng records evidence, claims, trace, and remaining missingness
```

## Best-effort conversion principle

Emitters should use best-effort semantic conversion with explicit missingness.

That means:

1. Convert information that is actually available from the source tool.
2. Preserve stable IDs and source references wherever possible.
3. Mark missing, unknown, partial, unsupported, or conflicting information explicitly.
4. Do not fabricate feature labels, material data, boundary conditions, solver results, mesh evidence, or geometry-modification evidence.
5. Update `validation/completeness_report.json` so AI readers know what is available and what is missing.

A package with partial information is acceptable if the absence is explicit.

Non-negotiable rule:

1. Emitters must only convert known information from source CAD/CAE artifacts and metadata.
2. Unknown or unmappable information must be written as explicit unknown/partial/missing/unsupported state.
3. Emitters must not guess unknown engineering facts to make the package look complete.
4. Violating this rule breaks the `.aieng` trust model for AI reasoning and handoff safety.

## Source-of-truth rule

Structured JSON/YAML resources are authoritative. Markdown summaries are derived aids.

For example:

- `geometry/topology_map.json` is authoritative for topology IDs when present.
- `graph/feature_graph.json` is authoritative for feature candidates and their grounding.
- `simulation/setup.yaml` is authoritative for simulation intent.
- `results/evidence_index.json` is authoritative for evidence state; claim proposals are review artifacts requiring human review.
- `provenance/tool_trace.json` is authoritative for recorded external tool steps.
- `validation/completeness_report.json` is authoritative for explicit missingness/completeness state.
- `README_FOR_AI.md` and `ai/summary.md` help AI readers, but must not be the only place where important engineering facts exist.

## Capability levels

Tools can implement only the level they can honestly support. Higher levels include lower-level capabilities where applicable.

| Level | Name | Typical tools | Main purpose |
|---:|---|---|---|
| L0 | Artifact reference only | any CAD/CAE export script | Attach source artifacts without semantic claims |
| L1 | Topology-aware CAD emitter | CAD API, OCC/OpenCascade, NX/Open API, FreeCAD | Emit stable topology references |
| L2 | Feature-aware CAD emitter | CAD feature tree, named selections, MBD/PMI-aware tools | Emit candidate or confirmed feature semantics |
| L3 | Simulation-aware CAE emitter | CAE preprocessor, solver deck parser | Emit material/load/BC/setup context |
| L4 | Evidence-aware writeback | mesher, solver, postprocessor, CAD executor | Write evidence, claims, and provenance after execution |
| L5 | Roundtrip-aware adapter | workflow orchestrator, mechanical_agent, CAD/CAE automation | Read task/patch/handoff, execute externally, write back evidence |

## L0: Artifact reference only

Minimum emitter capability: attach source artifacts and identify them in `manifest.json`.

Typical resources:

```text
geometry/source.step
geometry/normalized.step
simulation/solver_deck.inp
simulation/cae_imports/source_solver_deck.inp
results/artifacts/*
```

Rules:

- Do not claim topology, features, simulation setup, mesh, or solver results unless structured resources/evidence exist.
- If the source is only a STEP file, mark feature semantics and engineering intent as missing or unknown.
- Run or provide `validation/completeness_report.json` to expose missing information.

## L1: Topology-aware CAD emitter

A topology-aware CAD emitter writes stable topology references.

Required or expected resources:

```text
geometry/topology_map.json
```

Recommended fields include:

- body IDs
- face IDs
- edge IDs
- vertex IDs when available
- surface type
- bounding boxes
- area/length/radius/axis/normal when available
- source backend/provenance metadata

Rules:

- IDs should be stable within the exported package.
- If IDs are not stable across CAD re-export, say so in metadata or notes.
- Topology does not imply engineering feature truth.
- Missing topology details should be recorded as missing/partial, not inferred.

## L2: Feature-aware CAD emitter

A feature-aware CAD emitter writes semantic feature candidates or confirmed CAD features.

Expected resources:

```text
graph/feature_graph.json
graph/aag.json
ai/protected_regions.json
objects/interface_graph.json
visual/annotation_layers.json
```

Feature semantics may come from:

- CAD feature tree
- named selections
- PMI/MBD annotations
- user annotations
- rule-based recognition
- external feature-recognition tools

Rules:

- Mark feature confidence and source.
- Distinguish `candidate` from CAD/user-confirmed feature truth.
- Protected regions must list forbidden operations explicitly.
- Do not treat hole-like geometry as protected mounting holes unless that intent is provided or clearly marked as candidate.

## L3: Simulation-aware CAE emitter

A simulation-aware CAE emitter writes setup/context, not results.

Expected resources:

```text
simulation/setup.yaml
graph/constraints.json
simulation/cae_imports/parsed_materials.json
simulation/cae_imports/parsed_boundary_conditions.json
simulation/cae_imports/parsed_loads.json
simulation/cae_mapping.json
```

Rules:

- Simulation setup is intent/context, not solver evidence.
- Materials, loads, boundary conditions, solver target, and validation targets should reference feature IDs, interface IDs, topology IDs, or explicit CAE entity IDs.
- If CAE entities cannot be mapped to CAD/feature IDs, mark them as unmapped in `simulation/cae_mapping.json` and partial/missing in `validation/completeness_report.json`.
- Do not claim mesh generation or solver execution from setup files alone.

## L4: Evidence-aware writeback

Evidence-aware tools write back what external tools actually produced.

Expected resources:

```text
results/evidence_index.json
provenance/tool_trace.json
validation/status.yaml
validation/completeness_report.json
```

Claim proposals are review artifacts requiring human review.

Typical evidence-producing tools:

- CAD tools that produced a modified geometry artifact
- meshers that produced mesh files and quality reports
- solvers that produced result files
- postprocessors that produced validation reports
- manufacturing checkers that produced check reports

Rules:

- Evidence must reference actual artifacts or external references.
- `pass` and `fail` claims require `actual_evidence_ids`.
- `unsupported` means evidence is absent; it does not mean the claim is false.
- `.aieng` core does not generate solver evidence, mesh evidence, or CAD geometry modification evidence.
- `provenance/tool_trace.json` records what external tools report they did; it is audit/provenance, not validation by itself.

## L5: Roundtrip-aware adapter

A roundtrip-aware adapter can read `.aieng` task/patch/handoff resources, call external tools, and write back artifacts/evidence.

Reads:

```text
task/task_spec.yaml
task/external_tool_requirements.json
ai/patches/*.json
graph/feature_graph.json
ai/protected_regions.json
validation/completeness_report.json
```

Writes back:

```text
geometry/modified_*.step
simulation/updated_deck.inp
results/evidence_index.json
provenance/tool_trace.json
validation/completeness_report.json
```

Claim proposals are review artifacts requiring human review.

Rules:

- The adapter may execute external tools; `.aieng` core itself does not.
- Preserve protected regions and forbidden operations.
- Record failed, skipped, and successful external steps.
- After execution, update evidence and claim state rather than relying on prose.
- If a requested operation cannot be executed because required information is missing, record the missingness and refusal reason.

## Definition-sourced semantic emitter

`aieng define` provides a non-CAD entry path:

```text
structured YAML model definition
        ?
definition-sourced .aieng semantic package
        ?
future external CAD generator or CAD/CAE emitter
```

This mode is not a CAD emitter and does not generate geometry. It is a semantic-definition source that can provide design intent, semantic features, requirements, manufacturing assumptions, material context, and simulation intent before any STEP/B-rep exists.

A definition-sourced package should still follow this contract:

- set `manifest.json` `source_mode: definition`;
- write semantic features to `graph/feature_graph.json`;
- write constraints to `graph/constraints.json`;
- write context such as material and coordinate system under `engineering_context/`;
- write `validation/status.yaml` with `definition_sourced: true` and geometry generation marked `not_implemented`;
- write `validation/completeness_report.json` immediately so missing geometry/topology and unsupported mesh/solver evidence are explicit.

For capability-level purposes, definition-sourced packages are closest to L0 plus semantic L2 intent: they can describe features and requirements, but they do not provide CAD topology or executable geometry until a downstream CAD generator or CAD emitter writes those resources.

## Mapping examples

### FreeCAD / OpenCascade-style CAD emitter

Can start at L0/L1:

```text
geometry/source.step
geometry/topology_map.json
graph/aag.json
validation/completeness_report.json
```

If named objects or scripted features are available, it may reach L2 by emitting `graph/feature_graph.json` and `ai/protected_regions.json`.

### Siemens NX / CATIA / SolidWorks-style CAD emitter

Can potentially reach L2 or L5 if API access exposes feature tree, named faces, PMI/MBD annotations, and geometry modification automation.

The emitter should still map all proprietary objects into `.aieng` IDs and avoid storing proprietary-only semantics solely in prose.

### Abaqus / Ansys / Simcenter-style CAE emitter

Can start at L3 by writing `simulation/setup.yaml` or parsed CAE resources, then reach L4 by writing result evidence after solver execution.

Mesh/solver output should be referenced as artifacts and connected to claims through evidence IDs.

### Gmsh / CalculiX-style open tool writeback

Can implement L4:

```text
results/evidence_index.json
provenance/tool_trace.json
```

For example, a mesher writes mesh evidence and quality report references. A solver writes solver result evidence; claim proposals are review artifacts requiring human review.

### mechanical_agent-style orchestrator

Can implement L5 as an adapter/orchestrator:

1. Read `.aieng` task, handoff, protected regions, patch proposals, and completeness report.
2. Decide which external CAD/CAE tool to call.
3. Let the external tool execute.
4. Write back trace, evidence, claim status, and updated completeness.

The adapter is not the source of truth. The `.aieng` package remains the source-of-truth semantic/evidence record.

## Forbidden emitter behavior

Emitters and adapters must not:

- fabricate solver results, mesh evidence, geometry modification evidence, or manufacturing validation;
- mark claims as `pass` without actual evidence IDs (claim proposals require human review);
- treat Markdown summaries as source of truth;
- silently infer protected regions, materials, loads, boundary conditions, or feature truth;
- overwrite geometry resources without explicit operation and provenance;
- hide missing information instead of recording it in `validation/completeness_report.json`;
- claim `.aieng` core executed CAD/CAE tools when execution happened externally.

## Recommended minimal profiles

### CAD-only minimum

```text
manifest.json
geometry/source.step
validation/completeness_report.json
```

### Topology-aware CAD minimum

```text
manifest.json
geometry/source.step
geometry/topology_map.json
validation/completeness_report.json
```

### Feature-aware CAD minimum

```text
manifest.json
geometry/source.step
geometry/topology_map.json
graph/feature_graph.json
ai/protected_regions.json
validation/completeness_report.json
```

### CAE setup minimum

```text
manifest.json
simulation/setup.yaml
graph/constraints.json
validation/completeness_report.json
```

### Evidence writeback minimum

```text
manifest.json
results/evidence_index.json
provenance/tool_trace.json
validation/completeness_report.json
```

Claim proposals are review artifacts requiring human review.

## Validation expectations

After an emitter or adapter writes resources, run:

```bash
aieng write-completeness-report model.aieng --overwrite
aieng summarize model.aieng --overwrite
aieng validate model.aieng
```

A valid partial package is acceptable. The important requirement is that missingness and unsupported claims remain explicit.

