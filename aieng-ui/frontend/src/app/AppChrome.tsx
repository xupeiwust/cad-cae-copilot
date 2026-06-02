import { Settings } from "lucide-react";

import { api } from "../api";
import { NoticeCenter } from "../components/common";
import { PointerProvider } from "../components/PointerText";
import { SessionsSidebar } from "../components/SessionsSidebar";
import { ShapeIrObjectsCard } from "../components/ShapeIrObjectsCard";
import { ViewerPane } from "../components/ViewerPane";
import { SelectionInspectorCard } from "../components/agent/SelectionInspectorCard";
import { ChatPanel } from "../components/panels/ChatPanel";
import { GlobalSettingsDrawer } from "../components/settings/GlobalSettingsDrawer";
import { RuntimeSettingsDrawer } from "../components/settings/RuntimeSettingsDrawer";
import type { useWorkbenchApp } from "./useWorkbenchApp";

type AppChromeProps = {
  app: ReturnType<typeof useWorkbenchApp>;
};

export function AppChrome({ app }: AppChromeProps) {
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
        <header className="app-topbar">
          <div className="app-topbar-brand">
            <span className="app-logo">AIDE</span>
            <span className="app-topbar-divider" />
            <span className="app-topbar-project">{app.selectedProject?.name || "Workbench"}</span>
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
            chatSessions={app.chatSessions}
            activeSessionId={app.activeSessionId}
            onSelectSession={app.selectChatSession}
            onCreateSession={() => void app.createChatSession()}
            onDeleteSession={(sessionId) => void app.deleteChatSession(sessionId)}
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
            onInsertToChat={app.insertToChat}
            onRunPreprocess={app.runPreprocessFromPointer}
            cadGenerationProgress={app.cadGenerationProgress}
            highlightedFaceIds={app.highlightedFaceIds}
            brepSnapshot={app.brepSnapshot}
            onClearHighlightedFaces={app.clearHighlightedFaces}
          />

          <div className="chat-pane">
            {app.shapeIrObjects.length > 0 ? (
              <ShapeIrObjectsCard
                objects={app.shapeIrObjects}
                verification={app.shapeIrVerification}
                activeNodeId={app.selectedShapeIrNodeId}
                onSelectNode={app.selectShapeIrNode}
                pickedFaceIds={app.pickedFaces.map((face) =>
                  face.pointer.startsWith("@face:") ? face.pointer.slice("@face:".length) : face.pointer,
                )}
              />
            ) : null}
            {app.pickedFaces.length > 0 ? (
              <SelectionInspectorCard
                pickedFaces={app.pickedFaces}
                onClear={app.clearPickedFaces}
                onSetPrompt={app.setMessage}
                onUseInPrompt={app.insertToChat}
              />
            ) : null}
            <ChatPanel
              chatConnections={app.chatConnections}
              selectedChatConnectionId={app.selectedChatConnectionId}
              approvalMode={app.approvalMode}
              approvalModeDisabled={!app.activeSessionId}
              selectedConnectionBlocked={app.selectedConnectionBlocked}
              selectedId={app.selectedId}
              activeSessionId={app.activeSessionId}
              engineeringContext={app.engineeringContext}
              onContextSummaryChange={app.updateActiveSessionContextSummary}
              chatBusy={app.chatBusy}
              cadGenerating={app.cadGenerating}
              cadGenerationProgress={app.cadGenerationProgress}
              llmReady={app.llmReady}
              chatHistory={app.chatHistory}
              agentEvents={app.agentEvents}
              streamingState={app.streamingState}
              chatLogRef={app.chatLogRef}
              message={app.message}
              lastRuntimeRun={app.lastRuntimeRun}
              simulationPending={app.simulationPending}
              simulationProgress={app.simulationProgress}
              setSelectedChatConnectionId={app.setSelectedChatConnectionId}
              setApprovalMode={app.setActiveSessionApprovalMode}
              setSettingsOpen={app.setSettingsOpen}
              setMessage={app.setMessage}
              sendUnified={app.sendUnified}
              viewArtifact={app.viewArtifact}
              approveRun={app.approveRun}
              rejectRun={app.rejectRun}
              approveAutopilot={(runId) => void app.updateAutopilotRun(runId, "approve")}
              rejectAutopilot={(runId) => void app.updateAutopilotRun(runId, "reject")}
              cancelAutopilot={(runId) => void app.updateAutopilotRun(runId, "cancel")}
              reviseAutopilot={(runId, message) => void app.updateAutopilotRun(runId, "reply", message)}
              approveSimulation={() => void app.executeSimulation()}
              rejectSimulation={() => app.setSimulationPending(false)}
              recentPickedFaces={app.pickedFaces}
            />
          </div>
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
        localAdapters={app.selectedChatConnection.adapters ?? []}
        onLocalAgentChange={(key, value) => app.setLocalAgentConfig((prev) => ({ ...prev, [key]: value }))}
        onProbeLocalAgents={() => void app.probeLocalAgents()}
      />
      <GlobalSettingsDrawer open={app.globalSettingsOpen} onClose={() => app.setGlobalSettingsOpen(false)} />
    </PointerProvider>
  );
}
