# AGI Handoff Worked Example

This walkthrough shows how `.aieng` supports an AI/AGI-assisted CAD/CAE handoff without becoming an agent runtime, CAD kernel, mesher, solver, optimizer, or manufacturing checker.

The example is intentionally conservative. It demonstrates the information flow and evidence discipline, not a real CAD/CAE execution.

## Positioning

`.aieng` is the CAD/CAE-side semantic export and evidence package. Agent-facing tools such as CLI and MCP are optional access interfaces.

In this walkthrough:

```text
CAD/CAE emitter writes .aieng resources
        ?
agent reads structured package state
        ?
agent proposes task/patch/handoff
        ?
external CAD/CAE tools execute outside .aieng
        ?
adapter writes back evidence/claims/trace/completeness
        ?
validator checks consistency and summaries explain current state
```

The `.aieng` package remains the source-of-truth record. The agent is a consumer/proposer. External tools execute.

## Scenario

User intent:

```text
Reduce mass by 15% while keeping mounting holes unchanged.
```

Engineering boundary:

- mounting holes or hole pattern must remain protected;
- CAD geometry modification, meshing, solving, and manufacturing checks are external-tool responsibilities;
- `.aieng` records semantic state, requests, evidence, provenance, and missingness;
- unsupported claims are not false; they simply lack attached evidence.

## Step 1: CAD/CAE-side emitter creates or enriches the package

A CAD/CAE-side emitter writes whatever information it can honestly provide.

Example commands for a local scaffold/demo package:

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng --overwrite
aieng extract-topology build/bracket_001.aieng --overwrite
aieng build-aag build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng write-completeness-report build/bracket_001.aieng --overwrite
aieng summarize build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

Relevant resources:

```text
manifest.json
geometry/source.step
geometry/topology_map.json
graph/aag.json
graph/feature_graph.json
graph/constraints.json
ai/protected_regions.json
simulation/setup.yaml
validation/completeness_report.json
README_FOR_AI.md
ai/summary.md
```

Expected interpretation:

- topology and feature candidates are available when generated;
- protected regions are available if user/CAD/CAE context provided them;
- simulation setup is intent/context, not solver evidence;
- completeness report states which CAD/CAE information is available, partial, missing, or unsupported.

## Step 2: Agent reads package state

An agent can read the package directly or via optional MCP/CLI access.

Recommended first resources:

```text
manifest.json
validation/completeness_report.json
validation/status.yaml, if present
README_FOR_AI.md
ai/summary.md
graph/feature_graph.json
ai/protected_regions.json
simulation/setup.yaml
results/evidence_index.json, if present
provenance/tool_trace.json, if present
```

Optional MCP tools can expose the same information:

```text
get_manifest
get_completeness_report
get_feature
get_task_spec
get_external_tool_requirements
get_evidence_index
get_tool_trace
get_summary
```

Claim proposals require human review.

The agent should answer from structured resources first. It should not infer missing material, load, boundary condition, protected-region, mesh, solver, or geometry-modification information.

## Step 3: Agent or user writes a task contract

The task is recorded as structured data:

```bash
aieng write-task-spec build/bracket_001.aieng \
  --intent "Reduce mass by 15% while keeping mounting holes unchanged." \
  --task-id task_mass_reduce_001 \
  --overwrite
```

Resource:

```text
task/task_spec.yaml
```

Role:

- records the work order;
- records forbidden claims and claim policy;
- does not execute CAD/CAE;
- tells downstream agents/tools what evidence is required before acceptance.

## Step 4: Agent proposes a structured patch

The agent can propose a structured patch using existing feature IDs and protected-region constraints:

```bash
aieng propose-patch build/bracket_001.aieng \
  --intent "Reduce mass by 15% while keeping mounting holes unchanged."
```

Resource:

```text
ai/patches/*.json
```

Interpretation:

- patch is an unexecuted proposal;
- target features and protected features must be ID-grounded;
- no geometry has changed;
- no solver has run;
- acceptance requires external validation evidence.

## Step 5: Write external tool handoff requirements

Before execution, `.aieng` records what external tools are required:

```bash
aieng write-external-tool-requirements build/bracket_001.aieng \
  --handoff-id handoff_mass_reduce_001 \
  --overwrite
```

Resource:

```text
task/external_tool_requirements.json
```

Role:

- states that external CAD/CAE tools execute;
- lists required capabilities;
- lists writeback requirements;
- forbids `.aieng` core from executing CAD kernels, meshers, solvers, or manufacturing checks.

## Step 6: Seed the evidence and claim ledgers

Create the evidence/claim scaffold:

```bash
aieng write-evidence-scaffold build/bracket_001.aieng --overwrite
```

Resources:

```text
results/evidence_index.json
```

Claim proposals are review artifacts requiring human review.

Initial interpretation:

- task/handoff resources may be supported by `.aieng`-generated evidence items;
- solver, mesh, and geometry-modification claims start as `unsupported`;
- unsupported is not false;
- pass/fail status requires actual evidence IDs.

