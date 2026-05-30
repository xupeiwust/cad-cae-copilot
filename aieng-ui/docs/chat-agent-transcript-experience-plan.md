# Chat Agent Transcript Experience Refactor Plan

Status: **Implementation complete; awaiting product review**
Last updated: **2026-05-30**
Owner: **AIENG workbench maintainers + handoff LLM agents**

## Purpose

This document is the implementation handoff plan for changing the `aieng-ui`
chat experience from card-heavy run summaries into a Codex Desktop-like agent
transcript.

The target experience is:

```text
User
Create a CNC aluminum motor bracket with four mounting holes.

Agent
I will inspect the current project and check whether reusable geometry exists.

  done  aieng.agent_context
  done  cad.get_source

I am ready to write a new CAD model with a base plate, four-hole mounting
pattern, and two ribs. This will update the current project geometry.

  approval  cad.execute_build123d  [Review] [Approve] [Reject]

Agent
Geometry is built and the viewer has refreshed.

  done  cad.execute_build123d
  done  cad.critique
  artifact  GLB preview ready, 4 named parts
```

The chat should feel like a continuous working transcript. Tool calls are
compact timeline lines, approvals are inline decisions, detailed JSON/code stays
collapsed by default, and viewer/artifact updates appear as short status lines.

## Non-goals

- Do not rebuild the whole agent/autopilot system from scratch.
- Do not remove approval gates or weaken CAD/CAE execution policy.
- Do not make `aieng/src/` a capability reference. It is legacy and should not
  guide this work.
- Do not add another large orchestration component into `frontend/src/App.tsx`.
- Do not replace one oversized chat component with another oversized chat
  component.

## Current State

Relevant frontend files:

| Area | File | Current role |
|---|---|---|
| App orchestration | `frontend/src/app/useWorkbenchApp.ts` | Owns selected project, sessions, chat history, run routing, active session sync, viewer refresh integration. |
| Agent run hook | `frontend/src/app/useAgentRuns.ts` | Starts LLM/local autopilot runs, handles approval/reject/cancel, appends summarized run cards. |
| Live stream hook | `frontend/src/app/useAgentActivityStream.ts` | Subscribes to `/api/agent-activity/stream`, merges `autopilot_update`, chat messages, CAD build progress, and viewer refresh events. |
| Chat UI | `frontend/src/components/panels/ChatPanel.tsx` | Renders message bubbles, autopilot cards, approval cards, CAD/simulation progress, input toolbar. |
| Agent display helpers | `frontend/src/app/workbenchHelpers.ts` | Produces one-line autopilot summaries and labels. |
| Existing agent cards | `frontend/src/components/agent/` | Plan/result/activity/approval cards used by current chat. |
| Types | `frontend/src/appTypes.ts`, `frontend/src/types.ts` | Chat item and autopilot state types. |

Relevant backend files:

| Area | File | Current role |
|---|---|---|
| Autopilot engine | `backend/app/agent_autopilot/engine.py` | Agent step loop, tool execution, approval continuation, follow-ups, cancellation state update. |
| Autopilot schema | `backend/app/agent_autopilot/schema.py` | Run state, observation, approval, action schema. |
| Prompt builder | `backend/app/agent_autopilot/prompts.py` | Tells the agent how to choose tools and write user-visible summaries. |
| API routes/SSE | `backend/app/app_factory.py` | Autopilot REST endpoints, SSE stream, chat session/message persistence, direct tool bridge. |
| Activity broker | `backend/app/agent_activity.py` | In-process pub/sub for live UI events. |
| DB helpers | `backend/app/db.py` | Chat sessions/messages and settings persistence. |

Important current behavior:

- `llm-api` and `local-agent` chat submissions both use Autopilot runs.
- The backend returns an initial run state quickly, then continues in a worker
  thread.
- The UI receives `autopilot_update` snapshots over SSE.
- The UI currently renders one assistant bubble containing an `autopilotRun`
  card. Details show only the last few observations.
- User replies to a `chatting` run reuse the same `continue` API shape as
  approvals.
- `cancel_run()` currently marks a run cancelled but does not provide a
  guaranteed cooperative cancellation token for long-running work.

## Desired Product Principles

1. **Transcript first.** The chat log is the source of user-visible progress.
   Cards are secondary and only used for dense review details.
2. **Tool calls are compact.** A tool call should usually take one line:
   status, tool name, short summary, optional disclosure.
3. **Approvals are inline.** Approval UI lives where the pending tool appears,
   with a concise risk summary and a collapsible review panel.
4. **Agent text is visible.** `user_message`, `thought_summary`, final messages,
   and ask-user text should become normal assistant text when safe to show.
5. **Run state is replayable.** A refreshed browser should rebuild the same
   transcript without relying on fragile UI-only state.
6. **The user can steer.** Running conversations should support stop, follow-up,
   and revision requests without starting unrelated duplicate runs.
7. **Viewer updates are part of the transcript.** CAD/CAE artifacts should
   create short artifact lines with links/chips that affect the viewer.

## Status Management Rules

Use this status vocabulary in the task ledger:

| Status | Meaning |
|---|---|
| `TODO` | Not started. |
| `IN_PROGRESS` | Someone is actively implementing this task. Only one task per phase should usually be `IN_PROGRESS`. |
| `BLOCKED` | Work cannot continue without a concrete dependency or decision. Notes must name the blocker. |
| `REVIEW` | Implementation is complete and awaiting human/agent review. Verification command should be recorded. |
| `DONE` | Merged or accepted. Verification must be recorded. |
| `SKIPPED` | Intentionally not done. Notes must explain why. |

Every agent session that changes implementation must update the ledger row for
the task it touched:

- `Status`
- `Owner/session`
- `Files changed`
- `Verification`
- `Notes`

If a task reveals new subtasks, add rows instead of hiding them in notes.

## Phase 0 - Baseline, Scope Lock, and Feature Flag

Goal: establish a safe baseline before refactoring the chat UI.

