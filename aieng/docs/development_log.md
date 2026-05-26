# Development Log

This document records the phase-by-phase development history of `.aieng`. It is preserved for historical reference. For the current project overview, see the [README](../README.md).

---

## Phase Status Summary

**Phases 0–20 complete. Phase 30 benchmark shipped. Phase 35 design-target contract shipped.**

### Implemented

- **Phase 0** — package creation, manifest/schema validation, `aieng init`, and `aieng validate`
- **Phase 1** — STEP import as resource copy via `aieng import-step`
- **Phase 2** — mock topology extraction via `aieng extract-topology`
- **Phase 3** — rule-based feature candidate recognition via `aieng recognize-features`
- **Phase 4** — user engineering context application via `aieng apply-context`
- **Phase 5A** — deterministic AI-readable summary generation via `aieng summarize`
- **Phase 5B** — structured rule-based patch proposal generation via `aieng propose-patch`
- **Phase 5C** — AI understanding benchmark scaffold (`benchmarks/`)
- **Phase 5D** — reference demo walkthrough and scripted integration demo
- **Phase 6A** — CalculiX scaffold deck export via `aieng export-calculix`
- **Phase 6B** — machine-readable validation status file via `aieng update-validation-status`
- **Phase 7A** — geometry backend interface: `GeometryBackend` Protocol, `MockGeometryBackend`, `OCCGeometryBackend` placeholder, `--backend` CLI flag
- **Phase 7A+** — geometry backend contract documentation (`docs/geometry_backend_contract.md`)
- **Phase 7B.1** — optional OCC runtime detection via `detect_occ_runtime()` and `aieng geometry-backends`; `[geometry]` optional extra
- **Phase 7B.2** — experimental OCP/CadQuery-based real STEP topology extraction via `--backend occ` (requires `pip install cadquery`; mock remains default)
- **Phase 7C** — optional OCP topology demo: `scripts/run_ocp_topology_demo.py`, `docs/ocp_topology_demo.md`
- **Phase 8A** — visual index scaffold: `aieng build-visual-index`, `visual/annotation_layers.json`
- **Phase 8B** — visual resource manifest scaffold: `aieng build-visual-manifest`, `visual/model_manifest.json`
- **Phase 9A** — object registry scaffold: `aieng build-object-registry`, `objects/object_registry.json`
- **Phase 9B** — interface graph scaffold: `aieng build-interface-graph`, `objects/interface_graph.json`
- **Phase 10A** — CAE deck import scaffold: `aieng import-cae-deck`
- **Phase 10B** — explicit CAE mapping: `aieng apply-cae-mapping`
- **Phase 10C** — CAE/interface traceability: `cae_refs` enrichment in `objects/interface_graph.json`
- **Phase 4 (CAE result summary)** — `aieng summarize-cae-results` generates `results/result_summary.json`, `results/evidence_index.json`, and `results/postprocessing_summary.md`
- **Phase 5 (solver metadata)** — load case normalization with schema `"0.2"`
- **Phase 6 (precomputed metrics)** — `results/computed_metrics.json` ingestion with schema `"0.3"`
- **Phase 14** — CAE pre-processing summary via `aieng summarize-cae-preprocessing`
- **Phase 15** — CAE simulation run summary via `aieng summarize-cae-runs`
- **Phase 11A** — real STEP topology hardening scaffold (optional face-to-edge and edge-to-face ownership)
- **Phase 11B** — attributed adjacency graph (AAG): `aieng build-aag`
- **Phase 11C** — real STEP demo + benchmark scaffold (`scripts/generate_real_bracket_step.py`, `scripts/run_real_step_demo.py`)
- **Phase 12A** — documentation positioning refinement
- **Phase 13A** — parameterized feature/edit-handle scaffold with `parameter_source`, `editability`, `writeback_strategy`
- **Phase 13B** — semantic patch execution scaffold: `aieng apply-patch`
- **Phase 13C** — updated deck scaffold export: `aieng export-updated-deck`
- **Phase 13B (MCP)** — MCP server: `aieng serve` with 9 agent-callable tools
- **Phase 14A-min** — task specification schema: `aieng write-task-spec`
- **Phase 14B** — external tool handoff contract: `aieng write-external-tool-requirements`
- **Phase 14C** — evidence ledger + claim-evidence map: `aieng write-evidence-scaffold`
- **Phase 14D** — agent handoff benchmark scaffold (`benchmarks/handoff/`)
- **Phase 15A** — evidence writeback CLI: `aieng record-evidence`, `aieng update-claim`
- **Phase 15B** — provenance tool trace: `aieng record-trace`
- **Phase 15C** — cross-resource consistency validator
- **Phase 15D** — enhanced AI summary visibility
- **Phase 16A** — completeness/missingness report: `aieng write-completeness-report`
- **Phase 16B** — CAD/CAE emitter/writeback contract (`docs/cad_cae_emitter_contract.md`)
- **Phase 16C** — AGI handoff worked example (`docs/agi_handoff_walkthrough.md`)
- **Phase 20** — general CAD/CAE conversion contract + FreeCAD reference converter (`aieng convert`)
- **Rigorous Interop milestone** — all 12 gates G1–G12 PASS

