# MCP client compatibility matrix (#180)

Tested/documented compatibility for the external-agent MCP clients expected to
connect to the **AIENG Workbench** MCP server. Companion to
[`MCP_SETUP.md`](../MCP_SETUP.md), which holds the full connect-your-agent
snippets; this file records *what actually works per client* — transport,
prompt/resource visibility, approval behavior, and known limitations.

> **Honesty boundary.** Only the **Claude Code stdio** path was exercised live
> while writing this (see the captured evidence below). The Codex, Cursor, Cline,
> and VS Code/Copilot rows are documented from the **committed configs** in this
> repo and the clients' published MCP support; they are marked **documented, not
> verified this session** and must not be read as a tested guarantee. Re-run the
> per-client smoke (below) on the target client to promote a row to *verified*.

## Matrix

| Client | Config (in repo) | Transport(s) | Prompts / resources | Approval behavior | Status |
|---|---|---|---|---|---|
| **Claude Code** | `.mcp.json` (project root) ✅ committed | **stdio** (verified); HTTP/SSE via Docker tier (documented) | Tool list + onboarding **verified live**; server also registers MCP prompts/resources | **client-managed** (`--approval-mode client`); native `AskUserQuestion` for the plan-confirm boundary; also supports `managed` (viewer card), `elicit` (headless), and `block` | ✅ **Verified this session** (stdio) |
| **OpenAI Codex** | `.codex/config.toml` `[mcp_servers.aieng-workbench]` — committed as a template; the live config is **global** at `~/.codex/config.toml` (TOML, not JSON) | **stdio** (documented) | Tools supported by Codex MCP; prompt/resource surfacing depends on Codex version — not verified | **client-managed**; native `request_user_input` for plan-confirm; fallback `cad.confirm_modeling_plan`. For headless use `--approval-mode elicit` **only if** the Codex build advertises MCP elicitation (else it fail-safe denies) | 📄 Documented, not verified this session |
| **Cursor** | `.cursor/mcp.json` (project root) ✅ committed; Cursor also reads a global `~/.cursor/mcp.json`. Does **not** read `.vscode/mcp.json` | **stdio** (documented) | Tools supported by Cursor MCP; prompt/resource surfacing version-dependent — not verified | **client-managed**; no guaranteed native question tool → falls back to `cad.confirm_modeling_plan` (Cursor's tool-approval dialog) | 📄 Documented, not verified this session |
| **Cline** (VS Code extension) | Its own `cline_mcp_settings.json` (VS Code globalStorage); does **not** read `.vscode/mcp.json` — copy the server block from `MCP_SETUP.md` | **stdio** (documented) | Tools supported by Cline MCP; prompts/resources not verified | **client-managed**; Cline's per-tool auto-approve/ask dialog; fallback `cad.confirm_modeling_plan` | 📄 Documented, not verified this session |
| **VS Code / GitHub Copilot** | `.vscode/mcp.json` (`servers`, `type: "stdio"`) ✅ committed | **stdio** (documented); HTTP/SSE via Docker tier | Per-client; VS Code/Copilot MCP support is still evolving — not verified | **client-managed**; falls back to `cad.confirm_modeling_plan` (the client's permission dialog) | 📄 Documented, not verified this session |

All three committed configs launch the **same** server over stdio:

```
conda run -n aieng311 --no-capture-output python -m app.mcp_server [--approval-mode client]
```

with `AIENG_BACKEND_URL=http://127.0.0.1:8000`. When the backend is down the
server **falls back to in-process execution** automatically, so tools still work
(no live viewer) — this is the headless tier-1 path.

## Captured evidence — Claude Code (stdio), this session

`aieng.agent_readme` called over the `.mcp.json` stdio connection returned:

- **74 registered tools** (`registry.tool_count: 74`, `registry_hash` present) →
  tool listing works.
- The full **onboarding quickstart** text → prompt/guide content is visible to
  the client.
- **Version surface** `aieng.version_surface.v1`, `mcp_tool_surface` version
  `0.1.0-alpha.1` (policy `unstable`) → the compatibility contract is reachable.
- Returned **with the backend (port 8000) not running** → in-process fallback
  confirmed (headless tier-1).

This exercises acceptance items: external client connects (stdio), tool list
visible, onboarding/prompt visible. CAD-mutation/approval and viewer-refresh on
the *packaged* path remain the dogfood scope of #143 / #179.

## Transports

| Transport | When | Clients |
|---|---|---|
| **stdio** | Default. The client spawns `python -m app.mcp_server`. | Claude Code, Codex, Cursor/VS Code (all committed configs) |
| **HTTP / SSE** | Multi-client / debugging, and the **Docker all-in-one** tier (container exposes the MCP endpoint). | Any HTTP/SSE-capable MCP client; see Docker section of `MCP_SETUP.md` |

## Approval modes (server `--approval-mode`)

| Mode | Flag / env | Behavior |
|---|---|---|
| **client-managed** | `--approval-mode client` (default in committed configs) | The MCP client owns approval (its permission dialog / native question tool). |
| **managed viewer** | `--approval-mode managed --backend-url …` (`AIENG_MCP_MANAGED_APPROVAL=1`) | The running backend/viewer owns approval via its approval card. The surface can be the **web workbench** *or* the **VS Code extension** (#230), which renders each request as a native in-editor modal and resolves it. **Fails safe**: with no surface connected, gated calls return `approval_surface_unavailable` rather than hanging. |
| **elicit (headless)** | `--approval-mode elicit` (`AIENG_MCP_APPROVAL_MODE=elicit`) | The server prompts the human through **MCP client elicitation** — no workbench viewer needed. Requires the client to advertise the `elicitation` capability; if it does not, gated tools **fail safe** (`behavior: deny`, `code: approval_surface_unavailable`). Per-client elicitation support is version-dependent and **not verified here** — confirm with the smoke below before relying on it. |
| **hard-block** | `--approval-mode block` (`AIENG_MCP_BLOCK_APPROVAL_TOOLS=1`) | Inspection-only: all mutating tools (incl. plan-boundary CAD authoring) are blocked at the server; read-only tools still run. |

## Per-client smoke (promote a row to *verified*)

On the target client, after wiring the config from `MCP_SETUP.md`:

0. **Pre-flight the wiring** (client-agnostic): from the repo root run
   `aieng-workbench-mcp --doctor` (or `--doctor --backend-url http://127.0.0.1:8000`).
   It confirms an MCP config references `aieng-workbench`, the backend is reachable
   (if a URL is given), and the tool set is non-empty — with fix hints. A clean
   `OK`/`WARN` (exit 0) means the server side is wired before you test the client.
1. Ask the client to **list the aieng-workbench tools** → expect the wire names
   exposed by that client and a non-zero tool count. On the packaged HTTP/SSE
   path, the observed wire names use underscores, for example
   `aieng_agent_readme`, `aieng_list_projects`, `cad_execute_build123d`, and
   `cae_prepare_solver_run`. Dotted names such as `aieng.agent_readme` may appear
   in human-facing guides as family labels, but they are not the HTTP/SSE wire
   names in the current packaged image.
2. Call the onboarding tool (`aieng_agent_readme` on the HTTP/SSE path) → expect
   the onboarding text + `version_surface`.
3. Trigger an approval-gated call (e.g. a `cad.execute_build123d` plan) → expect
   the client's approval surface to fire (client-managed), or the managed/blocked
   behavior for those modes.
4. Record transport, prompt/resource visibility, and approval behavior; update
   the matrix row + its status.

## Known limitations

- **Codex** MCP config is **global**, not project-scoped — `cwd` must be the
  absolute path to your clone (the committed `.codex/config.toml` is a template).
- **Cursor** reads `.cursor/mcp.json` (committed here) or a global
  `~/.cursor/mcp.json`; it does **not** read `.vscode/mcp.json`. If a project-root
  `cwd` is not honored, set it to the absolute path of `aieng-ui/backend`.
- **Cline** is a VS Code extension that reads **its own** `cline_mcp_settings.json`
  (in VS Code globalStorage), not `.vscode/mcp.json` — copy the server block from
  `MCP_SETUP.md` into Cline's MCP settings.
- **VS Code / Copilot** MCP support is evolving across versions; if stdio
  discovery is flaky, use the Docker HTTP/SSE tier.
- **Headless approval (`--approval-mode elicit`)** depends on the client
  advertising the MCP `elicitation` capability; clients without it get a
  fail-safe deny, not a silent execution. This is version-dependent per client
  and is not verified here.
- Only Claude Code stdio is verified here. The matrix does **not** claim an
  untested client path works — run the smoke above to verify.
- Hosted / web-AI / OAuth connection modes are **out of scope** for this matrix.
