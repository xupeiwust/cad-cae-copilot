import { useEffect } from "react";
import { Settings } from "lucide-react";

import { api } from "../api";
import { NoticeCenter } from "../components/common";
import { PointerProvider } from "../components/PointerText";
import { PendingApprovals } from "../components/PendingApprovals";
import { SessionsSidebar } from "../components/SessionsSidebar";
import { ViewerPane } from "../components/ViewerPane";
import { GlobalSettingsDrawer } from "../components/settings/GlobalSettingsDrawer";
import { RuntimeSettingsDrawer } from "../components/settings/RuntimeSettingsDrawer";
import { isEmbedMode } from "./embed";
import type { useWorkbenchApp } from "./useWorkbenchApp";

type AppChromeProps = {
  app: ReturnType<typeof useWorkbenchApp>;
};

export function AppChrome({ app }: AppChromeProps) {
  const embed = isEmbedMode();

  // In embed mode (VS Code webview iframe), relay the picked faces to the host
  // shell so its "Copy modify" handoff can target the selected @face: pointers.
  useEffect(() => {
    if (!embed || typeof window === "undefined" || window.parent === window) return;
    window.parent.postMessage(
      { kind: "selectionChanged", pointers: app.pickedFaces.map((face) => face.pointer) },
      "*",
    );
  }, [embed, app.pickedFaces]);

  return (
    <PointerProvider value={app.pointerContextValue}>
      <NoticeCenter
        notice={app.notice ?? app.runtimeNotice}
        onDismiss={() => {
          if (app.notice) {
            app.setNotice(null);
          } else {
            app.setRuntimeNotice(null);
          }
        }}
      />
      <div className="app-shell">
        {!embed && (
        <header className="app-topbar">
          <div className="app-topbar-brand">
            <span className="app-logo">AIENG</span>
            <span className="app-topbar-divider" />
            <span className="app-topbar-project">{app.selectedProject?.name || "Workbench"}</span>
            <span className="app-topbar-mcp">Live CAD/CAE workbench + MCP server</span>
          </div>
          <div className="app-topbar-actions">
            <button
              type="button"
              className="app-topbar-btn"
              onClick={() => app.setSettingsOpen(true)}
              title="Settings"
            >
              <Settings className="h-4 w-4" />
            </button>
          </div>
        </header>
        )}

        <div className={app.sidebarCollapsed ? "app-main sidebar-collapsed" : "app-main"}>
          <SessionsSidebar
            collapsed={app.sidebarCollapsed}
            onCollapsedChange={app.setSidebarCollapsed}
            projectName={app.projectName}
            onProjectNameChange={app.setProjectName}
            busy={app.busy}
            selectedFile={app.selectedFile}
            onSelectedFileChange={app.setSelectedFile}
            selectedId={app.selectedId}
            selectedProject={app.selectedProject}
            projects={app.projects}
            stages={app.stages}
            runBusyTask={app.runBusyTask}
            refreshProjects={app.refreshProjects}
            setNotice={app.setNotice}
            runWorkbenchImportFlow={app.runWorkbenchImportFlow}
          />

          <ViewerPane
            runtimeReady={app.runtimeReady}
            runtimeProvider={app.runtimeProvider}
            selectedProject={app.selectedProject}
            effectiveViewerFormat={app.effectiveViewerFormat}
            activeFieldDescriptor={app.activeFieldDescriptor}
            effectiveViewerUrl={app.effectiveViewerUrl}
            pickedFaces={app.pickedFaces}
            onAddPickedFace={app.addPickedFace}
            onClearPickedFaces={app.clearPickedFaces}
            onCopyPointer={app.copyPointerText}
            cadGenerationProgress={app.cadGenerationProgress}
            highlightedFaceIds={app.highlightedFaceIds}
            brepSnapshot={app.brepSnapshot}
            onClearHighlightedFaces={app.clearHighlightedFaces}
          />

          <PendingApprovals
            approvals={app.pendingApprovals.filter(
              (item) => !item.projectId || item.projectId === app.selectedId,
            )}
            onResolve={app.resolveApproval}
          />
        </div>
      </div>

      <RuntimeSettingsDrawer
        open={app.settingsOpen}
        runtime={app.runtime}
        runtimeDraft={app.runtimeDraft}
        runtimeBusy={app.runtimeBusy}
        runtimeNotice={null}
        runtimeProvider={app.runtimeProvider}
        runtimeReady={app.runtimeReady}
        llmConfig={app.llmConfig}
        llmReady={app.llmReady}
        apiKey={app.apiKey}
        onApiKeyChange={app.updateApiKey}
        onClose={() => app.setSettingsOpen(false)}
        onDraftChange={app.updateRuntimeDraft}
        onLlmChange={app.updateLlmConfig}
        onLlmPreset={app.applyLlmProviderPreset}
        onLlmRestore={app.restoreDefaultLlmConfig}
        onLlmTestResult={app.handleLlmTestResult}
        onTest={() => void app.runRuntimeTask("test", () => api.testRuntimeConfig(app.runtimeDraft!))}
        onSave={() => void app.runRuntimeTask("save", () => api.updateRuntimeConfig(app.runtimeDraft!))}
        onRestore={app.restoreRuntimeDefaults}
        localAgentConfig={app.localAgentConfig}
        localAdapters={[]}
        onLocalAgentChange={(key, value) => app.setLocalAgentConfig((prev) => ({ ...prev, [key]: value }))}
        onProbeLocalAgents={() => undefined}
      />
      <GlobalSettingsDrawer open={app.globalSettingsOpen} onClose={() => app.setGlobalSettingsOpen(false)} />
    </PointerProvider>
  );
}