### CAT-P0-T01 - Capture Current Chat Flow Baseline

Objective:

- Document the current message lifecycle from input to rendered run card.
- Identify all code paths that write to `chatHistory`.

Files to inspect:

- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/app/useAgentRuns.ts`
- `frontend/src/app/useAgentActivityStream.ts`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/app/runtimeRunChat.ts`
- `frontend/src/app/workbenchHelpers.ts`
- `backend/app/app_factory.py`

Steps:

1. Search for `setChatHistory`, `setPersistentChatHistory`, `autopilotRun`,
   `chat_message`, and `autopilot_update`.
2. Add a short "Current flow notes" section to this document or a sibling
   scratch note under `aieng-ui/docs/`.
3. List every source that can append, update, or replace chat messages.
4. Record risky coupling points, especially persistence and session switching.

Acceptance:

- A future implementer can see all chat mutation paths before editing.
- No source code behavior is changed.

Verification:

- Documentation review.

### CAT-P0-T02 - Add a Transcript Feature Flag

Objective:

- Allow the new transcript UI to be developed without breaking the existing
  card-based UI.

Likely files:

- `frontend/src/appConstants.ts`
- `frontend/src/app/useBrowserStorageState.ts`
- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/settings/RuntimeSettingsDrawer.tsx` or a small debug
  toggle if settings already has a suitable place.

Steps:

1. Add a persisted boolean setting such as `aieng-ui.chat-transcript-v2`.
2. Default it to `false`.
3. Thread the flag into `ChatPanel`.
4. Render the current card UI when disabled.
5. Render a placeholder transcript container when enabled.
6. Keep all existing send/approval behavior unchanged.

Acceptance:

- Switching the flag changes only the rendering path.
- Existing chat works with the flag off.
- The flag can be toggled without losing the active session.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual: send one message with flag off, toggle on, toggle off.

### CAT-P0-T03 - Add Snapshot Tests or Focused Unit Tests for Mapping Inputs

Objective:

- Prepare for safe refactors by locking down how current run states map to UI
  data.

Likely files:

- `frontend/src/app/chatTranscript.ts` (new)
- `frontend/src/app/chatTranscript.test.ts` or existing test setup if present.
- If no frontend test harness exists, add backend-style fixtures as JSON and
  document manual verification instead.

Steps:

1. Create sample `AutopilotRunState` objects for running, awaiting approval,
   completed, failed, blocked, and chatting.
2. Do not build full UI yet.
3. Define expected lightweight transcript outputs in plain objects.
4. If frontend tests are available, add tests. If not, add fixtures and keep
   verification through `npm run build` until a test harness is introduced.

Acceptance:

- At least six representative run states can be converted deterministically.
- The mapping is independent of React components.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Frontend unit test command if available.

Phase 0 exit criteria:

- Existing UI remains intact.
- A feature flag exists.
- Current chat mutation paths are documented.
- Transcript mapping can be developed independently.

## Phase 1 - Transcript Domain Model

Goal: introduce a frontend transcript model that can represent messages, tool
lines, approvals, artifacts, and errors without changing backend protocols.

### CAT-P1-T01 - Define Transcript Types

Objective:

- Stop overloading `ChatHistoryItem` for every display concern.

Likely files:

- `frontend/src/appTypes.ts`
- `frontend/src/app/chatTranscript.ts` (new)

Proposed types:

```ts
export type ChatTranscriptItem =
  | TranscriptUserMessage
  | TranscriptAgentMessage
  | TranscriptToolLine
  | TranscriptApprovalLine
  | TranscriptArtifactLine
  | TranscriptStatusLine
  | TranscriptErrorLine;
```

Required common fields:

```ts
type TranscriptBase = {
  id: string;
  kind: "message" | "tool" | "approval" | "artifact" | "status" | "error";
  runId?: string | null;
  sessionId?: string | null;
  projectId?: string | null;
  createdAt: string;
};
```

Steps:

1. Add transcript types without removing `ChatHistoryItem`.
2. Include `detail?: unknown` for collapsible raw payloads.
3. Include stable `sourceId` fields for dedupe across SSE and persisted
   snapshots.
4. Keep status values small: `pending`, `running`, `done`, `failed`,
   `blocked`, `approval`.

Acceptance:

- Types compile.
- No existing component is forced to migrate yet.

Verification:

- `cd aieng-ui/frontend && npm run build`

### CAT-P1-T02 - Implement `runToTranscriptItems`

Objective:

- Convert existing `AutopilotRunState` snapshots into compact transcript items.

Likely files:

- `frontend/src/app/chatTranscript.ts`
- `frontend/src/app/workbenchHelpers.ts`

Mapping rules:

- `run.message` stays represented by the existing user message item; do not
  duplicate it unless the run appears without a paired user message.
- `observation.kind === "context"` -> status line.
- `observation.kind === "agent_activity"` with `tool_name` -> running/pending
  tool line.
- `observation.kind === "tool_result"` -> done tool line.
- `observation.kind === "tool_error"` -> failed tool line or error line.
- `observation.kind === "approval_required"` and `run.pending_approval` ->
  approval line.
- `observation.kind === "user_message"` from agent `chat`/`ask_user` -> agent
  message.
- `observation.kind === "final"` or `run.final_message` -> agent message.
- Tool outputs containing preview/artifact/named part fields -> artifact line.

Steps:

1. Implement the mapper as a pure function.
2. Deduplicate repeated status updates by `runId + observation.id`.
3. For current running tool, show the newest relevant observation.
4. Keep raw observation payloads in `detail`.
5. Ensure output order is stable by `created_at` and original index.

Acceptance:

- Running, completed, failed, approval, and chatting runs produce readable
  transcript items.
- The mapper never throws on unknown observation shapes.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Unit tests or fixture checks from CAT-P0-T03.

### CAT-P1-T03 - Convert Persisted Chat Items to Transcript Items

Objective:

- Make persisted session replay work with both legacy messages and new
  transcript rendering.

Likely files:

- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/app/chatTranscript.ts`

