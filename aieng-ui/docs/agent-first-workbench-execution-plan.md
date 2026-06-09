# Agent-First Workbench Simplification Execution Plan

Status: **Superseded by MCP-first #17 product cutover**
Last updated: **2026-06-04**
Owner: **AIENG workbench maintainers + handoff LLM agents**

> **2026-06-04 update:** this older "right rail Agent workbench" direction has
> been superseded. The active product surface is now a full-width live CAD/CAE
> viewer plus the Workbench MCP server. The in-UI chat/composer/right rail is
> retired from active frontend wiring; backend chat/autopilot endpoints remain
> compatibility-only. External MCP agents are the primary CAD/CAE orchestration
> path.

## Purpose

This document is the implementation handoff plan for simplifying the current
`aieng-ui` product into an Agent-first CAD/CAE workbench.

The target product shape is:

```text
Left: model work area
  - 3D viewer
  - face / edge / group selection
  - field overlays
  - compact project and validation status

Right: Agent workbench
  - chat
  - selected geometry context
  - agent plan cards
  - human approval cards
  - result explanation cards
```

The core principle is:

```text
Use Agent wherever possible.
Use UI controls only for context, visibility, and human-in-the-loop approval.
Do not expose internal tools as the primary user workflow.
```

## Current State

Relevant files:

| Area | File | Current role |
|---|---|---|
| Main shell | `frontend/src/App.tsx` | Owns most UI state, selected project, chat, CAE, runtime, approval, viewer state, and routing between control-pane modes. |
| Mode list | `frontend/src/appConstants.ts` | Defines seven right-pane modes: `chat`, `project`, `agent`, `cae`, `recommend`, `copilot`, `pilot`. |
| Viewer | `frontend/src/components/ViewerPane.tsx` | Left-side model workspace with project facts, validation state, viewer, picked faces, highlighting, and field overlay wiring. |
| Chat | `frontend/src/components/panels/ChatPanel.tsx` | Best current candidate for the permanent right-side Agent workbench. |
| Tool panel | `frontend/src/components/panels/AgentPanel.tsx` | Exposes internal capability browser, workflow runner, benchmark, semantic map. Should become debug/developer-only. |
| CAE panel | `frontend/src/components/panels/CaePanel.tsx` | Exposes manual CAE import/result controls. Should be converted into Agent cards or debug-only controls. |
| Backend agent plan | `backend/app/agent_engine.py` | Builds guarded agent plans from LLM or heuristic planner. |
| Backend capabilities | `backend/app/agent_workbench.py` | Lists tool/capability metadata and chat connections. |
| Backend API | `backend/app/app_factory.py` | Provides `/api/agent/plan`, `/api/agent/runs`, `/api/runtime/runs`, approval endpoints, CAD generation, CAE, B-Rep, and activity stream. |

Important existing endpoints:

| Endpoint | Current purpose | Target role |
|---|---|---|
| `POST /api/agent/plan` | Create an Agent plan from natural language. | Primary planning path. |
| `POST /api/agent/runs` | Execute Agent plan through runtime tools. | Primary execution path. |
| `POST /api/runtime/runs/{id}/approve` | Resume approval-gated run. | Human-in-the-loop approval. |
| `POST /api/runtime/runs/{id}/reject` | Reject approval-gated run. | Human-in-the-loop rejection. |
| `GET /api/agent-activity/stream` | Live external agent/tool events. | Viewer refresh and progress. |
| `GET /api/projects/{id}/brep-graph` | Face/group/feature metadata. | Selection context for Agent. |
| `POST /api/projects/{id}/brep/pick-face` | Resolve picked 3D point to face. | Selection context for Agent. |
| `POST /api/projects/{id}/generate-cad-stream` | Direct chat-first CAD generation. | Short-term compatibility; eventually routed through Agent. |
| `POST /api/projects/{id}/run-simulation-stream` | Direct simulation path. | Short-term compatibility; eventually routed through Agent. |

## Product Target

### Primary workflow

```text
User describes intent or selects geometry
  -> Agent observes project + selected geometry
  -> Agent proposes a plan
  -> User approves only side-effecting or expensive steps
  -> Runtime executes tools
  -> Viewer refreshes
  -> Agent explains result and suggests next action
```

### Top-level modes

The user-facing right rail should not expose seven equivalent tabs. The target
top-level model is:

| Mode | User-facing? | Purpose |
|---|---:|---|
| `agent` | Yes | Permanent chat + Agent plan/results/approval surface. |
| `project` | Yes, compact | Project create/import/select and current project facts. |
| `debug` | Optional/dev only | Capability browser, raw workflows, benchmarks, raw artifacts, old manual panels. |

Everything else becomes Agent-owned capability:

| Current panel/mode | Target |
|---|---|
| `chat` | Rename/reshape into `agent`. |
| `agent` | Move to `debug`. |
| `cae` | Convert key output into Agent cards; keep manual import tools in `debug`. |
| `recommend` | Agent result card or suggested action list. |
| `copilot` | Agent-managed iterative loop card, not primary tab. |
| `pilot` | Internal planner/debug panel. |

