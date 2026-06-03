/**
 * Pure composer slash-command parsing. No DOM, no React, never throws.
 *
 * A slash command is recognized ONLY at the very start of the input (after any
 * leading whitespace). "please /build drone" is plain text, not a command.
 * Chinese (and any non-ASCII) text is preserved verbatim in `text`.
 */

export const COMPOSER_COMMANDS = ["build", "modify", "critique", "explain", "simulate"] as const;

export type ComposerCommand = (typeof COMPOSER_COMMANDS)[number];

export type ComposerIntentError = "unknown_command";

export type ComposerIntent = {
  /** The original, unmodified input. */
  rawText: string;
  /** The recognized command, or null when the input is plain text / unknown. */
  command: ComposerCommand | null;
  /** The raw "/token" as typed (e.g. "/build", "/foo"), or null when no leading slash. */
  commandRaw: string | null;
  /** The argument/prompt text after the command token (input itself when no command). */
  text: string;
  /** Non-fatal parse problems (e.g. an unknown command name). */
  errors: ComposerIntentError[];
};

const COMMAND_SET = new Set<string>(COMPOSER_COMMANDS);

function isComposerCommand(value: string): value is ComposerCommand {
  return COMMAND_SET.has(value);
}

/**
 * Parse the composer input into a {@link ComposerIntent}. Pure and total.
 */
export function parseComposerIntent(rawText: string): ComposerIntent {
  const input = rawText ?? "";
  const leadingWhitespace = input.match(/^\s*/)?.[0] ?? "";
  const body = input.slice(leadingWhitespace.length);

  // A command must be the first thing in the input (ignoring leading whitespace).
  if (!body.startsWith("/")) {
    return { rawText: input, command: null, commandRaw: null, text: input, errors: [] };
  }

  // "/<token><whitespace><rest>" — token is the run of non-whitespace after "/".
  const match = body.match(/^\/(\S*)\s*([\s\S]*)$/);
  const token = match?.[1] ?? "";
  const rest = match?.[2] ?? "";
  const commandRaw = `/${token}`;
  const name = token.toLowerCase();

  if (token === "") {
    // Bare "/" — still being typed; not an error, just not a command yet.
    return { rawText: input, command: null, commandRaw, text: rest, errors: [] };
  }

  if (isComposerCommand(name)) {
    return { rawText: input, command: name, commandRaw, text: rest, errors: [] };
  }

  return { rawText: input, command: null, commandRaw, text: rest, errors: ["unknown_command"] };
}
