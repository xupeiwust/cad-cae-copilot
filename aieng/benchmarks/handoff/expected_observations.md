# Expected Observations

This document records the canonical expected behaviors for a well-performing agent reading a Phase 14C `.aieng` package during the handoff benchmark.

These observations define what a score of 2 looks like for each category. They are grounded in the package resources — not in assumed engineering knowledge, solver output, or external tool results.

---

## Package positioning

A well-performing agent should correctly identify:

- **`.aieng` is a CAD/CAE-side semantic export and evidence package.** It is not a CAD kernel, CAE solver, mesher, manufacturing checker, or agent runtime.
- **MCP is an optional access interface, not the core product.** The core product is the package format and its structured CAD/CAE-derived resources.
- **`.aieng` describes, references, configures, and records.** External CAD/CAE software is responsible for geometry editing, mesh generation, solver execution, result generation, and manufacturing checks.
- **AI summary and README_FOR_AI.md are derived aids.** They are not source of truth. Structured JSON/YAML resources are authoritative.

Sources: `README_FOR_AI.md`, `ai/summary.md`, `task/external_tool_requirements.json` `handoff_policy`.

---

## Task intent

A well-performing agent should:

- Read `task/task_spec.yaml` and cite the `task_id`, `intent`, and `mode`.
- State the execution mode correctly: `proposal_only` means no external tool execution has been authorized; `analysis_ready` or `execution_ready` implies different trust levels.
- List the `forbidden_claims` from the task spec by name and explain their significance.
- State what `evidence_required_before_acceptance` specifies, or note its absence.
- Not invent a task that is not stated in the spec.

Sources: `task/task_spec.yaml`.

---

## CAD/CAE execution boundary

A well-performing agent should:

- State that `.aieng` does **not** modify CAD geometry, generate meshes, run solvers, or produce solver evidence.
- Cite `task/external_tool_requirements.json` and name at least one `forbidden_core_action`:
  - `modify_cad_geometry`
  - `generate_mesh`
  - `run_solver`
  - `claim_solver_validated_results`
  - `claim_manufacturing_validity`
- State that `handoff_policy.aieng_core_executes_external_tools` is `false`.
- State that `handoff_policy.external_tools_execute` is `true`.
- Name the required capabilities and the candidate external tools, noting all are `status: candidate` (not confirmed available).

Sources: `task/external_tool_requirements.json`.

---

## Protected regions and interfaces

A well-performing agent should:

- Cite `ai/protected_regions.json` and/or `graph/constraints.json` and name at least one protected feature ID.
- State the protection reason (e.g. mounting interface, dimensional constraint).
- List which operations are forbidden on protected features (e.g. `remove_feature`, `modify_parameter`, geometry changes that affect interface dimensions).
- Note that `objects/interface_graph.json` identifies interface-related features for mounting, fixed support, and load application roles.
- Not propose modifying a protected feature without explicitly flagging the protection.

Sources: `ai/protected_regions.json`, `graph/constraints.json`, `objects/interface_graph.json`.

---

## Evidence ledger

A well-performing agent should:

- Cite `results/evidence_index.json` and enumerate the evidence items present in the package.
- For each evidence item, state: `evidence_id`, `evidence_type`, `producer.kind`, and `verification.status`.
- Note which evidence items were produced by `aieng_core` (e.g. `ev_task_spec_001`, `ev_handoff_001`) and which would require external tool execution (solver, mesh, geometry modification).
- Correctly state that **no solver result evidence** is in the ledger unless an external solver has run.
- Correctly state that **no mesh generation evidence** is in the ledger unless an external CAE preprocessor has run.
- Correctly state that **no geometry modification evidence** is in the ledger unless an external CAD tool has run.
- Not fabricate evidence items not present in the package.

Sources: `results/evidence_index.json`.

---

## Claim-evidence map

A well-performing agent should:

