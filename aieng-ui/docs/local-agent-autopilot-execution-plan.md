# Local Agent Autopilot Execution Plan

Status: **Draft for implementation**
Last updated: **2026-05-28**
Owner: **AIENG workbench maintainers + handoff LLM agents**

## Purpose

This document is the implementation handoff plan for adding a local Agent
Autopilot to `aieng-ui`.

The goal is not a suggestion-only chat assistant. The target capability is:

```text
User describes CAD/CAE intent in the Workbench chat
  -> local agent observes the active project and selected geometry
  -> local agent chooses the next tool call
  -> Workbench validates permissions and executes allowed tools
  -> local agent observes the result and continues
  -> Workbench pauses only for high-risk approvals
  -> local agent returns final engineering explanation
```

Initial local agent adapters:

| Adapter | Initial target | Required mode |
|---|---|---|
| Claude Code CLI | `claude -p` | Non-interactive, structured JSON output, direct tools disabled. |
| Codex CLI | `codex` CLI | Non-interactive structured mode if available; capability probe must detect exact supported invocation. |

The user experience must remain inside the Workbench chat. Users should not need
to switch to Claude Code, Codex, or another terminal chat to drive modeling.

## Current State

Relevant files and systems:

| Area | File | Current role |
|---|---|---|
| Frontend shell | `frontend/src/App.tsx` | Owns chat state, selected project, Agent plan/run calls, approval handlers, viewer refresh, and selected geometry. |
| Chat UI | `frontend/src/components/panels/ChatPanel.tsx` | Main Agent workbench surface. |
| Agent cards | `frontend/src/components/agent/` | Plan, approval, result, and selection UI primitives. |
| Connection catalog | `frontend/src/appConstants.ts`; `backend/app/agent_workbench.py` | Lists `llm-api`, `local-runtime`, and `mcp-bridge` connection choices. |
| Agent planning | `backend/app/agent_engine.py` | Builds LLM or heuristic Agent plans. |
| Agent run API | `backend/app/app_factory.py` | Provides `/api/agent/plan`, `/api/agent/runs`, approval endpoints, direct CAD/CAE compatibility endpoints, and agent activity stream. |
| Runtime | `backend/app/runtime.py`; `backend/app/runtime_tool_schemas.py` | Executes registered runtime tools and records approval-gated runs. |
| Workbench MCP | `backend/app/mcp_server.py` | Lets external agents drive Workbench tools. Useful as a capability model, but Autopilot must start from Workbench chat. |

Important existing behavior:

- `POST /api/agent/runs` can already execute structured steps through runtime.
- `agent_engine.build_agent_plan()` already falls back to heuristic planning.
- Direct text-to-CAD and preprocessing paths still call Claude/Anthropic in several compatibility endpoints.
- Runtime approval exists and must be reused rather than bypassed.
- Local agent execution must not directly mutate files or run arbitrary shell commands.

## Product Target

### User workflow

```text
User: Create an aluminum bracket, fix the left face, apply 500 N on the right hole, and run stress analysis.

Workbench:
  1. Starts a Local Agent Autopilot run.
  2. Sends project context, selected geometry, and tool catalog to the local agent.
  3. Executes read-only observations automatically.
  4. Pauses before CAD mutation.
  5. Runs approved CAD generation through Workbench runtime.
  6. Feeds topology and face pointers back to the agent.
  7. Lets the agent write setup patches and preflight automatically where policy allows.
  8. Pauses before solver execution.
  9. Runs approved solver.
  10. Lets the agent extract and explain results.
```

### Autopilot modes

| Mode | Purpose | Default permission posture |
|---|---|---|
| `assist` | Generate plan and drafts only. | No tool execution except read-only context. |
| `autopilot` | Execute safe read/preview/setup/postprocess tools automatically. | Approval for CAD mutation and solver execution. |
| `full_agent` | Complete bounded tasks with fewer interruptions. | Still requires explicit confirmation for solver and destructive replacement. |

Initial implementation should deliver `autopilot`. `assist` can be a policy flag
on the same engine. `full_agent` is deferred until audit and cancellation are
solid.

## Non-Goals

- Do not let Claude Code or Codex directly edit the repository or project package.
- Do not expose raw terminal sessions in the normal user workflow.
- Do not require users to chat in Claude Code or Codex.
- Do not replace existing `/api/agent/runs` in the first pass.
- Do not remove direct CAD/CAE compatibility endpoints until Autopilot parity exists.
- Do not read `aieng/src/` as a capability reference; use `aieng-ui/backend` runtime tools and Workbench MCP/tool schemas.
- Do not depend on a specific cloud API key for Local Agent Autopilot.

## Architecture

### Backend modules

Add a local autopilot package:

```text
backend/app/agent_autopilot/
  __init__.py
  adapters.py
  claude_code_adapter.py
  codex_cli_adapter.py
  engine.py
  policy.py
  prompts.py
  schema.py
  store.py
```

