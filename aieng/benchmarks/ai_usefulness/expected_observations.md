# Expected Observations — AI Usefulness Benchmark

This document describes the canonical expected behaviors for a well-performing AI
in each benchmark condition. Use it as a reference when scoring.

---

## General principle

A well-performing AI in Condition B (with `.aieng`) should:

1. Cite specific resource paths, feature IDs, and field names from the package.
2. Explicitly acknowledge coverage_categories statuses — especially `missing`,
   `unsupported`, and `partial` — without filling gaps with invented information.
3. Distinguish between confirmed information, inferred/heuristic information, and
   missing information.
4. Never assert that `.aieng` ran a solver, mesher, optimizer, or CAD edit.
5. Correctly use stable IDs from the package rather than natural-language paraphrases.

A well-performing AI in Condition A (without `.aieng`) may:

- Produce reasonable guesses based on object names, but should still flag uncertainty.
- Lack access to `coverage_categories`, completeness status, and feature recognition
  confidence — this is the key difference between conditions.

---

## Track A — CAD Understanding

**Expected in Condition B:**

- Cites `graph/feature_graph.json` for feature types and parameters.
- Notes that feature types come from heuristic recognition (`recognition.method:
  freecad_name_heuristic`), not from confirmed CAD semantics.
- Cites `coverage_categories` with `geometry: missing` and `topology: missing`
  to explain what is not available.
- States that parameter values are proposals only (`parameter_source: converter_extracted`).
- Does not invent topology IDs, face IDs, or exact dimensions beyond what parameters provide.

**Expected delta vs. Condition A:**
- Condition B should score higher on `referenceability_score` (stable IDs cited).
- Condition B should score higher on `missingness_honesty_score` (explicit missing/partial status).
- `feature_identification_score` may improve slightly (confidence and uncertainty flags visible).

**Red flags (hallucination):**
- Invented face/edge topology references (no topology was extracted offline).
- Specific dimensional claims beyond recorded parameter values.
- Claims that feature types are confirmed from the CAD model.

---

## Track B — CAD Reconstruction Assistance

**Expected in Condition B:**

- Produces a reconstruction plan anchored to specific parameter values from
  `graph/feature_graph.json`.
- Labels each parameter with its `parameter_source` (`converter_extracted`) and notes
  that writeback requires an external FreeCAD adapter, not `.aieng`.
- Identifies which parameters are known and which would need to be provided externally
  (e.g. fillet radii if not in the FCStd properties).
- Does not generate code that assumes topology IDs (topology was not extracted).
- Cites `writeback_metadata: unsupported` to explain that `.aieng` cannot execute
  the reconstruction.

**Expected delta vs. Condition A:**
- Condition B should produce a more parameter-grounded plan (actual numeric values
  cited, not guesses).
- Condition B should more honestly flag what parameters are missing.

**Red flags (hallucination):**
- Generated code that references topology face IDs not present in the package.
- Claims that `.aieng` can run a FreeCAD script directly.
- Invented parameter values for features that have no recorded parameters.

---

## Track C — FEM Preprocessing Assistance

**Expected in Condition B:**

- Correctly states that materials, loads, and boundary conditions are `missing`
  in the package (cites `coverage_categories`).
- States that topology extraction (`geometry: missing`, `topology: missing`) must
  happen before a mesh can be generated.
- Lists external tool actions in the correct order: STEP export → topology extraction
  → meshing → apply materials/loads/BCs → solver run.
- Does not assert that any of these steps were performed by `.aieng`.
- Cites `mesh: missing` and `solver_deck: missing` explicitly.

**Expected delta vs. Condition A:**
- Condition B should score higher on `preprocessing_readiness_score` (structured
  checklist visible in package).
- Condition B should score higher on `missingness_honesty_score` (explicit coverage
  statuses for materials, loads, BCs, mesh).

**Red flags (hallucination):**
- Invented material properties (steel, aluminium, etc.) not recorded in the package.
- Claims that a mesh is available.
- Claims that loads or BCs are defined when they are explicitly `missing`.

---

## Track D — CAE Deck Understanding

**Expected in Condition B:**

- Correctly notes that simulation setup is `missing` from the package (no solver
  deck was imported in the reference fixture).
- Cites `cad_cae_mappings: missing` to explain that no confirmed CAD-to-CAE
  mapping exists.
- Does not invent load magnitudes, element types, or named selections.
- Suggests that `aieng import-cae-deck` and `aieng apply-cae-mapping` would be
  the appropriate next steps, explicitly noting these require engineer input.

**Expected delta vs. Condition A:**
- Condition B should score higher on `missingness_honesty_score` (explicit `missing`
  statuses visible for simulation categories).
- `referenceability_score` may improve if the AI cites resource paths.

**Red flags (hallucination):**
- Invented solver settings, element types, or material cards.
- Claims that a solver deck is present when it is not.
- Implied or stated that `.aieng` ran the solver.

---

## General red flags (all tracks)

The following behaviors indicate hallucination or boundary confusion in **any** track:

| Behavior | What to check |
|----------|---------------|
| Invents topology IDs (face_*, edge_*, body_*) | Was topology extracted? Check `topology: missing` in coverage_categories |
| Invents material properties not in the input | Check `materials: missing` in coverage_categories |
| Claims the model is solver-ready | Check all FEM-related categories in coverage_categories |
| Implies `.aieng` ran a solver, mesher, or CAD edit | `claim_policy.aieng_core_executes_solvers_meshers_or_optimizers = false` |
| Treats feature type as confirmed when it is heuristic | Check `recognition.method: freecad_name_heuristic` and `recognition.confidence` |
| Ignores `missing`, `partial`, or `unsupported` coverage statuses | Read `provenance/conversion_manifest.json` coverage_categories |
| Uses invented IDs instead of package IDs | Cross-check against `objects/object_registry.json` and `graph/feature_graph.json` |
