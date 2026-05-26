# Core Position: Adapt CAD/CAE Data to AI

Most AI-for-CAD/CAE approaches try to adapt AI to existing CAD/CAE systems. They add specialized fine-tuning, RAG, MCP tools, plugins, workflow agents, domain-specific skills, or other external scaffolding around files and applications that were not designed for general AI understanding.

`.aieng` takes the opposite approach: adapt CAD/CAE data to AI.

Core positioning phrase: **`.aieng` is a CAD/CAE-side semantic export and evidence package for AI-readable engineering state.**

Secondary usage phrase: **`.aieng` can carry semantic task-understanding layer metadata for AGI-assisted CAX process chains.**

Target phrase: **Self-describing engineering model package for general AI.**

> This file is the **inward-facing** positioning doc — the architectural rationale. For outward-facing product messaging, use **Better CAD agents start with better engineering context.** and see [`public-positioning.md`](public-positioning.md). Delivery focus remains core `.aieng` format capability, adapters, and real end-to-end product demonstrations.

Traditional CAD/CAE files were designed primarily for geometry kernels, solvers, manufacturing systems, and GUI tools. They encode exact geometry, solver decks, or application state, but they often do not expose why a part exists, which features matter, which interfaces are protected, which assumptions are active, which results are validated, or which modifications are allowed.

`.aieng` should become a self-describing engineering model package. Its goal is not merely to wrap CAD/CAE files for an agent. Its goal is to carry enough structured engineering meaning that a capable general AI can inspect the package and form a basic, traceable understanding of the model before using specialized tools.

The primary origin of the package should be CAD/CAE-side export, import, mapping, or evidence capture. Agent-facing access methods such as MCP are optional interfaces for consuming the package; they are not the center of the product and must not dictate the core data model.

A useful shorthand: the `.aieng` package is the house; CLI, MCP, and agent tools are windows into that house. Improve the windows when useful, but do not mistake them for the product.

`.aieng` does not replace STEP, CAD, CAE, meshing, solver, or manufacturing tools. It complements STEP/AP242/CAE decks with explicit semantic context so AGI/AI systems can reason about engineering tasks before driving external CAD/CAE tool calls.

“The file should carry enough engineering semantics that a general AI can understand the model before calling any tools.”

A mature `.aieng` package should help a general AI understand:

- what the part or engineering model is;
- the main geometry references and topology IDs;
- engineering features such as ribs, holes, flanges, plates, bosses, and interfaces;
- design intent and tradeoffs;
- protected regions and constraints;
- simulation setup and validation targets;
- validation state and evidence;
- visual mappings from previews to object and feature IDs;
- allowed operations and modification preconditions;
- assumptions, unknowns, and known limitations.

## Understanding vs. Execution

Understanding should come from the file. A general AI should be able to read the structured resources and distinguish known facts, inferred engineering meaning, user-provided assumptions, unvalidated suggestions, and solver-validated results.

Execution and validation use external deterministic tools. Exact geometry operations, meshing, solving, manufacturing checks, and export remain the responsibility of CAD kernels, CAE preprocessors, meshers, solvers, and manufacturing analysis tools. `.aieng` should describe, reference, configure, and record around those artifacts; it should not become the mesher or solver.

CAD/CAE/mesh/solver files remain execution artifacts produced and consumed by external engineering software. `.aieng` carries semantic context, design intent, constraints, validation state, and structured action proposals with traceable IDs.

The core design split is:

1. `.aieng` carries semantic engineering context.
2. AI/AGI agents inspect, reason, and propose structured changes.
3. Schemas constrain those proposals.
4. External deterministic CAX tools execute geometry/mesh/solver work and produce evidence that `.aieng` can reference or import.


## Software Repository Analogy

Code is comparatively AI-friendly because software repositories expose text, names, modules, tests, dependencies, version history, documentation, and execution feedback. A general AI can inspect a repository and often infer purpose, structure, constraints, and change safety before running the code.

Traditional CAD/CAE files rarely provide equivalent semantic scaffolding. Geometry may be precise, but design intent, feature meaning, validation status, and safe modification rules are often hidden in application state, engineering memory, external reports, or proprietary workflows.

`.aieng` should give engineering models similar scaffolding:

- named objects and stable IDs instead of anonymous geometry only;
- feature graphs instead of opaque topology only;
- design intent and assumptions instead of undocumented rationale;
- constraints and allowed operations instead of implicit tribal knowledge;
- validation status and evidence instead of unsupported safety claims;
- visual mappings instead of screenshots disconnected from geometry;
- patch history and decisions instead of untraceable edits.

The package should therefore behave more like an engineering model repository than a single CAD file.

## Related Work Lesson: text-to-cad

`earthtojake/text-to-cad` is an agent-side CAD authoring runtime. It is a useful reference point because it has converged on two patterns that are also valuable for `.aieng`:

- **Stable references.** `text-to-cad` uses `@cad[path/to/model.step#selector]` handles so agents can quote precise geometry across turns and into CLI commands. `.aieng` already has stable IDs in every structured resource; what is missing is a canonical *string form* over those IDs. See [reference_notation.md](reference_notation.md).
- **Review-oriented agent interaction.** `text-to-cad` separates authoring from review: agents edit source, regenerate explicit targets, validate programmatically, and hand artifacts to a read-only viewer. The separation is healthy; `.aieng` adopts the same posture by keeping structured JSON/YAML resources as source of truth and all summaries/indexes/visuals as derived. See [derived_artifact_discipline.md](derived_artifact_discipline.md).

`.aieng` should adopt stable structured references and review discipline, not CAD authoring workflow. The borrowing test is simple: delete `text-to-cad`'s geometry-generation core and the addressing and review patterns still make sense. The geometry-authoring identity does not survive that test, and importing it would change `.aieng`'s product.

`.aieng` remains the semantic and evidence package. Agent tools, MCP, CLI, and any future viewers are optional windows into the package; none of them is the product.

No solver, no mesher, no arbitrary CAD editing, no manufacturing check, and no text-to-CAD generation happens in `.aieng` core. Future Phase 18 work in this direction is limited to stable references, read-only inspection commands, derived-artifact discipline, and a benchmark refresh focused on AI package understanding.

See [text_to_cad_lessons.md](text_to_cad_lessons.md) for the full summary and `analysis/` for the underlying comparison and risk register.
