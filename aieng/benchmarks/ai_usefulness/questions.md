# AI Usefulness Benchmark Questions

Each question is asked in both conditions:

- **Condition A**: AI has raw source files only (STEP text dump, FCStd Document.xml excerpt, or solver deck text as provided).
- **Condition B**: AI has `.aieng` package contents only (README_FOR_AI.md, feature graph, object registry, coverage categories, completeness report, readiness report — but NOT the raw source file).

Questions are identical across conditions. All scoring is done with the rubric in
[scoring_rubric.md](scoring_rubric.md).

---

## Track A — CAD Understanding

**Input (Condition A):** FCStd Document.xml text dump (object names and types only).  
**Input (Condition B):** `README_FOR_AI.md`, `graph/feature_graph.json`, `objects/object_registry.json`, `provenance/conversion_manifest.json` (coverage_categories), `validation/completeness_report.json`.

---

**A1.** What features does this model contain? For each feature, state:
- its name
- its type (or best-guess type if uncertain)
- whether the type is confirmed or inferred/heuristic

**A2.** Which objects in this model are likely to be mounting holes? Cite the evidence for your answer. If you are uncertain, say so explicitly.

**A3.** What geometric information is currently available about this model? What geometric information is missing or unavailable?

**A4.** What information is explicitly recorded as missing, unsupported, or uncertain? List each item and its source.

**A5.** A downstream engineer wants to perform FEM preprocessing on this model. What information is already available in the package, and what would they need to obtain externally?

**A6.** Can you determine the exact dimensions of any feature from the available information? If so, cite the specific parameter values and their source. If not, explain why not.

---

## Track B — CAD Reconstruction Assistance

**Input (Condition A):** FCStd Document.xml text dump (object names, types, and numeric properties).  
**Input (Condition B):** `README_FOR_AI.md`, `graph/feature_graph.json`, `objects/object_registry.json`, `provenance/conversion_manifest.json`.

---

**B1.** Write a brief natural-language description of this model suitable for a drawing title block. Include:
- component type
- key geometric features
- approximate size (if determinable)
- what is known vs. what is uncertain

**B2.** Write a CadQuery reconstruction plan (not full code — a structured list of steps) that would recreate this model from the parameter values available. For each step, note whether the parameter value is known from the package or would need to be measured/provided.

**B3.** Which feature parameters are explicitly recorded as inferred or heuristic rather than confirmed from a parametric model? Cite the specific field that records this.

**B4.** If you were to generate a full CadQuery script, what would be the highest-risk assumptions you would need to make? What information is missing that would reduce that risk?

**B5.** What is the boundary reminder stated in the package about CAD editing? Cite the resource that states it.

---

## Track C — FEM Preprocessing Assistance

**Input (Condition A):** STEP file dump (geometry only, no annotations) or FCStd Document.xml.  
**Input (Condition B):** `README_FOR_AI.md`, `graph/feature_graph.json`, `validation/completeness_report.json`, `provenance/conversion_manifest.json`, `task/external_tool_requirements.json` (if present).

---

**C1.** What material properties are currently available in the package for FEM preprocessing? If materials are missing, state that explicitly.

**C2.** What loads are defined in the package? If no loads are defined, what would be needed to add them?

**C3.** What boundary conditions (supports, fixtures, symmetry) are available? If none, state that explicitly and describe what is typically needed.

**C4.** What mesh requirements or mesh handoff information is present? What meshing steps would be required before a solver could run?

**C5.** What is the recommended sequence of external tool actions needed to take this model from its current state to solver-ready? Be explicit about which steps require external CAD/CAE tools and which information must be provided by an engineer.

**C6.** Is this model solver-ready? If not, list every missing input item that would block a solver run.

---

## Track D — CAE Deck Understanding

**Input (Condition A):** Raw CalculiX `.inp` solver deck text (cards only, no annotations).  
**Input (Condition B):** `README_FOR_AI.md`, `simulation/setup.yaml` (if present), `simulation/cae_mapping.json` (if present), `validation/completeness_report.json`, `provenance/conversion_manifest.json`.

---

**D1.** What loads are defined in the model or solver configuration? For each load, state:
- load type
- magnitude and direction (if available)
- the named selection or surface it is applied to
- whether the mapping from CAD feature to solver boundary is confirmed or inferred

**D2.** What constraints (fixed supports, symmetry, displacement BCs) are defined? For each, state the named selection it is applied to and whether the CAD-to-CAE mapping is confirmed.

**D3.** What materials are used in this model? List each material and any properties available (Young's modulus, Poisson's ratio, density, yield stress).

**D4.** What element types are configured or expected? If not specified, state that explicitly.

**D5.** Which CAD features are explicitly mapped to CAE entities (named selections, surfaces, element sets)? Which have no confirmed CAE mapping?

**D6.** What information is missing that would prevent a complete CAE setup description? Be explicit about each gap and whether it is the converter's limitation, the source's limitation, or an as-yet-unperformed engineering step.
