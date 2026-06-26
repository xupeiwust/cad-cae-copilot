import type { PendingApproval } from "./pendingApprovals";
import type { ProjectTimeline } from "./projectTimeline";
import { readinessRows } from "./simulationReadiness";
import type {
  MeshConvergenceReport,
  MeshDiagnosticsResponse,
  ProjectRecord,
  ProjectSummary,
  SimulationReadinessResponse,
} from "../types";

export type MissionControlStatus = "ready" | "missing" | "blocked" | "unknown";

export type MissionControlCard = {
  key: string;
  label: string;
  status: MissionControlStatus;
  detail: string;
  meta?: string;
};

export type MissionControlNextAction = {
  label: string;
  detail: string;
  draft: string | null;
};

export type MissionControlWorkflowStep = {
  key: string;
  label: string;
  status: MissionControlStatus;
  detail: string;
  draft: string | null;
};

export type MissionControlModel = {
  projectName: string;
  packageName: string;
  packageStatus: MissionControlStatus;
  packageDetail: string;
  headline: string;
  cards: MissionControlCard[];
  workflowSteps: MissionControlWorkflowStep[];
  nextAction: MissionControlNextAction;
  evidenceNotes: string[];
};

export type MissionControlInput = {
  selectedProject: ProjectRecord | null;
  summary: ProjectSummary | null;
  pendingApprovals: PendingApproval[];
  projectTimeline: ProjectTimeline | null;
  simulationReadiness: SimulationReadinessResponse | null;
  meshDiagnostics: MeshDiagnosticsResponse | null;
  meshConvergenceReport: MeshConvergenceReport | null;
};

function memberSet(summary: ProjectSummary | null): Set<string> {
  return new Set((summary?.members ?? []).filter((item) => typeof item === "string" && item.length > 0));
}

function hasAnyMember(summary: ProjectSummary | null, members: string[]): boolean {
  const set = memberSet(summary);
  return members.some((member) => set.has(member));
}

function countPresent(summary: ProjectSummary | null, members: string[]): number {
  const set = memberSet(summary);
  return members.filter((member) => set.has(member)).length;
}

function packagePath(project: ProjectRecord | null, summary: ProjectSummary | null): string | null {
  const summaryPath = summary?.project?.aieng_file;
  return summaryPath || project?.aieng_file || null;
}

