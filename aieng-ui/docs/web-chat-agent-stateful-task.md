# aieng-ui Web Chat Agent 优化任务文档

状态：`Canonical Stateful Roadmap`  
创建日期：2026-06-02  
维护对象：`aieng-ui` Web Chat / Agent Autopilot / 前后端会话与上下文能力  
相关既有文档：[`web-chat-codex-agent-roadmap.md`](web-chat-codex-agent-roadmap.md)、[`chat-agent-transcript-current-flow.md`](chat-agent-transcript-current-flow.md)

> 本文档是后续 aieng-ui Web Chat Agent 优化的权威任务跟踪文档。每次开发前必须先阅读并更新本文档；每完成一个任务、做出关键技术选择、发现新的风险或阻塞，都必须更新对应状态。本文件必须始终保持自洽：任何维护者只读本文档和当前代码库，就能接手下一步工作。

## 1. 项目背景

aieng-ui 是 AI 辅助 CAD / CAE 工程工作台的主要 Web 运行界面，前端使用 React，后端使用 FastAPI。项目面向 STEP / `.aieng` 包、build123d CAD 建模、CAE 预处理、CalculiX 求解、工程证据审查、运行时工具审批等场景。

当前项目已经不只是一个普通聊天框：代码中已有 Web Chat、Chat Session、消息持久化、Agent Autopilot、Plan 事件、审批门、运行时工具、SSE 活动流等基础设施。但从产品体验看，Web Chat 仍需要继续从“工程聊天入口”升级为更接近 VS Code GitHub Copilot / Codex 插件侧边栏风格的工程化 Agent：

- 能先理解目标并形成 Plan。
- 能展示步骤状态和当前执行位置。
- 能在缺少上下文、需要审批、存在多种路径时主动询问用户。
- 能压缩长对话上下文，避免长期任务丢失目标。
- 能持续挂载 CAD / CAE 文件、仿真、代码生成和工程任务执行能力。

本文档不是一次性起步计划，而是长期维护的执行路线图。它记录当前代码事实、目标架构、UI 产品方向、任务状态、验收标准和决策日志，后续开发不得脱离本文档长期推进。

## 2. 总体目标

长期目标是把 aieng-ui Web Chat 从普通对话面板升级为具备基础 Agent 能力的工程化助手。目标能力如下：

- Plan-first 的 Agent 工作流。
- 智能任务拆解与下一步动作判断。
- 步骤状态跟踪，包括等待审批、失败、阻塞、完成。
- 主动向用户提问，而不是在关键信息缺失时盲目执行。
- 上下文摘要与压缩，支持长任务恢复。
- 会话状态持久化或至少结构化保存。
- IDE 插件式深色 Chat UI，能紧凑展示消息、Plan、工具、审批、上下文摘要。
- 后续扩展 CAD / CAE 文件分析、仿真任务规划、代码生成、工程任务执行等能力。

### 2.1 Codex / Copilot 参考基线

本路线图采用 OpenAI Codex 与 VS Code GitHub Copilot Agent Mode 的设计原则作为参考，而不是复制某个 UI 截图。

参考来源：

- OpenAI Codex 开源仓库：`https://github.com/openai/codex`
- Codex app-server item 协议：`codex-rs/app-server/README.md`
- OpenAI Codex ExecPlans 文档：`https://developers.openai.com/cookbook/articles/codex_exec_plans`
- VS Code Copilot Chat / Agent 工具文档：`https://code.visualstudio.com/docs/copilot/agents/agent-tools`
- VS Code Copilot Chat 模式文档：`https://code.visualstudio.com/docs/copilot/copilot-edits`

可直接借鉴的原则：

- **Thread item 模型**：UI 不应把所有内容渲染成聊天气泡。应把用户消息、Agent 消息、Plan、Reasoning summary、Command/Tool execution、File change、MCP tool call、Context compaction、Approval request 都视为可独立更新的 transcript item。
- **生命周期事件**：每个 item 需要 `started / delta / completed / failed / declined` 等生命周期，最终完成事件是权威结果。aieng-ui 当前的 `agent_events` 已接近这个方向，应继续收敛为统一 item event 协议。
- **轻量可读状态**：长任务期间应显示“正在准备上下文 / 正在调用工具 / 等待审批 / 执行完成 / 失败原因”，但默认折叠细节，避免厚重卡片堆满侧栏。
- **Plan 是可执行对象**：Plan 不只是展示文案，而是可恢复、可更新、可审计的执行状态。
- **Context compaction 是显式事件**：上下文压缩不应隐藏在模型调用内部，UI 要能显示“已压缩上下文”，后端要能保存摘要。
- **工具审批可配置**：参考 Copilot/Codex 的工具审批体验，支持 turn/session/workspace 级别的审批意图，但 aieng-ui 必须保留 CAD/CAE mutation 和 solver 的强审批边界。
- **活文档纪律**：参考 Codex ExecPlans，路线图必须持续更新状态、决策、风险和下一步，不能只改代码不更新文档。

### 2.2 产品级非目标

为避免偏离方向，以下不是本轮路线图目标：

- 不做客服聊天窗口风格。
- 不做大卡片堆叠式时间线。
- 不把 Agent 推理逻辑写进 React UI。
- 不用前端状态替代后端 Agent 状态。
- 不把 CAD/CAE mutation、求解器运行、项目删除等高风险操作自动放行。
- 不照搬浅色 Copilot 截图；aieng-ui 保持深色工程工作台风格。

## 3. 当前状态分析

### 3.1 已阅读的关键路径

| 区域 | 文件 | 当前结论 |
|---|---|---|
| 前端入口与状态编排 | `aieng-ui/frontend/src/app/useWorkbenchApp.ts` | 仍是主要应用状态组合层，负责项目、会话、Agent run、viewer、设置、工程动作等 wiring，职责较重。 |
| Chat 面板 | `aieng-ui/frontend/src/components/panels/ChatPanel.tsx` | 负责 transcript 容器、当前活动行、审批 dock、quick actions、连接选择、多行输入框、@face 自动补全。 |
| Transcript 映射 | `aieng-ui/frontend/src/app/chatTranscript.ts` | 纯函数合并 chat messages、agent events、run snapshots，生成 message/tool/approval/artifact/status/plan 等 transcript item。 |
| Transcript 组件 | `aieng-ui/frontend/src/components/chat/ChatTranscript.tsx` | 根据 item kind 渲染消息、工具、审批、artifact、错误、状态和 AgentPlanCard。 |
| Plan 展示 | `aieng-ui/frontend/src/components/agent/AgentPlanCard.tsx` | 已支持 compact plan card，展示 step 状态、当前 step、tool/skill/summary。 |
| 会话 hook | `aieng-ui/frontend/src/app/useChatSessions.ts` | 已支持项目级 chat session 拉取、创建、删除、重命名、active_run_id 同步。 |
| 消息 hook | `aieng-ui/frontend/src/app/useChatTranscript.ts` | 已支持 chat messages 与 agent events 加载、持久化新消息、刷新活动 Autopilot run。 |
| Agent run hook | `aieng-ui/frontend/src/app/useAgentRuns.ts` | 封装传统 plan/run 和 Autopilot run、approve/reject/cancel/reply/follow-up。 |
| SSE 活动流 | `aieng-ui/frontend/src/app/useAgentActivityStream.ts` | 订阅 `/api/agent-activity/stream`，处理 chat_message、chat_session_changed、autopilot_update、agent event、viewer refresh。 |
| 前端 API 封装 | `aieng-ui/frontend/src/api.ts` | 集中封装 REST API，包括 chat sessions/messages、agent events、Autopilot、runtime、CAD/CAE。 |
| 后端 DB | `aieng-ui/backend/app/db.py` | SQLite 中已有 `chat_sessions`、`chat_messages`、`agent_events`、`user_settings`。 |
| 后端路由 | `aieng-ui/backend/app/app_factory.py` | FastAPI 路由集中定义，包含 chat、contextual-chat、Autopilot、SSE、session/message/event API。 |
| Autopilot Schema | `aieng-ui/backend/app/agent_autopilot/schema.py` | 已有 `AgentPlan`、`AgentPlanStep`、`AgentWorkingState`、`AutopilotRunState`、`AutopilotApproval` 等结构。 |
| Autopilot Engine | `aieng-ui/backend/app/agent_autopilot/engine.py` | 已有默认 plan、事件发射、工具执行、审批、ask_user/chat/pause/final、repair loop、working_state 更新。 |
| Autopilot Store | `aieng-ui/backend/app/agent_autopilot/store.py` | run state 以 JSON 文件持久化，独立于 SQLite chat tables。 |
| 上下文记忆 | `aieng-ui/backend/app/agent_autopilot/context_memory.py` | 已有 compact memory / resume prompt 相关能力，但还需要产品级 context summary API 和 UI。 |
| 当前流程说明 | `aieng-ui/docs/chat-agent-transcript-current-flow.md` | 已记录当前 transcript replay 来源和风险耦合点。 |
| 既有 roadmap | `aieng-ui/docs/web-chat-codex-agent-roadmap.md` | 英文 Codex-style roadmap，很多 M1-M6 任务已标 DONE，可作为历史 backlog 和实现证据。 |

### 3.2 当前前端 Chat 实现位置

- 主面板：`aieng-ui/frontend/src/components/panels/ChatPanel.tsx`
- Transcript 数据转换：`aieng-ui/frontend/src/app/chatTranscript.ts`
- Transcript 渲染：`aieng-ui/frontend/src/components/chat/ChatTranscript.tsx`
- Plan 卡片：`aieng-ui/frontend/src/components/agent/AgentPlanCard.tsx`
- 消息 / 会话状态：`useChatTranscript.ts`、`useChatSessions.ts`
- Agent run 状态：`useAgentRuns.ts`
- SSE 实时同步：`useAgentActivityStream.ts`
- API 调用：`api.ts`

### 3.3 当前后端 Chat / Agent 接口位置

