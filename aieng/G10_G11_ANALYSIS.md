# Deep Analysis: G10 and G11 Gates - Tool Trace & Adapter Capability Conformance

**Date:** May 12, 2026  
**Analysis Scope:** Current implementation state for G10 and G11 in rigorous interop checklist  
**Current Status:** G10 = PARTIAL | G11 = PARTIAL

---

## Executive Summary

| Gate | Definition | Current State | Gap Analysis |
|---|---|---|---|
| **G10** | Tool trace metadata minimum contract is fixed and validated for all adapters | PARTIAL | Schema defined; validator has basic semantic checks; NO adapter conformance tests |
| **G11** | Adapter capability declaration is required and tested against emitted resources | PARTIAL | Capability levels documented in prose; NO schema-based capability model; NO adapter metadata enforcement |

---

## 1. Tool Trace Schema Structure (`schemas/tool_trace.schema.json`)

### Current Schema (0.1.0)

**Required Top-Level Fields:**
```json
{
  "format_version": "0.1.0" (const),
  "tool_trace_id": string (non-empty),
  "entries": TraceEntry[] (required),
  "claim_policy": ClaimPolicy (required)
}
```

**Optional Top-Level Fields:**
- `source_task_id` (string) — links to `task/task_spec.yaml` if present
- `source_handoff_id` (string) — links to `task/external_tool_requirements.json` if present

**TraceEntry Structure:**
```json
{
  "entry_id": string (non-empty, must be unique),
  "timestamp_utc": string (non-empty, ISO format expected but not enforced),
  "tool": ToolRef (required),
  "step": StepRecord (required),
  "artifacts_recorded": string[] (array of evidence IDs),
  "claims_advanced": string[] (array of claim IDs),
  "notes": string[] (array of freeform notes)
}
```

**ToolRef Structure:**
```json
{
  "tool_id": string (non-empty, required),
  "tool_role": enum (required, values: agent_runtime, cad_runtime, cae_runtime, 
                     cae_preprocessor, solver, postprocessor, manufacturing_checker),
  "version": string (optional)
}
```

**StepRecord Structure:**
```json
{
  "name": string (non-empty, required),
  "inputs": string[] (required, may be empty),
  "outputs": string[] (required, may be empty),
  "exit_status": enum (required, values: success, failure, skipped)
}
```

**ClaimPolicy (const-guarded boundary):**
```json
{
  "external_tools_execute": true (const),
  "aieng_core_executes_external_tools": false (const)
}
```

### Key Schema Constraints

✓ **FIXED (const guards):**
- `format_version` = `"0.1.0"` 
- `claim_policy.external_tools_execute` = `true`
- `claim_policy.aieng_core_executes_external_tools` = `false`

✓ **FLEXIBLE but typed:**
- `tool_id`, `tool_role`, `version` — no adapter-specific values or capability metadata required
- No `additional_properties: false` on `ToolRef` — could accept future fields like `capability_level` or `adapter_profile`

❌ **MISSING in schema:**
- No `capability_level` field (L0-L5 per emitter contract)
- No adapter profile metadata (e.g., `adapter_name`, `adapter_version`, `adapter_conformance_profile`)
- No explicit tool version requirements or constraints
- No adapter-level semantic assertions (e.g., what resource kinds the tool produced)

---

## 2. All Adapter Implementations in `src/aieng`

### Adapters by Category

#### **Import Adapters (Content ingestion from external sources)**

| Adapter | File | Input | Output | Current Capability Level | Tool Role |
|---|---|---|---|---|---|
| **STEP Importer** | `geometry/step_importer.py` | `.step` / `.stp` files | `geometry/source.step`, `geometry/normalized.step` | L0 (artifact reference) | CAD tool (implied) |
| **CAE Deck Importer** | `simulation/cae_deck_importer.py` | `.inp` (CalculiX) | Parsed materials, BCs, loads + mapping | L3 (simulation context) | CAE tool |
| **Solver Evidence Importer** | `simulation/solver_evidence_importer.py` | `.dat` result files | Evidence record in `results/evidence_index.json` | L4 (evidence writeback) | Solver |
| **Mesh Evidence Importer** | `simulation/mesh_evidence_importer.py` | `.msh` (Gmsh) | Evidence record + quality summary | L4 (evidence writeback) | Mesher |

