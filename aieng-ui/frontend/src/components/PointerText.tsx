import { createContext, Fragment, useContext } from "react";

/**
 * Parses inline @entity:id pointers emitted by the LLM/agent and renders
 * them as clickable chips. Pointer syntax matches what
 * GeometryContext.to_llm_text() and brep_graph emit on the backend.
 */

export type PointerKind = "face" | "feature" | "edge" | "group" | "artifact";

export type PointerToken = {
  kind: PointerKind;
  id: string;
};

// Matches @face:face_001, @feature:feat_xx, @artifact:results/x.json, etc.
// Artifact ids allow slashes, dots, and dashes; the others are word-ish.
const POINTER_RE = /@(face|feature|edge|group|artifact):([A-Za-z0-9_./\-]+)/g;

type Segment = { kind: "text"; text: string } | { kind: "pointer"; token: PointerToken };

export function parsePointers(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(POINTER_RE)) {
    const start = match.index ?? 0;
    if (start > last) {
      out.push({ kind: "text", text: text.slice(last, start) });
    }
    out.push({
      kind: "pointer",
      token: { kind: match[1] as PointerKind, id: match[2] },
    });
    last = start + match[0].length;
  }
  if (last < text.length) {
    out.push({ kind: "text", text: text.slice(last) });
  }
  return out;
}

export function hasPointer(text: string): boolean {
  POINTER_RE.lastIndex = 0;
  const has = POINTER_RE.test(text);
  POINTER_RE.lastIndex = 0;
  return has;
}

export type PointerChipProps = {
  token: PointerToken;
  highlighted?: boolean;
  onClick?(token: PointerToken): void;
};

export function PointerChip({ token, highlighted, onClick }: PointerChipProps) {
  const tooltip = (() => {
    switch (token.kind) {
      case "face":
        return `Click to ${highlighted ? "remove" : "highlight"} face in viewer`;
      case "feature":
        return "Click to highlight all faces of this feature";
      case "group":
        return "Click to highlight all faces in this group";
      case "edge":
        return "Edge reference";
      case "artifact":
        return "Package artifact path";
      default:
        return token.id;
    }
  })();
  return (
    <button
      type="button"
      className={`pointer-chip pointer-chip--${token.kind}${highlighted ? " pointer-chip--active" : ""}`}
      onClick={() => onClick?.(token)}
      title={tooltip}
    >
      <span className="pointer-chip__kind">@{token.kind}</span>
      <code className="pointer-chip__id">{token.id}</code>
    </button>
  );
}

export type PointerContextValue = {
  highlightedFaceIds: Set<string>;
  onClickPointer(token: PointerToken): void;
};

const PointerContext = createContext<PointerContextValue | null>(null);

export const PointerProvider = PointerContext.Provider;

export function usePointerContext(): PointerContextValue | null {
  return useContext(PointerContext);
}

export type PointerTextProps = {
  text: string | null | undefined;
  highlightedFaceIds?: Set<string>;
  onClickPointer?(token: PointerToken): void;
};

/**
 * Renders text with @entity:id pointers turned into clickable chips.
 * If `highlightedFaceIds` / `onClickPointer` are not passed as props, falls
 * back to the nearest PointerProvider in the component tree.
 */
export function PointerText({ text, highlightedFaceIds, onClickPointer }: PointerTextProps) {
  const ctx = useContext(PointerContext);
  const effectiveHighlighted = highlightedFaceIds ?? ctx?.highlightedFaceIds;
  const effectiveClick = onClickPointer ?? ctx?.onClickPointer;
  if (!text) return null;
  if (!hasPointer(text)) return <>{text}</>;
  const segments = parsePointers(text);
  return (
    <>
      {segments.map((seg, idx) => {
        if (seg.kind === "text") {
          return <Fragment key={idx}>{seg.text}</Fragment>;
        }
        const isFace = seg.token.kind === "face";
        const active = isFace && effectiveHighlighted?.has(seg.token.id);
        return (
          <PointerChip
            key={idx}
            token={seg.token}
            highlighted={active}
            onClick={effectiveClick}
          />
        );
      })}
    </>
  );
}
