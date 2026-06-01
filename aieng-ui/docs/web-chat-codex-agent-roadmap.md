# Web Chat Toward Codex-Style Agent Roadmap

Status: **Draft / executable backlog**
Last updated: **2026-06-01**
Owner: **AIENG workbench maintainers + handoff LLM agents**

## Purpose

This document turns the gap between the current AIENG Web Chat Autopilot and a
Codex-style engineering agent into concrete implementation tasks.

The target is not to bypass the agent with local shortcuts. The target is:

```text
Web Chat
  -> Autopilot Engine as the orchestrator
    -> shared policy / memory / plan / skill routing
      -> Adapter: Local Agent CLI or LLM API
        -> one structured next action
          -> skill/tool execution through runtime
            -> approval gates for mutations
              -> verification and recovery
```

Local Agent and LLM API must remain logically equivalent. They may differ only
in the decision backend, not in available tools, safety policy, memory contract,
skill-routing behavior, or UI transcript semantics.

## Current Baseline

Relevant current pieces:

| Area | Files | Notes |
|---|---|---|
| Autopilot engine | `backend/app/agent_autopilot/engine.py` | Runs one structured action at a time, checkpoints state, handles approvals, executes tools, emits events. |
| Adapters | `backend/app/agent_autopilot/*adapter.py` | Local CLI adapters and LLM API adapter return the same `AutopilotAgentAction` shape. |
| Runtime tools | `backend/app/runtime.py`, `backend/app/app_factory.py` | Tools are registered with schemas and approval metadata. |
| Policy | `backend/app/agent_autopilot/policy.py` | Allows read/preview/safe-write/mutation/solver classes. |
| Prompt/memory | `backend/app/agent_autopilot/prompts.py`, `context_memory.py` | Compacts tool catalog, observations, and project skill excerpts. |
| Project skills | `aieng-agent-skills/skills/*/SKILL.md` | Mostly behavior contracts; some legacy. |
| CAD skill tool | `backend/app/cad_skill_planner.py` | Early proof: read-only planner returns a parameterized `cad.execute_build123d` input for flanges. |
| Chat transcript | `frontend/src/app/chatTranscript.ts`, `useAgentActivityStream.ts` | Merges chat rows, agent events, and run snapshots into UI transcript items. |

Known user-visible problem:

- Long Local Agent JSON-mode calls still feel like waiting on a blank wall.
- Skill routing exists as prompt guidance, but the plan state is not yet a
  first-class machine-readable artifact.
- Tool failures generally become run failures instead of entering a repair loop.

## Status Management

Use this document as the task board. Update only the relevant task row and the
task's status note when you start or finish work.

Allowed statuses:

| Status | Meaning |
|---|---|
| `TODO` | Ready to pick up. |
| `IN_PROGRESS` | Someone is actively editing or validating it. Include owner/date in the row. |
| `BLOCKED` | Cannot proceed without a concrete dependency or decision. Add the blocker. |
| `DONE` | Implemented, tested, and documented. Include test evidence. |
| `DEFERRED` | Intentionally postponed. Add reason. |

Task update rule:

1. Change one task to `IN_PROGRESS` before editing.
2. Keep edits scoped to that task and its declared dependencies.
3. When done, update the task row with files touched and tests run.
4. If behavior changes user-visible flow, update `chat-agent-transcript-current-flow.md`
   or the relevant docs.

## Milestones

| Milestone | Goal | Exit Criteria |
|---|---|---|
| M1 | First-class agent plan state | Autopilot exposes a persistent plan with step statuses visible in UI. |
| M2 | Skill tools as structured capabilities | Common CAD creation flows go through agent-orchestrated skill tools, then normal approval. |
| M3 | Unified Local Agent / LLM API behavior | Both adapters consume the same prompt/memory/policy and produce equivalent event traces. |
| M4 | Live, trustworthy transcript | UI shows phase-specific progress and resumable state instead of generic waiting. |
| M5 | Recovery loop | Tool/schema/CAD failures produce repair actions before failing the run. |
| M6 | Working-state memory | Runs can resume with accepted assumptions, latest evidence, and current blockers. |

## Task Board

