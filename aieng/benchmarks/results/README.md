# Benchmark Results

This directory stores structured benchmark outputs written by `scripts/run_benchmark.py`.

## File format

Each run is written as `run_<timestamp>.json`, for example `run_20260511T103000Z.json`.

The JSON must conform to `benchmarks/results.schema.json`.

Each result records:

- provider and model metadata;
- executed condition set (`A`, `B`, or both);
- raw answers returned by the model;
- per-condition 8-category rubric scores;
- per-condition totals and A/B delta;
- cost estimate or token estimate metadata;
- warnings about missing optional inputs.

## Scoring

Scoring is aligned to the manual benchmark baseline:

- 8 categories
- `honesty`: `0`, `1`, or `2`
- `usefulness`: `0`, `1`, or `2`
- per-condition maximum: `16` honesty and `16` usefulness

The runner keeps raw question answers, then aggregates scoring at the category level so the totals match the manual `16`-point benchmark framing.

## Benchmark restrictions

The benchmark call must not use:

- RAG
- MCP tools
- skills
- plugins
- CAD tool calls
- solver calls

The goal is to measure file-native understanding from the provided benchmark inputs only.
