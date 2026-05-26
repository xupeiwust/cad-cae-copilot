# Derived Artifact Discipline

This note codifies what counts as source of truth in a `.aieng` package, what counts as a derived artifact, and the rules that protect the boundary between them. It is a written rule for what `.aieng` already does in practice, plus the planned posture for future derived artifacts.

## Source of truth

Structured JSON/YAML resources are source of truth.

These include (non-exhaustive):

- `manifest.json`
- `geometry/topology_map.json`
- `graph/feature_graph.json`, `graph/constraints.json`
- `objects/interface_graph.json`
- `ai/protected_regions.json`, `ai/patches/*.json`
- `simulation/setup.yaml`, `simulation/cae_imports/*`, `simulation/cae_mapping.json`
- claim proposals (review artifacts requiring human review), `results/evidence_index.json`
- `provenance/tool_trace.json`
- `validation/status.yaml`, `validation/completeness_report.json`
- `task/task_spec.yaml`, `task/external_tool_requirements.json`

These resources are written by explicit, named CLI verbs from explicit inputs (a STEP file, a user context YAML, a deck, a mapping file, an evidence record, a trace entry). They are authoritative within the package.

## Derived artifacts

The following are derived from source-of-truth resources and **must not** be treated as authoritative engineering state on their own:

- **Markdown summaries** — `README_FOR_AI.md`, `ai/summary.md`. These are orientation aids for general AI readability. They are written from the structured resources; they do not extend or override those resources.
- **Generated topology and graph indexes** — `graph/aag.json`, `objects/object_registry.json`, parts of `objects/interface_graph.json` that are pure index views, the visual annotation layers in `visual/annotation_layers.json`, the visual manifest in `visual/model_manifest.json`.
- **Benchmark outputs** — `benchmarks/handoff/*` results, `benchmark_runs/<family>_<NNN>/results_*.md`.
- **Future visual snapshots** — if any rendering helper is ever introduced behind an optional extra, the PNG/PDF/SVG output is a derived artifact only.

A derived artifact carries either a provenance marker (`extraction_mode`, `runtime_provider`, `parameter_source`, `generated_index: true`, `not_source_of_truth: true`) or is unambiguously identifiable as derived by its file type and location (Markdown summaries, snapshot files).

## Rules

1. **Structured JSON/YAML resources are source of truth.** Any conflict between a structured resource and a derived artifact is resolved in favour of the structured resource.

2. **Markdown summaries are derived orientation aids only.** They must not be quoted as the authoritative value for any feature, claim, evidence, or completeness item. AI readers and tools should consult the underlying JSON/YAML for any decision.

3. **Generated topology, AAG, object registry, interface graph, visual index, summaries, benchmark outputs, and future snapshots are derived artifacts.** They are reproducible from declared source resources.

4. **Derived artifacts must declare or preserve provenance where applicable.** Examples:
   - `geometry/topology_map.json` records `extraction_mode` and `runtime_provider`.
   - `graph/feature_graph.json` records `parameter_source`, `editability`, and `writeback_strategy` per feature.
   - `graph/aag.json` records `generated_index: true`.
   - `objects/object_registry.json` and `objects/interface_graph.json` are marked as generated indexes; their source-of-truth fields point back to the originating structured resources.
   - Future visual snapshots carry a sidecar declaring producer kind and `not_validation_evidence: true`.

5. **Derived artifacts must not silently become engineering truth.** When a derived artifact disagrees with its source resource, the validator and any consumer must treat the source as authoritative and flag the divergence.

6. **Visual snapshots must never be accepted as solver, mesh, CAD, manufacturing, or validation evidence.** Even if a future rendering helper is introduced, snapshot artifacts:
   - are stored outside `results/`,
   - carry a `not_validation_evidence: true` sidecar,
   - are rejected by `results/evidence_index.json` at the schema level (planned guard),
   - are rejected by `aieng record-evidence` at the writeback layer (planned guard).

7. **No claim may be advanced without explicit evidence.** Every claim's `decision_criteria` carries `auto_advance: false`, `pass_requires`, and `unsupported_if`. A claim status only advances when an explicit, schema-validated evidence record is attached. This rule is independent of which derived artifacts exist around the claim.

8. **Default install must remain lightweight and local-first.** `pip install aieng` provides a working `aieng validate` with no network access, no heavy CAD dependencies, no GUI toolchain. Optional capabilities (geometry parsing, MCP server, future viewer) live behind extras and never enter the default install.

9. **Avoid broad "regenerate everything" commands.** The CLI is granular: each verb writes one structured resource (with at most an index update). There is no `aieng regenerate-all`. Granularity preserves the explicit dependency between each source input and each derived output and prevents derived artifacts from drifting silently when something upstream changes.

10. **Any generated artifact should be reproducible from declared source resources or clearly marked as externally produced evidence.** The two admissible origins for any artifact inside an `.aieng` package are:
    - **derived** — reproducible by running named CLI verbs against the package's source-of-truth resources;
    - **externally produced evidence** — written by `aieng record-evidence` / `aieng record-trace` from external CAD/CAE/mesher/solver tools, identified by `producer_kind`, `producer_tool`, `producer_version`, and `exit_status`.
    A third category does not exist. Anything that fits neither must be removed or correctly relabelled.

## Why this matters

A `.aieng` package is intended to be readable by a general AI that has no access to the producing CAD/CAE tools. If derived artifacts could overwrite source resources, or if visual snapshots could pass as evidence, the package would silently mislead the AI. The discipline above is what keeps the package honest under inspection.

## Related documents

- [Core position](core_position.md)
- [Reference notation](reference_notation.md)
- [Lessons from text-to-cad](text_to_cad_lessons.md)
- [CAD/CAE emitter and writeback contract](cad_cae_emitter_contract.md)
- [Rigorous interop acceptance checklist](rigorous_interop_acceptance_checklist.md) (G5 cross-resource validator; G9 claim decision thresholds)