| ID | Status | Title | Dependencies | Owner / Notes |
|---|---|---|---|---|
| WCA-M1-T01 | DONE | Define persistent `AgentPlan` schema | None | Codex / 2026-06-01. Files: `schema.py`, `__init__.py`, `test_agent_autopilot_schema.py`. Tests: `python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_store.py`. |
| WCA-M1-T02 | DONE | Attach `AgentPlan` to `AutopilotRunState` | WCA-M1-T01 | Codex / 2026-06-01. Files: `schema.py`, `engine.py`, `test_agent_autopilot_engine.py`, `test_agent_autopilot_store.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_store.py`; `python -m pytest tests/test_agent_autopilot_schema.py`. |
| WCA-M1-T03 | DONE | Emit plan lifecycle events | WCA-M1-T02 | Codex / 2026-06-01. Files: `engine.py`, `app_factory.py`, `test_agent_autopilot_engine.py`, `test_api.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_store.py tests/test_agent_autopilot_schema.py`; `python -m pytest tests/test_api.py::test_autopilot_plan_events_are_persisted tests/test_api.py::test_agent_autopilot_run_dry_run tests/test_api.py::test_agent_autopilot_continue_and_cancel`. |
| WCA-M1-T04 | DONE | Render AgentPlan card in transcript | WCA-M1-T03 | Codex / 2026-06-01. Files: `chatTranscript.ts`, `AgentPlanCard.tsx`, `ChatTranscript.tsx`, `style.css`, `types.ts`. Tests: `npm run build`; browser load of `http://localhost:5173` (backend fetch failed because port 8000 is not running). |
| WCA-M2-T01 | DONE | Formalize skill tool output contract | None | Codex / 2026-06-01. Files: `schema.py`, `cad_skill_planner.py`, `prompts.py`, `context_memory.py`, related tests. Tests: `python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py tests/test_agent_autopilot_schema.py`; `python -m pytest tests/test_agent_autopilot_engine.py`. |
| WCA-M2-T02 | DONE | Expand CAD skill planner: mounting plate | WCA-M2-T01 | Codex / 2026-06-01. Files: `cad_skill_planner.py`, `test_cad_skill_planner.py`. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_prompts.py tests/test_context_memory.py tests/test_agent_autopilot_engine.py`. |
| WCA-M2-T03 | DONE | Expand CAD skill planner: L bracket | WCA-M2-T01 | Codex / 2026-06-01. Files: `cad_skill_planner.py`, `test_cad_skill_planner.py`. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`. |
| WCA-M2-T04 | DONE | Expand CAD skill planner: enclosure/box | WCA-M2-T01 | Codex / 2026-06-01. Files: `cad_skill_planner.py`, `test_cad_skill_planner.py`. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`. |
| WCA-M2-T05 | DONE | Expand CAD skill planner: bushing/spacer | WCA-M2-T01 | Codex / 2026-06-01. Files: `cad_skill_planner.py`, `test_cad_skill_planner.py`. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`. |
| WCA-M2-T06 | DONE | Add skill selection diagnostics | WCA-M2-T01 | Codex / 2026-06-01. Files: `schema.py`, `cad_skill_planner.py`, `prompts.py`, `context_memory.py`, `chatTranscript.ts`, tests. Tests: `python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py tests/test_agent_autopilot_schema.py`; `npm run build`. |
| WCA-M3-T01 | DONE | Add adapter equivalence tests | M1 partial | Codex / 2026-06-01. Files: `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_llm_adapter.py`. |
| WCA-M3-T02 | DONE | Normalize timeout/progress semantics | None | Codex / 2026-06-01. Files: `adapters.py`, `claude_code_adapter.py`, `codex_cli_adapter.py`, `llm_api_adapter.py`, `engine.py`, adapter tests. Tests: `python -m pytest tests/test_agent_autopilot_adapters.py tests/test_agent_autopilot_llm_adapter.py`; `python -m pytest tests/test_agent_autopilot_engine.py`. |
| WCA-M3-T03 | DONE | Enforce single tool catalog source | None | Codex / 2026-06-01. Files: `test_agent_autopilot_prompts.py`. Tests: `python -m pytest tests/test_agent_autopilot_prompts.py tests/test_api.py::test_health_endpoint`. |
| WCA-M4-T01 | DONE | Add typed `agent_phase_changed` events | WCA-M1-T03 | Codex / 2026-06-01. Files: `engine.py`, `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py::test_autopilot_plan_events_are_persisted`. |
| WCA-M4-T02 | DONE | Add UI phase timeline row | WCA-M4-T01 | Codex / 2026-06-01. Files: `chatTranscript.ts`. Tests: `npm run build`. |
| WCA-M4-T03 | DONE | Improve approval card from skill plan | WCA-M2-T01 | Codex / 2026-06-01. Files: `schema.py`, `engine.py`, `chatTranscript.ts`, `ApprovalLine.tsx`, `style.css`, tests. Tests: `python -m pytest tests/test_agent_autopilot_engine.py`; `npm run build`. |
| WCA-M5-T01 | DONE | Add repairable error classification | None | Codex / 2026-06-01. Files: `schema.py`, `engine.py`, `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_schema.py`. |
| WCA-M5-T02 | DONE | Implement `repair_tool_input` loop | WCA-M5-T01 | Codex / 2026-06-01. Files: `schema.py`, `engine.py`, `prompts.py`, `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`; `npm run build`. |
| WCA-M5-T03 | DONE | CAD build failure repair prompt | WCA-M5-T02 | Codex / 2026-06-01. Files: `context_memory.py`, `prompts.py`, `test_context_memory.py`, `test_agent_autopilot_prompts.py`. Tests: `python -m pytest tests/test_context_memory.py tests/test_agent_autopilot_prompts.py tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_schema.py`; `npm run build`. |
| WCA-M6-T01 | DONE | Add Agent Working State blackboard | WCA-M1-T02 | Codex / 2026-06-01. Files: `schema.py`, `context_memory.py`, `engine.py`, `app_factory.py`, `types.ts`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_context_memory.py tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_store.py tests/test_agent_autopilot_prompts.py`; `npm run build`. |
| WCA-M6-T02 | DONE | Persist accepted assumptions | WCA-M6-T01 | Codex / 2026-06-01. Files: `engine.py`, `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_context_memory.py tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_store.py`; `npm run build`. |
| WCA-M6-T03 | DONE | Add run resume summary | WCA-M6-T01 | Codex / 2026-06-01. Files: `context_memory.py`, `engine.py`, `test_context_memory.py`, `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_context_memory.py tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_store.py tests/test_agent_autopilot_prompts.py`; `npm run build`. |
| WCA-QA-T01 | DONE | End-to-End Smoke: 40mm Flange | WCA-M2-T02, WCA-M4-T03, WCA-M6-T03 | Codex / 2026-06-01. Files: `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py::test_autopilot_plan_events_are_persisted tests/test_api.py::test_agent_autopilot_run_dry_run tests/test_api.py::test_agent_autopilot_continue_and_cancel`; `npm run build`. |
| WCA-QA-T02 | DONE | End-to-end smoke: unsupported CAD request | WCA-M2-T06 | Codex / 2026-06-01. Files: `test_agent_autopilot_engine.py`. Tests: `python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_engine.py`; `npm run build`. |

## Detailed Tasks

### WCA-M1-T01 — Define Persistent `AgentPlan` Schema

Status: `DONE` — Codex / 2026-06-01. Added `AgentPlan` / `AgentPlanStep`, exported them from the package, and covered empty defaults, Pydantic round-trip, and old run payload compatibility. Tests: `python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_store.py`.

Objective:

Create a typed plan model that represents what the agent is trying to do, not
just what action it selected next.

Recommended files:

- `backend/app/agent_autopilot/schema.py`
- `backend/tests/test_agent_autopilot_schema.py`

Implementation steps:

1. Add `AgentPlanStep` with fields:
   - `id: str`
   - `title: str`
   - `kind: observe | skill | tool | approval | verify | repair | summarize`
   - `status: pending | running | completed | blocked | failed | skipped`
   - `tool_name: str | None`
   - `skill_name: str | None`
   - `summary: str`
   - `evidence: dict[str, Any]`
2. Add `AgentPlan` with:
   - `id`
   - `objective`
   - `status`
   - `steps`
   - `current_step_id`
   - `created_at`, `updated_at`
3. Keep defaults backward compatible so old run JSON files still validate.
4. Add schema tests for empty plan, round-trip serialization, and old run
   payloads without plan.

Acceptance criteria:

- `AutopilotRunState.model_validate(old_payload)` still works.
- New plan objects round-trip through Pydantic.
- No frontend changes required in this task.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_schema.py tests/test_agent_autopilot_store.py
```

