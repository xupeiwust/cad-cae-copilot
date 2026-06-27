import { backendUrl } from "./livePreview";

type ProjectPromptInput = {
  projectId: string;
  projectName?: string;
};

type ModifyPromptInput = ProjectPromptInput & {
  /** Face pointers the user picked in the live preview, e.g. `@face:f_top_001`. */
  pointers?: string[];
};

function projectLabel({ projectId, projectName }: ProjectPromptInput): string {
  return projectName && projectName !== projectId ? `${projectName} (${projectId})` : projectId;
}

export function starterPrompt(input: ProjectPromptInput): string {
  return [
    `Use the aieng-workbench MCP tools to create the first CAD model for project ${input.projectId}.`,
    "Start by calling aieng.agent_readme, aieng.list_projects, and aieng.agent_context.",
    "Then propose the first mechanical part and generate it with the existing AIENG CAD tools only if the workflow allows it.",
    "Keep CAD/package mutations reviewable and use existing approval gates; do not run solver tools or advance engineering claims.",
    "After the model exists, summarize the .aieng evidence package: CAD evidence, missing CAE setup, design targets, result evidence, provenance, and claim boundary.",
    "I have AIENG CAD Preview open on this project, so it refreshes automatically when the model updates - no need to tell me to look at a file.",
  ].join(" ");
}

export function modifyPrompt(input: ModifyPromptInput): string {
  const pointers = (input.pointers ?? []).filter(Boolean);
  const lines = [
    `Use the aieng-workbench MCP tools to modify project ${input.projectId}.`,
    "Call aieng.agent_context first to inspect the current geometry, then propose and apply the next CAD change.",
  ];
  if (pointers.length) {
    lines.push(
      `I selected ${pointers.length === 1 ? "this face" : "these faces"} in the live preview - target the edit at ${pointers.join(" ")}.`,
    );
  }
  lines.push("Keep the geometry reproducible and reviewable; use existing approval gates for CAD/package mutations.");
  lines.push("Do not run solver tools or advance engineering claims unless AIENG evidence and approvals explicitly support it.");
  lines.push("AIENG CAD Preview will refresh automatically when the edit succeeds.");
  return lines.join(" ");
}

export function projectContextPrompt(input: ProjectPromptInput): string {
  return `Project ${projectLabel(input)}, backend ${backendUrl()}, open in AIENG CAD Preview.`;
}