## Human-In-The-Loop Policy

Use four permission levels.

| Level | Examples | UI behavior |
|---|---|---|
| Auto | Read `agent_context`, read B-Rep graph, summarize, explain, recommend. | Run immediately and show observation. |
| Preview | Generate plan, generate code draft, CAE preflight, solver readiness check. | Show reviewable card, no package mutation. |
| Approve | `cad.execute_build123d`, `cad.refine`, `cae.apply_setup_patch`, `cae.generate_solver_input`, package writes. | Show approval card with side effects and tool name. |
| Explicit confirm | `cae.run_solver`, destructive replacement, batch runs. | Require clear text and dedicated approval action. |

Do not make the user approve every read-only step. Do not hide side effects.

## Non-Goals

- Do not redesign the entire backend runtime.
- Do not delete existing panels in the first implementation pass.
- Do not remove existing direct CAD/CAE endpoints until Agent parity exists.
- Do not build a full traditional CAD property editor.
- Do not expose `.aieng` internal package structure as normal user workflow.
- Do not read `aieng/src/` as a capability reference; use `aieng-ui/backend` and runtime tools.

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

If the LLM cannot update the document, it must paste the same handoff block in
the final response.

### Branch and PR discipline

Recommended branch naming:

```text
codex/agent-first-workbench-phase-N
```

One PR should cover one phase or one vertical slice. Avoid one giant PR covering
all phases.

### Verification baseline

Frontend checks:

```powershell
cd aieng-ui/frontend
npm install
npm run build
```

Backend targeted checks:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_agent_context.py tests/test_contextual_chat.py tests/test_intent_planner.py
```

When touching runtime, approval, or CAE:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_runtime_tools.py tests/test_agent_observation.py tests/test_simulation_runner.py
```

When touching CAD generation:

```powershell
cd aieng-ui/backend
python -m pytest tests/test_cad_generation.py tests/test_cad_observation.py tests/test_brep_graph.py
```

## Implementation Phases

### Phase 0 - Baseline and Guardrails

Goal: make the codebase easier to change without breaking the current demo.

#### AFW-P0-T01 - Record Current Frontend Baseline

Status: `DONE`

Scope:

- Run the frontend build.
- Record current build result in the task ledger.
- Do not modify production code.

Files likely touched:

- This document only.

Steps:

1. Run `npm run build` in `aieng-ui/frontend`.
2. If it fails, capture the first actionable error.
3. Mark this task `DONE` if build passes, or `BLOCKED` if build fails for unrelated existing reasons.

Acceptance criteria:

- The task ledger records build status.
- Any existing failure is documented before UI refactor begins.

Verification:

- `npm run build`

#### AFW-P0-T02 - Add Workbench Simplification Feature Flag

Status: `DONE`

Scope:

- Add a frontend feature flag so the new right rail can be developed without deleting old panels.
- Use a simple boolean constant first; do not introduce a feature flag framework.

Files likely touched:

- `frontend/src/appConstants.ts`
- `frontend/src/App.tsx`

Suggested implementation:

```ts
export const AI_FIRST_WORKBENCH_ENABLED = true;
```

Then use it in `App.tsx` to choose between old `CONTROL_PANE_MODES` rendering
and new simplified mode rendering.

Acceptance criteria:

- Existing app still renders when the flag is true.
- Old mode rendering can still be restored by setting the flag false.
- No behavior change outside control-pane rendering.

Verification:

- `npm run build`

#### AFW-P0-T03 - Define New Right-Rail Mode Type

Status: `DONE`

Scope:

- Introduce a smaller mode type for the new shell.
- Keep old `ControlPaneMode` until migration finishes.

Files likely touched:

- `frontend/src/appTypes.ts`
- `frontend/src/appConstants.ts`

Suggested types:

```ts
export type WorkbenchPaneMode = "agent" | "project" | "debug";
```

Suggested constants:

```ts
export const WORKBENCH_PANE_MODES = [
  { id: "agent", label: "Agent", detail: "Chat, plans, approvals" },
  { id: "project", label: "Project", detail: "Import and project facts" },
  { id: "debug", label: "Debug", detail: "Tools and raw workflow panels" },
] as const;
```

Acceptance criteria:

- New type and constants exist.
- Old types remain untouched.
- No panel behavior changes yet.

Verification:

- `npm run build`

### Phase 1 - Simplify the Workbench Shell

Goal: make the visible product match left model area + right Agent workbench.

#### AFW-P1-T01 - Extract Right Rail Component

Status: `DONE`

Scope:

- Extract the right-side `<aside className="side-pane">...</aside>` from
  `App.tsx` into a new component.
