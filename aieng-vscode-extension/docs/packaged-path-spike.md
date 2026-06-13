# VS Code extension packaged-path spike (#184)

Can the `aieng-cad-preview` VS Code extension connect to the **packaged** Docker /
installed-MCP distribution instead of assuming a repository checkout? This spike
answers from code inspection of `aieng-vscode-extension/` against the existing
distribution story (`MCP_SETUP.md`, the Docker all-in-one image).

> **Method note.** This is a **code-analysis** spike — it does not run the
> extension in VS Code against a container. Runtime validation is the proposed
> next slice (§6). Findings below are derived from the extension source and the
> packaged backend's known surface.

## Verdict: **GO** (low-effort packaged path already ~90% present)

The extension's data path is **already `backendUrl`-based** (HTTP + SSE) with an
explicit **`external`** backend mode. Pointing `aieng.backendUrl` at a running
**Docker all-in-one** backend makes the extension work with **no repo checkout
and no conda env**. The repo-checkout/conda assumption is isolated to one
*optional* convenience (the managed-spawn). The remaining work is docs/config and
a runtime validation pass — not an architecture change.

## 1. Current repo-checkout assumptions

| Surface | File | Repo-dependent? |
|---|---|---|
| **Managed-spawn backend** ("Start AIENG Backend") | `src/backendManager.ts` | **Yes.** Spawns `conda run -n aieng311 … python -m uvicorn app.main:app …` (configurable via `aieng.backendStartCommand` / `aieng.backendStartArgs`) with `cwd` resolved by scanning the workspace for `aieng-ui/backend/app/main.py` (`aieng.backendCwd` overrides). `start()` throws "Could not find aieng-ui/backend in the current VS Code workspace" when absent. This is the **only** path that assumes a clone + conda env. |
| Project list / create | `src/livePreview.ts` | No — `fetch(${backendUrl()}${path})`. |
| Live activity follow | `src/agentActivity.ts` | No — `EventSource(${backendUrl()}/api/agent-activity/stream)`. |
| Embedded viewer | `src/webview.ts` | No — iframe `src = ${backendUrl}/app/?project=…&embed=vscode` (CSP `frame-src ${backendUrl}`). |
| MCP status hint | `src/mcpStatus.ts` (`detectAgentMcp`) | No — informational. |

`aieng.backendUrl` defaults to `http://127.0.0.1:8000`. The home panel already
distinguishes **`external`** ("Connected to existing backend") from **`managed`**
(`src/homePanel.ts`): if a backend is already reachable, the extension uses it and
does **not** spawn or stop it (confirmed by the README "Backend lifecycle"
section). So *external mode is a first-class, already-implemented path.*

## 2. Docker all-in-one connection path

The Docker image serves backend + built viewer at `:8000` and MCP HTTP/SSE at
`:8765`, with `AIENG_MCP_MANAGED_APPROVAL=1`. Proposed user setup (no clone):

```bash
docker run --rm -it -p 8000:8000 -p 8765:8765 -v aieng-data:/data \
  ghcr.io/armpro24-blip/aieng-workbench:latest
```
then in VS Code settings: `"aieng.backendUrl": "http://127.0.0.1:8000"` and run
**AIENG: Open AIENG Home** (do **not** click "Start AIENG Backend").

**Compatibility analysis — expected to work as-is:**
- Project list/create → `GET/POST :8000/api/projects` (served by the container).
- Live follow → `:8000/api/agent-activity/stream` SSE (served).
- Embedded viewer → iframe `:8000/app/?embed=vscode` (the container serves the
  built React viewer at `/app/`).

**No blocker found in the connection design.** The only friction is UX: the home
panel surfaces "Start AIENG Backend", which is meaningless/misleading against
Docker (it would try the conda spawn and fail). See §6.

## 3. Installed MCP / backend path

- **Headless stdio MCP (`uvx aieng-workbench-mcp`)** serves **no HTTP backend and
  no viewer** — it is a stdio MCP server for an *agent*. The extension needs the
  HTTP API (`/api/projects`, `/api/agent-activity/stream`) and the `/app/` viewer.
  **Blocker (by design):** the pure stdio-MCP install is **insufficient** for this
  extension. The extension is a viewer/preview surface, not an MCP agent.
- **Installed full backend + viewer** — running `uvicorn app.main:app` from the
  installed `aieng-workbench-mcp` (or the Docker tier) provides `:8000` + `/app/`,
  which the extension consumes via external mode exactly like Docker.

**Conclusion:** the packaged path for this extension is **Docker all-in-one** (or
an equivalently-running full backend), *not* the headless stdio-MCP install.

## 4. Viewer/preview & approval behavior (packaged path)

- **Viewer:** native VS Code webview hosting an **iframe** of the container's
  `/app/?project=…&embed=vscode`. The embed flag is already handled by the viewer
  (the frontend reads `requestedProjectId()` / `embed`). Preview auto-opens/follows
  from the agent-activity SSE stream (`aieng.autoOpenPreviewOnActivity`).
- **Preview refresh:** SSE `project_id` events drive open/follow; the SSE client
  retries if the backend starts after VS Code — works whether the backend is
  Docker or local.
- **Approval:** the container runs **managed approval** (`AIENG_MCP_MANAGED_APPROVAL=1`),
  so approval-gated tools surface as approval cards **inside the workbench viewer**
  (the embedded iframe), resolvable there. The extension itself does not drive
  tools — the user's external MCP agent (Claude Code / Codex / Copilot) does — so
  the extension needs no approval logic of its own. (If the user instead runs the
  MCP server in `client` mode, approval is owned by their agent, not the viewer.)

## 5. "Install without cloning" — what must change

| # | Gap | Severity |
|---|-----|----------|
| 1 | Home panel offers "Start AIENG Backend" (conda + repo spawn) as the default remedy when the backend is unreachable; for non-contributors this fails and reads as repo-only. | UX (medium) |
| 2 | No documented "external mode against Docker" setup in the extension README; the Quick Start says "click Start AIENG Backend". | Docs (medium) |
| 3 | The extension `.vsix` is not published (only built locally / `npm run vsix`); "install without cloning" ultimately needs a marketplace listing or release asset. | Distribution (post-alpha, #23) |

None require re-architecting the connection — the external/`backendUrl` path
already exists.

## 6. Recommendation & minimal next slice

**GO** for a post-alpha extension that composes with the packaged distribution.
Minimal next slice (small, mostly docs/UX — no protocol change):

1. **Docs:** add an "Use with Docker (no clone)" section to the extension README —
   `docker run …`, set `aieng.backendUrl=http://127.0.0.1:8000`, open AIENG Home,
   skip "Start AIENG Backend". (Consumes #177's published image.)
2. **UX guard:** when the backend is unreachable, have the home panel recommend
   the Docker/external path first and label "Start AIENG Backend (managed)" as a
   *contributor* affordance (e.g. only when `aieng-ui/backend` is detected in the
   workspace). Optional: detect a reachable `backendUrl` and prefer external mode.
3. **Runtime validation (the part not done in this spike):** build the `.vsix`,
   run it against the Docker all-in-one image, confirm project create + embedded
   viewer iframe + SSE follow + a managed-approval card round-trip. Record results.
4. **Distribution (post-alpha, #23):** publish the `.vsix` (marketplace or release
   asset) so users install without cloning.

## Honesty / non-goals
- No extension release in this spike; no runtime test was performed (code analysis
  only — runtime validation is slice §6.3).
- Does not duplicate the Docker/uvx packaging — it **consumes** it (#177/#141).
- Hosted/OAuth out of scope.
