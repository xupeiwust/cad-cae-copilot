import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type {
  ReviewSupportPacketResponse,
  ReviewSupportPacketSection,
  ReviewSupportPacketSectionStatus,
} from "../../types";

type PacketState =
  | { status: "idle" }
  | { status: "loading"; mode: "preview" | "export" }
  | { status: "loaded"; mode: "preview" | "export"; response: ReviewSupportPacketResponse }
  | { status: "error"; message: string };

type Props = {
  projectId: string | null;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  refreshKey?: number | string;
};

const SECTION_ORDER: Array<{ id: string; label: string }> = [
  { id: "project_health", label: "Project Health" },
  { id: "design_targets", label: "Design Targets" },
  { id: "computed_metrics", label: "Computed Metrics" },
  { id: "target_comparison", label: "Target Comparison" },
  { id: "freecad_inspection", label: "FreeCAD Inspection Evidence" },
  { id: "cad_approval", label: "CAD Edit Approval" },
  { id: "structural_solver", label: "Structural Solver Run" },
  { id: "copilot_loop", label: "Copilot Loop Summary" },
  { id: "stale_evidence", label: "Stale Evidence" },
  { id: "audit_trail", label: "Audit / Tool Calls" },
  { id: "known_limitations", label: "Known Limitations" },
];

function statusBadge(status: ReviewSupportPacketSectionStatus): string {
  if (status === "included") return "badge badge-pass";
  if (status === "missing") return "badge badge-muted";
  if (status === "partial") return "badge badge-warn";
  if (status === "error") return "badge badge-fail";
  return "badge";
}