#### **Export/Generation Adapters (Content emission from `.aieng` to external formats)**

| Adapter | File | Input | Output | Current Capability Level | Tool Role |
|---|---|---|---|---|---|
| **CalculiX Deck Exporter** | `simulation/calculix_exporter.py` | `simulation/setup.yaml` + `feature_graph.json` | `simulation/solver_deck.inp` (scaffold) | L3 (simulation context) | CAE preprocessor |
| **Deck Updater (CalculiX)** | `simulation/deck_exporter.py` | `simulation/setup.yaml` + current state | `simulation/updated_deck.inp` | L3 (simulation context + mapping) | CAE preprocessor |

#### **Other Provenance/Metadata Adapters**

| Adapter | File | Purpose | Capability Level |
|---|---|---|---|
| **Tool Trace Recorder** | `provenance/tool_trace_writer.py` | Records external tool execution steps | L4 (evidence-aware writeback) |
| **Evidence Recorder** | `results/evidence_writer.py` | Records evidence artifacts and claim support | L4 (evidence-aware writeback) |

### Total Adapter Count
- **Import adapters:** 4
- **Export adapters:** 2
- **Provenance adapters:** 2
- **Total:** 8 adapters

---

## 3. Current Tool Trace Metadata Validation

### Validation Code Location
**File:** `src/aieng/validate.py`, function `_validate_tool_trace_semantics()` (lines 2470+)

### What IS Validated

**Required Field Checks:**
✓ `claim_policy` must be an object  
✓ `claim_policy.external_tools_execute` must be `true`  
✓ `claim_policy.aieng_core_executes_external_tools` must be `false`  
✓ `entries` must be an array  
✓ Each entry must have `entry_id` (string, non-empty)  
✓ Each entry must have `timestamp_utc`  
✓ Tool `tool_role` must be in allowed enum  
✓ Step `exit_status` must be in allowed enum  
✓ `entry_id` values must be unique (no duplicates)  

**Cross-Resource Checks:**
✓ `artifacts_recorded` IDs validated against `results/evidence_index.json` if present  
✓ Reports PASS when entry IDs are unique  

**Output:**
✓ Validator generates `ValidationMessage` objects with Level (PASS/WARN/FAIL) and text

### What IS NOT Validated

❌ **Adapter conformance:**
- No check that a specific adapter (e.g., CalculiX exporter) produced valid entries
- No tool registry or adapter catalog validation
- No capability-level conformance checks

❌ **Tool trace completeness per adapter:**
- No assertion that all adapters using tool trace have recorded their steps
- No check that adapter output matches tool trace claims
- No mapping of adapter identity to tool trace entries

❌ **Semantic conformance of tool role to adapter type:**
- `cad_runtime` and `cae_runtime` roles are allowed but there's no mapping to actual adapters
- No validation that claimed tool_role matches emitted artifact types
- No check that `cad_runtime` entry produced actual CAD artifacts

❌ **Cross-adapter consistency:**
- No validation that when multiple adapters run, their tool trace entries don't conflict
- No check for prerequisite tool runs (e.g., topology extraction before feature recognition)

❌ **Adapter-specific metadata:**
- No required adapter_name, adapter_version, or capability_level in tool trace
- No assertion about what the adapter can/cannot do

❌ **Evidence traceability per tool:**
- No check that artifacts_recorded actually exist as files in package
- No validation that claims_advanced match supported claim types
- Limited cross-check with claim_map.json

---

## 4. Adapter Capability Declarations: Current State

### Where Capability Information Currently Lives

**Documentation (prose only):**
- `docs/cad_cae_emitter_contract.md` defines 6 capability levels (L0-L5)
  - L0: Artifact reference only
  - L1: Topology-aware CAD emitter
  - L2: Feature-aware CAD emitter
  - L3: Simulation-aware CAE emitter
  - L4: Evidence-aware writeback
  - L5: Roundtrip-aware adapter

**In Code (implicit, no schema):**
- Import/export adapters have no declared capability level
- Tool trace writer has no adapter metadata fields
- No adapter registry or manifest

**Mapping Table (from analysis above):**

