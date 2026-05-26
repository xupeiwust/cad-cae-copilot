# `.aieng` Expected Capabilities

This document records expected capabilities when a general AI reads the generated `.aieng` package contents from the reference bracket demo.

## Expected capabilities

### Start from `README_FOR_AI.md`

The AI can begin with `README_FOR_AI.md` to understand how to inspect the package, which files are derived summaries, which files are source-of-truth structured resources, and which claims are not validated.

### Inspect `manifest.json`

The AI can use `manifest.json` to discover package identity, units, provenance, and indexed resources.

### Cite feature IDs

The AI can cite feature IDs from `graph/feature_graph.json`, such as:

- `feat_base_plate_001`
- `feat_hole_001`
- `feat_hole_pattern_001`
- `feat_unknown_001`

The exact set depends on the current mock topology and rule-based recognizer output.

### Distinguish facts, candidates, user context, and unvalidated results

The AI can distinguish:

- extracted/mock topology facts from `geometry/topology_map.json`;
- inferred candidate features from `graph/feature_graph.json`;
- user-provided assumptions and context from `graph/constraints.json`, `simulation/setup.yaml`, and `ai/protected_regions.json`;
- unvalidated results, because no mesh or solver result exists in the package.

### Identify protected regions

The AI can identify protected feature IDs from `ai/protected_regions.json` and protection constraints from `graph/constraints.json`. It should be able to say why those features are protected and which operations are forbidden.

### State no solver result exists

The AI should state that no mesh generation has been run, no solver result has been attached, and no stress/displacement claim is validated unless future result resources are present.

### Use patch proposal JSON as structured output

The AI can inspect `ai/patches/patch_0001.json` as a structured, unexecuted proposal. It can cite expected effects, warnings, required validation steps, and protected targets checked/avoided.

### Avoid modifying protected targets

The AI can use protected-region and patch-proposal resources to avoid geometry-changing operations on protected features such as `feat_hole_pattern_001`.

### Inspect `validation/status.yaml` and identify claim policy

The AI can read `validation/status.yaml` to determine the current validation state of the package. It can cite:

- `solver_mesh_status.mesh_generation: not_run` — no mesh has been generated.
- `solver_mesh_status.solver_execution: not_run` — no solver has been run.
- `solver_mesh_status.stress_validation: not_validated` — no stress result is validated.
- `claim_policy.forbidden_claims` — the explicit list of claims the AI must not make (e.g. "The design is safe.", "A solver has been run.", "A mesh has been generated.", "Manufacturing feasibility has been validated.").
- `claim_policy.allowed_claims` — the explicit list of claims the AI may make (e.g. "The package contains structured engineering context.", "Patch proposals are unexecuted suggestions.", "Solver deck is a scaffold if present.").

The AI should be able to answer "What must you not claim about this model?" by citing the `forbidden_claims` list directly, without relying on general domain knowledge.

### Distinguish solver deck scaffold from actual solver result

The AI can read `simulation/solver_deck.inp` and correctly identify it as a scaffold, not a complete or runnable FEA model. It should be able to state:

- The deck contains a material block (`*MATERIAL`, `*ELASTIC`, `*DENSITY`) populated from `simulation/setup.yaml`.
- Boundary condition and load intent are recorded as CalculiX comments referencing feature IDs, not as active `*BOUNDARY` or `*CLOAD` sections.
- No `*NODE`, `*ELEMENT`, `*NSET`, or `*ELSET` sections are present — no mesh exists.
- No `*STEP` or `*STATIC` section is present — no analysis has been defined or run.
- The deck cannot be submitted to a solver in its current state; it requires mesh generation, node/element set definitions, and active boundary and load sections.

This capability tests whether the AI can distinguish between a structured engineering intent artifact and a completed solver run.

### Inspect CAE import and mapping resources

The AI can inspect Phase 10A/10B/10C CAE resources without treating them as solver evidence:

- `simulation/cae_imports/parsed_materials.json` lists imported CAE material entities.
- `simulation/cae_imports/parsed_boundary_conditions.json` identifies `FIXED_HOLES` as an imported CAE boundary-condition target.
- `simulation/cae_imports/parsed_loads.json` identifies `LOAD_FACE` as an imported CAE load target.
- `simulation/cae_mapping.json` distinguishes CAE target names from `.aieng` feature/interface IDs and records explicit user-provided mappings.
- `objects/interface_graph.json` can include Phase 10C `cae_refs` that link CAE entities to generated engineering interfaces.
- `objects/object_registry.json` can include CAE-to-interface and CAE-to-feature relationships for navigation.

The AI should state that `FIXED_HOLES` maps to `feat_hole_pattern_001` and `iface_feat_hole_pattern_001`, while `LOAD_FACE` maps to `feat_base_plate_001`, with `mapping_method: user_provided` and `confidence: high`. It should avoid claiming these mappings were inferred automatically. It should also avoid claiming CAE results exist: no mesh generation, solver execution, or result import is implied by these resources.

### Read visual annotation scaffold and distinguish from rendered geometry

The AI can read `visual/annotation_layers.json` (Phase 8A) and correctly interpret it as structured annotation metadata, not a rendered or visualized 3D model. It should be able to:

- Identify the four annotation layers: `features`, `protected_regions`, `simulation_targets`, `unknown_or_unclassified`.
- Map feature IDs to visual roles: `candidate_feature` for base plate and hole candidates, `protected_region` for the hole pattern protected boundary condition target, `simulation_context` for boundary condition and load targets, `unclassified_geometry` for unknown features.
- State explicitly that no 3D rendering, glTF preview, image, mesh visualization, or geometric output has been generated. The `visual_rendering: not_generated` field in `validation/status.yaml` and the annotation metadata itself confirm this.
- Avoid claiming that a visual view of the part is available or that any rendering artifact exists.

This capability tests whether the AI can distinguish between a structured feature-to-visual-role mapping and actual rendered geometry output.

## Expected outcome

In the `.aieng` condition, strong answers should be grounded in structured resources and object IDs. They should avoid claiming engineering safety, manufacturability, or solver-validated performance when no evidence exists.
