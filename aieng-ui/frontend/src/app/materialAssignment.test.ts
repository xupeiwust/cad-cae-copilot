import { expect, test } from "vitest";

import {
  ALL_PARTS_TARGET,
  assignmentTargets,
  materialAssignmentDraft,
} from "./materialAssignment";

test("assignmentTargets always offers All-named-parts first, then each part", () => {
  const targets = assignmentTargets(["base_plate", "rib_main"]);
  expect(targets[0].value).toBe(ALL_PARTS_TARGET);
  expect(targets[0].label).toContain("(2)");
  expect(targets.map((t) => t.value)).toEqual([ALL_PARTS_TARGET, "base_plate", "rib_main"]);
  // labels humanize underscores
  expect(targets[2].label).toBe("rib main");
});

test("assignmentTargets tolerates empty / missing parts", () => {
  expect(assignmentTargets([]).map((t) => t.value)).toEqual([ALL_PARTS_TARGET]);
  expect(assignmentTargets(null).map((t) => t.value)).toEqual([ALL_PARTS_TARGET]);
  expect(assignmentTargets(["", "  "]).map((t) => t.value)).toEqual([ALL_PARTS_TARGET]);
});

test("materialAssignmentDraft drafts an all-parts /modify", () => {
  expect(materialAssignmentDraft("Al6061-T6", ALL_PARTS_TARGET)).toBe(
    "/modify assign material Al6061-T6 to all named parts",
  );
});

test("materialAssignmentDraft drafts a per-part /modify", () => {
  expect(materialAssignmentDraft("Steel-316L", "base_plate")).toBe(
    "/modify assign material Steel-316L to part base_plate",
  );
});

test("materialAssignmentDraft is null without a material or target", () => {
  expect(materialAssignmentDraft("", ALL_PARTS_TARGET)).toBeNull();
  expect(materialAssignmentDraft("Al6061-T6", "")).toBeNull();
  expect(materialAssignmentDraft(null, null)).toBeNull();
});
