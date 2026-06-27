# Review Handoff Workflow

Status: lightweight collaboration workflow for issue #434. This is not PLM,
access control, or realtime multi-user collaboration. It is the local-first path
for handing an AIENG project to another engineer or MCP-capable agent with
enough evidence context to continue review safely.

## What To Hand Off

Send two artifacts when possible:

1. The project `.aieng` package.
2. The review support packet exported from the Workbench report surface.

The `.aieng` package is the source of package evidence. The review packet is a
human-readable summary that cites package members and makes missing, stale, and
unsupported evidence visible.

## Export

From a running backend, the Workbench report surface uses these read-only /
report-export endpoints:

```text
GET  /api/projects/{project_id}/review-support-packet/preview
POST /api/projects/{project_id}/review-support-packet/export
```

The exported packet should include:

- package identity and key members;
- project health and recommended next actions;
- CAD/CAE evidence present in the package;
- evidence lifecycle counts for current, stale, unsupported, claim-supporting,
  and missing evidence;
- design target comparison when available;
- approval/audit relevant state when present;
- limitations and claim boundary.

## Send

1. Open Mission Control and confirm the package passport matches the project you
   intend to share.
2. Export the review support packet.
3. Send the `.aieng` package plus the review packet.
4. Include this note:

```text
Please inspect the .aieng package evidence before making CAD/CAE claims.
Treat the review packet as a summary, not the source of truth. Missing, stale,
or unsupported evidence should block claims until refreshed or reviewed.
CAD/package mutations, solver execution, and claim advancement remain
approval-gated.
```

## Receive

1. Open the `.aieng` package in AIENG or connect an MCP-capable agent to the
   backend.
2. Read the review packet first to understand package state and open questions.
3. Inspect structured package members before trusting prose summaries:
   - `manifest.json`
   - `geometry/topology_map.json`
   - `graph/feature_graph.json`
   - `simulation/setup.yaml`
   - `results/evidence_index.json`
   - `results/result_summary.json`
   - `results/computed_metrics.json`
   - `validation/evidence_report.json`
   - `ai/claim_map.json`
4. Ask the agent for evidence-backed next steps, not direct mutation.
5. Use the existing approval UI for any CAD edit, package mutation, solver run,
   or claim advancement.

## VS Code Handoff

VS Code Home is the launcher and prompt handoff surface. Use it to copy a
bounded agent prompt for the selected project, then continue detailed evidence
review in the Web Workbench.

The copied prompt should remain bounded to package evidence, approval gates, and
missing-evidence reporting. It should not imply that VS Code has replaced the
Workbench review, approval, or 3D evidence surfaces.

## Honesty Boundary

- A review packet is a summary, not hidden validation.
- Package completeness is not certification.
- Result availability is not design-target satisfaction.
- Design-target satisfaction is not claim advancement.
- Synthetic or fixture evidence must not be reported as a real solver result.
- Existing `.aieng` packages remain readable; handoff docs do not require a
  schema migration.
