> Note: `v0.1.0-alpha.3` supersedes `v0.1.0-alpha.2`. It is a cleanup release: no new features, no new evaluator-facing capabilities. Approximately 700 lines of dormant `claim_map` plumbing (forbidden under the alpha contract) are retired from CLI, validator, summary renderer, completeness report, mesh handoff, evidence report, and the packaged schema set.

## Summary

`v0.1.0-alpha.3` is an experimental pre-release. Treat its outputs as
review material that requires human engineering judgment. There are no
new user-facing capabilities relative to `v0.1.0-alpha.2`; the public
package contract is unchanged. What changed is the amount of code that
exists behind it.

The alpha contract has always been: no claim maps, no automatic claim
advancement, no autonomous engineering decisions. In `v0.1.0-alpha.2` a
number of internal modules still contained read paths and cross-reference
rules for `results/claim_map.json` even though no compliant alpha
package can contain that file. Those paths are now gone.

## What changed

- `src/aieng/validate.py`: stops reading `results/claim_map.json`;
  retired rules cross-referencing claim_map with `validation/status.yaml`,
  `task/task_spec.yaml`, `provenance/tool_trace.json`,
  `validation/evidence_report.json`, and `simulation/mesh_handoff_contract.json`;
  `_validate_claim_map` and `_validate_evidence_claim_cross_reference`
  removed.
- `src/aieng/validation/evidence_report_writer.py`: drops the claim_map
  read; the `claims` array in `validation/evidence_report.json` is now
  always emitted as `[]`; the schema reflects two authoritative sources
  (validation status + evidence index) instead of three.
- `src/aieng/validation/completeness_writer.py`: the `validation/completeness_report.json`
  no longer contains a `claim_map` category; the schema enum is updated.
- `src/aieng/ai/summary_writer.py`: `README_FOR_AI.md` and `ai/summary.md`
  no longer surface a `## Claim-evidence map` section in any form.
- `src/aieng/simulation/mesh_handoff_writer.py`: `target_claim_ids` in
  the mesh handoff contract is now hardcoded to the default; the
  derivation-from-claim_map path is removed.
- `src/aieng/schemas/claim_map.schema.json` is no longer shipped with
  the wheel.
- Python package version: `0.1.0a1` → `0.1.0a2`.

## Explicit non-goals

Unchanged from `v0.1.0-alpha.2`. This release does **not** provide and
does **not** claim to provide:

- engineering certification,
- automatic engineering validation,
- solver authority,
- autonomous engineering decisions,
- automatic claim advancement,
- claim acceptance/rejection workflows,
- claim maps as part of the intended alpha contract,
- a CAD kernel,
- a solver replacement,
- a guarantee that STEP conversion captures design intent.

## Safety / review semantics

Unchanged. The intended safety posture is conservative:

- `claim_advancement: "none"` is the default invariant.
- Evidence is not claim.
- Proposal is not acceptance.
- Freshness is not validation.
- Diagnostics are not certification.
- Tool execution must not silently advance engineering claims.

## Installation

`v0.1.0-alpha.3` is a pre-release. Pip will not install it by default
unless you opt in. The published Python package version is `0.1.0a2`.

```bash
pip install --pre aieng-format==0.1.0a2
# or, from the source tree:
pip install -e .
```

Python 3.11 or newer is required.

## Verification

After installing the wheel:

```bash
python -c "import aieng; print(aieng.FORMAT_VERSION)"
python -c "from importlib.resources import files; print(files('aieng.schemas').joinpath('manifest.schema.json').is_file())"
python -c "from importlib.metadata import version; print(version('aieng-format'))"
aieng --help
aieng init --model-id smoke_001 --out smoke.aieng
aieng validate smoke.aieng
```

Expected:

- `FORMAT_VERSION` prints `0.1.0`,
- `importlib.resources` reports the packaged manifest schema is present,
- `importlib.metadata.version('aieng-format')` reports `0.1.0a2`,
- the CLI listing must not contain `update-claim`,
- `aieng validate` exits 0 with a mix of `PASS` and `WARN` messages.

Repository test status at tag time:

- `python -m pytest -q`: `1860 passed, 14 skipped, 10 warnings`.
- Installed-wheel smoke test (`tests/smoke/test_installed_wheel.py`): 4/4 passed.
- Wheel rebuilt and re-installed into a clean venv outside the source
  tree; CLI round-trip on a fresh package: exit 0.

## Known warnings

- Benchmark fixtures under `benchmark_runs/` still contain
  `results/claim_map.json` files. They are evaluator fixtures, not part
  of the release contract.
- Real-geometry STEP extraction via OCP/CadQuery is experimental,
  platform dependent, and review-required. The default backend is the
  mock backend.
- `pytest -q` emits 10 zipfile duplicate-name `UserWarning`s from tests
  that intentionally rewrite ZIP members. Cosmetic; no test failures.
- The earlier `v0.1.0-alpha.1` tag still exists on this repository at
  pre-publication draft commit `408af998` and is unrelated to this
  release line. Treat it as stale.

## Next cleanup targets

Out of scope for this tag; tracked for a follow-up alpha:

- Scrub or annotate the `results/claim_map.json` files inside
  `benchmark_runs/` fixtures.
- Tighten the public API surface around the pure semantics modules and
  add a stability table to `docs/package-semantics.md`.
- Eliminate the zipfile duplicate-name warnings by rewriting ZIPs
  atomically in the affected tests.
- Decide whether to retire `claim_proposal.schema.json` review-only
  semantics or promote them as the canonical alpha proposal flow.

---

`.aieng` is an auditable engineering context format. It is not an
engineering authority. Outputs from this release are review material.
