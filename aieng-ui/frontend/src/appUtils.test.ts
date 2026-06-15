import { describe, expect, it } from "vitest";

import { fieldLabel } from "./appUtils";

describe("fieldLabel", () => {
  it("returns human labels for canonical result-field names", () => {
    expect(fieldLabel("von_mises")).toBe("Von Mises");
    expect(fieldLabel("sxx")).toBe("Sxx");
    expect(fieldLabel("s1")).toBe("S1 (max principal)");
    expect(fieldLabel("tresca")).toBe("Tresca");
    expect(fieldLabel("disp_magnitude")).toBe("Magnitude");
    expect(fieldLabel("ux")).toBe("Ux");
    expect(fieldLabel("safety_factor")).toBe("Safety factor (yield/VM)");
  });

  it("resolves legacy aliases to the same labels", () => {
    expect(fieldLabel("stress")).toBe("Von Mises");
    expect(fieldLabel("displacement")).toBe("Magnitude");
  });

  it("falls back to the raw name for unknown fields", () => {
    expect(fieldLabel("temperature")).toBe("temperature");
  });
});