| Adapter | Declared Capability in Code | Actual Emitted Resources | Inferred Level |
|---|---|---|---|
| STEP Importer | None | `geometry/source.step`, `geometry/normalized.step`, manifest update | L0 |
| CAE Deck Importer | None | Parsed materials/BCs/loads JSON, CAE mapping | L3 |
| Solver Evidence Importer | None | `results/evidence_index.json`, notes | L4 |
| Mesh Evidence Importer | None | `results/evidence_index.json`, quality summary | L4 |
| CalculiX Exporter | None | `simulation/solver_deck.inp` (scaffold) | L3 |
| Deck Updater | None | `simulation/updated_deck.inp` | L3 |
| Tool Trace Recorder | None | `provenance/tool_trace.json` entry | L4 |
| Evidence Recorder | None | `results/evidence_index.json` record | L4 |

❌ **No adapter has an explicit, machine-readable capability declaration in the code**

### Why This Matters for G11

When an adapter runs, `.aieng` currently has:
1. ✓ Prose documentation of what capability levels *should* do
2. ❌ No way to validate what a specific adapter *actually* does
3. ❌ No schema to express adapter capability constraints
4. ❌ No conformance tests that check emitted resources match declared capability

**Example gap:** If an adapter declares itself as L2 (feature-aware), we have no test that asserts:
- It produces `graph/feature_graph.json`
- It does NOT produce solver results
- It properly mapped feature IDs to topology entities
- It did NOT generate mesh or run solver

---

## 5. What's Missing for G10 (PASS Criteria)

**Gate Definition:** Tool trace metadata minimum contract is fixed and validated for all adapters

**G10 PASS Criteria (inferred):**
1. ✓ Schema is fixed (DONE in tool_trace.schema.json v0.1.0)
2. ✓ Validator performs semantic checks on structure (DONE in validate.py)
3. ✓ Validator detects violations of claim_policy (DONE)
4. ❌ Validator ensures ALL adapters that record tool trace comply with schema
5. ❌ Conformance tests for each adapter's tool trace output
6. ❌ Tool registry or metadata mapping to connect adapters to their trace entries
7. ❌ Cross-resource validation: tool_trace entries vs evidence_index vs claim_map
8. ❌ Adapter identity requirement: tool trace entries must be traceable to a known adapter

### Specific Gaps

**Gap 1: No adapter conformance tests for tool trace output**
- Each adapter (STEP importer, CAE deck importer, solver evidence importer, etc.) should have tests that:
  - Verify it calls `record_trace_package()` with correct `tool_role`
  - Verify `artifacts_recorded` list matches actually written resources
  - Verify `claims_advanced` list matches supported claim types for that adapter
  - Verify entry is schema-valid

**Current Test Coverage:**
- ✓ `tests/test_tool_trace.py` has 35+ tests for the writer and validator
- ❌ No tests in `tests/test_apply_cae_mapping.py` checking tool trace output
- ❌ No tests in `tests/test_calculix_exporter.py` checking tool trace output
- ❌ No tests for solver/mesh evidence importers recording traces
- ❌ No tests that verify adapters use consistent tool IDs

**Gap 2: No adapter registry or identity binding**
- There is no machine-readable list of adapters and their expected metadata
- Example: When `tool_id="calculix"` appears in tool_trace, we cannot validate:
  - Does such an adapter exist?
  - Is its version known?
  - What capability level is it claiming?
  - What resources should it have produced?

**Gap 3: No artifact materiality checks**
- Tool trace says `artifacts_recorded: ["evidence_001", "evidence_002"]`
- Validator does NOT check that these IDs actually exist in `results/evidence_index.json` unless that resource is already present
- No check that emitted resources (e.g., `simulation/solver_deck.inp`) are mentioned in trace

**Gap 4: No cross-adapter validation**
- If adapter A (mesh generation) runs before adapter B (solver), tool trace order should be checked
- No validation that prerequisite adapters have run before dependent adapters

**Gap 5: No "adapter-level" semantic validation**
- Tool trace `claims_advanced: ["stress_distribution_computed"]` is just a string
- No schema linking claim types to valid tool roles (e.g., only `solver` role can advance `stress_*` claims)

---

