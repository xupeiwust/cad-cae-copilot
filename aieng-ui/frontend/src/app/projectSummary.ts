import { projectViewerUrl } from "../appUtils";
import type { ProjectRecord, ProjectSummary, RuntimeConfigSnapshot } from "../types";

export function buildFallbackSummary(
  project: ProjectRecord,
  runtimeSnapshot: RuntimeConfigSnapshot | null,
): ProjectSummary {
  return {
    project,
    files: {},
    members: [],
    manifest: null,
    feature_graph: null,
    topology: null,
    validation: null,
    viewer: {
      asset_format: project.web_asset_format ?? null,
      asset_path: project.web_asset ?? null,
      asset_exists: Boolean(project.web_asset),
    },
    viewer_url: projectViewerUrl(project),
    ai_summary: null,
    derived: {},
    summary_error: "project summary unavailable; using project metadata fallback",
    summary_mode: "project_fallback",
    integration: runtimeSnapshot ?? undefined,
  };
}