- Do not change behavior in this task.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/components/WorkbenchRightRail.tsx`

Suggested component:

```tsx
export function WorkbenchRightRail(props: WorkbenchRightRailProps) {
  return <aside className="side-pane">...</aside>;
}
```

Implementation notes:

- Keep props explicit.
- Do not introduce global state.
- If prop count is too high, group props by panel:
  `chatProps`, `projectProps`, `debugProps`, `caeProps`.

Acceptance criteria:

- `App.tsx` render method becomes smaller.
- Current tabs and panels still behave as before.
- No visual redesign yet.

Verification:

- `npm run build`

#### AFW-P1-T02 - Add New Agent-First Mode Header

Status: `DONE`

Scope:

- When `AI_FIRST_WORKBENCH_ENABLED` is true, show only `Agent`, `Project`, and `Debug` right-rail modes.
- Default mode should be `agent`.
- Keep old seven-mode behavior behind the flag.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/components/WorkbenchRightRail.tsx`
- `frontend/src/appConstants.ts`
- `frontend/src/appTypes.ts`

Acceptance criteria:

- User sees only three top-level right-rail modes in the new shell.
- `Agent` renders `ChatPanel`.
- `Project` renders `ProjectPanel`.
- `Debug` renders old internal panels.

Verification:

- `npm run build`

#### AFW-P1-T03 - Move Internal Panels Under Debug

Status: `DONE`

Scope:

- Place the following existing panels under `Debug`:
  - `AgentPanel`
  - `CaePanel`
  - `RecommendationsPanel`
  - `CopilotLoopPanel`
  - `IntentPlannerCard`
- Use a small debug sub-tab or accordion inside `Debug`.
- Do not delete panels.

Files likely touched:

- `frontend/src/components/WorkbenchRightRail.tsx`
- Optional: `frontend/src/components/panels/DebugPanel.tsx`

Suggested sub-tabs:

```text
Tools
CAE
Recommendations
Loop
Planner
```

Acceptance criteria:

- Normal user path is not crowded by internal panels.
- All old panels remain reachable from `Debug`.
- The active project and props still flow correctly.

Verification:

- `npm run build`

#### AFW-P1-T04 - Compact Viewer Header

Status: `DONE`

Scope:

- Reduce the visual weight of `ViewerPane` header and toolbar.
- Keep project name, validation state, selected field/preview state.
- Move less important facts into a status bar or compact details line.

Files likely touched:

- `frontend/src/components/ViewerPane.tsx`
- `frontend/src/style.css`

Acceptance criteria:

- Model viewer gets more vertical space.
- Runtime/global settings remain reachable.
- No information is fully lost; lower-priority facts are just less prominent.

Verification:

- `npm run build`
- Manual browser check if a dev server is running.

### Phase 2 - Introduce Agent Turn State

Goal: make chat, plans, approvals, and results first-class UI state instead of
scattered special cases.

#### AFW-P2-T01 - Add Agent Turn Types

Status: `DONE`

Scope:

- Add frontend types for Agent turns, plan cards, approval cards, observations, and selected geometry context.

Files likely touched:

- `frontend/src/appTypes.ts`
- Possibly `frontend/src/types.ts`

Suggested types:

```ts
export type AgentTurnStatus =
  | "draft"
  | "planning"
  | "planned"
  | "awaiting_approval"
  | "running"
  | "completed"
  | "failed"
  | "rejected";

export type SelectedGeometryContext = {
  pointers: string[];
  faces: PickedFace[];
  highlightedFaceIds: string[];
};

export type AgentTurn = {
  id: string;
  userMessage: string;
  createdAt: string;
  status: AgentTurnStatus;
  projectId: string | null;
  selectedGeometry?: SelectedGeometryContext;
  plan?: ChatHistoryItem["plan"];
  runId?: string;
  summary?: string;
  errors?: string[];
};
```

Acceptance criteria:

- Types compile.
- No runtime behavior changes yet.

Verification:

- `npm run build`

#### AFW-P2-T02 - Build AgentPlanCard Component

Status: `DONE`

Scope:

- Extract plan rendering from `ChatPanel` into reusable card component.
- Keep current chat display compatible with existing `ChatHistoryItem`.

Files likely touched:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/agent/AgentPlanCard.tsx`
- `frontend/src/style.css`

Acceptance criteria:

- Chat plan items render through `AgentPlanCard`.
- Approval-required steps are visually distinct.
- Tool names are visible in compact form for traceability.

Verification:

- `npm run build`

#### AFW-P2-T03 - Build ApprovalCard Component

Status: `DONE`

Scope:

- Extract runtime approval UI from `ChatPanel` into reusable component.
- The card must show:
  - pending tool name
  - run status
  - side-effect summary if available
  - approve button
  - reject button

Files likely touched:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/agent/ApprovalCard.tsx`
- `frontend/src/style.css`

Acceptance criteria:

- Existing `lastRuntimeRun?.status === "awaiting_approval"` behavior is unchanged.
- Approval and reject still call existing handlers.
- UI text clearly communicates side effects.

Verification:

- `npm run build`

#### AFW-P2-T04 - Build AgentResultCard Component

Status: `DONE`

Scope:

- Extract CAD result, preprocess result, simulation result, advisory, and artifact links into focused result cards.
- Do this incrementally; start with CAD and simulation result only.

Files likely touched:

- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/agent/AgentResultCard.tsx`
- `frontend/src/style.css`

Acceptance criteria:

- CAD result still shows face count, feature count, and generated code details.
- Simulation result still shows stress, displacement, FoS, node count, heatmap toggle.
- ChatPanel becomes shorter and easier to maintain.

Verification:

- `npm run build`

### Phase 3 - Make Agent the Default Execution Path

Goal: reduce hard-coded frontend intent routing and move decisions to Agent plan/run.

#### AFW-P3-T01 - Package Selected Geometry With User Prompt

Status: `DONE`

Scope:

- When sending a chat message, include selected geometry context.
- Short-term: append structured context to the prompt.
- Longer-term: send a typed field to backend.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/api.ts`

Short-term prompt format:

```text
User request:
<message>

Selected geometry:
- @face:f_xxx planar load_surface
- @face:f_yyy cylindrical unknown
```

Acceptance criteria:

- If faces are picked, the Agent receives their pointers.
- Existing autocomplete still works.
- No backend API changes required for the first pass.

Verification:

- `npm run build`

#### AFW-P3-T02 - Add Typed Selected Geometry to Agent API

Status: `DONE`

Scope:

- Extend `/api/agent/plan` and `/api/agent/runs` payloads with optional `selected_geometry`.
- Include this context in the Agent planning prompt.

Files likely touched:

- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `backend/app/app_factory.py`
- `backend/app/agent_engine.py`
- Backend tests for agent planning.

Suggested payload:

```json
{
  "message": "...",
  "project_id": "...",
  "selected_geometry": {
    "pointers": ["@face:f_top_001"],
    "faces": [
      {
        "pointer": "@face:f_top_001",
        "label": "top planar face",
        "surface_type": "plane",
        "roles": ["load_surface"]
      }
    ]
  }
}
```

Acceptance criteria:

- Backend accepts payload without breaking old clients.
- LLM planning prompt includes selected geometry.
- Heuristic planner ignores the field safely if it does not need it.

Verification:

- `npm run build`
- `python -m pytest tests/test_intent_planner.py tests/test_agent_context.py`

#### AFW-P3-T03 - Route General Chat Through Agent Plan/Run

Status: `DONE`

Scope:

- Change `sendUnified` so the default path is:
  1. create Agent run or plan
  2. render plan/result/approval
- Keep direct handlers for CAD generation and simulation only as compatibility fallback.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`

Implementation rule:

- If prompt clearly requires an immediate side-effecting action, create a plan first.
- If prompt is informational, run read-only Agent steps automatically.
- Do not remove `executeCadFromPrompt` or `executeSimulation` yet.

Acceptance criteria:

- Normal chat messages use `/api/agent/runs` or `/api/agent/plan`.
- Approval-gated steps still pause.
- Existing CAD/simulation demos still work.

Verification:

- `npm run build`
- Manual test:
  - "summarize current model"
  - "make this bracket thicker"
  - "run simulation"

#### AFW-P3-T04 - Convert Direct CAD Generation Into Agent-Compatible Card

Status: `DONE`

Scope:

- Keep `/generate-cad-stream` if needed, but represent it as an Agent action in the UI.
- The user should see "Agent is generating CAD" rather than a separate hidden flow.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/agent/AgentResultCard.tsx`

Acceptance criteria:

- Streaming CAD progress appears inside the Agent workbench.
- Final result is rendered as an Agent result card.
- Viewer refresh still occurs.

Verification:

- `npm run build`
- Manual CAD generation test.

### Phase 4 - Selection Inspector and Geometry-Aware Agent Actions

Goal: make selecting faces/edges the natural way to guide the Agent.

#### AFW-P4-T01 - Add Selection Inspector Card

Status: `DONE`

Scope:

- Add a compact selected-geometry card above or inside the Agent workbench.
- Show last picked faces and clear action.

Files likely touched:

- `frontend/src/components/agent/SelectionInspectorCard.tsx`
- `frontend/src/components/WorkbenchRightRail.tsx`
- `frontend/src/style.css`

Card content:

```text
Selected geometry
@face:f_top_001
plane · roles: load_surface

[Use in prompt] [Clear]
```

Acceptance criteria:

- Picked faces are visible without opening debug panels.
- Clicking pointer still highlights model.
- Clear button clears picked faces.

Verification:

- `npm run build`

#### AFW-P4-T02 - Add Geometry Suggested Actions

Status: `DONE`

Scope:

- Show a small set of context actions for selected faces.
- Actions should insert natural-language prompts, not directly mutate the model.

Files likely touched:

- `frontend/src/components/agent/SelectionInspectorCard.tsx`
- `frontend/src/App.tsx`

Suggested actions:

| Action | Prompt inserted |
|---|---|
| Add holes | `Add mounting holes on @face:...` |
| Offset face | `Offset @face:... by 2 mm` |
| Fillet nearby edge | `Fillet the relevant edge near @face:... by 2 mm` |
| Fixed support | `Use @face:... as fixed support for preprocessing` |
| Apply load | `Apply a load on @face:...` |