### Upcoming

- **Phase 17A** — stabilize real STEP geometry extraction as default entry path
- **Phase 17B** — mesh handoff completeness (`aieng write-mesh-handoff`)

---

## Checkpoint — Phase 30/35 (2026-05-17)

**Benchmark milestone merged.** Phase 30 automated A/B benchmark now has 4 shipped CAE reasoning scenarios. Scenario 4 (setup-correction audit) measured the first correctness divergence between raw-dump Condition A and structured `.aieng` Condition B under Kimi `kimi-for-coding` (n=10, T=0): A 0.450 accuracy vs B 0.950 accuracy. Scenarios 1–3 show comparable correctness with 3.5–7.5× token-efficiency advantage for Condition B. See `benchmarks/llm_engineering_usefulness/README.md` and observation reports in `results/runs/`.

**Phase 35 design-target contract complete through PR 4.**
- PR 1 — schema/docs/examples alignment: dual-format `design_targets.schema.json`, `design_target_comparison.schema.json`, example YAML, and `docs/design_targets.md`.
- PR 2 — structured comparison logic: `design_target_comparisons` block with `pass`/`fail`/`unknown`/`not_evaluated` semantics; no automatic claim advancement.
- PR 3 — CLI surface: `aieng compare-design-targets <package>` with `--output json|text` and `--write-summary`; atomic ZIP writeback; no `claim_map` mutation.
- PR 4 — benchmark Scenario 2 integration: mass-reduction target and safety-factor floor moved into `task/design_targets.yaml`; Condition A receives YAML in raw dump; Condition B references structured resource.
- PR 5 — UI display deferred to future phase.

**Stabilization issues closed:**
- Issue #60 — negation-aware scoring for setup-correction rubric: correctly negated statements (e.g. "not ready for solver", `ready_for_solver: false`) are no longer penalized.
- Issue #59 — OCC/STEP environment gating: tests that only need topology setup now explicitly use `--backend mock`; `tests/_geometry_capability.py` probe added for working OCC STEP backend.

**Full-suite health at checkpoint:** 1582 passed, 15 skipped, 0 failures.

**Deferred work:**
- Design-target UI display (pass/fail/unknown badges) — PR 5.
- True geometry-diff preservation checking for `preserve` targets.
- Objective priority comparison logic remains policy-only (`not_evaluated`).
- Second-model benchmark evaluation.
- LLM-graded rubric for open-ended reasoning.

---

## Current Maturity

