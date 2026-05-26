# AIENG Technical Roadmap

Status: **v0.46** (Chat-first CAD/CAE Workbench with Simulation Runner)
Last updated: **2026-05-25**

## Current state summary

AIENG is an evidence-grounded CAD/CAE Copilot decision review workbench. The Copilot MVP closed loop is complete, and the chat-first simulation pipeline is now functional end-to-end:

```
Project Health → Design Targets → Computed Metrics → Target Comparison
→ FreeCAD Inspection → Approval-gated CAD Edit → Structural Preflight
→ Approval-gated Solver Run → FRD Extraction → Metrics Refresh
→ Target Comparison Refresh → Copilot Loop Report → Engineering Review Packet
→ Contextual Approval Panels → Workflow Sections → Parametric Template Drafts
-> Explicit Template-to-Design-Targets Handoff
-> Approval-gated Template CAD Fixture Metadata
-> B-Rep Graph (symbolic face/edge/group pointers)
-> AI Preprocessing with B-Rep-aware face selection
-> Gmsh Mesh + CalculiX Solve (approval-gated, SSE streaming)
-> Post-processing Verdict vs Design Targets (FoS, material advisory)
-> Stress Heatmap GLB Visualization
-> Contextual Engineering Chat
-> Engineering Action Plan (intent classification)
```

**Verification baseline:** 563+ backend tests passed, 3 skipped. Frontend build passes.

## Capability map

| Version | Capability | Repo | Issue | Status | Depends on |
|---|---|---|---|---|---|
| v0.35 | Template draft to design targets / setup review handoff | aieng-ui | #14 | ✅ Implemented | v0.34 |
| v0.35.1 | Natural Language Intent Planner v1 | aieng-ui | #23 | ✅ Implemented | v0.35 |
| v0.35.2 | Agent Observation Loop (structured per-action observation + next-action recommender) | aieng-ui | #24 | ✅ Implemented | v0.35.1 |
| v0.36 | CAD Observation v1 (read-only CAD state observer attached to IntentObservation) | aieng-ui | #25 | ✅ Implemented | v0.35.2 |
| v0.37 | AIENG-wrapped FreeCAD MCP Pilot (snapshot import/inspect + exported-geometry registration; no FreeCAD execution) | aieng-ui | #26 | ✅ Implemented | v0.36 |
| v0.38 | B-Rep Graph Engine (symbolic face/edge/group pointer index from topology) | aieng-ui | — | ✅ Implemented | v0.37 |
| v0.39 | AI Preprocessing v2 with B-Rep-aware face selection | aieng-ui | — | ✅ Implemented | v0.38 |
| v0.40 | Simulation Runner (Gmsh mesh + CalculiX solve + FRD parse + atomic write-back) | aieng-ui | — | ✅ Implemented | v0.39 |
| v0.41 | Post-processing Intelligence (FoS advisory, material alternatives, verdict vs targets) | aieng-ui | — | ✅ Implemented | v0.40 |
| v0.42 | Stress Heatmap Visualization (per-node Von Mises GLB from FRD) | aieng-ui | — | ✅ Implemented | v0.40 |
| v0.43 | Contextual Engineering Chat (Claude-powered, grounded in project state) | aieng-ui | — | ✅ Implemented | v0.41 |
| v0.44 | Engineering Action Plan (typed intent classification for chat-first UX) | aieng-ui | — | ✅ Implemented | v0.43 |
| v0.45 | Multi-load-case target comparison | aieng-ui | #17 | 🔜 Planned | v0.41 |
| v0.46 | Batch approval workflow for multiple structural runs | aieng-ui | #18 | 🔜 Planned | v0.45 |
| v0.47 | Review Support Packet v1.1 (downloadable bundle) | aieng-ui | #19 | 🔜 Planned | v0.31 |
| v0.48 | OpenFOAM / CFD adapter radar and safety plan | aieng-ui | #20 | 🔜 Planned | — |
| v0.49 | OpenFOAM preflight-only adapter | aieng-ui | #21 | 🔜 Planned | v0.48 |
| v0.50 | CFD artifact readiness viewer | aieng-ui | #22 | 🔜 Planned | v0.49 |
| v0.51+ | Optional CFD execution fixture | aieng-ui | — | 🔮 Future | v0.50 |

## Dependency graph

```
v0.34 Template authoring drafts
  ├── v0.35 Template → design targets handoff
  │     ├── v0.35.1 Natural Language Intent Planner
  │     │     └── v0.35.2 Agent Observation Loop
  │     │           └── v0.36 CAD Observation v1 (read-only)
  │     │                 └── v0.37 AIENG-wrapped FreeCAD MCP Pilot
  │     │                       └── v0.38 B-Rep Graph Engine
  │     │                             └── v0.39 AI Preprocessing v2 (B-Rep aware)
  │     │                                   └── v0.40 Simulation Runner
  │     │                                         ├── v0.41 Post-processing Intelligence
  │     │                                         │     ├── v0.42 Stress Heatmap GLB
  │     │                                         │     ├── v0.43 Contextual Engineering Chat
  │     │                                         │     ├── v0.44 Engineering Action Plan
  │     │                                         │     └── v0.45 Multi-load-case comparison
  │     │                                         └── v0.46 Batch approval workflow
  │     └── (engineering_template.generate_cad_fixture shipped in v0.34/v0.35
  │         as the controlled geometry-metadata fixture path)
  │
  └── v0.47 Review Packet v1.1 (independent)

v0.30 Structural closed loop (independent)
  └── v0.45 Multi-load-case comparison

v0.48 CFD radar (independent)
  └── v0.49 OpenFOAM preflight
        └── v0.50 CFD artifact viewer
              └── v0.51+ CFD execution (future)
```

## What must not be started too early

1. **Natural Language Intent Planner auto-execution** — v0.35.1 and v0.44 are planning/preview layers only. They must not directly execute CAD/CAE tools, bypass approval gates, or auto-approve mutating steps.
2. **Arbitrary text-to-CAD** — controlled template generation only. Free-form generation requires stronger validation and is out of MVP scope.
3. **OpenFOAM execution** — v0.48–v0.50 are research + preflight + viewer only. No solver execution until v0.51+ and only after structural path is hardened.
4. **Automatic optimization / batch autonomy** — v0.46 requires explicit per-batch approval. No autonomous loop.
5. **Certification language** — never. Claim advancement stays `none`.

## Safety boundaries (all versions)

- Read-only by default.
- Approval-gated for mutation, solver, mesh, CAD edit.
- Missing/unavailable data is honest — never fabricated.
- Claim advancement: `none`.
- External tools are untrusted execution backends behind adapter contract.
