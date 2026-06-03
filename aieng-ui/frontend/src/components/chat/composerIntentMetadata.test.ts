import { test } from "vitest";

import type { ChatHistoryItem } from "../../appTypes";
import { chatItemExtra, persistedMessageToChatItem } from "../../app/chatStateUtils";
import { toComposerIntentMetadata } from "./composerIntent";

test("composer intent metadata for the send pipeline", () => {
  // /build creates command=build with the trailing text as the prompt.
  let m = toComposerIntentMetadata("/build drone");
  expectEqual(m.command, "build", "/build -> build");
  expectEqual(m.commandRaw, "/build", "/build -> commandRaw");
  expectEqual(m.text, "drone", "/build -> text");
  expectEqual(m.errors.length, 0, "/build -> no errors");
  expectEqual(m.mentions.length, 0, "/build -> no mentions");

  // Normal message -> command null, no errors.
  m = toComposerIntentMetadata("make a bracket");
  expectEqual(m.command, null, "plain -> null command");
  expectEqual(m.commandRaw, null, "plain -> null commandRaw");
  expectEqual(m.text, "make a bracket", "plain -> raw text");

  // Unknown command keeps the error but still produces metadata.
  m = toComposerIntentMetadata("/foo bar");
  expectEqual(m.command, null, "/foo -> null command");
  expectEqual(m.commandRaw, "/foo", "/foo -> commandRaw kept");
  expectEqual(m.errors.includes("unknown_command"), true, "/foo -> unknown_command error");

  // Mentions are extracted (recognized kinds only).
  m = toComposerIntentMetadata("/modify @face:f_top use @project:proj_1 ignore @edge:e_9");
  expectEqual(m.command, "modify", "mentions: command parsed");
  expectEqual(m.mentions.length, 2, "mentions: only recognized kinds");
  expectEqual(m.mentions[0].kind, "face", "mentions: face kind");
  expectEqual(m.mentions[0].value, "f_top", "mentions: face value");
  expectEqual(m.mentions[0].raw, "@face:f_top", "mentions: raw token");
  expectEqual(m.mentions[1].kind, "project", "mentions: project kind");

  // @part and @artifact mentions parse into { kind, raw, value }.
  m = toComposerIntentMetadata("/explain @part:rotor_1 and @artifact:model.glb");
  expectEqual(m.command, "explain", "part/artifact: command parsed");
  expectEqual(m.mentions.length, 2, "part/artifact: two mentions");
  expectEqual(m.mentions[0].kind, "part", "part/artifact: part kind");
  expectEqual(m.mentions[0].value, "rotor_1", "part/artifact: part value (underscore+digit)");
  expectEqual(m.mentions[0].raw, "@part:rotor_1", "part/artifact: part raw");
  expectEqual(m.mentions[1].kind, "artifact", "part/artifact: artifact kind");
  expectEqual(m.mentions[1].value, "model.glb", "part/artifact: artifact value (dot kept)");

  // Multiple part mentions are all recorded (order preserved); unknown kinds dropped.
  m = toComposerIntentMetadata("/modify @part:arm_L @part:arm_R ignore @widget:w_1");
  expectEqual(m.mentions.length, 2, "multi-part: unknown kind ignored");
  expectEqual(m.mentions[0].value, "arm_L", "multi-part: first");
  expectEqual(m.mentions[1].value, "arm_R", "multi-part: second");

  // A non-ASCII part value is preserved verbatim.
  m = toComposerIntentMetadata("/critique @part:转子");
  expectEqual(m.mentions.length, 1, "chinese mention: one");
  expectEqual(m.mentions[0].value, "转子", "chinese mention: value preserved");

  // Chinese command + text roundtrips verbatim.
  m = toComposerIntentMetadata("/build 一个四旋翼无人机");
  expectEqual(m.command, "build", "chinese: command parsed");
  expectEqual(m.text, "一个四旋翼无人机", "chinese: text preserved");

  // chatItemExtra carries composer_intent (snake_case) AND keeps client_id.
  const item: ChatHistoryItem = {
    id: "local-123",
    role: "user",
    body: "/build drone",
    createdAt: "2026-06-03T00:00:00.000Z",
    mode: "runtime",
    composerIntent: toComposerIntentMetadata("/build drone"),
  };
  const extra = chatItemExtra(item)!;
  expectEqual(extra.client_id, "local-123", "extra: client_id preserved");
  expectEqual((extra.composer_intent as { command?: string }).command, "build", "extra: composer_intent.command");

  // Roundtrip back from a persisted message restores composerIntent.
  const restored = persistedMessageToChatItem({
    id: 7,
    project_id: "p1",
    role: "user",
    content: "/build drone",
    created_at: "2026-06-03T00:00:00.000Z",
    extra,
  });
  expectEqual(restored.composerIntent?.command, "build", "roundtrip: composerIntent.command");
  expectEqual(restored.id, "db-7", "roundtrip: db id");

  // A plain persisted message (no composer_intent) stays backward compatible.
  const legacy = persistedMessageToChatItem({
    id: 8,
    project_id: "p1",
    role: "user",
    content: "hello",
    created_at: "2026-06-03T00:00:00.000Z",
    extra: { client_id: "x" },
  });
  expectEqual(legacy.composerIntent, undefined, "legacy: no composerIntent");
  expectEqual(legacy.body, "hello", "legacy: body intact");
});

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