## 6. What's Missing for G11 (PASS Criteria)

**Gate Definition:** Adapter capability declaration is required and tested against emitted resources

**G11 PASS Criteria (inferred):**
1. ✓ Capability levels defined in prose (L0-L5 in emitter contract)
2. ❌ Schema for adapter capability declaration (in manifest, tool trace, or separate resource)
3. ❌ Requirement that adapters declare their capability level
4. ❌ Tests that verify declared capability matches emitted resources
5. ❌ Enforcement that adapters do not exceed declared capability
6. ❌ Tests for each adapter's capability profile

### Specific Gaps

**Gap 1: No schema for adapter capability metadata**
- Current tool_trace.schema.json has no `capability_level` or `adapter_profile` field
- Adapters have no way to declare: "I am L3" or "I am L4 but I cannot do mesh quality validation"
- No schema field for adapter-specific limitations or assumptions

**Proposed structure (for G11 PASS):**
```json
{
  "tool": {
    "tool_id": "calculix_exporter",
    "tool_role": "cae_preprocessor",
    "version": "1.0.0",
    "adapter_capability_level": 3,
    "adapter_profile": "simulation_preprocessor",
    "declared_limitations": [
      "Does not validate mesh quality",
      "Does not generate mesh elements",
      "Scaffold deck only, not solver-ready"
    ]
  }
}
```

**Gap 2: No adapter profile manifest**
- No resource mapping adapter names to capability levels, versions, and constraints
- Example missing resource: `provenance/adapter_registry.json` or manifest extension

**Proposed structure:**
```json
{
  "format_version": "0.1.0",
  "adapters": [
    {
      "adapter_id": "step_importer",
      "adapter_role": "geometry_source",
      "capability_level": 0,
      "supported_formats": ["step", "stp"],
      "produces": ["geometry/source.step", "geometry/normalized.step"],
      "version": "1.0.0"
    },
    {
      "adapter_id": "cae_deck_importer",
      "adapter_role": "cae_context",
      "capability_level": 3,
      "supported_formats": ["inp"],
      "produces": ["simulation/setup.yaml", "graph/constraints.json"],
      "version": "1.0.0"
    }
  ]
}
```

**Gap 3: No conformance tests per adapter**
- Each adapter should have tests asserting:
  - **Capability match:** Produced resources match declared capability level
  - **Negative assertion:** Does NOT produce resources outside capability
  - **Metadata presence:** Records correct tool_role and adapter_id in trace
  - **Limitations respected:** Scaffold/incomplete markers present when declared

**Example tests missing:**
```python
def test_calculix_exporter_is_L3_does_not_run_solver():
    # CalculiX exporter should produce setup.yaml, not .result or mesh
    # Exported deck should have scaffold marker
    # Tool trace should have tool_role == "cae_preprocessor"
    # Should NOT claim solver_validated in claims_advanced
    pass

def test_solver_evidence_importer_is_L4_records_tool_role():
    # Should call record_trace_package with tool_role == "solver"
    # Should populate artifacts_recorded with evidence IDs
    # Should NOT claim geometry_modified
    pass
```

**Gap 4: No adapter identity tracking**
- Adapters are identified only by function name or file path, not by stable `adapter_id`
- CLI commands don't record which adapter was invoked in tool trace
- Example: `aieng export-calculix` calls CalculiX exporter but tool_trace doesn't record `adapter_id="calculix_exporter"`

**Gap 5: No capability-vs-output validation**
- After export, validator does NOT check:
  - If adapter declared L3, does NOT check that output includes only L3 resources
  - If adapter declared L4, does NOT verify evidence_index.json entries match tool trace
  - If adapter declared L2, does NOT assert that feature_graph.json is present

**Gap 6: No resource matching for capability levels**
- No test that enforces: if an adapter produces L4 resources, it must also appear in tool trace with L4 evidence

---

## 7. Recent Commits Related to Tool Trace / Adapter Metadata

### Git History (last 20 commits, filtered)

