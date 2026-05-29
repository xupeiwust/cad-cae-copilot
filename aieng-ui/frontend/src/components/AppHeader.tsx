import { Activity, PanelRight, Settings } from "lucide-react";
import { cn } from "../lib/utils";

export interface AppHeaderProps {
  projectName?: string;
  liveSyncStatus: "live" | "polling" | "reconnecting" | "offline" | "connecting";
  liveSyncDetail: string;
  onToggleSidebar: () => void;
  onOpenSettings: () => void;
  sidebarOpen: boolean;
}

const statusConfig: Record<string, { dot: string; label: string }> = {
  live: { dot: "bg-success", label: "Live" },
  polling: { dot: "bg-warning animate-pulse", label: "Polling" },
  reconnecting: { dot: "bg-warning animate-pulse", label: "Reconnecting" },
  offline: { dot: "bg-danger", label: "Offline" },
  connecting: { dot: "bg-warning animate-pulse", label: "Connecting" },
};

export function AppHeader({
  projectName,
  liveSyncStatus,
  liveSyncDetail,
  onToggleSidebar,
  onOpenSettings,
  sidebarOpen,
}: AppHeaderProps) {
  const status = statusConfig[liveSyncStatus] ?? statusConfig.connecting;

  return (
    <header className="col-span-full flex h-10 items-center justify-between border-b border-white/[0.04] bg-bg-base px-3 select-none">
      {/* Left: Logo + Project name */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold tracking-tight text-primary-400">AIDE</span>
          <span className="h-3.5 w-px bg-white/10" />
          <span className="max-w-[200px] truncate text-xs text-text-secondary">
            {projectName || "Engineering Workbench"}
          </span>
        </div>
      </div>

      {/* Center: View tabs (placeholder for future use) */}
      <div className="hidden items-center gap-1 md:flex">
        <button className="sidebar-tab sidebar-tab-active">Geometry</button>
        <button className="sidebar-tab">Simulation</button>
        <button className="sidebar-tab">Report</button>
      </div>

      {/* Right: Connection status + actions */}
      <div className="flex items-center gap-2">
        {/* Connection status pill */}
        <div
          className="flex items-center gap-1.5 rounded-full border border-white/[0.06] bg-bg-surface px-2 py-0.5"
          title={liveSyncDetail}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", status.dot)} />
          <span className="text-2xs font-medium text-text-secondary">{status.label}</span>
        </div>

        {/* Settings button */}
        <button
          type="button"
          className="btn-ghost"
          onClick={onOpenSettings}
          title="Settings"
          aria-label="Open settings"
        >
          <Settings className="h-3.5 w-3.5" />
        </button>

        {/* Sidebar toggle */}
        <button
          type="button"
          className={cn("btn-ghost", sidebarOpen && "text-primary-400")}
          onClick={onToggleSidebar}
          title="Toggle sidebar"
          aria-label="Toggle sidebar"
        >
          <PanelRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </header>
  );
}
