# Changelog

All notable changes to the `.aieng` format and tooling are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Schema versioning follows the policy in `docs/roadmap.md` (Issue #17).

---

## Schema versioning policy

All JSON Schema files carry `format_version: "0.1.0"`. This version is **not** semver — it is a package-level format epoch.

**What triggers a version bump:**
- Removing a previously required field
- Changing a `const` value
- Renaming a field that existing packages reference by name
- Changing an `enum` to remove a previously valid value

**What does NOT trigger a version bump:**
- Adding optional fields (additive and backward-compatible)
- Adding new `enum` values
- Adding new validator checks that only WARN (not FAIL) on existing valid packages
- New resources added to the package format (they are absent from older packages, which remain valid)

**Experimental resources** (any resource with `scaffold` in its roadmap status) may change shape before stabilizing. Treat them as `0.x` within the epoch.

---

## [Unreleased]

### Added — Phase 21C: per-run directory structure for first recorded run (2026-05-13)

Clean structure for capturing one complete manually-executed benchmark run once
answers are available. No answers fabricated; no API calls made; no performance
claims implied.

- `benchmarks/ai_usefulness/results/runs/README.md` — workflow explanation: copy
  template directory, paste raw answers, score independently, fill result.json,
  write observation report, commit. Explicit one-scenario limitation warning.
- `benchmarks/ai_usefulness/results/runs/run_TEMPLATE/condition_a_answers.md` —
  answer template with metadata table (model, temperature, system prompt) and
  per-question sections (Q1–Q5 verbatim text, raw AI response FILL_IN slots).
  Prominently marked TEMPLATE. Paste-verbatim instruction prevents editorial cleanup.
- `benchmarks/ai_usefulness/results/runs/run_TEMPLATE/condition_b_answers.md` —
  same structure as condition_a_answers.md for the Condition B session.
- `benchmarks/ai_usefulness/results/runs/run_TEMPLATE/scoring_notes.md` — per-
  question and per-dimension scoring template: evidence cited, score awarded (0/1/2),
  rationale field; hallucination instance table; delta summary table. Score Condition A
  before Condition B instruction explicit.
- `benchmarks/ai_usefulness/results/runs/run_TEMPLATE/result.json` — schema-valid
  sentinel JSON (run_id `run_00000000T000000Z`, all scores zero, model/provider/
  evaluator FILL_IN). Template warnings include: unfilled marker, replace all FILL_IN
  values, single-scenario limitation. Validates against `results.schema.json`.
- `benchmarks/ai_usefulness/results/runs/run_TEMPLATE/observation_report.md` —
  narrative template: summary, what Condition A got right, what Condition B improved,
  key delta drivers, unexpected behaviors, failure modes, run limitations. Contains
  one-scenario limitation section with mandatory FILL_IN.
- `benchmarks/ai_usefulness/HOWTO_RUN.md` — Step 7 expanded to a 7-part sub-step
  covering the full runs/ directory workflow (copy, paste answers, scoring, result.json,
  validation, observation report, commit). Run directory layout diagram added.
- `benchmarks/ai_usefulness/results/README.md` — Phase 21C section added with per-run
  directory structure diagram and link to `runs/README.md`.
- `tests/test_phase21c.py` — 40 tests: directory/file existence; FILL_IN placeholders
  in all markdown templates; template result.json schema validation; sentinel run_id and
  scores; template warnings (including single-scenario); Q1–Q5 sections in answer
  templates; metadata sections; scoring notes dimension/hallucination/delta sections;
  observation report limitation/condition/generalization sections; runs/README workflow
  and file inventory; HOWTO_RUN.md updated references.

**No fabricated answers. No API calls. No performance claims.**
The template directory explicitly prevents accidental use as a real result (all-zero
sentinel scores, FILL_IN markers, mandatory template warnings in result.json).

- 1232 tests pass (40 new), 17 skipped, 0 failures.

### Added — Phase 21B: first run-record structure and execution protocol (2026-05-13)

Run-record structure and manual execution protocol for the first Phase 21 benchmark run.

- `benchmarks/ai_usefulness/HOWTO_RUN.md` — step-by-step manual execution protocol
  covering: prerequisites; recording model/version/temperature/system-prompt metadata;
  Condition A and Condition B input preparation; cross-condition leakage prevention
  (separate fresh sessions, no cross-contamination, Condition A first); verbatim question
  delivery; independent per-condition scoring; result recording and schema validation;
  interpretation guidance. Explicit "one-scenario limitation" section: one run on the
  sample bracket is one data point and does not support broad claims about `.aieng`
  utility across models, scenario types, or evaluators.
- `benchmarks/ai_usefulness/results/run_record_template.json` — schema-valid JSON
  template with sentinel placeholder values (`run_id: "run_00000000T000000Z"`,
  `model/provider/evaluator: "FILL_IN"`, all scores zero). Validates against
  `results.schema.json`. Has explicit `warnings` array stating it is an unfilled
  template. Copy, rename to `run_YYYYMMDDTHHMMSSZ.json`, and replace all placeholders
  before treating as a result.
- `benchmarks/ai_usefulness/results/README.md` — updated with Phase 21B instructions:
  template usage, file naming convention, validation command, single-scenario limitation
  warning.
- `benchmarks/ai_usefulness/README.md` — "Phase 21B — Recording the first run" section
  added with quick 4-step summary and link to `HOWTO_RUN.md`.
- `tests/test_phase21b.py` — 32 tests: HOWTO_RUN.md existence and key content (leakage
  prevention, fresh sessions, same model, temperature, verbatim questions, single-scenario
  limitation, schema validation, system prompt, evaluator); run_record_template.json
  schema conformance (sentinel run_id, FILL_IN markers, template warnings, excluded
  capabilities, scenario paths, all 8 dimensions); results README updated; benchmark
  README links HOWTO.

**No new code executes solvers, meshers, agents, CAD edits, or live AI APIs.**
Result template deliberately uses all-zero sentinel scores — no fabricated results.
The HOWTO explicitly states one run on one scenario is not sufficient for broad claims.

- 1192 tests pass (32 new), 17 skipped, 0 failures.

### Added — Phase 21A: sample bracket CAD understanding scenario (2026-05-13)

First complete, executable benchmark scenario under `benchmarks/ai_usefulness/scenarios/`.

- `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/README.md` —
  scenario overview: fixture description (4 objects: Plate 100×50×10mm,
  MountingHole_1/2 D=6mm, Flange_Top 40×20mm), what Condition B exposes vs. A,
  manual run instructions.
- `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_a.md` —
  raw Document.xml text extracted from `examples/sample_bracket.FCStd`; full
  FreeCAD XML with object types, properties, and values — the realistic Condition A
  baseline (no explicit coverage categories, no stable IDs).
- `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/condition_b_index.md` —
  lists required `.aieng` package resources (README_FOR_AI.md, manifest.json,
  conversion_manifest.json, completeness_report.json, feature_graph.json,
  object_registry.json); extraction commands; evaluator reference table for what
  the AI should cite in Condition B.
- `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/questions.md` —
  5 questions for Track A: Q1 feature inventory, Q2 mounting holes with evidence,
  Q3 geometry availability, Q4 explicit missingness, Q5 FEM preprocessing readiness;
  excluded capabilities list.
- `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/expected_scoring.md` —
  per-dimension expected score ranges; ground truth table (what is and isn't
  available in each condition); scoring calibration notes; illustrative totals:
  Condition A = 2, Condition B = 9, delta = +7.
- `benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding/example_result.json` —
  schema-valid illustrative result (clearly marked "NOT A REAL RUN"); conforms to
  `benchmarks/ai_usefulness/results.schema.json`; demonstrates full field set.
- `scripts/validate_benchmark_scenario.py` — lightweight CLI validator (no AI API
  calls): checks all 6 required files exist; validates `example_result.json`
  against `results.schema.json` (via jsonschema or manual fallback); checks
  `questions.md`, `condition_a.md`, `condition_b_index.md` content; optionally
  validates `condition_b.aieng` coverage_categories (all 15) and runs the aieng
  package validator; optional `--generate-package SOURCE` flag.
- `benchmarks/ai_usefulness/README.md` — "Running a benchmark scenario manually"
  section added with 6-step instructions (validate → generate package → Condition A
  session → Condition B session → score → compute delta); "Scenarios" index table.
- `tests/test_phase21a_scenario.py` — 35 tests: directory and 6 required files
  exist; `example_result.json` schema-valid and well-formed (run_id format,
  benchmark_scenario, track, required dimensions, hallucination_penalty consistent
  with count, Condition B > Condition A); `questions.md` has all 5 questions and
  all excluded capabilities; `condition_a.md` is substantial and names model
  objects; `condition_b_index.md` has backtick resources and key filenames;
  `expected_scoring.md` covers all 4 key dimensions; benchmark README mentions
  scenarios.

**Boundary reaffirmed:** no new code runs solvers, meshers, agents, or CAD edits.

- 1160 tests pass (34 new), 17 skipped, 0 failures.

### Added — Phase 20 closeout + Phase 21 AI usefulness benchmark scaffold (2026-05-13)

**Phase 20 closeout — end-to-end FreeCAD conversion smoke path and quality gates**

- `tests/test_conversion_manifest_quality.py` (19 new tests): end-to-end offline smoke
  path using `examples/sample_bracket.FCStd`; asserts all 15 adaptive coverage
  categories present; validates every status value against the 7-value enum; verifies
  explicit missingness/unsupported/inferred recording (no silent omissions); confirms
  complete categories list emitted resources; verifies legacy L-level fields pass schema
  as optional; confirms readiness `information_state` reads `coverage_categories` as
  primary source (topology→missing, object_registry→available, writeback_metadata→unsupported);
  zero FAILs on validator; source FCStd preserved verbatim.
- `README.md` — "What `.aieng` is (and is not)" section added near the top with a
  two-column boundary table; positioning statement visible without scrolling.
- `docs/cad_cae_conversion_contract.md` — coverage category table and status value
  table added; manifest description calls `coverage_categories` the primary interface
  (incremented in the previous increment, finalized here).

**Phase 21 — AI usefulness benchmark scaffold**

- `benchmarks/ai_usefulness/README.md` — benchmark overview: central question
  (with vs. without `.aieng`), two-condition design, four tracks, scoring summary,
  non-goals.
- `benchmarks/ai_usefulness/questions.md` — full question sets for all four tracks:
  A (CAD understanding, 6 questions), B (CAD reconstruction, 5 questions),
  C (FEM preprocessing, 6 questions), D (CAE deck understanding, 6 questions).
  All questions asked in both conditions.
- `benchmarks/ai_usefulness/scoring_rubric.md` — seven scoring dimensions with
  0/1/2 criteria: `geometry_understanding_score`, `feature_identification_score`,
  `referenceability_score`, `missingness_honesty_score`,
  `preprocessing_readiness_score` (Track C), `hallucination_penalty` (−1/instance),
  `task_success_score` (0/1). Max scores: 9 (tracks A/B/D), 11 (track C).
- `benchmarks/ai_usefulness/expected_observations.md` — canonical expected behaviors
  for well-performing AI in each condition and track; general and per-track red flags.
- `benchmarks/ai_usefulness/input_index.md` — preparation instructions for both
  conditions; FCStd extraction commands; which package resources to include per track.
- `benchmarks/ai_usefulness/result_template.md` — structured per-run form with
  two-condition score tables, hallucination instance log, per-question notes, delta
  summary.
- `benchmarks/ai_usefulness/results.schema.json` — JSON schema for machine-readable
  results; `benchmark_scenario: "ai_usefulness_v1"`; `DimensionScores` def with
  all seven dimensions; `track` enum; separate `condition_a_scores`/`condition_b_scores`.
- `benchmarks/ai_usefulness/results/README.md` — placeholder noting no runs yet.

**Boundary reaffirmed across all new artifacts:**
No new code executes solvers, meshers, optimization loops, autonomous agents, or CAD
edits. The benchmark specifically measures AI understanding improvement, not
`.aieng` automation capability.

- 1126 tests pass (19 new), 17 skipped, 0 failures.

### Added — Phase 20 (increment 2): Adaptive conversion manifest + benchmark design groundwork (2026-05-13)

This increment refactors the Phase 20 conversion manifest away from rigid L0–L5 levels
as the primary interface and toward an adaptive, per-category coverage record.

- `schemas/conversion_manifest.schema.json` — `coverage_categories` added as a **required**
  primary field. Each entry carries `category` (15-value enum), `status` (7-value enum:
  `complete`, `partial`, `inferred`, `missing`, `unsupported`, `unavailable_in_source`,
  `unknown`), and optional `resources_emitted`, `missing_items`, `inferred_items`, `notes`.
  `declared_capability_levels` / `achieved_capability_levels` are demoted to optional
  shorthand; they are still written by the FreeCAD converter for backward compatibility.
- `src/aieng/converters/base.py` — new `CoverageCategory` dataclass with `to_dict()`;
  added to `ConversionResult` as `coverage_categories: list[CoverageCategory]` (default
  empty list for converters that have not been updated yet).
- `src/aieng/converters/freecad.py` — `_build_coverage_categories()` populates all 15
  categories for offline FCStd conversion with accurate status values reflecting what the
  reference converter can and cannot extract.
- `src/aieng/converters/writer.py` — `coverage_categories` serialised into the manifest
  alongside the existing level shorthand.
- `src/aieng/converters/readiness.py` — `_converter_section()` now exposes
  `coverage_categories`; `_information_state_section()` reads from `coverage_categories`
  as primary source (status-mapped to info-state buckets) and supplements with completeness
  report categories for any not already covered.
- `src/aieng/validate.py` — PASS message emitted for `coverage_categories` presence;
  level subset check remains conditional on both optional fields being present.
- `docs/cad_cae_conversion_contract.md` — coverage categories and status values documented;
  manifest description updated to call `coverage_categories` the primary interface.
- `docs/benchmark_design.md` — new benchmark design groundwork document: four tracks
  (CAD understanding, reconstruction assistance, FEM preprocessing, CAE deck
  understanding), seven scoring dimensions, scoring notes, input requirements, non-goals.
- Tests: `test_conversion_manifest_schema_validates_minimal_payload` updated to use the
  new required `coverage_categories` field; `test_conversion_manifest_schema_validates_optional_levels_shorthand`
  added; coverage assertions added in `test_freecad_converter.py` and `test_readiness_demo.py`.
- 1107 tests pass (1 new), 17 skipped, 0 failures.

### Added — Phase 20: General CAD/CAE conversion contract + FreeCAD reference converter (2026-05-13)

This phase formalises `.aieng` as a CAD/CAE-to-AI semantic *conversion* layer.
The boundary is explicit: converters read, structure, and record. They do not
execute solvers, meshers, optimizers, or CAD edits.

- `docs/cad_cae_conversion_contract.md` — general contract document defining
  capability levels L0–L5 (source metadata, geometry/topology, object registry,
  feature-aware, editability metadata, roundtrip writeback metadata) and the
  non-negotiable converter boundary.
- `schemas/converter_capabilities.schema.json` — static, source-agnostic
  capability profile for a converter implementation.
- `schemas/conversion_manifest.schema.json` — per-package conversion record
  written to `provenance/conversion_manifest.json` with declared/achieved
  capability levels, source metadata + sha256, emitted resources, unsupported
  items, uncertainty notes, and converter claim policy guards.
- `schemas/manifest.schema.json` — `source_mode` enum extended with
  `"converter"` (alongside existing `"step"`, `"definition"`).
- `schemas/completeness_report.schema.json` — category enum extended with
  `source_conversion`.
- `schemas/feature_graph.schema.json` — `parameter_source` enum extended with
  `converter_extracted`.
- `src/aieng/converters/` — converter framework: `base.py` (protocol, profile,
  result, claim policy), `registry.py` (registration), `writer.py` (writes the
  package, manifest, conversion manifest, capabilities snapshot, and refreshes
  the completeness report), `readiness.py` (derives a structured readiness
  report from an existing converter-produced package), and `freecad.py` (the
  FreeCAD reference converter — offline FCStd zip parsing with optional
  FreeCAD runtime detection; never runs solvers, meshers, optimizers, or CAD
  edits).
- CLI: `aieng convert <source> --out <package.aieng>`,
  `aieng converter-capabilities`, `aieng readiness-report <package.aieng>`.
- Validator additions: schema lookup for both new resources; semantic check
  that achieved levels are a subset of declared levels; semantic check that
  `source_mode=converter` requires `provenance/conversion_manifest.json`;
  WARN (not FAIL) for missing topology in converter-sourced packages;
  cross-resource consistency between converter source_system values.
- `validation/completeness_writer.py` — new `source_conversion` completeness
  category derived from the embedded conversion manifest; gracefully reports
  `not_applicable` for non-converter packages.
- `scripts/generate_sample_fcstd.py` + `examples/sample_bracket.FCStd` —
  synthetic FCStd fixture for tests/demos (no FreeCAD installation required).
- Tests: `tests/test_conversion_contract.py`,
  `tests/test_freecad_converter.py`, `tests/test_readiness_demo.py` (16 new
  tests). Existing test suite (1106 tests) continues to pass.

Non-goals reaffirmed: no universal CAD emitter, no GUI/viewer, no agent
runtime, no autonomous CAE workflow, no calls to Gmsh/CalculiX/optimizers,
no automatic CAD edits.

### Added — Phase 19 C1/C2 + G10 conformance increments (2026-05-13)
- `src/aieng/ai/summary_writer.py`: added "Feature recognition quality" sections in both `README_FOR_AI.md` and `ai/summary.md`, including confidence distribution, uncertainty-note coverage, and recognition-method counts.
- `src/aieng/patch/executor.py`: expanded guarded CadQuery regeneration writeback support beyond base plate to include flange feature families (`flange`, `flange_candidate`) under existing regeneration safety gates.
- `tests/test_summary.py`: added assertions for recognition-quality summary visibility.
- `tests/test_patch_executor.py`: added flange-family CadQuery writeback coverage test.
- `tests/test_adapter_tool_trace_conformance.py`: expanded adapter tool-trace conformance coverage for cross-resource integrity (`artifacts_recorded` and `claims_advanced`) plus CLI-path metadata conformance checks.

### Added — Phase 17A/17B implementation progress (2026-05-13)
- CLI: `aieng extract-topology` now defaults to `--backend auto` with runtime-based `occ` (OCP) preference and `mock` fallback.
- CLI: new `aieng write-mesh-handoff` command writes `simulation/mesh_handoff_contract.json` and updates manifest resource mapping.
- Schema: added `schemas/mesh_handoff_contract.schema.json` with explicit execution-boundary const guards (`external_tools_execute=true`, `aieng_core_executes_mesher=false`).
- Validator: added mesh handoff schema + semantic checks (geometry source existence, topology face/edge reference validity, target-claim ID presence checks).
- Completeness: added `real_geometry_extraction` and `mesh_handoff_contract` category to `validation/completeness_report.json` generation/schema.
- Tests:
	- OCC auto-backend selection tests,
	- guarded real STEP OCC extraction -> completeness integration check,
	- guarded real bracket OCC feature-recognition candidate-type check,
	- mesh handoff claim-ID mapping checks,
	- mesh handoff round-trip compatibility test (`write-mesh-handoff` -> `import-mesh-evidence` -> `summarize` -> `validate`).

### Added — Phase 15D (2026-05-12)
- `ai/summary_writer.py`: evidence index breakdown by `evidence_type`, `producer.kind`, and verification status; claim map counts by `verification_status` with explicit unsupported/fail ID lists; tool trace exit status breakdown and failure WARNING
- 14 new tests in `tests/test_summary.py`

### Added — Phase 15C (2026-05-12)
- `validate.py`: `_validate_cross_resource_consistency()` — six inter-resource consistency checks across all Phase 14/15 ledgers (solver_execution vs claims, forbidden_core_actions vs evidence, tool_trace.claims_advanced vs claim_map, dangling artifact paths)
- `mcp/server.py`: `tool_get_tool_trace` + `get_tool_trace` registered in `create_server()`
- 17 new tests in `tests/test_cross_resource_consistency.py`, 3 new MCP tests in `tests/test_tool_trace.py`

### Added — Phase 15B (2026-05-11, contributor)
- `schemas/tool_trace.schema.json`: strict schema for `provenance/tool_trace.json`; `const` guards enforce execution boundary
- `src/aieng/provenance/tool_trace_writer.py`: `record_trace_package()` — append-only audit log of external tool steps
- CLI: `aieng record-trace`
- Validator, MCP `get_tool_trace`, summary section, 43 tests

### Added — Phase 15A (2026-05-11, contributor)
- `src/aieng/results/evidence_writer.py`: `record_evidence_package()`, `update_claim_package()` — evidence writeback guards; `aieng_core` blocked from producing solver/mesh/geometry evidence
- CLI: `aieng record-evidence`, `aieng update-claim`

### Added — Phase 14D (2026-05-10)
- `benchmarks/handoff/`: questions (10 groups A–J), scoring rubric (8 categories, 0/1/2, max 16), expected observations, input index, result template, `results.schema.json`
- 42 tests in `tests/test_handoff_benchmark.py`

### Added — Phase 14C (2026-05-10)
- `schemas/evidence_index.schema.json`, `schemas/claim_map.schema.json`
- `src/aieng/results/evidence_writer.py`: `write_evidence_scaffold_package()`
- CLI: `aieng write-evidence-scaffold`
- Validator checks, MCP `get_evidence_index` + `get_claim_map`, summary sections

### Added — Phase 14B (2026-05-10)
- `schemas/external_tool_requirements.schema.json`
- `src/aieng/task/external_tool_requirements_writer.py`
- CLI: `aieng write-external-tool-requirements`
- Validator checks, MCP `get_external_tool_requirements`, summary section

### Added — Phase 14A-min (2026-05-10)
- `schemas/task_spec.schema.json`
- `src/aieng/task/task_spec_writer.py`
- CLI: `aieng write-task-spec`
- Validator checks, MCP `get_task_spec`, summary section

### Added — Phases 0–13C, 13B (MCP)
See `docs/mvp_checkpoint.md` for the full phase history prior to Phase 14.

---

## Stable vs. experimental

| Resource | Status |
|----------|--------|
| `manifest.json` | Stable |
| `geometry/topology_map.json` | Stable (mock backend) / Experimental (OCC backend) |
| `graph/feature_graph.json` | Stable |
| `graph/aag.json` | Stable scaffold |
| `graph/constraints.json` | Stable |
| `simulation/setup.yaml` | Stable |
| `simulation/solver_deck.inp` | Stable scaffold |
| `simulation/updated_deck.inp` | Stable scaffold |
| `simulation/cae_imports/*` | Stable scaffold |
| `simulation/cae_mapping.json` | Stable scaffold |
| `ai/protected_regions.json` | Stable |
| `ai/patches/patch_NNNN.json` | Stable scaffold |
| `ai/summary.md` | Stable (generated, not source-of-truth) |
| `README_FOR_AI.md` | Stable (generated, not source-of-truth) |
| `validation/status.yaml` | Stable |
| `visual/annotation_layers.json` | Stable scaffold |
| `visual/model_manifest.json` | Stable scaffold |
| `objects/object_registry.json` | Stable scaffold |
| `objects/interface_graph.json` | Stable scaffold |
| `task/task_spec.yaml` | Stable scaffold |
| `task/external_tool_requirements.json` | Stable scaffold |
| `results/evidence_index.json` | Stable scaffold |
| `results/claim_map.json` | Stable scaffold |
| `provenance/tool_trace.json` | Stable scaffold |
| `provenance/conversion_manifest.json` | Stable scaffold (Phase 20) |
| `provenance/converter_capabilities.json` | Stable scaffold (Phase 20) |