```
117de44 feat: add MCP tool_get_tool_trace and Phase 15C cross-resource 
         consistency validator
         - Added MCP endpoint for reading tool_trace
         - Cross-resource validator checks tool_trace vs evidence_index vs claim_map
         - Does NOT add adapter capability metadata

805a544 feat: add provenance tool trace
         - Implemented tool_trace_writer.py
         - Added record_trace_package() CLI command
         - Tool trace schema 0.1.0 fixed
         - Entries tracked with deterministic IDs
```

**Key observation:** Both commits focus on *structure* and *cross-resource consistency*, not on *adapter-specific capability requirements* or *adapter conformance tests*.

---

## 8. Summary: Gap Analysis for PASS Status

### G10: Tool Trace Metadata Minimum Contract (PARTIAL → PASS)

#### What's Done ✓
1. Schema is fixed at 0.1.0 with const-guarded boundary
2. Validator performs structure checks and policy validation
3. Entry uniqueness enforced
4. Cross-reference checks to evidence_index exist
5. Tool trace writer creates deterministic entries

#### What's Missing ❌
1. **Adapter conformance tests (8 critical test suites needed)**
   - Each adapter (STEP importer, CAE deck importer, solver evidence importer, mesh importer, CalculiX exporter, deck updater, evidence recorder, trace recorder) needs tests verifying:
     - Correct tool_role declaration
     - Matching artifacts_recorded list
     - Valid claims_advanced (or empty if N/A)
     - Schema compliance

2. **Adapter registry / identity requirement**
   - No machine-readable list of known adapters
   - No validation that `tool_id` values correspond to known adapters
   - No adapter_id tracking in manifest or tool trace

3. **Tool trace completeness validation**
   - No check that all adapters that should record traces actually do
   - No assertion that artifact paths in trace match resources in package
   - No validation of tool_role vs emitted resource types

4. **Cross-adapter consistency**
   - No dependency checking (e.g., topology extraction must precede feature recognition)
   - No validation of tool execution order when relevant

### G11: Adapter Capability Declaration (PARTIAL → PASS)

#### What's Done ✓
1. Capability levels L0-L5 documented in `docs/cad_cae_emitter_contract.md`
2. Mapping examples provided
3. Forbidden behaviors listed
4. Recommended minimal profiles documented

#### What's Missing ❌
1. **Schema for capability declaration (HIGH IMPACT)**
   - No JSON schema for adapter capability metadata
   - No `capability_level` field in tool_trace or manifest
   - No adapter_profile or declared_limitations resource
   - Proposed: extend tool_trace schema or add `provenance/adapter_registry.json`

2. **Adapter registry resource**
   - No machine-readable mapping of adapter → capability_level → produces/limits
   - Proposed: `provenance/adapter_registry.json` (new resource, optional)

3. **Capability conformance tests (HIGH IMPACT - 8 test suites)**
   - Each adapter needs tests asserting:
     - Produces ONLY resources matching declared L-level
     - Does NOT produce resources outside L-level
     - Correctly identifies itself in tool trace
     - Correctly declares limitations / unsupported features
   - Example: CalculiX exporter (L3) should NOT produce solver results (L4)

4. **Adapter identity in CLI**
   - CLI commands (e.g., `aieng export-calculix`) should record adapter identity
   - Tool trace entries should include stable adapter_id

5. **Validator enforcement**
   - Validator should check that emitted resources match declared capability level
   - Should FAIL if adapter produces L4 resources but declares L3
   - Should WARN if adapter declares L5 but only produces L3

6. **Documentation of adapter profiles per adapter**
   - Each adapter needs documented profile: what it can/cannot do
   - Example: CalculiX exporter is "simulation_preprocessor, L3, cannot validate mesh quality, scaffold output only"

---

## 9. Roadmap: From PARTIAL to PASS

### For G10 (Tool Trace Metadata Validation)

**Phase 1: Adapter conformance test suite (2-3 days)**
- [ ] Add test module `tests/test_adapter_tool_trace_conformance.py`
- [ ] Implement tests for each of 8 adapters:
  - [ ] STEP importer tool_trace output test
  - [ ] CAE deck importer tool_trace output test
  - [ ] Solver evidence importer tool_trace output test
  - [ ] Mesh evidence importer tool_trace output test
  - [ ] CalculiX exporter tool_trace output test
  - [ ] Deck updater tool_trace output test
  - [ ] Evidence recorder tool_trace output test
  - [ ] Tool trace recorder self-test
