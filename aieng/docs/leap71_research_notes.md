# LEAP71 Research Notes for `.aieng`

This document summarizes public research notes about LEAP71, PicoGK, ShapeKernel, and Noyron, and translates the useful lessons into design implications for the `.aieng` project.

The purpose of this document is not to copy LEAP71's system. The purpose is to learn from their public Computational Engineering approach and use it as inspiration for an AI-native CAD/CAE data format.

---

## 1. Why LEAP71 Matters for `.aieng`

LEAP71 is relevant because their public work points toward a similar thesis:

> Traditional CAD is not the ideal center of AI-native engineering workflows.

Their public materials suggest a workflow where engineering logic, physical constraints, manufacturing knowledge, and computational geometry are encoded into software models that generate engineering artifacts.

This is close to the direction of `.aieng`, but with an important difference:

```text
LEAP71 direction:
Computational engineering model -> generated geometry / manufacturing / simulation outputs

.aieng current direction:
Imported CAD/CAE files -> AI-readable engineering semantic layer -> validation / export / patch proposals
```

These two directions can eventually meet.

A strong future definition for `.aieng` is:

> `.aieng` is an AI-native engineering model exchange format for both imported CAD/CAE models and generated computational engineering models.

---

## 2. Public LEAP71 Concepts Worth Studying

### 2.1 Computational Engineering

LEAP71 describes its approach as Computational Engineering.

The important idea is that engineering design should not be represented only as manually created CAD geometry. Instead, engineering rules, physical reasoning, design constraints, manufacturing constraints, and geometry generation can be encoded in computational models.

For `.aieng`, the lesson is:

> The data format should not only preserve geometry. It should also preserve engineering logic, assumptions, constraints, and validation state.

---

### 2.2 PicoGK

PicoGK is LEAP71's open-source compact geometry kernel.

Public repository:
`https://github.com/leap71/PicoGK`

Important characteristics to study:

1. It is designed for computational engineering.
2. It is not a traditional feature-tree CAD kernel.
3. It appears oriented toward generated geometry, fields, voxels, meshes, lattices, and complex manufacturable shapes.
4. It is useful as a reference for how computational geometry systems can be exposed to developers.
5. It may be useful in future `.aieng` experiments, but it should not become a required dependency in v0.1.

Implication for `.aieng`:

```text
Do not hard-code `.aieng` to only support STEP/B-rep.
Do not hard-code `.aieng` to only support voxel/mesh/implicit geometry either.
Keep geometry resources backend-neutral.
```

Potential future geometry resource types:

```text
brep_step
brep_native
mesh
voxel_field
implicit_field
scalar_field
vector_field
lattice
preview_gltf
```

---

### 2.3 ShapeKernel

ShapeKernel is another public LEAP71 repository.

Public repository:
`https://github.com/leap71/LEAP71_ShapeKernel`

It appears to sit above PicoGK and provide reusable shape construction abstractions. It is useful as a reference for how low-level geometry operations can be lifted into higher-level shape primitives.

For `.aieng`, the lesson is:

> We may need both engineering features and shape primitives.

These are not the same thing.

Example distinction:

```text
Engineering Feature:
mounting_hole_pattern
- means: bolt interface
- important for: assembly, constraints, simulation, design intent

Shape Primitive:
cylindrical_cut
- means: geometric construction operation
- important for: geometry generation or modification
```

Possible future `.aieng` distinction:

```text
Feature
- engineering meaning
- design role
- constraints
- simulation relevance

ShapePrimitive
- construction method
- boolean operation
- geometry parameters
- generation backend
```

---

### 2.4 Noyron

Noyron appears to be LEAP71's proprietary computational engineering system.

Public descriptions suggest it encodes engineering knowledge, physical models, manufacturing rules, and geometry generation logic into a reusable computational framework.

Because Noyron is proprietary, do not assume implementation details.

For `.aieng`, the public-level lesson is:

> A serious AI-native engineering format should store more than geometry and summaries. It should store the logic and validation context that explain why a design exists.

This motivates adding future directories such as:

```text
engineering_logic/
manufacturing/
validation/
```

---

## 3. What We Should Learn From LEAP71

### Lesson 1: The Center Should Be the Engineering Model, Not the CAD File

