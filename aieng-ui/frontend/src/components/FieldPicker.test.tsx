/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import { FieldPicker } from "./FieldPicker";
import { RESULT_FIELD_GROUPS } from "./viewer/resultFields";

afterEach(cleanup);

describe("FieldPicker", () => {
  it("renders all selectable result fields grouped by category plus a none option", () => {
    render(<FieldPicker value="" onChange={vi.fn()} />);

    const select = screen.getByLabelText("Result field") as HTMLSelectElement;
    expect(select).toBeDefined();

    const options = Array.from(select.options).map((o) => o.value);
    const fieldCount = RESULT_FIELD_GROUPS.reduce((sum, g) => sum + g.fields.length, 0);
    expect(options.length).toBe(fieldCount + 1); // +1 for "None (geometry)"
    expect(options).toContain("");
    expect(options).toContain("von_mises");
    expect(options).toContain("s1");
    expect(options).toContain("ux");
    expect(options).toContain("safety_factor");

    const optgroups = Array.from(select.getElementsByTagName("optgroup")).map((g) => g.label);
    expect(optgroups).toEqual(["Stress", "Principal", "Displacement", "Safety"]);
  });

  it("reflects the current value and calls onChange", () => {
    const onChange = vi.fn();
    render(<FieldPicker value="von_mises" onChange={onChange} />);

    const select = screen.getByLabelText("Result field") as HTMLSelectElement;
    expect(select.value).toBe("von_mises");

    fireEvent.change(select, { target: { value: "safety_factor" } });
    expect(onChange).toHaveBeenCalledWith("safety_factor");
  });

  it("can be disabled", () => {
    render(<FieldPicker value="" onChange={vi.fn()} disabled />);
    const select = screen.getByLabelText("Result field") as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });
});