Acceptance criteria:

- Actions fill the chat input.
- User still sends/edits the prompt.
- No direct tool execution from these buttons.

Verification:

- `npm run build`

#### AFW-P4-T03 - Add Edge Selection Placeholder Contract

Status: `TODO`

Scope:

- The current visible code focuses on picked faces. Define type and UI placeholder for edges without implementing full picking if backend support is incomplete.

Files likely touched:

- `frontend/src/appTypes.ts`
- `frontend/src/components/agent/SelectionInspectorCard.tsx`

Suggested type:

```ts
export type PickedEdge = {
  pointer: string;
  label: string;
  curve_type?: string;
  roles: string[];
};
```

Acceptance criteria:

- The UI and types are ready for edge support.
- No fake edge behavior is presented to users.

Verification:

- `npm run build`

### Phase 5 - Agent-Owned CAE Flow

Goal: make preprocessing, solving, and post-processing feel like Agent work, not manual panel work.

#### AFW-P5-T01 - Convert Preprocess Result Into Agent Card

Status: `TODO`

Scope:

- Extract current preprocess result rendering from `ChatPanel`.
- Add clearer side-effect and artifact summary.

Files likely touched:

- `frontend/src/components/agent/AgentResultCard.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`

Acceptance criteria:

- Material, BC count, load count, mesh size, warnings, and artifacts remain visible.
- The card suggests the next step: solver preflight or edit setup.

Verification:

- `npm run build`

#### AFW-P5-T02 - Add Solver Preflight Card

Status: `TODO`

Scope:

- Render `cae.prepare_solver_run` or structural preflight output as a card.
- Show readiness, missing items, and next recommended action.

Files likely touched:

- `frontend/src/components/agent/SolverPreflightCard.tsx`
- `frontend/src/components/agent/AgentResultCard.tsx`
- Possibly backend response mapping in `App.tsx`.

Acceptance criteria:

- User can understand why solver can or cannot run.
- Missing material/BC/load/mesh is shown plainly.
- No solver execution happens from preflight.

Verification:

- `npm run build`
- `python -m pytest tests/test_runtime_tools.py tests/test_structural_adapter.py`

#### AFW-P5-T03 - Unify Solver Approval UI

Status: `TODO`

Scope:

- Replace separate `simulationPending` card with the generic `ApprovalCard` where possible.
- Keep `executeSimulation` fallback while runtime Agent path matures.

Files likely touched:

- `frontend/src/App.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`
- `frontend/src/components/agent/ApprovalCard.tsx`

Acceptance criteria:

- Solver execution is clearly approval-gated.
- User sees "Run Gmsh + CalculiX" or equivalent explicit side effect.
- Reject/cancel works.

Verification:

- `npm run build`

#### AFW-P5-T04 - Convert Postprocess Result Into Agent Explanation

Status: `TODO`

Scope:

- After simulation, show result summary as engineering explanation:
  - max von Mises
  - max displacement
  - FoS
  - pass/fail vs targets
  - hotspot pointer if available
  - heatmap toggle

Files likely touched:

- `frontend/src/components/agent/AgentResultCard.tsx`
- `frontend/src/components/panels/ChatPanel.tsx`

Acceptance criteria:

- Result card is understandable without opening `CaePanel`.
- Heatmap toggle still works.
- Target verdict remains visible.

Verification:

- `npm run build`

### Phase 6 - Debug Mode and Legacy Panel Containment

Goal: keep power tools available without making them the product.

#### AFW-P6-T01 - Create DebugPanel Wrapper

Status: `TODO`

Scope:

- Create a wrapper for internal panels.
- Add a short label that this is a developer/debug area.
- Do not add long in-app explanation text.

Files likely touched:

- `frontend/src/components/panels/DebugPanel.tsx`
- `frontend/src/components/WorkbenchRightRail.tsx`

Debug sections:

```text
Tools
Manual CAE
Recommendations
Loop
Planner
Artifacts
```

Acceptance criteria:

- Internal panels are reachable.
- They are no longer first-level product tabs.
- No props are lost.

Verification:

- `npm run build`

#### AFW-P6-T02 - Add Debug Visibility Switch

Status: `TODO`

Scope:

- Hide `Debug` by default unless a simple local setting or feature flag enables it.
- For development builds, it can remain visible.

Files likely touched:

- `frontend/src/appConstants.ts`
- `frontend/src/components/WorkbenchRightRail.tsx`
- Optional: settings drawer.

Suggested constant:

```ts
export const DEBUG_WORKBENCH_PANELS_ENABLED = true;
```

Acceptance criteria:

- Product demos can hide debug mode.
- Developers can re-enable it easily.

Verification:

- `npm run build`

### Phase 7 - Backend Agent Planning Improvements

Goal: make backend Agent planning aware of selected geometry and CAD/CAE stage.

#### AFW-P7-T01 - Extend Compact Context With Selected Geometry

Status: `TODO`

Scope:

- Update Agent planning payload handling so selected geometry is passed through to the LLM prompt.
- Keep payload optional.

