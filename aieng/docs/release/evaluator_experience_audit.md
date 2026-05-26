# Evaluator experience audit

Question: can a technically sophisticated new evaluator understand within 10 minutes:

- what `.aieng` is,
- why it is not CAD-to-JSON,
- why provenance/freshness/missingness matter,
- what the benchmark actually demonstrates?

## Short answer

**Partially.**

The repo now has strong material for the answer:
- `README.md`
- `docs/package-semantics.md`
- `examples/package_semantics_cookbook.py`
- golden examples in `tests/golden/`

But the evaluator path is still noisy because older converter/claim-map/runtime material remains visible and can compete with the new package-semantics story.

## Main confusion points

### 1. Stable semantics story vs broad historical surface

The README and package-semantics doc describe a focused evidence/provenance/freshness model, but the repo still contains many older docs and commands about:
- claim maps,
- `update-claim`,
- converter maturity levels,
- benchmark scaffolds,
- large runtime-oriented command surfaces.

A first-time evaluator can quickly lose track of what is intended for alpha versus what is historical or experimental.

### 2. Quick Start is still converter/CLI heavy

The current README quick start starts with:
- `import-step`
- `extract-topology`
- `recognize-features`
- `apply-context`
- `summarize`
- `propose-patch`
- `validate`

That is useful for power users, but it is not the shortest path to understanding the release thesis. The cookbook example is a much cleaner evaluator path and should arguably be the first recommended path for alpha review.

### 3. Legacy claim-map terminology creates direct contradictions

An evaluator who reads the release checklist (`No claim maps`) and then lands in `docs/command_reference.md`, `docs/architecture.md`, or `docs/agi_handoff_walkthrough.md` will see claim maps treated as normal behavior. That contradiction is likely to reduce trust.

### 4. Benchmark wording can still be over-read

The benchmark sections are largely careful, but terms like `correctness` and `geometric correctness` can be mistaken for engineering-correctness claims if read quickly. The benchmark is really about model-answer quality under a rubric, not design approval.

### 5. No single release landing page for alpha scope

There is no one-page evaluator landing doc saying:
- these modules are in scope,
- these CLI/runtime surfaces are experimental,
- these legacy docs are historical,
- this is the exact path to reproduce the release checks.

`docs/release-v0.1-alpha-checklist.md` comes close, but it is still a checklist, not a scoped evaluator guide.

## Terminology problems

1. `validation` is overloaded.
   - Sometimes it means schema/package validation.
   - Sometimes it means external engineering validation evidence.
   - Sometimes it appears in benchmark scoring language.

2. `correctness` is overloaded.
   - Sometimes it means answer correctness under a rubric.
   - Sometimes readers may interpret it as engineering correctness.

3. `claim` vocabulary is not consistently scoped.
   - New docs use proposal/readiness/non-advancement language.
   - Older docs still use claim-map/update-claim workflows.

## Onboarding friction

- Large repo surface area with many historical design docs.
- README badge/status drift (`status-beta`, hardcoded test count) makes the front door feel less curated.
- Installed-package versus editable-checkout expectations are not obvious.
- Benchmark docs include both implemented and design-only material, which can blur what is currently runnable.

## Missing or weak evaluator aids

### Missing
- A single alpha landing page that distinguishes stable core semantics from experimental runtime/converter surfaces.
- A stable-vs-experimental matrix.
- A short visual diagram that shows `artifact -> evidence -> freshness -> proposal -> review` at README level.

### Present but underused
- `examples/package_semantics_cookbook.py`
- `tests/golden/`
- `docs/package-semantics.md`

These are the strongest evaluator assets and should be front-loaded.

## Suggested improvements

1. **Make the cookbook the primary alpha evaluator entry point.**
2. **Quarantine or clearly label legacy claim-map docs and commands as not part of alpha scope.**
3. **Add a stable-vs-experimental matrix near the top of the README or in a dedicated alpha evaluator doc.**
4. **Replace ambiguous benchmark `correctness` wording with `task-score correctness` or equivalent clarifiers where practical.**
5. **Add a short release-scope diagram and “start here” box at the top of the release docs.**

## Conservative conclusion

A new evaluator can understand the intended core story within 10 minutes **if** they follow the modern path (`README` -> `docs/package-semantics.md` -> cookbook -> golden tests). The risk is that the broader repo still exposes enough legacy material to pull them off that path.
