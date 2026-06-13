# MCP client compatibility matrix (#180)

Tested/documented compatibility for the external-agent MCP clients expected to
connect to the **AIENG Workbench** MCP server. Companion to
[`MCP_SETUP.md`](../MCP_SETUP.md), which holds the full connect-your-agent
snippets; this file records *what actually works per client* — transport,
prompt/resource visibility, approval behavior, and known limitations.

> **Honesty boundary.** Only the **Claude Code stdio** path was exercised live
> while writing this (see the captured evidence below). The Codex and
> Cursor/VS Code rows are documented from the **committed configs** in this repo
> and the clients' published MCP support; they are marked **documented, not
> verified this session** and must not be read as a tested guarantee. Re-run the
> per-client smoke (below) on the target client to promote a row to *verified*.

## Matrix

| Client | Config (in repo) | Transport(s) | Prompts / resources | Approval behavior | Status |
|---|---|---|---|---|---|
| **Claude Code** | `.mcp.json` (project root) ✅ committed | **stdio** (verified); HTTP/SSE via Docker tier (documented) | Tool list + onboarding **verified live**; server also registers MCP prompts/resources | **client-managed** (`--approval-mode client`); native `AskUserQuestion` for the plan-confirm boundary; also supports `managed` (viewer card) and `block` | ✅ **Verified this session** (stdio) |
| **OpenAI Codex** | `.codex/config.toml` `[mcp_servers.aieng-workbench]` — committed as a template; the live config is **global** at `~/.codex/config.toml` | **stdio** (documented) | Tools supported by Codex MCP; prompt/resource surfacing depends on Codex version — not verified | **client-managed**; native `request_user_input` for plan-confirm; fallback `cad.confirm_modeling_plan` | 📄 Documented, not verified this session |
| **Cursor / VS Code (+ Copilot, Cline)** | `.vscode/mcp.json` (`type: "stdio"`) ✅ committed; Cursor/Cline reuse it | **stdio** (documented); HTTP/SSE via Docker tier | Per-client; VS Code/Copilot MCP support is still evolving — not verified | **client-managed**; no guaranteed native question tool → falls back to `cad.confirm_modeling_plan` (the client's permission dialog) | 📄 Documented, not verified this session |

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
| **managed viewer** | `--approval-mode managed --backend-url …` (`AIENG_MCP_MANAGED_APPROVAL=1`) | The running backend/viewer owns approval via its approval card. **Fails safe**: with no viewer connected, gated calls return `approval_surface_unavailable` rather than hanging. |
| **hard-block** | `--approval-mode block` (`AIENG_MCP_BLOCK_APPROVAL_TOOLS=1`) | Inspection-only: all mutating tools (incl. plan-boundary CAD authoring) are blocked at the server; read-only tools still run. |

## Per-client smoke (promote a row to *verified*)

On the target client, after wiring the config from `MCP_SETUP.md`:

1. Ask the client to **list the aieng-workbench tools** → expect the canonical
   names (`aieng.agent_readme`, `aieng.list_projects`, `cad.execute_build123d`,
   `cae.prepare_solver_run`, …) and a non-zero tool count.
2. Call `aieng.agent_readme` → expect the onboarding text + `version_surface`.
3. Trigger an approval-gated call (e.g. a `cad.execute_build123d` plan) → expect
   the client's approval surface to fire (client-managed), or the managed/blocked
   behavior for those modes.
4. Record transport, prompt/resource visibility, and approval behavior; update
   the matrix row + its status.

## Known limitations

- **Codex** MCP config is **global**, not project-scoped — `cwd` must be the
  absolute path to your clone (the committed `.codex/config.toml` is a template).
- **VS Code / Copilot** MCP support is evolving across versions; if stdio
  discovery is flaky, use the Docker HTTP/SSE tier.
- Only Claude Code stdio is verified here. The matrix does **not** claim an
  untested client path works — run the smoke above to verify.
- Hosted / web-AI / OAuth connection modes are **out of scope** for this matrix.