- [ ] Each test verifies: tool_role, artifacts_recorded, claims_advanced, schema compliance

**Phase 2: Adapter registry / identity (1-2 days)**
- [ ] Create adapter identity constants in each adapter module
- [ ] Add adapter_id to tool_trace entries (optional field in schema)
- [ ] Validator checks adapter_id against known registry

**Phase 3: Enhanced validator (1-2 days)**
- [ ] Add `_validate_adapter_conformance()` function
- [ ] Check artifacts_recorded exist in package or evidence_index
- [ ] Check tool_role matches expected adapter types
- [ ] Cross-check tool_trace vs feature/constraint/simulation setup resources

### For G11 (Adapter Capability Declaration)

**Phase 1: Capability metadata schema (2-3 days)**
- [ ] Extend `tool_trace.schema.json` with optional capability fields OR
- [ ] Create new `provenance/adapter_manifest.schema.json` or add to manifest.json
- [ ] Fields: adapter_id, adapter_capability_level (0-5), declared_limitations, declared_resources

**Phase 2: Adapter profile per adapter (3-4 days)**
- [ ] Document each adapter's profile in docstring
- [ ] Assign official capability level per adapter
- [ ] List limitations and unsupported features
- [ ] Map to emitted resource types

**Phase 3: Capability conformance tests (3-4 days)**
- [ ] Add test module `tests/test_adapter_capability_declaration.py`
- [ ] For each adapter, test:
  - [ ] Declared capability level matches emitted resources
  - [ ] Does not produce resources outside capability
  - [ ] Limitations are correctly represented (e.g., scaffold markers)
  - [ ] Tool trace declares correct capability_level field

**Phase 4: Validator capability enforcement (2-3 days)**
- [ ] Add `_validate_adapter_capability_conformance()` function
- [ ] FAIL if produced resources exceed declared capability
- [ ] WARN if declared capability not fully exercised
- [ ] Cross-check manifest adapter registry vs tool_trace entries

---

## 10. Conclusion: Recommended Action for Reaching PASS

### G10 Path to PASS (Medium Effort)
1. Create comprehensive adapter conformance test suite (validate tool_trace output per adapter)
2. Add adapter identity / registry validation to validator
3. Enhance tool_trace validator with artifact existence checks

**Estimated effort:** 4-7 days  
**Risk:** Low (tests mostly combinatorial, no schema changes needed)

### G11 Path to PASS (Higher Effort)
1. Define and implement capability metadata schema (extend tool_trace or add new resource)
2. Assign official capability levels to all 8 adapters with documented limitations
3. Create comprehensive capability conformance test suite
4. Enhance validator to check capability-vs-resources mismatch

**Estimated effort:** 8-14 days  
**Risk:** Medium (requires schema extension, may affect existing tool_trace instances)

### Combined G10+G11 Path to PASS (Recommended)
- **Do G10 first** (tool trace validation) — lower risk, enables testing framework
- **Then G11** (capability declaration) — builds on G10 infrastructure
- **Sequential effort:** ~12-21 days total
- **Parallel effort (if both tracked as issues):** ~10-15 days with proper task breakdown

### Proposed Acceptance Criteria for PASS

**G10 PASS:**
- [ ] All 8 adapters have passing conformance tests in CI
- [ ] Validator catches tool_trace entry violations
- [ ] Artifact traceability tests pass (artifacts_recorded exist)
- [ ] No adapter can bypass tool_trace recording without CI failure

**G11 PASS:**
- [ ] All adapters have declared capability level (0-5) in metadata
- [ ] Capability conformance tests pass for all adapters
- [ ] Validator enforces: produced resources ≤ declared capability level
- [ ] Tool_trace entries include adapter_capability_level field
- [ ] Documentation (docstring) per adapter specifies: name, role, L-level, limitations

---

## Appendix A: Adapter Implementation Reference

