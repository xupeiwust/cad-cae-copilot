import type { HomeProject, HomeStateMessage } from "./protocol";

export type HomeHandoffModel = {
  backend: {
    label: string;
    detail: string;
    state: "checking" | "ready" | "blocked";
  };
  mcp: {
    label: string;
    detail: string;
    state: "checking" | "ready" | "blocked";
  };
  project: {
    label: string;
    detail: string;
    state: "checking" | "ready" | "missing" | "blocked";
    selected?: HomeProject;
  };
  nextAction: {
    label: string;
    detail: string;
    prompt: string | null;
  };
};

function latestProject(projects: HomeProject[]): HomeProject | undefined {
  return [...projects].sort((left, right) => {
    const leftTime = Date.parse(left.updatedAt ?? "");
    const rightTime = Date.parse(right.updatedAt ?? "");
    return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
  })[0];
}

function projectPrompt(project: HomeProject, backendUrl: string): string {
  return [
    `Use the aieng-workbench MCP tools for project ${project.name} (${project.id}).`,
    `Backend: ${backendUrl}.`,
    "Start by reading AIENG context and package evidence before proposing changes.",
    "Summarize the current .aieng evidence package: CAD evidence, CAE setup, design targets, result evidence, provenance, and claim boundary.",
    "Before any mesh or solver workflow, inspect structural adapter preflight/capability status for FreeCADCmd, Gmsh, and CalculiX availability.",
    "Recommend the next safe CAD/CAE step. Do not run solver tools, mutate CAD, mutate the package, or advance engineering claims unless the existing AIENG approval gates explicitly allow it.",
    "Report only evidence-backed facts and call out missing evidence.",
  ].join("\n");
}

function setupPrompt(backendUrl: string): string {
  return [
    "Set up an AIENG project using the aieng-workbench MCP tools.",
    `Backend: ${backendUrl}.`,
    "Start by checking AIENG readiness and listing existing projects.",
    "If no project is suitable, create or import a project from STEP or an existing .aieng package.",
    "After the package exists, inspect the .aieng evidence package and summarize CAD evidence, missing CAE setup, design targets, result evidence, provenance, and claim boundary.",
    "Before any mesh or solver workflow, inspect structural adapter preflight/capability status for FreeCADCmd, Gmsh, and CalculiX availability.",
    "Do not run solver tools, mutate CAD, mutate the package, or advance engineering claims unless the existing AIENG approval gates explicitly allow it.",
  ].join("\n");
}

export function buildHomeHandoff(state: HomeStateMessage | null): HomeHandoffModel {
  if (!state) {
    return {
      backend: {
        label: "Checking backend",
        detail: "AIENG Home is checking the configured backend.",
        state: "checking",
      },
      mcp: {
        label: "Checking MCP",
        detail: "Workspace MCP configuration has not been inspected yet.",
        state: "checking",
      },
      project: {
        label: "Waiting for project list",
        detail: "Projects appear after the backend responds.",
        state: "checking",
      },
      nextAction: {
        label: "Wait for readiness check",
        detail: "Backend and MCP status are still loading.",
        prompt: null,
      },
    };
  }

  const connected = state.status === "connected";
  const mcpReady = state.agentMcp.configured;
  const selected = latestProject(state.projects);
  const backendState = connected ? "ready" : "blocked";
  const mcpState = mcpReady ? "ready" : "blocked";
  const projectState = !connected ? "blocked" : selected ? "ready" : "missing";

  let nextAction: HomeHandoffModel["nextAction"];
  if (!connected) {
    nextAction = {
      label: "Start or reconnect backend",
      detail: "Project creation, package import, and the Web Workbench are blocked until the backend responds.",
      prompt: null,
    };
  } else if (!mcpReady) {
    nextAction = {
      label: "Configure agent MCP",
      detail: "Add the aieng-workbench MCP server through the existing .mcp.json setup, then reopen the agent.",
      prompt: [
        "Configure my AIENG MCP client before engineering work.",
        "Use the repository .mcp.json path for the aieng-workbench server.",
        "After MCP tools are available, list AIENG projects and inspect package evidence before proposing CAD/CAE actions.",
      ].join("\n"),
    };
  } else if (selected) {
    nextAction = {
      label: `Continue ${selected.name}`,
      detail: "Open the Web Workbench for the detailed evidence, approval, and 3D surfaces; paste the prompt into your MCP-capable agent.",
      prompt: projectPrompt(selected, state.backendUrl),
    };
  } else {
    nextAction = {
      label: "Create or import a project",
      detail: "Start with a blank project, STEP import, or existing .aieng package, then hand the evidence package to your agent.",
      prompt: setupPrompt(state.backendUrl),
    };
  }

  return {
    backend: {
      label: connected ? "Backend reachable" : "Backend not reachable",
      detail: connected
        ? `${state.detail || "Connected"} at ${state.backendUrl}`
        : `${state.detail || "Backend stopped"} at ${state.backendUrl}`,
      state: backendState,
    },
    mcp: {
      label: mcpReady ? "Agent MCP ready" : "Agent MCP missing",
      detail: mcpReady
        ? state.agentMcp.detail
        : "No aieng-workbench MCP server was detected. Use the existing .mcp.json setup path.",
      state: mcpState,
    },
    project: {
      label: selected ? `Current project: ${selected.name}` : connected ? "No project selected" : "Project list unavailable",
      detail: selected
        ? `${selected.id}${selected.status ? ` - ${selected.status}` : ""}`
        : connected
          ? "Create a project or open a STEP/.aieng package to begin."
          : "Project list is blocked by backend connectivity.",
      state: projectState,
      selected,
    },
    nextAction,
  };
}
