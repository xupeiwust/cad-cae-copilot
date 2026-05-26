# MCP runtime bridge tools

These MCP tools delegate to the aieng-ui runtime REST API.  They do not
duplicate FreeCAD or package logic — all execution happens inside the
aieng-ui backend.

## Architecture

```
MCP client (Claude Code / Codex / any MCP client)
    │
    ▼
freecad-mcp server  (this repo)
  └── tools_runtime/  ← thin HTTP wrappers
              │
              │  REST  (AIENG_RUNTIME_BASE_URL)
              ▼
        aieng-ui backend  (port 8000 by default)
              │
              ├── freecad.inspect_geometry → FreeCADCmd subprocess
              ├── freecad.export_step      → FreeCADCmd subprocess
              ├── freecad.run_macro        → (approval-gated)
              └── aieng.*                  → package tools
```

## Setup

```bash
# 1. Start aieng-ui backend
cd path/to/aieng-ui && uvicorn app.main:app --port 8000

# 2. Start MCP server with runtime bridge enabled
AIENG_RUNTIME_BASE_URL=http://localhost:8000 freecad-mcp
```

### Claude Code / Codex configuration

`.claude/mcp.json`:
```json
{
  "mcpServers": {
    "aieng": {
      "command": "freecad-mcp",
      "env": {
        "AIENG_RUNTIME_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

HTTP transport (if running server separately):
```json
{
  "mcpServers": {
    "aieng": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Tools

### `aieng_list_runtime_tools`

Lists all tools registered in the aieng-ui runtime.

**Input:** none

**Returns:**
```json
{"status": "ok", "tools": [...], "count": 7}
```

---

### `aieng_start_runtime_run`

Starts a runtime run with a natural-language message and returns immediately.

**Input:**
| Field | Type | Description |
|---|---|---|
| `message` | string | Natural-language instruction routed by the runtime planner |
| `project_id` | string (optional) | Project ID for file path resolution |

**Returns:** full run record (may be in any status including `running`)

**Note:** For a synchronous experience use `aieng_inspect_geometry` or
`aieng_export_step` which wait automatically.

---

### `aieng_get_runtime_run`

Fetches a run record by ID.

**Input:**
| Field | Type | Description |
|---|---|---|
| `run_id` | string | Run ID from a previous `aieng_start_runtime_run` call |

---

### `aieng_inspect_geometry`

Inspects CAD geometry via the aieng-ui runtime.  Waits up to 120 s for
completion and returns the full run record.

FreeCAD execution happens inside the runtime backend — this tool does NOT
invoke FreeCAD directly.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project whose `metadata.json → source_step` provides the input file |

**Returns:** run record including `tool_results[0].output` with:
- `total_face_count`, `total_edge_count`, `total_vertex_count`
- `total_volume_mm3`, `total_area_mm2`
- `bounding_box` (xmin/xmax/ymin/ymax/zmin/zmax/xlen/ylen/zlen)
- `objects` list with per-object geometry

**Approval:** If the run unexpectedly reaches `awaiting_approval`, the
record is returned as-is without auto-approving.

---

### `aieng_export_step`

Exports CAD geometry to STEP format via the aieng-ui runtime.  Waits up to
120 s and returns the full run record including artifact metadata.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project for source file resolution |
| `output_path` | string (optional) | Desired STEP output path (see limitation below) |

**Returns:** run record including `tool_results[0].artifacts`:
```json
[{"path": "/path/to/part_export.step", "kind": "step", "role": "primary_geometry"}]
```

**Limitation:** `output_path` is accepted for forward compatibility but is
not yet forwarded to the runtime API.  The runtime auto-generates
`{stem}_export.step` alongside the source file.

---

### `aieng_approve_runtime_run`

Approves an `awaiting_approval` run and resumes execution.

**Input:**
| Field | Type | Description |
|---|---|---|
| `run_id` | string | Run ID |

**Note:** Review the pending step via `aieng_get_runtime_run` before approving.
Currently only `freecad.run_macro` requires approval.

---

### `aieng_reject_runtime_run`

Rejects an `awaiting_approval` run without executing the pending tool.

**Input:**
| Field | Type | Description |
|---|---|---|
| `run_id` | string | Run ID |

---

### `aieng_get_cae_status`

Returns honest CAE artifact presence for a project. Reports which CAE files
exist inside the `.aieng` package, but does NOT run a solver or synthesize
results.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID to inspect |

**Returns:**
```json
{
  "mode": "cae_setup",
  "artifacts": {"simulation/mesh/model.vtu": true, ...},
  "has_cae_setup": true,
  "has_mesh": true,
  "has_results": false,
  "has_fields": false,
  "has_validation": false,
  "detected_count": 5,
  "total_count": 15
}
```

---

### `aieng_get_cae_result_summary`

Returns a CAE/post-processing result summary for a project. This is a thin
wrapper over the aieng-ui runtime endpoint. The summary is generated from
detected artifact presence only; it does **not** run a solver, parse VTU/FRD
numerical fields, or synthesize extrema.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID to inspect |

**Returns:**
```json
{
  "schema_version": "0.1",
  "summary_type": "cae_postprocessing",
  "status": {
    "mode": "cae_result",
    "has_cae_setup": true,
    "has_mesh": true,
    "has_results": true,
    "has_fields": true,
    "has_validation": false,
    "solved": null,
    "converged": null,
    "warnings": []
  },
  "computed_values": {
    "extrema_computed": false,
    "max_displacement": null,
    "max_von_mises_stress": null,
    "minimum_safety_factor": null
  },
  "llm_summary": {
    "one_line": "CAE result artifacts detected...",
    "key_findings": [...],
    "risks": [...],
    "recommended_next_actions": [...],
    "limitations": ["This summary is based on artifact presence only..."]
  }
}
```

**Honest limitations:**
- `computed_values.extrema_computed` is always `false` in this version.
- No VTU/FRD/ODB numerical parsing is performed.
- No solver execution occurs.

---

### `aieng_get_cae_preprocessing_summary`

Returns the CAE pre-processing readiness summary for a project. Reports which
setup artifacts exist in the `.aieng` package and whether the package is ready
for solver execution. Read-only; no solver is executed and no mesh is generated.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID to inspect |

**Returns:**
```json
{
  "schema_version": "0.1",
  "status": {
    "has_cae_setup": true,
    "has_materials": true,
    "has_loads": true,
    "has_boundary_conditions": true,
    "has_constraints": false,
    "has_mesh": true,
    "has_load_cases": true,
    "has_solver_settings": true,
    "has_cae_mapping": false,
    "ready_for_solver": true,
    "missing_items": ["cae_mapping"]
  },
  "llm_summary": {
    "one_line": "Pre-processing setup is ready...",
    "key_findings": [...],
    "recommended_next_actions": [...],
    "limitations": ["Readiness is artifact-based only..."]
  }
}
```

**Honest limitations:**
- Readiness is based on artifact presence only; no physical correctness check.
- No solver execution. No mesh generation.

---

### `aieng_get_cae_simulation_run_summary`

Returns the simulation run metadata summary for a project. Reports the number
of runs found in the `.aieng` package, the latest run state, solver software,
and any recorded warnings or errors. Read-only; no solver is executed and no
VTU/FRD numerical fields are parsed.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID to inspect |

**Returns:**
```json
{
  "schema_version": "0.1",
  "status": {
    "has_simulation_runs": true,
    "run_count": 1,
    "latest_run_id": "run_001",
    "has_completed_run": true,
    "has_converged_run": true,
    "has_failed_run": false
  },
  "runs": [
    {
      "run_id": "run_001",
      "solver": "CalculiX",
      "software": "FreeCAD FEM / CalculiX",
      "state": "completed",
      "solved": true,
      "converged": true,
      "warnings": [],
      "errors": []
    }
  ],
  "llm_summary": {
    "one_line": "1 simulation run found...",
    "key_findings": [...],
    "limitations": ["Summary is metadata-based only..."]
  }
}
```

**Honest limitations:**
- Summary is metadata-based only; no VTU/FRD/ODB numerical parsing.
- No solver execution.

---

### `aieng_generate_computed_metrics`

Normalize external post-processing metrics into `results/computed_metrics.json`.

Starts a runtime run with the message "generate computed metrics" and passes
structured parameters via `tool_input`. The runtime routes this to
`postprocess.generate_computed_metrics`, which calls the exporter in
`aieng_freecad_mcp`. No solver is executed. No VTU/FRD/ODB fields are parsed.

**Input:**
| Field | Type | Description |
|---|---|---|
| `input_path` | string (required) | Path to raw metrics file (JSON or CSV) |
| `output_path` | string (optional) | Destination for `computed_metrics.json` |
| `project_id` | string (optional) | Project ID for auto output-path resolution |
| `load_case_id` | string (optional) | Load case identifier (default: `load_case_001`) |
| `software` | string (optional) | Name of software that produced the metrics |
| `source_files` | list[string] (optional) | Original solver result file paths |

**Returns:**
```json
{
  "status": "completed",
  "tool_results": [
    {
      "status": "success",
      "output": {
        "status": "ok",
        "output_path": ".../results/computed_metrics.json",
        "metrics_count": 3,
        "artifacts": [
          {
            "path": ".../results/computed_metrics.json",
            "kind": "computed_metrics",
            "role": "external_postprocessing_metrics"
          }
        ]
      }
    }
  ]
}
```

**Honest limitations:**
- The input file must already contain scalar metrics; no solver is run.
- Only flat JSON and CSV inputs are supported in this phase.
- Unknown metric keys are skipped with a warning.

---

### `aieng_refresh_cae_summary`

Regenerate CAE result summary, evidence index, and markdown artifacts inside
a `.aieng` package after external metrics have been imported.

Starts a runtime run with the message "refresh cae summary". The runtime
routes this to `postprocess.refresh_cae_summary`, which calls
`aieng.cae_result_summary.write_cae_result_summary_package` via the
`aieng-ui` bridge. No solver is executed. No VTU/FRD/ODB numerical
fields are parsed; the refresh reads only artifact presence and the
`computed_metrics.json` already present in the package.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for package resolution |
| `package_path` | string (optional) | Direct path to `.aieng` package |
| `overwrite` | boolean (optional) | Overwrite existing summary files (default: `true`) |

**Returns:** runtime run record. On success, `tool_results[0].output`
contains `status`, `package_path`, `schema_version`, and an `artifacts`
list with entries for `results/result_summary.json`,
`results/evidence_index.json`, and `results/postprocessing_summary.md`.
A `warnings` field is appended when the regenerated summary's
`schema_version` does not match the constant in
`aieng/src/aieng/schema_versions.py`.

**Honest limitations:**
- No solver execution.
- No numerical field parsing (VTU/FRD/ODB).
- The summary reflects what is in the package at refresh time; it does
  not synthesize missing artifacts.

---

### `aieng_apply_cae_setup_patch`

Apply a controlled patch to CAE setup artifacts inside a `.aieng` package.

Starts a runtime run with the message "apply cae setup patch". All patches are
validated before any write; the package is rewritten atomically. Rejected writes
return `status: "error"` with a specific `code`.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for package resolution |
| `package_path` | string (optional) | Direct path to `.aieng` package |
| `patches` | list[object] (required) | List of patch operations (see below) |
| `refresh_preprocessing_summary` | boolean (optional) | Refresh preprocessing summary after patching (default: `true`) |

**Patch object:**
| Field | Type | Description |
|---|---|---|
| `path` | string | Artifact path inside the package (must be an allowed setup path) |
| `action_type` | string | One of: `create_file`, `replace_json`, `merge_object`, `append_array_item` |
| `pointer` | string (optional) | JSON Pointer (RFC 6901) for targeted field ops |
| `before` | any (optional) | Expected current value guard for `replace_json` |
| `value` | any | New value or content |
| `content` | any | File content for `create_file` |

**Allowed write targets:** `simulation/cae_imports/`, `simulation/load_cases/`,
`simulation/solver_settings.json`, `simulation/cae_mapping.json`,
`graph/constraints.json`. All other paths (including `results/`) are rejected.

**Returns:**
```json
{
  "status": "ok",
  "changed_artifacts": [{"path": "...", "kind": "cae_setup_patch", "role": "patched_setup_artifact"}],
  "refreshed_artifacts": [...],
  "stale_artifacts": ["results/result_summary.json", "results/evidence_index.json", ...],
  "warnings": []
}
```

**Honest limitations:**
- No solver execution; no mesh generation.
- Path traversal, absolute paths, and `results/` writes are rejected.
- `claims_advanced=true` is not supported.

---

### `aieng_generate_solver_input`

Generate a runnable CalculiX solver input deck from a `.aieng` package.

Delegates to the aieng-ui runtime tool `cae.generate_solver_input`. Assembles a
runnable `.inp` deck by combining mesh from an existing imported source deck
(`source_solver_deck.inp`) with current materials, boundary conditions, loads,
and step configuration from the package's setup artifacts.

**This tool does NOT execute a solver or generate a mesh.** All generation logic
lives inside `aieng`; this is a thin runtime wrapper.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for automatic package resolution |
| `run_id` | string (optional) | Run identifier for output path (default: `"run_001"`) |
| `overwrite` | boolean (optional) | Overwrite an existing solver input deck (default: `true`) |

**Returns:**
```json
{
  "ok": true,
  "tool": "cae.generate_solver_input",
  "status": "completed",
  "out_path": "simulation/runs/run_001/solver_input.inp",
  "missing_items": [],
  "warnings": []
}
```

**Honest limitations:**
- The `.aieng` package must already contain an imported source deck with mesh.
- No mesh generation is performed; only setup artifacts are merged into the deck.
- Material names are auto-corrected to match `*SOLID SECTION` references with an explicit warning.
- Physical correctness of the generated deck is not checked.

---

### `aieng_extract_field_regions`

Extract high-magnitude spatial clusters from a CalculiX FRD result file.

Delegates to the aieng-ui runtime tool `cae.extract_field_regions`. Parses
per-node DISP or S fields, computes a scalar metric per node (von Mises stress
or displacement magnitude), thresholds nodes above a percentile cutoff, and
groups the remaining nodes into spatial clusters using distance-based connected
components.

Writes `results/field_regions.json` into the `.aieng` package with cluster
centroid, peak magnitude, and node count per cluster.

**This tool does NOT reimplement field parsing or clustering.** All computation
happens inside the aieng-ui backend.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for package resolution |
| `frd_path` | string (required) | Absolute path to the CalculiX `.frd` result file |
| `field` | string (optional) | FRD field name to analyse (`"S"` or `"DISP"`; default: `"S"`) |
| `metric` | string (optional) | Metric per node (`"von_mises"` or `"magnitude"`; default: `"von_mises"`) |
| `max_clusters` | integer (optional) | Maximum number of clusters to return (default: `3`) |
| `threshold_percentile` | float (optional) | Percentile cutoff (0–100; default: `90.0`) |
| `overwrite` | boolean (optional) | Overwrite existing `field_regions.json` (default: `true`) |
| `refresh_field_summary` | boolean (optional) | Refresh `results/field_summary.json` and `.md` after extraction (default: `true`) |

**Returns:**
```json
{
  "ok": true,
  "tool": "cae.extract_field_regions",
  "status": "completed",
  "cluster_count": 2,
  "clusters": [
    {
      "id": "cluster_001",
      "location": {"x": 10.05, "y": 0.0, "z": 0.0},
      "magnitude": {"value": 240.0, "unit": "MPa"},
      "node_count": 5,
      "feature_ref": null
    }
  ],
  "warnings": [],
  "artifacts": [{"path": "results/field_regions.json", "kind": "field_regions", "role": "high_magnitude_spatial_clusters"}]
}
```

**Honest limitations:**
- Spatial clustering uses node coordinates from the FRD mesh section; if coordinates are missing, extraction fails.
- Clusters are magnitude-based spatial bins, not rigorously connected components — this is an intentional MVP trade-off to avoid the 200MB+ VTK dependency.
- Only CalculiX text FRD is supported; binary FRD and VTU/ODB are not.
- No solver execution; the `.frd` file must already exist.

---

### `aieng_edit_cad_parameter`

Request an approval-gated edit to one declared CAD feature parameter.

Delegates to the aieng-ui runtime tool `cad.edit_parameter`. The runtime
validates that the feature exists, the parameter is declared editable, and the
new value is within declared bounds before invoking the FreeCAD bridge and
atomically writing any exported STEP artifact back into the `.aieng` package.

**This wrapper never auto-approves the mutation.** It returns the
`awaiting_approval` run record so the caller can inspect the pending step and
then call `aieng_approve_runtime_run` explicitly.

**Input:**
| Field | Type | Description |
|---|---|---|
| `feature_id` | string (required) | Stable feature ID from `graph/feature_graph.json` |
| `parameter_name` | string (required) | Declared editable parameter name |
| `new_value` | number/string (required) | Proposed replacement value |
| `project_id` | string (optional) | Project ID for package resolution |
| `package_path` | string (optional) | Explicit path to the `.aieng` package |
| `input_fcstd` | string (optional) | Source `.FCStd` path for the FreeCAD bridge |

**Returns:**
```json
{
  "run_id": "run_abc123",
  "status": "awaiting_approval",
  "pending_step_index": 0
}
```

**Honest limitations:**
- No topology-changing edits are allowed by this contract.
- No remeshing or solver execution is performed.
- Physical correctness is not claimed; downstream geometry, mesh, and result artifacts are marked stale by the runtime.

---

### `aieng_extract_solver_results`

Parse a CalculiX FRD result file and write `results/computed_metrics.json`
(max displacement, max von Mises stress) into a `.aieng` package.

Extracts real per-node numerical field data — this is the first tool that
produces `extrema_computed: true` in the CAE result summary without requiring
a manually prepared CSV/JSON input file.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for package resolution |
| `frd_path` | string (required) | Absolute path to the CalculiX `.frd` result file |
| `load_case_id` | string (optional) | Load case identifier (default: `load_case_001`) |
| `software` | string (optional) | Solver software name (default: `"CalculiX"`) |
| `overwrite` | boolean (optional) | Overwrite existing `computed_metrics.json` (default: `true`) |
| `refresh_result_summary` | boolean (optional) | Refresh CAE result summary after extraction (default: `true`) |

**Returns:**
```json
{
  "status": "ok",
  "package_path": "...",
  "metrics": {
    "schema_version": "0.1",
    "metrics_source": {"tool": "frd_parser_v1", "software": "CalculiX", "source_files": ["job.frd"]},
    "load_cases": [
      {
        "id": "load_case_001",
        "metrics": {
          "max_displacement": {"value": 0.82, "unit": "mm"},
          "max_von_mises_stress": {"value": 187.4, "unit": "MPa"}
        }
      }
    ],
    "warnings": []
  },
  "artifacts": [{"path": "results/computed_metrics.json", "kind": "computed_metrics", "role": "frd_extracted_postprocessing_metrics"}]
}
```

**Honest limitations:**
- Only DISP and S (stress tensor) fields are processed; other CalculiX fields are not yet extracted.
- Binary FRD format is not supported; file must be UTF-8 text (default CalculiX output).
- VTU/ODB format parsing is not implemented.
- No solver execution; the `.frd` file must already exist.

---

### `aieng_prepare_solver_run`

Return a reviewable solver run preflight plan for a `.aieng` project.

Delegates to the aieng-ui runtime tool `cae.prepare_solver_run`. Inspects
the `.aieng` package for required solver artifacts and checks whether a
`ccx` executable is on the server PATH — **without running it**.

**This tool performs no solver execution, generates no mesh, runs no
subprocess, and modifies no files.**  The runtime always returns
`requires_approval: true` and `solver_execution_performed: false`.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for automatic package resolution |
| `run_id` | string (optional) | Planned run identifier (default: `"run_001"`) |
| `solver` | string (optional) | Solver name in the report (default: `"CalculiX"`) |
| `load_case_id` | string (optional) | Load case to check for (default: `"load_case_001"`) |
| `input_deck_path` | string (optional) | Explicit path to a `.inp` deck on the server; if empty checks inside package |
| `extract_results` | boolean (optional) | Include `computed_metrics.json` in `planned_artifacts` (default: `true`) |
| `refresh_summary` | boolean (optional) | Include result summary artifacts in `planned_artifacts` (default: `true`) |

**Returns:**
```json
{
  "ok": true,
  "tool": "cae.prepare_solver_run",
  "ready_to_run": false,
  "solver": "CalculiX",
  "run_id": "run_001",
  "load_case_id": "load_case_001",
  "requires_approval": true,
  "solver_execution_performed": false,
  "preflight": {
    "has_mesh": true,
    "has_solver_settings": true,
    "has_load_case": true,
    "has_input_deck": false,
    "ccx_available": false,
    "missing_items": ["simulation/runs/run_001/solver_input.inp", "CalculiX executable (ccx) not found on PATH"]
  },
  "planned_artifacts": [
    {"path": "simulation/runs/run_001/solver_run.json", "kind": "solver_run_record", "role": "run_metadata"},
    {"path": "simulation/runs/run_001/solver_log.txt", "kind": "solver_log", "role": "solver_stdout"},
    {"path": "simulation/runs/run_001/outputs/result.frd", "kind": "frd_result", "role": "primary_result"},
    {"path": "results/computed_metrics.json", "kind": "computed_metrics", "role": "extracted_metrics"},
    {"path": "results/result_summary.json", "kind": "result_summary", "role": "postprocessing_summary"},
    {"path": "results/evidence_index.json", "kind": "evidence_index", "role": "evidence_index"},
    {"path": "results/postprocessing_summary.md", "kind": "markdown_report", "role": "human_readable_summary"}
  ],
  "warnings": [
    "No solver execution was performed.",
    "This is a preflight plan only. Solver execution requires external CalculiX setup.",
    "Run is not ready: 2 item(s) missing."
  ]
}
```

**Honest limitations:**
- No solver execution; no mesh generation; no input deck generation.
- `ccx_available` reflects `shutil.which` only — the executable is never invoked.
- `ready_to_run: true` requires all four artifacts AND `ccx` on the server PATH; in practice this will be `false` on most development machines.
- Physical correctness of the planned run is not checked or guaranteed.

---

### `aieng_run_solver`

Execute an external CalculiX solver run on an existing input deck.

Delegates to the aieng-ui runtime tool `cae.run_solver`. The runtime copies the `.inp` into a temp directory, runs `ccx` with a timeout, captures stdout/stderr, and writes `solver_run.json`, `solver_log.txt`, and `result.frd` back into the `.aieng` package.

**This tool does NOT run a solver inside the MCP server.** All solver execution happens inside the aieng-ui backend. Because solver execution is potentially destructive, the runtime gates this tool with `requires_approval=true`. The MCP tool returns the `awaiting_approval` run record without auto-approving. Use `aieng_approve_runtime_run` after reviewing the pending step.

**Input:**
| Field | Type | Description |
|---|---|---|
| `project_id` | string (optional) | Project ID for automatic package resolution |
| `run_id` | string (optional) | Run identifier (default: `"run_001"`) |
| `solver` | string (optional) | Solver name for metadata (default: `"CalculiX"`) |
| `input_deck_path` | string (optional) | Path to `.inp` deck inside the package |
| `extract_results` | boolean (optional) | Extract FRD scalar results after run (default: `true`) |
| `refresh_summary` | boolean (optional) | Refresh CAE summaries after run (default: `true`) |
| `overwrite` | boolean (optional) | Overwrite existing run artifacts (default: `true`) |
| `timeout_seconds` | integer (optional) | Subprocess timeout in seconds (default: `120`) |

**Returns:** run record (may be `awaiting_approval` if the approval gate is active)

When the run completes after approval, `tool_results[0].output` contains:
```json
{
  "ok": true,
  "tool": "cae.run_solver",
  "status": "completed",
  "solver_execution_performed": true,
  "return_code": 0,
  "changed_artifacts": [
    {"path": "simulation/runs/run_001/solver_input.inp", "kind": "solver_input", "role": "artifact"},
    {"path": "simulation/runs/run_001/solver_log.txt", "kind": "solver_log", "role": "artifact"},
    {"path": "simulation/runs/run_001/solver_run.json", "kind": "solver_run_record", "role": "artifact"},
    {"path": "simulation/runs/run_001/outputs/result.frd", "kind": "frd_result", "role": "artifact"}
  ],
  "warnings": [],
  "errors": [],
  "extracted_metrics": {...},
  "refreshed_summaries": ["result_summary", "preprocessing_summary"]
}
```

**Honest limitations:**
- Only CalculiX (`ccx`) is supported.
- The input deck must already exist inside the package; no mesh generation or input deck generation is performed.
- `converged` is always `null` in `solver_run.json` because CalculiX exit codes alone are not reliable evidence of convergence.
- Solver execution happens on the aieng-ui backend server, not inside the MCP server.

## Approval workflow

```
1. aieng_start_runtime_run(message="run macro")
   → {run_id: "abc", status: "awaiting_approval", tool_calls: [...]}

2. aieng_get_runtime_run(run_id="abc")
   → review pending_step_index, tool_calls[*].name, plan[*]

3a. aieng_approve_runtime_run(run_id="abc")  ← if safe to proceed
    → {status: "completed", ...}

3b. aieng_reject_runtime_run(run_id="abc")   ← if not approved
    → {status: "rejected", ...}
```

## Error format

All tools return a structured error dict on failure:
```json
{"status": "error", "message": "...", "code": "runtime_error"}
```

Common causes:
- `Connection error` — aieng-ui backend is not running at `AIENG_RUNTIME_BASE_URL`
- `HTTP 404` — run ID not found or endpoint mismatch
- `HTTP 422` — malformed request body

## Current limitations

| Limitation | Notes |
|---|---|
| `inputPath` not forwarded | Geometry/export tools resolve input from `project_id → metadata.json`; direct path override needs runtime API support |
| `output_path` not forwarded | Runtime auto-generates `{stem}_export.step` |
| Streaming events | Run events are polled; SSE/WebSocket is future |
| Single backend | One `AIENG_RUNTIME_BASE_URL` per server process |
| Real CAE solver | FreeCAD FEM integration is stubbed; real mesh+solve is future |
| Computed metrics exporter | Normalizes explicit scalar metrics only; no VTU/ODB parsing |
| FRD parser | Extracts DISP and S fields only; binary FRD and VTU/ODB not yet supported |
| Solver preflight | `ready_to_run` reflects artifact presence + `shutil.which`; no physical correctness check |

## Implementation

| File | Role |
|---|---|
| `src/freecad_mcp/aieng_runtime_client.py` | Synchronous HTTP client (`urllib.request`) |
| `src/freecad_mcp/tools_runtime/__init__.py` | `register_runtime_tools(mcp, client)` |
| `src/freecad_mcp/server.py` | Instantiates client and calls `register_runtime_tools` in lifespan |
| `tests/test_aieng_runtime_client.py` | Client unit tests (mocked HTTP) |
| `tests/test_runtime_mcp_tools.py` | MCP tool tests (fake client) |
