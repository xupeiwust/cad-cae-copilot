# Benchmark Methodology

This document describes the current implemented method for the `.aieng` file-native understanding benchmark.

The benchmark is designed to test whether a general LLM can produce more useful engineering understanding from a structured `.aieng` package than from raw geometry input alone, while remaining equally honest about uncertainty and missing evidence.

## Objective

The benchmark compares two input conditions for the same reference scenario:

- **Condition A**: raw STEP input only
- **Condition B**: a generated `.aieng` package containing structured engineering resources

The goal is not to test CAD execution, meshing, or solver performance. The goal is to test **file-native engineering understanding before tool use**.

## Benchmark Scenario

The current runnable scenario is `real_bracket_001`.

Its main assets are:

- raw geometry fixture: `examples/real_bracket.step`
- question set: `benchmark_runs/real_bracket_001/questions.md`
- Condition B input index: `benchmark_runs/real_bracket_001/aieng_input_index.md`
- scoring rubric: `benchmarks/scoring_rubric.md`
- result schema: `benchmarks/results.schema.json`

## Core Principle

The benchmark evaluates whether structured package resources improve understanding without allowing the model to rely on external augmentation.

During the benchmark call, the model must not use:

- RAG
- MCP tools
- skills
- plugins
- CAD tool calls
- solver calls

This makes the benchmark a comparison between:

1. what can be inferred from raw geometry input alone, and
2. what can be understood directly from a self-describing engineering package.

## Conditions

### Condition A

Condition A provides only the raw STEP file:

- `examples/real_bracket.step`

No feature graph, constraints, simulation setup, validation status, or AI summary is provided.

### Condition B

Condition B provides a `.aieng` package generated from the same reference model.

The required input set is defined by `benchmark_runs/real_bracket_001/aieng_input_index.md` and currently includes:

- `README_FOR_AI.md`
- `manifest.json`
- `geometry/topology_map.json`
- `graph/aag.json`
- `graph/feature_graph.json`
- `graph/constraints.json`
- `simulation/setup.yaml`
- `ai/protected_regions.json`
- `ai/summary.md`
- `validation/status.yaml`
- `ai/patches/patch_0001.json` when present

Optional supplementary resources may also be included, such as:

- `geometry/source.step`
- `geometry/normalized.step`
- `objects/object_registry.json`
- `objects/interface_graph.json`

The default Condition B package path is:

- `build/real_bracket_001.aieng`

## Question Set

Both conditions use the same question set from `benchmark_runs/real_bracket_001/questions.md`.

The current questions test areas such as:

- part identity and likely function
- mounting interfaces
- preserved features during mass reduction
- explicit versus inferred constraints
- simulation intent and validation gaps
- topology adjacency reasoning
- the effect of `graph/aag.json` on confidence
- structured patch planning
- required deterministic validation steps
- remaining unknowns

Using the same questions for both conditions keeps the comparison focused on the effect of the input representation.

## Execution Method

The benchmark runner is implemented in:

- `scripts/run_benchmark.py`
- `src/aieng/benchmarking/runner.py`

### High-level flow

1. Load the question set.
2. Resolve whether the run should execute Condition A, Condition B, or both.
3. If Condition B is requested and the `.aieng` package is missing, prepare it by running `scripts/run_real_step_demo.py`.
4. Load the Condition A raw STEP text and the Condition B indexed resources.
5. Estimate prompt and completion token usage.
6. For each selected condition:
   - ask the model to answer the benchmark questions in strict JSON
   - ask the model to score those answers against the rubric in strict JSON
7. Aggregate per-condition totals and A/B deltas.
8. Validate the final result against `benchmarks/results.schema.json`.
9. Write the structured result JSON into `benchmarks/results/`.

### Two-call structure per condition

Each condition currently uses two model calls:

1. **Answer call**: the model answers the benchmark questions from the provided files only
2. **Score call**: the model scores the generated answers against the rubric

This means a full `both` run uses four model calls in total.

## Prompt Structure

The answer prompt instructs the model to:

- use only the provided inputs
- avoid external tools or hidden context
- return strict JSON

The expected answer payload contains:

- `question_id`
- `answer`
- `citations`
- `unknowns`

The score prompt then provides:

- the condition label
- the question set
- the generated answers
- the scoring rubric
- the category definitions

The expected scoring payload contains:

- `category_id`
- `category_name`
- `honesty`
- `usefulness`
- `reason`

## Scoring Method

Scoring uses the rubric in `benchmarks/scoring_rubric.md`.

There are **8 categories**, and each category is scored on **2 independent dimensions**:

- **Honesty**
- **Usefulness**

Each dimension uses a `0-2` scale:

- `0`: absent or incorrect
- `1`: partially correct but vague
- `2`: correct, grounded, and actionable

The eight categories are:

1. Object identity understanding
2. Feature grounding with IDs
3. Constraint / protected-region awareness
4. Simulation intent understanding
5. Validation honesty
6. Patch proposal structure
7. Avoidance of hallucinated solver / manufacturing claims
8. Distinction between facts, candidates, assumptions, and validated results

### Totals

For each condition, the runner computes:

- `honesty_total`
- `usefulness_total`
- `max_total`

With 8 categories and a maximum score of 2 per dimension, the per-condition maximum is:

- `16` honesty
- `16` usefulness

When both conditions are run, the runner also computes:

- `delta_honesty`
- `delta_usefulness`

These deltas show whether the `.aieng` package improved the model's file-native understanding relative to raw STEP input.

## Result Format

Each benchmark run is written as a structured JSON file in:

- `benchmarks/results/`

The filename format is:

- `run_<timestamp>.json`

Each result records:

- provider and model metadata
- benchmark scenario ID
- condition results
- included files for each condition
- excluded capabilities
- raw answer JSON text
- raw scoring JSON text
- per-condition totals
- overall deltas
- token and cost estimates
- warnings about missing optional resources

The result must conform to:

- `benchmarks/results.schema.json`

## Progress Reporting

The CLI script `scripts/run_benchmark.py` prints text progress updates while running.

Current progress output covers:

- input loading
- Condition B preparation when needed
- provider setup
- answer generation for each condition
- scoring for each condition
- result writing

This is intended to make long-running model calls easier to monitor in a terminal session.

## Reproducible Commands

### Dry run

```bash
python scripts/run_benchmark.py --provider anthropic --model claude-test --condition both --dry-run
```

### Full run

```bash
python scripts/run_benchmark.py --provider anthropic --model claude-3-7-sonnet-latest --condition both
```

### OpenAI-compatible provider

```bash
python scripts/run_benchmark.py --provider openai-compatible --base-url https://example.invalid/v1 --model my-model --condition B
```

## Interpretation Guidance

This benchmark should be interpreted carefully.

High honesty in Condition A may simply mean the model correctly refuses to speculate from raw geometry. That is a good outcome, but it is not yet useful engineering understanding.

The intended success pattern for `.aieng` is:

- keep honesty high
- raise usefulness
- improve ID-grounded reasoning
- improve constraint and validation awareness
- avoid hallucinated solver or manufacturing claims

In other words, the benchmark does not reward confidence by itself. It rewards **grounded usefulness under explicit uncertainty**.

## Limitations

The current implementation has important limitations:

- it covers one reference scenario, `real_bracket_001`
- it is not yet a broad benchmark suite across multiple part families
- the scoring step is itself model-based rather than human-adjudicated
- Condition B package generation may be blocked if optional local geometry dependencies are unavailable
- the benchmark measures understanding from provided files, not downstream engineering correctness

Because of these limits, benchmark scores should be treated as comparative evidence about representation quality, not as proof of engineering validity.
