# AGENTS.md

This file gives AI coding agents the context and rules needed to work on this repository.

The project is an MVP for an **AI-native CAD/CAE engineering data format** called `.aieng`.

The goal is not to build a full CAD system or a full CAE system. The goal is to design and validate a self-describing engineering model package that makes CAD/CAE data natively intelligible to general AI systems.

`.aieng` is not merely an agent wrapper around existing CAD/CAE files. It is a structured engineering model repository that carries geometry references, topology, feature semantics, design intent, constraints, simulation context, validation state, visual mappings, and allowed operations in forms that an AI can inspect before calling external tools.

---

## 1. Project Mission

Traditional CAD/CAE files are optimized for geometry kernels, solvers, manufacturing systems, and GUI workflows.

This project explores a self-describing engineering model package optimized for general AI understanding, structured modification, deterministic validation, and export to existing CAD/CAE tools.

The core hypothesis:

> The file should carry enough engineering semantics that a general AI can understand the model before calling any tools.

AI agents should not directly edit raw CAD/CAE files. They should operate on a semantic engineering object graph that references precise geometry, captures design intent, stores simulation setup, records validation state, and supports validated patch proposals.

The reference scenario for v0.1 is:

> Import a single mechanical bracket STEP file, convert it into a `.aieng` package, generate topology and feature graphs, attach basic static structural simulation context, create AI-readable summaries, and produce patch proposals.

The bracket scenario is only a validation case. The real product is the `.aieng` format and supporting tooling.

---

## Core Position: Adapt CAD/CAE Data to AI

Most current AI-for-CAD/CAE approaches try to adapt AI to existing CAD/CAE files through specialized training, RAG, MCP tools, plugins, workflow agents, domain-specific skills, or fine-tuning.

This project takes the opposite direction:

> Adapt CAD/CAE data to AI.

The root problem is not only that current LLMs lack CAD/CAE ability. The deeper issue is that traditional CAD/CAE files were never designed to expose engineering meaning to general intelligence. They prioritize exact geometry kernels, solver input decks, graphical software state, or proprietary application workflows.

`.aieng` should therefore be a self-describing engineering model package. It should carry enough structured meaning for a capable general AI to understand the model's geometry references, topology, features, design intent, constraints, simulation context, validation state, visual mappings, and allowable modifications before using specialized external tools.

External tools are still expected and allowed for exact geometry operations, meshing, solving, manufacturing checks, and export. But they should not be prerequisites for basic engineering understanding. The package itself should explain what the model is, what matters, what is protected, what has been validated, what remains uncertain, and what operations are allowed.

Design implications:

1. `.aieng` is not merely an AI-agent intermediate layer around existing CAD/CAE files.
2. `.aieng` is closer to an engineering model repository than a single CAD file.
3. Structured data is the source of truth; prose summaries help AI consumption but must not replace schemas, IDs, references, constraints, or validation records.
4. External CAD/CAE tools execute and verify; the `.aieng` package carries the semantic context needed to decide what should be executed and verified.
5. Future resources should make validation state, visual-to-geometry mappings, allowable operations, assumptions, and uncertainty explicit.
6. Conversion should be best-effort with explicit missingness: translate available CAD/CAE information, and mark absent, unknown, partial, unsupported, or conflicting information in structured resources rather than guessing or fabricating it.

---

## 2. Non-Goals

Do not implement these in v0.1 unless explicitly requested:

1. A full CAD modeling application.
2. A full CAE platform.
3. A general-purpose parametric modeling kernel.
4. A complex assembly system.
5. Nonlinear contact analysis.
6. Fluid, thermal, fatigue, composite, or multiphysics simulation.
7. A custom geometry kernel.
8. Direct LLM editing of geometry files.
9. Perfect automatic feature recognition.
10. Full replacement of STEP, Parasolid, Abaqus, Nastran, Ansys, or other industry formats.

The project should stay focused on the data format, schemas, validators, and import/export pipeline.

---

## 3. Core Design Principle

The `.aieng` package is a structured, self-describing engineering model package.

It should separate:

1. Precise geometry resources.
2. Stable topology references.
3. Engineering features and semantic graph relationships.
4. Design intent, assumptions, and known limitations.
5. Constraints, protected regions, and allowed operations.
6. Simulation setup and analysis intent.
7. Validation state and evidence.
8. AI-readable summaries and structured AI context.
9. Patch proposals.
10. Exported solver artifacts.
11. Visual mappings and preview artifacts.

