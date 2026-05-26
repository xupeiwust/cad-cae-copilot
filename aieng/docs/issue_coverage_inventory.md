# Issue Coverage Inventory

Date: 2026-05-13

## Scope and stated goal

The project goal is to create a CAD/CAE semantic export layer that allows engineering software to convert data into a format more easily understood by LLMs at output time. This enables LLMs to perform tasks such as understanding the engineering model, configuring pre-processing (CAE setup), and proposing model adjustments — before requesting any external CAD/CAE tool execution.

This inventory compares:

1. Planned or missing capabilities in the local roadmap and checkpoint docs.
2. Local issue markdown files under `issues/`.

Checked sources:

- `issues/phase_17a_real_step_stabilization.md`
- `issues/phase_17b_mesh_handoff_completeness.md`
- `issues/phase_18_reference_system.md`
- `issues/phase_18c_semantic_coverage_benchmark.md`
- `issues/phase_18_optional_viewer.md`
- `issues/phase_18_benchmark_refresh.md` (superseded)
- `issues/phase_19_c1_real_feature_recognition_quality.md`
- `issues/phase_19_c2_writeback_breadth_expansion.md`
- `issues/phase_19_c3_allowed_operation_catalog.md`
- `issues/phase_19_c4_consolidated_validation_view.md`
- `issues/boundary_c5_no_arbitrary_brep_editing.md`
- `issues/boundary_c6_no_rendering_gltf_in_core.md`
- `docs/roadmap.md`
- `docs/mvp_checkpoint.md`
- `README.md`
- `docs/rigorous_interop_acceptance_checklist.md`

Note: This is a workspace-local check. It does not query remote GitHub issue state directly.

---

## Maturity assessment against the goal

The core semantic export format is substantially built (Phases 0–16E, Rigorous Interop achieved). A rough maturity breakdown against each LLM task type:

| LLM task type | Status |
|---|---|
| **Model understanding** — feature semantics, topology, design intent, protected regions, constraints | ~80% complete. Geometry extraction is still experimental (OCC backend); feature recognition is rule-based candidates, not kernel-quality. Phase 17A stabilises the real geometry path. |
| **Pre-processing configuration** — CAE setup, boundary conditions, loads, material mapping, mesh handoff | ~75% complete. CAE deck import, mapping, export scaffold, and mesh handoff contract (Phase 17B) are implemented or planned. Mesh generation and solver execution are deliberately external. |
| **Model adjustments** — patch proposals, parameter edits, CAD writeback | ~60% complete. Semantic patch proposals and execution are implemented. Executable CAD writeback (G7) covers `base_plate_candidate` features via CadQuery parametric path. Broader writeback coverage requires either richer parametric models in the package or explicit external CAD tool integration. |
| **Validation and evidence tracking** — recording what external tools produced and what claims it supports | ~90% complete. Evidence ledger, claim map, tool trace, completeness report, and cross-resource validator are all implemented (G1–G12 pass). |
| **AI-facing addressing** — stable handles for citing specific records in chat, MCP, CLI | ~75% complete. Canonical `@aieng[...]` reference form and read-only ref CLI are implemented; remaining work is broader benchmark integration and usage discipline. |
| **Benchmark coverage of LLM understanding** | ~45% complete. Bracket family plus first Phase 18C-min coverage probe scaffold (`plate_with_pattern_001`) with rich/sparse variants and extended category prompts. |

**Summary:** The format foundation is solid. The remaining distance to the stated goal falls into three categories:
- **Near-term (Phase 17):** geometry quality (real STEP stabilisation, mesh handoff).
- **Near-term (Phase 18):** AI-facing references and broader benchmark validation.
- **Medium-term:** broader executable CAD writeback and richer feature recognition on real geometry.

---

## Coverage summary

### A) Covered by local issue docs

