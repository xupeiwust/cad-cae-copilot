# Architecture

## Overview

```text
AI agent/caller
  -> MCP tool call
FreeCAD MCP server
  -> schema/path validation
  -> controlled execution
  -> structured result
FreeCAD / FEM / solver (optional runtime)
  -> artifacts + logs + deterministic observations
.aieng adapter (optional)
  -> evidence_index.json
  -> tool_trace.json
  -> claim_map.json (explicit update only)
```

## Module Layout

```text
src/freecad_mcp/
  server.py
  config.py
  tool_contracts.py
  contracts.py
  bridge/
  cae_core/
  tools_cad/
  tools_cae/
  tools_aieng/
  aieng_bridge/
```

Key `.aieng` bridge modules: context, guards, persistence, patch, postprocessing, claims, references, audit, planner.

## Standard Execution Flow

1. Receive tool call.
2. Validate schema and safe paths.
3. Run approved operation in controlled workspace.
4. Capture artifacts/logs/exit details.
5. Extract deterministic observations.
6. Optionally persist evidence and trace.
7. Return structured result with explicit claim policy.

## Core Workflow Components

### Patch Bridge (`aieng_execute_patch`)

1. Load patch (`patch_json`, `patch_path`, or package `patch.json`).
2. Parse supported/unsupported operations.
3. Resolve targets, run guards, execute step-by-step, stop on first failure.
4. Optionally export modified STEP/FCStd.
5. Optionally persist evidence/trace/patch run record.

### Optional CAD->CAE Orchestration (`aieng_run_cad_to_cae_workflow`)

This helper is optional and explicit.

- CAD and CAE remain independent first-class workflows.
- Not default after patch execution.
- Does not auto-advance claims.
- Conservative defaults: `run_solver=False`, `run_postprocess=False`, `engineering_validation=false`, `claims_advanced=false`.

### Post-Processing (`aieng_postprocess_results`)

- Extract deterministic metrics.
- Export CSV (and VTK only when field data exists).
- Persist evidence/trace when requested.
- Improves readability; does not validate claims.

### Claim Update (`aieng_update_claim`)

Only this path may modify `claim_map.json`.

- Validates claim/evidence/criteria inputs.
- Supports deterministic evaluate mode and explicit manual mode.
- Supports dry-run without writes.

### Reference Mapping and Audit

- `aieng_build_reference_map` and `aieng_mark_references_needing_review` manage traceability metadata.
- `aieng_generate_audit_report` summarizes evidence/trace/reference/claim discipline and writes reports only.

## Composable Paths (v1.0)

1. CAD-only
2. CAE-only
3. Optional explicit CAD->CAE
4. Reference mapping
5. Explicit claim update

These paths are composable, not automatic. The agent/caller controls ordering.

## Runtime and Test Modes

- Mock mode validates logic without requiring FreeCAD.
- Real FreeCAD/FEM/solver paths are optional and use skip-based tests when runtime is unavailable.

## Package Write Policy

Allowed writes: generated artifacts, evidence/trace files, patch run records, completeness resources, and explicit claim updates.

Disallowed default writes: in-place source mutation, hidden claim/status changes, or writes outside package/job boundaries.
