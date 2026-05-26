---
title: "[Phase 17B] Mesh handoff completeness for external Gmsh integration"
labels: ["phase-17", "phase-17b", "mesh", "handoff", "cae"]
status: closed
---

## Motivation

The package already supports mesh evidence import, but the outbound handoff contract to external meshing tools is not yet first-class. A structured handoff resource is needed so external Gmsh workflows can consume package intent consistently and write evidence back in a traceable way.

Phase 17B closes the round-trip gap: handoff contract out, evidence back in.

## Goal

Implement mesh handoff completeness with a schema-validated contract resource and validator integration, without executing meshing inside `.aieng`.

## Scope

1. Define `simulation/mesh_handoff_contract.json` schema and resource shape.
2. Add CLI command:
   - `aieng write-mesh-handoff <package.aieng>`
3. Contract includes:
   - geometry source path,
   - recommended meshing parameters,
   - entity/tag references derived from current package state,
   - claim IDs expected to be supported by mesh evidence.
4. Integrate validator checks when handoff contract is present.
5. Document canonical round trip:
   - write handoff contract,
   - external Gmsh execution,
   - import mesh evidence via existing evidence import flow.
6. Add mesh handoff presence/status into `validation/completeness_report.json`.

## Non-goals

- No in-core mesh generation.
- No Gmsh invocation by `.aieng` core.
- No solver execution.
- No geometry modification.

## Acceptance criteria

- [x] `aieng write-mesh-handoff` writes valid `simulation/mesh_handoff_contract.json`.
- [x] Schema enforces execution-boundary policy (no mesher execution by core).
- [x] `aieng validate` checks mesh handoff contract when present.
- [x] Existing mesh evidence import tests remain passing.
- [x] Docs include handoff round-trip instructions and limits.

## Test plan

- Unit tests for handoff writer output shape and required fields.
- Schema validation tests including boundary-guard const checks.
- Integration test for contract-generation plus evidence-import compatibility.
- Regression tests for existing mesh evidence import behavior.

## Boundary guardrails

- `.aieng` produces handoff contracts and records evidence only.
- External tools execute meshing and produce mesh artifacts.
- Mesh handoff contract is not solver evidence by itself.

## Related

- `docs/roadmap.md` (Phase 17B)
- `README.md` (Upcoming Phase 17)
- `docs/mvp_checkpoint.md` (Upcoming section)
- `docs/rigorous_interop_acceptance_checklist.md` (Issue #36 reference)

## Closure evidence

Current implementation evidence (workspace state):
- Commit hash: `acace1a`.
- Tests passing:
   - `python -m pytest tests/test_mesh_handoff_contract.py tests/test_import_mesh_evidence.py tests/test_docs_checkpoint.py -q` -> pass.
   - Includes contract writer/schema/validator coverage and round-trip compatibility checks with `import-mesh-evidence`.
- Docs updated:
   - `docs/command_reference.md` (`aieng write-mesh-handoff` command and round-trip context).
   - `docs/roadmap.md`, `docs/mvp_checkpoint.md`, `README.md` (Phase 17B scope/status).

Issue closure status:
- Local issue doc status set to `closed`.
