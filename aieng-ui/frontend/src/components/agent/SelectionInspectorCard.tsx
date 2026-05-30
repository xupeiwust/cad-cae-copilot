import type { PickedFace } from "../../appTypes";
import { PointerText } from "../PointerText";

type SelectionInspectorCardProps = {
  pickedFaces: PickedFace[];
  onClear(): void;
  onSetPrompt(text: string): void;
  onUseInPrompt(text: string): void;
};

export function SelectionInspectorCard({
  pickedFaces,
  onClear,
  onSetPrompt,
  onUseInPrompt,
}: SelectionInspectorCardProps) {
  if (!pickedFaces.length) return null;

  // A "mesh_region" face is the whole body of a mesh part (manifold/SDF/optimized
  // topology), not a discrete B-Rep face — so picking it highlights the entire part.
  // Label these as whole-body selections so the panel matches what the viewer shows.
  const isRegion = (face: PickedFace) => face.surface_type === "mesh_region";
  const allRegions = pickedFaces.every(isRegion);
  const anyRegion = pickedFaces.some(isRegion);
  const countNoun = allRegions ? "body" : anyRegion ? "selection" : "face";

  const pointerText = pickedFaces.map((face) => face.pointer).join(" ");
  const primaryPointer = pickedFaces[0]?.pointer ?? "@face:selected";
  const suggestedActions = [
    { label: "Add holes", prompt: `Add mounting holes on ${primaryPointer}` },
    { label: "Offset face", prompt: `Offset ${primaryPointer} by 2 mm` },
    { label: "Fillet edge", prompt: `Fillet the relevant edge near ${primaryPointer} by 2 mm` },
    { label: "Fixed support", prompt: `Use ${primaryPointer} as fixed support for preprocessing` },
    { label: "Apply load", prompt: `Apply a load on ${primaryPointer}` },
  ];

  return (
    <section className="selection-inspector-card" aria-label="Selected geometry">
      <div className="selection-inspector-head">
        <strong>Selected geometry</strong>
        <span>{pickedFaces.length} {countNoun}{pickedFaces.length !== 1 ? "s" : ""}</span>
      </div>
      {anyRegion && (
        <p className="selection-inspector-note">
          This is a mesh part — selecting it highlights the whole body, not a single
          B-Rep face (mesh geometry has no per-face topology).
        </p>
      )}
      <div className="selection-inspector-list">
        {pickedFaces.map((face) => (
          <div key={face.pointer} className="selection-inspector-item">
            <code><PointerText text={face.pointer} /></code>
            <span>
              {isRegion(face) ? "whole body (mesh region)" : (face.surface_type || "unknown")}
              {" · roles: "}{face.roles.length ? face.roles.join(", ") : "unknown"}
            </span>
          </div>
        ))}
      </div>
      <div className="selection-inspector-actions">
        <button type="button" className="ghost-button compact-button" onClick={() => onUseInPrompt(pointerText)}>
          Use in prompt
        </button>
        <button type="button" className="ghost-button compact-button" onClick={onClear}>
          Clear
        </button>
      </div>
      <div className="selection-inspector-suggestions" aria-label="Geometry suggested actions">
        {suggestedActions.map((action) => (
          <button
            key={action.label}
            type="button"
            className="ghost-button compact-button"
            onClick={() => onSetPrompt(action.prompt)}
          >
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}
