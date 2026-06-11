import { useCallback, useEffect, useState } from "react";

import { isEmbedMode } from "./embed";

export function useSettingsUI() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(isEmbedMode());

  useEffect(() => {
    if (!settingsOpen) return;

    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSettingsOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [settingsOpen]);

  return {
    settingsOpen,
    setSettingsOpen,
    globalSettingsOpen,
    setGlobalSettingsOpen,
    sidebarCollapsed,
    setSidebarCollapsed,
  };
}
