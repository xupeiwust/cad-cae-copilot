/**
 * @vitest-environment happy-dom
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MissionControlPanel } from "./MissionControlPanel";
import type { MissionControlModel } from "../app/missionControl";

afterEach(cleanup);

function model(overrides: Partial<MissionControlModel> = {}): MissionControlModel {
  return {
    projectName: "Bracket",
    packageName: "bracket.aieng",
    packageStatus: "ready",
    packageDetail: "bracket.aieng preserves CAD, CAE, provenance, and review evidence.",
    headline: "CAD evidence loaded; CAE setup not complete",
    cards: [
      { key: "package", label: ".aieng package", status: "ready", detail: "bracket.aieng", meta: "4/5 key evidence members" },
      { key: "results", label: "Result evidence", status: "missing", detail: "No solver/result evidence is available.", meta: "claims not auto-advanced" },
    ],
    workflowSteps: [
      { key: "package", label: "Create package", status: "ready", detail: ".aieng package is available.", draft: null },
      { key: "cae_setup", label: "Bind CAE setup", status: "missing", detail: "Materials are missing.", draft: "Propose missing CAE setup. Do not run solver." },
      { key: "solver", label: "Run solver", status: "blocked", detail: "Solver run must go through existing approval gates.", draft: "Prepare approval-gated solver run. Do not claim validation." },
    ],
    nextAction: {
      label: "Define CAE setup",
      detail: "Ask the agent to inspect package evidence.",
      draft: "Inspect package evidence. Do not run solver.",
    },
    evidenceNotes: [
      ".aieng is the package evidence source of truth.",
      "No result evidence is present; solver values must not be claimed.",
    ],
    ...overrides,
  };
}

describe("MissionControlPanel", () => {
  it("renders package identity, evidence cards, and claim boundary text", () => {
    render(<MissionControlPanel model={model()} />);

    expect(screen.getByText("Mission Control")).toBeTruthy();
    expect(screen.getByText(".aieng evidence package")).toBeTruthy();
    expect(screen.getAllByText("bracket.aieng").length).toBeGreaterThan(0);
    expect(screen.getByText("Result evidence")).toBeTruthy();
    expect(screen.getByText("claims not auto-advanced")).toBeTruthy();
    expect(screen.getByText(/solver values must not be claimed/)).toBeTruthy();
    expect(screen.getByText("CAD to CAE workflow")).toBeTruthy();
    expect(screen.getByText("Bind CAE setup")).toBeTruthy();
    expect(screen.getByText("Run solver")).toBeTruthy();
  });

  it("copies bounded agent prompt when available", () => {
    const onCopyDraft = vi.fn();
    render(<MissionControlPanel model={model()} onCopyDraft={onCopyDraft} />);

    fireEvent.click(screen.getByRole("button", { name: /Copy prompt/i }));

    expect(onCopyDraft).toHaveBeenCalledWith("Inspect package evidence. Do not run solver.");
  });

  it("omits copy action when there is no draft", () => {
    render(<MissionControlPanel model={model({ nextAction: { label: "Review approval", detail: "Use approval UI.", draft: null } })} />);

    expect(screen.queryByRole("button", { name: /Copy prompt/i })).toBeNull();
  });

  it("copies step-level prompts without executing the workflow", () => {
    const onCopyDraft = vi.fn();
    render(<MissionControlPanel model={model()} onCopyDraft={onCopyDraft} />);

    fireEvent.click(screen.getByRole("button", { name: "Copy Run solver prompt" }));

    expect(onCopyDraft).toHaveBeenCalledWith("Prepare approval-gated solver run. Do not claim validation.");
  });
});
