# Condition B — Raw AI Answers

This file stores the raw, unedited AI responses from the Condition B session.
Paste verbatim — do not summarize, paraphrase, or correct the AI's answers.
Score in `scoring_notes.md` after both conditions are complete.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | run_20260514T021302Z |
| model | unknown |
| provider | unknown |
| session date (UTC) | 2026-05-14 |
| temperature | unknown |
| system prompt | none |
| input provided | `.aieng` package resources listed in `condition_b_index.md` |

---

## Q1 — Feature inventory

**Question (verbatim):**
> What features or objects does this model contain? For each one, state:
> - its name
> - its type (or your best-guess type, if uncertain)
> - whether the type is confirmed by the source or is an inference on your part

**Raw AI response:**

## Q1. Features / objects in the model

The package identifies **four discovered objects** from the FreeCAD source: `Plate`, `MountingHole_1`, `MountingHole_2`, and `Flange_Top`. The object registry says these were generated from `FCStd Document.xml`, and also warns that the registry is an index rather than the ultimate source of truth. 

| Name                   |       Source object / label | Type stated in source | Feature type in feature graph | Confirmed or inferred?                                                                        |
| ---------------------- | --------------------------: | --------------------: | ----------------------------: | --------------------------------------------------------------------------------------------- |
| `Base plate` / `Plate` | `Plate`, label `Base plate` |           `Part::Box` |                  `base_plate` | `Part::Box` is source-recorded; `base_plate` is inferred/candidate via heuristic.             |
| `MountingHole_1`       |            `MountingHole_1` |    `PartDesign::Hole` |               `mounting_hole` | `PartDesign::Hole` is source-recorded; `mounting_hole` is inferred/candidate via heuristic.   |
| `MountingHole_2`       |            `MountingHole_2` |    `PartDesign::Hole` |               `mounting_hole` | `PartDesign::Hole` is source-recorded; `mounting_hole` is inferred/candidate via heuristic.   |
| `Flange_Top`           |                `Flange_Top` |     `PartDesign::Pad` |                      `flange` | `PartDesign::Pad` is source-recorded; `flange` is inferred/candidate via heuristic.           |

The feature graph explicitly states that recognition used `freecad_name_heuristic`, with medium confidence, and that feature type was inferred from the FreeCAD object name/type rather than confirmed CAD feature semantics. 

---

## Q2 — Mounting holes

**Question (verbatim):**
> Which objects in this model are mounting holes? Cite the evidence for your answer.
> If you are uncertain about any identification, state that explicitly and explain why.

**Raw AI response:**

## Q2. Which objects are mounting holes?

The objects identified as mounting holes are:

1. **`MountingHole_1`**
2. **`MountingHole_2`**

Evidence: both appear in the discovered object list as `PartDesign::Hole`, and the feature graph classifies both as `type: mounting_hole`. Each has parameters `Depth: 10.0` and `Diameter: 6.0`.  

However, the identification is **not fully confirmed geometry truth**. The conversion manifest records uncertainty notes saying these features were classified as `mounting_hole` from the FCStd object name and type and should be treated as candidates, not confirmed truth.  The feature graph also says all feature candidates are heuristic and require CAD feature-tree access in runtime mode or engineer review for confirmation. 

So: **yes, `MountingHole_1` and `MountingHole_2` are the mounting-hole candidates; the source strongly suggests they are holes, but the converter marks the semantic "mounting hole" classification as heuristic.**

---

## Q3 — Available geometry

**Question (verbatim):**
> What geometric information is currently available about this model?
> What geometric information is missing or could not be determined from the input?

**Raw AI response:**

## Q3. Geometric information available vs. missing

### Available geometric / parametric information

The model uses **millimeters** for length units, with force in N, mass in kg, and stress in MPa. 

The feature graph contains the following extracted parameter proposals:

| Feature          |                                       Available parameters |
| ---------------- | ---------------------------------------------------------: |
| `Base plate`     | `Length = 100.0 mm`, `Width = 50.0 mm`, `Height = 10.0 mm` |
| `MountingHole_1` |                     `Diameter = 6.0 mm`, `Depth = 10.0 mm` |
| `MountingHole_2` |                     `Diameter = 6.0 mm`, `Depth = 10.0 mm` |
| `Flange_Top`     |                      `Length = 40.0 mm`, `Width = 20.0 mm` |

These are described as parameters lifted from FreeCAD property values for proposal use; the converter does not regenerate geometry. 

### Missing or unavailable geometric information

The package explicitly says **real geometry extraction was not performed**. The completeness report lists `geometry/source.step` and `geometry/normalized.step` as missing, and states `real_geometry_extraction: false`. 