### WCA-M1-T02 — Attach `AgentPlan` to `AutopilotRunState`

Status: `DONE` — Codex / 2026-06-01. Added `plan` to `AutopilotRunState`, initialized a coarse plan for new runs, updated plan steps during adapter/tool/approval transitions, and verified store round-trip. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_store.py`; `python -m pytest tests/test_agent_autopilot_schema.py`.

Objective:

Store the current plan in every Autopilot run so background workers, polling,
and replay all see the same orchestration state.

Recommended files:

- `backend/app/agent_autopilot/schema.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/tests/test_agent_autopilot_engine.py`
- `backend/tests/test_agent_autopilot_store.py`

Implementation steps:

1. Add `plan: AgentPlan | None = None` to `AutopilotRunState`.
2. On run start, create a coarse plan:
   - Observe context
   - Select skill/tool
   - Prepare action
   - Await approval when needed
   - Execute
   - Verify
   - Summarize
3. Update plan step statuses as the existing engine moves through actions.
4. Keep the legacy `steps: list[AutopilotStep]` untouched for compatibility.

Acceptance criteria:

- Every new run has a plan before first adapter invocation.
- Plan survives store save/load.
- Approval state marks an approval step as `blocked` or `running`, not just run status.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_store.py
```

### WCA-M1-T03 — Emit Plan Lifecycle Events

Status: `DONE` — Codex / 2026-06-01. Added `agent_plan_created` and `agent_plan_step_updated` events, persisted them through the API event table, and covered engine/API replay behavior. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_store.py tests/test_agent_autopilot_schema.py`; `python -m pytest tests/test_api.py::test_autopilot_plan_events_are_persisted tests/test_api.py::test_agent_autopilot_run_dry_run tests/test_api.py::test_agent_autopilot_continue_and_cancel`.

Objective:

Make plan changes visible through the same append-only event stream used by
the transcript.

Recommended files:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`
- `backend/tests/test_api.py`

Implementation steps:

1. Emit `agent_plan_created` after run start.
2. Emit `agent_plan_step_updated` whenever a plan step changes status.
3. Include stable `event_id` values based on `run_id`, `plan_id`, `step_id`, and
   a status version or timestamp.
4. Ensure duplicate SSE delivery remains idempotent in frontend replay.

Acceptance criteria:

- Persisted events are enough to reconstruct a compact plan timeline.
- Existing `autopilot_update` snapshots remain available as fallback.

Suggested tests:

```bash
python -m pytest tests/test_api.py::test_autopilot_events_are_persisted
```

