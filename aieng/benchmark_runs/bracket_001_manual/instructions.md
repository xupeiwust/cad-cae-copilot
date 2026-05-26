# Manual Benchmark Run: Bracket 001

This package contains everything needed to run the bracket reference benchmark manually. The benchmark compares what a general AI understands from raw STEP-like input versus generated `.aieng` package contents.

**No API calls, no LLM integrations, no RAG, no MCP tools, no plugins, no solvers, and no CAD tools are used or required.**

---

## What this benchmark tests

The core `.aieng` thesis is:

> Adapt CAD/CAE data to AI. The file should carry enough engineering semantics that a general AI can understand the model before calling any tools.

This benchmark operationalizes that thesis: ask the same engineering questions in two separate AI sessions, score the answers, and compare.

---

## Step 1: Generate the reference `.aieng` package

From the repository root, run the reference demo to produce `build/bracket_001.aieng`:

```bash
python scripts/run_reference_demo.py
```

Or run the equivalent CLI chain manually:

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng --overwrite
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng build-visual-index build/bracket_001.aieng --overwrite
aieng build-visual-manifest build/bracket_001.aieng --overwrite
aieng build-interface-graph build/bracket_001.aieng --overwrite
aieng import-cae-deck build/bracket_001.aieng --deck examples/bracket_loadcase.inp --format calculix --overwrite
aieng apply-cae-mapping build/bracket_001.aieng --mapping examples/bracket_cae_mapping.yaml --overwrite
aieng build-interface-graph build/bracket_001.aieng --overwrite
aieng build-object-registry build/bracket_001.aieng --overwrite
aieng summarize build/bracket_001.aieng --overwrite
aieng propose-patch build/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng export-calculix build/bracket_001.aieng --out build/solver_deck.inp --overwrite
aieng update-validation-status build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

Verify the package was created and is valid before proceeding. The output of `aieng validate` should report no failures.

### Phase 10A/10B/10C CAE notes

- `import-cae-deck` imports the minimal CalculiX fixture into `simulation/cae_imports/*` and creates `simulation/cae_mapping.json`.
- `apply-cae-mapping` applies explicit user-provided mappings from `examples/bracket_cae_mapping.yaml`.
- `build-interface-graph` is intentionally run twice: once before mapping so `iface_feat_hole_pattern_001` exists, and once after mapping so `objects/interface_graph.json` includes `cae_refs`.
- `build-object-registry` is run after the enriched interface graph so CAE-to-interface and CAE-to-feature relationships appear in `objects/object_registry.json`.

---

## Step 2: Extract the `.aieng` package contents

The `.aieng` file is a zip archive. Extract it to inspect the files:

```bash
# Python
import zipfile
with zipfile.ZipFile("build/bracket_001.aieng") as z:
    z.extractall("build/bracket_001_extracted/")
```

Or use any zip tool.

The benchmark input files for Condition B are listed in [`aieng_input_index.md`](aieng_input_index.md).

---

## Step 3: Run Condition A — Raw STEP input only

Open a **new** AI chat session with no prior context about this project.

Provide **only** the raw STEP file content. See [`raw_step_input.md`](raw_step_input.md) for what to include and what to exclude.

**Critical constraints for Condition A:**
- Do **not** provide `README_FOR_AI.md`.
- Do **not** provide `feature_graph.json`.
- Do **not** provide `constraints.json`.
- Do **not** provide `setup.yaml`.
- Do **not** provide `protected_regions.json`.
- Do **not** provide `summary.md`.
- Do **not** provide any patch proposal files.
- Do **not** provide `bracket_user_context.yaml`.
- Do **not** explain that the topology is mock-based.
- Do **not** explain the project thesis.
- Do **not** provide external RAG, MCP tools, skills, plugins, solver access, CAD tool access, or any specialized engineering knowledge beyond what is in the raw STEP file.

Ask **all** questions from [`questions.md`](questions.md) in order.

Record all answers verbatim or with sufficient detail to score them.

---

## Step 4: Run Condition B — `.aieng` package input

Open a **new, separate** AI chat session with no prior context about Condition A.

Provide all files listed in [`aieng_input_index.md`](aieng_input_index.md) as context.

**Critical constraints for Condition B:**
- Do **not** provide external RAG, MCP tools, skills, plugins, solver access, CAD tool access, or any specialized engineering knowledge beyond the package contents.
- Do **not** explain the `.aieng` format beyond what is in `README_FOR_AI.md`.
- Do **not** tell the AI which answers you expect.

Ask the **same** questions from [`questions.md`](questions.md) in order.

Record all answers verbatim or with sufficient detail to score them.

---

## Step 5: Score both conditions

Use [`scoring_sheet.md`](scoring_sheet.md) and [`benchmarks/scoring_rubric.md`](../../benchmarks/scoring_rubric.md) to score answers from both conditions.

Score each category 0, 1, or 2:
- **0** = absent or incorrect
- **1** = partially correct but vague
- **2** = correct, grounded, cites relevant IDs or structured resources

---

## Step 6: Record observations

See [`expected_observations.md`](expected_observations.md) for what differences to look for between conditions.

After scoring, note in [`scoring_sheet.md`](scoring_sheet.md):
- Which categories showed the largest gap between conditions.
- Any hallucinations or unsupported claims in either condition.
- Any information that should be added as a future `.aieng` resource.

---

## Important notes

- This benchmark measures package intelligibility, not engineering correctness or solver accuracy.
- The bracket fixture is a mock. The STEP file does not contain real geometry. Topology is mock-generated. Feature recognition is rule-based. All engineering context is user-provided.
- Do not interpret benchmark results as proof that the bracket design is safe, manufacturable, or solver-validated.
- Record results in a copy of `scoring_sheet.md` with a date and session identifier.
