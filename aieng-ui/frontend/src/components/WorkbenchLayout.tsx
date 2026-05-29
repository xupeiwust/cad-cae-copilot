import { type ReactNode } from "react";
import { cn } from "../lib/utils";

export interface WorkbenchLayoutProps {
  header: ReactNode;
  viewer: ReactNode;
  sidebar: ReactNode;
  sidebarOpen: boolean;
  className?: string;
}

/**
 * WorkbenchLayout - 主布局容器
 *
 * Grid layout:
 *   - rows: 40px header + 1fr content
 *   - cols: 1fr viewer + auto sidebar (0 when collapsed)
 *
 * The sidebar collapses by setting its width to 0px via the grid-template-columns
 * transition, while maintaining the same row height as the viewer.
 */
export function WorkbenchLayout({
  header,
  viewer,
  sidebar,
  sidebarOpen,
  className,
}: WorkbenchLayoutProps) {
  return (
    <div
      className={cn(
        "grid h-screen w-screen overflow-hidden bg-bg-darkest transition-all duration-300 ease-spring",
        sidebarOpen
          ? "grid-rows-[40px_1fr] grid-cols-[1fr_380px]"
          : "grid-rows-[40px_1fr] grid-cols-[1fr_0px]",
        className,
      )}
    >
      {/* Header — spans full width across both columns */}
      <div className="col-span-full">{header}</div>

      {/* Main viewer area */}
      <div className="relative min-w-0 overflow-hidden">{viewer}</div>

      {/* Sidebar — collapsible right panel */}
      <aside
        className={cn(
          "flex min-w-0 flex-col overflow-hidden border-l border-white/[0.06] bg-bg-base transition-all duration-300 ease-spring",
          sidebarOpen ? "opacity-100" : "w-0 border-l-0 opacity-0",
        )}
      >
        {sidebar}
      </aside>
    </div>
  );
}
