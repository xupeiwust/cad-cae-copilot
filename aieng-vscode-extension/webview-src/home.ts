import type { HomeProject, HomeStateMessage, HomeToWebviewMessage, HomeWebviewMessage } from "../src/protocol";

declare function acquireVsCodeApi(): { postMessage(message: HomeWebviewMessage): void };
const vscode = acquireVsCodeApi();

const style = document.createElement("style");
style.textContent = `
:root { color-scheme: light dark; --line: var(--vscode-panel-border, rgba(128,128,128,0.25)); }
* { box-sizing:border-box; }
html,body,#app { min-height:100%; margin:0; }
body { font-family:var(--vscode-font-family); font-size:var(--vscode-font-size,13px); color:var(--vscode-foreground); background:var(--vscode-editor-background); }
button { font:inherit; color:inherit; cursor:pointer; }
.page { max-width:720px; margin:0 auto; padding:28px 24px; display:flex; flex-direction:column; gap:22px; }
.busy { opacity:.6; pointer-events:none; }
.eyebrow { font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--vscode-descriptionForeground); }
h1 { margin:6px 0 6px; font-size:20px; font-weight:600; }
p { margin:0; color:var(--vscode-descriptionForeground); line-height:1.5; }
.steps { display:flex; flex-direction:column; }
.step { display:grid; grid-template-columns:auto 1fr; gap:14px; align-items:start; padding:16px 0; border-top:1px solid var(--line); }
.step:first-child { border-top:0; padding-top:4px; }
.step-n { width:22px; height:22px; border-radius:50%; display:grid; place-content:center; font-size:12px; color:var(--vscode-descriptionForeground); border:1px solid var(--line); }
.step-body { display:grid; gap:6px; min-width:0; }
.step-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.step-head strong { font-size:13px; font-weight:600; }
.step-body span { color:var(--vscode-descriptionForeground); font-size:12px; line-height:1.5; }
.step-body code { font-family:var(--vscode-editor-font-family,monospace); }
.step-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:4px; }
.status { display:inline-flex; align-items:center; gap:5px; font-size:11px; color:var(--vscode-descriptionForeground); }
.status .ok { color:var(--vscode-foreground); }
.btn { border:1px solid var(--vscode-button-border,transparent); border-radius:4px; background:var(--vscode-button-secondaryBackground,rgba(128,128,128,0.18)); color:var(--vscode-button-secondaryForeground,var(--vscode-foreground)); padding:6px 12px; font-size:13px; }
.btn:hover { background:var(--vscode-button-secondaryHoverBackground,rgba(128,128,128,0.28)); }
.btn.primary { background:var(--vscode-button-background); color:var(--vscode-button-foreground); }
.btn.primary:hover { background:var(--vscode-button-hoverBackground); }
.section-title { font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--vscode-descriptionForeground); margin-bottom:8px; }
.projects { display:flex; flex-direction:column; gap:8px; }
.project { border:1px solid var(--line); border-radius:6px; padding:12px; display:grid; gap:8px; }
.project:hover { border-color:var(--vscode-focusBorder); }
.project strong { font-size:13px; }
.project span { color:var(--vscode-descriptionForeground); font-size:12px; }
.row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.badge { font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.03em; color:var(--vscode-foreground); background:var(--vscode-editorWidget-background,var(--vscode-input-background,transparent)); border:1px solid var(--line); border-radius:4px; padding:2px 7px; }
.mini { border:1px solid var(--vscode-button-border,transparent); border-radius:4px; background:var(--vscode-button-secondaryBackground,rgba(128,128,128,0.18)); color:var(--vscode-button-secondaryForeground,var(--vscode-foreground)); padding:5px 10px; font-size:12px; }
.mini:hover { background:var(--vscode-button-secondaryHoverBackground,rgba(128,128,128,0.28)); }
.empty { border:1px dashed var(--line); border-radius:6px; padding:16px; color:var(--vscode-descriptionForeground); font-size:12px; }
.toast { position:fixed; left:50%; bottom:22px; transform:translateX(-50%); background:var(--vscode-notifications-background,var(--vscode-editorWidget-background)); color:var(--vscode-notifications-foreground,var(--vscode-foreground)); border:1px solid var(--vscode-notifications-border,var(--line)); border-radius:6px; padding:8px 12px; font-size:12px; opacity:0; transition:opacity .18s; }
.toast.show { opacity:1; }
`;
document.head.appendChild(style);

const app = document.querySelector<HTMLElement>("#app")!;
let currentState: HomeStateMessage | null = null;
let busy = false;

function send(message: HomeWebviewMessage): void {
  vscode.postMessage(message);
}

