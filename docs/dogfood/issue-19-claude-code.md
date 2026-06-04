# Claude Code MCP Dogfood Report — Issue #19

Date: 2026-06-04
Agent: Claude Code (via VSCode extension)
Workbench: aieng-workbench MCP server

## Summary

Claude Code successfully completed the main MCP-first dogfood flow against the local Workbench.

## What worked

- Claude Code connected to `aieng-workbench` via the repo `.mcp.json`.
- Read-only onboarding/context worked:
  - `aieng_agent_readme`
  - `aieng_list_projects`
  - `aieng_agent_context`
- Project used: `f6ea8c666dde`.
- Initial project was `Codex Verify Drone`.
- `cad_execute_build123d` was used with `mode="replace"`.
- The old drone geometry was replaced with a CNC mounting bracket.
- Workbench approval appeared and was approved by the human.
- CAD generation succeeded and the viewer showed the bracket.
- Face picking worked:
  - picked face: `@face:face_007`
  - resolved as base plate front side face
  - normal: `+Y`
  - area: approximately `1,120 mm^2`
- Minimal illustrative CAE setup/preflight worked:
  - fixed support: `@face:face_005`
  - lateral pressure/load face: `@face:face_007`
  - illustrative aluminum-like material
  - illustrative lateral pressure: `0.5 MPa`
- Setup artifacts were written.
- Preflight returned `ready_to_run=false` with actionable missing items.

## Not run / not claimed

- Solver was intentionally not run.
- No production-grade engineering validity is claimed.
- Mesh generation and full solver execution were not tested.

## Gaps found

1. **Approval timeout coordination**
   - The first gated CAD call timed out.
   - The agent could not tell whether the approval UI was visible, missed, or never surfaced.
   - Follow-up: expose clearer approval state and pending approval hints.

2. **Stale/broken project discovery**
   - A newer `flange_80mm_01` project surfaced during discovery but returned 404.
   - Follow-up: hide stale entries or mark broken projects clearly in project discovery.

3. **CAE setup patch ergonomics**
   - `cae_apply_setup_patch` required custom fields such as `action_type` and `content`.
   - This was not obvious from the agent-facing tool description.
   - Follow-up: add examples and clearer schema documentation.

4. **CAE artifact orchestration**
   - Materials, loads, BCs, and solver settings were written, but preflight still required mesh files, load case JSON, solver input deck, and `ccx` on PATH.
   - Follow-up: add a guided minimal linear-static setup workflow or make preflight return recommended next MCP tool calls.

5. **Face pointer validation**
   - CAE setup accepted `face_005` and `face_007`.
   - If topology changes later, these IDs may become stale.
   - Follow-up: validate CAE face references against the current topology map and store a topology revision/hash.

## Verdict

The MCP-first direction is validated for the main local CAD workflow:

`external agent -> MCP -> Workbench approval -> CAD generation -> viewer -> face picking -> CAE setup/preflight`

Remaining work is mostly around approval UX, project discovery hygiene, and making CAE setup less fragmented for external agents.
