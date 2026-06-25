# Issue #363 packaged one-prompt setup smoke

Date: 2026-06-25

Host: Windows, Docker Desktop / Docker Engine available.

Scope: packaged Docker image + MCP-over-HTTP/SSE health and onboarding smoke.
No CAD model was generated and no solver was run.

## Image and container

- Image: `ghcr.io/armpro24-blip/aieng-workbench:latest`
- Repo digest:
  `ghcr.io/armpro24-blip/aieng-workbench@sha256:0c54cdf3951904ea6772c4deebf19f2b9d1b334ec6d3b0b2e2d68133eaaf0941`
- Local image id:
  `sha256:231414b23e3cc8fdf4f046bd00065f88d695ebeec8c3b38ff39f60b929ce87d0`
- Image created: `2026-06-25T08:41:51.327343511Z`
- Container: `aieng-issue363-smoke`
- Data volume: `aieng-issue363-data`

Default port `8000` was already occupied by a local `aieng311` Python backend, so
the smoke used safe alternate host ports:

```powershell
docker pull ghcr.io/armpro24-blip/aieng-workbench:latest
docker run -d --name aieng-issue363-smoke `
  -p 18000:8000 `
  -p 18765:8765 `
  -v aieng-issue363-data:/data `
  ghcr.io/armpro24-blip/aieng-workbench:latest
```

## Health checks

- Container status: `Up ... (healthy)`.
- Workbench UI: `GET http://localhost:18000/app/` returned `200`.
- MCP SSE endpoint: `GET http://localhost:18765/sse` returned `200 OK`,
  `content-type: text/event-stream`, and an endpoint event.
- Container logs reported:
  - backend started on `0.0.0.0:8000`,
  - MCP HTTP server started on `0.0.0.0:8765`,
  - data volume mounted at `/data`.

The SSE curl check timed out after receiving the endpoint event because SSE is a
long-lived stream. That timeout is expected for a bounded command-line probe.

## MCP tool smoke

Used the installed Python `mcp` client package against:

```text
http://localhost:18765/sse
```

Observed:

- Tool count: `90`.
- Expected HTTP/SSE wire names present:
  - `aieng_agent_readme`
  - `aieng_list_projects`
  - `cad_execute_build123d`
- `aieng_agent_readme` returned onboarding text successfully
  (`isError: false`, 6455 text chars).
- `aieng_list_projects` returned successfully and initially reported an empty
  project list.

Important naming note:

- Calling dotted names such as `aieng.agent_readme` and `aieng.list_projects`
  over the packaged HTTP/SSE path returned `Unknown tool`.
- The current packaged MCP wire names are underscore-based. Docs and prompts
  should tell users to call the names shown by their client.

## Project and persistence smoke

Created one empty project in the isolated Docker volume:

```text
tool: aieng_create_project
name: issue-363-one-prompt-smoke
project_id: 850b362550c6
```

Then:

- `aieng_list_projects` returned the created project.
- `aieng_agent_context { project_id: "850b362550c6" }` returned successfully.
- Restarted the container with `docker restart aieng-issue363-smoke`.
- After restart, the container became healthy again and `aieng_list_projects`
  still returned `issue-363-one-prompt-smoke`.

This verifies that the packaged path can start, expose MCP tools, run onboarding,
create/read a project, and preserve project metadata across a container restart
when a named Docker volume is used.

## Not covered

- No external GUI MCP client was used for this run.
- No VS Code extension approval modal was tested.
- No CAD mutation was approved.
- No viewer refresh after CAD generation was tested.
- No `@face:*` pointer was copied.
- No CAE preflight, mesh generation, or solver run was performed.

These remain required before #363 can be considered fully complete.