## Step 7: External CAD/CAE tools execute outside `.aieng`

This step is not performed by `.aieng` core.

Possible external tool actions:

```text
FreeCAD/NX/SolidWorks/CATIA modifies CAD geometry
Gmsh/HyperMesh/Ansys Meshing generates mesh
CalculiX/Abaqus/Ansys/Nastran runs solver
postprocessor produces stress/displacement report
manufacturing checker produces manufacturability report
```

The actual execution may be orchestrated by a human, a CAD/CAE script, `mechanical_agent`, or another workflow system.

`.aieng` only receives artifacts and metadata afterward.

## Step 8: Adapter writes back evidence

After external execution, an adapter records evidence:

```bash
aieng record-evidence build/bracket_001.aieng \
  --kind geometry_modification \
  --producer-kind external_cad \
  --producer-tool freecad \
  --artifact-kind step \
  --artifact-path geometry/modified_patch_001.step \
  --claim-support claim_geometry_modification_001 \
  --evidence-id ev_geometry_modification_001 \
  --notes "External CAD tool reported modified STEP export."
```

Example solver evidence:

```bash
aieng record-evidence build/bracket_001.aieng \
  --kind solver_result \
  --producer-kind external_solver \
  --producer-tool calculix \
  --artifact-kind result_file \
  --artifact-path results/artifacts/ccx_run_001.frd \
  --claim-support claim_solver_result_001 \
  --evidence-id ev_solver_result_001 \
  --notes "External solver result artifact recorded; result interpretation must be checked separately."
```

Important rule:

- record only artifacts that actually exist or externally referenced artifacts that are real;
- do not mark claims as pass until evidence is sufficient and linked.

## Step 9: Human reviews claim proposals

When evidence supports or contradicts a claim, claim proposals require human review:

- A human reviewer examines the evidence and claim proposal artifacts.
- Claim status changes are made through human review, not automated CLI commands.
- If a result fails a target, the reviewer marks it accordingly with evidence IDs. If no evidence exists, keep `unsupported`.

## Step 10: Adapter records tool trace

Record what external tools reported doing:

```bash
aieng record-trace build/bracket_001.aieng \
  --tool-id calculix \
  --tool-role solver \
  --step-name run_static_structural \
  --exit-status success \
  --input simulation/updated_deck.inp \
  --output results/artifacts/ccx_run_001.frd \
  --artifact ev_solver_result_001 \
  --claim claim_solver_result_001 \
  --notes "External solver run recorded by adapter."
```

Resource:

```text
provenance/tool_trace.json
```

Interpretation:

- tool trace is audit/provenance;
- it is not engineering validation by itself;
- consistency checks require claims advanced in the trace to match claim proposals reviewed by a human.

## Step 11: Refresh completeness and summary

After writeback, refresh missingness and AI-readable summaries:

```bash
aieng write-completeness-report build/bracket_001.aieng --overwrite
aieng summarize build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

Expected result:

- completeness report shows fewer missing/unsupported categories if evidence was attached;
- summary exposes evidence counts, claim status, and tool trace entries;
- validator catches contradictions, dangling references, or unsupported claims incorrectly advanced by trace.

## What the agent can safely conclude

The agent may say:

- what resources exist;
- which feature IDs and protected regions are declared;
- what task intent and handoff requirements exist;
- which evidence items are attached;
- which claims are pass/fail/unsupported according to claim proposals (review artifacts requiring human review);
- which external tools are recorded in `tool_trace.json`;
- what information remains missing according to `completeness_report.json`.

The agent must not say:

- the design is safe unless safety criteria and solver evidence support that claim;
- stress target is satisfied unless parsed/validated solver evidence supports it;
- mesh was generated unless mesh evidence exists;
- solver was run unless solver evidence and/or trace supports it;
- CAD geometry was modified by `.aieng` core;
- candidate features are confirmed engineering truth unless source evidence says so.

## Minimal end-to-end checklist

A good handoff package should contain, when relevant:

```text
manifest.json
validation/completeness_report.json
task/task_spec.yaml
task/external_tool_requirements.json
results/evidence_index.json
provenance/tool_trace.json
README_FOR_AI.md
ai/summary.md
```

Claim proposals are review artifacts requiring human review.

Optional but valuable:

```text
geometry/topology_map.json
graph/aag.json
graph/feature_graph.json
graph/constraints.json
ai/protected_regions.json
simulation/setup.yaml
objects/interface_graph.json
visual/annotation_layers.json
```

## Relation to mechanical_agent

`mechanical_agent` can become an L5 roundtrip-aware adapter:

1. Read `.aieng` package state and completeness.
2. Choose external CAD/CAE tools.
3. Execute those tools outside `.aieng`.
4. Write evidence, claim proposals, and tool trace back into `.aieng` (claim proposals require human review).
5. Let `aieng validate` check consistency.

This keeps `mechanical_agent` and `.aieng` complementary: `mechanical_agent` can orchestrate, while `.aieng` remains the structured semantic/evidence record.

