# v0.1-alpha Readiness Checklist

This checklist defines a documentation and release-readiness gate for a
`v0.1-alpha` style state. It does not add feature scope. See
[`package-semantics.md`](package-semantics.md) for the core package semantics
story and [`../examples/package_semantics_cookbook.py`](../examples/package_semantics_cookbook.py)
for a dependency-free in-memory walkthrough. For the current release-notes draft, see
[`releases/v0.1.0-alpha.1.md`](releases/v0.1.0-alpha.1.md).

For the current repository publish gate, see
[`release/current_alpha_release_gate.md`](release/current_alpha_release_gate.md).

## Scope of v0.1-alpha

Stable-ish and contract-tested core semantics live in `aieng` and are imported
from direct submodules:

- `aieng.cae_result_summary`
- `aieng.package_manifest`
- `aieng.evidence_resolver`
- `aieng.package_consistency`
- `aieng.review_readiness`
- `aieng.claim_proposal`
- `aieng.audit_event`
- `aieng.revalidation_status`
- `aieng.support_packet`

The common invariant is `claim_advancement: "none"`. Evidence, proposals,
freshness state, audit records, readiness diagnostics, and consistency checks do
not silently advance engineering claims.

## Reference runtime status

- `aieng-ui` is a reference runtime/workbench.
- It exercises real and simulated CAE workflows through local HTTP APIs, project
  I/O, package ZIP I/O, tool execution, and orchestration.
- It delegates package semantics to `aieng` core; it is not the semantic source
  of truth.

## What is intentionally NOT included

- No claim acceptance/rejection workflow.
- No claim maps.
- No automatic claim advancement.
- No certification or validation claims.
- No full CAD kernel.
- No solver replacement.
- No guarantee that STEP contains design intent.
- No multi-CAD production adapter guarantee.

## Required checks before tagging

For `aieng`:

```bash
python -m pytest tests/test_support_packet.py tests/test_public_api.py tests/test_examples.py tests/test_core_semantics_golden.py tests/test_revalidation_status.py tests/test_audit_event.py tests/test_claim_proposal.py tests/test_review_readiness.py tests/test_package_consistency.py tests/test_evidence_resolver.py tests/test_package_manifest.py tests/test_cae_result_summary.py -q
```

For `aieng-ui`:

```bash
cd backend
python -m pytest -c NUL tests/test_api.py -q
```

## Release blockers

- Any test failure.
- Any accidental claim map creation.
- Any automatic claim advancement.
- Broken public imports.
- Docs implying certification/validation.
- README framing as only CAD-to-JSON.

## 10-minute evaluator path

1. Read [`docs/package-semantics.md`](package-semantics.md).
2. Run the cookbook example: `python examples/package_semantics_cookbook.py`.
3. Inspect golden examples in [`tests/golden/`](../tests/golden/).
4. Run the focused core tests listed above.
5. Optionally inspect `aieng-ui` reference runtime docs/tests to see how runtime
   ZIP/project I/O delegates package semantics to `aieng` core.
