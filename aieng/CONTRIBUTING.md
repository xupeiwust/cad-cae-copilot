# Contributing to `.aieng`

Thank you for your interest in contributing. This document covers local setup, the test workflow, the project's core design rules, and PR expectations.

---

## Local setup

```bash
conda create -n aieng311 python=3.11
conda activate aieng311
pip install -e .
```

Optional: real STEP topology via OCP/CadQuery (not required for most contributions):

```bash
pip install -e ".[geometry]"
```

Verify the install:

```bash
aieng --help
python -m pytest -q
```

All tests should pass. The two `skipped` tests require the optional OCC backend and are expected to skip when CadQuery is not installed.

---

## Running tests

```bash
# Fast: run everything
conda run -n aieng311 python -m pytest -q

# Single file
conda run -n aieng311 python -m pytest tests/test_evidence_ledger.py -q

# Verbose with stdout
conda run -n aieng311 python -m pytest -v -s tests/test_cross_resource_consistency.py
```

Tests use only stdlib + `pyyaml` + `jsonschema`. No network access, no external CAD/CAE tools, no LLM calls.

---

## Project layout

```
src/aieng/          core package
  ai/               summary writer, patch proposer
  geometry/         topology extraction backends
  graph/            feature graph, AAG, constraints
  mcp/              MCP server (optional extra)
  patch/            patch executor
  provenance/       tool trace writer
  results/          evidence writer (ledger + claim map)
  task/             task spec + external tool requirements writers
  validation/       validation status writer
  validate.py       package validator (all resources)
  cli.py            CLI entry point (aieng ...)

schemas/            JSON Schema files for every structured resource
tests/              one test file per feature area
docs/               roadmap, command reference, MCP server, architecture
benchmarks/         agent handoff benchmark scaffold
scripts/            demo and fixture scripts
```

---

## Core design rules

### Execution boundary

`.aieng` **describes, references, configures, and records**. It does not execute.

- External CAD/CAE software is responsible for: geometry editing, mesh generation, solver execution, result generation, and manufacturing checks.
- `.aieng` core must not call subprocesses, CAD kernels, meshers, or solvers.
- Every new resource that touches execution state must have `const` guards in its JSON Schema enforcing this boundary (see `schemas/evidence_index.schema.json` for the pattern).

### Claim honesty

- `unsupported` means no evidence attached yet — not false, not violated.
- Claims about solver results, mesh generation, or geometry modification must not be set to `pass` without actual external evidence.
- `forbidden_claims` and `claim_policy` fields in task specs and validation status exist to make violations machine-detectable.

### No fabricated evidence

- `record_evidence_package()` guards against `aieng_core` producing `solver_result`, `mesh_evidence`, or `geometry_modification` items.
- Do not bypass these guards.

---

## What a new resource contribution looks like

A complete Phase contribution typically includes all of:

| Artifact | Location |
|----------|----------|
| JSON Schema with `const` guards | `schemas/<name>.schema.json` |
| Writer function | `src/aieng/<area>/<name>_writer.py` |
| CLI subcommand | `src/aieng/cli.py` |
| Validator checks | `src/aieng/validate.py` |
| MCP tool | `src/aieng/mcp/server.py` |
| Summary section | `src/aieng/ai/summary_writer.py` |
| Tests | `tests/test_<name>.py` |
| Docs update | `docs/roadmap.md`, `docs/mvp_checkpoint.md`, `docs/command_reference.md` |

Partial contributions are welcome — open an issue first and describe the scope so others can coordinate.

---

## PR checklist

- [ ] All tests pass: `python -m pytest -q` (zero failures)
- [ ] Execution boundary not violated: no subprocess calls, no CAD/CAE kernel imports
- [ ] Schema has `const` guards for boundary-relevant flags if a new resource was added
- [ ] `unsupported` is used correctly — not as a synonym for false
- [ ] `docs/roadmap.md` updated with implementation details
- [ ] `docs/mvp_checkpoint.md` updated (phase table, CLI list, resource table, test count)
- [ ] Schema `format_version` unchanged unless a breaking change is intentional (see `CHANGELOG.md` and `docs/schema_versioning.md`)
- [ ] No new runtime dependencies added without discussion

---

## Opening issues

- Use the issue templates if available.
- Issues tagged `good first issue` are self-contained and well-scoped — no coordination needed.
- Issues tagged `help wanted` may need discussion before starting.
- For large changes, open a draft PR early so the direction can be reviewed before the full implementation.

---

## Questions

Open a GitHub Discussion or issue. There is no Slack or Discord at this time.
