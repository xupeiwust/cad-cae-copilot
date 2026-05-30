# Chat Agent Transcript Demo

Last updated: 2026-05-30

## Setup

```powershell
cd aieng-ui/backend
python -m uvicorn app.main:app --reload
```

```powershell
cd aieng-ui/frontend
npm run dev
```

Open the frontend URL shown by Vite, create or select a project, and keep the
settings drawer's `Chat Transcript` toggle enabled.

## Scenario

1. Send: `Create a CNC aluminum motor bracket with four mounting holes and two ribs.`
2. Expect a user transcript message followed by compact status/tool lines such
   as `Autopilot run started`, `aieng.agent_context`, and an approval row for
   `cad.execute_build123d`.
3. Open the approval details. Confirm the target project, side-effect summary,
   risk summary, and code preview match the request.
4. Approve the CAD write.
5. Expect `tool_started`, `tool_completed`, optional `cad.critique`, and an
   artifact line with named parts or preview information.
6. While the run is active, send a follow-up such as `Make the ribs taller but
   keep the hole pattern unchanged.` Expect the message to appear immediately
   and queue or route to the active run instead of starting an unrelated run.
7. Use `Stop` during a running step. Expect a cancellation transcript line and
   no later agent step after the cancellation checkpoint.
8. Refresh the browser. The same chat messages and agent event lines should
   replay from `chat_messages` plus `agent_events`.

## Verification Commands

```powershell
cd aieng-ui/frontend
npm run build
```

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_autopilot_engine.py tests/test_persistence.py tests/test_agent_activity.py tests/test_agent_autopilot_schema.py
```