| Capability | Status |
|-----------|--------|
| `.aieng` package format and resource pipeline | Implemented |
| JSON schema validation for all structured resources | Implemented |
| Cross-resource ID integrity validation | Implemented |
| Topology extraction | Experimental OCC available (`--backend occ`, requires CadQuery); mock remains default |
| Feature recognition | Rule-based (deterministic heuristics on mock topology) |
| Engineering context | User-provided (YAML supplied by the user) |
| AI summaries and patch proposals | Deterministic rule-based (no LLM, no RAG, no external AI) |
| CAE setup/deck scaffold export | Implemented (scaffold only for external CAE tools; no mesh, no solver run) |
| Validation status record | Implemented (`validation/status.yaml` with claim policy) |
| Optional OCC runtime detection | Implemented |
| Real STEP topology extraction | Experimental (OCP/CadQuery; mock remains default) |
| Visual annotation scaffold | Implemented (annotation metadata only; no rendering) |
| Visual resource manifest scaffold | Implemented (visual resource claims only; no rendering) |
| Object registry scaffold | Implemented (cross-file object index only; not source-of-truth) |
| Interface graph scaffold | Implemented (structured interface index only; not source-of-truth) |
| CAE deck import scaffold | Implemented (parsed materials/BCs/loads + conservative mapping only; no solver run) |
| Explicit CAE mapping | Implemented (user-provided mapping only; no automatic inference) |
| CAE refs in interface graph | Implemented (generated traceability only; no CAE execution) |
| Attributed adjacency graph (AAG) | Implemented (generated face adjacency index; not source-of-truth) |
| Topology adjacency hardening | Implemented scaffold (optional face-edge ownership metadata) |
| Real STEP scripted demo pipeline | Implemented scaffold (optional scripts; requires CadQuery/OCP) |
| Parameterized feature edit handles | Implemented scaffold (guarded parameter metadata) |
| Patch execution | Implemented scaffold (semantic parameter update only by default) |
| Updated CAE deck scaffold export | Implemented scaffold (reflects current setup; no mesh, no solver run) |
| MCP server | Implemented (9 agent-callable tools; claim_policy enforcement) |
| Task specification schema | Implemented scaffold (structured agent task contract) |
| External tool handoff contract | Implemented scaffold (required capabilities, candidate tools, handoff policy) |
| Evidence ledger + claim-evidence map | Implemented scaffold (records external-tool evidence and claim status) |
| Evidence writeback CLI | Implemented scaffold (external tools can write back evidence) |
| Provenance tool trace | Implemented scaffold (audit/provenance only) |
| Solver numeric evidence import | Implemented (deterministic extraction of max von Mises, displacement, reaction force) |
| Mesh evidence import | Implemented (Gmsh v2/v4 node/element counts) |
| CAD writeback (parametric regeneration) | Implemented (CadQuery parametric regeneration for base plate features) |
| Roundtrip invariance | Implemented (source STEP immutable; execution record auditable) |
| Claim decision thresholds | Implemented (every claim has `decision_criteria`) |
| Interop conformance suite | Implemented (CI runs representative fixture tests for all 12 gates) |
| Design-target schema and comparison | Implemented (`task/design_targets.yaml`, `design_target_comparisons` block) |
| Design-target CLI | Implemented (`aieng compare-design-targets`) |
| Automated LLM engineering-usefulness benchmark | Implemented (4 scenarios, 2-axis scoring, `inspect_ai` harness) |
| CAD/CAE interoperability maturity | **Rigorous Interop ACHIEVED** (May 2026) |
| Mesh generation | External CAE responsibility |
| Solver execution/results generation | External CAE responsibility |
| Real CAD geometry modification | External CAD responsibility |
| CAD/CAE heavy dependencies | Not required for default install |

---

## Benchmark Results

### First Benchmark Result

| Input | Honesty / non-hallucination | Engineering usefulness |
|---|---:|---:|
| Raw STEP only | 16 / 16 | 1 / 16 |
| `.aieng` package | 16 / 16 | 16 / 16 |

The raw STEP condition was honest but not actionable. The `.aieng` condition was both honest and actionable.

See [benchmark_runs/bracket_001_manual/results_run_001.md](../benchmark_runs/bracket_001_manual/results_run_001.md).

