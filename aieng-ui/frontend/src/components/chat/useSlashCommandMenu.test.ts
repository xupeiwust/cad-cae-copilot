import { test } from "vitest";

import {
  SLASH_COMMANDS,
  applySlashCommand,
  filterSlashCommands,
  slashCommandQuery,
} from "./useSlashCommandMenu";

test("slash command menu pure logic", () => {
  // "/" at the start opens with an empty query.
  const bare = slashCommandQuery("/", 1);
  expectEqual(bare?.query, "", "bare slash -> empty query");
  expectEqual(bare?.start, 1, "bare slash -> start after slash");

  // "/b" filters to a partial query.
  expectEqual(slashCommandQuery("/b", 2)?.query, "b", "/b -> query b");

  // Caret moved past the command token (after a space) closes the menu.
  expectEqual(slashCommandQuery("/build drone", 9), null, "caret past token -> closed");
  // Caret still inside the token keeps it open.
  expectEqual(slashCommandQuery("/build drone", 4)?.query, "build", "caret in token -> query");

  // A slash NOT at the start never opens the menu.
  expectEqual(slashCommandQuery("please /build", 13), null, "mid-string slash -> closed");

  // An "@" mention must NOT trigger the slash menu (input does not start with /).
  expectEqual(slashCommandQuery("@face:f_top", 5), null, "@ mention -> no slash menu");
  expectEqual(slashCommandQuery("use @f", 6), null, "@ mid-line -> no slash menu");

  // Registry carries a description + example for every command (discoverability).
  expectEqual(SLASH_COMMANDS.length, 5, "five commands in registry");
  for (const def of SLASH_COMMANDS) {
    expectEqual(def.description.length > 0, true, `${def.command}: has description`);
    expectEqual(def.example.startsWith(`/${def.command}`), true, `${def.command}: example is a /command`);
    expectEqual(def.title.length > 0, true, `${def.command}: has title`);
    expectEqual(def.label, `/${def.command}`, `${def.command}: label is /command`);
  }

  // Empty query shows all commands.
  expectEqual(filterSlashCommands("").length, SLASH_COMMANDS.length, "empty query -> all commands");
  expectEqual(filterSlashCommands("").length, 5, "five supported commands");

  // "b" filters to build only.
  const b = filterSlashCommands("b");
  expectEqual(b.length, 1, "b -> one match");
  expectEqual(b[0].command, "build", "b -> build");

  // Case-insensitive prefix filter.
  expectEqual(filterSlashCommands("CRI")[0]?.command, "critique", "CRI -> critique");

  // Unknown prefix is stable (no matches, no throw).
  expectEqual(filterSlashCommands("zzz").length, 0, "unknown prefix -> no matches");

  // Accepting a command inserts "/<command> " and keeps trailing args.
  let applied = applySlashCommand("/b", "build");
  expectEqual(applied.text, "/build ", "accept /b -> /build + space");
  expectEqual(applied.cursor, "/build ".length, "caret after the space");

  applied = applySlashCommand("/b drone", "build");
  expectEqual(applied.text, "/build drone", "accept keeps the trailing argument");
  expectEqual(applied.cursor, "/build ".length, "caret after the command, before the arg");

  // Accepting from bare slash works too.
  applied = applySlashCommand("/", "simulate");
  expectEqual(applied.text, "/simulate ", "bare slash -> full command");
});

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
