# Local Agent Autopilot Handoff

Last updated: 2026-05-30

## Current Implementation State

Local Agent Autopilot is implemented through:

- Backend package: `backend/app/agent_autopilot/`
- Capability endpoint: `GET /api/local-agents/capabilities`
- Run endpoints:
  - `POST /api/agent/autopilot/runs`
  - `GET /api/agent/autopilot/runs/{run_id}`
  - `POST /api/agent/autopilot/runs/{run_id}/continue`
  - `POST /api/agent/autopilot/runs/{run_id}/reply`
  - `POST /api/agent/autopilot/runs/{run_id}/follow-up`
  - `POST /api/agent/autopilot/runs/{run_id}/cancel`
- Frontend connection id: `local-agent`
- Run state directory: `aieng-ui/data/agent_autopilot/runs/`

The local agent never receives permission to call Workbench tools directly. It
returns one JSON action at a time; the backend validates the action, applies
policy, and executes only Workbench runtime tools.

Current CAD behavior:

- Before `cad.execute_build123d`, the Autopilot prompt requires a compact CAD brief: units/origin, key dimensions, features, semantic labels, validation targets, and assumptions.
- CAD source is expected to use named parameters, `.label`, `.color`, and `Compound(children=[...])`; exports remain the runner's responsibility.
- `cad.execute_build123d` remains approval-gated. After approval and successful execution, the engine automatically runs read-only `cad.critique` when the tool is registered.
- Critique observations are compacted before being sent back to the local agent so prompt growth stays bounded.
- The React UI now uses the compact transcript UI as the sole chat rendering
  path; the temporary `aieng-ui.chat-transcript-v2` fallback setting and legacy
  Agent card path have been removed.

## Chat Transcript Architecture

Transcript rendering is split into three layers:

- `frontend/src/app/chatTranscript.ts` is a pure mapper for persisted chat
  messages, Autopilot run snapshots, and typed agent events.
- `frontend/src/components/chat/` contains focused transcript components for
  messages, tool rows, approvals, artifact rows, and collapsed details.
- `backend/app/db.py` persists append-only `agent_events`; the frontend fetches
  them through `GET /api/projects/{project_id}/agent-events`.

The backend still publishes `autopilot_update` snapshots for compatibility, but
new transcript rows should come from typed events when possible:
`agent_message`, `tool_started`, `tool_completed`, `tool_failed`,
`approval_requested`, `approval_resolved`, `artifact_ready`,
`run_status_changed`, and `run_cancelled`.

Normal conversation is no longer routed through approval continuation:

- `continue` is for approve/reject and backwards compatibility.
- `reply` resumes chatting/blocked/approval-revision runs without approving.
- `follow-up` queues text while a run is already working.

To reset replay state during local development, clear chat rows through the UI
or delete the local sqlite database under `aieng-ui/data/aieng.db`.

## Adapter Configuration

Environment variables:

| Variable | Purpose |
|---|---|
| `AIENG_CLAUDE_CODE_COMMAND` | Override the Claude Code command; default `claude`. |
| `AIENG_CODEX_CLI_COMMAND` | Override the Codex command; default `codex`. |
| `AIENG_LOCAL_AGENT_WORKSPACE` | Optional workspace passed to Claude Code via `--add-dir`. |
| `AIENG_DISABLE_CLAUDE_CODE_ADAPTER=1` | Force Claude adapter to blocked. |
| `AIENG_DISABLE_CODEX_CLI_ADAPTER=1` | Force Codex adapter to blocked. |
| `AIENG_RUN_LOCAL_AGENT_SMOKE=1` | Enable the real Claude Code smoke test. |
| `AIENG_RUN_CODEX_LOCAL_AGENT_SMOKE=1` | Enable the real Codex CLI smoke test. |

Safe probe commands:

```powershell
claude --help
codex --help
codex exec --help
```

Claude Code expected support:

- `-p` / `--print`
- `--bare`
- `--no-session-persistence`
- `--output-format json`
- `--json-schema`
- `--permission-mode plan`
- `--tools ""`

Codex expected support:

- `codex exec`
- `--output-schema`
- `--sandbox read-only`
- root option `--ask-for-approval never`
- `--output-last-message`

## Verification Commands

Backend baseline:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_context.py tests/test_runtime_tools.py tests/test_agent_observation.py
```

Autopilot tests:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_policy.py tests/test_agent_autopilot_adapters.py tests/test_agent_autopilot_store.py tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_local_smoke.py
```

Claude Code smoke, explicit only:

```powershell
cd aieng-ui/backend
$env:AIENG_RUN_LOCAL_AGENT_SMOKE="1"
python -m pytest tests/test_agent_autopilot_local_smoke.py
```

Codex CLI smoke, explicit only:

```powershell
cd aieng-ui/backend
$env:AIENG_RUN_CODEX_LOCAL_AGENT_SMOKE="1"
python -m pytest tests/test_agent_autopilot_local_smoke.py::test_codex_cli_local_smoke
```

Frontend:

```powershell
cd aieng-ui/frontend
npm run build
```

Live UI sync:

- `/api/agent-activity/stream` emits `project_changed` and `viewer_asset_changed` events for project-mutating tools and CAD preview writes.
- The frontend shows `Live`, `Reconnecting`, or `Polling` in the Chat header. During stream failure or active agent work, it polls the selected project every 2.5s as a fallback.
- Manual browser refresh should not be required after `cad.execute_build123d`, `/generate-cad`, or `/refine-cad` when the backend is running and `AIENG_BACKEND_URL` is set.

## Known Gaps

- Codex structured smoke passed locally with Codex v0.134.0. The adapter uses a
  strict `input_json` string field because OpenAI structured output rejects
  arbitrary nested tool input objects.
- Claude Code structured smoke passed locally after using `--bare`,
  `--no-session-persistence`, stdin prompt input, and parsing the CLI
  `structured_output` wrapper. The adapter cleans up timed-out process trees on
  Windows.
- The vertical slice is covered through Workbench-side deterministic tests and
  fake-agent demo checkpoints. A full live Claude/Codex natural-language CAD
  run remains useful as a manual product acceptance pass.

## Resetting Local Runs

To clear local Autopilot run state:

```powershell
Remove-Item -Recurse -Force aieng-ui/data/agent_autopilot/runs
```

Do this only for local development; project package audit logs are separate.

## Next Recommended Task

Run a live Local Agent CAD request in the Workbench UI using the adapter that is
available on the target machine, then record the resulting screenshots and any
adapter diagnostics in the demo doc.