```
STEP Importer
├── File: src/aieng/geometry/step_importer.py
├── Function: import_step_package()
├── Reads: .step/.stp files from filesystem
├── Writes: geometry/source.step, geometry/normalized.step
├── Tool role: CAD runtime (implied)
├── Capability: L0 (artifact reference only)
└── Tool trace: NOT CURRENTLY RECORDED (gap)

CAE Deck Importer
├── File: src/aieng/simulation/cae_deck_importer.py
├── Function: import_cae_deck_package()
├── Reads: .inp (CalculiX) from filesystem
├── Writes: simulation/cae_imports/*, simulation/cae_mapping.json
├── Tool role: CAE preprocessor
├── Capability: L3 (simulation context)
└── Tool trace: NOT CURRENTLY RECORDED (gap)

Solver Evidence Importer
├── File: src/aieng/simulation/solver_evidence_importer.py
├── Function: import_solver_evidence_package()
├── Reads: .dat (solver result) from filesystem
├── Writes: results/evidence_index.json, results/claim_map.json (via evidence_writer)
├── Tool role: Solver (external)
├── Capability: L4 (evidence writeback)
└── Tool trace: RECORDS via record_evidence_package()

Mesh Evidence Importer
├── File: src/aieng/simulation/mesh_evidence_importer.py
├── Function: import_mesh_evidence_package()
├── Reads: .msh (Gmsh) from filesystem
├── Writes: results/evidence_index.json (via evidence_writer)
├── Tool role: CAE preprocessor (mesh generator)
├── Capability: L4 (evidence writeback)
└── Tool trace: RECORDS via record_evidence_package()

CalculiX Exporter
├── File: src/aieng/simulation/calculix_exporter.py
├── Function: export_calculix_package()
├── Reads: simulation/setup.yaml, feature_graph.json, protected_regions.json
├── Writes: simulation/solver_deck.inp (inside package + optional external)
├── Tool role: CAE preprocessor
├── Capability: L3 (simulation context, scaffold only)
└── Tool trace: NOT CURRENTLY RECORDED (gap)

Deck Updater (CalculiX)
├── File: src/aieng/simulation/deck_exporter.py
├── Function: export_updated_deck_package()
├── Reads: simulation/setup.yaml, simulation/cae_mapping.json
├── Writes: simulation/updated_deck.inp
├── Tool role: CAE preprocessor
├── Capability: L3+ (simulation context with current state)
└── Tool trace: NOT CURRENTLY RECORDED (gap)

Tool Trace Recorder (Provenance)
├── File: src/aieng/provenance/tool_trace_writer.py
├── Function: record_trace_package()
├── Reads: package metadata, existing tool_trace.json if present
├── Writes: provenance/tool_trace.json (append-only)
├── Tool role: Agent runtime (implied)
├── Capability: L4 (evidence/provenance recording)
└── Tool trace: Self-referential; records its own entry

Evidence Recorder (Provenance)
├── File: src/aieng/results/evidence_writer.py
├── Function: record_evidence_package()
├── Reads: package, evidence artifact references
├── Writes: results/evidence_index.json, results/claim_map.json
├── Tool role: Agent runtime (implied)
├── Capability: L4 (evidence writeback)
└── Tool trace: INTEGRATION with tool_trace_writer via record_trace_package()
```

---

## Appendix B: Cross-Reference Matrix

| Adapter | Records Tool Trace? | Has Conformance Tests? | Has Capability Declaration? | Capability Level |
|---|---|---|---|---|
| STEP Importer | ❌ NO | ❌ NO | ❌ NO | L0 (inferred) |
| CAE Deck Importer | ❌ NO | ❌ NO | ❌ NO | L3 (inferred) |
| Solver Evidence Importer | ✓ YES (via evidence_writer) | ⚠️ PARTIAL | ❌ NO | L4 (inferred) |
| Mesh Evidence Importer | ✓ YES (via evidence_writer) | ⚠️ PARTIAL | ❌ NO | L4 (inferred) |
| CalculiX Exporter | ❌ NO | ❌ NO | ❌ NO | L3 (inferred) |
| Deck Updater | ❌ NO | ❌ NO | ❌ NO | L3 (inferred) |
| Tool Trace Recorder | ✓ YES (self) | ✓ YES | ⚠️ IMPLIED | L4 (documented) |
| Evidence Recorder | ✓ YES (via integration) | ✓ PARTIAL | ⚠️ IMPLIED | L4 (documented) |

---

**End of G10/G11 Deep Analysis**
