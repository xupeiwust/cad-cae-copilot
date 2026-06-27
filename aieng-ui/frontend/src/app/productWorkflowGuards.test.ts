import { describe, expect, it } from "vitest";

import { buildMissionControl } from "./missionControl";
import type { PendingApproval } from "./pendingApprovals";
import type { ProjectTimeline } from "./projectTimeline";
import type { ProjectRecord, ProjectSummary } from "../types";

const project: ProjectRecord = {
  id: "guard-project",
  name: "Guard bracket",
  status: "ready",
  created_at: "2026-06-27T00:00:00Z",
  updated_at: "2026-06-27T00:00:00Z",
  aieng_file: "/tmp/guard-bracket.aieng",
  web_asset: "/assets/guard.glb",
  web_asset_format: "glb",
};

function baseSummary(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    project,
    members: [
      "manifest.json",
      "geometry/topology_map.json",
      "graph/feature_graph.json",
      "provenance/tool_trace.json",
    ],
    manifest: { name: "Guard bracket" },
    feature_graph: { features: [] },
    topology: { faces: [] },
    validation: null,
    viewer: null,
    ai_summary: null,
    derived: {},
    ...overrides,
  };
}

function caeSummary(overrides: Partial<NonNullable<ProjectSummary["cae"]>> = {}): NonNullable<ProjectSummary["cae"]> {
  return {
    present: true,
    constraints_count: 1,
    constraint_types: {},
    materials_count: 1,
    boundary_conditions_count: 1,
    loads_count: 1,
    evidence_count: 1,
    result_evidence_count: 0,
    results_available: false,
    available_fields: [],
    simulation_targets: [],
    protected_regions: [],
    materials: [],
    boundary_conditions: [],
    loads: [],
    evidence: [],
    ...overrides,
  };
}

function emptyTimeline(overrides: Partial<ProjectTimeline> = {}): ProjectTimeline {
  return {
    entries: [],
    runCount: 0,
    activityCount: 0,
    warningCount: 0,
    diagnosticCount: 0,
    snapshotCount: 0,
    unstructuredFailureCount: 0,
    ...overrides,
  };
}

function build(overrides: Partial<Parameters<typeof buildMissionControl>[0]> = {}) {
  return buildMissionControl({
    selectedProject: project,
    summary: baseSummary(),
    pendingApprovals: [],
    projectTimeline: emptyTimeline(),
    simulationReadiness: null,
    meshDiagnostics: null,
    meshConvergenceReport: null,
    ...overrides,
  });
}

function missionText(model: ReturnType<typeof buildMissionControl>): string {
  return [
    model.packageDetail,
    model.headline,
    model.nextAction.label,
    model.nextAction.detail,
    model.nextAction.draft,
    ...model.cards.flatMap((card) => [card.label, card.status, card.detail, card.meta]),
    ...model.packageIdentity.flatMap((item) => [item.label, item.status, item.detail, ...item.members]),
    ...model.trustBadges.flatMap((badge) => [badge.label, badge.detail]),
    ...model.workflowSteps.flatMap((step) => [step.label, step.status, step.detail, step.draft]),
    ...model.evidenceNotes,
  ].filter((item): item is string => typeof item === "string").join("\n");
}

function expectNoOverclaim(text: string): void {
  expect(text).not.toMatch(/\b(is|as|equals|means)\s+(certified|certification)\b/i);
  expect(text).not.toMatch(/\b(validated for production|production-ready|safe for production)\b/i);
  expect(text).not.toMatch(/\bsolver (passed|validated|verified) the design\b/i);
  expect(text).not.toMatch(/\b(ignore|skip|bypass) approval/i);
}