1. Phase 17A real STEP stabilization: covered by `issues/phase_17a_real_step_stabilization.md` and GitHub issue #35. Status: closed.
2. Phase 17B mesh handoff completeness: covered by `issues/phase_17b_mesh_handoff_completeness.md` and GitHub issue #36. Status: closed.
3. Phase 18A reference notation and ref CLI: covered by `issues/phase_18_reference_system.md` (implemented and closed).
4. Phase 18C semantic coverage benchmark refresh: covered by `issues/phase_18c_semantic_coverage_benchmark.md` (in-progress).
5. Phase 18B viewer: covered by `issues/phase_18_optional_viewer.md` (deferred by design).
6. Old Phase 18C draft handling: covered by `issues/phase_18_benchmark_refresh.md` (superseded marker).
7. Phase 19 C1-C4 implementation backlog: covered by local issue stubs and GitHub issues #45-#48 (C1/C2/C3/C4 closed).
8. Boundary decisions C5-C6: covered by local boundary records and GitHub issues #49-#50.
9. Phase 19 C4 consolidated validation view: implemented and closed (issue #48).

### B) Roadmap items now normalized into local issue docs

1. **Phase 17A (issue #35):** local doc exists at `issues/phase_17a_real_step_stabilization.md`.
2. **Phase 17B (issue #36):** local doc exists at `issues/phase_17b_mesh_handoff_completeness.md`.

Status: this former gap is now closed.

### C) Capability backlog now tracked by dedicated issue docs

These are grouped by type. The distinction matters: **implementation gaps** are features within `.aieng`'s boundary that are not yet built; **boundary decisions** are permanent non-goals that `.aieng` core will not implement by design.

#### C1 — Implemented: real CAD feature recognition quality uplift (closed)

Feature recognition remains deterministic and candidate-level by design, but now includes explicit real-topology quality signals, uncertainty annotations, and measurable confidence uplift for strong real-topology evidence versus mock baseline.

**Tag:** `implemented-closed`

#### C2 — Implemented: executable CAD writeback breadth expansion (closed)

The executable writeback path has been expanded beyond `base_plate_candidate` to include guarded `flange` and `flange_candidate` regeneration support. Unsupported families continue to fail safely with explicit refusal reasons.

**Note:** Arbitrary STEP/B-rep editing remains permanently out of scope. This item is about *extending the existing guarded parametric path*, not adding arbitrary CAD editing.

**Tag:** `implemented-closed`

#### C3 — Implemented: allowed-operation catalogs (closed)

The package now supports a first-class structured per-feature allowed-operation catalog at `graph/allowed_operations_catalog.json`, including operation admissibility, preconditions, and blocked-by constraints. Validator checks and planner integration are in place.

**Tag:** `implemented-closed`

#### C4 — Implemented: unified validation-state evidence report (closed)

Validation state consolidation is now implemented via `validation/evidence_report.json`, generated from `validation/status.yaml`, `results/claim_map.json`, and `results/evidence_index.json`, with validator consistency checks and CLI/MCP/summary integration.

**Canonical resource name: `validation/evidence_report.json`**

Naming rationale:
- Lives in `validation/`, not `results/`. The `validation/` directory already contains `completeness_report.json` — a consolidated view resource following the `<noun>_report.json` suffix pattern. Consolidated views belong in `validation/`; source-of-truth claim/evidence records belong in `results/`.
- `evidence_report` signals a consolidated view of evidence and claim status, distinguished from `completeness_report` (which covers available/missing/unknown per section).
- Prior drafts used `results/validation_report.json` — this was incorrect on both the directory (derived views should not go in `results/`) and the noun (`validation_report` is already used as a `--kind` value by `aieng record-evidence`, a different namespace).

The three underlying source-of-truth resources remain authoritative. `validation/evidence_report.json` is a derived view only, reproducible from those sources and clearly marked as such.

**Tag:** `implemented-closed`

#### C5 — Boundary decision: arbitrary STEP/B-rep direct editing

`.aieng` does not and will not perform arbitrary STEP/B-rep geometry editing. This is a permanent product boundary, not a deferred implementation item. External CAD tools remain responsible for geometry editing.

**Tag:** `non-goal-v0.1` (permanent boundary)

#### C6 — Boundary decision: visual preview rendering and glTF generation

`.aieng` does not generate rendered previews, screenshots, glTF files, or mesh visualisations. The visual scaffold (annotation layers, model manifest) is metadata-only. Rendering is an external tool responsibility. The optional viewer (Phase 18B, deferred) would visualise structured package state, not render geometry.

**Tag:** `non-goal-v0.1` (permanent boundary)

---

## Suggested backlog normalisation

1. Keep closed-state records for #35 and #36 synchronized between local docs and GitHub.
2. Keep Phase 19 closure records (#45-#48) synchronized between local docs and GitHub.
3. Keep C5-C6 boundary records (#49, #50) explicit so they are not reopened as implementation requests.
4. Cross-link active issue numbers from `docs/roadmap.md` and `docs/mvp_checkpoint.md` to keep roadmap and issue backlog aligned.

---

## Minimal next steps

1. Continue Phase 18C semantic coverage benchmark refresh (expand fixtures and negative-test packages).
2. Keep Phase 18A reference system docs/tests synchronized with CLI and MCP behavior.
3. Keep C5/C6 boundary notes (#49, #50) unchanged unless product scope is explicitly revised.

The Phase 18A and 18C-min work (references, benchmark refresh) is represented by local issue docs; #37 is closed, and 18C remains active.
