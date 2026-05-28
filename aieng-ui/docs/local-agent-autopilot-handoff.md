# Local Agent Autopilot Handoff

Last updated: 2026-05-28

## Current Implementation State

Local Agent Autopilot is implemented through:

- Backend package: `backend/app/agent_autopilot/`
- Capability endpoint: `GET /api/local-agents/capabilities`
- Run endpoints:
  - `POST /api/agent/autopilot/runs`
  - `GET /api/agent/autopilot/runs/{run_id}`
  - `POST /api/agent/autopilot/runs/{run_id}/continue`
  - `POST /api/agent/autopilot/runs/{run_id}/cancel`
- Frontend connection id: `local-agent`
- Run state directory: `aieng-ui/data/agent_autopilot/runs/`

The local agent never receives permission to call Workbench tools directly. It
returns one JSON action at a time; the backend validates the action, applies
policy, and executes only Workbench runtime tools.

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
