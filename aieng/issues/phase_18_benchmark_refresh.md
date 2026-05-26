---
title: "[Phase 18C] Benchmark refresh — SUPERSEDED"
labels: ["phase-18", "phase-18c", "superseded"]
status: superseded
---

## Status: Superseded

This issue draft has been superseded by [`phase_18c_semantic_coverage_benchmark.md`](phase_18c_semantic_coverage_benchmark.md), which reframes the benchmark work as a **general CAX semantic coverage** refresh rather than a fixed part-family list.

The reframing matters because `.aieng` does not declare a fixed set of supported part families. Fixtures are coverage probes for the *kinds of reasoning* the package should enable (reference correctness, completeness reasoning, unsupported-claim correctness, evidence trace, external-tool-boundary correctness) and for the failure modes the package should resist (hallucinated IDs, dangling references, auto-advanced claims, snapshot-as-evidence).

Please use [`phase_18c_semantic_coverage_benchmark.md`](phase_18c_semantic_coverage_benchmark.md) instead. No further edits should be made to this file.
