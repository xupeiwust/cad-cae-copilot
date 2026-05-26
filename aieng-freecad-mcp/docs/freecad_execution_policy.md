# FreeCAD Execution Policy

## Core Rule

FreeCAD execution must be controlled, whitelisted, and auditable.

The MCP must never run arbitrary Python or shell commands supplied by an AI agent.

## Allowed Execution Pattern

1. Receive MCP tool call.
2. Validate input against schema.
3. Create isolated job workspace.
4. Copy or reference approved input artifacts.
5. Run approved FreeCAD script or module.
6. Capture stdout, stderr, exit status, and generated files.
7. Validate expected outputs.
8. Write evidence and trace records.
9. Return structured result.

## Disallowed Execution Pattern

- Direct arbitrary Python execution.
- Direct shell command passthrough.
- Writing outside approved package or workspace roots.
- Modifying source artifacts in place.
- Hiding failed recompute, failed export, failed mesh, or failed solver runs.

## Job Workspace

Every operation should run inside an isolated workspace:

```text
jobs/
  job_YYYYMMDD_NNN/
    input/
    output/
    logs/
    trace.json
```

## Required Trace Fields

Each execution trace should include:

- job ID
- operation name
- tool name
- FreeCAD version
- invoked approved script/module
- input artifact IDs
- output artifact IDs
- stdout log path
- stderr log path
- exit status
- warnings
- errors
- evidence IDs written
- claim IDs possibly supported

## Source Artifact Policy

Source artifacts must be immutable by default.

Modified geometry must be written to new paths such as:

- `geometry/modified_*.FCStd`
- `geometry/modified_*.step`

## Failure Policy

Failures must be explicit.

A failed FreeCAD recompute, mesh generation, export, or solver run must produce:

- failed status
- trace entry
- captured logs
- no claim advancement
- clear error or unsupported reason
