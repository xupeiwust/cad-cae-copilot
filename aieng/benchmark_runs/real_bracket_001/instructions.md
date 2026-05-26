# Instructions: Manual Benchmark (Real Bracket)

## 1) Prepare inputs

1. Ensure the environment is active and package is editable-installed:
   - `conda run -n aieng311 python -m pip install -e .`
2. Generate real STEP fixture if missing:
   - `conda run -n aieng311 python scripts/generate_real_bracket_step.py --overwrite`
3. Run the real-step pipeline:
   - `conda run -n aieng311 python scripts/run_real_step_demo.py`
4. Optionally prepare benchmark input copies:
   - `conda run -n aieng311 python scripts/prepare_real_benchmark_pack.py`

## 2) Condition A: raw STEP only

Provide only the file specified by `raw_step_input_spec.md` and ask all questions in `questions.md`.

## 3) Condition B: `.aieng` package resources

Provide files listed in `aieng_input_index.md` and ask the same questions in `questions.md`.

## 4) Scoring

Use `scoring_sheet.md` with the rubric under `benchmarks/scoring_rubric.md`.

## 5) Expected pattern

See `expected_observations.md` for expected differences between Condition A and Condition B.
