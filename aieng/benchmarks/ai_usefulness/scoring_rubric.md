# AI Usefulness Benchmark Scoring Rubric

Score each question/task response on the dimensions below. Record scores separately
for **Condition A** (without `.aieng`) and **Condition B** (with `.aieng`). The delta
(B minus A) is the key outcome metric.

---

## Scale

Each scored dimension uses **0, 1, or 2**:

- **0 = absent, incorrect, or hallucinated** — the AI failed to address the dimension,
  gave a wrong or fabricated answer, or invented information not present in the input.
- **1 = partially correct but vague or weakly grounded** — the AI addressed the dimension
  without citing specific resources, field names, IDs, or status values; or with
  unsupported assumptions mixed in.
- **2 = correct and grounded** — the AI gave a correct answer grounded in specific
  resources, field names, feature IDs, or status values visible in the input. No
  unsupported claims.

The key distinction between **1** and **2** is **groundedness**: a 2 requires the AI
to cite specific field names, resource paths, IDs, or status values from the input.

---

## Dimensions

### 1. `geometry_understanding_score` (0–2)

Does the AI correctly identify what geometric information is available, and what is not?

- **0** — invents geometry details not present in the input; or ignores geometry
  questions entirely; or claims geometry is available when it is missing.
- **1** — correctly states that geometry information is or is not present, but without
  citing specific coverage_categories entries, completeness statuses, or feature
  parameters.
- **2** — cites specific `coverage_categories` entries (e.g. `geometry: missing`,
  `topology: missing`) or specific feature parameter values and their `parameter_source`
  field; correctly qualifies what is confirmed vs. inferred.

*Applies to: Tracks A, B, C.*

---

### 2. `feature_identification_score` (0–2)

Does the AI correctly identify features and their properties?

- **0** — invents feature types or names not present in the input; or confuses object
  names with confirmed CAD semantics; or ignores `recognition.confidence` and
  `uncertainty_note` fields.
- **1** — lists features from the input without citing specific IDs, types, recognition
  confidence, or uncertainty notes.
- **2** — cites specific feature IDs, their `type`, `recognition.confidence` value, and
  `uncertainty_note` (or equivalent uncertainty marker); correctly labels features as
  heuristic candidates vs. confirmed where applicable.

*Applies to: Tracks A, B, C, D.*

---

### 3. `referenceability_score` (0–2)

Does the AI correctly use stable IDs and cross-resource references from the package?

- **0** — invents IDs, references resources that are not in the input, or uses unstable
  natural-language descriptions instead of available structured IDs.
- **1** — references some IDs or resource paths but without consistent citation; or
  occasionally invents IDs alongside real ones.
- **2** — consistently uses feature IDs (`feat_*`), object IDs (`obj_*`), resource paths
  (`graph/feature_graph.json`, `provenance/conversion_manifest.json`, etc.), and
  field names from the actual input when answering questions.

*Applies to: Tracks A, B, C, D.*

---

### 4. `missingness_honesty_score` (0–2)

Does the AI accurately and explicitly report missing, uncertain, unsupported, and
unavailable information?

- **0** — invents missing information (e.g. fabricates material properties, loads, or
  mesh requirements); or claims information is present when it is explicitly recorded
  as missing or unsupported in `coverage_categories`.
- **1** — acknowledges some missing information in general terms, but does not cite
  `coverage_categories` status values or specific `missing_items` / `inferred_items`
  from the manifest; or only partially reports what is missing.
- **2** — explicitly cites `coverage_categories` statuses (`missing`, `unsupported`,
  `partial`, `inferred`, `unknown`) for relevant categories; lists specific
  `missing_items` or `inferred_items` where present; does not fill gaps with guesses.

*Applies to: Tracks A, B, C, D. This is the most important dimension.*

---

### 5. `preprocessing_readiness_score` (0–2) — Track C only

Does the AI produce a correct, bounded, grounded FEM preprocessing readiness assessment?

- **0** — asserts the model is solver-ready without verifying materials, loads, BCs,
  and mesh; or fabricates solver settings; or implies `.aieng` runs the solver.
- **1** — produces a preprocessing plan that is partially correct but omits key missing
  inputs (e.g. does not mention missing materials or loads); or does not distinguish
  what `.aieng` can provide from what requires external tools.
- **2** — produces a complete preprocessing plan that enumerates all available inputs
  and all missing inputs from the package; correctly states that mesh generation, solver
  execution, and CAD geometry editing require external tools; cites specific
  `coverage_categories` statuses for materials, loads, BCs, mesh.

*Applies to: Track C only.*

---

### 6. `hallucination_penalty` (−1 per fabricated fact, unbounded below)

Deduct **1 point** for each distinct engineering fact that the AI fabricated and that
is **not** present or inferable from the provided input. Count conservatively — one
coherent invented claim (e.g. "The material is steel with E=200 GPa") is one instance
even if it contains multiple sub-values.

**What counts as hallucination:**
- Invented material properties not in the input
- Invented feature dimensions or coordinates not in the input
- Fabricated load magnitudes or directions
- Invented stable IDs not present in any provided resource
- Claims that the model is solver-ready without evidence
- Claims that `.aieng` ran a solver, mesher, or CAD edit

**What does NOT count as hallucination:**
- Explicitly labeled hypothetical examples ("If the material were steel, then...")
- Acknowledged inferences from named features ("The object named 'MountingHole_1' is likely a mounting hole")
- Correctly cited inferred items from `inferred_items` or `recognition.confidence`

*Applies to: all tracks.*

---

### 7. `task_success_score` (0 or 1)

Binary: did the AI accomplish the core task goal?

- **1** — the AI produced a useful, substantively correct response that advances the
  stated task goal (understanding the model, producing a reconstruction plan,
  identifying preprocessing requirements, etc.)
- **0** — the AI failed to produce a useful response; or the response was predominantly
  hallucinated; or the core task goal was not addressed.

*Applies to: all tracks.*

---

## Maximum scores

| Track | Positive dimensions | Max score |
|-------|--------------------:|----------:|
| A (CAD Understanding) | 4×2 + 1 | **9** |
| B (CAD Reconstruction) | 4×2 + 1 | **9** |
| C (FEM Preprocessing) | 5×2 + 1 | **11** |
| D (CAE Deck) | 4×2 + 1 | **9** |

`hallucination_penalty` is uncapped below zero.

---

## Key scoring note

**Missingness honesty is a first-class dimension.** A response that says
"materials are not recorded in this package — see `coverage_categories` status=missing"
scores **2** on `missingness_honesty_score` even if no materials are available. A response
that invents material properties scores **0** on `missingness_honesty_score` and incurs
a `hallucination_penalty`.

The benchmark rewards honest, grounded responses over confident but fabricated ones.

---

## Interpreting the delta

Compute: **Δ = Score(Condition B) − Score(Condition A)** for each dimension and total.

A positive delta means `.aieng` improved AI performance on that dimension.
A zero delta means `.aieng` provided no additional benefit on that dimension.
A negative delta would indicate a regression introduced by the package (unlikely but possible
if the structured resources confused the AI more than the raw source).
