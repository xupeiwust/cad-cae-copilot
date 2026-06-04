# Web Chat → VSCode-Parity Agentic Session (Approach A)

Status: **MCP-FIRST #17 PRODUCT CUTOVER — in-UI chat retired from active UI; backend chat/autopilot compatibility retained**
Last updated: **2026-06-04**
Owner: **AIENG workbench maintainers**

> **Strategic update (#17):** the product direction is now MCP-first: a
> full-width live CAD/CAE model viewer plus a world-class MCP server for BYO
> agents. The active frontend no longer renders the embedded chat, composer,
> sessions rail, or chat-dependent panels. External MCP agents drive CAD/CAE;
> the Workbench UI mirrors geometry, exposes spatial pointers, and stays focused
> on project/viewer operations. The backend chat/autopilot routes are retained
> only as compatibility surfaces for old clients/tests and are not the active
> product path.
>
> **Safety boundary:** `AIENG_MCP_BLOCK_APPROVAL_TOOLS=1` hard-refuses
> approval-gated MCP tools for inspection/planning deployments. In normal BYO
> mode, MCP clients provide their own permission UX for gated mutations.

> Supersedes the "engine is always the orchestrator" assumption from
> [`web-chat-codex-agent-roadmap.md`](web-chat-codex-agent-roadmap.md) **for the
> Claude path only**. The existing single-action engine path
> (`llm-api`, `claude-code`, `codex-cli`) stays intact and selectable; this adds
> a parallel, opt-in `claude-agent` path that reaches VSCode-level capability.

---

## Problem (verified in code)

The aieng UI chat is dramatically weaker than the VSCode Claude Code chat
because the two run **different orchestration models**:

| | VSCode Claude Code | aieng UI chat (today) |
|---|---|---|
| Orchestrator | Claude itself (full agentic loop) | backend `AutopilotEngine` |
| LLM role | drives multi-step tool chains + thinking | single `AutopilotAgentAction` JSON oracle per step |
| Workbench tools | full `cad.*/cae.*/aieng.*` via MCP | adapter Claude gets **none** (`--tools "Read,Edit,Grep,Glob,LS,Search"`, no `--mcp-config`); engine executes tools |
| Skills | real `Skill`/`Task` invocation | prompt excerpts only (`project_skills.py`) |
| Docs (AGENTS.md/CLAUDE.md) | auto-loaded from cwd = repo root | adapter cwd = `aieng-ui/backend`, single-action mode → not loaded/usable |
| Extended thinking | yes | no (single JSON action) |

Evidence:
- [`claude_code_adapter.py:506-520`](../backend/app/agent_autopilot/claude_code_adapter.py#L506-L520)
  — `--json-schema <action_schema>` single action, `--tools` allowlist excludes
  `Skill`/`Task`/MCP, no `--mcp-config`.
- [`claude_code_adapter.py:317`](../backend/app/agent_autopilot/claude_code_adapter.py#L317)
  — subprocess cwd is the backend process dir, not the repo root.
- [`engine.py` `_step_loop`](../backend/app/agent_autopilot/engine.py) — engine is
  the orchestrator; the adapter only returns one action; the engine executes via
  `tool_executor`.

This is the same root cause behind issue #16 ("skills are prompt-only") and the
user-reported "API and local agent both can't read AGENTS.md / call skills".

---

## Target architecture

```text
UI chat message (adapter_id = "claude-agent")
  -> backend run scaffolding (run_id, transcript, approval store) UNCHANGED
    -> ClaudeAgentSession: spawn a REAL agentic claude session
         cwd = repo root            -> CLAUDE.md / AGENTS.md / .claude skills load
         --mcp-config .mcp.json     -> cad.* / cae.* / aieng.* callable directly
         --output-format stream-json -> Claude runs its own multi-step loop + thinking
         --permission-prompt-tool   -> gated mutations bridge back to the existing UI approval gate
    -> stream-json events translated into the existing event contract
       (run_status_changed / tool_started / tool_completed / approval_requested / agent_message / ...)
    -> existing frontend transcript + approval cards render unchanged
```

Backend's job shrinks to: project scoping, approval bridging, transcript
translation. Claude is the orchestrator (VSCode parity).

---

## Acceptance criteria (definition of done)

- [ ] A UI chat run on the `claude-agent` path can model a part end-to-end via the
      real `cad.execute_build123d` MCP tool — no engine single-action loop.
- [ ] The session demonstrably **reads repo docs** (can answer from AGENTS.md/
      CLAUDE.md) and can **invoke a workspace skill** (`Skill`/`Task`).
- [ ] Every gated mutation (`cad.execute_build123d`, `cad.edit_parameter`,
      `cad.replace_part`, `cad.remove_part`, `cae.run_solver`,
      `aieng.delete_project`, `aieng.apply_shape_ir_patch`) still pauses for UI
      approval — **the agentic path never bypasses approval.**
- [ ] Tool calls, results, thinking summaries, and the final message render in
      the existing transcript with correct terminal/active states.
- [ ] The existing `llm-api` / `claude-code` / `codex-cli` paths are unchanged
      and still selectable. The new path is opt-in (flag + adapter selection).
- [ ] Windows: session spawns without interactive prompts; validated via
      TestClient (backend not hot-reloaded — see memory `project_backend_reload_hang`).

---

## Phases (MVP-first; each independently testable)

### Phase 1 — Agentic session module (no engine changes) — IN PROGRESS
New module `backend/app/agent_autopilot/claude_agent_session.py`:
- `build_agent_command(...)` — pure, testable construction of the `claude`
  stream-json agentic command (cwd=repo root, `--mcp-config`, `--add-dir`,
  `--permission-prompt-tool`, no crippling `--tools` allowlist).
- `translate_stream_event(json_obj) -> list[event-contract dicts]` — pure mapper
  from Claude stream-json events to our `_publish_agent_event` contract.
- `ClaudeAgentSession.run(...)` — spawn, stream stdout line-delimited JSON, call
  `on_event` per translated event, enforce timeout, Windows-safe process kill.
- Capability probe (`--version` / stream-json support) for the runtime settings UI.
- Tests: command construction + stream-json fixture → event translation. No live
  nested agent required.

### Phase 2 — Approval bridge (MCP permission-prompt tool) — DONE
- `agentic_approval.py` — pure name normalization, gated classification (single
  source = registry `requires_approval`), decision contract, `PermissionBroker`
  (process-local poll/resolve rendezvous).
- MCP `request_approval` tool in `mcp_server.py` (gated behind
  `AIENG_AGENTIC_PERMISSION_TOOL=1`; **fail-safe deny** if backend unreachable).
- Backend endpoints: `POST /api/agent/agentic/permission` (auto-allow non-gated,
  pending+`approval_requested` event for gated), `GET …/{id}` (poll),
  `POST …/{id}/resolve` (UI approve/deny + `approval_resolved` event).
- Tests: `test_agentic_approval.py` — 13 passing (pure + API roundtrip:
  non-gated auto-allow, gated pending→approve→allow, deny, 404s).

### Phase 3 — Run wiring + frontend selection
Backend — DONE:
- `claude_agent_session.build_run_mcp_config` injects per-run env
  (`AIENG_AUTOPILOT_RUN_ID/PROJECT_ID/SESSION_ID`, `AIENG_AGENTIC_PERMISSION_TOOL=1`,
  `AIENG_BACKEND_URL`) into a temp MCP config; `ClaudeAgentSession.run` writes it,
  attaches `--permission-prompt-tool`, spawns with cwd=repo root, cleans up.
- `create_agent_autopilot_run` dispatches to `_run_agentic_session` when
  `adapter_id == "claude-agent"` (same run scaffolding/transcript; legacy path
  untouched); stored run status updated from the terminal stream event.
- Tests: `test_claude_agent_session.py` per-run config injection (15 total).

Frontend (A1) — DONE:
- `claude-agent` advertised as a chat connection (`agent_workbench.list_chat_connections`,
  `ready` when the `claude` CLI is available; `DEFAULT_CHAT_CONNECTIONS` fallback).
- `useAgentRuns.runAutopilotAgent` routes `claude-agent` → `adapter_id="claude-agent"`
  (skips local-adapter resolution).
- Approval card approve/deny routes to `POST …/permission/{id}/resolve` when the
  transcript item carries `agenticPermissionId` (threaded ApprovalLine →
  ChatTranscript → ChatPanel → AppChrome → `updateAutopilotRun`); engine path
  unchanged. `api.resolveAgenticPermission` added.
- Builds clean (tsc + vite); frontend tests green; backend `claude-agent`
  advertised confirmed via TestClient.

Live finding #1 (2026-06-04) — **approval bypass, FIXED.** First live `claude-agent`
run built geometry but the gated `cad.execute_build123d` ran WITHOUT an approval
prompt. Two root causes:
1. `--permission-prompt-tool` is skipped by Claude for tools already in the user's
   permission allow-list (the dev machine allow-lists `mcp__aieng-workbench__*`).
2. Without `--strict-mcp-config`, Claude could load the user's *global* workbench
   MCP server (no run-scoped approval env) instead of the per-run one.
Fix: approval is now enforced **server-side in the workbench MCP tool handler**
(`mcp_server._make_handler` → `_agentic_permission_decision`), independent of
Claude's permission settings; gated tools block on the broker before executing.
Command now passes `--strict-mcp-config` and drops `--permission-prompt-tool`.
**Requires a backend restart** to load the updated `claude_agent_session` (the MCP
handler reloads per-run automatically since each run spawns a fresh server).

Live finding #2 (2026-06-04) — **session_id mismatch, FIXED.** The approval gate
fired correctly (logs showed `POST …/permission` + a long `GET …/permission/{id}`
poll loop), but the approval card never appeared and earlier tool/text events were
also missing. Root cause: `_run_agentic_session` passed the Claude-CLI `--session-id`
UUID (`uuid5(run_id)`) as the **event** session_id, so every emitted event
(assistant text, tool_started, approval_requested) was tagged with that UUID
instead of the real **chat** session — the UI filters events by chat session and
silently dropped them, leaving the MCP tool polling forever. Fix:
`ClaudeAgentSession.run` now takes both `session_id` (chat, for event association +
MCP env) and `claude_session_id` (CLI UUID); `_run_agentic_session` passes
`request.session_id` for events and the uuid5 only for the CLI. **Requires backend
restart** (also kills the stuck polling run).

Remaining:
- **Re-validate live** after backend restart: assistant text + tool lines now
  render; gated build pauses at the approval card; approve → builds; deny →
  `approval_denied`.
- Reduce poll log noise (server-side long-poll) — cosmetic.
- Confirm `--strict-mcp-config` doesn't drop needed context; watch stream-json.
- Continue/reply/follow-up → session resume (`--resume <claude_session_id>`,
  derived `uuid5(run_id)`).
- Skills wiring: repo has `aieng-agent-skills/`, not `.claude/skills/` — docs
  (AGENTS.md/CLAUDE.md) load via cwd=repo root, but skills need a pointer.
- `cancel` for an agentic run should kill the session subprocess (not yet wired).

### Phase 4 — Hardening
- Reconcile plan/replay model with native agent loop (or render a derived plan).
- Token/cost accounting from stream-json `result` usage.
- Parity tests vs VSCode behavior on the canonical flows (/build, /modify, /simulate).

---

## Non-goals
- Removing the existing engine path (kept for `llm-api` / non-Claude CLIs).
- Bypassing any approval gate.
- Changing CAD/CAE tool semantics.
