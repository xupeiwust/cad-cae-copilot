import { useMemo, useState, type ReactNode } from "react";

export type DebugPanelSection = {
  id: string;
  label: string;
  children: ReactNode;
};

export function DebugPanel({ sections }: { sections: DebugPanelSection[] }) {
  const firstSectionId = sections[0]?.id ?? "";
  const [activeSectionId, setActiveSectionId] = useState(firstSectionId);
  const activeSection = useMemo(
    () => sections.find((section) => section.id === activeSectionId) ?? sections[0] ?? null,
    [activeSectionId, sections],
  );

  if (!activeSection) return null;

  return (
    <section className="debug-panel">
      <div className="advanced-panel-intro">
        <strong>Advanced workspace</strong>
        <span>Diagnostics, simulation utilities, and experimental workflows are kept here so the main build view stays focused.</span>
      </div>
      <div className="debug-panel-tabs" role="tablist" aria-label="Advanced workbench sections">
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            role="tab"
            aria-selected={activeSection.id === section.id}
            className={activeSection.id === section.id ? "debug-panel-tab active" : "debug-panel-tab"}
            onClick={() => setActiveSectionId(section.id)}
          >
            {section.label}
          </button>
        ))}
      </div>
      <div className="debug-panel-body">{activeSection.children}</div>
    </section>
  );
}
