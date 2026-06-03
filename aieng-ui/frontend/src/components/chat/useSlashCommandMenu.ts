import { useMemo, useState } from "react";

import { COMPOSER_COMMANDS, type ComposerCommand } from "./composerIntent";

export type SlashCommandDef = {
  command: ComposerCommand;
  /** The "/name" token shown in the menu and inserted into the textarea. */
  label: string;
  /** Short title-case name (e.g. "Build"). */
  title: string;
  /** One-line description of what the command does. */
  description: string;
  /** A concrete usage example shown to aid discovery. */
  example: string;
};

/** Static catalog of supported slash commands (display order). */
export const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    command: "build",
    label: "/build",
    title: "Build",
    description: "Create a new CAD model",
    example: "/build create a quadcopter",
  },
  {
    command: "modify",
    label: "/modify",
    title: "Modify",
    description: "Modify the current CAD model",
    example: "/modify add rotor guards",
  },
  {
    command: "critique",
    label: "/critique",
    title: "Critique",
    description: "Inspect the current model",
    example: "/critique check manufacturability",
  },
  {
    command: "explain",
    label: "/explain",
    title: "Explain",
    description: "Explain the current project / model",
    example: "/explain describe the drone structure",
  },
  {
    command: "simulate",
    label: "/simulate",
    title: "Simulate",
    description: "Prepare or run simulation / CAE",
    example: "/simulate estimate load response",
  },
];

// Sanity guard: keep SLASH_COMMANDS aligned with the parser's command set.
if (SLASH_COMMANDS.length !== COMPOSER_COMMANDS.length) {
  // Non-fatal — surfaces a divergence during tests/dev without throwing in prod.
  // eslint-disable-next-line no-console
  console.warn("SLASH_COMMANDS is out of sync with COMPOSER_COMMANDS");
}

/**
 * The slash-command token being typed at the start of the input, or null. The
 * menu is only active when the input begins with "/" (no leading whitespace —
 * it must be the literal first character) and the caret is within the leading
 * command token (before the first space). This keeps it from fighting the `@`
 * pointer autocomplete, which only triggers mid-line after an "@".
 */
export function slashCommandQuery(text: string, cursor: number): { query: string; start: number } | null {
  if (!text.startsWith("/")) return null;
  const firstSpace = text.indexOf(" ");
  const tokenEnd = firstSpace === -1 ? text.length : firstSpace;
  if (cursor > tokenEnd) return null; // caret moved past the command token
  return { query: text.slice(1, tokenEnd), start: 1 };
}

/** Commands whose name starts with `query` (case-insensitive). Empty => all. */
export function filterSlashCommands(query: string): SlashCommandDef[] {
  const q = query.toLowerCase();
  if (!q) return SLASH_COMMANDS;
  return SLASH_COMMANDS.filter((c) => c.command.startsWith(q));
}

/**
 * Replace the leading "/token" with "/<command> ", preserving any text that
 * followed the token and placing the caret right after the inserted space.
 */
export function applySlashCommand(text: string, command: ComposerCommand): { text: string; cursor: number } {
  const firstSpace = text.indexOf(" ");
  const tokenEnd = firstSpace === -1 ? text.length : firstSpace;
  const rest = text.slice(tokenEnd).replace(/^\s+/, "");
  const insert = `/${command} `;
  return { text: `${insert}${rest}`, cursor: insert.length };
}

export type SlashCommandMenu = {
  open: boolean;
  query: string;
  index: number;
  matches: SlashCommandDef[];
  /** Recompute from the current textarea value + caret. */
  onInput(text: string, cursor: number): void;
  /** Move the highlighted command (delta +1/-1), wrapping. */
  moveSelection(delta: number): void;
  /** Accept a command (the given one, else the highlighted one). Returns the new
   *  text + caret, or null if there is nothing to accept. Closes the menu. */
  accept(text: string, command?: ComposerCommand): { text: string; cursor: number } | null;
  close(): void;
};

/**
 * Headless slash-command menu state machine. Owns no DOM and renders no UI — the
 * component supplies the textarea value/caret and applies the returned text/caret.
 */
export function useSlashCommandMenu(): SlashCommandMenu {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);

  const matches = useMemo(() => filterSlashCommands(query), [query]);

  function close(): void {
    setOpen(false);
    setQuery("");
    setIndex(0);
  }

  function onInput(text: string, cursor: number): void {
    const token = slashCommandQuery(text, cursor);
    if (token) {
      setQuery(token.query);
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

  function accept(text: string, command?: ComposerCommand): { text: string; cursor: number } | null {
    const chosen = command ?? matches[index]?.command;
    if (!chosen) return null;
    const result = applySlashCommand(text, chosen);
    close();
    return result;
  }

  return { open, query, index, matches, onInput, moveSelection, accept, close };
}