Traditional CAD files describe shapes.

AI-native engineering systems need to describe:

1. What the object is.
2. Why it exists.
3. What constraints govern it.
4. Which features can be changed.
5. Which interfaces must remain fixed.
6. What physical targets it must satisfy.
7. Which manufacturing process is assumed.
8. What validation has been performed.
9. Which assumptions are unvalidated.

Implication:

```text
.aieng should be an engineering model package, not just a CAD wrapper.
```

---

### Lesson 2: Geometry Is Necessary but Not Sufficient

A `.step` file can encode precise geometry, but it usually does not encode enough design intent.

A mesh or rendered image can help AI perceive shape, but it cannot reliably preserve:

1. Exact dimensions.
2. Parametric constraints.
3. Assembly interfaces.
4. Manufacturing intent.
5. Simulation boundary conditions.
6. Engineering tradeoffs.

Implication:

```text
.aieng should preserve precise geometry and attach semantic layers to it.
```

---

### Lesson 3: Support Both Imported and Generated Models

The original `.aieng` MVP focuses on imported CAD:

```text
STEP -> .aieng -> topology map -> feature graph -> simulation setup -> patch proposal
```

LEAP71's public work suggests a complementary future path:

```text
computational engineering model -> generated geometry -> .aieng -> simulation/manufacturing outputs
```

Implication:

`.aieng` should support two long-term modes:

```text
Mode A: Imported Model Mode
- Source comes from STEP or another CAD/CAE format.
- The system extracts topology, features, constraints, and AI context.

Mode B: Generated Model Mode
- Source comes from computational engineering rules or code.
- The system stores generation parameters, design rules, geometry outputs, and validation outputs.
```

---

### Lesson 4: Engineering Logic Should Be a First-Class Resource

The current v0.1 `.aieng` structure includes:

```text
geometry/
graph/
simulation/
ai/
results/
previews/
```

Inspired by LEAP71, future versions should consider:

```text
engineering_logic/
manufacturing/
validation/
```

Possible future package structure:

```text
bracket_001.aieng/
├── manifest.json
├── geometry/
├── graph/
├── simulation/
├── engineering_logic/
│   ├── design_rules.yaml
│   ├── assumptions.yaml
│   ├── performance_targets.yaml
│   └── generation_parameters.json
├── manufacturing/
│   ├── process.yaml
│   ├── constraints.yaml
│   └── inspection_plan.yaml
├── validation/
│   ├── simulation_results.json
│   ├── physical_test_results.json
│   ├── discrepancy_report.json
│   └── validation_status.yaml
├── ai/
├── results/
└── previews/
```

For v0.1, these can remain future-facing concepts. Do not implement them unless explicitly requested.

---

### Lesson 5: AI Should Propose, Deterministic Systems Should Validate

LEAP71's public positioning emphasizes computation, physical constraints, and manufacturing rules.

For `.aieng`, this reinforces the rule:

> AI agents generate structured proposals. Deterministic tools validate and execute them.

Never let the LLM be the only authority for engineering correctness.

Correct flow:

```text
User intent
  -> AI patch proposal
  -> schema validation
  -> constraint validation
  -> geometry operation
  -> mesh generation
  -> solver validation
  -> report
```

Incorrect flow:

```text
User intent
  -> LLM directly edits geometry
  -> LLM claims design is valid
```

---

## 4. What We Should Not Copy

Do not blindly copy LEAP71's approach.

### 4.1 Do Not Make PicoGK a Required v0.1 Dependency

PicoGK is interesting, but `.aieng` v0.1 needs to first stabilize:

1. Package structure.
2. Manifest.
3. Schemas.
4. Validator.
5. STEP resource import.
6. Mock topology map.
7. Feature graph.
8. Patch proposal mechanism.

Heavy geometry dependencies should come later.

---

### 4.2 Do Not Abandon STEP/B-rep

LEAP71's public tools appear strongly oriented toward generated complex geometry. That does not remove the need for traditional CAD interoperability.

For `.aieng`, STEP and B-rep remain important because many existing engineering models come from traditional CAD systems.

Principle:

```text
Support generated geometry in the future, but keep imported CAD support strong.
```

---