Add or adjust test names as needed.

### WCA-M1-T04 — Render AgentPlan Card in Transcript

Status: `DONE` — Codex / 2026-06-01. Added a pure transcript plan mapper, replayable `AgentPlanCard`, and compact responsive styles without changing `ChatPanel.tsx`. Tests: `npm run build`; browser load of `http://localhost:5173` (backend fetch failed because port 8000 is not running).

Objective:

Show users the agent's current plan instead of a generic running line.

Recommended files:

- `frontend/src/app/chatTranscript.ts`
- `frontend/src/components/agent/AgentPlanCard.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/style.css`

Implementation steps:

1. Extend transcript event mapping for `agent_plan_created` and
   `agent_plan_step_updated`.
2. Reuse or extend `AgentPlanCard` rather than adding plan JSX to
   `ChatPanel.tsx`.
3. Show statuses with compact labels:
   - pending
   - running
   - waiting approval
   - done
   - blocked
   - failed
4. Keep long tool inputs hidden behind existing details affordances.

Acceptance criteria:

- Transcript replay after refresh shows the same plan state.
- No large JSX block is added to `ChatPanel.tsx`.
- Mobile width does not cause overlapping text.

Suggested tests:

```bash
npm run build
```

Manual check:

- Start a Local Agent run.
- Refresh browser.
- Confirm plan card replays with the current step.

### WCA-M2-T01 — Formalize Skill Tool Output Contract

Status: `DONE` — Codex / 2026-06-01. Added `SkillToolOutput`, normalized CAD skill planner responses to `proposed_tool` / `proposed_input` / `verification_targets` / `fallback_recommendation`, and kept `next_tool` / `execute_input` / `validation_targets` aliases for compatibility. Tests: `python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py tests/test_agent_autopilot_schema.py`; `python -m pytest tests/test_agent_autopilot_engine.py`.

Objective:

Make all skill tools return a common shape so the agent can reason about them
and the UI can render them consistently.

Recommended files:

- `backend/app/agent_autopilot/schema.py`
- `backend/app/cad_skill_planner.py`
- `backend/tests/test_cad_skill_planner.py`
- `backend/docs` optional if a short contract doc is preferred

Contract:

```json
{
  "status": "ready | unsupported | needs_clarification | error",
  "skill_name": "string",
  "intent": "string",
  "brief": "string",
  "assumptions": ["string"],
  "warnings": ["string"],
  "proposed_tool": "string | null",
  "proposed_input": {},
  "verification_targets": ["string"],
  "fallback_recommendation": "string | null"
}
```

Implementation steps:

1. Decide whether this is a Pydantic model or documented dict contract.
2. Rename existing `next_tool` / `execute_input` fields or provide aliases for
   backward compatibility.
3. Update prompt compaction and context memory compaction to prefer the common
   fields.
4. Add tests for ready, unsupported, and needs-clarification outputs.

Acceptance criteria:

- `cad.plan_build123d_skill` returns the common contract.
- Prompt/memory compaction keeps `proposed_input.code` when needed for the next
  agent action.
- No mutation occurs in skill planner tools.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py
```

### WCA-M2-T02 — Expand CAD Skill Planner: Mounting Plate

Status: `DONE` — Codex / 2026-06-01. Added mounting plate detection, dimension/hole parsing, parameterized build123d template, manufacturing warnings, and contract tests. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_prompts.py tests/test_context_memory.py tests/test_agent_autopilot_engine.py`.

Objective:

Add a deterministic template for flat mounting plates with a rectangular bolt
pattern.

Recommended files:

- `backend/app/cad_skill_planner.py`
- `backend/app/runtime_tool_schemas.py`
- `backend/tests/test_cad_skill_planner.py`

Trigger examples:

- `建模一个120x80x8mm安装板，四个M6孔`
- `make a 100 by 60 mounting plate with 4 holes`

Implementation steps:

1. Detect `安装板`, `mounting plate`, `base plate`.
2. Parse length, width, thickness when present.
3. Default to sensible values when missing:
   - thickness 8mm
   - hole diameter 6mm
   - edge margin at least 2x hole radius
4. Generate build123d with:
   - `base_plate` label
   - `MOUNTING_HOLE_COUNT_X/Y` constants
   - through holes
   - filleted vertical/circular edges where safe
5. Return skill contract with assumptions and verification targets.

Acceptance criteria:

- Generated code compiles.
- If build123d is available, generated code executes to `Compound`.
- Skill warns if hole edge margin violates rule.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py
```

### WCA-M2-T03 — Expand CAD Skill Planner: L Bracket

Status: `DONE` — Codex / 2026-06-01. Added L bracket detection, base/back/rib template with canonical labels, M-hole parsing, and critique verification targets. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`.

Objective:

Add a deterministic L-bracket template suitable for CNC or printing.

Recommended files:

- `backend/app/cad_skill_planner.py`
- `backend/tests/test_cad_skill_planner.py`

Trigger examples:

- `建模一个L型支架，底板80x40，立板60高，M5孔`
- `make an L bracket with ribs`

Implementation steps:

