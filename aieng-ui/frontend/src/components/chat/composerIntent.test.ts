import { test } from "vitest";

import { COMPOSER_COMMANDS, parseComposerIntent } from "./composerIntent";

test("composer intent parsing", () => {
  // Empty input -> plain text, no command, no errors.
  let i = parseComposerIntent("");
  expectEqual(i.command, null, "empty: no command");
  expectEqual(i.commandRaw, null, "empty: no commandRaw");
  expectEqual(i.text, "", "empty: text empty");
  expectEqual(i.errors.length, 0, "empty: no errors");

  // Normal text -> no command, text === rawText.
  i = parseComposerIntent("build a bracket");
  expectEqual(i.command, null, "plain: no command");
  expectEqual(i.commandRaw, null, "plain: no commandRaw");
  expectEqual(i.text, "build a bracket", "plain: text is raw input");

  // Every supported command, with an argument.
  for (const cmd of COMPOSER_COMMANDS) {
    const parsed = parseComposerIntent(`/${cmd} payload here`);
    expectEqual(parsed.command, cmd, `${cmd}: recognized`);
    expectEqual(parsed.commandRaw, `/${cmd}`, `${cmd}: commandRaw`);
    expectEqual(parsed.text, "payload here", `${cmd}: text after token`);
    expectEqual(parsed.errors.length, 0, `${cmd}: no errors`);
  }

  // The headline example.
  i = parseComposerIntent("/build drone");
  expectEqual(i.command, "build", "/build drone -> build");
  expectEqual(i.text, "drone", "/build drone -> text drone");

  // Command with no argument.
  i = parseComposerIntent("/critique");
  expectEqual(i.command, "critique", "/critique -> critique");
  expectEqual(i.text, "", "/critique -> empty text");

  // Unknown command -> command null, commandRaw kept, unknown_command error.
  i = parseComposerIntent("/foo x");
  expectEqual(i.command, null, "/foo: no command");
  expectEqual(i.commandRaw, "/foo", "/foo: commandRaw kept");
  expectEqual(i.errors.includes("unknown_command"), true, "/foo: unknown_command error");
  expectEqual(i.text, "x", "/foo: rest text preserved");

  // Slash not at the start -> not a command.
  i = parseComposerIntent("please /build drone");
  expectEqual(i.command, null, "mid-string slash: no command");
  expectEqual(i.commandRaw, null, "mid-string slash: no commandRaw");
  expectEqual(i.text, "please /build drone", "mid-string slash: text is raw input");

  // Bare slash while typing -> no command, no error.
  i = parseComposerIntent("/");
  expectEqual(i.command, null, "bare slash: no command");
  expectEqual(i.commandRaw, "/", "bare slash: commandRaw is /");
  expectEqual(i.errors.length, 0, "bare slash: no error");

  // Leading whitespace before a command is tolerated.
  i = parseComposerIntent("   /modify thinner walls");
  expectEqual(i.command, "modify", "leading ws: command recognized");
  expectEqual(i.text, "thinner walls", "leading ws: text");

  // Case-insensitive command name; commandRaw preserves what was typed.
  i = parseComposerIntent("/Build drone");
  expectEqual(i.command, "build", "case-insensitive: /Build -> build");
  expectEqual(i.commandRaw, "/Build", "case-insensitive: commandRaw preserved");

  // Chinese argument is preserved verbatim.
  i = parseComposerIntent("/build 一个四旋翼无人机");
  expectEqual(i.command, "build", "chinese: command recognized");
  expectEqual(i.text, "一个四旋翼无人机", "chinese: argument preserved");

  // Chinese plain text without a command stays intact.
  i = parseComposerIntent("帮我做一个支架");
  expectEqual(i.command, null, "chinese plain: no command");
  expectEqual(i.text, "帮我做一个支架", "chinese plain: text preserved");
});

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