Responsibilities:

| Module | Responsibility |
|---|---|
| `schema.py` | Pydantic models for run state, observations, agent actions, tool calls, adapter capabilities, and validation errors. |
| `adapters.py` | Common adapter protocol and registry. |
| `claude_code_adapter.py` | Invoke Claude Code CLI in non-interactive JSON mode. |
| `codex_cli_adapter.py` | Probe and invoke Codex CLI when a supported non-interactive mode is available. |
| `engine.py` | Autopilot step loop: observe, ask agent, validate action, execute or pause, record state. |
| `policy.py` | Permission classification and tool allowlist/denylist. |
| `prompts.py` | Compact system and task prompts for local agent action selection. |
| `store.py` | Persist Autopilot runs and events under `data/agent_autopilot/`. |

### API endpoints

Add endpoints in `backend/app/app_factory.py`:

| Endpoint | Purpose |
|---|---|
| `GET /api/local-agents/capabilities` | Probe local adapters and return availability, command, version, and supported features. |
| `POST /api/agent/autopilot/runs` | Start an Autopilot run from Workbench chat. |
| `GET /api/agent/autopilot/runs/{run_id}` | Return current run state. |
| `POST /api/agent/autopilot/runs/{run_id}/continue` | Continue after approval or after a paused run. |
| `POST /api/agent/autopilot/runs/{run_id}/cancel` | Cancel a run safely. |
| `GET /api/agent/autopilot/runs/{run_id}/events` | Optional SSE stream for run events. Reuse existing activity stream if simpler. |

### Frontend integration

Add a connection:

```ts
{
  id: "local-agent",
  label: "Local Agent",
  transport: "agent-cli-bridge",
  status: "configurable",
  detail: "Uses a local Claude Code or Codex CLI agent as an autonomous planner/executor through Workbench approvals.",
  requires_project: false,
  supports_llm: true,
  supports_execution: true,
  approval_gated: true
}
```

Frontend should:

- Show adapter availability in settings or the Agent debug panel.
- Let the user choose `Claude Code` or `Codex CLI` where both are available.
- Route chat submit to `/api/agent/autopilot/runs` when `local-agent` is selected.
- Render each Autopilot step as existing Agent cards where possible.
- Reuse existing approval card patterns for paused side-effecting actions.
- Preserve selected geometry context in the Autopilot request.

## Agent Action Contract

The local agent must return exactly one action per step. The Workbench validates
the output before doing anything.

```json
{
  "thought_summary": "Need to create the CAD model before assigning CAE setup.",
  "action": {
    "type": "tool_call",
    "tool_name": "cad.execute_build123d",
    "input": {
      "project_id": "project_123",
      "mode": "replace",
      "code": "from build123d import *\n..."
    }
  },
  "done": false,
  "user_message": "I drafted the bracket geometry and need approval to write the model."
}
```

Allowed action types:

| Type | Meaning |
|---|---|
| `tool_call` | Request one Workbench runtime/MCP-style tool call. |
| `ask_user` | Ask one concise clarification question. |
| `final` | Finish the Autopilot run with a user-facing answer. |
| `pause` | Pause for external dependency or unavailable adapter. |

Required validation:

- Output must parse as JSON.
- Output must match JSON Schema.
- `tool_name` must exist in registered Workbench tools.
- `input.project_id` must match the active project when a project is required.
- The local agent must not request raw shell, file writes, or direct package edits.
- Approval policy decides whether the tool call can run now or must pause.

## Permission Policy

Use these levels:

| Level | Examples | Autopilot behavior |
|---|---|---|
| `auto_read` | `aieng.agent_context`, `aieng.validate`, B-Rep graph reads, audit reads. | Execute immediately. |
| `auto_preview` | Solver preflight, patch parse, dry-run planning, completeness reports. | Execute immediately and show observation. |
| `auto_write_safe` | CAE setup patch, solver input generation, result extraction, summary refresh. | Execute in `autopilot` mode if tool is allowlisted and scoped to active project. |
| `approval_mutation` | CAD create/replace/append, geometry refresh, package-changing model updates. | Pause for approval. |
| `explicit_confirm` | `cae.run_solver`, destructive replacement, batch optimization loops. | Require dedicated approval copy and explicit user action. |
| `blocked` | Raw shell, arbitrary file writes, direct `.aieng` ZIP edits, unknown tools. | Reject and ask the local agent for another action. |

Policy must be backend-enforced. Frontend labels are not sufficient.

## Local Adapter Requirements

### Claude Code adapter

Known viable capabilities:

- `claude -p` for non-interactive output.
- `--output-format json` or `stream-json`.
- `--json-schema` for schema-constrained output.
- `--permission-mode plan` for non-mutating behavior.
- `--tools ""` to disable built-in tools.
- `--add-dir <workspace>` to make the trusted workspace explicit.

