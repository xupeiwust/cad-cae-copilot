# MVP 1 Development Plan

## Active Scope: MVP 1A Complete, MVP 1B Complete, MVP 1C-A Complete, MVP 1C-B1 Complete, MVP 1C-B2 Complete

This document scopes the work required for MVP 1: a minimal cross-project vertical slice where `aieng_freecad_mcp` can load an optional `.aieng` package, validate a guarded parametric edit, write evidence and trace records, mark affected references as `needs_review`, and always return `"claims_advanced": false`.

---

## 1. Overall MVP 1 Goal

Build a composable execution bridge between `.aieng` packages and FreeCAD that:

- Loads `.aieng` zip packages as optional execution context.
- Reads manifest, feature graph, task spec, references, evidence index, trace, and claim map.
- Validates parametric edits against guards before execution.
- Writes evidence and trace records back into the `.aieng` package.
- Marks affected geometry references as `needs_review`.
- Never modifies `claim_map.json` during execution.
- Always returns `claims_advanced: false` from execution tools.
- Operates in both `.aieng`-enhanced and standalone modes.

---

## 2. Current Repository State Summary

### `aieng/` (format and core)

- Owns the `.aieng` package format: zipped packages with typed resources.
- Defines schemas: `manifest`, `claim_map`, `evidence_index`, `tool_trace`, `patch_proposal`.
- Provides zip-based package creation, evidence writing, trace writing, and claim updating.
- Enforces core policy: `aieng_core` cannot produce `solver_result`, `mesh_evidence`, or `geometry_modification` evidence.
- Operates exclusively on **zipped .aieng packages**.

### `aieng_freecad_mcp/` (execution adapter)

- Owns the MCP server, CAD/CAE tools, and `.aieng` bridge.
- Already implements: context loading (unpacked dirs), guards, patch execution, evidence/trace persistence, reference marking, claim update layer.
- Enforces: `claims_advanced: false` by default; only `claims.py::update_claim_status()` may modify `claim_map.json`.
- Operates on **unpacked directories** for `.aieng` context.
- Has comprehensive unit and integration tests for all bridge components.

### The Gap

MVP 1A closed the zip/unpacked directory interoperability gap. `aieng_freecad_mcp` now loads `.aieng` zip packages as context and persists evidence/trace into them. The remaining gap for MVP 1B is end-to-end guarded parametric edit validation and execution through a stubbed CAD boundary, so the full patch lifecycle works without requiring real FreeCAD in default tests.

---

## 3. Overall MVP 1 Phases

| Phase | Scope | FreeCAD Required | Status |
|---|---|---|---|
| **1A** | Zip package loading and persistence (context, evidence, trace) | No | **Complete** |
| **1B** | Guarded parametric edit validation with simulated/stubbed execution | No | **Complete** |
| **1C-A** | FreeCAD availability check (read-only, config + filesystem probe) | No | **Complete** |
| **1C-B1** | Executor config and FreeCAD marked-test cleanup | No | **Complete** |
| **1C-B2** | Real guarded parameter edit via FreeCADCmd subprocess | Yes (marked tests only) | **Complete** |

---

## 4. Detailed MVP 1A Plan

### 4.1 Goal

Enable `aieng_freecad_mcp` to load `.aieng` zip packages as optional context and persist evidence/trace records into them, while preserving all existing unpacked-directory behavior. Prove that `claim_map.json` is never modified and `claims_advanced` remains `false`.

### 4.2 Work Items

#### WI-1: Extend context loader for zip packages

**File:** `src/freecad_mcp/aieng_bridge/context.py`

**What:** Extend `load_aieng_context()` to auto-detect `.aieng` files (by extension) and read all resources from the zip archive. When the path is a directory, preserve existing behavior.

**Resources to load from zip:**
- `manifest.json`
- `graph/feature_graph.json`
- `graph/task_spec.json`
- `references/reference_map.json`
- `results/evidence_index.json`
- `provenance/tool_trace.json`
- `results/claim_map.json`

**Behavior:**
- If `package_path` ends with `.aieng`, open as `zipfile.ZipFile`.
- Read each JSON resource via `zipfile.open(name)`.
- Populate `AiengPackageContext` identically to directory mode.
- If a resource is missing in the zip, treat it the same as a missing file in a directory (`None` or default).
- If `package_path` is a directory, use existing logic unchanged.
- Return context with `mode: "aieng_enhanced"` if manifest is found and valid, else `"standalone"`.

**Test file:** `tests/test_zip_context.py`

**Tests:**
- Load context from a valid `.aieng` zip with all resources populated.
- Load context from a `.aieng` zip with missing optional resources (graceful fallback).
- Load context from a directory (existing behavior unchanged).
- Load context from a non-existent path (standalone mode).
- Verify `AiengPackageContext` fields match between zip and dir for the same package content.

---

#### WI-2: Extend persistence layer for zip packages

**File:** `src/freecad_mcp/aieng_bridge/persistence.py`

**What:** Extend `persist_standard_result_to_aieng()` and its helpers to write evidence and trace entries into `.aieng` zip packages. Preserve existing unpacked-directory behavior.

**Behavior:**
- Detect `.aieng` extension on `package_path`.
- For evidence: read existing `results/evidence_index.json` from zip, append new entry, write back.
- For trace: read existing `provenance/tool_trace.json` from zip, append new entry, write back.
- Use atomic write pattern: extract zip to temp directory, modify files, create new zip at temp path, `os.replace` over original.
- Never create or modify `results/claim_map.json` during this process.
- Return metadata dict with `evidence_id` and `trace_id` (same contract as directory mode).

**Error handling:**
- If the zip is malformed, raise `PersistenceError`.
- If atomic replace fails (e.g., file locked on Windows), raise `PersistenceError` with descriptive message.

**Test file:** `tests/test_persistence_zip.py`

**Tests:**
- Append evidence entry to `.aieng` zip; verify `results/evidence_index.json` contains the new entry and all prior entries.
- Append trace entry to `.aieng` zip; verify `provenance/tool_trace.json` contains the new entry and all prior entries.
- Persist full `StandardToolResult` to `.aieng` zip; verify both evidence and trace are written.
- Verify `claim_map.json` in zip is unchanged after persistence.
- Verify atomicity: if persistence fails mid-write, original zip is unmodified (or replace is atomic).
- Test schema conformance: load written `evidence_index.json` and `tool_trace.json` and validate against `aieng/schemas/` using `jsonschema`.