Files likely touched:

- `backend/app/agent_engine.py`
- `backend/app/app_factory.py`
- `backend/tests/test_contextual_chat_pointers.py` or new test.

Acceptance criteria:

- LLM prompt includes selected pointers and roles.
- No selected geometry produces no change.
- Invalid selected geometry payload is ignored safely.

Verification:

- `python -m pytest tests/test_contextual_chat_pointers.py tests/test_intent_planner.py`

#### AFW-P7-T02 - Teach Heuristic Planner Selection-Aware CAE

Status: `TODO`

Scope:

- If message includes selected face pointers and asks for fixed support/load/preprocess, heuristic planner should propose relevant CAE setup/preflight steps when tools are available.

Files likely touched:

- `backend/app/agent_engine.py`
- Tests in `backend/tests/`.

Acceptance criteria:

- "Use selected face as fixed support" produces a reviewable plan.
- Missing project ID still warns clearly.
- No unsupported mutation is invented.

Verification:

- `python -m pytest tests/test_intent_planner.py tests/test_agent_observation.py`

#### AFW-P7-T03 - Prefer Runtime CAD Tools Over Legacy Direct Endpoints

Status: `TODO`

Scope:

- Agent planner should prefer registered tools:
  - `cad.get_source`
  - `cad.execute_build123d`
  - `cad.refine`
  - `cad.get_named_part_bbox`
- Avoid routing new UX through old direct generation endpoints when runtime tools are available.

Files likely touched:

- `backend/app/agent_engine.py`
- `frontend/src/App.tsx`

Acceptance criteria:

- CAD mutations appear as approval-gated Agent steps.
- `cad.execute_build123d` side effects are visible before approval.
- Existing direct CAD endpoints remain for compatibility.

Verification:

- `python -m pytest tests/test_cad_generation.py tests/test_runtime_tools.py`
- `npm run build`

### Phase 8 - Visual Polish and Usability

Goal: make the simplified workbench feel deliberate, not merely hidden.

#### AFW-P8-T01 - Restyle Right Rail for Agent Workbench

Status: `TODO`

Scope:

- Make the right rail read as a focused Agent console.
- Avoid nested cards.
- Keep controls compact.

Files likely touched:

- `frontend/src/style.css`
- `frontend/src/components/panels/ChatPanel.tsx`
- Agent card components.

Acceptance criteria:

- Chat input remains visible and usable.
- Approval/result cards are scannable.
- Text does not overflow on common desktop widths.

Verification:

- `npm run build`
- Browser screenshot/manual inspection.

#### AFW-P8-T02 - Restyle Viewer as Model Work Area

Status: `TODO`

Scope:

- Emphasize the model viewport as the primary workspace.
- Keep selected model/project state available but compact.

Files likely touched:

- `frontend/src/components/ViewerPane.tsx`
- `frontend/src/style.css`

Acceptance criteria:

- Viewer has more useful space.
- Selection/highlight affordances remain obvious.
- Field overlay state remains visible.

Verification:

- `npm run build`
- Browser screenshot/manual inspection.

### Phase 9 - Documentation and Release Readiness

Goal: make the new architecture understandable to future LLMs and maintainers.

#### AFW-P9-T01 - Update Technical Roadmap

Status: `TODO`

Scope:

- Add Agent-first workbench simplification entry to `technical-roadmap.md`.
- Link to this execution plan.

Files likely touched:

- `aieng-ui/docs/technical-roadmap.md`

Acceptance criteria:

- Roadmap records new direction.
- Current status and next milestone are clear.

Verification:

- Markdown review.

#### AFW-P9-T02 - Add Developer Handoff Notes

Status: `TODO`

Scope:

- Document:
  - where right rail mode state lives
  - how Agent turns are represented
  - how approval cards are wired
  - which panels are debug-only

Files likely touched:

- This document
- Optional new `aieng-ui/docs/agent-first-workbench-handoff.md`

Acceptance criteria:

- A fresh LLM can continue without rediscovering architecture.
- Known compatibility fallbacks are listed.

Verification:

- Markdown review.

## Task Ledger

Update this table as work progresses.

