# Phase 21A Scenario: Sample Bracket — CAD Understanding (Track A)

**Scenario ID**: `sample_bracket_cad_understanding`  
**Track**: A — CAD Understanding  
**Benchmark**: `ai_usefulness_v1`  
**Status**: Scaffold — no runs recorded yet.

---

## Part description

The `sample_bracket` is a synthetic four-object mechanical assembly used as the Phase 20
reference fixture. It is intentionally simple — enough structure to meaningfully compare
AI responses with and without `.aieng`, but small enough to evaluate by hand.

| Object | FCStd type | Known parameters |
|--------|-----------|-----------------|
| `Plate` (label: "Base plate") | `Part::Box` | Length=100 mm, Width=50 mm, Height=10 mm |
| `MountingHole_1` | `PartDesign::Hole` | Diameter=6 mm, Depth=10 mm |
| `MountingHole_2` | `PartDesign::Hole` | Diameter=6 mm, Depth=10 mm |
| `Flange_Top` | `PartDesign::Pad` | Length=40 mm, Width=20 mm |

**What is available in Condition B (`.aieng` package, offline conversion):**
- Feature graph with heuristic feature candidates (`base_plate`, `mounting_hole`, `flange`)
- Object registry with stable IDs (`obj_plate`, `obj_mountinghole_1`, etc.)
- All 15 coverage categories with explicit status values
- `geometry: missing`, `topology: missing` (offline — no STEP exported)
- `materials: missing`, `loads: missing`, `boundary_conditions: missing`
- All uncertainty notes from heuristic recognition

**What is NOT in the package (offline conversion):**
- B-rep geometry (no STEP file)
- Stable topology IDs (no OCC extraction)
- Confirmed CAD semantics (all features are heuristic candidates)
- Any simulation setup

---

## How to run this benchmark manually

### Step 0 — Generate the Condition B package (one-time setup)

```bash
aieng convert examples/sample_bracket.FCStd \
    --out benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng
```

Verify the package is valid:
```bash
aieng validate benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng
```

Extract resources for the benchmark session:
```bash
python -c "
import zipfile
with zipfile.ZipFile('benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng') as z:
    z.extractall('benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b_contents/')
"
```

### Step 1 — Run Condition A

Open a fresh AI session. Provide **only** the contents of `condition_a.md` to the AI.
Do not provide any `.aieng` resources, structured JSON, or the `.aieng` package.

Ask the questions from [questions.md](questions.md) one by one. Record responses.

### Step 2 — Run Condition B

Open a new, separate AI session (same model, same provider, no cross-session context).
Provide the following files from the extracted `condition_b_contents/` directory:

- `README_FOR_AI.md`
- `manifest.json`
- `provenance/conversion_manifest.json`
- `validation/completeness_report.json`
- `graph/feature_graph.json`
- `objects/object_registry.json`

(See [condition_b_index.md](condition_b_index.md) for the full list.)

Ask the **same** questions from [questions.md](questions.md) in the same order.

### Step 3 — Score both conditions

Use the rubric in [../scoring_rubric.md](../scoring_rubric.md) to score each dimension for
both conditions. Reference [expected_scoring.md](expected_scoring.md) for guidance on
what earns a 0, 1, or 2 for this specific model.

### Step 4 — Record results

Copy [../result_template.md](../result_template.md) to
`benchmarks/ai_usefulness/results/run_YYYYMMDDTHHMMSSZ.md` and fill in your scores.

For machine-readable results, create a JSON file following `../results.schema.json`.
See [example_result.json](example_result.json) for the structure (note: the example
contains illustrative values, not real run data).

---

## Files in this directory

| File | Purpose |
|------|---------|
| `README.md` | This file — scenario description and run instructions |
| `condition_a.md` | Raw input for Condition A (FCStd Document.xml text) |
| `condition_b_index.md` | Index of `.aieng` package resources for Condition B |
| `questions.md` | Track A questions selected for this scenario |
| `expected_scoring.md` | Per-dimension scoring guidance for this model |
| `example_result.json` | Illustrative result JSON (validates against schema; not a real run) |
| `condition_b.aieng` | Generated at runtime — not committed to the repo |
| `condition_b_contents/` | Extracted at runtime — not committed to the repo |

---

## Excluded capabilities (confirm before running)

- [ ] MCP tool calls
- [ ] RAG or retrieval augmentation
- [ ] Skills, plugins, or LLM fine-tuning
- [ ] External CAD tool calls
- [ ] External CAE tool calls
- [ ] Solver execution
- [ ] LLM API calls beyond prompting with designated input files
- [ ] In Condition A: `.aieng` package resources excluded
- [ ] In Condition B: raw FCStd or STEP files excluded