1. Detect `L型支架`, `角码`, `L bracket`, `angle bracket`.
2. Generate named parts:
   - `base_plate`
   - `back_plate`
   - `rib_1`, `rib_2` when ribs requested or defaulted
   - `mounting_hole_pattern`
3. Use constants for thickness, plate dimensions, hole diameters, rib thickness.
4. Ensure minimum thickness >= 3mm unless user explicitly requests another
   manufacturing mode.
5. Return verification targets for `cad.critique`.

Acceptance criteria:

- Generated code uses canonical engineering labels.
- Agent approval message can explain side effects from returned brief.
- `cad.critique` should have enough semantic labels to audit the result.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_engine.py
```

### WCA-M2-T04 — Expand CAD Skill Planner: Enclosure / Box

Status: `DONE` — Codex / 2026-06-01. Added enclosure/case detection, wall thickness parsing, wall/cover/boss template, warnings for thin walls, and tests. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`.

Objective:

Add a deterministic electronics enclosure template with walls, lid, and optional
mounting bosses.

Recommended files:

- `backend/app/cad_skill_planner.py`
- `backend/tests/test_cad_skill_planner.py`

Trigger examples:

- `建模一个100x60x30mm外壳，壁厚3mm`
- `make an electronics enclosure with screw bosses`

Implementation steps:

1. Detect `外壳`, `盒子`, `enclosure`, `case`.
2. Parse outer dimensions and wall thickness.
3. Generate named parts:
   - `wall_body` or `base_plate` depending on current feature graph conventions
   - `cover`
   - `boss_1...boss_4` if screw bosses are requested/defaulted
4. Prefer `rounded_box` helper if available in `cad.execute_build123d` runtime.
5. Keep fixture/load faces planar.

Acceptance criteria:

- Wall thickness is surfaced as editable constants.
- Warnings appear if requested wall thickness is below manufacturing default.
- Generated code remains readable and parameterized.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py
```

### WCA-M2-T05 — Expand CAD Skill Planner: Bushing / Spacer

Status: `DONE` — Codex / 2026-06-01. Added spacer/bushing/sleeve detection, OD/ID/length parsing, axisymmetric template, invalid OD/ID handling, and tests. Tests: `python -m pytest tests/test_cad_skill_planner.py`; `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py`.

Objective:

Add a deterministic axisymmetric template for bushings, spacers, and sleeves.

Recommended files:

- `backend/app/cad_skill_planner.py`
- `backend/tests/test_cad_skill_planner.py`

Trigger examples:

- `建模一个外径20mm内径8mm长度30mm的轴套`
- `make a 10mm spacer with 5mm bore`

Implementation steps:

1. Detect `轴套`, `衬套`, `隔套`, `spacer`, `bushing`, `sleeve`.
2. Parse OD, ID, length.
3. Use `Cylinder` plus center `Hole` or `revolved_profile`.
4. Label the main part `base_plate` only if feature graph expects a mechanical
   primary body; otherwise use a semantic label like `bushing`.
5. Return validation targets for ID < OD and wall thickness >= default.

Acceptance criteria:

- Invalid OD/ID combinations return `needs_clarification` or `error`, not bad code.
- Generated code has constants suitable for `cad.edit_parameter`.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py
```

### WCA-M2-T06 — Add Skill Selection Diagnostics

Status: `DONE` — Codex / 2026-06-01. Added `match_confidence`, `matched_terms`, and `rejection_reason` to skill outputs, prompt/memory compaction, and transcript tool summaries. Tests: `python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_prompts.py tests/test_context_memory.py tests/test_agent_autopilot_schema.py`; `npm run build`.

Objective:

When a skill planner supports or rejects a request, expose why. This makes the
agent feel deliberate rather than arbitrary.

Recommended files:

- `backend/app/cad_skill_planner.py`
- `backend/app/agent_autopilot/prompts.py`
- `frontend/src/app/chatTranscript.ts`

Implementation steps:

1. Add `match_confidence`, `matched_terms`, and `rejection_reason` to skill
   planner output.
2. Compact those fields into prompt memory.
3. In UI, optionally show a small details line:
   - `CAD skill matched: flange / 法兰盘`
   - `No deterministic CAD skill matched; agent will author build123d directly`

Acceptance criteria:

- Unsupported outputs help the agent choose a fallback.
- User can see whether a template or free-form authoring path was selected.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_prompts.py
npm run build
```

### WCA-M3-T01 — Add Adapter Equivalence Tests

Status: `DONE` — Codex / 2026-06-01. Added fake Local/LLM adapter equivalence coverage through `AutopilotEngine`, asserting shared context bootstrap, skill tool execution, policy classification, observation kinds, and approval behavior. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_llm_adapter.py`.

Objective:

Prove Local Agent and LLM API follow the same Autopilot policy/tool/memory path.

Recommended files:

- `backend/tests/test_agent_autopilot_engine.py`
- `backend/tests/test_agent_autopilot_llm_adapter.py`
- `backend/tests/test_agent_autopilot_adapters.py`

Implementation steps:

1. Build a fake Local adapter and fake LLM provider that return the same action:
   call `cad.plan_build123d_skill`.
