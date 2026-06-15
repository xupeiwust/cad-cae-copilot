import { describe, expect, it } from "vitest";

import { resolveApiBase } from "./apiBase";

describe("packaged viewer API base", () => {
  it("defaults to the serving origin instead of a fixed host port", () => {
    expect(resolveApiBase(undefined)).toBe("");
    expect(resolveApiBase("http://127.0.0.1:8000")).toBe("http://127.0.0.1:8000");
  });
});
