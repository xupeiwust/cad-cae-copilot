# .aieng Package Handoff Runbook

Status: lightweight handoff path for issue #437. This runbook explains how to
send an AIENG project to another engineer or MCP-capable agent while preserving
the evidence context that makes the package reviewable.

## Purpose

An `.aieng` package is the portable engineering evidence layer for AIENG. It is
not a CAD kernel, solver, PLM database, or certification stamp. It carries the
artifacts another reviewer needs to understand what exists, what is missing,
what is stale, what was approved, and which engineering claims remain
unsupported.

Use this handoff whenever a project moves from one person, agent, or machine to
another.

## Send

1. Open the project in the Workbench and review Mission Control.
2. Confirm the package passport shows the expected geometry, CAE setup, result,
   provenance, claim-boundary, and handoff-summary members.
3. Export or share the project `.aieng` package.
4. If review context is needed, also export the review support packet from the
   Workbench report surface.
5. Send both files with a short note that package evidence is advisory until a
   reviewer confirms the relevant artifacts.

## Receive

1. Open the `.aieng` package in the Workbench or connect an MCP-capable agent to
   the backend.
2. Ask the agent to inspect package evidence before proposing CAD or CAE work.
3. Verify these package members first when present:
   - `manifest.json`
   - `geometry/topology_map.json`
   - `graph/feature_graph.json`
   - `simulation/setup.yaml`
   - `simulation/cae_mapping.json`
   - `results/evidence_index.json`
   - `results/result_summary.json`
   - `results/computed_metrics.json`
   - `provenance/tool_trace.json`
   - `validation/evidence_report.json`
   - `ai/claim_map.json`
   - `README_FOR_AI.md`
   - `ai/summary.md`
4. Treat missing, stale, or unsupported evidence as a blocker for claims, not as
   permission to infer the missing result.
5. Use the existing approval gates for CAD mutation, package mutation, solver
   execution, and claim advancement.

## Safe Agent Prompt

```text
Use the aieng-workbench MCP tools to inspect this .aieng package before making
CAD or CAE claims. Start with the package context and evidence members:
manifest, geometry/topology, feature graph, CAE setup, result evidence,
computed metrics, provenance, validation/evidence reports, and claim map.

Summarize what evidence exists, what is missing, what appears stale, and which
claims are unsupported. Do not mutate CAD, mutate the package, run solver tools,
or advance engineering claims unless AIENG approval gates explicitly allow it.
Report only evidence-backed facts and call out missing evidence.
```

## Honesty Boundary

- Package completeness is not certification.
- A solver preflight is not solver execution.
- A synthetic or fallback field is not real solver evidence.
- A result artifact is evidence, not automatic claim advancement.
- A handoff summary is derived context; structured package members remain the
  source to inspect.

## Verification

For a handoff demo, the receiver should be able to answer:

- What geometry evidence is inside the package?
- Is CAE setup present, and which required inputs are missing?
- Are solver result artifacts present, and are they real or fallback evidence?
- Which claims cite evidence, and which claims remain unadvanced?
- Which next action is safe under the current approval and evidence state?
