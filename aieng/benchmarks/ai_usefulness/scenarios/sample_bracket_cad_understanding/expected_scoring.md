# Expected Scoring — Sample Bracket CAD Understanding

This document records the expected scoring for each benchmark dimension in each condition.
Use it as a scoring guide when evaluating responses against this scenario.

---

## Ground truth for this model

Before scoring, confirm the evaluator knows:

| Fact | Source (Condition B) | Present in Condition A? |
|------|---------------------|------------------------|
| 4 objects: Plate, MountingHole_1, MountingHole_2, Flange_Top | `feature_graph.json` | Yes (Document.xml) |
| `Plate` type = `base_plate` (heuristic) | `feature_graph.json` → `features[0].type` | Inferable from type `Part::Box` |
| Holes are `mounting_hole` (heuristic) | `feature_graph.json` → `features[].type` | Inferable from name `MountingHole_*` |
| `Flange_Top` type = `flange` (heuristic) | `feature_graph.json` → `features[3].type` | Inferable from name |
| All types are heuristic, not confirmed | `feature_graph.json` → `recognition.method: freecad_name_heuristic` | NOT explicitly stated in Document.xml |
| `geometry: missing` | `conversion_manifest.json` → `coverage_categories` | NOT in Document.xml |
| `topology: missing` | `conversion_manifest.json` → `coverage_categories` | NOT in Document.xml |
| `materials: missing` | `conversion_manifest.json` → `coverage_categories` | NOT in Document.xml |
| Numeric parameters: Plate=100×50×10mm, Holes D=6mm depth=10mm | Both conditions | Yes |

---

## Dimension-by-dimension expected scores

### `geometry_understanding_score`

**Condition A expected range: 0–1**

- **0**: AI claims geometry is fully available, or makes no mention of what is and isn't available.
- **1**: AI correctly notes parameters are available but does not distinguish between
  "numeric property values" and "real geometry" (no mention of missing STEP/topology).

In Condition A, the AI has no way to know that B-rep geometry and topology are absent —
the Document.xml does not say so. A score of 1 is the realistic ceiling.

**Condition B expected range: 1–2**

- **2**: AI cites `coverage_categories` in `conversion_manifest.json` with `geometry: missing`
  and `topology: missing`, and correctly distinguishes parameter values from geometry.
- **1**: AI mentions geometry/topology are unavailable but without citing `coverage_categories`.

**Delta expected: +1 to +2**

---

### `feature_identification_score`

**Condition A expected range: 0–1**

- **1**: AI correctly identifies object names and their likely types from `Part::Box` and
  `PartDesign::Hole` type strings, plus the "MountingHole" prefix.
- **0**: AI confuses types or invents feature classifications not supported by the XML.

In Condition A, the AI cannot cite `recognition.confidence` or `uncertainty_note` because
those fields only exist in the `.aieng` package.

**Condition B expected range: 1–2**

- **2**: AI cites specific feature IDs (`feat_plate`, `feat_mountinghole_1`, `feat_mountinghole_2`,
  `feat_flange_top`), their `type` values, `recognition.confidence` values, and
  `uncertainty_note` (e.g. "Feature type was inferred from FCStd object name").
- **1**: AI identifies feature types but does not cite IDs or confidence values.

**Delta expected: +1 to +1**

---

### `referenceability_score`

**Condition A expected range: 0**

- **0**: The Document.xml does not contain stable AIeng IDs. The AI can only use `name`
  attributes (`Plate`, `MountingHole_1`, etc.) which are natural-language names, not
  `@aieng[...]`-resolvable references. The AI cannot cite `.aieng` resource paths.

Any positive score in Condition A on this dimension is a hallucination bonus.

**Condition B expected range: 1–2**

- **2**: AI consistently cites `feat_*` IDs from `graph/feature_graph.json` and/or
  `obj_*` IDs from `objects/object_registry.json`, and names the resources by path.
- **1**: AI uses some IDs but inconsistently, or cites IDs without naming the resource.

**Delta expected: +1 to +2**

---

### `missingness_honesty_score`

**Condition A expected range: 0**

- **0**: The Document.xml contains no explicit missingness records. A well-intentioned AI
  might say "I don't know whether topology is available" but cannot cite structured
  evidence. Any positive score requires the AI to spontaneously note what the XML
  doesn't contain — rare and typically vague (so at best a 1).

**Condition B expected range: 1–2**

- **2**: AI cites `coverage_categories` entries with `missing` status for geometry, topology,
  materials, loads, boundary_conditions, mesh, solver_deck, etc. Lists specific
  `missing_items` text from at least one entry. Does not fill any gap with invented data.
- **1**: AI acknowledges missing items in general but without citing coverage_categories
  by field name or listing specific entries.

**Delta expected: +1 to +2**

This is typically the highest-impact dimension for `.aieng` vs. raw source comparison.

---

### `hallucination_penalty`

**Condition A expected: 0 to −2**

Likely hallucinations in Condition A:
- Inventing face/edge topology references (e.g. "the base plate has 6 faces numbered F1–F6")
- Claiming materials are steel/aluminium when none are specified
- Asserting the model is FEM-ready when no simulation setup exists
- Stating B-rep coordinates for hole positions when none are given

**Condition B expected: 0**

The package explicitly states what is missing. A well-performing AI should not
fabricate missing information when it is explicitly labelled `missing` in
`coverage_categories`.

---

### `task_success_score`

Both conditions are expected to score **1** if the AI attempts the questions in good
faith and produces a substantively useful response. The delta here is usually 0.

A score of **0** is appropriate only if the AI refuses to engage, produces incoherent
output, or gives an answer that is predominantly hallucinated.

---

## Illustrative total score expectations

These are illustrative, not guaranteed. Actual scores depend on the AI model and version.

| Dimension | Condition A (expected) | Condition B (expected) | Expected Δ |
|-----------|:---------------------:|:---------------------:|:-----------:|
| geometry_understanding | 1 | 2 | +1 |
| feature_identification | 1 | 2 | +1 |
| referenceability | 0 | 2 | +2 |
| missingness_honesty | 0 | 2 | +2 |
| hallucination_penalty | −1 | 0 | +1 |
| task_success | 1 | 1 | 0 |
| **Total** | **2** | **9** | **+7** |

A delta of +5 or higher on this scenario is a strong signal that `.aieng` meaningfully
improves AI performance on CAD understanding tasks for this model class.

---

## Scoring calibration notes

1. **Do not reward vagueness.** "Geometry might be missing" without citing
   `coverage_categories` should score 1 in Condition B, not 2.
2. **Reward honest uncertainty.** "The feature type `flange` is a heuristic inference
   from the name `Flange_Top`, not a confirmed FreeCAD feature semantic" is correct and
   grounded — score 2 for feature_identification.
3. **Penalise boundary confusion.** If the AI implies `.aieng` can run a solver,
   generate a mesh, or execute CAD edits, that is a hallucination.
4. **Hallucination threshold.** One clear fabricated claim = −1. Two or more coherent
   fabrications from a single topic (e.g. a made-up FEM mesh setup) = −1 per distinct claim.