function basename(path: string | null): string {
  if (!path) return "No .aieng package";
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function hasCaeSetup(summary: ProjectSummary | null): boolean {
  const cae = summary?.cae;
  return Boolean(
    cae?.present ||
      cae?.artifact_detection?.has_cae_setup ||
      cae?.preprocessing_summary?.status.has_cae_setup ||
      cae?.result_summary?.status.has_cae_setup,
  );
}

function hasMeshEvidence(summary: ProjectSummary | null): boolean {
  const cae = summary?.cae;
  return Boolean(
    cae?.artifact_detection?.has_mesh ||
      cae?.result_summary?.status.has_mesh ||
      hasAnyMember(summary, ["simulation/mesh/mesh.inp", "simulation/mesh/mesh_metadata.json"]),
  );
}

function hasResultEvidence(summary: ProjectSummary | null): boolean {
  const cae = summary?.cae;
  return Boolean(
    cae?.results_available ||
      (cae?.result_evidence_count ?? 0) > 0 ||
      cae?.artifact_detection?.has_results ||
      cae?.artifact_detection?.has_fields ||
      cae?.result_summary?.status.has_results ||
      cae?.result_summary?.status.has_fields ||
      hasAnyMember(summary, ["results/evidence_index.json", "results/result_summary.json", "results/computed_metrics.json"]),
  );
}

function hasDesignTargets(summary: ProjectSummary | null): boolean {
  return hasAnyMember(summary, ["task/design_targets.yaml", "task/design_targets.yml"]);
}

function timelineApprovalCount(timeline: ProjectTimeline | null): number {
  return (timeline?.entries ?? []).filter((entry) => entry.actionableApproval).length;
}

function requiredMissing(readiness: SimulationReadinessResponse | null): string[] {
  if (readiness?.missing_required_inputs?.length) return readiness.missing_required_inputs;
  return readinessRows(readiness)
    .filter((row) => row.required && row.status === "missing")
    .map((row) => row.label);
}

function meshVerdict(diagnostics: MeshDiagnosticsResponse | null): string | null {
  if (!diagnostics?.available) return null;
  const verdict = diagnostics.overall_verdict || diagnostics.verdict || "unknown";
  return String(verdict);
}

function bestTimelineAction(timeline: ProjectTimeline | null): MissionControlNextAction | null {
  for (const entry of timeline?.entries ?? []) {
    const action = entry.nextActions.find((item) => item.availableNow || item.blockedReason);
    if (!action) continue;
    const status = action.availableNow ? "available" : "blocked";
    const reason = action.blockedReason ? ` ${action.blockedReason}` : "";
    const flags = action.safetyFlags.length ? ` Safety: ${action.safetyFlags.join(", ")}.` : "";
    return {
      label: action.availableNow ? action.label : `Resolve: ${action.label}`,
      detail: `${status}.${reason}${flags}`,
      draft: [
        `Next AIENG action: ${action.label}`,
        action.tool ? `Tool: ${action.tool}` : null,
        action.blockedReason ? `Blocked: ${action.blockedReason}` : null,
        action.blockedReasonCodes.length ? `Reason codes: ${action.blockedReasonCodes.join(", ")}` : null,
        "Use existing approval gates. Do not claim solver validation unless package evidence supports it.",
      ].filter(Boolean).join("\n"),
    };
  }
  return null;
}

function buildWorkflowSteps(args: {
  pkgPresent: boolean;
  cadEvidence: boolean;
  caeSetup: boolean;
  missingRequired: string[];
  meshEvidence: boolean;
  meshBlocked: boolean;
  meshVerdict: string | null;
  resultEvidence: boolean;
  designTargets: boolean;
  approvals: number;
}): MissionControlWorkflowStep[] {
  const {
    pkgPresent,
    cadEvidence,
    caeSetup,
    missingRequired,
    meshEvidence,
    meshBlocked,
    meshVerdict,
    resultEvidence,
    designTargets,
    approvals,
  } = args;

  return [
    {
      key: "package",
      label: "Create package",
      status: pkgPresent ? "ready" : "missing",
      detail: pkgPresent ? ".aieng package is available." : "Import STEP or open a .aieng package.",
      draft: pkgPresent ? null : "Create or open a .aieng package, then inspect package evidence. Do not run solver tools.",
    },
    {
      key: "geometry",
      label: "Check geometry",
      status: cadEvidence ? "ready" : pkgPresent ? "missing" : "unknown",
      detail: cadEvidence ? "Topology or feature evidence is present." : "Package-level CAD evidence is not visible yet.",
      draft: cadEvidence ? null : "Inspect the .aieng package and refresh CAD semantics/topology evidence. Do not mutate CAD geometry.",
    },
    {
      key: "cae_setup",
      label: "Bind CAE setup",
      status: caeSetup ? (missingRequired.length ? "blocked" : "ready") : "missing",
      detail: caeSetup
        ? missingRequired.length
          ? `Missing ${missingRequired.join(", ")}.`
          : "Required setup evidence is available."
        : "Materials, loads, constraints, or mapping evidence is missing.",
      draft: caeSetup && !missingRequired.length
        ? null
        : `Inspect package evidence and propose missing CAE setup${missingRequired.length ? ` for: ${missingRequired.join(", ")}` : ""}. Keep changes reviewable and approval-gated where required.`,
    },
    {
      key: "mesh",
      label: "Check mesh",
      status: meshEvidence ? (meshBlocked ? "blocked" : "ready") : caeSetup ? "missing" : "unknown",
      detail: meshEvidence
        ? meshVerdict
          ? `Diagnostics: ${meshVerdict}.`
          : "Mesh artifacts are present."
        : "Mesh evidence is not available.",
      draft: meshEvidence && !meshBlocked
        ? null
        : "Review mesh readiness for this .aieng package and propose mesh evidence or refinement. Do not claim solver results.",
    },
    {
      key: "solver",
      label: "Run solver",
      status: resultEvidence ? "ready" : approvals > 0 ? "blocked" : meshEvidence && !meshBlocked ? "blocked" : "missing",
      detail: resultEvidence
        ? "Solver/result evidence is present."
        : approvals > 0
          ? "A gated runtime action is waiting for review."
          : meshEvidence && !meshBlocked
            ? "Solver run must go through existing approval gates."
            : "Solver input/result evidence is not ready.",
      draft: resultEvidence
        ? null
        : "Prepare a solver run from existing .aieng evidence. Keep solver execution approval-gated and report only evidence-backed outputs.",
    },
    {
      key: "report",
      label: "Review report",
      status: resultEvidence ? "ready" : "missing",
      detail: resultEvidence
        ? designTargets
          ? "Compare design targets and summarize limitations."
          : "Result evidence exists; design targets are missing or not visible."
        : "No result evidence is available for review.",
      draft: resultEvidence
        ? "Review .aieng result evidence, compare design targets if present, list limitations, and prepare an engineering report. Do not advance claims automatically."
        : "Summarize current .aieng evidence gaps and recommended next actions. Do not invent solver values.",
    },
  ];
}

export function buildMissionControl(input: MissionControlInput): MissionControlModel {
  const {
    selectedProject,
    summary,
    pendingApprovals,
    projectTimeline,
    simulationReadiness,
    meshDiagnostics,
    meshConvergenceReport,
  } = input;

  const pkgPath = packagePath(selectedProject, summary);
  const pkgName = basename(pkgPath);
  const pkgPresent = Boolean(pkgPath || summary?.manifest || (summary?.members?.length ?? 0) > 0);
  const keyPackageMembers = countPresent(summary, [
    "manifest.json",
    "geometry/topology_map.json",
    "graph/feature_graph.json",
    "results/evidence_index.json",
    "provenance/tool_trace.json",
  ]);
  const caeSetup = hasCaeSetup(summary);
  const meshEvidence = hasMeshEvidence(summary);
  const resultEvidence = hasResultEvidence(summary);
  const designTargets = hasDesignTargets(summary);
  const approvals = pendingApprovals.length + timelineApprovalCount(projectTimeline);
  const missingRequired = requiredMissing(simulationReadiness);
  const verdict = meshVerdict(meshDiagnostics);
  const meshBlocked = verdict === "fail" || verdict === "warning";
  const meshConverged = meshConvergenceReport?.overall_verdict === "converged";
  const cadEvidence = Boolean(
    pkgPresent &&
      (summary?.feature_graph || summary?.topology || hasAnyMember(summary, ["graph/feature_graph.json", "geometry/topology_map.json"])),
  );

  const cards: MissionControlCard[] = [
    {
      key: "package",
      label: ".aieng package",
      status: pkgPresent ? "ready" : "missing",
      detail: pkgPresent ? pkgName : "Import STEP or open a .aieng package to create the evidence source.",
      meta: pkgPresent ? `${keyPackageMembers}/5 key evidence members` : undefined,
    },
    {
      key: "cad",
      label: "CAD evidence",
      status: cadEvidence ? "ready" : pkgPresent ? "unknown" : "missing",
      detail: pkgPresent
        ? "Topology or feature evidence is available for agent inspection."
        : "No package-level CAD evidence is loaded yet.",
      meta: selectedProject?.web_asset ? "preview asset available" : "preview state unknown",
    },
    {
      key: "cae",
      label: "CAE setup",
      status: caeSetup ? (missingRequired.length ? "blocked" : "ready") : "missing",
      detail: caeSetup
        ? missingRequired.length
          ? `Missing required inputs: ${missingRequired.join(", ")}.`
          : "Materials, loads, constraints, or mapping evidence is present."
        : "No CAE setup evidence yet.",
      meta: designTargets ? "design targets present" : "design targets missing",
    },
    {
      key: "mesh",
      label: "Mesh evidence",
      status: meshEvidence ? (meshBlocked ? "blocked" : "ready") : caeSetup ? "missing" : "unknown",
      detail: meshEvidence
        ? verdict
          ? `Mesh diagnostics: ${verdict}.`
          : "Mesh artifacts are present."
        : caeSetup
          ? "Generate or import mesh evidence before solver preparation."
          : "Configure CAE setup before mesh evidence matters.",
      meta: meshConverged ? "mesh convergence evidence present" : undefined,
    },
    {
      key: "results",
      label: "Result evidence",
      status: resultEvidence ? "ready" : meshEvidence ? "missing" : "unknown",
      detail: resultEvidence
        ? "Solver/result artifacts exist; review design targets before making claims."
        : "No solver/result evidence is available.",
      meta: "claims not auto-advanced",
    },
    {
      key: "approval",
      label: "Approval state",
      status: approvals > 0 ? "blocked" : "ready",
      detail: approvals > 0
        ? `${approvals} approval item${approvals === 1 ? "" : "s"} waiting for review.`
        : "No pending approval gate is visible.",
      meta: "mutations remain gated",
    },
  ];
  const workflowSteps = buildWorkflowSteps({
    pkgPresent,
    cadEvidence,
    caeSetup,
    missingRequired,
    meshEvidence,
    meshBlocked,
    meshVerdict: verdict,
    resultEvidence,
    designTargets,
    approvals,
  });

  const timelineAction = bestTimelineAction(projectTimeline);
  let nextAction: MissionControlNextAction = {
    label: "Inspect package evidence",
    detail: "Review the current package evidence before choosing a mutating workflow.",
    draft: "Inspect the current .aieng package evidence and summarize missing CAD/CAE evidence. Do not run mutating tools or advance claims.",
  };
  if (!selectedProject) {
    nextAction = {
      label: "Create or open a project",
      detail: "Start with a STEP file or an existing .aieng package.",
      draft: null,
    };
  } else if (!pkgPresent) {
    nextAction = {
      label: "Create package evidence",
      detail: "Import the model so AIENG can build the portable .aieng evidence package.",
      draft: "Import the selected CAD model into AIENG, generate the .aieng package, and inspect package evidence. Do not run solver tools.",
    };
  } else if (approvals > 0) {
    nextAction = {
      label: "Review pending approval",
      detail: "A gated tool is waiting. Review the existing approval UI before continuing.",
      draft: null,
    };
  } else if (timelineAction) {
    nextAction = timelineAction;
  } else if (resultEvidence) {
    nextAction = {
      label: "Review results and report",
      detail: "Result evidence exists. Compare design targets and generate a review report before making engineering claims.",
      draft: "Review .aieng result evidence, compare design targets, summarize limitations, and prepare an engineering report. Do not advance claims automatically.",
    };
  } else if (!caeSetup) {
    nextAction = {
      label: "Define CAE setup",
      detail: "Ask the agent to inspect package evidence and propose materials, loads, constraints, and design targets.",
      draft: "Inspect the current .aieng package evidence, then propose the missing CAE setup: material, loads, constraints, and design targets. Do not run the solver and do not advance claims.",
    };
  } else if (missingRequired.length) {
    nextAction = {
      label: "Fill required CAE inputs",
      detail: `Complete missing required inputs: ${missingRequired.join(", ")}.`,
      draft: `Update the CAE setup for the current .aieng package by filling these missing required inputs: ${missingRequired.join(", ")}. Keep changes reviewable and approval-gated where required.`,
    };
  } else if (!meshEvidence) {
    nextAction = {
      label: "Prepare mesh evidence",
      detail: "Generate or import mesh artifacts before preparing a solver run.",
      draft: "Inspect current CAE setup and prepare mesh evidence for this .aieng package. Do not claim solver results until a real solver run writes evidence.",
    };
  } else if (meshBlocked) {
    nextAction = {
      label: "Resolve mesh diagnostics",
      detail: `Mesh diagnostics are ${verdict}; review quality before solver execution.`,
      draft: "Review mesh diagnostics for the current .aieng package and propose a safer mesh refinement or setup correction. Do not run the solver until diagnostics are acceptable or explicitly approved.",
    };
  } else if (!resultEvidence) {
    nextAction = {
      label: "Prepare approval-gated solver run",
      detail: "Mesh evidence exists; solver execution must still go through existing approval gates.",
      draft: "Prepare the solver run from existing .aieng package evidence. Keep solver execution approval-gated and report only evidence-backed outputs.",
    };
  }

  const evidenceNotes = [
    pkgPresent ? ".aieng is the package evidence source of truth." : "No portable .aieng evidence package is loaded.",
    resultEvidence
      ? "Solver/result evidence is present, but engineering claims still require explicit review."
      : "No result evidence is present; solver values must not be claimed.",
    designTargets
      ? "Design targets can be compared against available evidence."
      : "Design targets are missing or not visible in the package.",
  ];

  return {
    projectName: selectedProject?.name ?? "No project selected",
    packageName: pkgName,
    packageStatus: pkgPresent ? "ready" : "missing",
    packageDetail: pkgPresent
      ? `${pkgName} preserves CAD, CAE, provenance, and review evidence.`
      : "Create or open a .aieng package to preserve evidence across tools and agents.",
    headline: resultEvidence
      ? "Result evidence available; review targets before claims"
      : caeSetup
        ? "CAE setup in progress; evidence gaps remain"
        : pkgPresent
          ? "CAD evidence loaded; CAE setup not complete"
          : "Start by creating a portable .aieng evidence package",
    cards,
    workflowSteps,
    nextAction,
    evidenceNotes,
  };
}
