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

/** Recognized mention kinds carried as composer-intent metadata. */
export const COMPOSER_MENTION_KINDS = ["workspace", "project", "artifact", "part", "face"] as const;

export type ComposerMentionKind = (typeof COMPOSER_MENTION_KINDS)[number];

export type ComposerMention = {
  kind: ComposerMentionKind;
  /** The full "@kind:value" token as typed. */
  raw: string;
  /** The id after the colon, when present. */
  value?: string;
};

const MENTION_KIND_SET = new Set<string>(COMPOSER_MENTION_KINDS);

/**
 * Extract lightweight "@kind[:value]" mentions from the input. Only the
 * recognized {@link COMPOSER_MENTION_KINDS} are returned; geometry pointer
 * prefixes that are not product-level mentions (e.g. @edge, @group) are ignored
 * here. Pure and total — never throws.
 */
export function extractComposerMentions(text: string): ComposerMention[] {
  const input = text ?? "";
  const mentions: ComposerMention[] = [];
  const re = /@([A-Za-z]+)(?::([^\s]+))?/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(input)) !== null) {
    const kind = match[1].toLowerCase();
    if (!MENTION_KIND_SET.has(kind)) continue;
    const mention: ComposerMention = { kind: kind as ComposerMentionKind, raw: match[0] };
    if (match[2]) mention.value = match[2];
    mentions.push(mention);
  }
  return mentions;
}

/**
 * The wire-shape carried through the send pipeline (chat message `extra` and the
 * autopilot run request). Intentionally free of UI-only state and of start/end
 * indices — it records *what was intended*, not how it was typed. `command` is
 * null for plain input; `text` preserves the original (incl. non-ASCII) text.
 */
export type ComposerIntentMetadata = {
  command: ComposerCommand | null;
  commandRaw: string | null;
  text: string;
  mentions: ComposerMention[];
  errors: string[];
};

export type ComposerCommandSuggestion = {
  command: ComposerCommand;
  /** Conservative 0..1 score; higher when the keyword leads the input. */
  confidence: number;
  /** The keyword that triggered the suggestion (for display / debugging). */
  reason: string;
};

// Conservative keyword heuristics, English + Chinese. Order = priority: the
// first matching rule wins, so more specific verbs should not be shadowed.
const SUGGESTION_RULES: { command: ComposerCommand; keywords: string[] }[] = [
  {
    command: "build",
    keywords: ["build", "create", "generate", "draw", "model a", "画", "创建", "生成", "建模"],
  },
  {
    command: "modify",
    keywords: ["modify", "change", "add ", "remove", "replace", "optimize", "加", "改", "修改", "删除", "替换", "优化"],
  },
  {
    command: "critique",
    keywords: ["critique", "check", "inspect", "review", "problem", "manufactur", "检查", "审查", "问题", "可制造"],
  },
  {
    command: "explain",
    keywords: ["explain", "describe", "what is", "解释", "说明", "介绍"],
  },
  {
    command: "simulate",
    keywords: ["simulate", "simulation", "analysis", "analyse", "analyz", "load", "stress", "仿真", "模拟", "载荷", "应力"],
  },
];

/** Minimum trimmed length before we attempt a natural-language suggestion. */
const MIN_SUGGESTION_LENGTH = 3;

/**
 * Suggest a slash command for free-form input, or null. Pure, total, and
 * conservative — it never fires for input that is already a command, that is
 * too short, or that matches no keyword. Advisory only: callers must not block
 * sending on it.
 */
export function suggestComposerCommand(input: string, _context?: unknown): ComposerCommandSuggestion | null {
  const trimmed = (input ?? "").trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("/")) return null; // already a command — nothing to suggest
  if (trimmed.length < MIN_SUGGESTION_LENGTH) return null;
  const lower = trimmed.toLowerCase();
  for (const rule of SUGGESTION_RULES) {
    for (const keyword of rule.keywords) {
      const k = keyword.toLowerCase();
      const idx = lower.indexOf(k);
      if (idx === -1) continue;
      return { command: rule.command, confidence: idx === 0 ? 0.8 : 0.6, reason: keyword.trim() };
    }
  }
  return null;
}

/**
 * Prefix a message with "/command " unless it already starts with a slash.
 * Pure — used to apply a natural-language suggestion. Never strips or rewrites
 * existing command text.
 */
export function prefixComposerCommand(message: string, command: ComposerCommand): string {
  if ((message ?? "").replace(/^\s+/, "").startsWith("/")) return message;
  return `/${command} ${message}`;
}

/** Build the send-pipeline metadata for a raw composer input. Pure and total. */
export function toComposerIntentMetadata(rawText: string): ComposerIntentMetadata {
  const intent = parseComposerIntent(rawText);
  return {
    command: intent.command,
    commandRaw: intent.commandRaw,
    text: intent.text,
    mentions: extractComposerMentions(rawText),
    errors: [...intent.errors],
  };
}