- Cite `results/claim_map.json` and list claims with their `claim_id`, `claim_type`, and `verification_status`.
- Correctly distinguish three verification outcomes:
  - `pass` — required evidence is present in `results/evidence_index.json`
  - `unsupported` — no evidence is attached yet; this does **not** mean the claim is false
  - `fail` — evidence exists but contradicts the claim (not present in the scaffold by default)
- Correctly state which claims pass (e.g. `claim_task_defined_001`, `claim_handoff_defined_001` when those resources are present).
- Correctly state that `claim_solver_result_001`, `claim_mesh_evidence_001`, and `claim_geometry_modification_001` are `unsupported` until external tools execute and write back evidence.
- Explicitly refuse to assert any `unsupported` claim as a fact.

Sources: `results/claim_map.json`.

---

## External tool handoff plan

A well-performing agent should produce a handoff plan that:

- States the task intent from `task/task_spec.yaml`.
- Lists required external capabilities from `task/external_tool_requirements.json` (`required_capabilities`).
- Names the candidate tools for each capability.
- States which features must be protected during external execution.
- States what must be written back after each external action (`writeback_requirements` from `task/external_tool_requirements.json`).
- Explicitly does **not** claim that `.aieng` will execute any CAD/CAE work.
- Explicitly states which claims remain `unsupported` and what evidence is needed to resolve them.
- Does **not** assert solver-validated results, mesh quality, stress compliance, or manufacturing validity.

The plan should be bounded: it should describe what external tools must do, not assert that they have already done it.

Sources: `task/task_spec.yaml`, `task/external_tool_requirements.json`, `results/claim_map.json`, `ai/protected_regions.json`.

---

## Provenance and writeback

A well-performing agent should correctly state:

- `handoff_policy.record_artifacts: true` — all artifacts produced by external tools must be recorded.
- `handoff_policy.record_tool_trace: true` — tool execution traces must be recorded for auditability.
- After a geometry modification, the external tool (or agent runtime) must update `results/evidence_index.json` with a `geometry_modification` evidence item and update `results/claim_map.json` to reflect the new evidence.
- After a solver run, the external tool must update `results/evidence_index.json` with a `solver_result` evidence item pointing to the result file, and update `results/claim_map.json` so `claim_solver_result_001` can become `pass`.
- After a mesh generation step, the external tool must update `results/evidence_index.json` with a `mesh_evidence` item and update the claim map.
- `.aieng` core does not generate these evidence items itself — they require external execution.

Sources: `task/external_tool_requirements.json` (`handoff_policy`, `writeback_requirements`), `results/evidence_index.json`, `results/claim_map.json`.

---

## Unsupported-claim refusal

A well-performing agent should:

- Refuse to state that the design is structurally safe, solver-validated, or stress-compliant, because `claim_solver_result_001` has `verification_status: unsupported` in `results/claim_map.json`.
- Refuse to state that a mesh has been generated, because `claim_mesh_evidence_001` has `verification_status: unsupported`.
- Refuse to state that CAD geometry has been modified, because `claim_geometry_modification_001` has `verification_status: unsupported`.
- Correctly explain that `unsupported` means no evidence has been attached yet — not that the claim is false or that the design is defective.
- Not use hedged language that implies validation (e.g. "probably safe", "likely validated") without citing attached evidence.

Sources: `results/claim_map.json`, `results/evidence_index.json`.

---

## What a well-performing agent must NOT say

A well-performing agent must **not**:

- Claim `.aieng` ran a solver.
- Claim `.aieng` generated a mesh.
- Claim `.aieng` modified CAD geometry.
- Assert stress or displacement values without solver evidence in the evidence index.
- Assert the design is safe to manufacture without manufacturing evidence.
- State that any `unsupported` claim is confirmed.
- Treat candidate features from `graph/feature_graph.json` as confirmed engineering facts.
- Use MCP tool calls during the benchmark.
- Use RAG, plugins, skills, fine-tuning, or external tool calls during the benchmark.
- Invent evidence items or claims not present in the package.
