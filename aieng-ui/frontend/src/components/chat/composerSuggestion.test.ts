import { test } from "vitest";

import { prefixComposerCommand, suggestComposerCommand } from "./composerIntent";

test("natural-language command suggestion", () => {
  // Each command is suggested from representative English phrasing.
  expectEqual(suggestComposerCommand("create a quadcopter")?.command, "build", "create -> build");
  expectEqual(suggestComposerCommand("draw a new bracket")?.command, "build", "draw -> build");
  expectEqual(suggestComposerCommand("add rotor guards")?.command, "modify", "add -> modify");
  expectEqual(suggestComposerCommand("change the wall thickness")?.command, "modify", "change -> modify");
  expectEqual(suggestComposerCommand("check manufacturability")?.command, "critique", "check -> critique");
  expectEqual(suggestComposerCommand("inspect the model")?.command, "critique", "inspect -> critique");
  expectEqual(suggestComposerCommand("describe the drone structure")?.command, "explain", "describe -> explain");
  expectEqual(suggestComposerCommand("explain this project")?.command, "explain", "explain -> explain");
  expectEqual(suggestComposerCommand("estimate load response")?.command, "simulate", "load -> simulate");
  expectEqual(suggestComposerCommand("run a stress analysis")?.command, "simulate", "stress -> simulate");

  // Chinese phrasing for each command.
  expectEqual(suggestComposerCommand("创建一个无人机")?.command, "build", "创建 -> build");
  expectEqual(suggestComposerCommand("优化壁厚")?.command, "modify", "优化 -> modify");
  expectEqual(suggestComposerCommand("检查可制造性")?.command, "critique", "检查 -> critique");
  expectEqual(suggestComposerCommand("解释一下结构")?.command, "explain", "解释 -> explain");
  expectEqual(suggestComposerCommand("做载荷仿真")?.command, "simulate", "仿真 -> simulate");

  // Confidence is higher when the keyword leads the input.
  const lead = suggestComposerCommand("create a part");
  expectEqual(lead?.confidence, 0.8, "leading keyword -> 0.8");
  const mid = suggestComposerCommand("please create a part");
  expectEqual(mid?.confidence, 0.6, "mid keyword -> 0.6");

  // Slash-prefixed input never produces a suggestion (already a command).
  expectEqual(suggestComposerCommand("/modify add a rib"), null, "slash input -> null");
  expectEqual(suggestComposerCommand("   /build drone"), null, "slash after ws -> null");

  // Too short / empty / no-keyword inputs are conservative (null).
  expectEqual(suggestComposerCommand(""), null, "empty -> null");
  expectEqual(suggestComposerCommand("hi"), null, "too short -> null");
  expectEqual(suggestComposerCommand("the quick brown fox"), null, "no keyword -> null");

  // Reason reports the triggering keyword.
  expectEqual(suggestComposerCommand("inspect the model")?.reason, "inspect", "reason is the keyword");
});

test("applying a suggestion prefixes the command", () => {
  // Plain message gets prefixed with "/command ".
  expectEqual(prefixComposerCommand("add a rib", "modify"), "/modify add a rib", "prefix added");
  // Already a command -> unchanged (never double-prefix, never strip).
  expectEqual(prefixComposerCommand("/build drone", "modify"), "/build drone", "existing command untouched");
  expectEqual(prefixComposerCommand("  /build drone", "modify"), "  /build drone", "leading ws + command untouched");
  // Chinese message prefixes correctly and preserves the text.
  expectEqual(prefixComposerCommand("优化壁厚", "modify"), "/modify 优化壁厚", "chinese prefixed + preserved");
});

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