export function ReviewSupportPacketCard({
  projectId,
  expanded = true,
  onExpandedChange,
  refreshKey,
}: Props) {
  const [state, setState] = useState<PacketState>({ status: "idle" });
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);

  useEffect(() => {
    setState({ status: "idle" });
    setLastRefreshed(null);
  }, [projectId]);

  const preview = useCallback(async () => {
    if (!projectId) return;
    setState({ status: "loading", mode: "preview" });
    try {
      const response = await api.getReviewSupportPacketPreview(projectId);
      setState({ status: "loaded", mode: "preview", response });
      setLastRefreshed(new Date().toLocaleString());
    } catch (err) {
      setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [projectId]);

  const exportPacket = useCallback(async () => {
    if (!projectId) return;
    setState({ status: "loading", mode: "export" });
    try {
      const response = await api.exportReviewSupportPacket(projectId, { include_preview_markdown: true });
      setState({ status: "loaded", mode: "export", response });
      setLastRefreshed(new Date().toLocaleString());
    } catch (err) {
      setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [projectId]);

  useEffect(() => {
    if (!refreshKey) return;
    if (state.status === "loaded") void preview();
  }, [refreshKey, preview, state.status]);

  const response = state.status === "loaded" ? state.response : null;
  const sectionsById = new Map<string, ReviewSupportPacketSection>();
  for (const section of response?.sections ?? []) {
    sectionsById.set(section.id, section);
  }
  const isLoading = state.status === "loading";

  return (
    <article className="copilot-loop__demo-card review-support-packet-card">
      <div className="copilot-loop__demo-health">
        <div className="copilot-loop__demo-health-header">
          <div>
            <strong>Engineering Review Support Packet</strong>
            <span className="panel__hint">
              Creates a review packet from existing project evidence. Does not certify design safety.
              Does not run CAD, mesh, or solver tools. Missing evidence is shown honestly, never invented.
            </span>
          </div>
          <div className="button-row">
            <button
              type="button"
              className="primary-button compact-button"
              onClick={() => void preview()}
              disabled={!projectId || isLoading}
            >
              {state.status === "loading" && state.mode === "preview" ? "Building preview…" : "Preview packet"}
            </button>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={() => void exportPacket()}
              disabled={!projectId || isLoading}
            >
              {state.status === "loading" && state.mode === "export" ? "Exporting…" : "Export packet"}
            </button>
            {onExpandedChange ? (
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={() => onExpandedChange(!expanded)}
              >
                {expanded ? "Collapse" : "Expand"}
              </button>
            ) : null}
          </div>
        </div>

        {!projectId ? (
          <p className="panel__hint">Select a project to build or export a review support packet.</p>
        ) : null}

        {lastRefreshed ? <p className="panel__hint">Last action: {lastRefreshed}</p> : null}

        {!expanded ? (
          <p className="panel__hint">
            Collapsed. Expand to preview or export the engineering review support packet.
          </p>
        ) : null}

        {expanded ? (
          <>
            {state.status === "error" ? (
              <div className="inline-error">Review packet failed: {state.message}</div>
            ) : null}

            {response ? (
              <>
                <article className="copilot-loop__subcard">
                  <header className="freecad-inspection-card__result-header">
                    <strong>
                      Packet status{" "}
                      <span className={response.ok ? "badge badge-pass" : "badge badge-fail"}>
                        {response.ok ? "built" : "failed"}
                      </span>
                    </strong>
                    <span className="badge badge-muted">claim advancement: {response.claim_advancement}</span>
                  </header>
                  <p className="panel__hint">{response.claim_boundary}</p>
                  <dl className="compact-dl">
                    <dt>Packet id</dt>
                    <dd><code>{response.packet_id}</code></dd>
                    {response.markdown_path ? (
                      <>
                        <dt>Markdown artifact</dt>
                        <dd><code>{response.markdown_path}</code></dd>
                      </>
                    ) : null}
                    {response.manifest_path ? (
                      <>
                        <dt>JSON manifest</dt>
                        <dd><code>{response.manifest_path}</code></dd>
                      </>
                    ) : null}
                    {!response.markdown_path && !response.manifest_path ? (
                      <>
                        <dt>Mode</dt>
                        <dd>preview-only — not written to package</dd>
                      </>
                    ) : null}
                  </dl>
                  {response.errors.length ? (
                    <ul className="error-list">
                      {response.errors.map((e, idx) => <li key={idx}>{e}</li>)}
                    </ul>
                  ) : null}
                  {response.warnings.length ? (
                    <ul className="warning-list">
                      {response.warnings.map((w, idx) => <li key={idx}>{w}</li>)}
                    </ul>
                  ) : null}
                </article>

                <article className="copilot-loop__subcard">
                  <strong>Section checklist</strong>
                  <p className="panel__hint">
                    Each evidence section is reported as <code>included</code>, <code>partial</code>,
                    <code> missing</code>, or <code>error</code>. Missing means no fabrication.
                  </p>
                  <div className="table-scroll">
                    <table className="mini-table">
                      <thead>
                        <tr>
                          <th>Section</th>
                          <th>Status</th>
                          <th>Artifacts</th>
                        </tr>
                      </thead>
                      <tbody>
                        {SECTION_ORDER.map((row) => {
                          const sec = sectionsById.get(row.id);
                          const status = sec?.status ?? "missing";
                          const paths = sec?.artifact_paths ?? [];
                          return (
                            <tr key={row.id}>
                              <td>{row.label}</td>
                              <td><span className={statusBadge(status)}>{status}</span></td>
                              <td>
                                {paths.length === 0 ? (
                                  <span className="panel__hint">—</span>
                                ) : (
                                  <ul className="artifact-list">
                                    {paths.slice(0, 4).map((p) => <li key={p}><code>{p}</code></li>)}
                                    {paths.length > 4 ? <li>…(+{paths.length - 4} more)</li> : null}
                                  </ul>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </article>

                {response.preview_markdown ? (
                  <article className="copilot-loop__subcard">
                    <header className="freecad-inspection-card__result-header">
                      <strong>Packet preview</strong>
                      <span className="badge badge-muted">read-only</span>
                    </header>
                    <p className="panel__hint">
                      This is the Markdown that would be (or has been) written to the package.
                    </p>
                    <pre className="review-support-packet-card__preview">{response.preview_markdown}</pre>
                  </article>
                ) : null}
              </>
            ) : (
              <p className="panel__hint">
                Build a preview to see how this project's evidence packages up. Export writes the packet
                under <code>reports/review_support/</code> in the .aieng package.
              </p>
            )}
          </>
        ) : null}
      </div>
    </article>
  );
}