Do not collapse everything into one JSON file.

Do not use natural language as the source of truth when structured data is available.

Do not use mesh, images, point clouds, or thumbnails as the primary representation of CAD geometry.

---

## 4. Package Structure

A `.aieng` package should be treated as a zip package with typed resources.

Expected v0.1 structure:

```text
bracket_001.aieng/
├── manifest.json
├── geometry/
│   ├── source.step
│   ├── normalized.step
│   └── topology_map.json
├── graph/
│   ├── feature_graph.json
│   ├── semantic_graph.json
│   └── constraints.json
├── simulation/
│   ├── setup.yaml
│   ├── material_assignments.json
│   └── solver_deck.inp
├── ai/
│   ├── summary.md
│   ├── editable_variables.json
│   ├── protected_regions.json
│   └── patches/
├── results/
│   └── placeholder.json
└── previews/
    ├── thumbnail.png
    └── model.glb
```

Not every file must exist in the earliest phases, but the validator should be able to clearly report what is missing.

Future-facing package guidance:

1. Treat the package as an engineering model repository with typed resources, not as one monolithic CAD file.
2. Keep exact geometry files in `geometry/`, but expose AI-readable meaning through topology maps, feature graphs, semantic graphs, constraints, validation records, and summaries.
3. Add future validation-state resources without claiming solver evidence before it exists, for example `validation/state.json` or `results/validation_report.json`.
4. Add future visual mapping resources when previews exist, for example mappings from thumbnail or GLB selections back to topology and feature IDs.
5. Add future allowed-operation resources when patch execution is implemented, for example machine-readable operation catalogs and preconditions.
6. Preserve all cross-resource references with stable IDs.

---

## 5. Recommended Repository Structure

Use this structure unless the repository already has another agreed structure:

```text
aieng-format/
├── README.md
├── AGENTS.md
├── pyproject.toml
├── docs/
│   ├── format_spec_v0_1.md
│   ├── reference_scenario_bracket.md
│   └── architecture.md
├── schemas/
│   ├── manifest.schema.json
│   ├── topology_map.schema.json
│   ├── feature_graph.schema.json
│   ├── constraints.schema.json
│   └── patch_proposal.schema.json
├── src/
│   └── aieng/
│       ├── __init__.py
│       ├── cli.py
│       ├── package.py
│       ├── validate.py
│       ├── geometry/
│       │   ├── __init__.py
│       │   ├── step_importer.py
│       │   ├── topology_extractor.py
│       │   └── gltf_exporter.py
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── feature_graph.py
│       │   ├── feature_recognition.py
│       │   └── constraints.py
│       ├── simulation/
│       │   ├── __init__.py
│       │   ├── setup.py
│       │   ├── gmsh_mesher.py
│       │   └── calculix_exporter.py
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── summary_writer.py
│       │   ├── patch_schema.py
│       │   └── prompt_templates.py
│       └── examples/
│           └── bracket_reference.py
├── tests/
│   ├── test_package.py
│   ├── test_validate_manifest.py
│   ├── test_topology_map.py
│   ├── test_feature_graph.py
│   └── test_patch_proposal.py
└── examples/
    ├── bracket.step
    ├── bracket_user_context.yaml
    └── expected_output/
```

---

## 6. Development Phases

Follow the phases in order. Do not jump to CAD kernel integration before the format and validator are stable.

### Phase 0: Package, Schemas, Validator

Implement:

1. Python package `aieng`.
2. CLI entrypoint `aieng`.
3. `aieng init`.
4. `.aieng` zip package creation.
5. JSON schemas.
6. `aieng validate`.
7. Unit tests.

Success criteria:

1. Can create an empty `.aieng` package.
2. Can validate `manifest.json`.
3. Can report missing or invalid resources clearly.
4. Tests pass.

---

### Phase 1: STEP Import

Implement:

1. `aieng import-step <step_file> --out <package.aieng>`.
2. Copy input STEP to `geometry/source.step`.
3. Copy or normalize to `geometry/normalized.step`.
4. Update manifest.
5. Add validation checks.

Do not implement real topology extraction yet.

Success criteria:

1. Import command produces a valid `.aieng`.
2. `manifest.json` correctly references geometry resources.
3. Tests cover valid and missing STEP cases.

---

### Phase 2: Topology Map Interface

Implement a pluggable topology extraction interface.

Required components:

1. `TopologyExtractor` protocol or abstract base class.
2. `MockTopologyExtractor` for tests.
3. `OCCBasedTopologyExtractor` placeholder.
4. `aieng extract-topology <package.aieng>`.
5. `geometry/topology_map.json`.

The mock extractor should produce deterministic data for tests.

Do not block Phase 2 on OCCT bindings.

Success criteria:

1. `topology_map.json` conforms to schema.
2. Face, edge, and body IDs are stable within the test fixture.
3. The validator can detect missing geometry references.

---

### Phase 3: Basic Feature Graph

Implement rule-based feature recognition.

Required support:

1. Candidate holes from cylindrical faces.
2. Hole grouping by diameter and axis.
3. Mounting hole pattern.
4. Base plate candidate.
5. Unknown feature fallback.
6. User manual annotations.

Success criteria:

1. `feature_graph.json` conforms to schema.
2. Mounting holes can be represented.
3. Base plate can be represented.
4. Feature references point to topology IDs.

---

### Phase 4: Engineering Context and Constraints

Implement context application from YAML.

Required support:

1. Material assignment.
2. Protected features.
3. Fixed boundary conditions.
4. Force loads.
5. Static structural target constraints.
6. `simulation/setup.yaml`.
7. `graph/constraints.json`.

Success criteria:

1. User context can be converted into structured constraints.
2. Simulation setup references valid features.
3. Validator detects missing target features.

---

### Phase 5: AI Summary and Patch Proposal

Implement:

1. `aieng summarize`.
2. `ai/summary.md`.
3. Patch proposal schema.
4. Rule-based patch proposal generator.
5. Optional LLM-generated patch proposal, but only if schema validated.

Patch proposals must reference feature IDs.

Do not allow free-floating natural language operations with no object references.

Success criteria:

1. Summary lists features, constraints, materials, and simulation intent.
2. Patch proposal for "reduce mass by 15% while keeping mounting holes unchanged" can be generated.
3. Protected features are explicitly checked.
4. Patch proposal validates against schema.

---

### Phase 6: Solver Export

Implement basic CAE export.

Required support:

1. Read `simulation/setup.yaml`.
2. Generate placeholder or basic Gmsh/CalculiX artifacts.
3. Write `simulation/solver_deck.inp`.
4. Validate existence and basic content.

v0.1 does not need to complete a real solve.

Success criteria:

1. Solver deck contains material data.
2. Solver deck contains boundary condition data.
3. Solver deck contains load data.
4. Output path is recorded in manifest or simulation resources.

---

## 7. CLI Commands

The expected CLI shape:

```bash
aieng init --model-id bracket_001 --out bracket_001.aieng
aieng import-step examples/bracket.step --out bracket_001.aieng
aieng extract-topology bracket_001.aieng
aieng recognize-features bracket_001.aieng
aieng apply-context bracket_001.aieng --context examples/bracket_user_context.yaml
aieng summarize bracket_001.aieng
aieng propose-patch bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng export-calculix bracket_001.aieng --out build/solver_deck.inp
aieng validate bracket_001.aieng
```

Prefer clear error messages over silent failure.

---

## 8. Data Model Requirements

### 8.1 EngineeringModel

Represents the whole package.

Must include:

1. Model ID.
2. Format version.
3. Units.
4. Resource paths.
5. Creation metadata.

---

### 8.2 GeometryEntity

Represents a topology or geometry entity.

Supported v0.1 types:

```text
solid
shell
face
wire
edge
vertex
```

A face should ideally include:

1. ID.
2. Surface type.
3. Bounding box.
4. Area.
5. Normal or axis when applicable.
6. Radius for cylindrical faces when applicable.

---

### 8.3 Feature

Represents an engineering-level object.

Supported v0.1 feature types:

```text
base_plate
mounting_hole
mounting_hole_pattern
rib
fillet
chamfer
boss
flange
interface_face
unknown_feature
```

Each feature should include:

1. ID.
2. Type.
3. Name.
4. Geometry references.
5. Parameters.
6. Intent.
7. Relationships when applicable.

