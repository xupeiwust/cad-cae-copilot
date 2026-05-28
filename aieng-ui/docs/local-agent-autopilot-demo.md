# Local Agent Autopilot Demo

Last updated: 2026-05-28

This manual demo validates the MVP path for a simple bracket. It assumes the
backend and frontend are running locally and at least one local adapter is
available.

## 1. Start the Workbench

```powershell
cd aieng-ui/backend
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd aieng-ui/frontend
npm run dev
```

Open `http://localhost:5173`.

## 2. Confirm Local Agent Capability

```powershell
curl http://localhost:8000/api/local-agents/capabilities
```

Expected:

- Claude Code is `available` when `claude -p` JSON/schema mode is detected.
- Codex is `available` only when `codex exec --output-schema` and read-only
  sandbox controls are detected.
- Missing or unsupported CLIs are reported as `missing` or `blocked`, not as a
  server error.

## 3. Create or Select a Project

Use an existing project or create a new one in the Workbench. The demo is easier
to inspect when the project is empty or disposable.

## 4. Run a CAD Request

Select `Local Agent` in the chat connection dropdown, then send:

```text
Create a simple aluminum L bracket with two bolt holes. Name the vertical leg,
horizontal leg, and holes. Stop before writing CAD and ask for approval.
```

Expected:

- The chat shows a Local Agent run card.
- If the agent asks for `cad.execute_build123d`, the card pauses for approval.
- The approval copy names `cad.execute_build123d`.

Approve the action.

Expected after approval:

- The backend executes through Workbench runtime, not through the CLI agent.
- The run receives a tool-result observation.
- The project preview/topology should refresh if the CAD runtime succeeds.

## 5. Run a Preprocessing Request

Select a suitable face in the viewer when available, then send:

```text
Use the selected face as the fixed support. Apply a 500 N load to the opposite
hole region and prepare the solver input, but do not run the solver yet.
```

Expected:

- Safe setup/preflight tools can run automatically under policy.
- The agent should use selected `@face:` pointers when they are available.
- If geometry is ambiguous, the agent asks a concise clarification question.

## 6. Solver Approval Check

Send:

```text
Run the solver and summarize max stress and displacement.
```

Expected:

- `cae.run_solver` pauses for explicit approval.
- Rejection leaves the solver unrun.
- Approval executes through Workbench runtime, then post-processing can continue
  automatically once the vertical slice is completed.

## Current Expected Gaps

As of 2026-05-28, the Workbench-side CAD/CAE vertical slices are implemented and
covered by backend tests. A live natural-language run with a real local adapter
is still the best product acceptance pass; if it blocks, record the exact
adapter diagnostic and update the task ledger.

## Deterministic Script

For a safe API-level checkpoint demo that does not write CAD, run:

```powershell
cd aieng-ui/backend
python scripts/demo_local_agent_autopilot.py --project-id demo_autopilot
```

Expected:

- Prints local adapter capability diagnostics.
- Starts a fake Local Agent run.
- Stops at a `cad.execute_build123d` approval checkpoint.

To continue in dry-run mode:

```powershell
python scripts/demo_local_agent_autopilot.py --project-id demo_autopilot --approve
```