Steps:

1. Add `chatHistoryToTranscriptItems(chatHistory)` pure function.
2. Convert normal user/assistant messages to message items.
3. For entries with `autopilotRun`, append `runToTranscriptItems`.
4. For legacy `cadResult`, `simulationResult`, `preprocessResult`, and
   `artifactPaths`, generate artifact/status lines.
5. Preserve legacy rendering when the feature flag is off.

Acceptance:

- A previously saved session can be displayed in transcript mode.
- Legacy result payloads do not disappear.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual: load an existing session with an autopilot card and switch transcript
  flag on.

Phase 1 exit criteria:

- Transcript data model exists.
- Existing run snapshots can render as transcript items.
- No backend change is required.

## Phase 2 - Minimal Transcript UI

Goal: replace the large autopilot card path with compact transcript rendering
behind the feature flag.

### CAT-P2-T01 - Create Transcript Components

Objective:

- Move transcript rendering out of `ChatPanel.tsx`.

New files:

- `frontend/src/components/chat/ChatTranscript.tsx`
- `frontend/src/components/chat/TranscriptMessage.tsx`
- `frontend/src/components/chat/ToolLine.tsx`
- `frontend/src/components/chat/ApprovalLine.tsx`
- `frontend/src/components/chat/ArtifactLine.tsx`
- `frontend/src/components/chat/EventDetail.tsx`

Steps:

1. `ChatTranscript` receives transcript items and callback props.
2. `TranscriptMessage` renders user/agent text using existing `MarkdownText`
   and `PointerText`.
3. `ToolLine` renders one compact row with status, tool, summary, elapsed if
   available, and optional details disclosure.
4. `ApprovalLine` renders inline review/approve/reject/cancel controls.
5. `ArtifactLine` renders viewer/artifact/named-part updates.
6. `EventDetail` handles raw JSON/code/details in a collapsed disclosure.

Acceptance:

- `ChatPanel.tsx` delegates transcript rendering instead of embedding the
  entire UI.
- Components are focused and reusable.

Verification:

- `cd aieng-ui/frontend && npm run build`

### CAT-P2-T02 - Wire Transcript Rendering into `ChatPanel`

Objective:

- Use transcript mode when the feature flag is enabled.

Likely files:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/app/useWorkbenchApp.ts`

Steps:

1. Compute `transcriptItems` from `chatHistory`.
2. Pass approval handlers, artifact viewer handlers, heatmap handlers, and
   viewer callbacks into `ChatTranscript`.
3. Keep the old bubble/card rendering intact behind the flag.
4. Keep `cadGenerationProgress`, `simulationProgress`, and current activity line
   visible, but make them compact in transcript mode.
5. Ensure empty state copy still works.

Acceptance:

- Feature flag on: autopilot runs show as compact transcript lines.
- Feature flag off: existing card UI is unchanged.
- Approve/reject/cancel still work.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual: start fake or LLM autopilot run, approve/reject if prompted.

### CAT-P2-T03 - Add Transcript Styling

Objective:

- Make the transcript compact, readable, and less card-like.

Likely files:

- `frontend/src/style.css`

Design rules:

- Avoid nested cards.
- Use small status glyphs or existing icons.
- Keep tool rows visually subordinate to agent text.
- Details should be collapsed by default.
- Buttons in approval rows should be compact and aligned.
- Text must fit on narrow viewports.

Steps:

1. Add `.chat-transcript`, `.transcript-message`, `.tool-line`,
   `.approval-line`, `.artifact-line`, and `.event-detail` classes.
2. Use restrained borders/dividers rather than large filled panels.
3. Ensure mobile wrapping does not overlap controls.
4. Keep contrast accessible.

Acceptance:

- Transcript reads like a continuous conversation.
- Tool details do not dominate the UI.
- Approval controls are visible but compact.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Browser/manual visual QA on desktop and mobile width.

### CAT-P2-T04 - Improve Auto-scroll Behavior

Objective:

- Avoid pulling users away from older transcript details while a run is active.

Likely files:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/chat/ChatTranscript.tsx`

Steps:

1. Detect whether the chat log is near the bottom before auto-scrolling.
2. Auto-scroll only when near bottom or when the user sends a message.
3. When new activity arrives while scrolled up, show a compact "new activity"
   button.
4. Clicking the button scrolls to bottom.

Acceptance:

- Users can inspect earlier tool details without being forced to bottom.
- New activity remains discoverable.

Verification:

- Manual: run an autopilot task, scroll up, observe new activity button.

Phase 2 exit criteria:

- Transcript UI is usable behind a flag.
- Old UI remains available.
- Approval and artifact links still function.

## Phase 3 - Approval, Reply, and Revision Semantics

Goal: separate approval from conversation continuation and make review actions
clear.

### CAT-P3-T01 - Add Explicit Reply API for Chatting Runs

Objective:

- Stop using approval continuation semantics for normal user replies.

Likely files:

- `backend/app/app_factory.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/tests/test_agent_autopilot_engine.py`
- `backend/tests/test_api.py`
- `frontend/src/api.ts`
- `frontend/src/app/useAgentRuns.ts`
- `frontend/src/app/useWorkbenchApp.ts`

Backend API:

```text
POST /api/agent/autopilot/runs/{run_id}/reply
Body: { "message": "..." }
```

Steps:

1. Add backend route that only accepts active `chatting`, `blocked`, or
   `running` states according to policy.
2. Add `AutopilotEngine.reply_to_run(run_id, message)`.
3. For `chatting`, append user message observation and resume step loop.
4. For `awaiting_approval`, do not approve. Record user message as a revision
   request and let the agent choose a new action.
5. Add frontend `api.replyAutopilot`.
6. Change `sendUnified()` so `chatting` runs use reply, not continue/approve.

Acceptance:

- User replies no longer set `approved=true`.
- Approval and conversation are separate concepts in code and UI.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py::test_agent_autopilot_continue_and_cancel`
- `cd aieng-ui/frontend && npm run build`

### CAT-P3-T02 - Redesign Approval Review Payload

Objective:

- Give users enough information to approve safely without opening raw JSON first.

Likely files:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/agent_autopilot/schema.py`
- `backend/app/agent_autopilot/policy.py`
- `frontend/src/components/chat/ApprovalLine.tsx`
- `frontend/src/app/chatTranscript.ts`

Steps:

1. Extend approval data with optional fields:
   - `side_effect_summary`
   - `risk_summary`
   - `target_project_id`
   - `code_preview`
   - `artifact_preview`
   - `recommended_action`
2. Populate these fields for `cad.execute_build123d`, `cad.edit_parameter`,
   `aieng.convert`, and `cae.run_solver`.
3. Render the concise fields directly in `ApprovalLine`.
4. Keep raw input JSON/code in `EventDetail`.
5. Add "Ask agent to revise" action that sends a reply instead of rejecting.

Acceptance:

- CAD approval clearly says what will change.
- Solver approval clearly says an external solver may run.
- Users can ask for revision without losing the run.

Verification:

- Backend tests for approval payload fields.
- `cd aieng-ui/frontend && npm run build`
- Manual approval checkpoint.

### CAT-P3-T03 - Use Agent `user_message` as Display Text

Objective:

- Let the agent provide short user-visible progress messages instead of the UI
  inventing all summaries.

Likely files:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/agent_autopilot/prompts.py`
- `frontend/src/app/chatTranscript.ts`
- `frontend/src/app/workbenchHelpers.ts`
- `backend/tests/test_agent_autopilot_prompts.py`
- `backend/tests/test_agent_autopilot_engine.py`

Steps:

1. Strengthen prompt rules:
   - `user_message` is concise user-visible progress.
   - It must not include hidden chain-of-thought.
   - It should explain approval side effects before mutation.
2. When an action includes `user_message`, record it as an observation kind such
   as `agent_message` or reuse `user_message` with clear source metadata.
3. Map it to an assistant transcript message.
4. Avoid duplicate messages when final message repeats the same content.

Acceptance:

- Agent progress appears as normal assistant text.
- Tool rows remain compact.
- No private reasoning is displayed.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_prompts.py tests/test_agent_autopilot_engine.py`
- `cd aieng-ui/frontend && npm run build`

Phase 3 exit criteria:

- Approval and reply flows are semantically separate.
- Approval review is informative.
- Agent-authored visible messages appear in the transcript.

## Phase 4 - Typed SSE Events and Append-only Event Store

Goal: make live transcript updates incremental and replayable instead of
rebuilding from whole run snapshots.

### CAT-P4-T01 - Define Backend Agent Event Schema

Objective:

- Establish a stable event contract for the transcript UI.

Likely files:

- `backend/app/agent_autopilot/schema.py`
- `backend/app/agent_activity.py`
- `backend/tests/test_agent_autopilot_schema.py`

Event types:

```text
agent_message
tool_started
tool_completed
tool_failed
approval_requested
approval_resolved
artifact_ready
viewer_refreshed
run_status_changed
run_completed
run_failed
run_cancelled
```

Required fields:

```text
event_id, type, run_id, project_id, session_id, created_at
```

Steps:

1. Add Pydantic models or typed dict helpers for agent events.
2. Provide a safe `publish_agent_event()` helper.
3. Keep existing `autopilot_update` for compatibility.
4. Add tests for serialization and required fields.

Acceptance:

- Event payloads are deterministic and documented in code.
- Existing SSE subscribers are not broken.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_activity.py`

### CAT-P4-T02 - Publish Fine-grained Events from Autopilot Engine

Objective:

- Emit transcript-ready events as work happens.

Likely files:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`
- `backend/tests/test_agent_autopilot_engine.py`
- `backend/tests/test_agent_activity.py`

Steps:

1. Emit `agent_message` when `user_message`, `chat`, `ask_user`, or final text
   is available.
2. Emit `tool_started` immediately before a workbench tool executes.
3. Emit `tool_completed` or `tool_failed` after execution.
4. Emit `approval_requested` when policy requires approval.
5. Emit `approval_resolved` after approve/reject/revision.
6. Emit `artifact_ready` for tool outputs containing preview URLs, artifact
   paths, named parts, or result files.
7. Emit `run_status_changed` for major status transitions.

Acceptance:

- Frontend can update transcript without waiting for full run snapshots.
- Full run snapshots are still published for fallback.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_activity.py`

### CAT-P4-T03 - Add Append-only Event Persistence

Objective:

- Persist transcript event history for reliable session replay.

Likely files:

- `backend/app/db.py`
- `backend/app/app_factory.py`
- `backend/tests/test_persistence.py`
- `backend/tests/test_api.py`

Proposed storage:

```text
agent_events
  id integer primary key
  event_id text unique
  run_id text
  project_id text
  session_id text
  type text
  status text nullable
  content text nullable
  payload_json text
  created_at text
```

API:

```text
GET /api/projects/{project_id}/agent-events?session_id=...
```

Steps:

1. Add DB migration/initialization for `agent_events`.
2. Insert every typed agent event as it is published.
3. Add an endpoint to list events by project/session.
4. Make event insertion idempotent by `event_id`.
5. Keep `chat_messages` unchanged for user/assistant text compatibility.

Acceptance:

- Page refresh can replay events even after the run is terminal.
- Duplicate SSE events do not create duplicate persisted rows.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_persistence.py tests/test_api.py`

### CAT-P4-T04 - Consume Typed Events in Frontend

Objective:

- Update transcript incrementally from event stream.

Likely files:

