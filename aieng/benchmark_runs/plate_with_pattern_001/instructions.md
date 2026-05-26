# Instructions

## 1. Prepare fixture inputs

Run:

```bash
python scripts/prepare_plate_with_pattern_benchmark_pack.py
```

This generates:

- build/plate_with_pattern_001_rich.aieng
- build/plate_with_pattern_001_sparse.aieng
- benchmark_runs/plate_with_pattern_001/input/condition_b_rich/*
- benchmark_runs/plate_with_pattern_001/input/condition_b_sparse/*

## 2. Run manual benchmark prompts

Use questions.md for both variants.

- rich: point the AI to input/condition_b_rich files
- sparse: point the AI to input/condition_b_sparse files

## 3. Score with two-dimension rubric

Use benchmarks/scoring_rubric.md and scoring_sheet.md.

## 4. Guardrails

- No RAG, MCP tools, plugins, skills, or solver/CAD calls.
- Any ungrounded factual claim should be scored as hallucination.
- unsupported is not false.