- 传统 Chat：`POST /api/projects/{project_id}/chat`
- 上下文 Chat：`POST /api/projects/{project_id}/contextual-chat`
- Chat Session：
  - `GET /api/projects/{project_id}/chat-sessions`
  - `POST /api/projects/{project_id}/chat-sessions`
  - `PATCH /api/projects/{project_id}/chat-sessions/{session_id}`
  - `DELETE /api/projects/{project_id}/chat-sessions/{session_id}`
- Chat Messages：
  - `GET /api/projects/{project_id}/chat-messages`
  - `POST /api/projects/{project_id}/chat-messages`
  - `DELETE /api/projects/{project_id}/chat-messages`
- Agent Events：
  - `GET /api/projects/{project_id}/agent-events`
- Autopilot：
  - `POST /api/agent/autopilot/runs`
  - `GET /api/agent/autopilot/runs/{run_id}`
  - `POST /api/agent/autopilot/runs/{run_id}/continue`
  - `POST /api/agent/autopilot/runs/{run_id}/reply`
  - `POST /api/agent/autopilot/runs/{run_id}/follow-up`
  - `POST /api/agent/autopilot/runs/{run_id}/cancel`
- 实时事件流：`GET /api/agent-activity/stream`

### 3.4 当前消息流转方式

1. 用户在 `ChatPanel.tsx` 输入消息。
2. `useWorkbenchApp.ts` 的 `sendUnified()` 根据当前 connection、是否存在 active Autopilot run、工程 intent 等决定路径。
3. Local Agent / LLM API 路径调用 `useAgentRuns.ts` 中的 `runAutopilotAgent()` 或 `updateAutopilotRun()`。
4. 用户消息通过 `useChatTranscript.ts` 的 `setPersistentChatHistory()` 保存到 `chat_messages`。
5. 后端 Autopilot run 状态写入 `agent_autopilot/runs/{run_id}.json`。
6. 后端通过 `agent_events` 和 `/api/agent-activity/stream` 发布 plan、tool、approval、status 等事件。
7. 前端 `useAgentActivityStream.ts` 收到事件，更新 chatHistory、agentEvents、viewer 和项目状态。
8. `chatTranscript.ts` 将持久消息、事件、run snapshot 合并为可渲染 transcript items。

### 3.5 当前能力状态

| 能力 | 状态 | 说明 |
|---|---|---|
| 流式输出 | 部分支持 | 已有 SSE 活动流和 `StreamingState`，能展示 progress/content/tool_call；但真正 token-by-token assistant 内容流是否覆盖所有 adapter 路径需继续确认。 |
| 会话历史 | 已支持 | SQLite `chat_sessions` / `chat_messages`，按 project/session 读取与写入。 |
| Agent 事件持久化 | 已支持 | SQLite `agent_events`，用 event_id 去重，支持 transcript replay。 |
| Plan 概念 | 已支持 | 后端 `AgentPlan` / `AgentPlanStep`，前端 `AgentPlanCard`。 |
| Step 状态展示 | 已支持基础版 | 状态包含 pending/running/completed/blocked/failed/skipped，前端映射为 pending/running/done/waiting approval/failed/skipped。 |
| 主动询问用户 | 后端基础支持 | `AutopilotAskUser` 和 `ask_user` action 已存在；UI 对 blocked/chatting/reply 的体验还需强化。 |
| 上下文摘要 | 部分支持 | `AgentWorkingState` 和 `context_memory.py` 已有工作记忆与 resume prompt；缺少面向用户和长期会话的 context summary API / UI。 |
| 审批策略 | 已支持基础版 | `AutopilotApproval`、runtime approval、Autopilot continue approve/reject 已存在。 |
| Tool Call 概念 | 已支持 | runtime tools、Autopilot tool_call、policy、tool_executor 已存在。 |
| UI 风格 | 部分符合 | 已是深色工程工作台风格，但 ChatPanel 仍承担较多逻辑，输入区和 context/approval/mode 入口仍可继续产品化。 |

### 3.6 当前主要问题

前端主要问题：

- `useWorkbenchApp.ts` 仍集中组合太多业务状态，是后续维护风险最高的文件。
- `ChatPanel.tsx` 已拆出 transcript 和 `AgentInputBox`，但仍承担活动状态、审批 dock、quick actions 等多种职责。
- Context Summary 目前没有明确 UI 入口。
- Agent mode / approval mode / context source / attachment 等入口仍不够像 IDE 插件侧边栏。
- `agent_phase_changed` 事件在 `chatTranscript.ts` 中可映射，但 `useAgentActivityStream.ts` 的显式事件白名单目前未包含 `agent_phase_changed`，是否通过其他路径到达 UI 需要继续验证。

后端主要问题：

- `app_factory.py` 路由较集中，Agent session / plan / context summary API 后续应拆出更清晰的 router/service。
- Autopilot run state 存在 JSON store，chat/session/events 存在 SQLite，二者一致性和清理策略需要进一步产品化。
- 现有 `AgentPlan` 字段和本文档目标字段不完全一致，需要做兼容设计，不应直接破坏现有 API。
- 上下文压缩目前更偏内部 prompt memory，还不是独立可管理的会话摘要资源。
- 审批模式目前以工具 policy / approval 为主，缺少用户可见的 session-level `approval_mode`。

当前可复用代码：

- `AgentPlan`、`AgentPlanStep`、`AgentWorkingState`、`AutopilotRunState`
- `AutopilotEngine` 的 action loop、审批、repair、working state
- `chat_sessions` / `chat_messages` / `agent_events`
- `chatTranscript.ts` 的纯映射层
- `AgentPlanCard`、`ApprovalLine`、`ToolLine`、`StreamingMessage`
- `useChatSessions`、`useChatTranscript`、`useAgentRuns`、`useAgentActivityStream`

当前需要新增或强化的模块：

- 后端 `AgentContextSummary` 模型与 API。
- 后端 session-level `approval_mode` 或运行配置。
- 前端 `ContextSummaryPanel`。
- 前端 Agent mode / Approval mode selector。
- 更明确的 Agent Session API facade，避免前端直接拼装过多 run/session/message/event 细节。
- 面向 CAD / CAE 的 agent next-action policy 测试集。

## 4. Agent 能力设计

### 4.1 Agent Session

Agent Session 是用户在某个项目内的一条可恢复工程对话。当前已有 `chat_sessions`，后续直接扩展为 Agent Session，不另建完全平行的会话系统。

目标字段：

- `session_id`
- `project_id`
- `user_id`，当前为空，保留多用户扩展位
- `title`
- `created_at`
- `updated_at`
- `messages`
- `current_plan`
- `context_summary`
- `status`
- `approval_mode`
- `active_run_id`
- `metadata`

当前映射：

- `session_id/project_id/title/status/active_run_id/created_at/updated_at` 已在 `chat_sessions` 中存在。
- `messages` 已在 `chat_messages` 中存在。
- `current_plan` 当前在 Autopilot run JSON 中存在，尚未成为 session-level 字段。
- `context_summary` 当前缺少持久化 API。
- `approval_mode` 当前缺少 session-level 配置。

### 4.2 Agent Plan

当前后端已有 `AgentPlan`：

- `id`
- `objective`
- `status`
- `steps`
- `current_step_id`
- `created_at`
- `updated_at`

长期目标是保持兼容，同时在文档和 UI 中统一命名：

- `plan_id` 可映射为当前 `id`
- `goal` 可映射为当前 `objective`
- `title` 由 objective 派生，后续作为可编辑显示字段

目标状态：

- `pending`
- `running`
- `completed`
- `blocked`
- `failed`
- `cancelled`

### 4.3 Plan Step

当前后端已有 `AgentPlanStep`：

- `id`
- `title`
- `kind`
- `status`
- `tool_name`
- `skill_name`
- `summary`
- `evidence`

后续兼容扩展为：

- `step_id`
- `title`
- `description`
- `status`
- `type`
- `input`
- `output`
- `error`
- `depends_on`
- `created_at`
- `updated_at`

步骤状态至少包括：

- `pending`
- `in_progress`，可映射当前 `running`
- `completed`
- `failed`
- `skipped`
- `waiting_for_user`，可映射当前 `blocked` 且 kind 为 `approval` 或 ask_user

兼容原则：前端通过 mapper 层把后端现有 status 映射为 UI 展示状态，不一次性改破现有 Autopilot schema。

### 4.4 Agent Next Action

每轮 Agent 输出后，应结构化判断下一步动作。当前 `AutopilotAction` 已支持：

- `tool_call`
- `ask_user`
- `final`
- `pause`
- `chat`

产品层定义更高层的 `AgentNextAction`：

- `answer_user`
- `create_plan`
- `update_plan`
- `execute_step`
- `ask_user`
- `summarize_context`
- `wait_for_user`
- `finish_task`

映射规则：

| AgentNextAction | 当前可映射实现 |
|---|---|
| `answer_user` | `AutopilotFinal` 或 `AutopilotChat` |
| `create_plan` | `create_default_agent_plan()` 或后续 planner |
| `update_plan` | `AutopilotEngine._set_plan_step()` 和 plan events |
| `execute_step` | `AutopilotToolCall` |
| `ask_user` | `AutopilotAskUser` |
| `summarize_context` | `context_memory.py` / 新增 summary API |
| `wait_for_user` | `awaiting_approval` / `blocked` / `chatting` |
| `finish_task` | `final` + run status completed |

### 4.5 主动询问用户机制

Agent 应主动询问用户的场景：

- 用户目标不明确，例如“优化一下”但没有目标指标。
- 缺少关键文件、项目、几何或 CAE 上下文。
- 操作可能破坏现有工程数据、删除项目、覆盖几何、运行外部求解器。
- 需求存在多种实现路径且会影响架构，例如新增后端 API 还是复用现有 Autopilot API。
- 触发审批策略，例如严格审批、自动执行只读、手动执行。
- 工程任务存在物理假设，例如材料、载荷、边界条件、单位不明确。

UI 需要把 `ask_user` 明确渲染为等待用户输入的状态，而不是普通 assistant 文本。

### 4.6 Approval Mode 产品标准