- `frontend/src/app/useAgentActivityStream.ts`
- `frontend/src/app/chatTranscript.ts`
- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/api.ts`

Steps:

1. Add API method to fetch persisted agent events.
2. Add `agentEventToTranscriptItems(event)` pure function.
3. In SSE handler, apply typed events to transcript state.
4. Continue to process `autopilot_update` as fallback.
5. Dedupe by `event_id` or stable source key.
6. On session load, fetch chat messages and agent events, then merge by time.

Acceptance:

- Live updates appear as individual transcript rows.
- Refresh preserves the same transcript.
- Compatibility remains for backends that only emit `autopilot_update`.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual: start run, refresh page during/after run, compare transcript.

Phase 4 exit criteria:

- Typed live events exist.
- Events are persisted.
- Frontend transcript can render from events plus legacy snapshots.

## Phase 5 - Interrupt, Queue, and Cooperative Cancellation

Goal: make the agent feel steerable while it works.

### CAT-P5-T01 - Add Cooperative Cancellation Tokens

Objective:

- Make cancel/stop more than a status label.

Likely files:

- `backend/app/agent_autopilot/store.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`
- `backend/tests/test_agent_autopilot_engine.py`

Steps:

1. Add a cancellation marker in store or a lightweight in-process registry.
2. Check cancellation before each adapter invocation.
3. Check cancellation before each tool execution.
4. Check cancellation after each tool returns.
5. For subprocess adapters, terminate timed/cancelled child processes where
   possible.
6. Mark run `cancelled` and emit `run_cancelled`.

Acceptance:

- Cancelling a run prevents later steps from executing.
- Cancelling during a long adapter call attempts subprocess termination.
- Already-started non-interruptible tool calls finish honestly and then stop.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_adapters.py`

### CAT-P5-T02 - Allow Follow-up Input During Active Runs

Objective:

- Do not disable the text input whenever an agent is busy.

Likely files:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/app/useAgentRuns.ts`

Steps:

1. Replace global textarea disabled behavior with mode-aware behavior.
2. If no active run, send starts a new run.
3. If a run is `running`, send creates a queued follow-up or interrupt message.
4. If a run is `awaiting_approval`, send is treated as a revision/comment.
5. If a run is `chatting`, send replies to the run.
6. Show clear button labels: `Send`, `Send follow-up`, `Ask revision`.

Acceptance:

- User can type while the agent works.
- The UI clearly shows whether the message will start, reply, or queue.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual active-run interaction.

### CAT-P5-T03 - Add Follow-up Queue Semantics

Objective:

- Preserve user follow-ups that arrive while a tool is running.

Likely files:

- `backend/app/agent_autopilot/schema.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`
- `backend/tests/test_agent_autopilot_engine.py`
- `frontend/src/app/chatTranscript.ts`

Steps:

1. Add `queued_user_messages` or equivalent to run state.
2. Add endpoint:
   `POST /api/agent/autopilot/runs/{run_id}/follow-up`.
3. If a tool is currently running, store the message and emit a status event.
4. Before the next adapter invocation, include queued messages in observations.
5. Clear messages once consumed.
6. Render queued messages in transcript as user messages with `queued` status.

Acceptance:

- A follow-up sent during work influences the next agent step.
- The user sees that the follow-up is queued, not lost.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py`
- `cd aieng-ui/frontend && npm run build`

### CAT-P5-T04 - Add Stop Button and Status Copy

Objective:

- Expose cancellation in a Codex-like way.

Likely files:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/chat/ChatTranscript.tsx`
- `frontend/src/style.css`

Steps:

1. Add a compact `Stop` button near the input when a run is active.
2. Disable only while the cancel request is in flight.
3. Add transcript line when stop is requested and when cancellation completes.
4. Preserve approval buttons if a run is waiting for approval.

Acceptance:

- User can stop active runs from the chat input area.
- Transcript records cancellation.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual cancel during running and awaiting approval states.

Phase 5 exit criteria:

- Runs can be stopped cooperatively.
- Users can continue typing while a run is active.
- Follow-ups are queued or routed with clear semantics.

## Phase 6 - Viewer, Artifact, and Pointer Integration

Goal: make CAD/CAE outputs visible as lightweight transcript events and connect
them to the viewer.

### CAT-P6-T01 - Normalize Artifact Events

Objective:

- Convert CAD/CAE outputs into consistent artifact transcript lines.

Likely files:

- `frontend/src/app/chatTranscript.ts`
- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`

Artifact summary fields:

- `preview_url`
- `preview_format`
- `artifact_paths`
- `named_parts`
- `parts_added`
- `geometry_report`
- `solver_run_id`
- `result_summary`

Steps:

1. Detect these fields in tool outputs.
2. Emit `artifact_ready` backend events where possible.
3. Map legacy tool outputs to artifact transcript lines.
4. Keep raw output collapsed.

Acceptance:

- CAD generation success produces a short viewer/artifact line.
- Solver/postprocess success produces a short result/artifact line.

Verification:

- Backend engine tests for emitted artifact event.
- `cd aieng-ui/frontend && npm run build`

### CAT-P6-T02 - Add Named Part and Pointer Chips

Objective:

- Make generated parts and topology references actionable from chat.

Likely files:

- `frontend/src/components/chat/ArtifactLine.tsx`
- `frontend/src/components/PointerText.tsx`
- `frontend/src/app/useGeometryPointers.ts`
- `frontend/src/components/ViewerPane.tsx`

Steps:

1. Render named parts as compact chips.
2. Render pointer strings through existing `PointerText`.
3. If a chip can map to faces/features, trigger highlight.
4. If mapping is unavailable, show a details disclosure with the available
   topology data.
5. Avoid adding heavy cards for part lists.

Acceptance:

- Users can identify which parts were created.
- Pointer references remain clickable/readable.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual CAD generation with named parts.

### CAT-P6-T03 - Viewer Refresh Feedback

Objective:

- Make viewer refresh visible without noisy notices.

Likely files:

- `frontend/src/app/useAgentActivityStream.ts`
- `frontend/src/app/chatTranscript.ts`
- `frontend/src/components/chat/ArtifactLine.tsx`

Steps:

1. Convert `viewer_asset_changed` into an artifact/status transcript line.
2. Include preview format and timestamp.
3. If viewer refresh fails, show an error line.
4. Keep existing `refreshViewerAsset()` behavior.

