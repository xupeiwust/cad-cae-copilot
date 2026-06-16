/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import { ClippingPlaneControls } from "./ClippingPlaneControls";

afterEach(cleanup);

function renderControls(props: Partial<React.ComponentProps<typeof ClippingPlaneControls>> = {}) {
  const defaults = {
    available: true,
    enabled: false,
    onEnabledChange: vi.fn(),
    axis: "x" as const,
    onAxisChange: vi.fn(),
    position: 0.5,
    onPositionChange: vi.fn(),
    flip: false,
    onFlipChange: vi.fn(),
  };
  return render(<ClippingPlaneControls {...defaults} {...props} />);
}

describe("ClippingPlaneControls", () => {
  it("does not render when unavailable", () => {
    renderControls({ available: false });
    expect(screen.queryByText("Section plane")).toBeNull();
  });

  it("toggles clipping via checkbox", () => {
    const onEnabledChange = vi.fn();
    renderControls({ enabled: false, onEnabledChange });

    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect(onEnabledChange).toHaveBeenCalledWith(true);
  });

  it("switches axis with axis buttons", () => {
    const onAxisChange = vi.fn();
    renderControls({ enabled: true, axis: "x", onAxisChange });

    fireEvent.click(screen.getByLabelText("Set clip axis to y"));
    expect(onAxisChange).toHaveBeenCalledWith("y");
  });

  it("updates position via slider", () => {
    const onPositionChange = vi.fn();
    renderControls({ enabled: true, position: 0.2, onPositionChange });

    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "0.75" } });
    expect(onPositionChange).toHaveBeenCalledWith(0.75);
  });

  it("flips side when flip button is clicked", () => {
    const onFlipChange = vi.fn();
    renderControls({ enabled: true, flip: false, onFlipChange });

    fireEvent.click(screen.getByTitle("Flip which side of the plane is visible"));
    expect(onFlipChange).toHaveBeenCalledWith(true);
  });

  it("resets to defaults when reset is clicked", () => {
    const onAxisChange = vi.fn();
    const onPositionChange = vi.fn();
    const onFlipChange = vi.fn();
    renderControls({
      enabled: true,
      axis: "z",
      position: 0.1,
      flip: true,
      onAxisChange,
      onPositionChange,
      onFlipChange,
    });

    fireEvent.click(screen.getByTitle("Reset to X-axis middle"));
    expect(onAxisChange).toHaveBeenCalledWith("x");
    expect(onPositionChange).toHaveBeenCalledWith(0.5);
    expect(onFlipChange).toHaveBeenCalledWith(false);
  });
});
