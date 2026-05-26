# v1.0.0-rc1 / v1.0.0 Release Checklist

## Tests

- [x] All tests pass: `python -m pytest tests/` (242 passed, 11 skipped)
- [x] No regressions in existing test suite
- [x] Real FreeCAD runtime tests skipped or passed (not failing)
- [x] Real solver integration tests skipped or passed (not failing)
- [x] Audit report tests pass
- [x] End-to-end demo tests pass
- [x] Claim discipline tests pass

## Demos

- [x] `python scripts/run_v1_end_to_end_demo.py` completes successfully
- [x] `python scripts/run_aieng_patch_demo.py` completes successfully
- [x] `python scripts/run_cad_to_cae_demo.py` completes successfully
- [x] `python scripts/run_postprocessing_demo.py` completes successfully
- [x] `python scripts/run_claim_update_demo.py` completes successfully
- [x] `python scripts/run_reference_mapping_demo.py` completes successfully
- [x] `python scripts/run_real_static_solver_demo.py` exits cleanly (skips if FreeCAD unavailable)

## Claim Policy

- [x] All mutating tools return `claims_advanced: false`
- [x] Only `aieng_update_claim` modifies `claim_map.json`
- [x] Evidence entries do not have `claims_advanced: true`
- [x] Surrogate evidence includes `engineering_validation: false`
- [x] No hidden claim advancement in any tool

## Documentation

- [x] README.md has install instructions
- [x] README.md has quickstart
- [x] README.md explains standalone vs .aieng-enhanced mode
- [x] README.md explains runtime optional dependencies
- [x] README.md explains claim policy
- [x] README.md links to all demos
- [x] docs/architecture.md is up to date
- [x] docs/tool_contract.md includes all tools (including planner)
- [x] docs/evidence_and_claim_policy.md includes audit reports
- [x] docs/roadmap.md marks v1.0.0-rc1 as Implemented scaffold / RC
- [x] docs/release_v1_demo.md exists and is accurate
- [x] docs/release_checklist.md exists

## Package Metadata

- [x] pyproject.toml version is `1.0.0rc1` (RC)
- [x] pyproject.toml description is accurate
- [x] pyproject.toml dependencies are correct
- [x] pyproject.toml dev dependencies are correct

## Known Limitations

Documented in README and docs:

- [x] Topology-changing edits are unsupported
- [x] Topology-stable face IDs are not guaranteed
- [x] Real solver path depends on local FreeCAD/FEM/CalculiX
- [x] VTK export requires field data pipeline
- [x] No automatic BC/load remapping after geometry change
- [x] Compound claim logic (AND/OR) is not implemented

## Final Verification

- [x] `python -m pytest tests/` passes with 242 tests
- [x] Demo script prints success message
- [x] Audit report JSON and Markdown are generated
- [x] No auto-advancement violations detected
