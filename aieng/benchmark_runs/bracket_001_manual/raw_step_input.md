# Condition A: Raw STEP Input

This file defines what to provide to the AI for **Condition A** of the manual benchmark.

---

## What to provide

Provide **only** the raw STEP file content from:

```
examples/bracket.step
```

Paste the full text of that file into the AI session as the only input. No other files, context, or explanation should be provided.

---

## What NOT to provide

Do **not** include any of the following:

- `README_FOR_AI.md`
- `manifest.json`
- `geometry/topology_map.json`
- `graph/feature_graph.json`
- `graph/constraints.json`
- `simulation/setup.yaml`
- `ai/protected_regions.json`
- `ai/summary.md`
- `ai/patches/patch_0001.json`
- `examples/bracket_user_context.yaml`
- Any summary, walkthrough, or documentation file
- Any explanation that topology extraction is mock-based
- Any explanation of the `.aieng` format or project thesis
- Any RAG context, MCP tools, skills, plugins, CAD tools, solver tools, or extra engineering knowledge

The AI session for Condition A must rely solely on the raw STEP text content below.

---

## Raw STEP text

Copy the contents of `examples/bracket.step` and paste it here before starting the benchmark session.

The file is a minimal STEP-like fixture for the reference demo:

```
examples/bracket.step
```

> **Evaluator action required:** paste the actual file content in the space below before running the benchmark.

---

<!-- PASTE RAW STEP CONTENT HERE -->

```
[paste contents of examples/bracket.step here]
```

<!-- END OF RAW STEP CONTENT -->

---

## Session setup

When providing the raw STEP text to the AI, use a prompt such as:

> Here is a STEP file for a mechanical part. Please read it carefully.
>
> [paste STEP text]

Then ask the questions from [`questions.md`](questions.md) in order.

Do **not** explain what the part is, what the project is about, or what answers you expect.

---

## Important caveats for scoring Condition A

- The STEP fixture used in this demo is a mock file. It contains an ISO-10303-21 header and a single PRODUCT entity but no real geometry data.
- A real benchmark should use a real STEP file with actual B-rep geometry. The comparison principle remains the same.
- When scoring, give credit for answers that correctly state the input is insufficient or that specific information cannot be determined from STEP content alone.