Missing geometry/topology details include:

| Missing information                                                                       | Evidence                                                                                                                       |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| B-rep / STEP geometry                                                                     | Conversion manifest says B-rep geometry is missing and requires FreeCAD runtime STEP export or external `aieng import-step`.   |
| Stable face / edge / body IDs                                                             | Conversion manifest says stable topology IDs are missing and require `aieng extract-topology --backend occ` on a STEP export.  |
| Topology map                                                                              | Completeness report lists `geometry/topology_map.json` as missing.                                                             |
| Adjacency graph / AAG                                                                     | Completeness report lists `graph/aag.json` as missing.                                                                         |
| Geometry references per feature                                                           | Each feature has empty `geometry_refs: {}` in the feature graph.                                                               |
| Hole positions, axes, placement, face ownership, through/blind confirmation from geometry | Not present in the extracted parameters; only diameter/depth are present for the holes.                                        |
| Flange height/thickness/placement/orientation                                             | Only length and width are present for `Flange_Top`.                                                                            |
| Interfaces/contact surfaces                                                               | Completeness report lists `objects/interface_graph.json` as missing.                                                           |

---

## Q4 — Explicit missingness

**Question (verbatim):**
> What information about this model is explicitly recorded as missing, unsupported,
> or uncertain? List each item with its source.
>
> If there is no explicit missingness record in the input, say so.

**Raw AI response:**

## Q4. Explicitly recorded missing, unsupported, or uncertain information

There **is** an explicit missingness record in the input. The conversion manifest and completeness report both record missing, unsupported, partial, and uncertain items.

### Missing / unsupported records

| Category              | Explicit record                                                                                |
| --------------------- | ---------------------------------------------------------------------------------------------- |
| Geometry              | B-rep geometry is missing; offline FCStd parsing did not produce STEP geometry.                |
| Geometry artifacts    | `geometry/source.step` and `geometry/normalized.step` are missing.                             |
| Topology              | Stable face/edge/body IDs and `geometry/topology_map.json` are missing.                        |
| Adjacency             | `graph/aag.json` is missing.                                                                   |
| Stable references     | Object IDs are slug-derived from FCStd names, not confirmed CAD-stable references.             |
| Parameters            | Non-numeric, computed, and constrained parameters were not extracted.                          |
| Assemblies            | Assembly structure status is unknown; converter does not inspect FCStd assembly structure.     |
| Materials             | Material assignments were not extracted.                                                       |
| Loads                 | Load definitions are missing / not present in FCStd `Document.xml`.                            |
| Boundary conditions   | Boundary-condition definitions are missing / not present in FCStd `Document.xml`.              |
| Mesh                  | Mesh was not generated; external meshing is required.                                          |
| Solver deck           | No solver deck is present.                                                                     |
| CAD-to-CAE mappings   | CAD-to-CAE mappings are missing and require geometry and mesh first.                           |
| Protected regions     | Protected regions are missing and must be provided by the engineer.                            |
| Writeback strategy    | L5 writeback metadata / roundtrip rebuild strategy is unsupported by the reference converter.  |
| CAE imports           | Solver deck, parsed materials, parsed boundary conditions, and parsed loads are missing.       |
| Mesh handoff contract | `simulation/mesh_handoff_contract.json` is missing.                                            |
| Evidence ledger       | `results/evidence_index.json` is missing, so no external tool evidence is recorded.            |
| Mesh evidence         | No mesh evidence has been imported; mesh generation or quality must not be claimed.            |
| Claim map             | `results/claim_map.json` is missing.                                                           |
| Tool trace            | `provenance/tool_trace.json` is missing.                                                       |
| Validation status     | `validation/status.yaml` is missing.                                                           |
| Visual resources      | `visual/model_manifest.json` and `visual/annotation_layers.json` are missing.                  |
| Interface graph       | `objects/interface_graph.json` is missing.                                                     |

### Explicit uncertainty records

The manifest lists uncertainty notes for all four feature candidates:

| Feature               | Explicit uncertainty                                                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `feat_plate`          | Classified as `base_plate` from object name `Plate` and type `Part::Box`; candidate, not confirmed truth.                     |
| `feat_mountinghole_1` | Classified as `mounting_hole` from object name `MountingHole_1` and type `PartDesign::Hole`; candidate, not confirmed truth.  |
| `feat_mountinghole_2` | Classified as `mounting_hole` from object name `MountingHole_2` and type `PartDesign::Hole`; candidate, not confirmed truth.  |
| `feat_flange_top`     | Classified as `flange` from object name `Flange_Top` and type `PartDesign::Pad`; candidate, not confirmed truth.              |

