# Condition B: `.aieng` Input Index

This file lists the package files to provide to the AI for **Condition B** of the manual benchmark.

Generate the package first by following Step 1 in [`instructions.md`](instructions.md). Then extract the zip and provide the files below.

---

## Files to provide

### `README_FOR_AI.md`

**Why included:** Top-level AI reader guide. Explains the package structure, which files are derived summaries versus source-of-truth structured resources, and what claims are not validated. An AI reading this first can orient itself without domain-specific training.

---

### `manifest.json`

**Why included:** Package identity, format version, units, provenance, and an index of all resource paths. Allows the AI to discover what is in the package and verify cross-references.

---

### `geometry/topology_map.json`

**Why included:** Stable face, edge, and body IDs with surface types, bounding boxes, areas, and radii. Provides the geometry-reference foundation that feature IDs point back to. Essential for grounding feature and constraint claims in specific geometric entities.

---

### `graph/feature_graph.json`

**Why included:** Feature objects with stable IDs (`feat_base_plate_001`, `feat_hole_pattern_001`, etc.), types, geometry references, parameters, and intent labels. This is the structured engineering feature layer. An AI can cite these IDs when answering questions about parts, features, and candidate recognition.

---

### `graph/constraints.json`

**Why included:** Structured constraints targeting feature IDs. Includes protection constraints, manufacturing rules, and simulation targets with reasons. Allows the AI to identify protected regions with their rationale.

---

### `simulation/setup.yaml`

**Why included:** Static structural simulation intent: material assignment, boundary conditions (fixed supports), force loads, mesh settings, and requested outputs. Provides the engineering setup without requiring a solver to have run.

---

### `simulation/cae_imports/parsed_materials.json`

**Why included:** Parsed CAE deck material entities from the imported CalculiX fixture. Allows the AI to identify material names and properties imported from the external CAE deck separately from user-provided simulation intent. This is parsed deck data only; it is not solver execution evidence.

---

### `simulation/cae_imports/parsed_boundary_conditions.json`

**Why included:** Parsed CAE boundary condition entities from the imported deck. Allows the AI to identify `FIXED_HOLES` as a CAE boundary-condition target and distinguish CAE target names from `.aieng` feature/interface IDs.

---

### `simulation/cae_imports/parsed_loads.json`

**Why included:** Parsed CAE load entities from the imported deck. Allows the AI to identify `LOAD_FACE` as a CAE load target and inspect the imported load value/direction metadata without claiming a solver run occurred.

---

### `simulation/cae_mapping.json`

**Why included:** Explicit CAE-to-`.aieng` mapping scaffold. It records that `FIXED_HOLES` maps to `feature_id: feat_hole_pattern_001` and `interface_id: iface_feat_hole_pattern_001`, and that `LOAD_FACE` maps to `feature_id: feat_base_plate_001`, both with `mapping_method: user_provided` and `confidence: high`. This tests whether the AI can cite user-provided mapping evidence and avoid treating mappings as automatic inference.

---

### `ai/protected_regions.json`

**Why included:** Explicit list of protected feature IDs and the operations that are allowed versus forbidden. Directly answers questions about what cannot be modified and why.

---

### `ai/summary.md`

**Why included:** Derived engineering summary generated from structured resources. Provides a human- and AI-readable narrative overview of features, material, constraints, simulation intent, and validation state. Note: this is a derived summary; the structured JSON/YAML files above are the source of truth.

---

### `ai/patches/patch_0001.json`

**Why included:** Structured, unexecuted patch proposal for the mass-reduction intent. Contains operations, target feature IDs, protected-target checks, expected effects, and required validation steps. Allows the AI to answer modification and validation-requirement questions with grounded structured output.

---

### `simulation/solver_deck.inp`

**Why included:** Included to test whether the AI understands that a solver deck scaffold exists but no solver has been run and no mesh exists. The deck contains material definitions, boundary condition intent, and load intent as CalculiX comments, but carries explicit scaffold markers stating it is not a complete runnable FEA model. An AI reading this should be able to explain what the deck represents and what is still missing (node sets, element connectivity, active boundary and load sections, a mesh, and a solver run).

---

### `validation/status.yaml`

**Why included:** Included to test whether the AI uses the structured validation status and claim policy to avoid unsupported engineering claims. The file explicitly records `mesh_generation: not_run`, `solver_execution: not_run`, and `stress_validation: not_validated`, and carries a `claim_policy` section with `forbidden_claims` (e.g. "The design is safe.", "A solver has been run.", "A mesh has been generated.") and `allowed_claims`. An AI reading this file should be able to cite the specific forbidden claims when asked what it cannot assert about the model.

---

### `visual/annotation_layers.json`

**Why included:** Included to test whether the AI understands the difference between structured visual annotation metadata and actual rendered geometry. The file maps feature IDs and topology IDs to visual roles across four annotation layers: `features` (all feature candidates labeled as `candidate_feature`), `protected_regions` (protected features labeled as `protected_region`), `simulation_targets` (boundary condition and load targets labeled as `simulation_context`), and `unknown_or_unclassified` (unrecognized topology labeled as `unclassified_geometry`). An AI reading this file should be able to describe which features map to which visual roles without claiming that a 3D view, glTF model, image, or rendered preview exists. This is annotation metadata only — no rendering has been performed.

---

### `objects/interface_graph.json`

**Why included:** Generated interface index containing mounting, protected, fixed-support, load-application, visual, and Phase 10C CAE reference roles. After explicit CAE mapping, it includes `cae_refs` linking `FIXED_HOLES` to `iface_feat_hole_pattern_001` and `LOAD_FACE` to the interface containing `feat_base_plate_001`. This tests whether the AI can inspect interface-level CAE traceability while recognizing the graph is a generated index, not source-of-truth.

---

### `objects/object_registry.json`

**Why included:** Generated cross-resource object/relationship index. After Phase 10C it includes CAE-to-interface and CAE-to-feature relationships derived from explicit mappings. This helps the AI navigate references across features, interfaces, CAE entities, constraints, visual annotations, patches, and validation resources while still treating original JSON/YAML files as authoritative.

---

## Files NOT to provide in Condition B

Do **not** provide any of the following to the AI in Condition B:

- `geometry/source.step` — providing the raw STEP file would mix Condition A input into Condition B
- `geometry/normalized.step` — same reason
- Any external RAG context
- Any MCP tools
- Any skills, plugins, or specialized AI augmentation
- Any explanation of the `.aieng` format beyond what is in `README_FOR_AI.md`
- Any explanation of expected answers

---

## Session setup

When providing the `.aieng` files to the AI, use a prompt such as:

> Here are the contents of a `.aieng` engineering model package. Please read all the files carefully.
>
> [provide each file in sequence]

Then ask the questions from [`questions.md`](questions.md) in order.

Do **not** explain what answers you expect, mention the raw-STEP condition, or provide any information beyond the package files listed above.