function render(): void {
  const state = currentState;
  const checking = !state;
  const connected = state?.status === "connected";
  const backend = state?.backendUrl ?? "http://127.0.0.1:8000";
  const projects = state?.projects ?? [];
  const backendMode = state?.backendMode ?? "stopped";
  const mcp = state?.agentMcp;

  const backendBadge = checking ? `<span class="status">checking...</span>`
    : connected ? `<span class="status"><span class="ok">running</span></span>`
    : `<span class="status">stopped</span>`;
  const backendCtl = connected
    ? (backendMode === "managed"
      ? `<button class="btn" data-action="stop-backend">Stop backend</button>`
      : "")
    : `<button class="btn primary" data-action="start-backend">Start backend</button><button class="btn" data-action="retry">Retry</button>`;
  const backendDesc = connected
    ? `Connected - ${escapeHtml(backend)}${backendMode === "managed" ? " - managed by this extension" : backendMode === "external" ? " - existing backend" : ""}`
    : `AIENG needs its backend running to build and store CAD - ${escapeHtml(backend)}`;

  const mcpReady = !!mcp?.configured;
  const mcpBadge = !mcp ? `<span class="status">checking...</span>`
    : mcpReady ? `<span class="status"><span class="ok">ready</span></span>`
    : `<span class="status">not found</span>`;
  const mcpDesc = mcpReady
    ? escapeHtml(mcp!.detail)
    : `Your agent (Claude Code / Codex) needs the AIENG tools. Add the <b>aieng-workbench</b> MCP server - see <code>.mcp.json</code> in the repo root - then reopen your agent.`;

  app.innerHTML = `<div class="page ${busy ? "busy" : ""}">
    <section class="hero">
      <div>
        <div class="eyebrow">AIENG</div>
        <h1>Model CAD with your AI agent, right in VS Code</h1>
        <p>Open the workbench, then ask your agent to build. It models through AIENG's tools and the 3D preview updates live. No separate app to juggle.</p>
      </div>
    </section>

    <section class="steps">
      <div class="step">
        <div class="step-n">1</div>
        <div class="step-body">
          <div class="step-head"><strong>Start the backend</strong> ${backendBadge}</div>
          <span>${backendDesc}</span>
          ${backendCtl ? `<div class="step-actions">${backendCtl}</div>` : ""}
        </div>
      </div>
      <div class="step">
        <div class="step-n">2</div>
        <div class="step-body">
          <div class="step-head"><strong>Connect your agent</strong> ${mcpBadge}</div>
          <span>${mcpDesc}</span>
        </div>
      </div>
      <div class="step">
        <div class="step-n">3</div>
        <div class="step-body">
          <div class="step-head"><strong>Create a project, then ask your agent</strong></div>
          <span>Open a project, click <b>Build</b> in the preview toolbar, and paste it into your agent chat.</span>
          <div class="step-actions">
            <button class="btn primary" data-action="create">Start new project</button>
            <button class="btn" data-action="open-live">Open existing</button>
            <button class="btn" data-action="open-package">Open .aieng file</button>
          </div>
        </div>
      </div>
    </section>

    <section class="projects">
      <div class="section-title">Recent projects</div>
      ${projects.length ? projects.map(renderProject).join("") : renderEmpty(connected ? "connected" : "unreachable")}
    </section>
    <div class="toast"></div>
  </div>`;
  bind();
}

function renderProject(project: HomeProject): string {
  const parts = project.namedParts.length ? `${project.namedParts.slice(0, 4).join(", ")}${project.namedParts.length > 4 ? "..." : ""}` : "No named parts yet";
  return `<article class="project">
    <div class="row"><strong>${escapeHtml(project.name)}</strong><span class="badge">${escapeHtml(project.status ?? "unknown")}</span></div>
    <span>${escapeHtml(project.id)} - ${escapeHtml(parts)}</span>
    <div class="row">
      <button class="mini" data-action="open-project" data-project="${escapeAttr(project.id)}">Open workbench</button>
    </div>
  </article>`;
}

function renderEmpty(status: string): string {
  if (status === "connected") {
    return `<div class="empty">No projects yet. Start a blank AIENG project, then ask your VS Code agent to generate the first CAD model.</div>`;
  }
  return `<div class="empty">Start the AIENG backend from this panel, or start your own backend separately and retry the connection.</div>`;
}

function bind(): void {
  app.querySelector<HTMLElement>('[data-action="create"]')?.addEventListener("click", () => send({ kind: "createProject" }));
  app.querySelector<HTMLElement>('[data-action="open-live"]')?.addEventListener("click", () => send({ kind: "openLiveProject" }));
  app.querySelector<HTMLElement>('[data-action="open-package"]')?.addEventListener("click", () => send({ kind: "openPackage" }));
  app.querySelector<HTMLElement>('[data-action="start-backend"]')?.addEventListener("click", () => send({ kind: "startBackend" }));
  app.querySelector<HTMLElement>('[data-action="stop-backend"]')?.addEventListener("click", () => send({ kind: "stopBackend" }));
  app.querySelector<HTMLElement>('[data-action="retry"]')?.addEventListener("click", () => send({ kind: "retry" }));
  app.querySelectorAll<HTMLElement>("[data-project]").forEach((element) => {
    element.addEventListener("click", () => {
      const projectId = element.dataset.project ?? "";
      if (element.dataset.action === "open-project") send({ kind: "openLiveProject", projectId });
    });
  });
}

function showToast(detail: string, tone: "info" | "error" = "info"): void {
  const toast = app.querySelector<HTMLElement>(".toast");
  if (!toast) return;
  toast.textContent = detail;
  toast.style.background = tone === "error" ? "var(--vscode-inputValidation-errorBackground, var(--vscode-errorForeground))" : "";
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1600);
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}

function escapeAttr(value: string): string {
  return escapeHtml(value);
}

window.addEventListener("message", (event: MessageEvent<HomeToWebviewMessage>) => {
  if (event.data.kind === "homeState") {
    currentState = event.data;
    render();
  }
  if (event.data.kind === "homeBusy") {
    busy = event.data.busy;
    render();
    if (event.data.detail) showToast(event.data.detail);
  }
  if (event.data.kind === "homeToast") showToast(event.data.detail, event.data.tone);
});

render();
send({ kind: "ready" });