describe("product workflow trust guards", () => {
  it("keeps empty and CAD-only states from implying solver evidence", () => {
    const empty = buildMissionControl({
      selectedProject: null,
      summary: null,
      pendingApprovals: [],
      projectTimeline: null,
      simulationReadiness: null,
      meshDiagnostics: null,
      meshConvergenceReport: null,
    });
    const cadOnly = build();

    for (const model of [empty, cadOnly]) {
      const text = missionText(model);
      expect(text).toMatch(/No result evidence|Results unknown/i);
      expect(text).toMatch(/must not be claimed|Do not run the solver|No solver\/result evidence/i);
      expectNoOverclaim(text);
    }
  });

  it("keeps missing CAE inputs and mesh failures blocked instead of solver-ready", () => {
    const missingInputs = build({
      summary: baseSummary({ members: ["manifest.json", "task/design_targets.yaml"], cae: caeSummary() }),
      simulationReadiness: {
        setup_source: "package",
        ready_for_solver: false,
        missing_required_inputs: ["material", "loads"],
      },
    });
    const meshFailure = build({
      summary: baseSummary({ members: ["manifest.json", "simulation/mesh/mesh.inp"], cae: caeSummary() }),
      meshDiagnostics: { available: true, overall_verdict: "fail" },
    });

    expect(missingInputs.workflowSteps.find((step) => step.key === "cae_setup")?.status).toBe("blocked");
    expect(meshFailure.workflowSteps.find((step) => step.key === "mesh")?.status).toBe("blocked");
    expect(meshFailure.nextAction.label).toBe("Resolve mesh diagnostics");
    expectNoOverclaim(missionText(missingInputs));
    expectNoOverclaim(missionText(meshFailure));
  });

  it("does not provide a copy prompt while a runtime approval is waiting", () => {
    const approval: PendingApproval = {
      permissionId: "perm-guard",
      toolName: "cae.run_solver",
      projectId: project.id,
      explanation: "Run solver",
      codePreview: null,
    };
    const model = build({ pendingApprovals: [approval] });

    expect(model.nextAction.label).toBe("Review pending approval");
    expect(model.nextAction.draft).toBeNull();
    expect(model.workflowSteps.find((step) => step.key === "solver")?.status).toBe("blocked");
    expect(missionText(model)).toMatch(/Approval blocked|waiting for review/i);
    expectNoOverclaim(missionText(model));
  });

  it("keeps solver results separate from design target satisfaction and claim advancement", () => {
    const model = build({
      summary: baseSummary({
        members: [
          "manifest.json",
          "results/evidence_index.json",
          "results/result_summary.json",
          "results/computed_metrics.json",
        ],
        cae: caeSummary({
          result_evidence_count: 1,
          results_available: true,
          available_fields: ["von_mises"],
          result_summary: {
            schema_version: "0.1",
            summary_type: "cae_result_summary",
            source: { package_path: "/tmp/guard-bracket.aieng", solver: "CalculiX", software: null, source_files: [] },
            status: {
              mode: "cae_result",
              has_cae_setup: true,
              has_mesh: true,
              has_results: true,
              has_fields: false,
              has_validation: false,
              warnings: [],
            },
            artifacts: {
              mesh_files: [],
              field_files: [],
              result_summary_files: ["results/result_summary.json"],
              evidence_files: ["results/evidence_index.json"],
              validation_files: [],
              setup_files: [],
            },
            solver_settings: null,
            load_cases: [],
            field_metadata: null,
            computed_values: {
              extrema_computed: true,
              max_displacement: null,
              max_von_mises_stress: null,
              minimum_safety_factor: null,
            },
            llm_summary: {
              one_line: "",
              key_findings: [],
              risks: [],
              recommended_next_actions: [],
              limitations: [],
            },
          },
        }),
      }),
    });

    const text = missionText(model);
    expect(model.cards.find((card) => card.key === "results")?.status).toBe("ready");
    expect(text).toMatch(/claims not auto-advanced|Do not advance claims automatically/i);
    expect(text).toMatch(/Design targets are missing|design targets are missing/i);
    expectNoOverclaim(text);
  });

  it("surfaces stale evidence as needing rerun without treating it as current", () => {
    const model = build({
      summary: baseSummary({
        derived: {
          revalidation_status: {
            requires_revalidation: true,
            reason: "geometry_changed",
          },
        },
      }),
    });
    const text = missionText(model);

    expect(model.trustBadges.find((badge) => badge.kind === "stale")?.label).toBe("Needs rerun");
    expect(text).toMatch(/requiring revalidation|Needs rerun/i);
    expectNoOverclaim(text);
  });
});