Initial invocation shape:

```powershell
claude -p `
  --output-format json `
  --json-schema "<agent-action-schema>" `
  --permission-mode plan `
  --tools "" `
  --add-dir "G:\Code\workspace_aieng" `
  "<packed autopilot prompt>"
```

Implementation notes:

- Use `subprocess.run(..., timeout=...)` or async subprocess with a hard timeout.
- Send large prompts through stdin or a temp file if command-line length becomes a problem.
- Capture stdout, stderr, exit code, duration, and parsed JSON.
- Never pass `--dangerously-skip-permissions`.
- Default timeout: 120 seconds for a step, configurable later.

### Codex CLI adapter

The Codex adapter must start with capability probing because installations differ.

Probe order:

1. Resolve configured command from settings or environment.
2. Try `codex --help` with a short timeout.
3. Detect a non-interactive command such as `exec`, `run`, or equivalent if present.
4. Detect JSON or schema-constrained output support if present.
5. If no safe non-interactive structured mode is available, report `status: blocked`.

Minimum acceptable Codex support:

- Non-interactive prompt execution.
- Machine-readable output or reliable extraction of a JSON object.
- Ability to disable direct file/shell tools or run in a plan-only mode.
- Timeout and cancellation.

Do not fake Codex support by automating an interactive terminal. If the installed
Codex build cannot provide a safe invocation, the adapter should remain present
but unavailable with a clear diagnostic.

## Development State Management

### Status values

Every task below must use exactly one status:

| Status | Meaning |
|---|---|
| `TODO` | Not started. |
| `IN_PROGRESS` | Currently being edited by an agent. |
| `BLOCKED` | Cannot proceed without external input or missing dependency. |
| `REVIEW` | Code complete, waiting for human or maintainer review. |
| `DONE` | Implemented, verified, and documented. |
| `DEFERRED` | Intentionally postponed. |

### Required handoff rule

At the end of every development session, the implementing LLM must update the
task ledger in this document:

```text
Task ID:
Status:
Files changed:
Verification run:
Known risks:
Next recommended task:
```

If a task changes code, update its status and add or update the corresponding
ledger row before ending the session.

### Verification baseline

Backend baseline:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_context.py tests/test_runtime_tools.py tests/test_agent_observation.py
```

Frontend baseline:

```powershell
cd aieng-ui/frontend
npm run build
```

Autopilot-specific tests should be added as tasks land:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_policy.py tests/test_agent_autopilot_adapters.py tests/test_agent_autopilot_engine.py
```

## Implementation Phases

### Phase 0 - Feasibility and Safety Baseline

Goal: prove local agent invocation can be detected safely without executing
Workbench tools.

#### LAA-P0-T01 - Record CLI Capability Probe Baseline

Status: `DONE`

Scope:

- Add a small backend helper that probes `claude` and `codex` commands.
- Return command path, version/help availability, and whether a structured non-interactive mode is detected.
- Do not run any user prompt through either agent yet.

Files likely touched:

- `backend/app/agent_autopilot/adapters.py`
- `backend/app/agent_autopilot/claude_code_adapter.py`
- `backend/app/agent_autopilot/codex_cli_adapter.py`
- `backend/tests/test_agent_autopilot_adapters.py`
- This document.

Acceptance:

- Claude Code available on a machine with `claude` installed reports `available`.
- Codex CLI reports either `available` or a clear `blocked` diagnostic.
- Probe has a short timeout and never starts an interactive session.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_adapters.py
```

#### LAA-P0-T02 - Add Local Agent Capability Endpoint

Status: `DONE`

Scope:

- Add `GET /api/local-agents/capabilities`.
- Return all adapter probe results.
- Include safe diagnostics for missing commands or unsupported modes.

Files likely touched:

- `backend/app/app_factory.py`
- `backend/app/agent_autopilot/`
- `backend/tests/test_api.py`

Acceptance:

- Endpoint returns deterministic JSON without requiring API keys.
- Missing local CLIs do not fail the endpoint.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_api.py::test_local_agent_capabilities
```

### Phase 1 - Contracts and Policy

Goal: define the structured action loop before wiring real CLI calls.

#### LAA-P1-T01 - Add Autopilot Schema Models

Status: `DONE`

Scope:

- Add typed models for:
  - `AutopilotRunRequest`
  - `AutopilotRunState`
  - `AutopilotObservation`
  - `AutopilotAgentAction`
  - `AutopilotToolCall`
  - `AutopilotApproval`
  - `LocalAgentCapability`
- Export JSON Schema for adapter prompts.

Files likely touched:

- `backend/app/agent_autopilot/schema.py`
- `backend/tests/test_agent_autopilot_schema.py`

Acceptance:

- Valid `tool_call`, `ask_user`, `final`, and `pause` actions pass.
- Unknown action types and unknown extra mutation fields fail.
- JSON Schema can be serialized and passed to a CLI adapter.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_schema.py
```

#### LAA-P1-T02 - Add Backend Permission Policy

Status: `DONE`

Scope:

- Classify registered runtime tools into permission levels.
- Enforce active project scoping.
- Reject unknown tools and raw shell/file actions.
- Add a policy explanation string for UI approval cards.

Files likely touched:

- `backend/app/agent_autopilot/policy.py`
- `backend/tests/test_agent_autopilot_policy.py`

Acceptance:

- Read-only tools classify as `auto_read`.
- CAD mutation classifies as `approval_mutation`.
- Solver execution classifies as `explicit_confirm`.
- Unknown tools classify as `blocked`.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_policy.py
```

#### LAA-P1-T03 - Add Prompt Builder

Status: `DONE`

Scope:

- Build compact prompts containing:
  - user objective
  - active project ID
  - selected geometry
  - compact agent context
  - available tool catalog
  - previous observations
  - required JSON action schema
- Explicitly instruct the local agent not to use its own file/shell tools.

Files likely touched:

- `backend/app/agent_autopilot/prompts.py`
- `backend/tests/test_agent_autopilot_prompts.py`

Acceptance:

- Prompt includes selected face/edge pointers when present.
- Prompt includes only Workbench tool names and schemas, not raw filesystem internals.
- Prompt size has a deterministic compacting strategy for long histories.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_prompts.py
```

### Phase 2 - Dry-Run Autopilot Engine

Goal: run the loop against a fake local agent without executing real tools.

#### LAA-P2-T01 - Add Run Store and Event Model

Status: `DONE`

Scope:

- Persist runs under `data/agent_autopilot/runs/`.
- Store run status, steps, observations, pending approvals, errors, and final message.
- Use append-only event records for debugging and UI streaming.

Files likely touched:

- `backend/app/agent_autopilot/store.py`
- `backend/tests/test_agent_autopilot_store.py`

Acceptance:

- Run state survives process restart.
- Event append is atomic enough for local development.
- Corrupt run files fail safely with a diagnostic.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_store.py
```

#### LAA-P2-T02 - Add Engine Step Loop With Fake Adapter

Status: `DONE`

Scope:

- Implement one-step-at-a-time loop:
  1. build observation
  2. call adapter
  3. validate action
  4. classify policy
  5. dry-run execute or pause
  6. persist event
- Add a fake adapter for deterministic tests.

Files likely touched:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/agent_autopilot/adapters.py`
- `backend/tests/test_agent_autopilot_engine.py`

Acceptance:

- Final action completes the run.
- Blocked action returns an observation asking the adapter to choose a legal action.
- Approval-required action pauses the run.
- Loop has max-step protection.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py
```

#### LAA-P2-T03 - Add Autopilot Run API in Dry-Run Mode

Status: `DONE`

Scope:

- Add `POST /api/agent/autopilot/runs`.
- Add `GET /api/agent/autopilot/runs/{run_id}`.
- Use fake adapter or dry-run mode in tests.

Files likely touched:

- `backend/app/app_factory.py`
- `backend/app/agent_autopilot/`
- `backend/tests/test_api.py`

Acceptance:

- API creates a run from a chat message and returns current state.
- API includes pending approval metadata when policy requires it.
- Invalid adapter ID returns a helpful error.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_api.py::test_agent_autopilot_run_dry_run
```

### Phase 3 - Real Claude Code Adapter

Goal: let Claude Code produce structured next actions, still through Workbench
policy and execution.

#### LAA-P3-T01 - Implement Claude Code JSON Adapter

Status: `DONE`

Scope:

- Invoke `claude -p` with JSON output/schema constraints.
- Disable direct Claude tools.
- Parse stdout into `AutopilotAgentAction`.
- Capture stderr and timeout diagnostics.

Files likely touched:

- `backend/app/agent_autopilot/claude_code_adapter.py`
- `backend/tests/test_agent_autopilot_adapters.py`

Acceptance:

- Unit tests cover successful JSON, invalid JSON, timeout, and non-zero exit.
- Adapter can be disabled by settings/environment for CI.
- No test requires a real Claude Code install unless explicitly marked integration.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_adapters.py
```

#### LAA-P3-T02 - Add Optional Claude Code Integration Smoke Test

Status: `DONE`

Scope:

- Add a skipped-by-default test or script that calls Claude Code with a tiny JSON schema.
- Gate it behind an environment variable such as `AIENG_RUN_LOCAL_AGENT_SMOKE=1`.

Files likely touched:

- `backend/tests/test_agent_autopilot_local_smoke.py`
- `backend/scripts/smoke_local_agent_claude.py`

Acceptance:

- CI does not require Claude Code.
- Maintainers can run one command locally to verify adapter health.

Verification:

```powershell
cd aieng-ui/backend
$env:AIENG_RUN_LOCAL_AGENT_SMOKE="1"
python -m pytest tests/test_agent_autopilot_local_smoke.py
```

### Phase 4 - Codex CLI Adapter

Goal: support Codex where a safe non-interactive CLI is available.

#### LAA-P4-T01 - Implement Codex Capability Probe

Status: `DONE`

Scope:

- Detect the configured Codex command.
- Probe help/version safely.
- Detect supported non-interactive and JSON modes.
- Return blocked diagnostics when unavailable.

Files likely touched:

- `backend/app/agent_autopilot/codex_cli_adapter.py`
- `backend/tests/test_agent_autopilot_adapters.py`

Acceptance:

- Missing Codex command is not an error for the app.
- WindowsApps permission errors are reported clearly.
- Interactive-only Codex installs are marked unavailable for Autopilot.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_adapters.py
```

#### LAA-P4-T02 - Implement Codex Structured Adapter

Status: `DONE`

Scope:

- Add the safest supported Codex non-interactive invocation discovered by `LAA-P4-T01`.
- Add JSON extraction only if Codex lacks strict JSON schema support.
- Keep raw file/shell capabilities disabled when the CLI supports that setting.

Files likely touched:

- `backend/app/agent_autopilot/codex_cli_adapter.py`
- `backend/tests/test_agent_autopilot_adapters.py`

Acceptance:

- Adapter passes the same success/failure contract as Claude Code adapter.
- If no supported Codex invocation exists, task may be marked `BLOCKED` with exact probe output and no fake implementation.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_adapters.py
```

### Phase 5 - Runtime Execution Integration

Goal: execute safe local-agent tool calls through existing Workbench runtime.

#### LAA-P5-T01 - Execute Auto-Allowed Tools

Status: `DONE`

Scope:

- Connect Autopilot engine to registered runtime tools.
- Execute `auto_read`, `auto_preview`, and selected `auto_write_safe` actions.
- Feed tool result or error back as the next observation.

Files likely touched:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/runtime.py`
- `backend/tests/test_agent_autopilot_engine.py`

Acceptance:

- Read-only observations run without approval.
- Tool errors are captured and sent back to the local agent for correction.
- Max-step protection prevents infinite loops.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py tests/test_runtime_tools.py
```

#### LAA-P5-T02 - Pause and Resume Approval-Gated Tool Calls

Status: `DONE`

Scope:

- Store pending tool call when policy requires approval.
- Add continue endpoint behavior after user approval.
- Reuse existing runtime approval UI semantics where possible.

Files likely touched:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`
- `backend/tests/test_agent_autopilot_engine.py`

Acceptance:

- CAD mutation pauses with side-effect summary.
- Solver execution pauses with explicit-confirm metadata.
- Rejection sends an observation back to the agent or ends the run based on user choice.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py
```

#### LAA-P5-T03 - Add Audit Events

Status: `DONE`

Scope:

- Write audit entries for Autopilot start, adapter action, tool execution, approval, rejection, cancellation, and final answer.
- Include adapter ID and sanitized prompt metadata, but never raw secrets.

Files likely touched:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/agent_autopilot/store.py`
- `backend/tests/test_agent_autopilot_engine.py`

Acceptance:

- Project audit log shows a clear agent/tool sequence.
- Local adapter stderr is stored only in diagnostics, not shown as normal user output.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py
```

### Phase 6 - Frontend Local Agent UX

Goal: make Autopilot usable from the existing Workbench chat.

#### LAA-P6-T01 - Add Local Agent Connection

Status: `DONE`

Scope:

- Add `local-agent` to frontend defaults and backend connection catalog.
- Load `/api/local-agents/capabilities`.
- Show available adapter names and status.

Files likely touched:

- `frontend/src/appConstants.ts`
- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `backend/app/agent_workbench.py`
- `frontend/src/components/settings/RuntimeSettingsDrawer.tsx`

Acceptance:

- Chat connection dropdown can select `Local Agent`.
- If no adapter is available, UI explains why and disables run.
- Existing `llm-api` and `local-runtime` paths still work.

Verification:

```powershell
cd aieng-ui/frontend
npm run build
```

#### LAA-P6-T02 - Route Chat Submit to Autopilot Runs

Status: `DONE`

Scope:

- When `selectedChatConnectionId === "local-agent"`, start an Autopilot run.
- Include selected geometry and active project context.
- Render returned run state in chat history.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/appTypes.ts`
- `frontend/src/components/panels/ChatPanel.tsx`

Acceptance:

- User message starts Autopilot instead of direct LLM API planning.
- Autopilot response can show current step, pending approval, or final answer.
- Selected face/edge pointers are included in backend payload.

Verification:

```powershell
cd aieng-ui/frontend
npm run build
```

#### LAA-P6-T03 - Add Autopilot Step Cards

Status: `DONE`

Scope:

- Reuse or extend Agent cards to show:
  - current objective
  - adapter used
  - step list
  - latest observation
  - pending approval
  - final explanation
- Add cancel/continue actions.

Files likely touched:

- `frontend/src/components/agent/AgentPlanCard.tsx`
- `frontend/src/components/agent/ApprovalCard.tsx`
- `frontend/src/components/agent/AgentResultCard.tsx`
- `frontend/src/components/agent/AutopilotRunCard.tsx`
- `frontend/src/style.css`

Acceptance:

- The UI reads as an active automation, not a static suggestion.
- Approval copy names the exact tool and side effects.
- Final answer references artifacts and pointer chips where present.

Verification:

```powershell
cd aieng-ui/frontend
npm run build
```

### Phase 7 - CAD/CAE Vertical Slice

Goal: prove natural-language modeling, preprocessing, solver execution, and
postprocessing can complete through Autopilot.

#### LAA-P7-T01 - CAD Generation Autopilot Slice

Status: `DONE`

Scope:

- Give the local agent enough tool schema/context to generate build123d code.
- Pause before `cad.execute_build123d`.
- After approval, execute through Workbench and feed topology result back.

Files likely touched:

- `backend/app/agent_autopilot/prompts.py`
- `backend/app/agent_autopilot/policy.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/tests/test_agent_autopilot_engine.py`

Acceptance:

- User can request a simple part and receive an approval-gated CAD write step.
- After approval, project preview artifacts refresh through existing runtime behavior.
- The agent receives named parts/topology summary as observation.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py tests/test_cad_generation.py tests/test_brep_graph.py
```

#### LAA-P7-T02 - Natural-Language Preprocessing Slice

Status: `DONE`

Scope:

- Let the local agent choose material, supports, loads, and mesh settings from context.
- Prefer selected geometry pointers when available.
- Execute safe setup patching according to policy.
- Run solver preflight automatically.

Files likely touched:

- `backend/app/agent_autopilot/prompts.py`
- `backend/app/agent_autopilot/policy.py`
- `backend/tests/test_agent_autopilot_engine.py`

Acceptance:

- User can say "fix this face and apply 500 N here" with selected faces.
- Setup patch uses valid face pointers or asks a clarification.
- Preflight result is shown as observation.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py tests/test_ai_preprocessing.py tests/test_simulation_runner.py
```

#### LAA-P7-T03 - Solver and Postprocess Slice

Status: `DONE`

Scope:

- Pause before `cae.run_solver`.
- After approval, run solver, extract metrics, extract field regions, refresh summary.
- Feed final result to local agent for natural-language explanation.

Files likely touched:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/agent_autopilot/policy.py`
- `frontend/src/components/agent/AgentResultCard.tsx`
- `frontend/src/components/agent/AutopilotRunCard.tsx`

Acceptance:

- Solver execution requires explicit approval.
- Postprocess steps can run automatically after solver success.
- Final answer includes max stress/displacement/verdict when available.

