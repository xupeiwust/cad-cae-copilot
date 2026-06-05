# AIENG CAD Preview for VS Code

A lightweight CAD context sidecar for AIENG. It does not host chat or orchestrate MCP tools. It previews models, lets you select authoritative B-Rep faces, and copies stable `@face:id` pointers for pasting into Claude Code, Codex, Copilot Chat, or any other chat surface.

## Features

- Open a local `.aieng` package directly as a read-only custom editor.
- Open a live AIENG Workbench project with `AIENG: Open Live CAD Preview`.
- Refresh live geometry automatically after `viewer_asset_changed` events.
- Orbit, zoom, hover, select, and multi-select mapped faces.
- Copy one face pointer or all selected pointers.
- Clearly disables pointer selection when an authoritative topology mapping is unavailable.

## Local `.aieng` mode

Double-click an `.aieng` file. The extension reads the ZIP package without modifying it and prefers:

1. `geometry/preview.glb`
2. `preview.glb`
3. `viewer/model.glb`
4. corresponding STL fallbacks

Stable face picking requires a GLB preview plus `graph/brep_graph.json` or `geometry/topology_map.json`. STL and packages without topology remain preview-only.

## Live Workbench mode

1. Start the existing AIENG backend.
2. Run `AIENG: Open Live CAD Preview` from the Command Palette.
3. Choose a project.

The default backend URL is `http://127.0.0.1:8000`. Override `aieng.backendUrl` in VS Code settings when needed. Set `aieng.liveProjectId` to skip the project picker.

Live mode uses:

- `GET /api/projects`
- `GET /api/projects/{id}/cad-preview`
- `GET /api/projects/{id}/brep-graph`
- `GET /api/agent-activity/stream`

Backend communication stays in the Extension Host, so the Webview does not depend on permissive CORS configuration.

## Development

```powershell
cd aieng-vscode-extension
npm install
npm run check
npm run build
```

Run `npm run vsix` to produce an installable `.vsix`.
