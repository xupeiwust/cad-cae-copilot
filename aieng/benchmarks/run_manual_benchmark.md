# Running the Manual Benchmark

This benchmark is manual by design. It does not call any LLM, AI API, RAG system, MCP tool, skill, plugin, CAD tool, solver, or mesher.

## Step 1: Generate the reference `.aieng` package

From the repository root, run:

```bash
python scripts/run_reference_demo.py
```

This creates `build/bracket_001.aieng` using the current reference demo chain.

## Step 2: Prepare the raw-input condition

Provide only the raw STEP-like input to a general AI:

```text
examples/bracket.step
```

Ask the questions from [`questions.md`](questions.md). Do not provide external RAG, MCP tools, skills, plugins, CAD-tool access, solver access, fine-tuning, or additional engineering context.

## Step 3: Prepare the `.aieng` condition

Provide the generated `.aieng` package contents to a general AI. At minimum, include:

- `README_FOR_AI.md`
- `manifest.json`
- `graph/feature_graph.json`
- `graph/constraints.json`
- `simulation/setup.yaml`
- `ai/protected_regions.json`
- `ai/summary.md`
- `ai/patches/patch_0001.json`
- `simulation/cae_imports/parsed_materials.json`
- `simulation/cae_imports/parsed_boundary_conditions.json`
- `simulation/cae_imports/parsed_loads.json`
- `simulation/cae_mapping.json`
- `objects/interface_graph.json`
- `objects/object_registry.json`

Including `geometry/topology_map.json` is recommended when asking geometry-reference questions.

Ask the same questions from [`questions.md`](questions.md). Again, do not provide external RAG, MCP tools, skills, plugins, CAD-tool access, solver access, fine-tuning, or specialized CAD/CAE training.

## Step 4: Score answers

Score each answer set with [`scoring_rubric.md`](scoring_rubric.md).

Look especially for whether the `.aieng` condition improves the AI's ability to:

- cite object and feature IDs;
- identify protected regions;
- distinguish candidate features from confirmed engineering truth;
- explain material and simulation intent without inventing data;
- state that no solver result exists;
- avoid claims that the design is safe;
- propose or cite structured changes that preserve protected interfaces.

## Step 5: Record observations

For each category, record:

- raw-input score;
- `.aieng` score;
- key evidence from the answer;
- hallucinations or unsupported claims;
- missing information that should become future `.aieng` resources.

The benchmark result should be interpreted as evidence about package intelligibility, not as evidence of geometry validity, solver accuracy, or manufacturing readiness.
