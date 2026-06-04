# MCP-First Constraint Migration Checklist

Status: completed audit for issue #20
Last updated: 2026-06-04

This checklist records what happened to the constraints that used to be spread
across AGENTS.md, the retired embedded-agent engine, runtime tool handlers, MCP
tool descriptions, and agent skills. It answers one question per rule: after the
MCP-first cutover, is the rule hard-enforced by the server, carried as portable
agent discipline, or explicitly agent-dependent?

## Classification

| Class | Meaning | Correct home |
|---|---|---|
| Hard | Must not be bypassable by a raw MCP client. | Runtime or MCP server rejection, validation, or fail-safe denial. |
| Soft | Correct operating discipline, but not safely enforceable for every agent. | MCP prompts/resources, tool descriptions, skills, rich tool returns. |
| Dropped | Retired embedded-agent behavior or agent-dependent judgment. | Document as not guaranteed; replace with evidence in tool returns where possible. |

## Hard Constraints

| Constraint | Current home | Survives raw MCP? | Evidence | Status / gap |
|---|---|---:|---|---|
| Approval-gated tools are identified from one registry field. | `runtime.register_tool(..., requires_approval=True)` plus tool schemas/descriptions. | Yes | `runtime.list_tools_for_mcp`; tests in `test_mcp_server.py` and `test_agentic_approval.py`. | Good. Keep the registry as the single source of truth. |
| Hard-block inspection mode refuses approval-gated tools before backend forwarding or in-process execution. | `mcp_server._mcp_hard_blocks_approval_tools`; env `AIENG_MCP_BLOCK_APPROVAL_TOOLS=1`. | Yes | `test_mcp_hard_block_refuses_gated_tool_before_dispatch`, `test_mcp_hard_block_refuses_solver_too`. | Good. This is the safest planning/inspection mode. |
| Workbench-managed approval mode routes gated MCP calls through the viewer approval broker. | `mcp_server._managed_approval_mode`; env `AIENG_MCP_MANAGED_APPROVAL=1`; repo `.mcp.json`. | Yes, when backend is reachable. Fail-safe deny when approval is unavailable. | `test_managed_approval_routes_gated_tool_through_broker`; approval broker endpoints in `app_factory.py`. | Good. This is the recommended local viewer mode. |
| Client-managed approval remains possible for clients that provide their own permission UX. | Unset both approval env flags. MCP descriptions include `[APPROVAL REQUIRED]`. | Partly. Depends on client. | `test_approval_gated_tools_advertise_in_description`. | Accepted as a compatibility mode, not the strongest safety posture. |
| CAD parameter edits are range-checked and preserve the old package if rebuild fails. | `cad.edit_parameter` implementation in `cad_generation.py`; feature graph parameter ranges. | Yes | `cad.edit_parameter` returns structured errors and `regression_diff`; related backend CAD tests. | Good. Keep ranges in feature graph and handler. |
| CAD edit collateral is surfaced rather than hidden. | `regression_diff` from `_diff_topology`. | Yes, as evidence in the tool return. | `cad.edit_parameter` and part edit responses. | Good. The server reports collateral; the human/agent decides next action. |
| Shape IR patches are atomic and validated. | `aieng.apply_shape_ir_patch` runtime path. | Yes | Tool is approval-gated and validates before overwrite. | Good. Keep dry-run available for inspection. |
| CAE setup patch writes only allowed setup paths. | `cae.apply_setup_patch` runtime handler. | Yes | Runtime validation rejects missing patches/path traversal/results paths. | Good. Schema is provider-compatible after the Codex/Kimi top-level union fix. |
| Solver execution is approval-gated and requires an existing prepared deck. | `cae.run_solver`; CalculiX run helper. | Yes for approval and deck presence. | `test_list_tools_for_mcp_marks_approval_tools`; `cae.prepare_solver_run` preflight. | Good. Sequence guidance remains soft, but missing deck prevents a real run. |
| Solver evidence is only produced by solver/postprocess tools, not by summaries. | `cae.run_solver`, `cae.extract_solver_results`, `postprocess.refresh_cae_summary`; package evidence artifacts. | Yes | `package_semantics.md`; result artifacts such as `result.frd`, `computed_metrics.json`, `evidence_index.json`. | Good. Claim advancement remains `none`. |
| MCP tool schemas are provider-compatible. | `runtime_tool_schemas.py`; `scripts/validate_mcp_schemas.py`. | Yes | `test_all_mcp_tool_schemas_are_provider_compatible`; schema validator script. | Good. This directly closes the Codex/Kimi schema compatibility gap found during dogfood. |

## Soft Constraints

