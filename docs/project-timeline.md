# Project Timeline

The workbench Project timeline panel is a read-only audit surface for a selected
project. It merges existing runtime data into one scannable history:

- runtime runs for the current project,
- runtime events such as approval requested / granted / rejected,
- tool result receipts when present,
- artifact paths written or referenced by receipts,
- advisory next actions returned by tools.

## Boundaries

- The panel never executes CAD, CAE, solver, or approval actions.
- Next actions are displayed as copy-only hints. They are not buttons and do not
  advance the workflow by themselves.
- Artifact paths are traceability links for humans and agents; their presence is
  not proof that a solver ran.
- Solver-result claims remain bounded by solver-run evidence such as completed
  `simulation/runs/*/solver_run.json` metadata and the normalized
  `results/result_summary.json#result_contract` block.

## Failure behavior

Missing historical runs, malformed receipts, or absent next-action fields degrade
to an empty or partial timeline. They must not block the viewer, CAD preview,
approval surface, or MCP-first workflow.
