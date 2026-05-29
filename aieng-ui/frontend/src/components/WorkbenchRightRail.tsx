import { forwardRef, type ReactNode } from "react";

import type { ControlPaneMode, WorkbenchPaneMode } from "../appTypes";
import { ControlPaneIcon } from "./common";

export type WorkbenchRightRailModeId = ControlPaneMode | WorkbenchPaneMode;

export type WorkbenchRightRailMode = {
  id: WorkbenchRightRailModeId;
  label: string;
  detail: string;
};

export type WorkbenchRightRailProps = {
  activeMode: WorkbenchRightRailModeId;
  activeModeDetail?: string;
  modes: WorkbenchRightRailMode[];
  children: ReactNode;
  onModeChange(mode: WorkbenchRightRailModeId): void;
};

export const WorkbenchRightRail = forwardRef<HTMLElement, WorkbenchRightRailProps>(
  function WorkbenchRightRail(
    {
      activeMode,
      activeModeDetail,
      modes,
      children,
      onModeChange,
    },
    ref,
  ) {
    return (
      <aside className="side-pane" ref={ref}>
        <div className="control-pane-header">
          <div>
            <span className="control-pane-kicker">AI Workbench</span>
            <strong>{activeModeDetail}</strong>
          </div>
        </div>

        <div className="control-pane-tabs" role="tablist" aria-label="Workbench control sections">
          {modes.map((mode) => (
            <button
              key={mode.id}
              type="button"
              role="tab"
              aria-selected={activeMode === mode.id}
              className={activeMode === mode.id ? "control-pane-tab active" : "control-pane-tab"}
              title={`${mode.label} · ${mode.detail}`}
              onClick={() => onModeChange(mode.id)}
            >
              <ControlPaneIcon mode={mode.id} />
              <span className="control-pane-tab-copy">
                <strong>{mode.label}</strong>
                <span>{mode.detail}</span>
              </span>
            </button>
          ))}
        </div>

        {children}
      </aside>
    );
  },
);