### Real STEP AI Benchmark Result (Phase 11E)

| Input | Honesty / non-hallucination | Engineering usefulness |
|---|---:|---:|
| Raw STEP only | 18 / 18 | 8 / 18 |
| `.aieng` package | 18 / 18 | 18 / 18 |

Raw STEP maintained strong honesty and partial geometry usefulness, while `.aieng` preserved honesty and improved end-to-end CAX task usefulness.

See [benchmark_runs/real_bracket_001/results_ai_run_001.md](../benchmark_runs/real_bracket_001/results_ai_run_001.md).

---

## Phase Usage Guides

### Phase 1 — STEP import

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng validate build/bracket_001.aieng
```

### Phase 2 / 7A — Topology extraction

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng
aieng validate build/bracket_001.aieng
```

### Phase 3 — Feature recognition

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng
aieng recognize-features build/bracket_001.aieng
aieng validate build/bracket_001.aieng
```

### Phase 3.5 — CAE artifact detection

```bash
aieng detect-cae-artifacts build/bracket_001.aieng
aieng detect-cae-artifacts build/bracket_001.aieng --json
```

### Phase 4 — Engineering context

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng
aieng recognize-features build/bracket_001.aieng
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml
aieng validate build/bracket_001.aieng
```

### Phase 5A — AI-readable summary

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng
aieng recognize-features build/bracket_001.aieng
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml
aieng summarize build/bracket_001.aieng
aieng validate build/bracket_001.aieng
```

### Phase 5B — Patch proposal

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng
aieng recognize-features build/bracket_001.aieng
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml
aieng summarize build/bracket_001.aieng
aieng propose-patch build/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng validate build/bracket_001.aieng
```

### Phase 6A — CalculiX scaffold deck export

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng --overwrite
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng summarize build/bracket_001.aieng --overwrite
aieng propose-patch build/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng export-calculix build/bracket_001.aieng --out build/solver_deck.inp --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 6B — Validation status

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng --overwrite
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng summarize build/bracket_001.aieng --overwrite
aieng propose-patch build/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng export-calculix build/bracket_001.aieng --out build/solver_deck.inp --overwrite
aieng update-validation-status build/bracket_001.aieng
aieng validate build/bracket_001.aieng
```

### Phase 7B.1 — Geometry backend detection

```bash
aieng geometry-backends
```

### Phase 7B.2 — Experimental OCP extraction

```bash
aieng geometry-backends
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --backend occ
aieng validate build/bracket_001.aieng
```

Requires `pip install cadquery`.

### Phase 8A — Visual index scaffold

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng build-visual-index build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 8B — Visual resource manifest

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng build-visual-index build/bracket_001.aieng --overwrite
aieng build-visual-manifest build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 9A — Object registry

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng propose-patch build/bracket_001.aieng --intent "Reduce mass by 15% while keeping mounting holes unchanged."
aieng build-visual-index build/bracket_001.aieng --overwrite
aieng build-visual-manifest build/bracket_001.aieng --overwrite
aieng build-object-registry build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 9B — Interface graph

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng build-visual-index build/bracket_001.aieng --overwrite
aieng build-interface-graph build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 10A — CAE deck import

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng apply-context build/bracket_001.aieng --context examples/bracket_user_context.yaml --overwrite
aieng import-cae-deck build/bracket_001.aieng --deck examples/bracket_loadcase.inp --format calculix
aieng validate build/bracket_001.aieng
```

### Phase 10B — Explicit CAE mapping