### 4.3 Do Not Treat Mesh or Voxel Data as the Only Truth

Generated geometry systems often use mesh, voxel, implicit, or field-based representations.

These are powerful, especially for additive manufacturing and complex geometries.

But many mechanical engineering workflows still need:

1. Precise interfaces.
2. Hole positions.
3. Mating surfaces.
4. Tolerances.
5. Assembly constraints.
6. B-rep export.

Principle:

```text
.aieng should allow multiple geometry representations and clearly label their role.
```

---

### 4.4 Do Not Infer Proprietary Noyron Details

Noyron is proprietary.

Only rely on public statements at the conceptual level.

Do not claim compatibility with Noyron.

Do not claim to reproduce Noyron.

Do not use private or reverse-engineered implementation details.

---

## 5. Concrete Implications for `.aieng`

### 5.1 Add Future-Ready Manifest Concepts

Do not implement all of these in v0.1, but design the manifest so future resource groups are possible.

Possible future `manifest.json` resource groups:

```json
{
  "resources": {
    "geometry": {
      "source": "geometry/source.step",
      "normalized": "geometry/normalized.step",
      "preview": "previews/model.glb"
    },
    "graph": {
      "topology_map": "geometry/topology_map.json",
      "feature_graph": "graph/feature_graph.json",
      "constraints": "graph/constraints.json"
    },
    "simulation": {
      "setup": "simulation/setup.yaml",
      "solver_deck": "simulation/solver_deck.inp"
    },
    "engineering_logic": {
      "design_rules": "engineering_logic/design_rules.yaml",
      "assumptions": "engineering_logic/assumptions.yaml"
    },
    "manufacturing": {
      "process": "manufacturing/process.yaml",
      "constraints": "manufacturing/constraints.yaml"
    },
    "validation": {
      "status": "validation/validation_status.yaml",
      "simulation_results": "validation/simulation_results.json"
    },
    "ai": {
      "summary": "ai/summary.md",
      "protected_regions": "ai/protected_regions.json"
    }
  }
}
```

For Phase 0, an empty `resources` object is acceptable.

---

### 5.2 Add Geometry Backend Metadata

Future geometry resources should declare their backend and representation type.

Example:

```json
{
  "geometry_resources": [
    {
      "id": "geom_source_step",
      "path": "geometry/source.step",
      "representation": "brep_step",
      "backend": "external_cad",
      "role": "source"
    },
    {
      "id": "geom_generated_mesh",
      "path": "geometry/generated_mesh.obj",
      "representation": "mesh",
      "backend": "picogk",
      "role": "derived"
    },
    {
      "id": "geom_preview",
      "path": "previews/model.glb",
      "representation": "preview_gltf",
      "backend": "threejs",
      "role": "visualization"
    }
  ]
}
```

This helps `.aieng` avoid being tied to one geometry system.

---

### 5.3 Separate Features From Shape Primitives

Future schema idea:

```json
{
  "features": [
    {
      "id": "feat_hole_pattern_001",
      "type": "mounting_hole_pattern",
      "engineering_role": "mounting_interface",
      "geometry_refs": {
        "faces": ["face_021", "face_022"]
      }
    }
  ],
  "shape_primitives": [
    {
      "id": "shape_cylindrical_cut_001",
      "type": "cylindrical_cut",
      "construction_role": "subtractive_geometry",
      "parameters": {
        "diameter_mm": 6.5,
        "depth_mm": 8.0
      },
      "produces_feature": "feat_hole_001"
    }
  ]
}
```

This distinction is important if `.aieng` eventually supports generated computational engineering models.

---

### 5.4 Add Design Rule Resources Later

Future design rules could look like:

```yaml
rules:
  - id: rule_min_hole_edge_distance
    type: manufacturing_rule
    description: Hole edge distance should be at least 2x hole diameter.
    applies_to: mounting_hole
    expression: edge_distance_mm >= 2 * diameter_mm
    severity: error

  - id: rule_min_wall_thickness
    type: manufacturing_rule
    description: Minimum wall thickness for metal LPBF.
    applies_to: thin_wall
    expression: thickness_mm >= 1.2
    severity: warning
```

For v0.1, these should remain conceptual.

---

### 5.5 Add Validation State Later

