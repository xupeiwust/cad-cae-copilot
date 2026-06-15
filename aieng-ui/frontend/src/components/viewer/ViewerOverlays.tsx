import type { CadGenerationProgress, PickedFace, ViewerLoadState } from "../../appTypes";
import type { FieldProbe } from "../../types";
import { CadProgressPanel } from "../CadProgressPanel";
import { formatFieldValue } from "./resultFields";

// Presentational overlays drawn on top of the THREE canvas: load/error state,
// the hovered-face tooltip with MCP-instruction copy buttons, the multi-select
// list, the highlight-count badge, the CAD-generation progress panel, and the
// field-probe readout. Pure rendering — all interaction is delegated through callbacks.
export type ViewerOverlaysProps = {
  viewerState: { status: ViewerLoadState; detail: string };
  tooltipFace: PickedFace | null;
  fieldProbe?: FieldProbe | null;
  onClearFieldProbe?(): void;
  pickedFaces: PickedFace[];
  highlightedFaceIds: Set<string>;
  cadGenerationProgress: CadGenerationProgress | null;
  onCopyPointer(text: string): void;
  onClearPickedFaces(): void;
  onClearHighlightedFaces(): void;
};

export function ViewerOverlays({
  viewerState,
  tooltipFace,
  fieldProbe,
  onClearFieldProbe,
  pickedFaces,
  highlightedFaceIds,
  cadGenerationProgress,
  onCopyPointer,
  onClearPickedFaces,
  onClearHighlightedFaces,
}: ViewerOverlaysProps) {
  return (
    <>
      {viewerState.status !== "ready" ? (
        <div className={`viewer-overlay state-${viewerState.status}`}>
          <strong>
            {viewerState.status === "error"
              ? "Preview load failed"
              : viewerState.status === "loading"
                ? "Loading model"
                : "Waiting for preview"}
          </strong>
          <span>{viewerState.detail}</span>
        </div>
      ) : null}
      {tooltipFace && (
        <div className="viewer-face-tooltip">
          <div className="viewer-face-tooltip-row">
            <span className="viewer-face-tooltip-badge">{tooltipFace.surface_type}</span>
            <strong>{tooltipFace.pointer}</strong>
          </div>
          <div className="viewer-face-tooltip-label">{tooltipFace.label}</div>
          {tooltipFace.roles.length > 0 && (
            <div className="viewer-face-tooltip-roles">{tooltipFace.roles.join(", ")}</div>
          )}
          <div className="viewer-face-tooltip-actions">
            <button
              type="button"
              className="viewer-face-action-btn"
              onClick={() => onCopyPointer(`Apply a 500 N load on ${tooltipFace.pointer}`)}
              title="Copy MCP-agent instruction for a 500 N load"
            >
              Copy load instruction
            </button>
            <button
              type="button"
              className="viewer-face-action-btn"
              onClick={() => onCopyPointer(`Set ${tooltipFace.pointer} as fixed support`)}
              title="Copy MCP-agent instruction for a fixed support"
            >
              Copy support instruction
            </button>
            <button
              type="button"
              className="viewer-face-action-btn secondary"
              onClick={() => onCopyPointer(tooltipFace.pointer)}
            >
              Copy pointer
            </button>
          </div>
          <small>Shift+Click to multi-select</small>
        </div>
      )}
      {fieldProbe && (
        <div
          className="viewer-field-probe"
          style={{
            position: "absolute",
            left: fieldProbe.screenX + 12,
            top: fieldProbe.screenY + 12,
            zIndex: 6,
            background: "rgba(17, 24, 39, 0.92)",
            color: "#e5e7eb",
            borderRadius: 6,
            padding: "6px 10px",
            font: "12px/1.35 system-ui, sans-serif",
            maxWidth: 220,
            boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
            pointerEvents: "auto",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
            <strong>Field probe</strong>
            <button
              type="button"
              onClick={onClearFieldProbe}
              title="Clear probe"
              style={{
                background: "transparent",
                border: "none",
                color: "#9ca3af",
                cursor: "pointer",
                fontSize: 14,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>
          <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>
            {formatFieldValue(fieldProbe.value, fieldProbe.unit)}
          </div>
          <div style={{ marginTop: 2, opacity: 0.8, fontVariantNumeric: "tabular-nums" }}>
            node ({fieldProbe.coord.map((c) => c.toFixed(2)).join(", ")})
          </div>
          {fieldProbe.pointer ? (
            <div style={{ marginTop: 2, opacity: 0.8 }}>{fieldProbe.pointer}</div>
          ) : null}
          <small style={{ display: "block", marginTop: 4, opacity: 0.6 }}>Click another point to update</small>
        </div>
      )}
      {pickedFaces.length > 0 && (
        <div className="viewer-face-multisel">
          <div className="viewer-face-multisel-header">
            <strong>{pickedFaces.length} face{pickedFaces.length !== 1 ? "s" : ""} selected</strong>
            <button type="button" className="ghost-button compact-button" onClick={onClearPickedFaces}>
              Clear
            </button>
          </div>
          <div className="viewer-face-multisel-list">
            {pickedFaces.map((f) => (
              <div key={f.pointer} className="viewer-face-multisel-item">
                <span className="viewer-face-multisel-badge">{f.surface_type}</span>
                <code>{f.pointer}</code>
                <button
                  type="button"
                  className="viewer-face-multisel-use"
                  onClick={() => onCopyPointer(f.pointer)}
                  title="Copy pointer"
                >
                  Copy
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {highlightedFaceIds.size > 0 && (
        <div className="viewer-face-highlight-badge">
          <span>
            <strong>{highlightedFaceIds.size}</strong> face{highlightedFaceIds.size !== 1 ? "s" : ""} highlighted
          </span>
          <button type="button" className="ghost-button compact-button" onClick={onClearHighlightedFaces}>
            Clear
          </button>
        </div>
      )}
      {cadGenerationProgress && (
        <div className="viewer-cad-progress-overlay">
          <CadProgressPanel progress={cadGenerationProgress} />
        </div>
      )}
    </>
  );
}