| Constraint | Current home | Why soft | Current coverage | Follow-up |
|---|---|---|---|---|
| First calls: `aieng.agent_readme`, `aieng.list_projects`, `aieng.agent_context`. | AGENTS.md, MCP discipline resource, `aieng_mcp_first_onboarding` prompt, CAD skill. | Agents can ignore ordering. | Strong prompt/resource coverage. | Keep in every packaging tier in #22. |
| Use MCP tools, not legacy `aieng/src`, to understand live capability. | AGENTS.md and skills. | Reading source cannot be blocked. | Repeated in onboarding and skill text. | #15 should shorten and layer this rule. |
| Prefer `cad.get_source` before incremental edits. | MCP discipline resource and CAD skill. | Not every edit strictly needs it. | Strong guidance. | No code gap. |
| Label/color parts and declare editable constants. | AGENTS.md, CAD skill, tool descriptions. | The server cannot infer design intent for every unlabeled part. | Tool returns expose named parts and editable parameter index. | #21 should improve standard-part semantic tagging. |
| Inspect 4-view thumbnail and geometry_report; do fail-first review. | AGENTS.md, MCP resource, CAD skill. | Visual judgment is agent/human behavior. | Rich tool returns make it possible. | Cannot be hard-enforced. |
| Prefer bd_warehouse for fasteners, bearings, gears, threads, pipes, and flanges. | CAD skill and MCP resource. | Raw geometry can still be valid without bd_warehouse. | Pre-bound modules and examples. | #21 should tag bd_warehouse-derived parts in feature graph/BOM. |
| Run `cad.critique` after mechanical CAD generation. | AGENTS.md, MCP resource, CAD skill. | Some CAD is organic/product work or not engineering. | Tool exists and returns deterministic findings. | Optional future prompt can nudge harder for mechanical labels. |
| CAE workflow order: inspect setup, patch missing material/load/constraints, preflight, generate deck, run solver, extract results. | CAE skill and MCP prompt/resource. | Some steps are conditional; raw clients can call tools directly. | `cae.prepare_solver_run` returns missing items; `cae.run_solver` fails without deck. | #19 gap: preflight could return recommended next MCP calls. |
| Ask the user for missing required CAE inputs. | CAE skill and readiness reports. | Server cannot know user intent for missing physics. | `simulation_readiness.py` classifies inputs; setup patch can add explicit values. | No hard server gap. |
| Treat stale artifacts as historical until refreshed. | AGENTS.md, package semantics, agent context. | Reporting style is agent behavior. | Revalidation status and agent context warnings. | #19 gap: face references need stronger topology revision/hash validation. |
| Keep dev skills separate from modeling/CAE agent skills. | MCP skill prompt registration reads only `aieng-agent-skills/skills`. | Filesystem exposure depends on packaging. | `test_mcp_first_skills.py` asserts dev skills do not leak. | #22 packaging must preserve this split. |

## Dropped Or Agent-Dependent Rules

| Retired rule | Previous home | MCP-first decision | Replacement |
|---|---|---|---|
| `/build`, `/modify`, `/critique`, `/explain`, `/simulate` mutation/read-only/final-answer guards. | Embedded autopilot engine and composer intent routing. | Dropped from hard enforcement. External agents reason natively; raw MCP is tool-based, not chat-final based. | Tool-level approval, tool evidence, skills, and prompts. |
| Natural-language intent classification and low-confidence `ask_user` forcing. | Retired engine. | Dropped as a server constraint. | Agent skill discipline: clarify when target/action is ambiguous. |
| Parametric slot extraction automatically biasing `cad.edit_parameter`. | Retired engine context injection; surviving pure binder still supports panels/tools. | No longer a hard route. | `cad.list_editable_parameters`, feature graph parameters, CAD skill guidance. |
| Final-answer solver-result guard (`do not claim solver results unless solver_executed=true`). | Retired engine. | Cannot be enforced on arbitrary external-agent prose. | CAE skill hard rule plus tool evidence. Server still controls whether solver artifacts exist. |
| "Look at all four views." | AGENTS.md / skill. | Agent-dependent. | Return thumbnail and geometry_report; document the expectation. |
| Transcript terminal-state normalization for embedded chat UI. | Frontend chat transcript and retired autopilot run display. | Mostly compatibility/dead-code cleanup, not active product behavior. | Live activity stream and approval overlay should stay focused on active MCP events. |

## Gaps Found In This Audit

| Gap | Impact | Action |
|---|---|---|
| MCP setup/self-description mentioned hard-block mode but not viewer-managed approval mode. | A new maintainer or external agent could think approval depends only on the MCP client in normal local dogfood. | Fixed in this change by updating `MCP_SETUP.md` and MCP discipline text to document `AIENG_MCP_MANAGED_APPROVAL=1`. |
| CAE face references can become stale after topology-changing CAD edits. | A load/support may target a face ID that no longer means the same surface. | Track under #19 follow-up: validate CAE face references against current topology and store a topology revision/hash. |
| bd_warehouse standard parts still rely mostly on labels for downstream semantics. | Critique/CAE/BOM can miss fasteners/bearings/gears if labels are weak. | Track under #21. |
| AGENTS.md still contains detailed chat-era routing text. | External agents may over-read retired embedded-engine behavior as current MCP behavior. | Track under #15. Keep canonical docs layered and shorter. |
| Packaging must preserve the same hard/soft split. | Docker/uvx forms could accidentally omit managed approval, prompts, or skill separation. | Track under #22. Acceptance for #22 should include this checklist. |

## Current Recommendation

For local MCP-first dogfood and the future Docker viewer path, prefer:

1. `AIENG_MCP_MANAGED_APPROVAL=1`
2. `AIENG_BACKEND_URL=http://127.0.0.1:8000`
3. Viewer open on the target project

This makes the workbench UI the approval authority. For planning-only or
inspection-only deployments, set `AIENG_MCP_BLOCK_APPROVAL_TOOLS=1`; this takes
precedence and refuses gated tools. Reserve client-managed approval for clients
with a trustworthy permission UX or for headless compatibility modes.

## Verification Pointers

- `aieng-ui/backend/app/mcp_server.py`
- `aieng-ui/backend/tests/test_mcp_server.py`
- `aieng-ui/backend/tests/test_agentic_approval.py`
- `aieng-ui/backend/tests/test_mcp_first_skills.py`
- `aieng-ui/backend/scripts/validate_mcp_schemas.py`
- `aieng-agent-skills/skills/aieng-cad-authoring/SKILL.md`
- `aieng-agent-skills/skills/aieng-cad-cae-copilot/SKILL.md`
