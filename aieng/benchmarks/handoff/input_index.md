# Benchmark Input Index

This document describes the input files used for the agent handoff benchmark and how to prepare them.

---

## Overview

The benchmark uses a single `.aieng` package prepared through Phase 14C, meaning it includes task spec, external tool requirements, evidence index, and claim map in addition to the standard geometry, topology, feature, constraint, simulation, AAG, and validation status resources.

The input is provided as extracted package contents (individual files), not as the binary ZIP. The AI reads the file contents directly.

---

## How to prepare the benchmark input

### Option A: Use the reference bracket demo package

Run the full pipeline on the reference bracket example:

```bash
# Create and populate package
aieng init --model-id bracket_001 --out benchmark/bracket_001.aieng
aieng import-step examples/bracket.step --out benchmark/bracket_001.aieng
aieng extract-topology benchmark/bracket_001.aieng
aieng build-aag benchmark/bracket_001.aieng
aieng recognize-features benchmark/bracket_001.aieng
aieng apply-context benchmark/bracket_001.aieng --context examples/bracket_user_context.yaml
aieng update-validation-status benchmark/bracket_001.aieng
aieng build-visual-index benchmark/bracket_001.aieng
aieng build-visual-manifest benchmark/bracket_001.aieng
aieng build-object-registry benchmark/bracket_001.aieng
aieng build-interface-graph benchmark/bracket_001.aieng
aieng write-task-spec benchmark/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng write-external-tool-requirements benchmark/bracket_001.aieng
aieng write-evidence-scaffold benchmark/bracket_001.aieng
aieng summarize benchmark/bracket_001.aieng
```

### Option B: Use the scripted reference demo

```bash
python scripts/run_reference_demo.py
```

Then run the Phase 14 commands above on the output package.

### Extracting files for the benchmark

```python
import zipfile, os

pkg_path = "benchmark/bracket_001.aieng"
output_dir = "benchmark/extracted/"

with zipfile.ZipFile(pkg_path) as zf:
    zf.extractall(output_dir)
```

---

## Input files

The following files are provided to the AI in the benchmark. All are extracted from the `.aieng` package.

### Primary task and evidence resources (Phase 14)

| File | Description |
|------|-------------|
| `task/task_spec.yaml` | Active task specification: intent, mode, forbidden claims, claim policy |
| `task/external_tool_requirements.json` | External tool handoff contract: required capabilities, candidate tools, handoff policy, writeback requirements, forbidden core actions |
| `results/evidence_index.json` | Evidence ledger: what artifacts exist, who produced them, what claims they support |
| `results/claim_map.json` | Claim-evidence map: which claims are pass/fail/unsupported |

### Package orientation

| File | Description |
|------|-------------|
| `manifest.json` | Package identity, units, provenance, and indexed resource paths |
| `README_FOR_AI.md` | AI reader guide: reading order, claim discipline rules, source-of-truth list |
| `ai/summary.md` | Derived engineering narrative (derived; not source of truth) |

### Geometry and topology

| File | Description |
|------|-------------|
| `geometry/topology_map.json` | Topology entity IDs (face, edge, vertex); may be mock-generated |
| `graph/aag.json` | Attributed adjacency graph (generated from topology_map; not source-of-truth) |

### Features and constraints

| File | Description |
|------|-------------|
| `graph/feature_graph.json` | Feature candidates with stable IDs referencing topology IDs |
| `graph/constraints.json` | Structured constraints targeting feature IDs |
| `ai/protected_regions.json` | Protected feature IDs and forbidden operations |
| `ai/patches/*.json` | Patch proposals (unexecuted suggestions; not applied modifications) |

### Simulation and CAE

| File | Description |
|------|-------------|
| `simulation/setup.yaml` | Simulation intent: material, boundary conditions, loads, targets |
| `simulation/cae_imports/parsed_materials.json` | Parsed CAE deck materials (scaffold) |
| `simulation/cae_imports/parsed_boundary_conditions.json` | Parsed CAE deck boundary conditions (scaffold) |
| `simulation/cae_imports/parsed_loads.json` | Parsed CAE deck loads (scaffold) |
| `simulation/cae_mapping.json` | Conservative CAE entity to feature/interface ID mapping |

### Object and interface index

| File | Description |
|------|-------------|
| `objects/interface_graph.json` | Generated interface index (navigation aid; not source-of-truth) |
| `objects/object_registry.json` | Generated cross-file object index (navigation aid; not source-of-truth) |

### Validation state

| File | Description |
|------|-------------|
| `validation/status.yaml` | Claim policy and validation-state ledger |

---

## What is NOT provided as input

The following are intentionally excluded from the benchmark input:

- Raw STEP/B-rep file content (the earlier benchmark covers raw STEP comparison)
- Rendered 3D geometry images or previews
- Solver result files
- Mesh files
- FEA output or stress/displacement data

---

## Excluded capabilities during the benchmark

The benchmark evaluator must confirm that the following were excluded during the AI's evaluation:

- MCP tool calls of any kind
- RAG or retrieval augmentation
- Skills, plugins, or LLM fine-tuning
- External CAD tool calls (FreeCAD, CATIA, SolidWorks, etc.)
- External CAE tool calls (CalculiX, Abaqus, Ansys, etc.)
- Solver execution
- Mesh generation
- Manufacturing checker calls
- LLM API calls beyond prompting with the listed package contents

---

## Input size guidance

Provide all files to the AI in a single context window where possible. If the total token count exceeds context limits, prioritize in this order:

1. `task/task_spec.yaml`
2. `task/external_tool_requirements.json`
3. `results/evidence_index.json`
4. `results/claim_map.json`
5. `README_FOR_AI.md`
6. `ai/summary.md`
7. `ai/protected_regions.json`
8. `graph/feature_graph.json`
9. `graph/constraints.json`
10. `objects/interface_graph.json`
11. `validation/status.yaml`
12. All remaining resources
