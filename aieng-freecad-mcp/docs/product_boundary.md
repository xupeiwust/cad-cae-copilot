# Product Boundary

## Definition

`aieng-freecad-mcp` is a composable FreeCAD MCP execution interface for CAD/CAE operations.

It is not an autonomous CAD/CAE workflow engine.

## Core Principle

FreeCAD MCP performs controlled CAD/CAE execution. `.aieng` carries semantic state, constraints, evidence, provenance, references, missingness, unsupported states, and claim status.

`.aieng` is an enhancer, not a hard dependency.

## Responsibilities

| Layer | Responsibility |
|---|---|
| `.aieng` package | Semantic resources, constraints, references, evidence, provenance, claim map |
| FreeCAD MCP | Controlled execution adapter, optional `.aieng` context use, evidence/trace writeback |
| FreeCAD / CAE tools | Modeling, meshing, solving, result generation |
| Agent/caller | Chooses tool order, requests bounded operations, requests claim updates |

## Modes

Standalone mode:

- No `.aieng` required.
- Tools run from explicit inputs.
- Evidence can be returned but package persistence does not occur.
- Claims are not advanced.

`.aieng`-enhanced mode:

- Uses package context (task, graph, constraints, references, evidence, claims).
- Applies guards and rejects unsupported/protected operations.
- Can persist evidence and trace.
- Supports explicit evidence-backed claim updates.

## CAD / CAE Independence

CAD and CAE are independent first-class capabilities.

- CAD does not automatically trigger meshing, solving, post-processing, or claim updates.
- CAE does not require prior CAD mutation.
- CAD->CAE is optional and explicit.

Supported paths: CAD-only, CAE-only, reference mapping, post-processing evidence, explicit claim update, optional explicit CAD->CAE orchestration.

Not supported: automatic CAD->CAE workflow, automatic CAD->CAE->claim workflow.

## Evidence and Claims

Evidence is not a claim.

The following do not imply validation or claim pass: artifacts, meshes, solver runs, result metrics, visualizations.

Claim status changes only through explicit evidence-backed claim update operations.

All non-claim-update execution/evidence/orchestration tools default to:

```json
{
  "claims_advanced": false
}
```

Only explicit claim update may modify `results/claim_map.json`.

## Planner / Capability Inspection Boundary

Capability/planning tools must be read-only and planning-neutral.

They may report capabilities, resources, inputs, side effects, missing info, unsupported operations, `needs_review`, and policy reminders.

They must not prescribe workflow order or replace agent judgment. The agent/caller decides sequencing.

## Allowed vs Disallowed

This project may:

- inspect models and package context
- run guarded parametric edits
- run CAE steps when explicitly requested
- produce artifacts/evidence/trace
- expose runtime capabilities
- report unsupported, missing, uncertain, unavailable, and `needs_review`

This project must not:

- replace `.aieng` as source of semantic truth
- auto-advance claims
- treat solver/visual success as validation
- force CAD before CAE or CAE after CAD
- hide unsupported/missing/not_found/needs_review states
- expose arbitrary Python or shell execution as normal public tools
- make FreeCAD/FEM/CalculiX or `.aieng` hard requirements for default usage

## Feature Direction Check

Before adding a feature, confirm it preserves:

- composable execution boundaries
- standalone usability without `.aieng`
- explicit claim discipline
- CAD/CAE independence
- explicit side effects and transparent unsupported/missing states
- caller-controlled workflow ordering

If any answer is no, redesign the feature.