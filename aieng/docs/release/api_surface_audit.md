# API surface freeze audit

This audit reviews public imports, package exports, package metadata, CLI entrypoints, example imports, and top-level module structure.

## Observed public surfaces

### Explicitly signaled stable-ish surfaces

These are the strongest alpha-freeze candidates because they are:
- described as core package semantics,
- imported directly in `examples/package_semantics_cookbook.py`, and
- exercised by `tests/test_public_api.py`.

| Module | Stable candidate scope |
|---|---|
| `aieng.package_manifest` | artifact classification and manifest assembly helpers |
| `aieng.evidence_resolver` | evidence reference freshness resolution |
| `aieng.package_consistency` | consistency diagnostics, including claim-map absence checks |
| `aieng.review_readiness` | review-readiness rollup |
| `aieng.claim_proposal` | proposal artifact construction and validation |
| `aieng.audit_event` | audit-event construction and JSONL helpers |
| `aieng.revalidation_status` | geometry freshness / revalidation transitions |
| `aieng.cae_result_summary` | CAE result/evidence summary helpers |
| `aieng.support_packet` | pure support-packet assembly |

These modules each declare `__all__`, which further supports freezing them at the symbol level for alpha.

### Package-level stable candidates

| Symbol | Assessment |
|---|---|
| `aieng.__version__` | reasonable package-version API |
| `aieng.FORMAT_VERSION` | format contract constant; should remain stable but should be documented as a **format** version, not a package release label |
| console script `aieng` | entrypoint name is stable enough to keep, but the full command matrix is not yet alpha-frozen |

## Unstable or experimental surfaces

These areas are importable today but do not look ready for alpha freeze.

| Surface | Why it should remain experimental/private |
|---|---|
| `aieng.cli` command matrix | broad, historically accreted, and still exposes claim-map flows that contradict current release positioning |
| `aieng.validate.validate_package` | useful and heavily tested, but broad validator semantics still encode legacy claim-map and cross-resource rules |
| `aieng.results.evidence_writer` | writes evidence + claim-map scaffolds; contradicts current alpha contract |
| `aieng.validation.*` writers | package-assembly helpers tied to evolving package layout and legacy claim-map assumptions |
| `aieng.simulation.*` | mixed maturity; some modules are scaffolds/importers rather than frozen semantics |
| `aieng.geometry.*` | backend-specific, with experimental OCP/CadQuery support |
| `aieng.converters.*` | adapter-facing conversion layer, not the core semantics freeze target |
| `aieng.mcp.*` | runtime integration surface, not a pure semantics contract |
| `aieng.ai.*` | derived summaries and prompting-oriented helpers, not core semantics |
| `aieng.modeling_plan.*`, `aieng.task.*`, `aieng.objects.*`, `aieng.graph.*` | useful, but not represented in the narrowed alpha-semantics story |
| `aieng.benchmarking.*` | benchmark harness, not package-format API |

## Accidentally exposed internal APIs

Because Python package modules are importable by path, the repo currently exposes many implementation-oriented modules without clearly marking them private. The main accidental exposures are:

- `aieng.results.evidence_writer`
- `aieng.validation.completeness_writer`
- `aieng.validation.evidence_report_writer`
- `aieng.validation.status_writer`
- `aieng.mcp.server`
- `aieng.simulation.mesh_handoff_writer`
- `aieng.ai.summary_writer`
- `aieng.validate`

These may be legitimate internal modules, but the current packaging layout makes them look just as importable as the intended core semantics modules.

## Recommended deprecations / scope reductions before alpha freeze

1. **Do not freeze claim-map APIs.**
   - `aieng.results.evidence_writer`
   - CLI commands such as `write-evidence-scaffold` and `update-claim`
   - MCP `get_claim_map`

2. **Do not freeze the full CLI command set.**
   Freeze only the existence of the `aieng` entrypoint if needed; keep subcommands explicitly experimental.

3. **Do not treat `aieng.validate.validate_package` as stable package-semantics API yet.**
   It is valuable, but it currently couples to legacy resources and repo-root schemas.

4. **Keep experimental backends and converter paths out of the alpha contract.**
   OCP/CadQuery extraction, converter capability profiles, and benchmarking harnesses should remain documented as experimental or auxiliary.

## Alpha freeze recommendations

### Freeze for `v0.1.0-alpha.1`

Freeze only the direct-submodule pure semantics story:

- `aieng.cae_result_summary`
- `aieng.package_manifest`
- `aieng.evidence_resolver`
- `aieng.package_consistency`
- `aieng.review_readiness`
- `aieng.claim_proposal`
- `aieng.audit_event`
- `aieng.revalidation_status`
- `aieng.support_packet`

And keep the following invariant in release notes and docs:

- `claim_advancement: "none"`
- evidence is not claim
- proposal is not acceptance
- freshness is not validation

### Keep experimental/private

Everything else should be treated as experimental unless separately reviewed and explicitly documented.

## Conservative conclusion

The repo already contains a good **core semantics freeze candidate**, but it does **not** yet have a cleanly narrowed public surface. The alpha release should freeze the pure semantics modules only and avoid implying stability for the broader CLI/runtime/claim-map stack.