2. Run both through `AutopilotEngine`.
3. Assert:
   - same policy classification
   - same tool call execution
   - same observation kinds
   - same approval behavior when next action is `cad.execute_build123d`

Acceptance criteria:

- Tests fail if LLM API bypasses skill routing or policy.
- No production code should special-case Local Agent vs LLM API except adapter invocation.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_llm_adapter.py
```

### WCA-M3-T02 — Normalize Timeout / Progress Semantics

Status: `DONE` — Codex / 2026-06-01. Added common progress phase constants, normalized Claude/Codex/LLM API progress callbacks, mapped heartbeat waits to `waiting_for_model`, and tested progress phase order. Tests: `python -m pytest tests/test_agent_autopilot_adapters.py tests/test_agent_autopilot_llm_adapter.py`; `python -m pytest tests/test_agent_autopilot_engine.py`.

Objective:

Make Local CLI and LLM API adapter progress events comparable, so UI can show
the same phases regardless of backend.

Recommended files:

- `backend/app/agent_autopilot/adapters.py`
- `backend/app/agent_autopilot/claude_code_adapter.py`
- `backend/app/agent_autopilot/codex_cli_adapter.py`
- `backend/app/agent_autopilot/llm_api_adapter.py`
- `backend/tests/test_agent_autopilot_adapters.py`

Common phases:

- `started`
- `prompt_prepared`
- `request_sent`
- `waiting_for_model`
- `parsing_output`
- `completed`
- `timeout`
- `error`

Implementation steps:

1. Define phase constants or a `ProgressEvent` typed dict.
2. Update each adapter to emit the common phases.
3. Keep existing event payload fields that the UI already consumes.
4. Reduce generic `waiting_for_cli` reliance by mapping it to
   `waiting_for_model` with adapter metadata.

Acceptance criteria:

- UI no longer needs to infer backend type from free-form message text.
- Local Agent and LLM API both report a meaningful wait phase.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_adapters.py tests/test_agent_autopilot_llm_adapter.py
```

### WCA-M3-T03 — Enforce Single Tool Catalog Source

Status: `DONE` — Codex / 2026-06-01. Added compact tool catalog equivalence coverage so Local and LLM paths share the same tool names/schema summaries, including `cad.plan_build123d_skill`. Tests: `python -m pytest tests/test_agent_autopilot_prompts.py tests/test_api.py::test_health_endpoint`.

Objective:

Prevent Local Agent and LLM API from seeing different tools or schemas.

Recommended files:

- `backend/app/agent_autopilot/prompts.py`
- `backend/app/app_factory.py`
- `backend/tests/test_agent_autopilot_prompts.py`

Implementation steps:

1. Confirm both adapter paths receive `runtime_tools=_rt.list_tools_for_mcp()`.
2. Add a test that constructs both paths and compares compact tool names.
3. Ensure any future adapter-specific constraints are metadata only, not hidden
   tool catalog changes.

Acceptance criteria:

- New tool registration automatically appears to both Local Agent and LLM API.
- Test covers `cad.plan_build123d_skill`.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_prompts.py tests/test_api.py
```

### WCA-M4-T01 — Add Typed `agent_phase_changed` Events

Status: `DONE` — Codex / 2026-06-01. Added `agent_phase_changed` events for context bootstrap, prompt preparation, adapter waits, tool execution, and verification. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py::test_autopilot_plan_events_are_persisted`.

Objective:

Replace vague “waiting” copy with structured, truthful phase changes.

Recommended files:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/app_factory.py`
- `frontend/src/app/chatTranscript.ts`

Implementation steps:

1. Add event type `agent_phase_changed`.
2. Payload should include:
   - `phase`
   - `adapter_id`
   - `plan_step_id`
   - `message`
   - `elapsed_seconds` when available
3. Emit phases at:
   - context bootstrap
   - prompt preparation
   - adapter waiting
   - skill execution
   - tool execution
   - verification
4. Keep `run_status_changed` for compatibility.

Acceptance criteria:

- UI can render progress without parsing English strings.
- Events persist and replay.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py tests/test_api.py
```

### WCA-M4-T02 — Add UI Phase Timeline Row

Status: `DONE` — Codex / 2026-06-01. Mapped typed phase events into compact transcript status rows and reused progress-row collapsing for repeated waits. Tests: `npm run build`.

Objective:

Show a compact live timeline that communicates the run is alive and where it is.

Recommended files:

- `frontend/src/app/chatTranscript.ts`
- `frontend/src/components/chat/StreamingMessage.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/style.css`

Implementation steps:

1. Map `agent_phase_changed` to a transcript item.
2. Collapse repeated wait events into one updating row.
3. Show elapsed time only when useful.
4. Keep styling quiet and dense, aligned with workbench UI.

Acceptance criteria:

- Long Local Agent waits show one stable row, not repeated noisy messages.
- Refresh preserves the latest phase.
- Mobile layout has no text overlap.

Suggested tests:

```bash
npm run build
```

Manual check:

- Start a long adapter run.
- Confirm transcript says which phase is waiting.

### WCA-M4-T03 — Improve Approval Card From Skill Plan