A future validation file could look like:

```yaml
validation_status:
  geometry_validity:
    status: pass
    checked_at: "2026-05-06T00:00:00Z"

  mesh_generation:
    status: not_run

  static_structural_analysis:
    status: not_run

  manufacturing_rules:
    status: warning
    warnings:
      - rule_min_wall_thickness not evaluated
```

This helps AI agents avoid overstating engineering certainty.

---

## 6. Suggested Update to `AGENTS.md`

Add this section to `AGENTS.md`:

```markdown
## LEAP71-Inspired Architectural Note

Public LEAP71 projects such as PicoGK and ShapeKernel are useful references for Computational Engineering workflows.

Agents may study these public repositories for inspiration, especially around generated geometry, reusable shape primitives, and computational engineering models.

However:

1. Do not copy proprietary LEAP71/Noyron concepts.
2. Do not assume Noyron implementation details.
3. Do not make PicoGK or ShapeKernel required dependencies in v0.1.
4. Do not abandon STEP/B-rep interoperability.
5. Keep `.aieng` backend-neutral.
6. Design `.aieng` to eventually support both imported CAD models and generated computational engineering models.

The key lesson is:

> `.aieng` should represent an engineering model, not merely a CAD file.
```

---

## 7. Suggested Future Codex Prompt

Use this after Phase 0 is complete.

```text
Read AGENTS.md and docs/leap71_research_notes.md.

Update the architecture documentation to clarify that `.aieng` should support two long-term modes:

1. Imported Model Mode:
   Existing CAD/CAE files are imported and converted into an AI-readable semantic engineering package.

2. Generated Model Mode:
   Computational engineering models generate geometry, simulation setup, manufacturing data, and validation outputs into the `.aieng` package.

Do not implement Generated Model Mode yet.

Only update documentation and schemas in a future-compatible way. Keep Phase 0 behavior unchanged.
```

---

## 8. Open Questions

These questions should be revisited after Phase 0 and Phase 1.

### 8.1 Geometry Representation

Should `.aieng` define a unified geometry resource registry that supports STEP, B-rep, mesh, voxel, implicit, and field data?

Likely answer: yes, but not in v0.1.

---

### 8.2 Engineering Logic

Should engineering logic be stored as declarative YAML, executable code, or both?

Possible answer:

```text
v0.1-v0.2: declarative YAML only
future: declarative rules + executable computational model references
```

---

### 8.3 Generated Model Provenance

If a model is generated by code, should `.aieng` store:

1. Code hash?
2. Generator name?
3. Input parameters?
4. Dependency versions?
5. Random seeds?
6. Output geometry references?

Likely answer: yes.

---

### 8.4 AI Patch Execution

Should AI patch proposals eventually target:

1. Feature graph only?
2. Shape primitives?
3. Engineering logic rules?
4. Geometry kernel operations?
5. All of the above?

Likely answer:

```text
Start with feature graph and simulation setup.
Later support shape primitives and engineering logic.
Only then support geometry execution.
```

---

## 9. Practical Recommendation

Do not change Phase 0.

Phase 0 should remain:

1. Package format.
2. Manifest.
3. Schemas.
4. Validator.
5. CLI.
6. Tests.

After Phase 0, add the LEAP71-inspired design direction as documentation and future schema extensibility.

Recommended next file additions:

```text
docs/leap71_research_notes.md
docs/architecture.md
docs/future_generated_model_mode.md
```

Recommended future schema additions:

```text
geometry_resource.schema.json
engineering_logic.schema.json
manufacturing_constraints.schema.json
validation_status.schema.json
```

But do not implement these until the base package and validator are solid.

---

## 10. Summary

LEAP71 provides strong public evidence that AI-native engineering should move beyond manual CAD workflows.

The key inspiration for `.aieng` is:

```text
Engineering logic should be stored.
Design intent should be explicit.
Geometry should be precise but backend-neutral.
Simulation and manufacturing context should be first-class.
AI should propose changes through structured patches.
Deterministic validators and solvers should check correctness.
```

The most important framing update is:

> `.aieng` is not just an AI-friendly CAD file. It is an AI-native engineering model package that can support both imported CAD/CAE models and generated computational engineering models.