| Task ID | Status | Owner/session | Files changed | Verification | Notes |
|---|---|---|---|---|---|
| AFW-P0-T01 | DONE | Codex / 2026-05-27 | `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Baseline recorded. Vite emitted a non-blocking chunk-size warning: `dist/assets/index-BtZI6Nj_.js` is 1,047.05 kB after minification. |
| AFW-P0-T02 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/appConstants.ts`; `aieng-ui/frontend/src/App.tsx`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added `AI_FIRST_WORKBENCH_ENABLED` and routed right-rail tab/detail rendering through the flag. Current flag-on path preserves existing modes until the simplified mode constants land in AFW-P0-T03 / AFW-P1-T02. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-DRBpNBwx.js` is 1,047.10 kB after minification. |
| AFW-P0-T03 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/appTypes.ts`; `aieng-ui/frontend/src/appConstants.ts`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added `WorkbenchPaneMode` and `WORKBENCH_PANE_MODES` for the future Agent / Project / Debug shell. No panel behavior changed. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-DRBpNBwx.js` is 1,047.10 kB after minification. |
| AFW-P1-T01 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/frontend/src/components/WorkbenchRightRail.tsx`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Extracted the right-side rail shell into `WorkbenchRightRail` with explicit mode/header props and children for existing panels. Current tabs and panel rendering remain unchanged. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-PARb94yb.js` is 1,047.35 kB after minification. |
| AFW-P1-T02 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/frontend/src/components/WorkbenchRightRail.tsx`; `aieng-ui/frontend/src/components/common.tsx`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | With `AI_FIRST_WORKBENCH_ENABLED=true`, the right rail now shows `Agent`, `Project`, and `Debug`. Agent renders `ChatPanel`, Project renders `ProjectPanel`, and Debug currently renders the old internal panels sequentially until AFW-P1-T03 adds debug sub-tabs. Legacy seven-mode rendering remains behind the flag. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-Db_a1ljY.js` is 1,047.96 kB after minification. Browser/manual check was not run because no browser automation tool was available in this session. |
| AFW-P1-T03 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/frontend/src/components/panels/DebugPanel.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added `DebugPanel` with compact sub-tabs for Tools, CAE, Recommendations, Loop, and Planner. In Agent-first mode, old internal panels are reachable only under Debug; legacy seven-mode behavior remains behind the feature flag. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-BkPrE670.js` is 1,048.82 kB after minification. Browser/manual check was not run because no browser automation tool was available in this session. |
| AFW-P1-T04 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/components/ViewerPane.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Compacted the viewer header by moving project, validation, and preview state into small header chips and converting the old large project toolbar into a lighter status strip for STEP, model ID, feature count, and topology count. Viewer stage margins/header spacing were reduced so the model viewport gets more vertical room. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-ppDpRk5X.js` is 1,049.19 kB after minification. Browser/manual check was not run because no browser automation tool was available in this session. |
| AFW-P2-T01 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/appTypes.ts`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added `AgentTurnStatus`, `SelectedGeometryContext`, and `AgentTurn` frontend types for future chat/plan/approval/result state. No runtime behavior changed. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-ppDpRk5X.js` is 1,049.19 kB after minification. |
| AFW-P2-T02 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/components/panels/ChatPanel.tsx`; `aieng-ui/frontend/src/components/agent/AgentPlanCard.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Extracted chat plan rendering into `AgentPlanCard`. Plan steps keep compact tool-name traceability and approval-required statuses are visually distinct. Existing `ChatHistoryItem.plan` data remains compatible. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-HKWFxYAc.js` is 1,049.64 kB after minification. |
| AFW-P2-T03 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/components/panels/ChatPanel.tsx`; `aieng-ui/frontend/src/components/agent/ApprovalCard.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Extracted runtime approval UI into `ApprovalCard`. The card shows run status, pending tool name, side-effect summary when available, and uses the existing approve/reject handlers unchanged. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-DxDy6KmJ.js` is 1,050.37 kB after minification. |
| AFW-P2-T04 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/components/panels/ChatPanel.tsx`; `aieng-ui/frontend/src/components/agent/AgentResultCard.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Extracted CAD and simulation result rendering into `AgentResultCard`. CAD face/feature/code details and simulation metrics, heatmap toggle, warnings, artifacts, and verdict display remain compatible with existing `ChatHistoryItem` fields. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-CeCeCAIs.js` is 1,050.00 kB after minification. |
| AFW-P3-T01 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added short-term selected-geometry prompt packaging. Picked faces are formatted under `Selected geometry:` with pointer, surface type, roles, and label, then sent to Agent/contextual chat/runtime paths while the visible chat history keeps the user's original message. Existing pointer autocomplete remains unchanged. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-CNkEf4iP.js` is 1,050.46 kB after minification. |
| AFW-P3-T02 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/api.ts`; `aieng-ui/frontend/src/App.tsx`; `aieng-ui/backend/app/app_factory.py`; `aieng-ui/backend/app/agent_engine.py`; `aieng-ui/backend/tests/test_api.py`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed; `python -m pytest tests/test_intent_planner.py tests/test_agent_context.py tests/test_api.py::test_agent_plan_accepts_selected_geometry_context` passed | Added optional `selected_geometry` to frontend Agent plan/run payloads and backend Agent plan handling. Backend sanitizes invalid selected geometry safely, returns accepted selected geometry in the Agent plan, and includes it in LLM planning prompt payloads. |
| AFW-P3-T03 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed; `python -m pytest tests/test_intent_planner.py tests/test_agent_context.py tests/test_api.py::test_agent_plan_accepts_selected_geometry_context` passed | General chat now routes through `/api/agent/runs` via `runAgentChat`. Clear side-effecting non-CAD requests such as preprocessing/material/mesh/target now create an Agent plan first. CAD generate/refine and simulation approval remain direct compatibility fallbacks. Manual browser scenarios were not run because no browser automation tool was available in this session. |
| AFW-P3-T04 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/frontend/src/components/panels/ChatPanel.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Direct CAD generation/refinement compatibility flows now present themselves as Agent actions: streaming progress says `Agent is generating CAD`, final messages say Agent generated/refined CAD, and final CAD details render through `AgentResultCard`. Viewer refresh behavior remains unchanged. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-Ci8CJ1g-.js` is 1,047.49 kB after minification. Manual CAD generation test was not run because no browser automation tool was available in this session. |
| AFW-P4-T01 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/frontend/src/components/agent/SelectionInspectorCard.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added a compact selected-geometry card above the Agent workbench chat. Picked faces render with clickable `PointerText`, surface type, roles, and Use in prompt / Clear actions wired to existing chat insertion and picked-face clearing. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-Dq51InH6.js` is 1,048.59 kB after minification. |
| AFW-P4-T02 | DONE | Codex / 2026-05-27 | `aieng-ui/frontend/src/App.tsx`; `aieng-ui/frontend/src/components/agent/SelectionInspectorCard.tsx`; `aieng-ui/frontend/src/style.css`; `aieng-ui/docs/agent-first-workbench-execution-plan.md` | `npm run build` passed | Added selected-face suggested actions for holes, offset, fillet, fixed support, and load. Buttons fill the chat input with natural-language prompts using the selected pointer and do not execute tools directly. Vite emitted the existing non-blocking chunk-size warning: `dist/assets/index-Cj1E0lbK.js` is 1,049.22 kB after minification. |
| AFW-P4-T03 | TODO | | | | |
| AFW-P5-T01 | TODO | | | | |
| AFW-P5-T02 | TODO | | | | |
| AFW-P5-T03 | TODO | | | | |
| AFW-P5-T04 | TODO | | | | |
| AFW-P6-T01 | TODO | | | | |
| AFW-P6-T02 | TODO | | | | |
| AFW-P7-T01 | TODO | | | | |
| AFW-P7-T02 | TODO | | | | |
| AFW-P7-T03 | TODO | | | | |
| AFW-P8-T01 | TODO | | | | |
| AFW-P8-T02 | TODO | | | | |
| AFW-P9-T01 | TODO | | | | |
| AFW-P9-T02 | TODO | | | | |

## Recommended First PR

The first PR should include only:

1. `AFW-P0-T01`
2. `AFW-P0-T02`
3. `AFW-P0-T03`
4. `AFW-P1-T01`

Reason:

- It lowers risk by extracting structure before changing behavior.
- It gives later LLMs a smaller, clearer surface to continue from.
- It keeps the current demo usable.

## Recommended Second PR

The second PR should include:

1. `AFW-P1-T02`
2. `AFW-P1-T03`
3. `AFW-P6-T01`

Reason:

- It delivers the visible simplification.
- It keeps all existing capabilities reachable under debug.
- It does not require backend changes.

## Recommended Third PR

The third PR should include:

1. `AFW-P2-T01`
2. `AFW-P2-T02`
3. `AFW-P2-T03`
4. `AFW-P2-T04`

Reason:

- It creates the reusable UI primitives needed for Agent-first execution.
- It reduces `ChatPanel` complexity before changing behavior.

## Recommended Fourth PR

The fourth PR should include:

1. `AFW-P3-T01`
2. `AFW-P3-T02`
3. `AFW-P7-T01`

Reason:

- It makes selected geometry part of Agent context.
- It avoids major execution routing changes until context is reliable.

## Recommended Fifth PR

The fifth PR should include:

1. `AFW-P3-T03`
2. `AFW-P3-T04`
3. `AFW-P5-T01`
4. `AFW-P5-T03`

Reason:

- It begins moving actual workflows into Agent-owned cards.
- It still keeps compatibility fallbacks.

## LLM Handoff Prompt Template

Use this prompt when handing a task to a new LLM:

```text
You are working in G:\Code\cad-cae-copilot.
Read AGENTS.md first. Do not inspect aieng/src for capability discovery.

Implement task <TASK_ID> from:
aieng-ui/docs/agent-first-workbench-execution-plan.md

Constraints:
- Keep changes scoped to the task.
- Preserve existing behavior unless the task explicitly changes it.
- Update the Task Ledger before finishing.
- Run the verification commands listed for the task.
- If a verification command cannot run, record why.

Return:
- Summary of changes.
- Files changed.
- Verification results.
- Remaining risks.
```

## Definition of Done for the Whole Plan

The simplification is complete when:

- The default UI is left model workspace + right Agent workbench.
- The right rail no longer exposes seven equal product modes.
- Internal tools are debug/developer-only.
- Selected geometry is visible to the user and passed to Agent planning.
- CAD, preprocessing, simulation, and postprocessing can be represented as Agent plan/result/approval cards.
- Approval-gated tools have clear human-in-the-loop cards.
- Existing direct CAD/CAE paths are either routed through Agent or retained only as compatibility fallback.
- Frontend build passes.
- Relevant backend agent/runtime tests pass.