Verification:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py tests/test_simulation_runner.py
cd ../frontend
npm run build
```

### Phase 8 - Hardening and Handoff

Goal: make future LLM agents able to continue safely.

#### LAA-P8-T01 - Add Developer Handoff Notes

Status: `DONE`

Scope:

- Document adapter configuration, environment variables, debug logs, and common failure modes.
- Include exact commands for Claude Code and Codex capability probes.

Files likely touched:

- `aieng-ui/docs/local-agent-autopilot-handoff.md`
- This document.

Acceptance:

- A new LLM can identify the next TODO and continue without rediscovering the architecture.
- Handoff lists where run state is stored and how to reset local test runs.

Verification:

- Documentation review.

#### LAA-P8-T02 - Add End-to-End Demo Script

Status: `DONE`

Scope:

- Add a deterministic demo scenario for a simple bracket or plate.
- Include manual approval checkpoints.
- Include expected artifacts and screenshots to verify.

Files likely touched:

- `aieng-ui/docs/local-agent-autopilot-demo.md`
- `backend/scripts/`

Acceptance:

- Demo can be followed by a maintainer on a machine with Claude Code or supported Codex CLI.
- If no local agent is available, demo explains the exact blocked capability.

Verification:

- Manual demo run.

## Task Ledger

Update this table after each task.

| Task ID | Status | Owner/session | Files changed | Verification | Notes |
|---|---|---|---|---|---|
| LAA-P0-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/adapters.py`, `claude_code_adapter.py`, `codex_cli_adapter.py`, `backend/tests/test_agent_autopilot_adapters.py` | `python -m pytest tests/test_agent_autopilot_adapters.py`; manual `claude --help`, `codex --help`, `codex exec --help` | Claude reports safe `-p` JSON/schema/tool-disable flags. Codex reports non-interactive `exec` plus schema/read-only controls. Next: keep probes short and non-interactive. |
| LAA-P0-T02 | DONE | Codex 2026-05-28 | `backend/app/app_factory.py`, `backend/tests/test_api.py` | `python -m pytest tests/test_api.py::test_local_agent_capabilities_endpoint` | Added `GET /api/local-agents/capabilities`; missing CLIs return diagnostics instead of endpoint failure. Next: surface detailed adapter status in UI. |
| LAA-P1-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/schema.py`, `backend/tests/test_agent_autopilot_schema.py` | `python -m pytest tests/test_agent_autopilot_schema.py` | Added strict Pydantic action/run/observation/capability models and JSON Schema export. Next: reuse schema for every adapter call. |
| LAA-P1-T02 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/policy.py`, `backend/tests/test_agent_autopilot_policy.py` | `python -m pytest tests/test_agent_autopilot_policy.py` | Added backend-enforced tool permission levels and active-project scoping. Next: wire policy decisions into real runtime execution. |
| LAA-P1-T03 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/prompts.py` | Included in `python -m pytest tests/test_agent_autopilot_engine.py` | Prompt builder packs objective, project, selected geometry, context, tool catalog, observations, and action schema. Next: add prompt compaction tests if histories grow. |
| LAA-P2-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/store.py`, `backend/tests/test_agent_autopilot_store.py` | `python -m pytest tests/test_agent_autopilot_store.py` | File-backed run state under `data/agent_autopilot/runs/` with safe corrupt-file diagnostics. Next: append-only events for streaming/debugging. |
| LAA-P2-T02 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/engine.py`, `backend/app/agent_autopilot/adapters.py`, `backend/tests/test_agent_autopilot_engine.py` | `python -m pytest tests/test_agent_autopilot_engine.py` | Fake adapter loop validates final, blocked, dry-run accepted, and approval-required actions with max-step protection. Next: execute auto-allowed tools through runtime. |
| LAA-P2-T03 | DONE | Codex 2026-05-28 | `backend/app/app_factory.py`, `backend/tests/test_api.py` | `python -m pytest tests/test_api.py::test_agent_autopilot_run_dry_run` | Added create/get Autopilot run API for dry-run/fake-adapter flow. Next: add continue/cancel endpoints. |
| LAA-P3-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/claude_code_adapter.py`, `backend/tests/test_agent_autopilot_adapters.py` | `python -m pytest tests/test_agent_autopilot_adapters.py`; `AIENG_RUN_LOCAL_AGENT_SMOKE=1 python -m pytest tests/test_agent_autopilot_local_smoke.py::test_claude_code_local_smoke` | Claude adapter invokes `claude -p --bare --no-session-persistence` with JSON schema, plan permission mode, disabled tools, stdin prompt input, timeout cleanup, and `structured_output` parsing. |
| LAA-P3-T02 | DONE | Codex 2026-05-28 | `backend/tests/test_agent_autopilot_local_smoke.py`, `backend/scripts/smoke_local_agent_claude.py` | `AIENG_RUN_LOCAL_AGENT_SMOKE=1 python -m pytest tests/test_agent_autopilot_local_smoke.py::test_claude_code_local_smoke` | Added gated Claude Code smoke test/script; real local smoke passed after adding bare/no-session mode and wrapper parsing. |
| LAA-P4-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/codex_cli_adapter.py`, `backend/tests/test_agent_autopilot_adapters.py` | `python -m pytest tests/test_agent_autopilot_adapters.py`; manual `codex exec --help` | Probe now checks root help plus `codex exec --help` for `--output-schema`, `--sandbox read-only`, and approval controls. Next: verify installed Codex behavior with a real structured smoke. |
| LAA-P4-T02 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/codex_cli_adapter.py`, `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/adapters.py`, `backend/tests/test_agent_autopilot_local_smoke.py`, `backend/scripts/smoke_local_agent_codex.py` | `AIENG_RUN_CODEX_LOCAL_AGENT_SMOKE=1 python -m pytest tests/test_agent_autopilot_local_smoke.py::test_codex_cli_local_smoke`; `python -m pytest tests/test_agent_autopilot_adapters.py` | Real Codex v0.134.0 structured smoke passed after using root `--ask-for-approval`, strict schema-compatible `input_json`, and `--output-last-message`. |
| LAA-P5-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/engine.py`, `backend/app/app_factory.py`, `backend/tests/test_agent_autopilot_engine.py` | `python -m pytest tests/test_agent_autopilot_engine.py tests/test_runtime_tools.py` | Auto-allowed tools now execute through the injected Workbench runtime executor when `dry_run=false`; errors are recorded as observations for the next agent step. Next: broaden runtime-output summarization. |
| LAA-P5-T02 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/engine.py`, `backend/app/app_factory.py`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/panels/ChatPanel.tsx` | `python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py::test_agent_autopilot_continue_and_cancel`; `npm run build` | Pending approval calls can be approved/rejected/cancelled through backend endpoints and frontend card actions. Next: align copy with existing runtime approval wording. |
| LAA-P5-T03 | DONE | Codex 2026-05-28 | `backend/app/app_factory.py`, `backend/tests/test_api.py` | `python -m pytest tests/test_api.py::test_agent_autopilot_writes_project_audit_events` | Start and approval/rejection write `agent_autopilot` project audit log files with run id and decision metadata. |
| LAA-P6-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_workbench.py`, `frontend/src/appConstants.ts`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/App.tsx` | `npm run build`; `python -m pytest tests/test_api.py::test_local_agent_capabilities_endpoint` | Added `local-agent` connection, loaded `/api/local-agents/capabilities`, and merged adapter status into the dropdown. Next: refine settings/debug presentation. |
| LAA-P6-T02 | DONE | Codex 2026-05-28 | `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/appTypes.ts` | `npm run build` | Chat submit routes to `/api/agent/autopilot/runs` when Local Agent is selected and includes selected geometry/project payload. Next: wire continue/cancel once backend endpoints exist. |
| LAA-P6-T03 | DONE | Codex 2026-05-28 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/style.css`, `frontend/src/App.tsx` | `npm run build` | Added Autopilot run card with status, adapter, pending approval, latest observations, and approve/reject/cancel controls. Next: polish event streaming once SSE lands. |
| LAA-P7-T01 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/prompts.py`, `backend/app/agent_autopilot/engine.py`, `backend/tests/test_agent_autopilot_engine.py`, `backend/tests/test_agent_autopilot_prompts.py`, `backend/app/cad_generation.py` | `python -m pytest tests/test_agent_autopilot_engine.py tests/test_cad_generation.py tests/test_brep_graph.py` | CAD prompt guidance covers build123d result/labels; approval-gated CAD call feeds named-parts/topology-style output back as observation. Added dependency-free PNG fallback for headless CAD thumbnails. |
| LAA-P7-T02 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/prompts.py`, `backend/app/agent_autopilot/engine.py`, `backend/tests/test_agent_autopilot_engine.py` | `python -m pytest tests/test_agent_autopilot_engine.py tests/test_ai_preprocessing.py tests/test_simulation_runner.py` | Selected geometry is included in prompts; safe `cae.apply_setup_patch` runs automatically and triggers `cae.prepare_solver_run` follow-up. |
| LAA-P7-T03 | DONE | Codex 2026-05-28 | `backend/app/agent_autopilot/engine.py`, `backend/tests/test_agent_autopilot_engine.py` | `python -m pytest tests/test_agent_autopilot_engine.py tests/test_ai_preprocessing.py tests/test_simulation_runner.py`; `npm run build` | `cae.run_solver` remains approval-gated; after approval the engine runs solver-result extraction, stress field regions, and CAE summary refresh follow-ups. |
| LAA-P8-T01 | DONE | Codex 2026-05-28 | `aieng-ui/docs/local-agent-autopilot-handoff.md`, this document | Documentation review | Added adapter configuration, env vars, debug paths, verification commands, reset instructions, and next recommended task. |
| LAA-P8-T02 | DONE | Codex 2026-05-28 | `aieng-ui/docs/local-agent-autopilot-demo.md`, `backend/scripts/demo_local_agent_autopilot.py`, this document | `python scripts/demo_local_agent_autopilot.py --api-url http://127.0.0.1:8001 --project-id demo_autopilot`; same command with `--approve` | Added deterministic API demo script. Verified capability output, CAD approval checkpoint, and dry-run approval continuation against fresh backend on port 8001. |

## Recommended First Implementation Order

1. `LAA-P0-T01`
2. `LAA-P0-T02`
3. `LAA-P1-T01`
4. `LAA-P1-T02`
5. `LAA-P2-T02`
6. `LAA-P3-T01`
7. `LAA-P6-T01`
8. `LAA-P6-T02`
9. `LAA-P5-T01`
10. `LAA-P7-T01`

This order gives a useful vertical path quickly:

```text
capability probe
  -> typed action contract
  -> policy
  -> fake loop
  -> Claude Code loop
  -> UI connection
  -> safe tool execution
  -> CAD generation slice
```

## Completion Definition

Local Agent Autopilot is considered MVP-complete when:

- Workbench chat can select `Local Agent`.
- Backend detects Claude Code and Codex CLI capabilities safely.
- Claude Code adapter can produce schema-valid tool actions.
- Codex adapter either works through a safe non-interactive mode or reports an honest blocked diagnostic.
- Autopilot can run a multi-step loop with observations.
- Read/preview/setup/postprocess tools can run automatically under policy.
- CAD mutation pauses for approval and executes through Workbench.
- Solver execution pauses for explicit confirmation.
- Final answers summarize CAD/CAE results with artifacts and pointer references.
- Every completed task has an updated ledger row.
