# Final release review — v0.1.0-alpha.1

## Branch

- Name: `release/v0.1.0-alpha.1`
- Pushed to: `github` (`https://github.com/armpro24-blip/aieng`) and `origin` (`https://git-fkb.ostfalia.de/id664823/aieng`)
- Not tagged. Not merged. Not published.

## Commit

- Release-prep commit hash: `5ba893908ed06d47f8b813d6f6db6ecbb67fd828`
- Subject: `release: prepare v0.1.0-alpha.1`

## Package metadata

- Distribution name: `aieng-format`
- Python version: `0.1.0a1`
- Development status classifier: `Development Status :: 3 - Alpha`
- Build backend: `hatchling`
- Wheel artifact (local, not published): `dist/aieng_format-0.1.0a1-py3-none-any.whl`

## Git tag target

- Intended tag: `v0.1.0-alpha.1`
- Tag commit: `5ba893908ed06d47f8b813d6f6db6ecbb67fd828`
- Tag has NOT been created in this session. Tag creation is left to the human releaser.

## Tests run

- `python -m pytest -q` on `release/v0.1.0-alpha.1` after staging and after commit
  - Result: `1860 passed, 14 skipped, 10 warnings in ~35s`
  - Warnings are zipfile duplicate-name `UserWarning`s emitted by a handful of tests that intentionally rewrite ZIP members. Cosmetic; no failures.

## Smoke test result

- Built wheel from the source tree with `python -m build --wheel`.
- Installed the wheel into a clean virtualenv (`/tmp/aieng_smoke`) without using the repo as a Python path or editable install.
- Ran `tests/smoke/test_installed_wheel.py` both:
  - under `pytest` inside the source tree (4/4 passed), and
  - as a standalone script from `/tmp` (outside the repo root) using the venv interpreter — output: `installed-wheel smoke: OK`.
- Smoke test confirms:
  - `importlib.resources.files("aieng.schemas")` resolves required schemas in the installed package,
  - core public API symbols import without filesystem assumptions,
  - `python -m aieng.cli --help` runs and does not list `update-claim`,
  - `aieng init` + `aieng validate` round-trip succeeds outside the repo (exit 0).

## What changed in this release branch

- Removed `update-claim` from the CLI and removed claim-map accessors from the MCP server.
- Reframed `record-evidence`, `import-solver-evidence`, `import-mesh-evidence` as evidence-only writebacks; no automatic claim advancement.
- Migrated JSON schemas into `aieng.schemas` as a proper Python subpackage and switched `validate.py` / `definition.py` to load schemas via `importlib.resources` with a filesystem fallback.
- Updated `pyproject.toml`: version `0.1.0a1`, classifier `3 - Alpha`, replaced `force-include` with an `artifacts` entry so the wheel ships schemas without duplicate-name warnings.
- Softened certification-adjacent wording in `README.md` and `src/aieng/validation/status_writer.py`; clarified benchmark "correctness" framing.
- Cleaned alpha-facing claim-map / update-claim language in `docs/architecture.md`, `docs/agi_handoff_walkthrough.md`, `docs/mvp_checkpoint.md`, `docs/reference_notation.md`, and `docs/command_reference.md`.
- Added `docs/release/` audit and release-note artifacts.
- Added `tests/smoke/test_installed_wheel.py` and `tests/smoke/__init__.py`.

## Remaining warnings

- Internal modules still read `results/claim_map.json` when present (`completeness_writer.py`, `evidence_report_writer.py`, `validate.py`, `simulation/mesh_handoff_writer.py`, `ai/summary_writer.py`). These paths are quarantined: no alpha-facing CLI/MCP surface exposes them. They should be retired in `v0.1.0-alpha.2` or `v0.1.0-alpha.3`.
- `src/aieng/schemas/claim_map.schema.json` still ships with the wheel for backwards compatibility with packages that already contain a claim_map.json. It is not promoted as an alpha contract artifact.
- Benchmark fixtures under `benchmark_runs/` still contain `results/claim_map.json` files. They are evaluator fixtures, not part of the release contract.
- 10 zipfile duplicate-name warnings from tests; cosmetic.
- Schema loading verified for filesystem-installed wheels; not validated against zipapp/PyOxidizer-style frozen distributions, which are not in scope for this release.

## Release recommendation

**YES WITH WARNINGS.**

All three named release blockers (claim-map alpha surfaces, schema packaging, alpha metadata) have concrete fixes in this branch. Full test suite is green. The wheel is verified installable and usable outside the source tree. The remaining residue is dormant internal plumbing and benchmark fixtures, none of which contradict the alpha story.

## Next human action

1. Create the annotated tag `v0.1.0-alpha.1` at commit `5ba893908ed06d47f8b813d6f6db6ecbb67fd828`.
2. Open a GitHub release using `docs/release/github_release_draft_v0.1.0-alpha.1.md` as the body.
3. Decide whether to attach `dist/aieng_format-0.1.0a1-py3-none-any.whl` as a release asset or publish to PyPI as a pre-release (`pip install aieng-format==0.1.0a1`).
4. Schedule `v0.1.0-alpha.2` cleanup of dormant claim-map plumbing.