```bash
aieng build-interface-graph build/bracket_001.aieng --overwrite
aieng import-cae-deck build/bracket_001.aieng --deck examples/bracket_loadcase.inp --format calculix --overwrite
aieng apply-cae-mapping build/bracket_001.aieng --mapping examples/bracket_cae_mapping.yaml --overwrite
aieng build-interface-graph build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 11B — AAG build

```bash
aieng import-step examples/bracket.step --out build/bracket_001.aieng
aieng extract-topology build/bracket_001.aieng --overwrite
aieng build-aag build/bracket_001.aieng --overwrite
aieng recognize-features build/bracket_001.aieng --overwrite
aieng validate build/bracket_001.aieng
```

### Phase 11C — Real STEP demo

```bash
python scripts/generate_real_bracket_step.py --overwrite
python scripts/run_real_step_demo.py
python scripts/prepare_real_benchmark_pack.py
```

Requires CadQuery/OCP.

### Phase 13A — Parameterized feature scaffold

Phase 13A extends `graph/feature_graph.json` with guarded edit metadata:
- `parameter_source` — where parameters came from (`mock`, `ocp_extracted`, `user_provided`, `agent_defined`, future `cadquery_parametric`)
- `editability` — semantic-only vs executable regeneration
- `writeback_strategy` — parameter update, no write-back, or regeneration path

### Phase 13B — Semantic patch execution

```bash
aieng apply-patch build/bracket_001.aieng --patch patch_0001
```

Applies `modify_parameter` operations to structured feature parameters. Does not perform arbitrary STEP/B-rep editing.

### Phase 13C — Updated deck export

```bash
aieng export-updated-deck build/bracket_001.aieng
```

Writes `simulation/updated_deck.inp` reflecting current `simulation/setup.yaml`. Scaffold only.

### Phase 7C — OCP topology demo

```bash
python scripts/run_ocp_topology_demo.py path/to/model.step
```

See [docs/ocp_topology_demo.md](ocp_topology_demo.md) for full instructions.

---

## Checkpoint — MCP design-target inspection (2026-05-17)

**Repo:** `aieng-freecad-mcp`
**Commit:** `1118944`

### Tools added

- `aieng_read_design_targets` — read-only MCP tool that inspects `task/design_targets.yaml` inside an `.aieng` package
- `aieng_read_design_target_comparisons` — read-only MCP tool that inspects `results/result_summary.json#design_target_comparisons`

### Capabilities

- Reads from both zipped `.aieng` and directory-form packages
- Returns graceful missing-resource states (does not crash when files are absent)
- Supports legacy and modern design target field styles
- Does not mutate the package, CAD, or `claim_map.json`
- Does not call solver or FreeCAD operations
- Safe for agent preflight and evidence inspection

### Boundary rules

- Read-only: no package writeback, no claim advancement
- Artifact-threshold checks only: pass/fail comparisons are not engineering certification
- Agents should inspect design targets before proposing CAD/CAE changes

### Tests

- Targeted tests: 36 passed
- Full MCP suite: passed, 23 skipped (FreeCAD/solver environment-gated)

### Deferred

- Design-target-aware mutation gating (use target context to advise/reject CAD proposals)
- True geometry-diff preservation checking
- Objective-priority resolution logic

---

## Global Import Policy

All external import pathways default to evidence/artifact ingestion only. Importing data into `.aieng` does not, by itself, advance engineering claims.

Import layers are intentionally separated:

1. **Artifact presence**: an imported external file or generated package resource is present and referenced.
2. **Parsed facts**: deterministic parsed observations or extracted fields may be recorded as structured facts.
3. **Claim linkage**: evidence may point at tracked claim IDs so the package can show what the artifact could support.
4. **Explicit claim status update**: claim status changes in `results/claim_map.json` only when an explicit action such as `aieng update-claim` is taken with traceable evidence IDs.

This policy applies across import commands such as `aieng import-step`, `aieng import-cae-deck`, `aieng import-solver-evidence`, and `aieng import-mesh-evidence`.

---

## Core Principle

> The file should carry enough engineering semantics that a general AI can understand the model before calling any tools.

`.aieng` should behave more like an engineering model repository than a single CAD file. Structured JSON/YAML resources are the source of truth; prose summaries help AI consumption but must not replace stable IDs, geometry references, constraints, validation records, or allowed operations.