审批模式采用会话级持久化，字段为 `approval_mode`。成熟产品默认值为 `balanced`。

| Mode | 行为 | 自动放行范围 | 强制审批范围 |
|---|---|---|---|
| `strict` | 每个工具调用前都请求确认 | 无 | 所有 tool call |
| `balanced` | 默认模式，读操作和纯摘要自动执行，高风险动作审批 | read-only inspection、context summary、plan update、safe transcript event | CAD/CAE mutation、solver run、项目删除、外部命令、文件覆盖、审批策略变更 |
| `manual` | Agent 只生成计划和建议，不自动执行工具 | 无 | 所有 tool call；用户手动触发执行 |

不可被任何模式自动放行的操作：

- `cad.execute_build123d`
- `cad.edit_parameter`
- `cad.replace_part`
- `cad.remove_part`
- `cad.set_reference_image`
- `cae.run_solver`
- project delete / archive destructive operation
- 任意外部进程执行
- 任意会覆盖工程 artifact 的操作

UI 表达：

- Composer 顶部或底部使用轻量 selector 显示当前模式。
- 默认 `balanced`。
- 模式说明用 tooltip，不在主界面放长说明。
- 当某个操作被强制审批时，approval row 写明原因，例如 `CAD mutation requires approval in every mode`。

## 5. 上下文管理与压缩设计

### 5.1 上下文组成

基础上下文应包括：

- 用户原始目标。
- 当前 Plan。
- 当前执行中的 Step。
- 已完成步骤及结果摘要。
- 失败步骤及错误摘要。
- 用户明确约束。
- 已接受的假设。
- 关键文件路径。
- 重要代码结论。
- 当前项目 ID、session ID、active run ID。
- CAD / CAE 相关证据路径。
- 未解决问题。
- 下一步动作。

当前可复用来源：

- `AutopilotRunState.message`
- `AutopilotRunState.plan`
- `AutopilotRunState.observations`
- `AutopilotRunState.working_state`
- SQLite `chat_messages`
- SQLite `agent_events`
- 项目级 `agent_context`

### 5.2 压缩触发条件

触发条件：

- 单 session 消息数超过阈值，例如 40 条。
- agent events 超过阈值，例如 200 条。
- 估算 token 数超过阈值。
- 用户切换任务目标。
- Plan 完成一个阶段。
- run 从 `chatting` 进入下一轮 follow-up 前。
- 执行 mutation / solver 前，需要整理关键假设和风险。

### 5.3 压缩摘要格式

摘要文本采用 Markdown front matter + 正文的格式，便于人读和机器解析：

```markdown
---
schema_version: 1
session_id: "..."
project_id: "..."
updated_at: "2026-06-02T00:00:00Z"
goal: "..."
next_action: "..."
---

## current_state
- ...

## important_decisions
- ...

## completed_steps
- ...

## pending_steps
- ...

## user_constraints
- ...

## relevant_files
- `aieng-ui/frontend/src/components/panels/ChatPanel.tsx`

## risks
- ...
```

后端保存为 JSON 时使用以下结构：

```json
{
  "schema_version": 1,
  "session_id": "string",
  "project_id": "string",
  "goal": "string",
  "current_state": "string",
  "important_decisions": ["string"],
  "completed_steps": ["string"],
  "pending_steps": ["string"],
  "user_constraints": ["string"],
  "relevant_files": ["string"],
  "risks": ["string"],
  "next_action": "string",
  "updated_at": "string"
}
```

### 5.4 前后端职责划分

后端负责：

- 生成、保存、更新 context summary。
- 维护 Agent 状态、Plan 状态、WorkingState。
- 根据消息、事件、run state 生成压缩上下文。
- 暴露 summary API。
- 确保 summary 不包含敏感 API key。

前端负责：

- 展示当前 Plan、步骤状态和摘要入口。
- 展示 context summary 的可读版本。
- 提供“压缩上下文 / 刷新摘要”按钮。
- 在发送消息时携带 session/run/project ID。

前端不应把 Agent 推理逻辑写死在 UI 组件中。

## 6. 前端 UI 改造设计

### 6.1 UI 风格

目标风格是 VS Code GitHub Copilot / Codex 侧边栏式工程 Agent，而不是网页客服聊天窗口。

硬性 UI 规则：

- 深色主题，延续当前 workbench，不引入浅色插件截图风格。
- 默认展示轻量 transcript row，不用厚重卡片承载每一条状态。
- 只有审批、上下文摘要、可展开错误详情允许使用轻量 panel；不使用大面积阴影卡片。
- Plan 展示应像“执行清单 / step ledger”，默认紧凑，当前步骤高亮，细节折叠。
- Tool / CAD / CAE / solver 状态应像 IDE 输出行：图标、名称、状态、耗时、简短摘要。
- 失败信息默认显示一行原因，详情按需展开。
- 审批项必须醒目但不臃肿：一条 pending approval row + compact actions + 可展开 payload。
- 输入区类似 IDE chat composer：多行输入、模式选择、工具/上下文入口、审批策略入口、发送/停止按钮。
- 文案使用工程状态词：`Planning`、`Reading context`、`Calling tool`、`Waiting for approval`、`Running solver`、`Compacted context`、`Done`、`Failed`。
- 禁止用“Agent 正在思考中”这类空泛状态长期占位；必须说明可验证阶段。

### 6.2 页面结构

Chat 侧边栏结构：

```text
Chat Side Pane
  Header Strip
    Mode: Ask / Plan / Agent / Edit-like CAD
    Connection: LLM API / Local Agent / Runtime
    Session title + current run state

  Transcript
    User message rows
    Agent message rows
    Plan ledger rows
    Tool execution rows
    Approval rows
    Artifact/result rows
    Context compaction rows

  Optional Drawer
    Context Summary
    Accepted assumptions
    Current blockers
    Relevant CAD/CAE artifacts

  Composer
    Multiline input
    Context attachment / selected geometry chips
    Mode selector
    Approval policy selector
    Send / Stop
```

布局原则：

- Header 只放状态和控制，不放解释性长文。
- Transcript 是主体验，所有状态从上到下自然流动。
- Context Summary 默认折叠，打开后作为侧栏内抽屉或 inline details，不占据主 transcript 大量高度。
- Composer 始终贴底，支持长输入但有最大高度。
- 新状态进入时不强制打断用户阅读旧消息；保留当前的 “New activity” 行为。

### 6.3 组件演进计划

结合当前结构，执行以下组件演进，不重复造组件：

| 目标组件 | 当前对应 | 处理方式 |
|---|---|---|
| `AgentChatPanel` | `ChatPanel.tsx` | 可后续重命名或保持现名，重点是继续减轻职责。 |
| `AgentMessageList` | `ChatTranscript.tsx` | 已存在，不重复创建。 |
| `AgentMessageItem` | `TranscriptMessage.tsx` | 已存在，不重复创建。 |
| `AgentPlanView` | `AgentPlanCard.tsx` | 已存在，后续增强交互与错误展示。 |
| `AgentPlanStepItem` | `AgentPlanStepRow` 内部函数 | 如增强复杂度再拆文件。 |
| `AgentInputBox` | `ChatPanel.tsx` 内 textarea | 抽出，承载附件、模式、审批入口。 |
| `AgentModeSelector` | `chat-connection-select` | 从连接选择中拆出更清晰的 Agent mode。 |
| `ApprovalModeSelector` | 暂无 | 新增，先做前端展示，后接后端 session config。 |
| `ContextSummaryPanel` | 暂无 | 新增，读取后端 context summary。 |
| `TranscriptStatusRow` | `ChatTranscript.tsx` inline status rendering | 新增或抽出，用统一 row 样式承载 phase/tool/context compaction。 |
| `ToolExecutionRow` | `ToolLine.tsx` | 保留轻量行，不升级成大卡片。 |
| `CompactApprovalRow` | `ApprovalLine.tsx` | 保留醒目状态和操作按钮，细节折叠。 |

### 6.4 Plan 展示能力

前端需要继续强化：

- 当前 Plan 标题。
- Plan 整体状态。
- 每个 Step 的状态。
- 当前正在执行的步骤。
- 失败步骤的错误信息。
- 等待用户确认的步骤。
- 已完成步骤的结果摘要。
- 当前 blockers 和 recommended next action。
- 长工具输入折叠显示。

### 6.5 Transcript Item 视觉规范

| Item | 默认展示 | 展开后展示 | 不允许 |
|---|---|---|---|
| User message | 左边细边框 + 文本 | 附件 / selected geometry | 大聊天气泡 |
| Agent message | 纯文本 + Markdown | 引用文件 / artifact chips | 头像大卡片 |
| Plan | 紧凑 step ledger | step 输入/输出/错误 | 每步一个重卡片 |
| Tool call | 一行工具名 + 状态 + 耗时 | 参数、输出摘要、artifact | 大面积代码块默认展开 |
| Approval | 一行风险 + approve/reject | code preview、side effects | 混在普通消息里 |
| Context compaction | 一行“Context compacted” | 摘要 diff / 新摘要 | 静默发生 |
| CAD/CAE artifact | 一行 artifact/result | 路径、named parts、预览链接 | 结果大卡片堆叠 |

### 6.6 状态文案规范

统一状态词：

- `Planning`
- `Reading project context`
- `Reading selected geometry`
- `Calling tool`
- `Waiting for approval`
- `Running CAD build`
- `Running solver`
- `Reviewing result`
- `Repairing failed input`
- `Compacting context`
- `Ready for follow-up`
- `Done`
- `Failed`

状态行必须满足：

- 一眼能看出当前阶段。
- 一眼能看出是否需要用户操作。
- 不显示模型内部冗长推理。
- 不重复刷屏，同类 progress row 要合并更新。

## 7. 后端 FastAPI 改造设计

### 7.1 会话相关

已有：

- `GET /api/projects/{project_id}/chat-sessions`
- `POST /api/projects/{project_id}/chat-sessions`
- `PATCH /api/projects/{project_id}/chat-sessions/{session_id}`
- `DELETE /api/projects/{project_id}/chat-sessions/{session_id}`

