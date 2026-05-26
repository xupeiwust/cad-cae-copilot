# Condition B Index — `.aieng` Package Resources

**Instructions for the evaluator**: Provide the files listed under "Required" to the AI
as its entire input. Do not provide the raw FCStd, STEP, or source files.

**Instructions for the AI**: Below are structured resources from a `.aieng` package
describing a mechanical bracket assembly. Answer the benchmark questions based only
on these resources.

---

## Required

- `README_FOR_AI.md`
- `manifest.json`
- `provenance/conversion_manifest.json`
- `validation/completeness_report.json`
- `graph/feature_graph.json`
- `objects/object_registry.json`

---

## Optional

- `ai/summary.md`

---

## How to extract these files

After generating `condition_b.aieng` (see `README.md`), extract with:

```bash
python -c "
import zipfile
with zipfile.ZipFile('benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b.aieng') as z:
    z.extractall('benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b_contents/')
print('Done — files in condition_b_contents/')
"
```

Key resources to read when scoring:

| Resource | What to check |
|----------|--------------|
| `provenance/conversion_manifest.json` | `coverage_categories` — 15 entries with explicit statuses |
| `graph/feature_graph.json` | Feature IDs, types, `recognition.confidence`, `uncertainty_note`, `parameter_source` |
| `objects/object_registry.json` | Object IDs (`obj_*`), `status`, `referenced_by` |
| `validation/completeness_report.json` | Per-category status: `available`, `partial`, `missing` |

---

## What the AI should see in Condition B (for evaluators)

The following information is explicitly present in the `.aieng` package and should be
cited by a well-performing AI:

| Fact | Resource | Field |
|------|----------|-------|
| `geometry: missing` | `conversion_manifest.json` | `coverage_categories[].status` |
| `topology: missing` | `conversion_manifest.json` | `coverage_categories[].status` |
| `object_registry: complete` | `conversion_manifest.json` | `coverage_categories[].status` |
| `materials: missing` | `conversion_manifest.json` | `coverage_categories[].status` |
| Feature type `base_plate` for `Plate` | `feature_graph.json` | `features[].type` |
| Feature type `mounting_hole` for holes | `feature_graph.json` | `features[].type` |
| `recognition.method: freecad_name_heuristic` | `feature_graph.json` | `features[].recognition.method` |
| `parameter_source: converter_extracted` | `feature_graph.json` | `features[].parameter_source` |
| `writeback_strategy: none` | `feature_graph.json` | `features[].writeback_strategy` |
| Stable IDs: `feat_plate`, `feat_mountinghole_1`, etc. | `feature_graph.json` | `features[].id` |
| Object IDs: `obj_plate`, `obj_mountinghole_1`, etc. | `object_registry.json` | `objects[].id` |
