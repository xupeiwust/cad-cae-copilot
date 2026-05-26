# Instructions

## 1. Prepare fixture inputs

```powershell
$env:PYTHONPATH='src'
python scripts/prepare_flange_benchmark_pack.py
```

This generates:

- `build/flange_001_rich.aieng`
- `build/flange_001_sparse.aieng`
- `benchmark_runs/flange_001/input/condition_b_rich/*`
- `benchmark_runs/flange_001/input/condition_b_sparse/*`

## 2. Validate packages

```powershell
$env:PYTHONPATH='src'
python -m aieng.cli validate build/flange_001_rich.aieng
python -m aieng.cli ref-check build/flange_001_rich.aieng
python -m aieng.cli validate build/flange_001_sparse.aieng
python -m aieng.cli ref-check build/flange_001_sparse.aieng
```

Both should pass with no FAIL lines.

## 3. Run manual benchmark prompts

Use [questions.md](questions.md) for both variants.

- **rich**: point the AI to `input/condition_b_rich/` files
- **sparse**: point the AI to `input/condition_b_sparse/` files

## 4. Score with two-dimension rubric

Use `benchmarks/scoring_rubric.md` and [scoring_sheet.md](scoring_sheet.md).

## 5. Guardrails

- No RAG, MCP tools, plugins, skills, or solver/CAD calls during evaluation.
- Any ungrounded factual claim should be scored as hallucination.
- `unsupported` is not `false`.
- Two interfaces are protected (`feat_bolt_hole_pattern_001` and `feat_pipe_bore_001`);
  the AI must respect both without being explicitly reminded.
