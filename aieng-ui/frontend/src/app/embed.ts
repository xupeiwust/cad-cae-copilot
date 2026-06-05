// Embed mode: the workbench is rendered inside the VS Code extension's webview
// (an <iframe> pointing at the backend-served SPA). The extension passes
// `?embed=vscode&project=<id>` so the app can preselect the project and slim its
// chrome to fit a side panel. In the plain browser these helpers return defaults.

function params(): URLSearchParams | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search);
}

export function isEmbedMode(): boolean {
  return params()?.get("embed") === "vscode";
}

export function requestedProjectId(): string | null {
  return params()?.get("project") ?? null;
}
