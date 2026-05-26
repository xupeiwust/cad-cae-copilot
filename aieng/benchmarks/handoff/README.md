# Agent Handoff Benchmark Scaffold

This directory defines a manual benchmark scaffold for evaluating whether a general AI can correctly understand `.aieng` as a **CAD/CAE-side semantic export and evidence package** and produce a correct external CAD/CAE handoff plan.

The benchmark is **not** about AI orchestration, tool execution, MCP capability, or solver performance. It is about whether the package contents alone give an agent enough structured information to reason correctly about task intent, execution boundaries, evidence requirements, claim honesty, and provenance expectations — before any external tool runs.

---

## Purpose

The handoff benchmark tests the operational phase of AI-assisted CAX work:

> Given a `.aieng` package with task spec, external tool requirements, evidence index, and claim map, can a general AI produce a correct, bounded handoff plan without fabricating execution evidence or violating the execution boundary?

This is complementary to the earlier AI understanding benchmark (`benchmarks/`), which tests whether `.aieng` improves general engineering understanding compared to raw STEP input. The handoff benchmark specifically targets Phase 14 resources: `task/task_spec.yaml`, `task/external_tool_requirements.json`, `results/evidence_index.json`, and `results/claim_map.json`.

---

## What this benchmark tests

1. **Task intent understanding** — can the agent read and cite `task/task_spec.yaml`?
2. **CAD/CAE execution boundary** — does the agent know what `.aieng` does vs. what external tools do?
3. **Protected region and interface awareness** — does the agent read `ai/protected_regions.json` and `objects/interface_graph.json`?
4. **Evidence ledger understanding** — can the agent read `results/evidence_index.json` and enumerate available evidence?
5. **Claim-map honesty** — does the agent correctly distinguish pass/fail/unsupported claims?
6. **Handoff plan usefulness** — can the agent produce a bounded, grounded handoff plan?
7. **Provenance and writeback awareness** — does the agent know what external tools must write back?
8. **Unsupported-claim refusal** — does the agent refuse to assert solver/stress/safety claims without evidence?

---

## What is excluded

This benchmark intentionally excludes all external augmentation:

- MCP tool calls
- RAG or retrieval augmentation
- Skills, plugins, or LLM fine-tuning
- External CAD tool calls (FreeCAD, Gmsh, CATIA, etc.)
- External CAE tool calls (CalculiX, Abaqus, etc.)
- Solver execution or result generation
- LLM API calls beyond prompting with package contents
- Manufacturing checker calls

These approaches are useful in production, but they must not be prerequisites for the benchmark. The question is whether the package contents alone carry enough structured information for correct reasoning.

---

## Input

See [input_index.md](input_index.md) for the full list of input files and how to extract them for the benchmark.

The benchmark uses a single `.aieng` package that has been fully prepared through Phase 14C: it includes task spec, external tool requirements, evidence index, and claim map in addition to geometry, topology, features, constraints, simulation setup, AAG, and validation status.

---

## Questions

See [questions.md](questions.md) for the full question set (10 question groups, approximately 30 individual questions).

---

## Scoring

See [scoring_rubric.md](scoring_rubric.md) for the 0/1/2 per-category rubric across 8 categories.

Maximum score: **16** (8 categories × 2 points each).

Unlike the earlier understanding benchmark, this benchmark does not use a two-condition comparison (raw STEP vs. `.aieng`). It evaluates a single `.aieng` package with Phase 14C resources against the expected behaviors defined in [expected_observations.md](expected_observations.md).

---

## Recording results

Use [result_template.md](result_template.md) to record a benchmark run. Save completed results under `benchmarks/handoff/results/` with a timestamped filename.

---

## Relation to the project thesis

`.aieng` is a **CAD/CAE-side semantic export and evidence package**. The handoff benchmark tests the operational claim:

> A general AI reading `.aieng` package contents should be able to reason correctly about task intent, execution boundaries, and evidence requirements — and produce a bounded handoff plan — without calling any external tools and without fabricating engineering evidence.

This benchmark does not test raw STEP vs. `.aieng` understanding (that is the earlier benchmark). It tests whether the Phase 14 task-contract and evidence resources specifically enable correct agent reasoning about the handoff boundary.

---

## Files in this directory

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `questions.md` | Full question set for the benchmark |
| `scoring_rubric.md` | 0/1/2 per-category scoring rubric |
| `expected_observations.md` | Canonical expected behaviors for a well-performing agent |
| `input_index.md` | List of input files and extraction instructions |
| `result_template.md` | Template for recording a benchmark run |
| `results.schema.json` | Optional JSON schema for structured result records |