Acceptance:

- User sees "Viewer refreshed" in the transcript after CAD updates.
- The viewer still updates on project mutations.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual external/MCP `cad.execute_build123d` or in-UI run.

Phase 6 exit criteria:

- Artifacts and viewer updates are represented compactly in chat.
- Named parts/pointers can be acted on from transcript lines.

## Phase 7 - Session Replay, Migration, and Cleanup

Goal: make transcript mode the default path and remove obsolete card-only code.

### CAT-P7-T01 - Merge Chat Messages and Agent Events on Session Load

Objective:

- Make reload/reopen behavior deterministic.

Likely files:

- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/app/useChatTranscript.ts` (new, optional)
- `frontend/src/app/chatTranscript.ts`
- `frontend/src/api.ts`

Steps:

1. Fetch chat messages.
2. Fetch agent events.
3. Convert both to transcript items.
4. Merge by `createdAt`, then stable source order.
5. Dedupe user/assistant messages that also exist as event payloads.
6. Keep fallback for sessions with no agent events.

Acceptance:

- Reopening a session produces stable ordering.
- Legacy sessions still show useful history.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual: run, refresh, switch sessions, return.

### CAT-P7-T02 - Move Chat State Out of `useWorkbenchApp`

Objective:

- Keep `useWorkbenchApp` as composition, not a large chat orchestrator.

Likely files:

- `frontend/src/app/useWorkbenchApp.ts`
- `frontend/src/app/useChatSessions.ts` (new)
- `frontend/src/app/useChatTranscript.ts` (new)
- `frontend/src/app/useAgentRuns.ts`
- `frontend/src/app/useAgentActivityStream.ts`

Steps:

1. Extract session list/load/create/update/delete into `useChatSessions`.
2. Extract transcript state, persistence, and message append/update into
   `useChatTranscript`.
3. Keep `useWorkbenchApp` wiring selected project, viewer, geometry, and hooks.
4. Ensure no new hook becomes too broad; split if needed.
5. Preserve existing behavior during extraction.

Acceptance:

- `useWorkbenchApp.ts` loses chat/session implementation details.
- Hook responsibilities are clear.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual smoke test: select project, switch sessions, send chat, run approval.

### CAT-P7-T03 - Make Transcript UI Default

Objective:

- Promote transcript mode after parity is proven.

Likely files:

- `frontend/src/appConstants.ts`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/style.css`

Steps:

1. Change feature flag default to enabled.
2. Keep a temporary fallback flag for one release if desired.
3. Update empty state and connection copy for the new flow.
4. Remove obvious dead CSS only after references are gone.

Acceptance:

- New users see transcript mode by default.
- Maintainers can still temporarily fall back if needed.

Verification:

- `cd aieng-ui/frontend && npm run build`
- Manual end-to-end chat flow.

### CAT-P7-T04 - Remove Obsolete Card Code

Objective:

- Clean up large card-only surfaces once transcript mode is stable.

Likely files:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/agent/AgentResultCard.tsx`
- `frontend/src/components/agent/AgentPlanCard.tsx`
- `frontend/src/components/agent/ApprovalCard.tsx`
- `frontend/src/style.css`
- `frontend/src/appTypes.ts`

Steps:

1. Search for every class and component used only by legacy card rendering.
2. Remove unused JSX branches.
3. Remove unused types and helpers.
4. Preserve components still used elsewhere.
5. Run TypeScript build and reference search.

Acceptance:

- No dead card-only rendering remains.
- Transcript components are the primary chat UI.

Verification:

- `cd aieng-ui/frontend && npm run build`
- `rg "autopilot-run-card|chat-cad-result|chat-sim-result" frontend/src`

Phase 7 exit criteria:

- Transcript mode is default.
- Session replay is deterministic.
- Major chat responsibilities are split out of `useWorkbenchApp`.
- Obsolete card code is removed or intentionally kept with notes.

## Phase 8 - Verification, Demo, and Handoff

Goal: prove the full experience and make it easy for later agents to continue.

### CAT-P8-T01 - Add End-to-end Manual Test Script

Objective:

- Give maintainers a repeatable chat transcript verification path.

Likely files:

- `aieng-ui/docs/chat-agent-transcript-demo.md` (new)
- `backend/scripts/demo_local_agent_autopilot.py` if reusable

Scenario:

1. Start backend and frontend.
2. Create/select a project.
3. Ask for a simple bracket CAD model.
4. Observe context/tool lines.
5. Review and approve CAD write.
6. Observe viewer refresh and artifact line.
7. Ask a follow-up refinement.
8. Stop or approve as appropriate.
9. Refresh the browser and confirm transcript replay.

Acceptance:

- A maintainer can follow the demo without reading source code.
- Expected transcript lines are listed.

Verification:

- Manual demo run.

### CAT-P8-T02 - Add Regression Tests for Session Replay and Events

Objective:

- Prevent future regressions in transcript persistence.

Likely files:

- `backend/tests/test_persistence.py`
- `backend/tests/test_agent_activity.py`
- `frontend` tests if available.

Steps:

1. Backend: create run/event records and assert list endpoint returns stable
   order.
2. Backend: duplicate event insert is idempotent.
3. Frontend: mapper handles duplicate event/snapshot input.
4. Frontend: approval event maps to exactly one approval line.

Acceptance:

- Replay and dedupe behavior are covered by tests or documented manual checks.

Verification:

- `cd aieng-ui/backend && python -m pytest tests/test_persistence.py tests/test_agent_activity.py`
- `cd aieng-ui/frontend && npm run build`

### CAT-P8-T03 - Update Handoff Documentation

Objective:

- Ensure later LLMs know the new architecture.

Likely files:

- `aieng-ui/docs/local-agent-autopilot-handoff.md`
- `aieng-ui/docs/runtime_architecture.md`
- This document.

Steps:

1. Add a "Chat transcript architecture" section to the handoff doc.
2. Link this plan.
3. Document how events, messages, sessions, and run states relate.
4. Document reset/debug paths for event persistence.
5. Update task ledger rows.

Acceptance:

- New agents can find the transcript architecture without searching source.

Verification:

- Documentation review.

Phase 8 exit criteria:

- Demo exists.
- Tests or manual checks cover the flow.
- Handoff docs are updated.

## Recommended Implementation Order

1. `CAT-P0-T01`
2. `CAT-P0-T02`
3. `CAT-P1-T01`
4. `CAT-P1-T02`
5. `CAT-P2-T01`
6. `CAT-P2-T02`
7. `CAT-P2-T03`
8. `CAT-P3-T01`
9. `CAT-P3-T02`
10. `CAT-P4-T01`
11. `CAT-P4-T02`
12. `CAT-P4-T03`
13. `CAT-P4-T04`
14. `CAT-P5-T01`
15. `CAT-P5-T02`
16. `CAT-P6-T01`
17. `CAT-P7-T01`
18. `CAT-P7-T02`
19. `CAT-P7-T03`
20. `CAT-P8-T01`

This order creates value early:

```text
feature flag
  -> transcript model
  -> compact UI from existing run snapshots
  -> better approval/reply semantics
  -> typed events and persistence
  -> interruption/follow-up
  -> viewer/artifact integration
  -> default rollout and cleanup