---

#### WI-3: Add schema conformance validation to tests

**What:** Ensure all persisted evidence and trace JSON conforms to `aieng/schemas/evidence_index.schema.json` and `aieng/schemas/tool_trace.schema.json`.

**Behavior:**
- In zip persistence tests, after writing, load the JSON from the zip and validate with `jsonschema.validate`.
- Do not copy schemas into `aieng_freecad_mcp`. Reference `../aieng/schemas/` from tests (document the path assumption).
- If `aieng` is not available at the expected path, skip schema validation with a warning.

---

#### WI-4: Shared test fixtures for `.aieng` zip packages

**What:** Create a pytest fixture that generates a valid `.aieng` zip package programmatically.

**Approach:**
- Use `aieng.package.create_package` from the sibling `aieng` repo to create the zip scaffold.
- Populate it with test data derived from `examples/parametric_bracket/package/`.
- This avoids checking in binary `.aieng` files.

**File:** `tests/conftest.py` (add fixture) or `tests/fixtures.py`

**Fixture contract:**
- Returns a `pathlib.Path` to a temp `.aieng` zip file.
- Temp file is cleaned up after test.
- Optionally accepts parameters for which resources to include.

---

### 4.3 MVP 1A Non-Goals

- FreeCAD execution or parameter setting.
- `old_value` capture from FreeCAD.
- STEP or FCStd export changes.
- Guard logic changes (reuse existing).
- Claim update logic changes (reuse existing).
- Schema redesign or schema copying.
- CAE, meshing, or solver execution.
- Reference map building (only reading and marking from zip).

---

### 4.4 MVP 1A Boundary Rules

1. **Zip vs directory is an implementation detail of I/O.** All public APIs (`load_aieng_context`, `persist_standard_result_to_aieng`) must accept both and behave identically from the caller's perspective.
2. **Never modify `claim_map.json` during persistence.** The persistence layer appends evidence and trace only. Claim map changes are the exclusive responsibility of `claims.py::update_claim_status()`.
3. **`claims_advanced` must be `false` in all trace entries written by the persistence layer.** This is enforced by the `TraceBlock` default in `tool_contracts.py` and must not be overridden.
4. **Do not duplicate `aieng` schemas.** Reference them from the sibling repo in tests only.
5. **Preserve all existing unpacked-directory tests.** Add zip tests; do not replace or break existing tests.
6. **MVP 1A makes no changes to the `aieng/` repository.** If an implementation step appears to require changes to `aieng/`, stop and document the reason before proceeding.

---

### 4.5 MVP 1A Test Strategy

**Default test suite (no FreeCAD required):**

| Test File | Coverage |
|---|---|
| `tests/test_zip_context.py` | Context loading from `.aieng` zip, resource fallbacks, parity with dir mode |
| `tests/test_persistence_zip.py` | Evidence/trace append to `.aieng` zip, atomicity, claim_map immutability, schema conformance |
| Existing tests | Unchanged; run to verify no regression |

**Test markers:**
- No new FreeCAD-dependent tests in 1A.
- All 1A tests must pass under `pytest -m "not freecad"`.

**Schema conformance:**
- Validate evidence_index.json against `aieng/schemas/evidence_index.schema.json`.
- Validate tool_trace.json against `aieng/schemas/tool_trace.schema.json`.
- Skip validation if `aieng/schemas/` is not found at the expected relative path.

---

### 4.6 MVP 1A Completion Criteria

- [x] `load_aieng_context()` reads all `.aieng` resources from zip packages correctly.
- [x] `persist_standard_result_to_aieng()` appends evidence and trace entries to `.aieng` zip packages correctly.
- [x] Existing unpacked-directory behavior is preserved and all existing tests pass.
- [x] After persistence to a `.aieng` zip, `results/claim_map.json` inside the zip is byte-identical to its pre-persistence state.
- [x] All trace entries written to `.aieng` zip have `claims_advanced: false`.
- [x] Evidence and trace JSON written to `.aieng` zip conform to `aieng` schemas (when schema files are available).
- [x] Default test suite passes without FreeCAD installed.
- [x] New tests cover edge cases: missing resources in zip, malformed zip, atomic write failure.

**MVP 1A Completed:** 2026-05-14
- Implementation commit: `73986bc`
- Plan commit: `42df320`
- Tests run: `pytest tests/ -m "not freecad"`
- Result: `366 passed, 13 skipped, 0 failures`
- FreeCAD required: No
- Claim map modified by execution/persistence: No
- `claims_advanced` set to true by execution paths: No

---

## 5. Detailed MVP 1B Plan

### MVP 1B: Guarded Parametric Edit Without Real FreeCAD

**Status:** Complete

---

### 5.1 Scope

Build the next vertical slice where `aieng_freecad_mcp` validates and executes a guarded parametric edit through an adapter or stub boundary, without requiring real FreeCAD in default tests.

