# One-prompt agent setup

This page gives a copy-paste prompt for an MCP-capable agent to bring up the
packaged AIENG Workbench, verify the MCP connection, and report whether the
system is ready for agent-driven CAD/CAE work.

Target path:

```text
Docker image + AIENG Workbench + MCP-over-HTTP/SSE + your MCP-capable agent
```

This is the supported quick-start path for trying the packaged workbench. It is
not a guarantee for local source builds, conda installs, unsupported MCP
clients, production certification, or automatic solver execution.

## Prerequisites

- Docker is installed and can run Linux containers.
- Port `8000` is free for the workbench UI.
- Port `8765` is free for the MCP-over-HTTP/SSE endpoint.
- The MCP client can connect to HTTP/SSE servers.
- The user has access to the published image:
  `ghcr.io/armpro24-blip/aieng-workbench:latest`.

Optional:

- VS Code extension / VSIX installed for editor-native preview and approval.
- A clean workspace where the agent can record the evidence packet.

## Copy-paste prompt

Paste this into your MCP-capable agent:

```text
Set up AIENG Workbench through the packaged Docker path and verify that it is
ready for MCP-driven CAD/CAE work.

Use these constraints:
- Prefer the published Docker image:
  ghcr.io/armpro24-blip/aieng-workbench:latest
- Do not use a source checkout or conda environment unless Docker is unavailable.
- Do not run a solver.
- Do not claim production certification.
- Treat CAD creation as optional smoke verification only after the workbench and
  MCP endpoint are healthy.

Steps:
1. Check that Docker is installed and can run containers.
2. Check whether ports 8000 and 8765 are already in use. If either is busy, tell
   me the conflict and suggest safe alternative port mappings instead of killing
   any process.
3. Pull the published image.
4. Start the workbench with a named data volume:
   docker run --rm -it -p 8000:8000 -p 8765:8765 -v aieng-data:/data ghcr.io/armpro24-blip/aieng-workbench:latest
5. Verify that the web workbench is reachable at:
   http://localhost:8000/app/
6. Verify that the MCP endpoint is reachable at:
   http://localhost:8765/sse
7. Configure or remind me how to configure my MCP client to connect to that SSE
   endpoint.
8. Through MCP, call:
   aieng.agent_readme
   aieng.list_projects
   and, if a project exists:
   aieng.agent_context { project_id }
9. Report the result as:
   - backend health
   - MCP endpoint health
   - visible tool count or tool names
   - onboarding call result
   - approval mode / approval surface
   - data volume persistence path
   - any blocker with one concrete next action

Optional smoke, only if I explicitly approve it:
- Create or select a project.
- Use MCP to create a small CAD model.
- Confirm the approval surface appears for gated CAD actions.
- Confirm the viewer refreshes.
- Copy one stable @face:* pointer if available.

Keep the report evidence-based. If a check was not performed, mark it
"not checked" rather than guessing.
```

## Expected healthy result

A successful setup should show:

- Workbench UI reachable at `http://localhost:8000/app/`.
- MCP-over-HTTP/SSE reachable at `http://localhost:8765/sse`.
- MCP tools visible to the connected agent, including `aieng.agent_readme`,
  `aieng.list_projects`, and `cad.execute_build123d`.
- Managed approval enabled for the packaged viewer path.
- Projects and `.aieng` packages stored under the `aieng-data` Docker volume.

If the optional CAD smoke is run, it should additionally show:

- a generated model in the workbench viewer,
- STEP/STL/GLB or preview artifacts,
- named parts or source metadata when the generated model provides them,
- and, when topology mapping is available, stable `@face:*` pointers.

## Evidence packet

When recording a dogfood run, capture:

- date, OS, Docker version, image tag or digest,
- the exact Docker command and port mapping,
- backend health result,
- MCP endpoint result,
- MCP client name and version,
- tool visibility / onboarding output summary,
- approval behavior observed,
- screenshot or short recording of the running workbench,
- optional generated project/package if CAD smoke was run,
- blockers or failure modes.

This evidence is useful for release gates and for updating the MCP compatibility
matrix. Do not promote a client path from "documented" to "verified" without
real client-side evidence.

## Troubleshooting

| Symptom | Likely cause | Next action |
|---|---|---|
| Docker command fails before pulling | Docker not installed, not running, or no registry access | Start Docker Desktop or verify registry access, then retry. |
| Port `8000` or `8765` is busy | Another local service is using the port | Choose explicit alternative mappings and update the MCP URL accordingly. |
| Workbench UI opens but no projects show | Backend URL / port mapping mismatch | Use the same host/port mapping for the UI and backend API. |
| MCP client cannot see tools | Client is not connected to the SSE endpoint or does not support that transport | Recheck the client MCP config; try stdio config from `aieng-ui/backend/MCP_SETUP.md` if SSE is unsupported. |
| Approval-gated CAD action fails | No approval surface is available or the request was denied | Open the workbench/extension approval surface and retry only after reviewing the plan. |
| Viewer is blank | No CAD model has been generated yet, or the preview asset failed | Run a small CAD smoke only after MCP health is confirmed; inspect backend logs if a preview artifact is missing. |

## Related docs

- [MCP-first VS Code workflow](mcp-first-vscode-workflow.md)
- [MCP setup by client](../aieng-ui/backend/MCP_SETUP.md)
- [MCP client compatibility matrix](../aieng-ui/backend/docs/mcp_client_compatibility.md)
