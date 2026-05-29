import { useMemo } from "react";

import type { ShapeIrObject, ShapeIrVerification } from "../appTypes";

type ShapeIrObjectsCardProps = {
  objects: ShapeIrObject[];
  verification: ShapeIrVerification | null;
  activeNodeId: string | null;
  onSelectNode(node: ShapeIrObject): void;
  // Face ids currently picked in the viewer (most recent first) — used to reverse
  // map a clicked face back to its Shape IR node.
  pickedFaceIds: string[];
};

function _editableParams(params: Record<string, unknown> | undefined): [string, string][] {
  if (!params) return [];
  return Object.entries(params).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)]);
}

export function ShapeIrObjectsCard({
  objects,
  verification,
  activeNodeId,
  onSelectNode,
  pickedFaceIds,
}: ShapeIrObjectsCardProps) {
  const faceToNode = useMemo(() => {
    const map = new Map<string, ShapeIrObject>();
    for (const obj of objects) {
      for (const faceId of obj.viewer_selectable_ids ?? []) {
        if (!map.has(faceId)) map.set(faceId, obj);
      }
    }
    return map;
  }, [objects]);

  if (!objects.length) return null;

  // Reverse selection: the most recently picked face that maps to a node wins,
  // so clicking a face in the viewer surfaces its source_ir_node.
  const reverseNode = pickedFaceIds.map((id) => faceToNode.get(id)).find(Boolean) ?? null;
  const active =
    reverseNode ?? objects.find((o) => o.node_id === activeNodeId) ?? null;
  const fromPickedFace = Boolean(reverseNode);

  return (
    <section className="shapeir-card" aria-label="Shape IR objects">
      <div className="shapeir-head">
        <strong>Shape IR objects</strong>
        <span>{objects.length} node{objects.length !== 1 ? "s" : ""}</span>
      </div>

      <div className="shapeir-list">
        {objects.map((obj) => {
          const isActive = active?.node_id === obj.node_id;
          return (
            <button
              key={obj.node_id}
              type="button"
              className={isActive ? "shapeir-item active" : "shapeir-item"}
              onClick={() => onSelectNode(obj)}
              title={`Highlight ${obj.node_id}`}
            >
              <span className="shapeir-item-name">{obj.node_id}</span>
              <span className="shapeir-chip">{obj.representation_kind ?? "unknown"}</span>
            </button>
          );
        })}
      </div>

      {active ? (
        <div className="shapeir-meta" aria-label={`Metadata for ${active.node_id}`}>
          <div className="shapeir-meta-title">
            <code>{active.node_id}</code>
            {fromPickedFace ? <span className="shapeir-hint">from picked face</span> : null}
          </div>
          <dl className="shapeir-meta-grid">
            <dt>type</dt><dd>{active.node_type ?? "—"}</dd>
            <dt>representation</dt><dd>{active.representation_kind ?? "—"}</dd>
            <dt>backend / runtime</dt><dd>{(active.backend ?? "—")} / {(active.runtime ?? "—")}</dd>
            <dt>capability</dt><dd>{active.capability_level ?? "—"}</dd>
            <dt>lossiness</dt><dd>{active.lossiness ?? "—"}</dd>
            <dt>CAD-editable</dt><dd>{active.cad_editable ? "yes" : "no"}</dd>
            <dt>linkage</dt><dd>{active.linkage ?? "—"}</dd>
            <dt>selectable</dt><dd>{(active.viewer_selectable_ids ?? []).length} entity(ies)</dd>
          </dl>

          {_editableParams(active.editable_parameters).length ? (
            <div className="shapeir-params">
              <span className="shapeir-params-label">editable parameters</span>
              <ul>
                {_editableParams(active.editable_parameters).map(([k, v]) => (
                  <li key={k}><code>{k}</code> = {v}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {verification ? (
            <div className="shapeir-verification">
              verification: <strong>{verification.status ?? "—"}</strong>
              {verification.warnings && verification.warnings.length
                ? ` · ${verification.warnings.length} warning(s)`
                : ""}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