新增或扩展：

- 在 session 中记录 `approval_mode`。
- 在 session 中关联 latest context summary。
- 增加 archive 而非 hard delete 的能力，避免长期任务误删。

### 7.2 消息相关

已有：

- `GET /api/projects/{project_id}/chat-messages`
- `POST /api/projects/{project_id}/chat-messages`
- `DELETE /api/projects/{project_id}/chat-messages`
- `GET /api/projects/{project_id}/agent-events`
- `/api/agent-activity/stream`

增强：

- 明确区分 raw chat message、assistant final message、agent event。
- 为 streaming content 建立更稳定的 event type。
- 为用户 reply / follow-up 与 run_id 的关联建立后端统一入口。

### 7.3 Plan 相关

已有：

- Autopilot run 中包含 `plan`。
- 事件包括 `agent_plan_created` / `agent_plan_step_updated`。

新增：

- `GET /api/agent/sessions/{session_id}/plan`
- `PATCH /api/agent/runs/{run_id}/plan`
- `PATCH /api/agent/runs/{run_id}/plan/steps/{step_id}`
- 或先在现有 Autopilot run API 上提供只读 plan endpoint。

### 7.4 上下文相关

新增：

- `GET /api/projects/{project_id}/chat-sessions/{session_id}/context-summary`
- `POST /api/projects/{project_id}/chat-sessions/{session_id}/context-summary/refresh`
- `PATCH /api/projects/{project_id}/chat-sessions/{session_id}/context-summary`

### 7.5 审批相关

已有：

- Runtime run approve/reject。
- Autopilot continue approve/reject。

新增：

- `GET /api/projects/{project_id}/chat-sessions/{session_id}/approval-mode`
- `PATCH /api/projects/{project_id}/chat-sessions/{session_id}/approval-mode`
- 对某个 step 进行批准 / 拒绝的稳定 API alias。

## 8. 数据结构目标契约

本节定义前后端共同遵守的目标契约。当前代码已经有一部分同名或相近结构，落地时必须通过兼容 mapper 平滑迁移，禁止直接破坏现有 Autopilot API。

### 8.1 TypeScript 目标契约

```ts
export type ApprovalMode = "strict" | "balanced" | "manual";

export type AgentStepStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "skipped"
  | "waiting_for_user";

export type AgentNextActionType =
  | "answer_user"
  | "create_plan"
  | "update_plan"
  | "execute_step"
  | "ask_user"
  | "summarize_context"
  | "wait_for_user"
  | "finish_task";

export interface AgentMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  mode?: string | null;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface AgentPlanStep {
  step_id: string;
  title: string;
  description?: string;
  status: AgentStepStatus;
  type: "observe" | "skill" | "tool" | "approval" | "verify" | "repair" | "summarize";
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string | null;
  depends_on?: string[];
  created_at: string;
  updated_at: string;
}

export interface AgentPlan {
  plan_id: string;
  title: string;
  goal: string;
  status: "pending" | "running" | "completed" | "blocked" | "failed" | "cancelled";
  steps: AgentPlanStep[];
  current_step_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContextSummary {
  schema_version: number;
  session_id: string;
  project_id: string;
  goal: string;
  current_state: string;
  important_decisions: string[];
  completed_steps: string[];
  pending_steps: string[];
  user_constraints: string[];
  relevant_files: string[];
  risks: string[];
  next_action: string;
  updated_at: string;
}

export interface AgentNextAction {
  type: AgentNextActionType;
  reason: string;
  target_step_id?: string | null;
  payload?: Record<string, unknown>;
}

export interface AgentSession {
  session_id: string;
  project_id: string;
  user_id?: string | null;
  title: string;
  status: "idle" | "running" | "waiting_for_user" | "completed" | "failed" | "archived";
  approval_mode: ApprovalMode;
  active_run_id?: string | null;
  messages: AgentMessage[];
  current_plan?: AgentPlan | null;
  context_summary?: ContextSummary | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
```

### 8.2 Pydantic 目标契约

```python
from typing import Any, Literal
from pydantic import BaseModel, Field

ApprovalMode = Literal["strict", "balanced", "manual"]
AgentStepStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "failed",
    "skipped",
    "waiting_for_user",
]
AgentNextActionType = Literal[
    "answer_user",
    "create_plan",
    "update_plan",
    "execute_step",
    "ask_user",
    "summarize_context",
    "wait_for_user",
    "finish_task",
]

class AgentMessage(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    mode: str | None = None
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class AgentPlanStep(BaseModel):
    step_id: str
    title: str
    description: str = ""
    status: AgentStepStatus = "pending"
    type: Literal["observe", "skill", "tool", "approval", "verify", "repair", "summarize"]
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

class AgentPlan(BaseModel):
    plan_id: str
    title: str
    goal: str
    status: Literal["pending", "running", "completed", "blocked", "failed", "cancelled"] = "pending"
    steps: list[AgentPlanStep] = Field(default_factory=list)
    current_step_id: str | None = None
    created_at: str
    updated_at: str

class ContextSummary(BaseModel):
    schema_version: int = 1
    session_id: str
    project_id: str
    goal: str
    current_state: str
    important_decisions: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    user_constraints: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_action: str = ""
    updated_at: str

class AgentNextAction(BaseModel):
    type: AgentNextActionType
    reason: str
    target_step_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

class AgentSession(BaseModel):
    session_id: str
    project_id: str
    user_id: str | None = None
    title: str
    status: Literal["idle", "running", "waiting_for_user", "completed", "failed", "archived"] = "idle"
    approval_mode: ApprovalMode = "balanced"
    active_run_id: str | None = None
    messages: list[AgentMessage] = Field(default_factory=list)
    current_plan: AgentPlan | None = None
    context_summary: ContextSummary | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
```

落地原则：这些结构是产品层目标模型；实际实现时优先与 `agent_autopilot/schema.py` 的现有模型做兼容映射。

### 8.3 与当前模型的兼容映射

| 目标字段 | 当前字段 | 处理规则 |
|---|---|---|
| `AgentSession.session_id` | `chat_sessions.id` | 前端展示使用 `session_id`，后端存储可继续使用 `id`。 |
| `AgentSession.active_run_id` | `chat_sessions.active_run_id` | 继续复用。 |
| `AgentSession.current_plan` | `AutopilotRunState.plan` | 初期从 active run 读取；后续可缓存到 session summary。 |
| `AgentSession.context_summary` | 暂无 | 新增 session-level summary API。 |
| `AgentSession.approval_mode` | 暂无 | 新增 session-level 配置，不替代 runtime tool policy。 |
| `AgentPlan.plan_id` | `AgentPlan.id` | API adapter 层映射，内部可继续使用 `id`。 |
| `AgentPlan.goal` | `AgentPlan.objective` | UI 统一显示 goal/objective。 |
| `AgentPlanStep.step_id` | `AgentPlanStep.id` | API adapter 层映射。 |
| `AgentPlanStep.type` | `AgentPlanStep.kind` | UI 统一显示 type/kind。 |
| `AgentPlanStep.in_progress` | `running` | 前端 mapper 负责转换。 |
| `AgentPlanStep.waiting_for_user` | `blocked` + approval/ask_user | 前端和后端事件层明确区分 approval 与 ask_user。 |
| `ContextSummary` | `AgentWorkingState` + messages/events | 新增模型从 working state、chat messages、agent events 合成。 |

### 8.4 WCA-P1-001 兼容映射结论

当前代码证据：

- 后端 `backend/app/agent_autopilot/schema.py` 已有稳定的 `AgentPlan`、`AgentPlanStep`、`AgentWorkingState` 和 `AutopilotRunState.plan`。
- 前端 `frontend/src/types.ts` 中已有两个不同概念：旧 runtime `AgentPlan`（`AgentRunResponse.agent` 使用）和 Autopilot 的 `AutopilotAgentPlan` / `AutopilotAgentPlanStep`。后续不要把这两个名字强行合并。
- `frontend/src/app/chatTranscript.ts` 已把 `agent_plan_created` / `agent_plan_step_updated` 合成为 `TranscriptAgentPlanLine`，并使用 `AutopilotAgentPlan` 原始字段。
- `frontend/src/components/agent/AgentPlanCard.tsx` 当前直接展示 `id/objective/kind/running/blocked` 体系，并把 `approval + blocked` 文案化为 `waiting approval`。

产品目标与现有模型的逐项差异：

| 产品目标 | 当前后端 / 前端 | 本轮兼容决定 | 后续实现位置 |
|---|---|---|---|
| `plan_id` | `AgentPlan.id`, `AutopilotAgentPlan.id` | 不改后端字段；API/UI adapter 需要时输出别名。 | `api.ts` 或新 Agent Session facade |
| `goal` | `AgentPlan.objective`, `AutopilotAgentPlan.objective` | UI 文案可显示为 goal，但数据继续读写 `objective`。 | `chatTranscript.ts`, ContextSummary API |
| `title` | 暂无 plan title | 从 `objective` 派生，不要求后端立即持久化。 | `AgentPlanCard` 或 summary service |
| `step_id` | `AgentPlanStep.id` | 不改后端字段；adapter 输出别名。 | API adapter / summary generator |
| `type` | `AgentPlanStep.kind` | 不改后端字段；前端类型保留 `kind`，产品层可映射为 `type`。 | mapper 层 |
| `description` | 暂无；近似 `summary` | 第一阶段不新增；显示时优先 `summary`。 | WCA-P4-003 |
| `input` / `output` | `evidence`、tool event payload、observation data | 不塞进 `AgentPlanStep`；从事件和 observation 合成。 | transcript mapper / context summary |
| `error` | `errors[]`、tool_failed event、failed step summary | 不直接扩展 PlanStep；由 mapper 读取事件和 step summary。 | WCA-P4-003 |
| `depends_on` | 暂无 | 当前 coarse plan 为线性步骤，不新增依赖字段。 | 后续 planner 增强 |
| `in_progress` | `running` | 产品层显示为 in progress；后端保持 `running`。 | UI/status mapper |
| `waiting_for_user` | `blocked` + `kind=approval` 或 ask_user 事件 | approval 与 ask_user 必须在事件层区分，不能只靠 `blocked`。 | WCA-P2-002 |
| `created_at` / `updated_at` on step | step 暂无时间；plan 有时间 | 不强行给 step 加时间；使用对应事件 `created_at` 作为 replay 时间。 | event mapper |

