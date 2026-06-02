import { useMemo, useState } from "react";

import type { PickedFace } from "../../appTypes";

/**
 * The active `@`-mention being typed at `cursor`, or null when the cursor is not
 * inside a mention token. A token starts at the last `@` before the cursor and
 * ends at the first space — matching the original AgentInputBox behavior.
 */
export function pointerMentionQuery(text: string, cursor: number): { query: string; start: number } | null {
  const before = text.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at === -1) return null;
  const token = before.slice(at + 1);
  if (token.includes(" ")) return null;
  return { query: token, start: at + 1 };
}

/** Case-insensitive filter on pointer or label substring. */
export function filterPointerMatches(faces: PickedFace[], query: string): PickedFace[] {
  const q = query.toLowerCase();
  return faces.filter(
    (face) => face.pointer.toLowerCase().includes(q) || face.label.toLowerCase().includes(q),
  );
}

/**
 * Replace the `@mention` token (whose text starts at `mentionStart`, i.e. just
 * after the `@`) up to `cursor` with `"<pointer> "`, returning the new text and
 * caret position. Mirrors the original insertAutocomplete logic.
 */
export function applyPointerSuggestion(
  text: string,
  mentionStart: number,
  cursor: number,
  pointer: string,
): { text: string; cursor: number } {
  const before = text.slice(0, mentionStart - 1); // drop the leading "@"
  const after = text.slice(cursor);
  const insert = `${pointer} `;
  return { text: `${before}${insert}${after}`, cursor: (before + insert).length };
}

export type PointerAutocomplete = {
  open: boolean;
  query: string;
  index: number;
  matches: PickedFace[];
  /** Recompute state from the current textarea value + caret. */
  onInput(text: string, cursor: number): void;
  /** Move the highlighted suggestion (delta +1/-1), wrapping. */
  moveSelection(delta: number): void;
  /** Accept a suggestion (the given face, else the highlighted one). Returns the
   *  new text + caret, or null if there is nothing to accept. Closes the popup. */
  accept(text: string, cursor: number, face?: PickedFace): { text: string; cursor: number } | null;
  close(): void;
};

/**
 * Headless `@`-pointer autocomplete state machine. Owns no DOM and renders no UI
 * — the component supplies the textarea value/caret and applies the returned
 * text/caret. Pure logic lives in the exported functions above (unit-tested).
 */
export function usePointerAutocomplete(faces: PickedFace[]): PointerAutocomplete {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [mentionStart, setMentionStart] = useState(0);

  const matches = useMemo(() => filterPointerMatches(faces, query), [faces, query]);

  function close(): void {
    setOpen(false);
    setQuery("");
  }

  function onInput(text: string, cursor: number): void {
    const mention = pointerMentionQuery(text, cursor);
    if (mention && faces.length) {
      setMentionStart(mention.start);
      setQuery(mention.query);
      setIndex(0);
      setOpen(true);
    } else {
      close();
    }
  }

  function moveSelection(delta: number): void {
    if (!matches.length) return;
    setIndex((i) => (i + delta + matches.length) % matches.length);
  }

  function accept(text: string, cursor: number, face?: PickedFace): { text: string; cursor: number } | null {
    const chosen = face ?? matches[index];
    if (!chosen) return null;
    const result = applyPointerSuggestion(text, mentionStart, cursor, chosen.pointer);
    close();
    return result;
  }

  return { open, query, index, matches, onInput, moveSelection, accept, close };
}
