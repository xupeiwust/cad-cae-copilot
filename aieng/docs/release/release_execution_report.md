# Release execution report

## Environment

- Repository: `aieng`
- Branch at execution time: `release/v0.1.0-alpha.1`
- OS: Windows
- Shell: PowerShell
- Python: `3.11.5`
- Working directory: source checkout

## Commands run

### Full test suite

```bash
pytest -q
```

### Focused core release-checklist suite

```bash
python -m pytest tests/test_support_packet.py tests/test_public_api.py tests/test_examples.py tests/test_core_semantics_golden.py tests/test_revalidation_status.py tests/test_audit_event.py tests/test_claim_proposal.py tests/test_review_readiness.py tests/test_package_consistency.py tests/test_evidence_resolver.py tests/test_package_manifest.py tests/test_cae_result_summary.py -q
```

## Results

### Full test suite result

- `1916 passed, 15 skipped, 10 warnings in 39.11s`

### Focused core release-check result

- `344 passed in 0.77s`

## Warnings observed

`pytest -q` produced 10 warnings, all from `zipfile` duplicate-member writes during tests.

Observed warning patterns:
- duplicate `simulation/runs/run_006/`
- duplicate `graph/feature_graph.json`
- duplicate `ai/patches/patch_0001.json`
- duplicate `manifest.json`

Assessment:
- these warnings did not fail tests,
- but they indicate that some test flows rewrite ZIP members in-place and may merit cleanup for long-term hygiene.

## Failed tests

- None.

## Skipped tests

- 15 skipped in the full suite.
- The skipped tests were not investigated further in this pass because the release task focused on audit/readiness rather than feature completion.

## Dependency issues observed

- No immediate dependency import failures during the executed test commands.
- This pass did **not** validate wheel/sdist install behavior in a clean environment.
- Optional benchmark/network/external-binary flows were not exercised as part of the release execution run.

## Release readiness summary

### Functional status

- Core semantics tests are green.
- Broader repository tests are green.
- Existing docs and examples support the narrowed core semantics story.

### Non-functional / release blockers

- Legacy claim-map/update-claim surfaces remain present across CLI, docs, MCP, and validation helpers.
- Packaging/installability risks remain because runtime code depends on repo-root schema assets not proven to ship with the wheel.
- Version/classifier/status metadata do not yet match the intended alpha tag.

## Conservative conclusion

From a test-execution perspective, the repository is strong.

From a release-engineering perspective, `v0.1.0-alpha.1` is **not yet a clean tag candidate** because semantic-positioning and packaging blockers remain.