演进原则：

- 本阶段不直接大改 `agent_autopilot/schema.py` 的 `AgentPlan` / `AgentPlanStep` 字段名，避免破坏 run JSON 兼容性和既有测试。
- 目标契约先作为产品层 / API facade / ContextSummary 的输出形状落地；后端 Autopilot 内部继续使用现有 schema。
- 前端新增类型时避免复用旧名 `AgentPlan`，优先使用 `AutopilotAgentPlan`、`AgentSessionPlanView` 或 `ContextSummaryPlan` 这类明确名称。
- `waiting_for_user` 必须由 `ask_user` 或 approval 事件语义确认，不能把所有 `blocked` 都展示成等待用户。
- 如果未来确实要扩展后端 `AgentPlanStep`，只追加可选字段，不重命名现有必填字段。

## 9. 分阶段任务拆解

### Phase 0：项目现状调查

目标：确认当前 Chat 前后端实现和可复用模块。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P0-001 | 阅读现有 Web Chat 前端结构 | DONE | P0 | `ChatPanel.tsx`, `chatTranscript.ts`, `useWorkbenchApp.ts`, `useChatSessions.ts`, `useChatTranscript.ts`, `useAgentRuns.ts`, `useAgentActivityStream.ts` | 已确认当前 Chat 组合、会话、消息、Agent run、SSE 同步路径。 | 文档第 3 节列出当前路径和问题。 | 2026-06-02 完成。 |
| WCA-P0-002 | 阅读现有后端 Chat / Agent 结构 | DONE | P0 | `app_factory.py`, `db.py`, `agent_autopilot/schema.py`, `engine.py`, `store.py`, `context_memory.py` | 已确认 SQLite、Autopilot JSON store、路由、schema、事件。 | 文档第 3 节列出当前后端状态。 | 2026-06-02 完成。 |
| WCA-P0-003 | 对齐既有 roadmap 与本文档 | DONE | P1 | `web-chat-codex-agent-roadmap.md`, `chat-agent-transcript-current-flow.md`, 本文档 | 既有英文 roadmap 作为历史执行记录，本文档作为当前中文权威状态面板。 | 英文文档只保留历史实现证据；新增活跃任务统一进入本文档。 | 2026-06-02 完成；英文 roadmap 已标为历史证据，current-flow 补充 plan/phase 事件事实和 WCA-P2-003 缺口；文档项无需运行代码测试。 |

### Phase 1：Agent 数据结构与状态模型

目标：定义 AgentSession、AgentPlan、AgentPlanStep、ContextSummary 等核心结构，并与现有 Autopilot schema 兼容。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P1-001 | 梳理现有 AgentPlan 与目标模型差异 | DONE | P0 | `backend/app/agent_autopilot/schema.py`, `frontend/src/types.ts`, 本文档第 8.4 节 | 当前已有 Plan 模型，但字段命名与本文档目标契约不完全一致。 | 产出兼容映射表，明确不破坏现有 API 的演进路径。 | 2026-06-02 完成；补充兼容映射结论和演进原则；文档项无需运行代码测试。 |
| WCA-P1-002 | 设计 AgentSession 扩展字段 | DONE | P0 | `backend/app/db.py`, `backend/app/app_factory.py`, `backend/tests/test_persistence.py`, `frontend/src/api.ts` | 扩展 `chat_sessions`，增加 `approval_mode`、`context_summary_json`、`context_summary_updated_at`。 | 新旧 session 兼容；默认 `approval_mode=balanced`; 前端可读取这些字段。 | 2026-06-02 完成；SQLite 兼容迁移、API 返回、PATCH 保存、前端类型已落地。Tests: `python -m pytest tests/test_persistence.py`; `npm run build`。 |
| WCA-P1-003 | 定义 ContextSummary 后端模型 | DONE | P0 | `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/__init__.py`, `backend/tests/test_agent_autopilot_schema.py` | 新增独立摘要模型，避免仅藏在 prompt memory。 | 有 Pydantic model 和测试。 | 2026-06-02 完成；新增严格 `ContextSummary` 模型、包导出和 round-trip/敏感额外字段拒绝测试。Tests: `python -m pytest tests/test_agent_autopilot_schema.py`。 |
| WCA-P1-004 | 定义 AgentNextAction 产品层枚举 | DONE | P1 | `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/__init__.py`, `backend/tests/test_agent_autopilot_schema.py`, `frontend/src/types.ts` | 和现有 `AutopilotAction` 做映射。 | 前后端类型一致，有 mapper 测试。 | 2026-06-02 完成；新增 `AgentNextAction` / `AgentNextActionType`、Autopilot action mapper、前端类型和 mapper 测试。Tests: `python -m pytest tests/test_agent_autopilot_schema.py`; `npm run build`。 |

### Phase 2：后端 Agent Workflow 基础实现

目标：实现基础 Plan 创建、状态更新、消息处理、下一步动作判断。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P2-001 | 补齐 Plan 只读 API | DONE | P1 | `backend/app/app_factory.py`, `backend/app/agent_autopilot/store.py`, `backend/tests/test_api.py`, `backend/tests/test_agent_autopilot_store.py`, `frontend/src/api.ts` | 当前只能通过 run 获取 plan；可新增轻量 endpoint。 | 前端可按 run_id 或 session_id 获取当前 plan。 | 2026-06-02 完成；新增 run-level 和 session-level 只读 plan endpoint、前端 API 封装和空 session 语义。Tests: `python -m pytest tests/test_api.py::test_autopilot_plan_read_api_by_run_and_session`; `python -m pytest tests/test_agent_autopilot_store.py`; `npm run build`。 |
| WCA-P2-002 | 明确 ask_user UI 事件语义 | DONE | P0 | `engine.py`, `schema.py`, `useAgentActivityStream.ts`, `chatTranscript.ts`, `AskUserLine.tsx`, `ChatTranscript.tsx`, `ChatPanel.tsx`, `style.css`, `test_agent_autopilot_engine.py`, `chat-agent-transcript-current-flow.md` | 当前后端有 `ask_user` action，但 UI 需要清晰等待用户输入。 | ask_user 渲染为 waiting_for_user 状态，并能 reply。 | 2026-06-02 完成；新增 `ask_user_requested` 事件、`ask_user` observation、实时白名单、独立 AskUserLine 回复 UI。Tests: `python -m pytest tests/test_agent_autopilot_engine.py::test_engine_emits_distinct_ask_user_event tests/test_agent_autopilot_schema.py`; `npm run build`。 |
| WCA-P2-003 | 检查 `agent_phase_changed` 事件前端接收链路 | DONE | P1 | `useAgentActivityStream.ts`, `chat-agent-transcript-current-flow.md` | mapper 已支持，但 SSE 显式白名单未看到该 event type。 | phase event 能从后端持久化和实时显示。 | 2026-06-02 完成；实时白名单加入 `agent_plan_created`、`agent_plan_step_updated`、`agent_phase_changed`，流程文档删除旧缺口。Tests: `npm run build`。 |
| WCA-P2-004 | session/run 一致性清理策略 | DONE | P2 | `backend/app/agent_autopilot/store.py`, `backend/app/app_factory.py`, `backend/tests/test_agent_autopilot_store.py`, `backend/tests/test_api.py` | project 删除已清理 DB，但 run JSON 与 session active_run_id 关系需明确。 | 删除/归档 session 时 active run 行为明确。 | 2026-06-02 完成；session 删除会取消该 session 的非终态 runs 并保留 cancelled run JSON，project 删除会清理该 project 的 run JSON/cancel markers。Tests: `python -m pytest tests/test_api.py::test_delete_project_removes_dir_and_chat tests/test_api.py::test_delete_project_removes_autopilot_runs tests/test_api.py::test_delete_chat_session_cancels_session_autopilot_runs tests/test_agent_autopilot_store.py`。 |

### Phase 3：上下文摘要与压缩

目标：实现基础上下文压缩机制。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P3-001 | 设计 context summary 存储位置 | DONE | P0 | `backend/app/db.py`, `backend/tests/test_persistence.py` | Context Summary 存储为 SQLite session 级 JSON 字段；run JSON 只保留运行时 working_state；`.aieng` artifact 只保存工程证据，不保存聊天摘要。 | DB migration 兼容旧库；summary 可按 session 获取和刷新。 | 2026-06-02 完成；`chat_sessions` 字段已落地，并新增 `update_chat_session_context_summary()` 写入/清空 helper。Tests: `python -m pytest tests/test_persistence.py`。 |
| WCA-P3-002 | 新增 context summary API | DONE | P0 | `backend/app/app_factory.py`, `backend/tests/test_api.py`, `frontend/src/api.ts` | 获取、刷新、更新摘要。 | 前端可读取并触发刷新。 | 2026-06-02 完成；新增 GET/PUT/refresh endpoints、前端 API 封装、规则刷新摘要和 API key/sk-token 脱敏测试。Tests: `python -m pytest tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh tests/test_persistence.py`; `npm run build`。 |
| WCA-P3-003 | 实现摘要生成器 | DONE | P1 | `backend/app/agent_autopilot/context_summary.py`, `backend/app/app_factory.py`, `backend/tests/test_context_summary.py`, `backend/tests/test_api.py` | 从 messages/events/run state 生成结构化摘要。 | 单元测试覆盖长消息、失败步骤、pending approval。 | 2026-06-02 完成；规则摘要生成器已抽成 service，覆盖长消息裁剪、API key/sk-token 脱敏、失败步骤和 pending approval。Tests: `python -m pytest tests/test_context_summary.py tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh`; `npm run build`。 |
| WCA-P3-004 | follow-up 前注入摘要 | DONE | P1 | `backend/app/app_factory.py`, `backend/app/agent_autopilot/context_memory.py`, `backend/tests/test_context_memory.py`, `backend/tests/test_api.py` | 长会话 follow-up 使用 summary 减少上下文漂移。 | prompt 中包含 goal/current_state/next_action。 | 2026-06-02 完成；start/continue/reply/follow-up engine 构造会把 session `context_summary` 注入 `agent_context.context_summary`，resume prompt 测试覆盖 goal/current_state/next_action。Tests: `python -m pytest tests/test_context_memory.py tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh tests/test_api.py::test_agent_autopilot_run_dry_run`; `npm run build`。 |

