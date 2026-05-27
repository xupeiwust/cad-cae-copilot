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
        <span>{pickedFaces.length} face{pickedFaces.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="selection-inspector-list">
        {pickedFaces.map((face) => (
          <div key={face.pointer} className="selection-inspector-item">
            <code><PointerText text={face.pointer} /></code>
            <span>{face.surface_type || "unknown"} · roles: {face.roles.length ? face.roles.join(", ") : "unknown"}</span>
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
