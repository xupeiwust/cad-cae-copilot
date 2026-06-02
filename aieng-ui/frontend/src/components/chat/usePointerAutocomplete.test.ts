import { test } from "vitest";

import type { PickedFace } from "../../appTypes";
import {
  applyPointerSuggestion,
  filterPointerMatches,
  pointerMentionQuery,
} from "./usePointerAutocomplete";

test("pointer autocomplete pure logic", () => {
  const faces: PickedFace[] = [
    { pointer: "@face:f_top", label: "top face", surface_type: "plane", roles: [] },
    { pointer: "@face:f_load", label: "load surface", surface_type: "plane", roles: [] },
    { pointer: "@edge:e_fillet", label: "fillet edge", surface_type: "bspline", roles: [] },
  ];

  // No "@" => no autocomplete.
  expectEqual(pointerMentionQuery("build a bracket", 15), null, "no mention without @");

  // Cursor right after "@" => empty query, mention starts after the @.
  const justAt = pointerMentionQuery("hello @", 7);
  expectEqual(justAt?.query, "", "empty query at bare @");
  expectEqual(justAt?.start, 7, "mention start after @");

  // Partial token "@f" => query "f".
  const partial = pointerMentionQuery("use @f", 6);
  expectEqual(partial?.query, "f", "partial mention query");

  // A space after the @ token closes the mention (cursor not inside it).
  expectEqual(pointerMentionQuery("use @face done", 14), null, "space ends the mention token");

  // Filtering on pointer or label substring (case-insensitive).
  expectEqual(filterPointerMatches(faces, "").length, 3, "empty query matches all");
  expectEqual(filterPointerMatches(faces, "load").map((f) => f.pointer).join(","), "@face:f_load", "match by label");
  expectEqual(filterPointerMatches(faces, "EDGE").map((f) => f.pointer).join(","), "@edge:e_fillet", "match by pointer, case-insensitive");
  expectEqual(filterPointerMatches(faces, "zzz").length, 0, "no matches is stable");

  // Accepting a suggestion replaces the "@query" token with "<pointer> "
  // (caret typically at end of the token, nothing after it).
  const text = "use @f";
  const mention = pointerMentionQuery(text, 6);
  expectEqual(mention?.start, 5, "mention start index");
  const applied = applyPointerSuggestion(text, mention!.start, 6, "@face:f_load");
  expectEqual(applied.text, "use @face:f_load ", "token replaced with pointer + space");
  expectEqual(applied.cursor, "use @face:f_load ".length, "caret after inserted pointer");
});

function expectEqual(actual: unknown, expected: unknown, label = "value") {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