### Phase 4：前端 Agent Chat UI 改造

目标：实现类似 IDE 插件风格的 Chat 面板、Plan 展示、Step 状态展示。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P4-001 | 抽出 AgentInputBox | DONE | P1 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/components/chat/AgentInputBox.tsx` | 减轻 ChatPanel，承载 textarea、send/stop、@face 补全。 | ChatPanel JSX 更轻，行为不变，`npm run build` 通过。 | 2026-06-02 完成；输入 toolbar、textarea 自动高度、@face autocomplete、send/stop 按钮已迁入 AgentInputBox；`npm run build` 通过，仅保留既有 Vite chunk warning。 |
| WCA-P4-002 | 新增 ContextSummaryPanel | DONE | P0 | `frontend/src/components/agent/ContextSummaryPanel.tsx`, `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/app/AppChrome.tsx`, `frontend/src/style.css` | 展示 goal、current state、pending steps、risks。 | 有折叠入口，长文本不撑破布局。 | 2026-06-02 完成；panel 按 active project/session 拉取并刷新 P3 context summary，默认折叠，展开展示 state/pending/risks/decisions/files；`npm run build` 通过，浏览器验证 app shell/chat pane/input 挂载正常，未选项目时 panel 按设计隐藏。 |
| WCA-P4-003 | 增强 AgentPlanCard | DONE | P1 | `frontend/src/components/agent/AgentPlanCard.tsx`, `frontend/src/app/chatTranscript.ts`, `frontend/src/style.css` | 展示 error/output/blocked reason/current blockers。 | 失败和等待用户状态清晰。 | 2026-06-02 完成；run snapshot plan line 传递 errors/currentBlockers，PlanCard 从 run diagnostics、step status、step evidence/output 提取最多 4 条诊断摘要；`npm run build` 通过，浏览器刷新 app shell/chat pane/input 正常。 |
| WCA-P4-004 | Agent mode / approval mode 控件 | DONE | P1 | `frontend/src/components/chat/AgentInputBox.tsx`, `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/app/AppChrome.tsx`, `frontend/src/app/useWorkbenchApp.ts`, `frontend/src/app/useAgentRuns.ts`, `frontend/src/app/useChatSessions.ts`, `frontend/src/types.ts`, `frontend/src/appConstants.ts`, `frontend/src/style.css` | 当前有 connection select，但缺少产品级 Agent mode 与 approval mode 控件。 | 用户可见并可保存审批策略；默认 `balanced`；CAD/CAE mutation 与 solver 永远需要显式审批。 | 2026-06-02 完成；Agent mode 作为本地偏好保存并传入 Autopilot run request，approval mode 从 active session 读取并 PATCH 持久化；无 active session 时 approval select 禁用；policy 联动仍由 WCA-P5-003 验证；`npm run build` 通过，浏览器验证控件/默认值/input 正常。 |
| WCA-P4-005 | UI 视觉整理 | DONE | P2 | `frontend/src/style.css`, `frontend/src/components/chat/AgentInputBox.tsx`, `frontend/src/components/agent/ContextSummaryPanel.tsx`, `frontend/src/components/agent/AgentPlanCard.tsx` | 更接近 IDE 插件侧边栏，保持深色紧凑。 | 桌面和移动无重叠，按钮文本不溢出。 | 2026-06-02 完成；chat toolbar 支持紧凑换行，connection/mode/approval/settings 控件无重叠，context 和 plan diagnostics 长文本可换行；`npm run build` 通过，浏览器 598px 侧栏验证无横向溢出、无控件重叠、input 尺寸稳定。 |

### Phase 5：前后端联调

目标：完成 Agent 消息、Plan 状态、上下文摘要的联动。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P5-001 | Plan replay 联调测试 | DONE | P0 | `frontend/src/app/chatTranscript.ts`, `frontend/src/app/chatTranscriptReplay.test.ts`, `backend/tests/test_api.py` | 刷新页面后 Plan 事件和 run snapshot 应一致。 | refresh 后 plan/step 状态不丢失。 | 2026-06-02 完成；修复 `event-plan:*` 未参与 snapshot 去重导致 stale run plan 和 replay plan 双显的问题；新增前端 replay smoke test 和后端 session events/plan API 对齐回归。Tests: `rolldown src/app/chatTranscriptReplay.test.ts --platform node --format esm --file %TEMP%/chatTranscriptReplay.test.mjs && node %TEMP%/chatTranscriptReplay.test.mjs`; `npm run build`; `python -m pytest tests/test_api.py::test_autopilot_plan_replay_sources_match_after_refresh tests/test_api.py::test_autopilot_plan_read_api_by_run_and_session`。 |
| WCA-P5-002 | context summary UI/API 联调 | DONE | P0 | `frontend/src/components/agent/ContextSummaryPanel.tsx`, `frontend/src/app/useChatSessions.ts`, `frontend/src/app/chatSessionState.ts`, `frontend/src/app/contextSummarySessionState.test.ts`, `backend/tests/test_api.py`, `backend/tests/test_context_summary.py` | 摘要刷新后 UI 立即更新。 | 长会话能显示最新摘要。 | 2026-06-02 完成；ContextSummaryPanel GET/refresh 成功后同步本地 panel 和 active session summary state，后端 refresh 后 `/chat-sessions` 返回最新摘要；新增前端 session state smoke test。Tests: `rolldown src/app/contextSummarySessionState.test.ts --platform node --format esm --file %TEMP%/contextSummarySessionState.test.mjs && node %TEMP%/contextSummarySessionState.test.mjs`; `npm run build`; `python -m pytest tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh tests/test_context_summary.py`。 |
| WCA-P5-003 | approval mode 联调 | DONE | P1 | `backend/app/agent_autopilot/policy.py`, `backend/app/agent_autopilot/engine.py`, `backend/app/app_factory.py`, `backend/tests/test_agent_autopilot_policy.py`, `backend/tests/test_agent_autopilot_engine.py`, `backend/tests/test_api.py`, `frontend/src/components/chat/AgentInputBox.tsx`, `frontend/src/app/useChatSessions.ts` | 审批模式影响后端 policy 执行。 | `strict/balanced/manual` 三档可验证；高风险 CAD/CAE mutation 与 solver 不受自动放行影响。 | 2026-06-02 完成；`balanced` 保持当前自动读/预览/安全写，`strict` 对 safe-write 要审批，`manual` 对 allowlisted tool 要审批；CAD mutation 和 solver 始终 require approval；session approval_mode 注入 AutopilotEngine policy。Tests: `python -m pytest tests/test_agent_autopilot_policy.py tests/test_agent_autopilot_engine.py::test_engine_approval_mode_controls_low_risk_tool_execution tests/test_api.py::test_session_approval_mode_manual_requires_approval_for_autopilot_tool`; `npm run build`。 |
| WCA-P5-004 | SSE + polling fallback 回归 | DONE | P1 | `frontend/src/app/useAgentActivityStream.ts`, `frontend/src/app/agentActivityFallback.ts`, `frontend/src/app/agentActivityFallback.test.ts`, `frontend/src/app/useWorkbenchApp.ts`, `backend/tests/test_agent_activity.py` | live stream 断开时仍能恢复项目与 run 状态。 | 手测和测试覆盖 reconnect/polling。 | 2026-06-02 完成；SSE error 进入 reconnect/polling 状态，fallback interval 同时 refresh project 和 active Autopilot run，terminal run 会同步 chatHistory/session/busy/streaming state；新增前端 fallback smoke test，后端 activity stream route/broker 回归通过。Tests: `rolldown src/app/agentActivityFallback.test.ts --platform node --format esm --file %TEMP%/agentActivityFallback.test.mjs && node %TEMP%/agentActivityFallback.test.mjs`; `npm run build`; `python -m pytest tests/test_agent_activity.py::test_activity_stream_route_registered tests/test_agent_activity.py::test_broker_publish_reaches_subscriber tests/test_agent_activity.py::test_broker_fans_out_to_all_subscribers`。 |

### Phase 6：CAD / CAE 场景增强

目标：为后续 CAD 文件分析、CAE 仿真规划、工程任务执行预留扩展点。

| ID | 任务名称 | 当前状态 | 优先级 | 关联文件 | 说明 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|
| WCA-P6-001 | CAD/CAE context source 面板 | DONE | P2 | `frontend/src/app/useWorkbenchApp.ts`, `frontend/src/app/engineeringContextSource.ts`, `frontend/src/components/agent/ContextSummaryPanel.tsx`, `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/style.css` | 展示当前项目、选中面、关键 artifact、CAE readiness。 | Agent 可解释当前使用了哪些工程上下文。 | 2026-06-02 完成；ContextSummaryPanel 展开详情中显示 Project、Viewer asset、Shape IR 验证、CAE readiness/results、选中/高亮面和 CAE field 来源；新增纯 helper 和 smoke test 锁定来源文案。Tests: `rolldown src/app/engineeringContextSource.test.ts --platform node --format esm --file %TEMP%/engineeringContextSource.test.mjs && node %TEMP%/engineeringContextSource.test.mjs`; `npm run build`；浏览器空项目 shell 验证无布局溢出。 |
| WCA-P6-002 | 仿真任务 Plan 模板 | DONE | P2 | `backend/app/intent_planner.py`, `backend/app/agent_autopilot/prompts.py`, `backend/app/agent_autopilot/engine.py`, `backend/tests/test_agent_observation.py`, `backend/tests/test_agent_autopilot_engine.py`, `backend/tests/test_agent_autopilot_prompts.py` | 将 run simulation 拆解为检查、预处理、审批、执行、解析。 | Plan steps 与现有 CAE 工具匹配。 | 2026-06-02 完成；Autopilot 仿真目标使用 CAE 专用 plan 标题；intent planner 对 simulation request 输出 `aieng.agent_context` / inspect / `cae.prepare_solver_run` / `cae.generate_solver_input` / approval-gated `cae.run_solver` / extract results / extract regions / refresh summary 的 workflow；prompt 规则同步。Tests: `python -m pytest tests/test_agent_observation.py::test_simulation_intent_plan_expands_to_full_cae_workflow tests/test_agent_observation.py::test_observation_for_premature_solver_request_reports_readiness_gaps`; `python -m pytest tests/test_agent_autopilot_engine.py::test_simulation_objective_uses_cae_plan_template tests/test_agent_autopilot_engine.py::test_preprocessing_slice_runs_preflight_after_setup_patch tests/test_agent_autopilot_engine.py::test_solver_slice_runs_postprocess_followups_after_approval`; `python -m pytest tests/test_agent_autopilot_prompts.py::test_system_layer_documents_simulation_workflow_template tests/test_agent_autopilot_prompts.py::test_local_and_llm_paths_share_compact_tool_catalog`。 |
| WCA-P6-003 | CAD 修改任务恢复机制 | DONE | P2 | `backend/app/agent_autopilot/context_memory.py`, `backend/app/agent_autopilot/prompts.py`, `backend/tests/test_context_memory.py`, `backend/tests/test_agent_autopilot_engine.py`, `backend/tests/test_agent_autopilot_prompts.py` | 修改失败时能基于摘要和错误继续 repair。 | CAD build error 有可读修复路径。 | 2026-06-02 完成；ContextMemoryManager 对 CAD build error 生成显式 `cad_build_repair` directive，full/resume prompt 保留 traceback、source snippet、failing input 和“只修失败 build123d 源码并保留 project/mode/model_kind/labels/colors/user intent”的指令；prompt 规则补回 `CAD BRIEF GATE` / `CAD SKILL ROUTING` / `CAD BUILD REPAIR` 标记；既有 repair loop 保持不变。Tests: `python -m pytest tests/test_context_memory.py::test_compact_cad_build_error_keeps_repair_context tests/test_context_memory.py::test_resume_prompt_surfaces_latest_cad_repair_directive`; `python -m pytest tests/test_agent_autopilot_engine.py::test_engine_repairs_recoverable_tool_input_once tests/test_agent_autopilot_engine.py::test_engine_fails_after_repair_attempts_are_exceeded`; `python -m pytest tests/test_agent_autopilot_prompts.py`。 |

## 10. 状态跟踪表

| ID | Phase | Task | Status | Priority | Related Files | Acceptance Criteria | Notes |
| -- | ----- | ---- | ------ | -------- | ------------- | ------------------- | ----- |
| WCA-P0-001 | Phase 0 | 阅读现有 Web Chat 前端结构 | DONE | P0 | `ChatPanel.tsx`, `chatTranscript.ts`, `useWorkbenchApp.ts`, `useChatSessions.ts`, `useChatTranscript.ts`, `useAgentRuns.ts`, `useAgentActivityStream.ts` | 当前前端路径已写入第 3 节 | 2026-06-02 已完成调查 |
| WCA-P0-002 | Phase 0 | 阅读现有后端 Chat / Agent 结构 | DONE | P0 | `app_factory.py`, `db.py`, `agent_autopilot/schema.py`, `engine.py`, `store.py`, `context_memory.py` | 当前后端路径已写入第 3 节 | 2026-06-02 已完成调查 |
| WCA-P0-003 | Phase 0 | 对齐既有 roadmap 与本文档 | DONE | P1 | `aieng-ui/docs/web-chat-codex-agent-roadmap.md`, `aieng-ui/docs/chat-agent-transcript-current-flow.md`, 本文档 | 英文历史 backlog 作为实现证据，中文文档作为活跃任务入口 | 2026-06-02 完成；文档对齐，无代码测试 |
| WCA-P1-001 | Phase 1 | 梳理现有 AgentPlan 与目标模型差异 | DONE | P0 | `backend/app/agent_autopilot/schema.py`, `frontend/src/types.ts`, 本文档第 8.4 节 | 产出兼容映射表 | 2026-06-02 完成；不破坏现有 API |
| WCA-P1-002 | Phase 1 | 设计 AgentSession 扩展字段 | DONE | P0 | `backend/app/db.py`, `backend/app/app_factory.py`, `backend/tests/test_persistence.py`, `frontend/src/api.ts` | `chat_sessions` 扩展 `approval_mode` 和 `context_summary_json` | 2026-06-02 完成；Tests: `python -m pytest tests/test_persistence.py`; `npm run build` |
| WCA-P1-003 | Phase 1 | 定义 ContextSummary 后端模型 | DONE | P0 | `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/__init__.py`, `backend/tests/test_agent_autopilot_schema.py` | 有 Pydantic model 和测试 | 2026-06-02 完成；Tests: `python -m pytest tests/test_agent_autopilot_schema.py` |
| WCA-P1-004 | Phase 1 | 定义 AgentNextAction 产品层枚举 | DONE | P1 | `backend/app/agent_autopilot/schema.py`, `backend/app/agent_autopilot/__init__.py`, `backend/tests/test_agent_autopilot_schema.py`, `frontend/src/types.ts` | 前后端类型一致，有 mapper 测试 | 2026-06-02 完成；Tests: `python -m pytest tests/test_agent_autopilot_schema.py`; `npm run build` |
| WCA-P2-001 | Phase 2 | 补齐 Plan 只读 API | DONE | P1 | `app_factory.py`, `store.py`, `test_api.py`, `test_agent_autopilot_store.py`, `api.ts` | 按 run/session 读取 plan | 2026-06-02 完成；Tests: `python -m pytest tests/test_api.py::test_autopilot_plan_read_api_by_run_and_session`; `python -m pytest tests/test_agent_autopilot_store.py`; `npm run build` |
| WCA-P2-002 | Phase 2 | 明确 ask_user UI 事件语义 | DONE | P0 | `engine.py`, `schema.py`, `useAgentActivityStream.ts`, `chatTranscript.ts`, `AskUserLine.tsx`, `ChatTranscript.tsx`, `ChatPanel.tsx`, `style.css`, `test_agent_autopilot_engine.py` | ask_user 渲染为 waiting_for_user 并支持 reply | 2026-06-02 完成；Tests: `python -m pytest tests/test_agent_autopilot_engine.py::test_engine_emits_distinct_ask_user_event tests/test_agent_autopilot_schema.py`; `npm run build` |
| WCA-P2-003 | Phase 2 | 检查 `agent_phase_changed` 接收链路 | DONE | P1 | `useAgentActivityStream.ts`, `chat-agent-transcript-current-flow.md` | phase event 实时和 replay 都可显示 | 2026-06-02 完成；Tests: `npm run build` |
| WCA-P2-004 | Phase 2 | session/run 一致性清理策略 | DONE | P2 | `store.py`, `app_factory.py`, `test_agent_autopilot_store.py`, `test_api.py` | session 删除/归档时 run 行为明确 | 2026-06-02 完成；Tests: `python -m pytest tests/test_api.py::test_delete_project_removes_dir_and_chat tests/test_api.py::test_delete_project_removes_autopilot_runs tests/test_api.py::test_delete_chat_session_cancels_session_autopilot_runs tests/test_agent_autopilot_store.py` |
| WCA-P3-001 | Phase 3 | 设计 context summary 存储位置 | DONE | P0 | `db.py`, `test_persistence.py` | SQLite session 级摘要字段落地 | 2026-06-02 完成；Tests: `python -m pytest tests/test_persistence.py` |
| WCA-P3-002 | Phase 3 | 新增 context summary API | DONE | P0 | `app_factory.py`, `test_api.py`, `api.ts` | 前端获取、刷新、更新摘要 | 2026-06-02 完成；Tests: `python -m pytest tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh tests/test_persistence.py`; `npm run build` |
| WCA-P3-003 | Phase 3 | 实现摘要生成器 | DONE | P1 | `context_summary.py`, `app_factory.py`, `test_context_summary.py`, `test_api.py` | 覆盖长消息、失败步骤、审批等待 | 2026-06-02 完成；Tests: `python -m pytest tests/test_context_summary.py tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh`; `npm run build` |
| WCA-P3-004 | Phase 3 | follow-up 前注入摘要 | DONE | P1 | `app_factory.py`, `context_memory.py`, `test_context_memory.py`, `test_api.py` | prompt 包含结构化摘要 | 2026-06-02 完成；Tests: `python -m pytest tests/test_context_memory.py tests/test_api.py::test_chat_session_context_summary_api_get_update_refresh tests/test_api.py::test_agent_autopilot_run_dry_run`; `npm run build` |
| WCA-P4-001 | Phase 4 | 抽出 AgentInputBox | DONE | P1 | `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/components/chat/AgentInputBox.tsx` | 行为不变，构建通过 | 2026-06-02 完成；输入区职责已拆出，`npm run build` 通过 |
| WCA-P4-002 | Phase 4 | 新增 ContextSummaryPanel | DONE | P0 | `frontend/src/components/agent/ContextSummaryPanel.tsx`, `frontend/src/components/panels/ChatPanel.tsx`, `frontend/src/app/AppChrome.tsx`, `frontend/src/style.css` | UI 可读摘要、可刷新 | 2026-06-02 完成；构建和浏览器轻量验证通过 |
| WCA-P4-003 | Phase 4 | 增强 AgentPlanCard | DONE | P1 | `frontend/src/components/agent/AgentPlanCard.tsx`, `frontend/src/app/chatTranscript.ts`, `frontend/src/style.css` | 错误、等待用户、结果摘要清晰 | 2026-06-02 完成；构建和浏览器轻量验证通过 |
| WCA-P4-004 | Phase 4 | Agent mode / approval mode 控件 | DONE | P1 | `frontend/src/components/chat/AgentInputBox.tsx`, `frontend/src/app/useWorkbenchApp.ts`, `frontend/src/app/useAgentRuns.ts`, `frontend/src/app/useChatSessions.ts`, `frontend/src/types.ts`, `frontend/src/style.css` | 用户可见并可保存审批策略 | 2026-06-02 完成；默认 `balanced`，构建和浏览器轻量验证通过 |
| WCA-P4-005 | Phase 4 | UI 视觉整理 | DONE | P2 | `frontend/src/style.css`, chat components | 桌面/移动无重叠 | 2026-06-02 完成；构建和浏览器窄侧栏验证通过 |
| WCA-P5-001 | Phase 5 | Plan replay 联调测试 | DONE | P0 | `frontend/src/app/chatTranscript.ts`, `frontend/src/app/chatTranscriptReplay.test.ts`, `backend/tests/test_api.py` | 刷新后 Plan 状态不丢 | 2026-06-02 完成；event replay 覆盖 stale snapshot plan，前端 smoke 和后端 API 回归通过 |
| WCA-P5-002 | Phase 5 | context summary UI/API 联调 | DONE | P0 | `ContextSummaryPanel`, context summary API, `chatSessionState.ts` | 摘要刷新后 UI 更新 | 2026-06-02 完成；前端 smoke、构建、后端 API 回归通过 |
| WCA-P5-003 | Phase 5 | approval mode 联调 | DONE | P1 | `backend/app/agent_autopilot/policy.py`, `backend/app/agent_autopilot/engine.py`, `backend/app/app_factory.py`, `frontend/src/components/chat/AgentInputBox.tsx` | 审批策略影响后端执行 | 2026-06-02 完成；三档策略联调和高风险审批边界测试通过 |
| WCA-P5-004 | Phase 5 | SSE + polling fallback 回归 | DONE | P1 | `frontend/src/app/useAgentActivityStream.ts`, `frontend/src/app/agentActivityFallback.ts`, `backend/tests/test_agent_activity.py` | 断流后可恢复状态 | 2026-06-02 完成；fallback 同时恢复 project 与 active run state |
| WCA-P6-001 | Phase 6 | CAD/CAE context source 面板 | DONE | P2 | `useWorkbenchApp.ts`, `engineeringContextSource.ts`, `ContextSummaryPanel` | 显示 Agent 使用的工程上下文 | 2026-06-02 完成；上下文详情可解释 project/viewer/Shape IR/CAE/face sources，前端 smoke 和 build 通过 |
| WCA-P6-002 | Phase 6 | 仿真任务 Plan 模板 | DONE | P2 | `intent_planner.py`, `prompts.py`, `engine.py` | CAE plan 与工具链匹配 | 2026-06-02 完成；simulation plan 明确 check/preprocess/approval_execute/parse phase，`cae.run_solver` 仍强审批 |
| WCA-P6-003 | Phase 6 | CAD 修改任务恢复机制 | DONE | P2 | `context_memory.py`, `engine.py` | CAD build error 可修复继续 | 2026-06-02 完成；resume/full prompt 显式携带 CAD repair directive |

## 11. 决策记录

| Date | Decision | Reason | Impact | Status |
| ---- | -------- | ------ | ------ | ------ |
| 2026-06-02 | 采用 Plan-first 工作流作为长期方向 | 当前代码已具备 `AgentPlan`、Plan event、Plan UI，继续强化成本最低 | 前后端新增能力围绕 Plan/Step 状态展开 | Accepted |
| 2026-06-02 | Agent 状态优先由后端管理 | 后端已有 Autopilot run JSON、SQLite messages/events，前端负责展示而不是推理 | 新增 context summary / approval_mode 优先后端落地 | Accepted |
| 2026-06-02 | UI 采用 IDE 插件式深色侧边栏风格 | aieng-ui 是工程工作台，不适合客服聊天式 UI | Chat 组件更紧凑、更状态化，去除厚重卡片堆叠 | Accepted |
| 2026-06-02 | 引入结构化上下文压缩机制 | 长任务会丢失目标，现有 working_state 还不等于用户可见摘要 | 新增 ContextSummary 模型、API 和 UI | Accepted |
| 2026-06-02 | 新建中文状态文档而不覆盖英文 roadmap | 既有英文 `web-chat-codex-agent-roadmap.md` 已有历史 DONE 任务 | 本文档作为中文长期跟踪入口，英文文档作为历史实现证据 | Accepted |
| 2026-06-02 | 会话级扩展字段先落 SQLite 和 API，不改变 runtime tool policy | `approval_mode` 是产品配置状态，不能绕过 CAD/CAE mutation 和 solver 的工具级审批边界 | `chat_sessions` 新增 `approval_mode`、`context_summary_json`、`context_summary_updated_at`；API 返回解析后的 `context_summary` 和原始 JSON 字段 | Accepted |
| 2026-06-02 | `ask_user` 使用独立 transcript item，不复用 approval UI | ask_user 是信息补全，不是工具执行授权；混用会让用户误以为正在批准 side effect | 新增 `ask_user_requested` 事件和 `AskUserLine`，approval row 继续只表达工具审批 | Accepted |
| 2026-06-02 | session 删除取消 runs，project 删除清理 runs | session 删除是会话级操作，需要保留 cancelled run 作为审计痕迹；project 删除是工程级永久删除，需要避免 orphan run JSON | `AutopilotStore` 支持按 project/session 枚举和删除；REST/tool 项目删除共用清理 helper | Accepted |
| 2026-06-02 | Context Summary refresh 必须做基础密钥脱敏 | 摘要是长期会话状态，不应持久化 API key 或 `sk-...` token 片段 | 规则刷新摘要对 secret-like 文本做 redaction；测试覆盖 `api_key=` 和 `sk-` token | Accepted |
| 2026-06-02 | Context Summary 生成器独立于 FastAPI/SQLite | 生成规则需要可单测、可复用，避免路由函数承载业务摘要逻辑 | 新增 `agent_autopilot/context_summary.py`，API 路由只收集数据并调用 service | Accepted |
| 2026-06-02 | follow-up/resume prompt 通过 `agent_context.context_summary` 注入会话摘要 | Prompt builder 已有 `agent_context` 层，复用该层可避免新增并行 prompt 字段 | start/continue/reply/follow-up engine 构造统一挂载 session summary | Accepted |

## 12. 风险与默认产品决策

### 12.1 当前风险

- 现有 Chat 架构已经有较多能力，但状态来源分散在 `chat_messages`、`agent_events`、Autopilot run JSON、前端 local state，长期一致性需要治理。
- `useWorkbenchApp.ts` 职责仍重，后续增加 Context Summary / Approval Mode 时容易继续膨胀。
- `app_factory.py` 路由集中，继续增加 Agent API 可能降低后端可维护性。
- 上下文压缩策略需要模型支持或清晰规则，否则可能丢失关键工程约束。
- 流式输出、步骤状态更新、事件持久化三者需要统一语义，避免刷新前后显示不一致。
- UI 改造可能影响现有项目面板、viewer、审批 dock 布局。
- 当前 `AgentPlanStep.status` 与本文档目标状态 `in_progress/waiting_for_user` 不完全一致，需要兼容映射。
- `approval_mode` 必须与现有 runtime policy 做“更严格者生效”的合并，不能绕过工具级审批边界。

### 12.2 已采纳默认产品决策

| Topic | Default Decision | Rationale | Implementation Target |
|---|---|---|---|
| Agent Session 持久化 | 扩展 `chat_sessions`，不另建平行 session 系统 | 当前 DB 和前端 hooks 已围绕 project/session 工作 | `approval_mode`, `context_summary_json`, `context_summary_updated_at` |
| Approval Mode | 默认 `balanced`，支持 `strict/balanced/manual` | 成熟产品需要效率与安全边界并存 | 高风险 CAD/CAE mutation 与 solver 永远审批 |
| Context Summary 存储 | SQLite session 级 JSON | 摘要属于会话状态，不属于工程证据 artifact | 后端 summary API + 前端 ContextSummaryPanel |
| 多会话 | 保留并强化现有多 session | 当前 UI 和 DB 已支持 | 新增 archive，删除保留为显式危险动作 |
| 工具调用路径 | 新能力优先走 Autopilot；保留 direct CAD/CAE 作为兼容路径 | 避免大爆炸迁移，同时让 Agent 成为长期主路径 | 新 UI 默认 Agent，旧路径逐步降级为 fallback |
| 附件与 CAD/CAE 文件 | Composer 支持附件入口，但文件导入仍走现有 project upload / import pipeline | 避免把工程文件处理塞进聊天组件 | Chat 只创建 attachment/context reference |
| 团队协作 | 数据结构保留 `user_id`，当前单用户本地优先 | 不阻塞本地产品体验 | `user_id` nullable，不做权限系统 |
| Context Summary UI | 默认折叠，显示一行摘要入口 | 保持 VS Code 插件式轻量体验 | 侧栏内 collapsible panel |
| 英文 roadmap | 作为历史实现记录；活跃任务进入本文档 | 避免双 backlog 分裂 | 新任务只维护本文档状态表 |

## 13. 后续使用方式

- 本文档是后续 aieng-ui Web Chat Agent 优化的长期任务跟踪文档。
- 每次开发前，应先阅读本文档、`web-chat-codex-agent-roadmap.md`、`chat-agent-transcript-current-flow.md`。
- 开始开发前，把对应任务状态改为 `IN_PROGRESS`，并写明 owner / 日期。
- 完成任务后，把状态改为 `DONE`，补充修改文件、测试命令和残留限制。
- 只有遇到外部依赖、缺失运行环境或无法由产品默认策略覆盖的问题，才把状态改为 `BLOCKED`，并说明具体 blocker。
- 每做出关键技术选择，需要更新第 11 节 Decision Log。
- 每发现新的架构风险或 UI 风险，需要更新第 12 节。
- 不允许长期只改代码不更新文档状态。