---

### 8.4 Constraint

Supported v0.1 constraint types:

```text
protect_geometry
protect_position
protect_dimension
min_value
max_value
preserve_interface
manufacturing_rule
simulation_target
```

Each constraint should include:

1. ID.
2. Type.
3. Target.
4. Reason.
5. Optional parameter and value.

---

### 8.5 SimulationSetup

v0.1 supports only:

```text
static_structural
```

The simulation setup should include:

1. Solver target.
2. Units.
3. Materials.
4. Material assignments.
5. Boundary conditions.
6. Loads.
7. Mesh settings.
8. Requested outputs.

---

### 8.6 AIContext

AI context includes:

1. Human-readable engineering summary.
2. Editable variables.
3. Protected regions.
4. Assumptions.
5. Known limitations.
6. Validation state summary.
7. Allowed operation summary.
8. Visual-to-geometry reference hints when preview artifacts exist.

The AI context is useful for general AI understanding, but structured JSON/YAML remains the source of truth. AI context must summarize or point to structured facts; it must not become the only place where important engineering meaning is stored.

---

### 8.7 PatchProposal

Patch proposals are how AI agents suggest model modifications.

A patch proposal must include:

1. Patch ID.
2. User intent.
3. Status.
4. Operations.
5. Target feature IDs.
6. Protected target checks.
7. Expected effects.
8. Required validation steps.

Allowed operation types for v0.1:

```text
modify_parameter
add_feature
remove_feature
protect_feature
assign_material
assign_boundary_condition
assign_load
```

---

## 9. Validator Rules

`aieng validate` must check at least:

1. `manifest.json` exists.
2. Format version is supported.
3. Required resource paths exist.
4. JSON files conform to schema.
5. Feature geometry references exist in topology map.
6. Constraints reference existing features.
7. Simulation setup references existing features.
8. Patch proposals do not modify protected targets without explicit violation status.
9. Units are present and consistent.
10. Missing optional files are warnings, not hard failures, unless required by current phase.

Validator output should be human-readable and testable.

Preferred output style:

```text
PASS manifest.json exists
PASS format_version = 0.1.0
PASS geometry/source.step exists
WARN graph/semantic_graph.json missing
FAIL feature feat_hole_001 references unknown face face_999
```

---

## 10. AI Agent Coding Rules

When working on this repository, AI agents must follow these rules:

1. Preserve the project scope.
2. Prefer simple, testable code.
3. Do not introduce heavy CAD dependencies before Phase 2 is stable.
4. Do not hard-code one CAD kernel as the only possible backend.
5. Keep topology extraction pluggable.
6. Validate all generated structured data.
7. Use IDs for all cross-references.
8. Do not store important facts only in prose.
8a. Do not silently fill missing CAD/CAE information. If material, loads, boundary conditions, protected regions, solver results, mesh evidence, or geometry-modification evidence are absent, record that absence explicitly.
9. Do not overwrite geometry resources without explicit command.
10. Do not claim engineering validity without validator or solver evidence.
11. Write tests for every CLI command.
12. Keep schemas versioned.
13. Prefer deterministic fixtures for tests.
14. Keep generated package contents reproducible where practical.
15. Avoid hidden side effects.

---

## 11. AI Agent Safety Rules for Engineering Claims

AI-generated output must distinguish between:

1. Known facts from structured data.
2. Inferred engineering meaning.
3. User-provided assumptions.
4. Unvalidated suggestions.
5. Solver-validated results.

Do not write:

> This design is safe.

Unless there is actual validated solver evidence and the criteria are defined.

Prefer:

> The current patch proposal requires validation through geometry checks, meshing, and static structural analysis before it can be considered acceptable.

Do not write:

> The maximum stress is below the target.

Unless solver results exist and were parsed.

Prefer:

> The target maximum von Mises stress is 120 MPa. No solver result has been attached yet.

---

## 12. Recommended Dependencies

For early phases:

```text
python >= 3.11
pydantic
jsonschema
pyyaml
typer
rich
pytest
```

Optional later dependencies:

```text
networkx
gmsh
pythonocc-core
cadquery
```

Do not add optional heavy dependencies to the core package unless needed.

Use extras when possible:

```toml
[project.optional-dependencies]
geometry = ["cadquery", "pythonocc-core"]
meshing = ["gmsh"]
dev = ["pytest", "ruff", "mypy"]
```

---

## 13. Coding Style

Preferred style:

1. Python 3.11+.
2. Type hints.
3. Small modules.
4. Explicit data classes or Pydantic models.
5. Clear CLI errors.
6. Unit tests for each phase.
7. No large hidden global state.
8. No network calls in tests.
9. No reliance on external CAD binaries for early tests.
10. Use fixtures for package contents.

---

## 14. Testing Strategy

Tests should cover:

1. Creating a package.
2. Reading and writing `manifest.json`.
3. Validating required resources.
4. Schema validation failures.
5. Importing STEP as a copied resource.
6. Mock topology extraction.
7. Feature graph references.
8. Constraint references.
9. Simulation setup references.
10. Patch proposal validation.
11. CLI happy paths.
12. CLI error paths.

Avoid tests that require a real CAD kernel until the geometry backend is explicitly enabled.

---

## 15. Example User Context YAML

Use this as the starting reference fixture:

```yaml
material: Al6061-T6

protected_features:
  - feat_hole_pattern_001

simulation:
  type: static_structural
  fixed:
    - feat_hole_pattern_001
  loads:
    - target: feat_top_flange_001
      type: force
      value_n: 500
      direction: [1, 0, 0]

targets:
  max_von_mises_stress_mpa: 120
```

---

## 16. Example Patch Intent

Agents should be able to handle this intent:

```text
Reduce mass by 15% while keeping mounting holes unchanged.
```

A valid response should be a structured patch proposal, not just prose.

It should include operations such as:

1. Modify rib thickness.
2. Add lightening pocket.
3. Preserve mounting hole pattern.
4. Require geometry validation.
5. Require mesh validation.
6. Require static structural validation.

---

## 17. Done Criteria for v0.1

The v0.1 milestone is complete when the repository can run a scripted demo:

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng
aieng recognize-features build/bracket_001.aieng
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml
aieng summarize build/bracket_001.aieng
aieng propose-patch build/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng export-calculix build/bracket_001.aieng --out build/solver_deck.inp
aieng validate build/bracket_001.aieng
```

The demo may use a mock topology extractor in v0.1, as long as the data format and validation chain are real.

---

## 18. Implementation Priority

Build in this order:

1. Package format.
2. Manifest schema.
3. Validator.
4. STEP import as resource copy.
5. Mock topology map.
6. Feature graph.
7. Constraints.
8. Simulation setup.
9. AI summary.
10. Patch proposal.
11. Solver deck export.
12. Real CAD kernel integration.

Do not reverse this order unless explicitly instructed.

---

## 19. Important Architectural Rule

The most important architectural rule:

> The `.aieng` file should carry enough engineering semantics that a general AI can understand the model before calling any tools; AI agents generate structured proposals, and deterministic tools validate and execute them.

This means:

1. The package explains model meaning through structured resources.
2. LLMs can inspect, reason, and propose.
3. Schemas constrain.
4. Validators check.
5. Geometry kernels execute exact geometry operations.
6. Meshers and solvers verify analysis claims.
7. Reports explain evidence, assumptions, and uncertainty.

Never let the LLM be the only authority for engineering correctness.

---

## 20. Suggested First Task for Codex

Start with this:

```text
Implement Phase 0 for the .aieng format project.

Create a Python package named aieng with:

1. A CLI entrypoint `aieng`.
2. `aieng init --model-id <id> --out <package.aieng>`.
3. `.aieng` as a zip package containing manifest.json and empty typed directories.
4. JSON schemas for manifest, topology_map, feature_graph, constraints, and patch_proposal.
5. `aieng validate <package.aieng>`.
6. Unit tests for init and validate.

Keep implementation simple. Do not implement STEP import or CAD parsing yet.
```

---

## 21. Project Positioning

This project is not CAD.

This project is not CAE.

This project is:

> A self-describing engineering model package that adapts CAD/CAE data to general AI understanding while preserving structured references, validation, and export paths to deterministic engineering tools.

The first reference scenario is static structural analysis of a mechanical bracket.

The long-term asset is the `.aieng` format, schemas, validator, semantic model resources, patch mechanism, validation records, visual mappings, allowed-operation model, and import/export pipeline.
