# VS Code to Web Workbench Product Workflow Guard

Status: dogfood checklist for issue #425. This path verifies that AIENG feels
like a product-grade CAD/CAE handoff without asking the user to trust hidden
state or unapproved tool execution.

## Goal

Verify the intended entry path:

1. VS Code Home starts or reconnects the backend.
2. VS Code Home shows MCP readiness and points missing MCP setup to `.mcp.json`.
3. The user opens or creates a project.
4. The user copies a bounded agent prompt.
5. Web Workbench opens as the detailed 3D, evidence, approval, and workflow
   surface.
6. Mission Control explains the `.aieng` package state, evidence gaps, approval
   gates, and next safe action.

## Required Checks

- Backend stopped: Home must show start/retry and no executable agent prompt
  that assumes project access.
- MCP missing: Home must point to existing MCP setup and must not imply AIENG
  tools are already available.
- No project: Home may offer create/import and a setup prompt, but the prompt
  must ask the agent to inspect readiness before CAD/CAE action.
- Project present: Home may offer Open Workbench and Copy prompt.
- Copied prompts must mention `.aieng` evidence and approval gates.
- Copied prompts must not ask the agent to bypass approval, run a solver
  without approval, or advance claims automatically.
- Web Workbench Mission Control must separate package evidence, runtime state,
  approval state, result evidence, design targets, and claim boundary.
- Solver/result artifacts may be shown as evidence, but not as certification,
  production readiness, or automatic design validation.
- Stale/unknown evidence must appear as stale/unknown, not as pass/fail.

## Non-Goals

- Do not require FreeCAD, Gmsh, or CalculiX for this dogfood path.
- Do not run real solver actions.
- Do not compare screenshots pixel-by-pixel unless a stable visual harness is
  introduced later.
- Do not duplicate Web Workbench engineering panels in VS Code Home.

## Regression Commands

```bash
cd aieng-ui/frontend
conda run -n aieng311 npm test -- --run src/app/productWorkflowGuards.test.ts src/app/missionControl.test.ts src/components/MissionControlPanel.test.tsx src/app/mcpFirstLayout.test.tsx
conda run -n aieng311 npm run build

cd ../../aieng-vscode-extension
conda run -n aieng311 npm test
conda run -n aieng311 npm run check
conda run -n aieng311 npm run build
```
