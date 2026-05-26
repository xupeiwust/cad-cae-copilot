/**
 * Placeholder for the legacy FreeCAD inspection card.
 *
 * The CAD-provider abstraction replaced the direct FreeCAD bridge on the
 * backend; the proper geometry-inspection panel rewrite is still pending in
 * the frontend cleanup todo. This stub keeps types green and renders a clear
 * "unavailable" notice until that rewrite lands.
 */

export type FreeCadInspectionCardProps = {
  projectId: string | null;
  highlighted?: boolean;
  expanded?: boolean;
  onExpandedChange?(next: boolean): void;
  onInspected?: (...args: unknown[]) => void;
  showHealthRerunPrompt?: unknown;
  onRunHealthCheck?: (...args: unknown[]) => void;
  refreshKey?: unknown;
};

export function FreeCadInspectionCard(_props: FreeCadInspectionCardProps) {
  return (
    <section className="workflow-section panel--muted">
      <header className="workflow-section__head">
        <strong>Geometry inspection</strong>
        <span className="badge badge-muted">unavailable</span>
      </header>
      <p className="panel__hint">
        Direct CAD inspection is not wired in this build. Use the agent
        pipeline (B-Rep graph build + geometry inspection tools) to gather
        feature evidence.
      </p>
    </section>
  );
}
