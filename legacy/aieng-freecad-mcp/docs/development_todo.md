# Development Todo

Status: planning document only. Items below are proposed future work and are not implemented by default.

Research basis:
- MCP landscape inventory: [docs/research/github_mcp_landscape.md](docs/research/github_mcp_landscape.md)
- Design synthesis: [docs/research/mcp_design_inspiration.md](docs/research/mcp_design_inspiration.md)

Core boundary to preserve:
- Composable FreeCAD MCP execution interface, not an autonomous workflow engine.
- Optional .aieng enhancement, not a hard dependency.
- CAD and CAE remain independent first-class workflows.
- CAD to CAE orchestration remains optional and explicit.
- Evidence is not a claim.
- Claim updates remain explicit and evidence-backed.
- Agent/caller decides workflow ordering.

## v1.1 - Tool Transparency and Inspection

Status: **Implemented**

### Machine-readable side-effect catalog

- Status: Implemented
- `src/freecad_mcp/tool_registry.py` defines `ToolRegistryEntry` with category, purpose, inputs, side effects, mutability, runtime requirements, dry-run support, and claim policy.
- `aieng_tool_registry_query` MCP tool provides read-only filtered queries.
- Tests: `tests/test_tool_registry.py`

### Stronger read-only CAD inspection

- Status: Implemented scaffold (existing `cad_inspect_object`, `cad_list_objects` already provide rich summaries)

### Runtime capability report improvements

- Status: Implemented scaffold (`freecad_runtime_capabilities` already exists)

### Stricter error taxonomy normalization

- Status: Implemented
- `src/freecad_mcp/contracts/failure_mode.py` defines `FailureMode` taxonomy and `classify_exception` heuristic.
- `FailureDetail` embedded in `StandardToolResult`, `CadToolResponse`, and `CaeBaseResponse`.
- Audit report includes failure-mode coverage ratio.
- Tests: `tests/test_failure_mode_taxonomy.py`

### Dry-run preview metadata

- Status: Implemented
- `src/freecad_mcp/contracts/operation_preview.py` defines `OperationPreview` model.
- `preview_operation` MCP tool returns previews without side effects.
- `CadToolResponse` and `CaeBaseResponse` carry optional `preview` field.
- Tests: `tests/test_operation_preview.py`

## v1.2 - Visual and Field Evidence

### Optional CAD visual preview artifacts

- purpose: export screenshots/light previews for review traceability
- benefit: faster human inspection
- guardrails: visual artifacts are evidence only; visual success is not validation; claim state unchanged unless explicit claim update
- non-goals: visual-only pass/fail shortcuts; replacing solver-backed criteria

### Field-oriented post-processing planning

- purpose: structured outputs for result fields/summaries
- benefit: better downstream portability
- guardrails: outputs remain observations; missing field data is explicit/auditable
- non-goals: autonomous claim interpretation; automatic chain to claim updates

## v1.3 - Adapter Research

### VTK/ParaView/PyVista adapter research

- purpose: evaluate post-processing/visualization adapter contracts
- benefit: future extensibility with boundary discipline
- guardrails: research-only until approved scope; preserve evidence/trace discipline; keep `.aieng` optional
- non-goals: immediate production implementation; autonomous orchestration shift

### CadQuery regeneration adapter research

- purpose: evaluate guarded regeneration options outside direct FreeCAD editing
- benefit: optional backend flexibility for constrained regeneration
- guardrails: no arbitrary script execution as normal public tool; preserve guards/side-effect declarations/claim policy; preserve CAD/CAE independence
- non-goals: prompt-to-code arbitrary execution surface; bypassing existing guard discipline

## Do Not Adopt

The following patterns are explicitly out of scope unless fundamentally redesigned to meet core policy constraints:

- Arbitrary Python execution tool as standard capability.
- Arbitrary shell execution tool.
- Autonomous CAD to CAE to claim orchestration.
- Solver-success to claim-pass shortcut.
- Visual-render to validation shortcut.
- Hidden package mutation without side-effect metadata.
- Weak or collapsed unsupported or missing or not_found or needs_review signaling.
