# Architecture

This document describes the current Phase 0 `.aieng` package shape and a future-facing architecture. The future-facing structure is not implemented yet and must not change Phase 0 behavior.

`.aieng` is positioned first as a CAD/CAE-side semantic export and evidence layer for AI-readable engineering state. It can carry semantic task-understanding layer metadata for AGI-assisted CAX process chains, but it complements STEP/CAD/CAE artifacts and does not replace deterministic CAD/CAE execution tools. MCP and other agent-facing tools are optional access interfaces, not the core architecture.

## CAX Process-Chain View

Conservative process-chain interpretation:

1. CAD/STEP/CAE input artifacts provide deterministic geometry, setup, deck, mesh, or result definitions.
2. CAD/CAE-side exporters, importers, or mapping tools write `.aieng` resources with traceable IDs, topology/feature/constraint context, validation state, and structured action proposals.
3. AGI/AI agents inspect `.aieng` resources through files or optional access interfaces such as MCP, then configure or request explicit CAD/CAE operations.
4. External CAD/CAE software executes geometry editing, meshing, solving, result generation, and manufacturing checks.
5. `.aieng` records references, mappings, imported summaries, validation evidence, and remaining uncertainty from those external tools.

Global import policy for this architecture:

Import commands are evidence-only by default and must not automatically advance claim status. Claim proposals are review artifacts requiring human review. The import layers are:

1. Artifact presence: imported files or package resources are attached and referenced.
2. Parsed facts: deterministic extracted fields or observations are recorded as structured data when available.
3. Claim linkage: evidence may link to tracked claim IDs so support relationships are explicit.
4. Claim status review: claim status changes require human review with traceable evidence IDs.

Structured resources are source of truth. Markdown summaries are derived aids.

Canonical AI-facing reference handles are defined in `docs/reference_notation.md` and implemented via `aieng ref-inspect`, `aieng ref-list`, and `aieng ref-check`.

The CAD/CAE emitter and writeback contract is documented in `docs/cad_cae_emitter_contract.md`. It defines capability levels for tools that can only attach artifacts, tools that can emit topology/features/simulation setup, and tools that can write back evidence after external execution.

## Reversible Edit Grounding

Phase 13 introduces a conservative edit-grounding split. Semantic edits can update structured feature parameters and record execution metadata, but that does not imply arbitrary CAD geometry modification. Reversible or executable CAD write-back requires an explicit parametric regeneration source and write-back strategy, then external CAD software remains responsible for producing the modified CAD artifact. Until such a source exists, mock/OCP-extracted parameters remain semantic-only. External CAE tools remain responsible for mesh generation, solver execution, and result generation; `.aieng` records setup intent, mappings, and evidence rather than becoming a mesher or solver.

## Current Phase 0 Structure

Phase 0 creates a `.aieng` zip package with `manifest.json` and typed empty directories:

```text
.aieng/
├── manifest.json
├── geometry/
├── graph/
├── simulation/
├── ai/
├── results/
└── previews/
```

Current Phase 0 behavior is intentionally minimal:

- `manifest.json` records model identity, format version, units, resources, and creation metadata.
- Empty typed directories reserve package locations for later resources.
- `aieng validate` checks the manifest, supported version, units, resource references, optional missing resources, and JSON schemas when present.
- Phase 0 does not import STEP, parse CAD, extract topology, recognize features, build simulation setup, generate patches, or export solver decks.

## Future-Facing Architecture

A future `.aieng` package may evolve toward a self-describing engineering model repository such as:

```text
.aieng/
├── README_FOR_AI.md
├── manifest.json
├── geometry/
├── objects/
│   ├── object_registry.json
│   ├── topology_map.json
│   └── feature_graph.json
├── intent/
│   ├── design_intent.yaml
│   ├── assumptions.yaml
│   └── tradeoffs.yaml
├── constraints/
│   ├── protected_regions.yaml
│   ├── allowed_operations.json
│   └── engineering_constraints.yaml
├── simulation/
│   ├── setup.yaml
│   └── validation_targets.yaml
├── validation/
│   ├── status.yaml
│   └── evidence/
├── visual/
│   ├── model.glb
│   ├── feature_snapshots/
│   └── annotation_layers.json
└── history/
    ├── decisions.md
    └── changes.jsonl
```

This future structure is guidance only. It is not part of the current Phase 0 runtime contract.

## Architectural Roles

- `README_FOR_AI.md`: concise package-level orientation for a general AI, pointing to structured resources rather than replacing them.
- `manifest.json`: package index, format version, units, resource paths, provenance, and later validation/compatibility metadata.
- `geometry/`: exact geometry resources such as source and normalized CAD files.
- `objects/`: stable object registry, topology references, and engineering feature graph.
- `intent/`: design intent, assumptions, and tradeoffs that explain why geometry and constraints exist.
- `constraints/`: protected regions, allowed operations, engineering limits, and modification preconditions.
- `simulation/`: intended analysis setup, material assignments, boundary conditions, loads, and validation targets.
- `validation/`: validation status and evidence from deterministic tools; this prevents prose-only engineering claims.
- `visual/`: previews and mappings from visual artifacts back to object, topology, and feature IDs.
- `history/`: decisions, patches, changes, and rationale over time.

## Phase Boundary

Do not retrofit this future layout into Phase 0 code until a later phase explicitly requires it. The current implementation should remain compatible with the existing Phase 0 package creation and validation tests.
