# Chat Agent Current Flow Notes

Last updated: 2026-05-30

## Mutation Paths

Frontend chat state is still coordinated by `frontend/src/app/useWorkbenchApp.ts`.
The main mutation paths are:

- `setPersistentChatHistory()` persists new `ChatHistoryItem` rows through
  `POST /api/projects/{project_id}/chat-messages`.
- `useAgentRuns.ts` appends user messages, runtime plan results, Autopilot run
  snapshots, approval/reply updates, and local error messages.
- `useAgentActivityStream.ts` upserts persisted chat messages from
  `chat_message`, upserts Autopilot snapshots from `autopilot_update`, and now
  records typed transcript events from `agent_message`, `tool_started`,
  `tool_completed`, `tool_failed`, `approval_requested`, `approval_resolved`,
  `artifact_ready`, `run_status_changed`, and `run_cancelled`.
- `useEngineeringActions.ts` appends direct CAD/CAE result messages for
  non-Autopilot flows.
- Session load in `useWorkbenchApp.ts` fetches persisted chat messages and
  persisted agent events, then refreshes any active Autopilot run snapshot.
- Session switching and project switching clear local `chatHistory` and
  `agentEvents` before loading the selected session.

## Risky Coupling Points

- `useWorkbenchApp.ts` still owns project selection, session loading,
  persistence, active run routing, and viewer refresh wiring. This remains the
  largest maintainability risk and is the next extraction target.
- `ChatPanel.tsx` keeps the legacy card path while transcript mode is the
  default. The fallback is intentional during parity testing, but it should not
  regain new behavior.
- Chat messages and agent events are persisted separately. Transcript replay
  merges them by timestamp and stable source id, so event ids must remain
  idempotent.
- `autopilot_update` snapshots remain the compatibility fallback. New live UI
  rows should prefer typed events when available.

## Current Replay Sources

Authoritative replay data now comes from:

- `chat_messages`: user and assistant text compatibility rows.
- `agent_events`: append-only transcript events keyed by `event_id`.
- `agent_autopilot/runs/{run_id}.json`: full run snapshots used for fallback
  and stale active-run refresh.

The transcript mapper lives in `frontend/src/app/chatTranscript.ts` and is pure:
it converts persisted chat rows, run snapshots, and typed agent events into
compact transcript items without depending on React.