**In scope:**
- Load `.aieng` zip or unpacked package context (reuse MVP 1A).
- Read parameter definitions and constraints from `feature_graph.json`.
- Validate requested parameter edits against the feature graph:
  - Reject unknown parameters (parameter not defined in feature's `parameters` list).
  - Reject non-editable parameters (`editability.executable` is `false` or missing).
  - Reject protected parameters or features (check against `protected_regions` in task spec if present).
  - Reject out-of-range values (check against `min_value`, `max_value`, or `constraints` if defined).
  - Reject unsupported units or missing required constraints.
- Use a stubbed or adapter-based execution boundary:
  - A `StubFreecadExecutor` or stub function returns deterministic execution results.
  - The stub simulates parameter mutation by returning `old_value`, `new_value`, and a success status.
  - No FreeCAD import or runtime dependency in the stub path.
- Produce deterministic `StandardToolResult` with `claims_advanced: false`.
- Write evidence records to `.aieng` package (zip or directory) via MVP 1A persistence.
- Append trace records to `.aieng` package (zip or directory) via MVP 1A persistence.
- Mark affected references as `needs_review` via existing `mark_references_needing_review()`.
- Preserve `results/claim_map.json` — never modify it during execution.
- Return `"claims_advanced": false` in all execution tool results.
- Keep default tests independent of FreeCAD.

---

### 5.2 Non-Goals

- Real FreeCAD execution or parameter mutation.
- `old_value` capture from real FreeCAD.
- STEP or FCStd export changes.
- CAE setup, meshing, or solver execution.
- Blender support or any non-FreeCAD CAD backend.
- Automatic CAD-to-CAE orchestration.
- Claim updates (`claim_map.json` is read-only during execution).
- Schema redesign or copying canonical `.aieng` schemas into `aieng_freecad_mcp`.
- Changes to `../aieng/` unless explicitly approved later.

---

### 5.3 Expected Behavior

**Patch proposal flow:**
1. Caller provides a patch proposal (e.g., `modify_parameter` on `feat_base_plate_001`, `thickness_mm` -> `8.0`).
2. `parse_patch_proposal()` validates the proposal structure (already exists).
3. `load_aieng_context()` loads the `.aieng` package context (zip or directory) — MVP 1A.
4. `resolve_feature_parameter()` maps semantic feature ID + parameter name to executable refs (already exists).
5. `check_operation_allowed()` runs guards against task spec, feature graph editability, and protected regions (already exists).
6. **New for 1B:** Additional parameter-level validation:
   - Verify parameter exists in feature's `parameters` list.
   - Verify `editability.executable` is `true`.
   - Verify value is within any declared `min_value` / `max_value` bounds.
   - Verify unit matches expected unit if specified.
7. **New for 1B:** Stubbed execution boundary simulates the parameter change:
   - Returns `{"old_value": <current>, "new_value": <requested>, "success": true}`.
   - If simulation constraints are violated, returns failure with reason.
8. `persist_standard_result_to_aieng()` writes evidence and trace — MVP 1A.
9. `mark_references_needing_review()` updates reference map for affected features — already exists.
10. Return `PatchExecutionSummary` with `status`, `steps`, `evidence_ids`, `trace_ids`, and `claim_policy` where `claims_advanced: false`.

**Stub behavior:**
- The stub does not import FreeCAD.
- The stub reads `current_value` from the feature graph parameter definition and returns it as `old_value`.
- The stub accepts the requested `new_value` and returns it.
- The stub validates type compatibility (e.g., numeric parameters reject string values).
- The stub can optionally simulate simple constraint failures (e.g., negative thickness).

---

### 5.4 Files Likely to Modify

| File | Change |
|---|---|
| `src/freecad_mcp/aieng_bridge/patch.py` | Extend `execute_patch_plan()` to support stubbed execution. May add `dry_run=True` path or accept a configurable executor/stub boundary. Add parameter-level validation before execution. |
| `src/freecad_mcp/aieng_bridge/guards.py` | Potentially extend `check_operation_allowed()` with parameter-level guards (range checks, unit checks) if not already present. |
| `src/freecad_mcp/aieng_bridge/stub_executor.py` *(new)* | Stubbed CAD executor implementing the same async interface as `FreecadExecutor`. Returns deterministic results without importing FreeCAD. |
| `tests/test_aieng_patch.py` | Add tests for stubbed execution path: valid edit, rejected edit, guard failure, evidence/trace persistence, reference marking, claim_map immutability. |
| `tests/test_stub_executor.py` *(new)* | Unit tests for stub boundary: deterministic results, type validation, constraint simulation. |

---

### 5.5 Tests to Add

**`tests/test_stub_executor.py`:**
- Stub returns deterministic `old_value` / `new_value` for a known parameter.
- Stub rejects non-numeric values for numeric parameters.
- Stub rejects values out of declared range.
- Stub does not import FreeCAD.

**`tests/test_aieng_patch.py` (extend):**
- Execute valid `modify_parameter` patch against `.aieng` zip with stubbed executor.
- Execute valid `modify_parameter` patch against unpacked directory with stubbed executor.
- Reject patch for non-editable feature (`editability.executable: false`).
- Reject patch for unknown parameter.
- Reject patch for out-of-range value.
- Verify evidence and trace are written to `.aieng` zip after stubbed execution.
- Verify `claim_map.json` is unchanged after stubbed execution.
- Verify `claims_advanced: false` in result.
- Verify affected references are marked `needs_review`.

**Integration tests:**
- Full end-to-end: load `.aieng` zip -> parse patch -> validate guards -> stub execute -> persist evidence/trace -> mark references.
- All default tests pass with `pytest -m "not freecad"`.

---

### 5.6 Boundary Rules

1. **Stub and real executor are interchangeable at the boundary.** `execute_patch_plan()` must accept either a real `FreecadExecutor` or a stub without structural code changes.
2. **Never modify `claim_map.json` during execution.** Only `claims.py::update_claim_status()` may modify claims.
3. **`claims_advanced` must be `false` in all execution tool results.** The stub boundary must not override this.
4. **Default tests must not require FreeCAD.** All 1B default tests pass under `pytest -m "not freecad"`.
5. **Reuse MVP 1A persistence.** Evidence and trace writeback to `.aieng` zip uses the existing persistence layer; do not duplicate zip I/O logic.
6. **Parameter validation happens before stub execution.** Rejections are recorded as `PatchExecutionStep` with `status: "rejected"`, not as exceptions.
7. **MVP 1B makes no changes to the `aieng/` repository.**

---

### 5.7 Completion Criteria

- [x] `execute_patch_plan()` runs end-to-end with a stubbed executor against `.aieng` zip packages.
- [x] Parameter-level validation rejects unknown, non-editable, out-of-range, and unit-mismatched parameters.
- [x] Guard checks (`check_operation_allowed`) run before stub execution and reject disallowed operations.
- [x] Stubbed execution returns deterministic `old_value` / `new_value` without importing FreeCAD.
- [x] Evidence and trace are persisted to `.aieng` zip after successful stubbed execution.
- [x] Affected references are marked `needs_review` after geometry-modifying stubbed execution.
- [x] `claim_map.json` is unchanged after stubbed execution.
- [x] All execution paths return `claims_advanced: false`.
- [x] Default test suite passes without FreeCAD installed.
- [x] Existing MVP 1A behavior is preserved (no regressions in zip loading or persistence).

**MVP 1B Completed:** 2026-05-14
- Implementation commit: `39a29ae`
- Implementation files:
  - ``src/freecad_mcp/aieng_bridge/stub_executor.py`` (new)
  - ``src/freecad_mcp/aieng_bridge/patch.py`` (parameter validation + stub integration)
  - ``tests/test_stub_executor.py`` (new)
  - ``tests/test_aieng_patch.py`` (stubbed execution tests)
- Tests run: ``pytest tests/ -m "not freecad"``
- Result: ``385 passed, 13 skipped, 0 failures``
- FreeCAD required: No
- Claim map modified by execution/persistence: No
- ``claims_advanced`` set to true by execution paths: No

---

### 5.8 Risks or Unclear Assumptions

| Risk | Mitigation |
|---|---|
| **Feature graph parameter schema may not define `min_value` / `max_value`.** | Gracefully skip range checks if bounds are absent; do not invent constraints. |
| **Stub executor interface drift from real FreecadExecutor.** | Keep stub minimal and aligned with the real executor's async interface; document deviations. |
| **Parameter validation logic overlap with guards.** | Define clear separation: guards check operation-level policy; parameter validation checks feature-graph constraints. |
| **Reference map marking may require geometry change detection.** | The stub should signal "geometry modified" when a parameter is successfully changed, triggering reference marking. |
| **Tests may accidentally depend on real FreeCAD if imports are not guarded.** | Ensure stub module has zero FreeCAD imports; gate any FreeCAD-dependent tests behind `@pytest.mark.freecad`. |

---

## 6. Detailed MVP 1C Plan

### MVP 1C: Optional FreeCAD Adapter Integration

**Status:** MVP 1C-A Complete, MVP 1C-B Planned

---

### 6.1 Goal

Connect the existing guarded parametric edit flow (MVP 1A context loading, MVP 1B validation and stub execution) to real FreeCAD execution when FreeCAD is available, while keeping FreeCAD entirely optional and excluded from default tests.

When FreeCAD is present and explicitly requested:
- Load `.aieng` package context (zip or directory) — reuse MVP 1A.
- Run full guard checks and parameter validation — reuse MVP 1B.
- Execute the parameter change through a real FreeCAD adapter.
- Capture the actual `old_value` from FreeCAD before mutation.
- Export modified CAD artifacts (STEP, FCStd) when requested.
- Persist evidence and trace records — reuse MVP 1A persistence.
- Mark affected references as `needs_review` — reuse existing logic.
- Always return `claims_advanced: false`.

When FreeCAD is absent:
- The system gracefully falls back to stubbed execution (MVP 1B).
- Default tests pass without FreeCAD installed.

---

### 6.2 Scope

**In scope:**
- FreeCAD path discovery via environment variable (`FREECAD_HOME`) and settings.
- FreeCAD availability check at runtime and during test collection.
- Real `cad_set_parameter` execution through the existing `FreecadExecutor` when connected.
- Actual `old_value` capture from FreeCAD before setting a new value.
- Real STEP and FCStd export after successful parameter modification.
- Integration tests that run real FreeCAD, gated behind `@pytest.mark.freecad`.
- All evidence/trace/reference persistence and claim immutability rules from MVP 1A/1B remain in effect.

**In scope for 1C-A (availability check):**
- Detect FreeCAD installation at configured path.
- Report availability in runtime capability inspection.
- Add `@pytest.mark.freecad` marker and skip logic.

**In scope for 1C-B1 (executor config and test cleanup):**
- Extend `FreecadExecutor._connect_embedded()` to check `FREECAD_HOME` and `FREECAD_MCP_FREECAD_PATH` before hard-coded platform fallbacks.
- Add `@pytest.mark.freecad` marker to existing real FreeCAD integration tests.
- Add `pytest_runtest_setup` hook in `conftest.py` for centralized skip behavior.

**In scope for 1C-B2 (real parameter edit):**
- Execute a bounded, guarded `modify_parameter` patch through a **FreeCADCmd subprocess** backend.
- Verify `old_value` is captured from the live document, not the feature graph.
- Verify exported STEP/FCStd artifacts are real files.
- Verify evidence records include actual FreeCAD-derived values.
- Prefer subprocess over embedded `import FreeCAD`; keep embedded mode as optional/legacy only.

---

### 6.3 Non-Goals

- Automatic CAD-to-CAE orchestration.
- Meshing or solver execution.
- Post-processing claim interpretation.
- Claim updates (`claim_map.json` is read-only during execution).
- Arbitrary natural-language CAD modeling.
- Arbitrary B-rep editing (only bounded parametric edits).
- Blender support or any non-FreeCAD CAD backend.
- Schema redesign or copying canonical `.aieng` schemas into this repo.
- Changes to `../aieng/`.
- Making FreeCAD a default test dependency.

---

### 6.4 Expected Behavior

**Real FreeCAD patch execution flow:**
1. Caller provides a patch proposal with `use_freecad=true` or similar explicit flag.
2. `load_aieng_context()` loads `.aieng` package context (zip or directory).
3. `parse_patch_proposal()` validates structure.
4. `resolve_feature_parameter()` maps semantic IDs to executable refs.
5. `check_operation_allowed()` runs guards.
6. `validate_parameter_edit()` checks parameter-level constraints.
7. **New for 1C:** FreeCAD availability check — if FreeCAD is not available, reject with clear message or fall back to stub (configurable).
8. **New for 1C-B2:** Real execution via **FreeCADCmd subprocess**:
   - Generate a bounded Python script from the validated patch operation (not arbitrary code).
   - Launch `FreeCADCmd` (or `freecadcmd`) as a subprocess with the script.
   - The script runs inside FreeCAD's own Python runtime, avoiding host Python ABI mismatch.
   - Actual `old_value` is read from the FreeCAD object before mutation.
   - Result includes real `old_value`, `new_value`, and post-recompute state.
   - Capture exit code, stdout, stderr, and a structured JSON result block.
9. `persist_standard_result_to_aieng()` writes evidence and trace.
10. `mark_references_needing_review()` updates reference map.
11. Return `PatchExecutionSummary` with `claims_advanced: false`.

**Fallback behavior:**
- If FreeCAD is not available and the caller did not explicitly request real execution, fall back to stubbed execution (MVP 1B).
- If FreeCAD was explicitly requested but is unavailable, return `status: "rejected"` with a clear reason.

---

### 6.5 FreeCAD Configuration

**Path resolution (no hard-coded paths):**
1. Check `FREECAD_HOME` environment variable.
2. Check `FREECAD_MCP_FREECAD_PATH` setting (existing config key).
3. Check common platform paths as fallback (for convenience, not required).
4. If no path resolves, FreeCAD is considered unavailable.

**The local path `D:\FreeCAD 1.1` must never be hard-coded in source.**
It may be used only via:
- Environment variable: `set FREECAD_HOME=D:\FreeCAD 1.1`
- Test configuration: pytest fixture or `.env` file
- CI configuration

**Settings precedence:**
```
FREECAD_HOME env var > pydantic-settings config > common fallback paths
```

---

### 6.6 FreeCAD Availability Check

**Runtime check:**
- `detect_freecad_runtime()` already exists in `freecad_runtime.py`.
- Extend it to check the configured path and attempt a lightweight import or version query.
- Return structured availability report: `freecad_available`, `version`, `path`, `error`.

**Test-level check:**
- Add `@pytest.mark.freecad` to any test that requires FreeCAD.
- `conftest.py` should register a custom marker and skip logic:
  ```python
  def pytest_runtest_setup(item):
      if "freecad" in item.keywords and not freecad_available():
          pytest.skip("FreeCAD not available")
  ```

**Import guard:**
- FreeCAD imports must only happen inside functions/methods, never at module import time.
- This ensures `pytest -m "not freecad"` never triggers a FreeCAD import.

---

### 6.7 Integration Test Strategy

**Test layers:**

| Layer | FreeCAD Required | Marker | Coverage |
|---|---|---|---|
| Unit | No | default | Stub executor, parameter validation, persistence, guards |
| Integration (zip/stub) | No | default | End-to-end patch flow with stubbed execution |
| Integration (FreeCAD) | Yes | `freecad` | Real parametric edit, artifact export, old value capture |

**FreeCAD integration tests to add:**
- `test_real_freecad_parameter_edit`: Execute a valid `modify_parameter` patch against a real FreeCAD document. Verify `old_value` is read from FreeCAD, not the feature graph.
- `test_real_freecad_step_export`: After parameter modification, export STEP and verify the file exists and is non-empty.
- `test_real_freecad_fcstd_export`: After parameter modification, save FCStd and verify the file exists.
- `test_real_freecad_guard_rejection`: Attempt to edit a protected feature; verify rejection before FreeCAD is touched.
- `test_real_freecad_evidence_persistence`: After real execution, verify evidence record contains actual FreeCAD-derived `old_value` and `new_value`.
- `test_real_freecad_claim_map_unchanged`: After real execution, verify `claim_map.json` is unchanged.
- `test_freecad_unavailable_skips`: Test that `@pytest.mark.freecad` tests skip when FreeCAD is absent.

**Test file:** `tests/test_real_freecad_patch_integration.py` (already exists; extend with 1C tests).

---

### 6.8 Files Likely to Modify

| File | Change |
|---|---|
| `src/freecad_mcp/bridge/executor.py` | Extend `FreecadExecutor` with configurable FreeCAD path from `FREECAD_HOME`; improve `_connect_embedded` path resolution. |
| `src/freecad_mcp/freecad_runtime.py` | Extend `detect_freecad_runtime()` to probe `FREECAD_HOME` and return structured availability. |
| `src/freecad_mcp/config.py` | Add `freecad_home` setting that reads `FREECAD_HOME` env var. |
| `src/freecad_mcp/aieng_bridge/patch.py` | Add `use_freecad` or `executor_type` parameter to `execute_patch_plan()`; route to real executor or stub based on availability and caller intent. |
| `src/freecad_mcp/tools_cad/__init__.py` | Ensure `_execute_set_parameter` works with real executor; no changes needed if interface is stable. |
| `tests/conftest.py` | Add `@pytest.mark.freecad` skip logic; add `freecad_available()` fixture. |
| `tests/test_real_freecad_patch_integration.py` | Add real FreeCAD integration tests for parameter edit, export, evidence persistence. |

---

### 6.9 Boundary Rules

1. **FreeCAD is optional.** Default tests pass without FreeCAD. The system must not crash on import if FreeCAD is absent.
2. **Never modify `claim_map.json` during execution.** Only `claims.py::update_claim_status()` may modify claims.
3. **`claims_advanced` must be `false` in all execution tool results.** Real FreeCAD execution must not override this.
4. **Explicit opt-in for real execution.** Real FreeCAD is not used automatically; the caller must explicitly request it or the tool must clearly signal when it is falling back to stub.
5. **Import guards required.** FreeCAD imports happen only inside function bodies, never at module level.
6. **Default tests must not require FreeCAD.** All default tests pass under `pytest -m "not freecad"`.
7. **MVP 1C makes no changes to the `aieng/` repository.**

---

### 6.10 Completion Criteria

- [x] **1C-A** FreeCAD path is configurable via `FREECAD_HOME` (no hard-coded paths).
- [x] **1C-A** `check_freecad_availability()` correctly reports FreeCAD availability at configured path.
- [x] **1C-A** `@pytest.mark.freecad` skips gracefully when FreeCAD is absent.
- [x] **1C-B1** `FreecadExecutor._connect_embedded()` checks `FREECAD_HOME` and `FREECAD_MCP_FREECAD_PATH` before platform fallbacks.
- [x] **1C-B1** `@pytest.mark.freecad` is applied to all real FreeCAD integration tests.
- [x] **1C-B1** `conftest.py` provides centralized skip logic for `@pytest.mark.freecad` tests.
- [x] **1C-B2** `execute_patch_plan()` can route to real FreeCAD execution via FreeCADCmd subprocess when requested and available.
- [x] **1C-B2** Real parameter edit captures actual `old_value` from FreeCAD.
- [x] **1C-B2** Real STEP and FCStd export produce valid files.
- [x] **1C-B2** Evidence and trace are persisted after real execution.
- [x] **1C-B2** Affected references are marked `needs_review` after real geometry-modifying execution.
- [x] **1C-B2** `claim_map.json` is unchanged after real execution.
- [x] **1C-A/1C-B1** All execution paths return `claims_advanced: false`.
- [x] **1C-A/1C-B1** Default test suite passes without FreeCAD installed.
- [x] **1C-A/1C-B1** FreeCAD-marked tests skip gracefully when FreeCAD is absent.
- [x] **1C-A/1C-B1** No regressions in MVP 1A or 1B behavior.

---

### 6.11 Risks or Unclear Assumptions

| Risk | Mitigation |
|---|---|
| **FreeCAD path varies across environments (Windows, Linux, macOS).** | Use `FREECAD_HOME` env var as primary; platform fallbacks are convenience only. |
| **FreeCAD import may fail silently or with confusing errors.** | Wrap import attempts in structured exception handling; report clear availability status. |
| **Host Python ABI mismatch prevents embedded `import FreeCAD`.** | Prefer FreeCADCmd subprocess; embedded mode is optional/legacy only. Subprocess runs FreeCAD's own Python runtime. |
| **Real FreeCAD execution may be slow, causing test timeouts.** | Set long timeouts for FreeCAD-marked tests; run them in CI only when FreeCAD is installed. |
| **FreeCAD version differences may affect behavior.** | Record FreeCAD version in evidence; document tested version in plan. |
| **Feature graph `current_value` may diverge from FreeCAD actual value.** | Always capture `old_value` from FreeCAD, never from feature graph, during real execution. |
| **Recompute may fail after parameter change, leaving invalid geometry.** | Check `doc.recompute()` success; report failed features in step result. |
| **Subprocess script injection risk.** | Generate scripts from bounded operations only; never accept arbitrary Python from callers. |

---

### 6.12 Suggested Implementation Phases

#### MVP 1C-A: FreeCAD Availability Check Only

**Status:** Complete

**Goal:** Detect and report FreeCAD availability without executing any CAD operations.

**Work items:**
1. ~~Add `freecad_home` config setting reading `FREECAD_HOME`.~~ Implemented via direct `os.environ` lookup in `availability.py`.
2. ~~Extend `detect_freecad_runtime()` to probe the configured path.~~ Implemented as new `check_freecad_availability()` in `aieng_bridge/availability.py`.
3. Add `@pytest.mark.freecad` marker in `pyproject.toml`.
4. Write tests for availability detection (works when FreeCAD present, skips when absent).

**Files:**
- `pyproject.toml` — registered `freecad` pytest marker
- `src/freecad_mcp/aieng_bridge/availability.py` *(new)* — `check_freecad_availability()` with structured `FreecadAvailabilityResult`
- `tests/test_availability.py` *(new)* — 8 default tests + 1 `@pytest.mark.freecad` test

**Completion:** `check_freecad_availability()` reports accurate availability; `@pytest.mark.freecad` tests skip cleanly.

**MVP 1C-A Completed:** 2026-05-14
- Implementation commit: `57bba7d`
- Tests run:
  - `pytest tests/ -m "not freecad"`
  - `set FREECAD_HOME=D:\FreeCAD 1.1 && pytest tests/ -m freecad`
- Results:
  - Default: `393 passed, 13 skipped, 1 deselected`
  - Marked FreeCAD availability: `1 passed, 406 deselected`
- FreeCAD required for default tests: **No**
- CAD files opened, modified, or saved: **No**
- `results/claim_map.json` modified: **No**
- `claims_advanced` set to `true`: **No**

#### MVP 1C-B1: Executor Configuration and FreeCAD Marked-Test Cleanup

**Status:** Complete

**Goal:** Centralize FreeCAD path configuration and gate all real FreeCAD tests behind `@pytest.mark.freecad` so that default tests never require FreeCAD.

**Work items:**
1. Extend `FreecadExecutor._connect_embedded()` to check `FREECAD_MCP_FREECAD_PATH` and `FREECAD_HOME` before platform fallbacks.
2. Add `pytest_runtest_setup` hook in `tests/conftest.py` to skip `@pytest.mark.freecad` tests when `import FreeCAD` fails.
3. Add `@pytest.mark.freecad` to `TestRealFreecadPatchIntegration` in `tests/test_real_freecad_patch_integration.py`.

**Files:**
- `src/freecad_mcp/bridge/executor.py` — updated `_connect_embedded()` env-var resolution
- `tests/conftest.py` — added `pytest_runtest_setup` skip hook
- `tests/test_real_freecad_patch_integration.py` — added `@pytest.mark.freecad` class marker

**Rationale for subprocess preference:** During 1C-B1 verification, `import FreeCAD` from the host Python 3.14 environment failed against FreeCAD 1.1 compiled modules (ABI mismatch). This confirms embedded import is fragile and should not be the primary real execution path.

**MVP 1C-B1 Completed:** 2026-05-14
- Implementation commit: `edbaebd`
- Tests run:
  - `python -m pytest -m "not freecad"`
  - `set FREECAD_HOME=D:\FreeCAD 1.1 && python -m pytest -m freecad`
- Results:
  - Default: `393 passed, 8 skipped, 6 deselected`
  - Marked FreeCAD: `6 skipped` (expected ABI mismatch)
- FreeCAD required for default tests: **No**
- CAD files opened, modified, or saved: **No**
- Files under `../aieng/` changed: **No**
- `results/claim_map.json` modified: **No**
- `claims_advanced` set to `true`: **No**

---

#### MVP 1C-B2: Real Guarded Parameter Edit via FreeCADCmd Subprocess

**Status:** Complete

**Goal:** Execute a bounded parametric edit through real FreeCAD using a **FreeCADCmd subprocess backend**, avoiding host Python ABI mismatch.

**Why subprocess over embedded:**
- Embedded `import FreeCAD` is fragile because FreeCAD compiled modules must match the host Python ABI.
- The current environment demonstrates this: FreeCAD 1.1 modules are not importable from Python 3.14.
- `FreeCADCmd` runs with FreeCAD's own Python runtime and avoids host Python ABI mismatch entirely.
- Subprocess execution improves isolation and auditability.
- Embedded mode may remain optional or legacy, but must not be the primary 1C-B2 path.
- XMLRPC may be considered later for long-running performance-oriented execution, but not for MVP 1C-B2.

**Work items:**
1. Implement a FreeCADCmd subprocess executor or equivalent adapter:
   - Generate bounded Python scripts from validated patch operations only (no arbitrary Python execution).
   - Launch `FreeCADCmd` (or `freecadcmd`) as a subprocess with the generated script.
   - Capture structured JSON result block, exit code, stdout, and stderr.
   - Implement timeout handling.
2. Configurable path resolution via `FREECAD_MCP_FREECAD_PATH` and/or `FREECAD_HOME`:
   - No hard-coded local paths in source code.
   - `FREECAD_MCP_FREECAD_PATH` takes precedence over `FREECAD_HOME`.
3. Integrate with `execute_patch_plan()`:
   - Route to subprocess executor when available and requested.
   - Fall back to stub executor when FreeCAD is unavailable or not requested.
4. Verify `old_value` is captured from the live FreeCAD document, not the feature graph.
5. Enable real STEP/FCStd export after successful edit.
6. Write integration tests for real execution, export, evidence persistence.

**Evidence and trace provenance:**
- Record command path (`FreeCADCmd` executable location).
- Record exit code.
- Record script hash (SHA-256 of generated script).
- Record artifact paths (STEP, FCStd) produced by execution.
- Record stdout/stderr summary or truncated content.

**Files:**
- `src/freecad_mcp/bridge/executor.py` — add subprocess execution mode
- `src/freecad_mcp/bridge/freecad_cmd.py` *(new)* — script generation and subprocess orchestration
- `src/freecad_mcp/aieng_bridge/patch.py` — route to subprocess executor
- `tests/test_real_freecad_patch_integration.py` — subprocess-backed integration tests

**Completion:** A guarded patch can be executed against real FreeCAD via subprocess; evidence records contain actual values; exports produce real files; all boundary rules hold.

**MVP 1C-B2 Completed:** 2026-05-14
- Implementation commit: `f5eaf11`
- Execution backend: `FreeCADCmd` subprocess executor
- Default tests: `pytest -m "not freecad"` → `419 passed, 14 skipped, 6 deselected`
- Embedded FreeCAD marked tests: `pytest -m freecad` → `6 skipped` due to expected Python ABI mismatch
- FreeCADCmd integration tests: `TestFreecadCmdPatchIntegration` → `6 passed`
- Source CAD files modified in place: No
- `results/claim_map.json` modified: No
- `claims_advanced` set to true: No
- Files under `../aieng/` changed: No
- `.aieng` schema changes: No
- FreeCAD remains an optional adapter backend

**Non-goals for 1C-B2:**
- No public arbitrary Python execution tool.
- No default FreeCAD dependency (marked tests only).
- No claim updates (`claim_map.json` remains read-only during execution).
- No CAE, meshing, or solver execution.
- No XMLRPC implementation (may be added later).

---

## 7. Non-Goals (All of MVP 1)

- CAE setup, meshing, or solver execution.
- Blender support or any non-FreeCAD CAD backend.
- Claim updates via execution tools (`claim_map.json` is read-only during execution).
- Schema redesign or creating canonical schema copies in `aieng_freecad_mcp`.
- Autonomous workflow orchestration (CAD to CAE to claim chaining).
- Visual-only validation shortcuts.
- Arbitrary Python or shell execution tools.

---

## 8. Boundary Rules (All of MVP 1)

1. **`.aieng` is optional.** `aieng_freecad_mcp` must function fully in standalone mode without any `.aieng` package.
2. **`aieng` stays CAD-agnostic.** No FreeCAD references, imports, or assumptions in the `aieng` repo.
3. **`aieng_freecad_mcp` does not own claim semantics.** It reads `claim_map.json` for guard context but never writes it during execution. Only `aieng_update_claim` (in `claims.py`) may modify claims.
4. **Execution tools never advance claims.** `claims_advanced` is always `false` in `StandardToolResult`, `TraceBlock`, and persisted trace entries.
5. **Evidence is not a claim.** Producing evidence does not change claim status.
6. **Zip and directory are interchangeable at the API level.** Callers should not need to know which format is used.

---

## 9. Test Strategy (All of MVP 1)

| Layer | FreeCAD Required | Marker | Coverage |
|---|---|---|---|
| Unit | No | default | Context loading, persistence, guards, parse, contracts |
| Integration (zip) | No | default | End-to-end patch flow with stubbed execution against `.aieng` zip |
| Integration (FreeCAD) | Yes | `freecad` | Real parametric edit, artifact export, old value capture |

**Default command:** `pytest -m "not freecad"` must pass without FreeCAD installed.
**Full command:** `pytest` runs all tests; FreeCAD-dependent tests skip gracefully if FreeCAD is absent.

---

## 10. Completion Criteria (All of MVP 1)

- [x] MVP 1A complete (see section 4.6).
- [x] MVP 1B complete (see section 5.7).
- [x] MVP 1C-A complete (see section 6.12).
- [x] MVP 1C-B1 complete (see section 6.12).
- [x] MVP 1C-B2: Real FreeCAD execution via subprocess works; marked tests pass when FreeCAD is available.
- [x] No regressions in existing standalone mode.
- [x] Boundary audit passes: zero `claim_map.json` writes outside `claims.py`; zero `claims_advanced=true` in execution path.

---

## 11. CAD/CAE Agent Runtime Confirmation Policy

This section documents the human-in-the-loop confirmation policy for agent-driven CAD/CAE operations. The policy is advisory for operators integrating the MCP server; it is not enforced in code.

### 11.1 Confirmation Levels

| Operation Category | Confirmation Required | Rationale |
|---|---|---|
| **Read-only inspection** (list documents, list objects, get parameter, inspect capabilities) | No | Read-only operations cannot mutate state or advance claims. |
| **Bounded guarded execution** (parameter edit within `.aieng` guard boundaries, explicitly requested) | No | Guards validate the edit before execution; the operation is bounded by feature graph constraints. |
| **Ambiguous CAD changes** (parameter edit with unclear target, missing feature graph, or conflicting constraints) | Yes | Ambiguity increases risk of unintended geometry mutation. |
| **Real CAD mutation** (creating new features, deleting objects, boolean operations) | Yes — bounded explicit request | Even with guards, creating or destroying geometry is a larger change than bounded parametric edits. |
| **CAE / solver execution** (meshing, solver deck export, solver run) | Yes — separate explicit request | CAE operations are computationally expensive and produce evidence that may affect claims. Each phase (CAD, mesh, solver) requires its own explicit request. |
| **Claim updates** (`aieng_update_claim`) | Yes — explicit evidence-backed request | Claim status changes are the most consequential operations; they require evidence IDs and a rationale. |

### 11.2 What "Bounded Explicit Request" Means

A bounded explicit request includes:
- **Target:** Specific feature ID or object name.
- **Parameter:** Specific parameter name (for parametric edits).
- **Value:** Specific new value, within declared constraints.
- **Scope:** Whether the operation is `dry_run`, `persist_to_aieng`, or produces artifacts.
- **Rollback plan:** How to revert if needed (e.g., re-setting the parameter to its `old_value`).

### 11.3 What "Separate Explicit Request" Means for CAE

A CAE workflow is not automatic. The agent or operator must explicitly request each phase:
1. **CAD phase:** Modify geometry (guarded parametric edit).
2. **Export phase:** Export STEP/FCStd (may be combined with CAD if requested).
3. **Mesh phase:** Generate mesh (separate tool call).
4. **Solver phase:** Run solver (separate tool call, disabled by default).
5. **Post-process phase:** Extract metrics (separate tool call).
6. **Claim phase:** Update claim status (separate tool call, requires evidence).

No tool automatically chains these phases. Orchestration is caller-driven.

### 11.4 Evidence Requirement for Claim Updates

`aieng_update_claim` requires:
- A valid `claim_id` from `claim_map.json`.
- A non-empty list of `evidence_ids` that support the requested status.
- A `rationale` string explaining why the evidence supports the claim.

Without evidence, claim updates are rejected.

### 11.5 Policy Summary

- Read freely. Edit carefully. Compute explicitly. Claim only with evidence.

---

## 12. Multi-CAD/CAE Boundary

This section clarifies the separation between the `.aieng` semantic model and CAD/CAE-specific execution adapters.

### 12.1 Principle

`.aieng` must remain **CAD/CAE-tool agnostic**. FreeCAD is one optional execution backend, not the semantic model. The `.aieng` package format, schemas, and core concepts must not assume FreeCAD or any single CAD/CAE tool.

### 12.2 What Belongs in the Adapter

FreeCAD-specific configuration and behavior belong in `aieng_freecad_mcp/`:

- `FREECAD_HOME` environment variable and path resolution.
- FCStd file handling (open, save, import, export).
- FreeCAD executable and Python module detection.
- FreeCAD object names and internal identifiers.
- FreeCAD Python snippets sent to the executor.
- FreeCAD adapter execution behavior (recompute, shape validation, etc.).

These details are opaque to `.aieng`. They may be recorded as **provenance** or **evidence metadata**, but they must not become required for interpreting `.aieng`.

### 12.3 What Belongs in `.aieng`

The `.aieng` semantic model owns generic concepts that are tool-agnostic:

- **resource** — any typed asset in the package.
- **artifact** — any generated file (STEP, mesh, solver deck, image).
- **parameter** — a named, typed, constrained value.
- **constraint** — a rule governing parameters or geometry.
- **operation** — a discrete action requested by a caller.
- **tool** — an execution boundary that performs operations.
- **adapter** — a concrete tool implementation (e.g., FreeCAD adapter).
- **evidence** — observable, reproducible output from tool execution.
- **provenance** — trace of who/what produced evidence and when.
- **reference** — a pointer to geometry, mesh, or result entities.
- **claim** — a declarative statement about design intent or verification.
- **missingness** — explicit acknowledgment that expected information is absent.
- **unsupported state** — explicit acknowledgment that a state is not handled.
- **`needs_review`** — a reference status indicating downstream recomputation may be required.

### 12.4 Adapter Extensibility

Future adapters for other CAD/CAE tools must be possible without redesigning `.aieng`:

- A new adapter introduces its own path resolution, executable detection, and execution behavior.
- It produces the same generic evidence types (`tool_result`, `parameter_change`, `artifact_produced`).
- It writes to the same `.aieng` persistence layer (evidence index, tool trace).
- It respects the same boundary rules (claim immutability, `claims_advanced: false`).

No `.aieng` schema change is required to add a new adapter.

### 12.5 Enforcement

MVP 1C must not introduce changes to `../aieng/` or `.aieng` schemas. Specifically:

- No FreeCAD-specific required fields may be added to `.aieng` resource schemas.
- FreeCAD object names may appear in `feature_graph.json` as adapter-local metadata, but must not be required for semantic interpretation.
- FreeCAD Python snippets may appear in tool trace entries as `code` metadata, but must not be required for evidence validation.
- Adapter-specific provenance keys (e.g., `freecad_version`, `freecad_path`) are allowed as optional metadata, never as required fields.

### 12.6 Examples

**Adapter-local (FreeCAD-specific):**
- `FREECAD_HOME`
- FCStd handling
- FreeCAD executable detection
- FreeCAD object names
- FreeCAD Python snippets
- FreeCAD adapter execution behavior

**Generic `.aieng` concepts:**
- `resource`, `artifact`, `parameter`
- `constraint`, `operation`, `tool`
- `adapter`, `evidence`, `provenance`
- `reference`, `claim`, `missingness`
- `unsupported state`, `needs_review`

---

## 13. Future Skill Direction (Post-MVP 1)

After MVP 1, the next product layer above `.aieng` and `aieng_freecad_mcp` is an agent-facing **CAD Copilot Skill**. This Skill would guide agent behavior for inspection, bounded proposal, and controlled execution — without becoming an execution engine itself.

See `docs/agentic-cad-cae-blueprint.md` Section 14 for the full Skill direction, including purpose, core workflows, demo/benchmark value, non-goals, and proposed repository structure.

No Skill package or source code is created yet. This is a documented product direction only.
