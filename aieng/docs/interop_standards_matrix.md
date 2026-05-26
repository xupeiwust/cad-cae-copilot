# CAD/CAE Interoperability Standards Matrix (Draft)

This document proposes a practical standards-first strategy for multi-CAD and multi-CAE support in `.aieng`.

The objective is to use established exchange standards where they are strong, and use `.aieng` as the semantic/evidence bridge where standards are incomplete.

## Why this exists

There is no single universal format that fully covers:

1. CAD geometry and feature semantics
2. CAE setup intent (materials, loads, BCs, targets)
3. mesh and solver execution evidence
4. result claims and provenance for AI-safe reasoning

A standards-first approach is still valuable, but it must be layered.

## Coverage matrix

| Standard / Ecosystem | Typical scope | Strengths | Gaps vs `.aieng` goals |
|---|---|---|---|
| STEP AP242 | CAD geometry + PMI/MBD exchange | Widely used; neutral geometry exchange; supports richer product data than older APs | Feature intent and CAE mapping often incomplete across toolchains; no direct claim/evidence/provenance model |
| IGES | Legacy CAD geometry exchange | Broad legacy compatibility | Weaker modern semantics than STEP AP242; not suitable as primary future baseline |
| Abaqus-style INP (also used by CalculiX) | CAE model/deck definition | Human-readable text deck; common workflow familiarity | Solver-specific dialect differences; deck alone is not solver evidence |
| Nastran BDF/DAT | CAE model/deck definition | Long-standing structural analysis ecosystem | Similar deck portability limits; no native AI-oriented claim/evidence/provenance layer |
| Solver result formats (FRD/ODB/etc.) | Result artifacts | Carry computed outputs from external execution | Tool-specific and unevenly portable; need normalization for package-level claims |

## Recommended layered strategy

1. Use STEP AP242 as the primary CAD exchange baseline.
2. Use one CAE deck baseline first (Abaqus-style INP / CalculiX path) for earliest end-to-end closure.
3. Keep internal `.aieng` resources solver-agnostic and CAD-kernel-agnostic.
4. Treat external formats as adapters into canonical `.aieng` resources.

In short:

- standards for artifact transport
- `.aieng` for semantic consistency, evidence, claims, and provenance

## Canonical resource mapping targets

For each adapter, map into these resources instead of exposing raw tool-specific semantics as core truth:

1. `manifest.json`
2. `geometry/topology_map.json`
3. `graph/feature_graph.json`
4. `simulation/setup.yaml`
5. `graph/constraints.json`
6. `results/evidence_index.json`
7. Claim proposals (review artifacts requiring human review)
8. `provenance/tool_trace.json`
9. `validation/completeness_report.json`

## Missingness and uncertainty policy

Adapter behavior must follow explicit missingness:

1. Convert what is present.
2. Mark absent, partial, unsupported, unknown, or conflicting explicitly.
3. Do not infer missing CAD/CAE facts.
4. Do not assert claim pass/fail without evidence IDs.

## Non-negotiable conversion rule

This is a hard rule for all adapters and future conversion work:

1. Only convert what is known from the source artifacts and metadata.
2. For unknown or unmappable information, record explicit unknown/partial/missing/unsupported state in structured resources.
3. Never guess unknown engineering facts during conversion.
4. If this rule is violated, the conversion is considered invalid for `.aieng` quality and trust requirements.

## Phase 17 implementation proposal

### Step 1: Baseline interoperability profile

Define and freeze a minimal profile:

1. CAD exchange baseline: STEP AP242
2. CAE deck baseline: Abaqus-style INP (CalculiX-compatible path)
3. Result import baseline: one text result path for MVP evidence writeback

### Step 2: First real closed loop

Implement one narrow end-to-end flow:

1. Import external result artifact
2. Record evidence into `results/evidence_index.json`
3. Claim proposals require human review (no automated claim status updates)
4. Append `provenance/tool_trace.json`
5. Refresh `validation/completeness_report.json`
6. Validate package

### Step 3: Capability declaration per adapter

Each adapter should declare capability level and limits (aligned with `docs/cad_cae_emitter_contract.md`):

1. What it can map reliably
2. What it cannot map
3. Which fields are generated vs externally sourced

## Decision criteria for first adapter

Use these criteria to select the first implementation target:

1. Text format readability and deterministic parsing
2. Reproducibility in CI without proprietary dependencies
3. High ratio of engineering value to implementation complexity
4. Clear evidence-to-claim mapping path

## Current recommendation

1. Keep STEP AP242 as CAD baseline target.
2. Start CAE proof path with Abaqus-style INP / CalculiX-compatible deck/result workflow.
3. Keep architecture explicitly open for Nastran/Ansys/Abaqus-native adapters later.

This avoids early lock-in while still delivering a real, auditable, end-to-end handoff loop.

## Resolved policy decision

1. Import pathways are evidence-only by default.
2. Import pathways do not automatically change claim status. Claim proposals are review artifacts requiring human review.
3. Claim status changes require human review with evidence references.

## Open decisions to finalize with team

1. What minimum result fields are required to recommend pass/fail review for specific claim IDs vs keep unsupported?
2. What adapter metadata is mandatory in tool trace entries?

## Phase 17 execution plan (issue-mapped)

The current gap analysis is now tracked as concrete issues and should be executed in this order.

1. CAD writeback bridge (highest impact): [#4](https://github.com/armpro24-blip/aieng/issues/4)
2. Solver numeric semantic extraction: [#28](https://github.com/armpro24-blip/aieng/issues/28)
3. Mesh artifact command chain and structured mesh evidence: [#29](https://github.com/armpro24-blip/aieng/issues/29)
4. Global evidence-only import policy alignment: [#30](https://github.com/armpro24-blip/aieng/issues/30)

Recommended delivery slices:

1. Slice A (writeback closure): deliver minimal executable CAD writeback for at least one supported patch operation path under explicit guardrails.
2. Slice B (solver claimability): deliver deterministic numeric extraction for supported result patterns and explicit unknown handling.
3. Slice C (mesh traceability): deliver mesh artifact intake with structured metadata and evidence/claim validator integration.
4. Slice D (policy consolidation): align docs, summaries, and validator messaging to one global "import is evidence-only unless claim status is explicitly updated" rule.

Definition of done for this wave:

1. External artifacts can enter `.aieng` with explicit structured provenance.
2. Numeric solver facts (when parseable) can support claim-review workflows.
3. Mesh evidence is first-class in command flow, not just schema vocabulary.
4. No import pathway implicitly advances claim status.