Status: `DONE` — Codex / 2026-06-01. Approval payloads/cards now include skill plan brief, assumptions, warnings, verification targets, and the existing code preview. Tests: `python -m pytest tests/test_agent_autopilot_engine.py`; `npm run build`.

Objective:

When a mutation is proposed from a skill plan, the approval card should show
human-readable assumptions and verification targets, not only code.

Recommended files:

- `backend/app/agent_autopilot/engine.py`
- `frontend/src/app/chatTranscript.ts`
- `frontend/src/components/agent/AgentPlanCard.tsx` or approval component

Implementation steps:

1. Attach most recent skill-plan summary to approval payload when the next tool
   is `cad.execute_build123d`.
2. Include:
   - brief
   - assumptions
   - warnings
   - verification targets
   - code preview
3. Keep code preview collapsed by default if long.

Acceptance criteria:

- For “40mm flange”, approval card clearly says OD, thickness, bore, bolt pattern.
- User can approve/reject without reading raw Python.
- Mutation still cannot execute before approval.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py
npm run build
```

### WCA-M5-T01 — Add Repairable Error Classification

Status: `DONE` — Codex / 2026-06-01. Added error classes and recoverability metadata to policy/tool/adapter/bootstrap error observations. Tests: `python -m pytest tests/test_agent_autopilot_engine.py tests/test_agent_autopilot_schema.py`.

Objective:

Classify tool failures so the agent knows whether it should repair input,
ask the user, or fail honestly.

Recommended files:

- `backend/app/agent_autopilot/schema.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/tests/test_agent_autopilot_engine.py`

Error classes:

- `schema_error`
- `policy_error`
- `tool_runtime_error`
- `cad_build_error`
- `timeout`
- `missing_context`
- `user_decision_required`
- `non_recoverable`

Implementation steps:

1. Add a helper to map exceptions/tool outputs to error classes.
2. Store class in `AutopilotObservation.data`.
3. Do not change retry behavior yet.

Acceptance criteria:

- Tool failures produce structured error observations.
- Existing UI still shows failure message.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py
```

### WCA-M5-T02 — Implement `repair_tool_input` Loop

Status: `DONE` — Codex / 2026-06-01. Added bounded repair attempts, repair plan status, recoverable tool-error loopback, and prompt guidance.

Objective:

Give the agent a bounded chance to repair recoverable tool inputs before failing
the run.

Recommended files:

- `backend/app/agent_autopilot/engine.py`
- `backend/app/agent_autopilot/prompts.py`
- `backend/tests/test_agent_autopilot_engine.py`

Implementation steps:

1. Add `repair_attempts` tracking per run or per plan step.
2. For recoverable classes, feed compact error data back into the adapter.
3. Add a prompt rule:
   - repair only the failed input
   - preserve user intent
   - do not change project id
4. Limit retries, likely 1-2 attempts.

Acceptance criteria:

- Bad JSON/tool input can be repaired once.
- Repeated failure becomes a clear `failed` or `blocked` status.
- No infinite loop.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py
```

### WCA-M5-T03 — CAD Build Failure Repair Prompt

Status: `DONE` — Codex / 2026-06-01. Added compact CAD build-error context and prompt guidance for targeted repair.

Objective:

When build123d code fails, the agent should receive the failing stderr/source
summary and produce a targeted fix.

Recommended files:

- `backend/app/agent_autopilot/context_memory.py`
- `backend/app/agent_autopilot/prompts.py`
- `backend/tests/test_context_memory.py`

Implementation steps:

1. Compact CAD build errors to:
   - exception type
   - top traceback line
   - failing tool input summary
   - source snippet if short enough
2. Add repair guidance:
   - prefer fixing imports/API misuse
   - keep constants and labels
   - avoid broad redesign unless required
3. Integrate with WCA-M5-T02 repair loop.

Acceptance criteria:

- CAD repair prompt is small enough for both Local Agent and LLM API.
- Repaired call still goes through approval if it mutates geometry.

Suggested tests:

```bash
python -m pytest tests/test_context_memory.py tests/test_agent_autopilot_engine.py
```

### WCA-M6-T01 — Add Agent Working State Blackboard

Status: `DONE` — Codex / 2026-06-01. Added run-level blackboard state, prompt injection, tool-result updates, and store round-trip coverage.

Objective:

Create a compact structured memory of the current run beyond raw observations.

Recommended files:

- `backend/app/agent_autopilot/schema.py`
- `backend/app/agent_autopilot/context_memory.py`
- `backend/app/agent_autopilot/engine.py`

Fields:

- `objective`
- `current_mode`
- `accepted_assumptions`
- `open_questions`
- `latest_evidence`
- `current_blockers`
- `last_successful_tool`
- `recommended_next_action`

Implementation steps:

1. Add model and default to run state.
2. Update blackboard after:
   - skill plan ready
   - approval accepted/rejected
   - tool completed
   - critique produced findings
   - user follow-up received
3. Feed compact blackboard into adapter prompt before raw observation tail.

Acceptance criteria:

- Adapter prompt can state current objective and latest blocker without scanning
  full history.
- Store round-trip works.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py tests/test_context_memory.py
```