The package-level policy also says missing information should not be inferred, unsupported is not false, and the conversion is best-effort. 

---

## Q5 — FEM preprocessing readiness

**Question (verbatim):**
> A downstream engineer wants to perform finite element analysis on this model.
> Based on the available information:
>
> (a) What information is already present that would be useful for FEM preprocessing?
> (b) What information is missing that would need to be obtained from external sources?
> (c) List the external steps that would be needed before a solver could run.

**Raw AI response:**

## Q5. FEM readiness assessment

### Q5(a). Information already present useful for FEM preprocessing

Useful information already present:

| FEM-relevant item              | Available information                                                                                                                                                      |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source provenance              | Original source was `sample_bracket.FCStd`, converted from FreeCAD by `freecad_reference`, with source metadata recorded.                                                  |
| Unit system                    | Length in mm, force in N, mass in kg, stress in MPa.                                                                                                                       |
| Object / feature inventory     | Base plate, two hole candidates, and top flange candidate are identified.                                                                                                  |
| Approximate feature parameters | Plate dimensions, hole diameters/depths, and flange length/width are available as extracted parameter proposals.                                                           |
| Editability metadata           | Features are marked `proposal_allowed`, but the converter itself cannot regenerate geometry.                                                                               |
| Conversion boundary            | The package clearly states no solver, mesher, optimizer, or CAD edit was executed.                                                                                         |
| Missingness / handoff guidance | The completeness report lists next recommended actions such as topology extraction, simulation setup, mesh handoff contract, evidence scaffold, and mesh artifact import.  |

### Q5(b). Information missing before FEM could run

A downstream engineer would still need, at minimum:

| Required for FEM                | Missing from package                                                                               |
| ------------------------------- | -------------------------------------------------------------------------------------------------- |
| Usable solver geometry          | STEP/B-rep geometry is missing.                                                                    |
| Topological references          | Stable face/edge/body IDs and topology map are missing.                                            |
| Mesh                            | No mesh has been generated or imported.                                                            |
| Material model                  | Material assignments were not extracted.                                                           |
| Loads                           | Load definitions are missing.                                                                      |
| Boundary conditions             | Boundary-condition definitions are missing.                                                        |
| Analysis setup                  | `simulation/setup.yaml` is missing.                                                                |
| Solver deck                     | No solver deck is present.                                                                         |
| CAD-to-CAE mappings             | CAE mapping is missing and cannot be established until geometry and mesh exist.                    |
| Mesh handoff contract           | Missing.                                                                                           |
| Evidence / validation artifacts | Evidence index, claim map, validation status, mesh evidence, and external tool trace are missing.  |

### Q5(c). External steps needed before a solver could run

A practical FEM handoff would require these external steps:

1. **Open the original FreeCAD model** or otherwise access the preserved source FCStd.
2. **Export real CAD geometry**, preferably STEP/B-rep, because the package currently lacks `geometry/source.step` and `geometry/normalized.step`. 
3. **Extract topology** using an OCC-backed process such as `aieng extract-topology --backend occ` on the STEP export, to produce stable face/edge/body IDs. 
4. **Verify the feature candidates** against CAD geometry or engineer review, especially the semantic classifications `base_plate`, `mounting_hole`, and `flange`.  
5. **Define material properties**, since material assignments are not present. 
6. **Define loads and boundary conditions**, since neither is present in the converted FCStd metadata. 
7. **Define protected / non-editable regions or analysis regions**, if needed for safe preprocessing or design modification; these are missing. 
8. **Create a simulation setup file or equivalent analysis specification**, including analysis type, contacts, constraints, load cases, units, and solver settings. The report lists `simulation/setup.yaml` as missing. 
9. **Generate a mesh externally**, then import or record mesh evidence; the package explicitly says no mesh evidence has been imported. 
10. **Map CAD/topology entities to CAE entities**, producing explicit CAD-to-CAE mappings once geometry and mesh exist. 
11. **Create or import a solver deck**, such as an Abaqus/CalculiX-style input deck or another solver-specific model. The package says no solver deck is present. 
12. **Run validation / evidence recording**, including tool trace, evidence index, claim map, and validation status, so future claims about mesh, loads, solve status, or results are traceable. 

Bottom line: this package is useful as a **semantic and provenance scaffold** for a simple FreeCAD bracket-like model, but it is **not yet solver-ready**. It contains object names, candidate feature types, units, and a few dimensional parameters, but lacks the real geometry, topology, mesh, materials, loads, boundary conditions, solver deck, and evidence records required for finite element analysis.

---

## Session notes

none — session ran normally