```

## Completion Definition

The refactor is complete when:

- Workbench chat defaults to the transcript UI.
- Autopilot run progress appears as compact, ordered transcript lines.
- Tool details are collapsed by default.
- Approvals are inline, informative, and distinct from normal replies.
- Users can stop active runs.
- Users can send follow-up/revision text without losing the active run.
- Typed SSE events drive live updates.
- Agent events are persisted and replayed on session load.
- CAD/CAE artifacts and viewer refreshes appear as transcript artifact lines.
- Legacy card-only code is removed or explicitly retained with documented
  ownership.
- Every completed task has an updated ledger row.

## Task Ledger

Update this table after each task.

| Task ID | Status | Owner/session | Files changed | Verification | Notes |
|---|---|---|---|---|---|
| CAT-P0-T01 | DONE | Codex goal session 2026-05-30 | `docs/chat-agent-transcript-current-flow.md` | Documentation review; `rg setChatHistory autopilot_update chat_message` | Current mutation paths and risky coupling points captured. |
| CAT-P0-T02 | DONE | Codex goal session 2026-05-30 | `frontend/src/appConstants.ts`, `frontend/src/app/useWorkbenchApp.ts`, `frontend/src/components/settings/RuntimeSettingsDrawer.tsx`, `frontend/src/components/panels/ChatPanel.tsx` | `cd aieng-ui/frontend && npm run build` | Temporary `aieng-ui.chat-transcript-v2` flag was used during rollout, then removed when CAT-P7 made transcript the sole UI path. |
| CAT-P0-T03 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/chatTranscript.ts`, `frontend/src/app/chatTranscriptFixtures.ts` | `cd aieng-ui/frontend && npm run build` | Pure mapper supports representative states; typed fixtures cover running, approval, completed, failed, blocked, and chatting until a frontend unit harness exists. |
| CAT-P1-T01 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/chatTranscript.ts` | `cd aieng-ui/frontend && npm run build` | Transcript item union and typed event shape added without removing `ChatHistoryItem`. |
| CAT-P1-T02 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/chatTranscript.ts` | `cd aieng-ui/frontend && npm run build` | `runToTranscriptItems` handles tool, approval, artifact, error, final, and chat observations defensively. |
| CAT-P1-T03 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/chatTranscript.ts` | `cd aieng-ui/frontend && npm run build` | Legacy chat entries, CAD/CAE/preprocess result payloads, and artifact paths map into transcript lines. |
| CAT-P2-T01 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/chat/*` | `cd aieng-ui/frontend && npm run build` | Focused transcript components added for messages, tools, approvals, artifacts, and details. |
| CAT-P2-T02 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/app/AppChrome.tsx` | `cd aieng-ui/frontend && npm run build` | Transcript rendering wired into `ChatPanel`; legacy card path later removed in CAT-P7-T04. |
| CAT-P2-T03 | DONE | Codex goal session 2026-05-30 | `frontend/src/style.css` | `cd aieng-ui/frontend && npm run build` | Compact transcript rows, inline approvals, artifact chips, and collapsed detail styling added. |
| CAT-P2-T04 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/app/useWorkbenchApp.ts` | `cd aieng-ui/frontend && npm run build`; prior browser desktop/mobile QA; `Invoke-WebRequest http://127.0.0.1:5173` | Near-bottom auto-scroll and new-activity button implemented and smoke-tested in the workbench. |
| CAT-P3-T01 | DONE | Codex goal session 2026-05-30 | `backend/app/app_factory.py`, `backend/app/agent_autopilot/engine.py`, `frontend/src/api.ts`, `frontend/src/app/useAgentRuns.ts`, `frontend/src/app/useWorkbenchApp.ts`, `backend/tests/test_agent_autopilot_engine.py` | `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py` | Explicit `reply` API added; chatting/revision no longer relies on approval=true continuation. |
| CAT-P3-T02 | DONE | Codex goal session 2026-05-30 | `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/engine.py`, `frontend/src/components/chat/ApprovalLine.tsx`, `frontend/src/app/chatTranscript.ts` | `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_engine.py` | Approval payload carries side effect, risk, target project, code preview, and recommended action fields. |
| CAT-P3-T03 | DONE | Codex goal session 2026-05-30 | `backend/app/agent_autopilot/engine.py`, `frontend/src/app/chatTranscript.ts`, `frontend/src/components/chat/TranscriptMessage.tsx` | `cd aieng-ui/frontend && npm run build` | Agent `chat`/`ask_user`/final text maps to normal assistant transcript messages. |
| CAT-P4-T01 | DONE | Codex goal session 2026-05-30 | `backend/app/agent_autopilot/engine.py`, `frontend/src/app/chatTranscript.ts`, `frontend/src/api.ts` | `cd aieng-ui/backend && python -m pytest tests/test_agent_activity.py tests/test_persistence.py` | Typed agent event contract implemented as append-only event rows plus SSE payloads. |
| CAT-P4-T02 | DONE | Codex goal session 2026-05-30 | `backend/app/agent_autopilot/engine.py`, `backend/app/app_factory.py` | `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_activity.py` | Engine emits agent messages, tool lifecycle, approval, artifact, status, and cancellation events. |
| CAT-P4-T03 | DONE | Codex goal session 2026-05-30 | `backend/app/db.py`, `backend/app/app_factory.py`, `backend/tests/test_persistence.py` | `cd aieng-ui/backend && python -m pytest tests/test_persistence.py` | `agent_events` table and idempotent list endpoint added. |
| CAT-P4-T04 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/useAgentActivityStream.ts`, `frontend/src/app/useWorkbenchApp.ts`, `frontend/src/app/chatTranscript.ts`, `frontend/src/api.ts` | `cd aieng-ui/frontend && npm run build` | Frontend consumes typed SSE events and persisted event replay, with `autopilot_update` fallback intact. |
| CAT-P5-T01 | DONE | Codex goal session 2026-05-30 | `backend/app/agent_autopilot/store.py`, `backend/app/agent_autopilot/engine.py`, `backend/tests/test_agent_autopilot_engine.py` | `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py` | Cooperative cancel markers are checked between adapter/tool steps and surfaced in transcript events; force-terminating adapter subprocesses remains future hardening. |
| CAT-P5-T02 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/app/useWorkbenchApp.ts` | `cd aieng-ui/frontend && npm run build` | Text input remains usable during active runs; send label reflects follow-up/revision routing. |
| CAT-P5-T03 | DONE | Codex goal session 2026-05-30 | `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/engine.py`, `frontend/src/api.ts`, `backend/tests/test_agent_autopilot_engine.py` | `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py` | Follow-up queue added and consumed before the next adapter invocation. |
| CAT-P5-T04 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/components/chat/ApprovalLine.tsx`, `frontend/src/style.css` | `cd aieng-ui/frontend && npm run build`; prior browser desktop/mobile QA; `Invoke-WebRequest http://127.0.0.1:5173` | Stop controls added in approval rows and input area. |
| CAT-P6-T01 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/chatTranscript.ts`, `backend/app/agent_autopilot/engine.py`, `backend/app/app_factory.py` | Backend focused pytest + frontend build | CAD/CAE outputs normalize to artifact transcript lines and `artifact_ready` events. |
| CAT-P6-T02 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/chat/ArtifactLine.tsx`, `frontend/src/components/PointerText.tsx` | `cd aieng-ui/frontend && npm run build` | Named parts render as artifact chips; pointer tokens in artifact summaries remain clickable through the shared `PointerText` provider. |
| CAT-P6-T03 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/chatTranscript.ts`, `frontend/src/app/useAgentActivityStream.ts`, `backend/app/app_factory.py` | `cd aieng-ui/frontend && npm run build` | `viewer_asset_changed` maps to compact artifact/status replay and existing viewer refresh remains intact. |
| CAT-P7-T01 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/useWorkbenchApp.ts`, `frontend/src/api.ts`, `frontend/src/app/chatTranscript.ts` | `cd aieng-ui/frontend && npm run build` | Session load fetches chat messages and agent events and merges them for transcript rendering. |
| CAT-P7-T02 | DONE | Codex goal session 2026-05-30 | `frontend/src/app/useChatSessions.ts`, `frontend/src/app/useChatTranscript.ts`, `frontend/src/app/chatStateUtils.ts`, `frontend/src/app/useWorkbenchApp.ts` | `cd aieng-ui/frontend && npm run build` | Session lifecycle, transcript persistence, replay, and upsert helpers extracted into focused modules; `useWorkbenchApp` is back to composition/wiring. |
| CAT-P7-T03 | DONE | Codex goal session 2026-05-30 | `frontend/src/appConstants.ts`, `frontend/src/components/settings/RuntimeSettingsDrawer.tsx`, `frontend/src/components/panels/ChatPanel.tsx` | `cd aieng-ui/frontend && npm run build` | Transcript UI is now unconditional; the temporary fallback setting and drawer toggle were removed. |
| CAT-P7-T04 | DONE | Codex goal session 2026-05-30 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/components/agent/AgentResultCard.tsx`, `frontend/src/components/agent/AgentPlanCard.tsx`, `frontend/src/components/agent/ApprovalCard.tsx`, `frontend/src/style.css` | `cd aieng-ui/frontend && npm run build`; `rg "autopilot-run-card|chat-cad-result|chat-sim-result" frontend/src` | Legacy card branch, card components, fallback flag wiring, and obsolete card CSS removed; transcript components are the sole chat rendering path. |
| CAT-P8-T01 | DONE | Codex goal session 2026-05-30 | `docs/chat-agent-transcript-demo.md` | Documentation review | Repeatable manual demo script added. |
| CAT-P8-T02 | DONE | Codex goal session 2026-05-30 | `backend/tests/test_persistence.py`, `backend/tests/test_agent_autopilot_engine.py`, `frontend/src/app/chatTranscriptFixtures.ts` | `cd aieng-ui/backend && python -m pytest tests/test_agent_autopilot_engine.py tests/test_persistence.py tests/test_agent_activity.py tests/test_agent_autopilot_schema.py`; `cd aieng-ui/frontend && npm run build` | Backend replay/event and queue/reply regression tests added; frontend mapper coverage is represented by typed fixtures until a frontend test runner is introduced. |
| CAT-P8-T03 | DONE | Codex goal session 2026-05-30 | `docs/local-agent-autopilot-handoff.md`, `docs/runtime_architecture.md`, this document | Documentation review | Transcript architecture and reset/debug paths documented. |