### WCA-M6-T02 — Persist Accepted Assumptions

Status: `DONE` — Codex / 2026-06-01. Approved skill-plan assumptions are persisted into working state and appear in the next prompt.

Objective:

When a user approves a skill-generated CAD plan, record its assumptions as
accepted for the run and future follow-ups.

Recommended files:

- `backend/app/agent_autopilot/engine.py`
- `backend/tests/test_agent_autopilot_engine.py`

Implementation steps:

1. Detect approval of a tool call that originated from a skill plan.
2. Copy assumptions into `working_state.accepted_assumptions`.
3. On later follow-up, include accepted assumptions in prompt context.

Acceptance criteria:

- If user approves default flange thickness, later “make it thicker” has a
  known baseline.
- Rejected approval does not mark assumptions as accepted.

Suggested tests:

```bash
python -m pytest tests/test_agent_autopilot_engine.py
```

### WCA-M6-T03 — Add Run Resume Summary

Status: `DONE` — Codex / 2026-06-01. Continued adapter turns use compact resume summaries with working state, current plan step, latest observation, and pending/blocker context.

Objective:

When an interrupted or continued run resumes, the adapter gets a concise state
summary instead of stale full context.

Recommended files:

- `backend/app/agent_autopilot/context_memory.py`
- `backend/app/agent_autopilot/engine.py`
- `backend/tests/test_context_memory.py`

Implementation steps:

1. Add `build_resume_prompt` or extend incremental prompt.
2. Include:
   - current objective
   - current plan step
   - latest tool result/error
   - accepted assumptions
   - pending approval or blocker
3. Use it on continue/reply/follow-up paths.

Acceptance criteria:

- Resuming after approval does not re-send a bulky full prompt.
- Follow-up runs retain enough context to avoid asking repeated questions.

Suggested tests:

```bash
python -m pytest tests/test_context_memory.py tests/test_agent_autopilot_engine.py
```

### WCA-QA-T01 — End-to-End Smoke: 40mm Flange

Status: `DONE` — Codex / 2026-06-01. Added backend smoke for skill plan, approval, CAD execution, critique follow-up, accepted assumptions, and final response.

Objective:

Prove the intended user flow works:

```text
User: 建模一个40mm的法兰盘
Agent -> cad.plan_build123d_skill
Agent -> cad.execute_build123d approval
User approves
Runtime executes CAD
Runtime runs cad.critique follow-up
UI shows result and verification
```

Recommended files:

- `backend/tests/test_agent_autopilot_engine.py`
- `backend/tests/test_api.py`
- frontend manual checklist

Implementation steps:

1. Add a backend fake-action scenario matching the flow.
2. If build123d is available in CI/dev, run an integration test guarded by
   availability.
3. Manually test in browser once UI plan/phase tasks land.

Acceptance criteria:

- No direct CAD generation endpoint is used.
- Mutating CAD call requires approval.
- Critique follow-up runs automatically after approval/execution.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_engine.py
```

### WCA-QA-T02 — End-to-End Smoke: Unsupported CAD Request

Status: `DONE` — Codex / 2026-06-01. Added unsupported CAD smoke coverage for skill diagnostics, fallback source inspection, approval gating, and final fallback completion.

Objective:

Prove unsupported skill requests still behave like a capable agent.

Scenario:

```text
User: 建模一个复杂机器人外壳
Agent -> cad.plan_build123d_skill
Skill -> unsupported with fallback recommendation
Agent -> cad.get_source or direct authored build123d path
Agent -> approval before mutation
```

Implementation steps:

1. Add fake-action test for unsupported skill output.
2. Ensure prompt/memory keeps `fallback_recommendation`.
3. UI should display that no deterministic skill matched.

Acceptance criteria:

- Unsupported skill does not block the run by itself.
- Agent explains fallback path.
- Approval still gates mutation.

Suggested tests:

```bash
python -m pytest tests/test_cad_skill_planner.py tests/test_agent_autopilot_engine.py
```

## Handoff Protocol For Future LLM Agents

Before starting:

1. Read this document.
2. Read root `AGENTS.md`.
3. Read `aieng-ui/docs/chat-agent-transcript-current-flow.md`.
4. Check `git status --short` and do not overwrite unrelated work.
5. Pick exactly one task ID unless the user asks for a larger batch.

During work:

1. Mark the task `IN_PROGRESS` in the task board.
2. Keep edits inside the task's recommended files unless tests reveal a needed
   dependency.
3. Add or update tests in the same commit-sized unit.
4. Run the suggested tests.

When finished:

1. Mark the task `DONE`.
2. Add a short note in the task board:
   - files changed
   - tests run
   - remaining limitations
3. If blocked, mark `BLOCKED` and state the exact missing dependency or decision.

## Design Principles

- Agent remains the orchestrator.
- Skill tools are read-only planners/authors/reviewers unless explicitly marked
  and approved as mutations.
- Runtime tools remain the only side-effect path.
- Local Agent and LLM API share the same plan, memory, policy, and tool catalog.
- UI displays truthful state, not speculative thinking.
- Verification is a first-class step, not an afterthought.
- Failure should usually produce a repair opportunity before the run fails.
