# Issue #179 Packaged External-Agent Dogfood Evidence

Date: 2026-06-15
Agent: OpenAI Codex
Published image: `ghcr.io/armpro24-blip/aieng-workbench:latest`
Image digest: `sha256:4592a01d6c53a849437e70105a1982bfa4d68d66aada4cdaa9cd3d1215d17bec`

## Evidence Summary

- Connected to the published Docker image over MCP SSE, outside the maintainer
  source-checkout runtime.
- Observed 74 tools, 6 prompts, and the MCP-first discipline resource.
- Confirmed a real CAD mutation succeeds through the published image's default
  external-client-managed approval path.
- In client-managed mode, built a real build123d bracket through MCP.
- Project `502477adae2e` reached `viewer_ready_glb`.
- Published viewer asset `viewer/model.glb` returned HTTP 200 and was 69,288
  bytes.
- The fixed-image full viewer refreshed on host port `18002`, rendered the
  model, and produced no browser errors.
- Selected a model face in the full viewer, which highlighted and displayed
  `@face:face_013`; clicked **Copy pointer**, then pasted that pointer back into
  the external-agent flow as the CAE load target.
- Agent context independently exposed 16 B-Rep faces and
  `@face:face_003`.
- CAE preflight honestly returned `ready_to_run=false`, listed missing mesh,
  solver settings, and input deck, and returned concrete
  `recommended_next_calls`.
- No solver execution or engineering-validity claim was made.

## Finding And Fix

The packaged viewer defaulted API requests to `http://127.0.0.1:8000`. The SPA
therefore loaded but showed no projects when Docker mapped the backend to a
different host port, for example `-p 18000:8000`.

The frontend now defaults to same-origin API requests. `VITE_API_BASE` remains
available for the Vite development server and deliberately split deployments.

## Reproduction

Run the published image twice:

1. Default external-client-managed mode to exercise a real CAD mutation.
2. Client-managed mode to run the real CAD / viewer-asset / pointer / CAE
   preflight flow.

```powershell
docker run -d --name aieng-issue179-managed -p 18001:8000 -p 18766:8765 `
  ghcr.io/armpro24-blip/aieng-workbench:latest
docker run -d --name aieng-issue179-client -e AIENG_MCP_MANAGED_APPROVAL=0 `
  -p 18000:8000 -p 18765:8765 `
  ghcr.io/armpro24-blip/aieng-workbench:latest
```

Then run:

```powershell
python aieng-ui/backend/scripts/packaged_dogfood.py `
  --managed-mcp-url http://127.0.0.1:18766/sse `
  --client-mcp-url http://127.0.0.1:18765/sse `
  --backend-url http://127.0.0.1:18000 `
  --face-pointer "@face:face_013" `
  --image-digest sha256:4592a01d6c53a849437e70105a1982bfa4d68d66aada4cdaa9cd3d1215d17bec `
  --output docs/dogfood/issue-179-evidence.json
```

The script emits a JSON evidence packet containing discovery counts, approval
behavior, project and asset details, a face pointer, and CAE preflight results.

## Friction Punch-List

- **Fixed:** packaged SPA API requests were pinned to host port `8000`; use
  same-origin requests so arbitrary Docker port mappings work.
- PowerShell callers must quote `@face:...` values when passing them as command
  arguments.
- The published image's default approval behavior is external-client-managed;
  document that distinction prominently for first-time operators.

## Non-Goals

- A real solver was intentionally not run.
- Owner-triggered PyPI publication and release metrics remain outside #179.
