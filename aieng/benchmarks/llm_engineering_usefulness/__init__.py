"""Automated A/B benchmark — does .aieng help an LLM understand CAD/CAE state?

Phase 30 of the LLM-assisted CAD/CAE design roadmap (see github issue #54).

Complements (does NOT replace) the existing manual ``benchmarks/ai_usefulness/``:

- ``ai_usefulness/`` — human-conducted, broad qualitative + quantitative coverage,
  one scenario per directory, scored against a 7-dimension rubric.
- ``llm_engineering_usefulness/`` — automated via the ``inspect_ai`` harness,
  deterministic A/B comparison, agentic Condition B with AIENG tools, narrower
  per-scenario rubric.
"""
