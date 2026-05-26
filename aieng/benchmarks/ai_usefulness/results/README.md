# AI Usefulness Benchmark Results

No real benchmark runs have been recorded yet.

---

## Phase 21B — Run structure ready

The run-record structure for the first benchmark run is in place. See
[`../HOWTO_RUN.md`](../HOWTO_RUN.md) for step-by-step execution instructions.

### Template

[`run_record_template.json`](run_record_template.json) is a schema-valid template with
sentinel placeholder values. Copy it to `run_YYYYMMDDTHHMMSSZ.json`, replace all
`FILL_IN` markers and zero scores with actual run data, then validate:

```bash
python -c "
import json, sys
try:
    import jsonschema
    schema = json.loads(open('benchmarks/ai_usefulness/results.schema.json').read())
    result = json.loads(open('benchmarks/ai_usefulness/results/run_YYYYMMDDTHHMMSSZ.json').read())
    v = jsonschema.Draft202012Validator(schema)
    errs = list(v.iter_errors(result))
    if errs:
        for e in errs: print('FAIL', e.message)
        sys.exit(1)
    print('PASS  schema valid')
except ImportError:
    print('WARN  jsonschema not installed')
"
```

### File naming

```
results/run_20260601T143022Z.json   ← actual run
results/run_record_template.json    ← template (do not use as a result)
```

The `run_id` inside the file must match the filename stem.

---

## Important limitation

One run on one scenario is **not sufficient for broad conclusions** about `.aieng`'s
utility. See the "One-scenario limitation" section in [`../HOWTO_RUN.md`](../HOWTO_RUN.md).

---

## Phase 21C — Per-run directory structure

Each complete run is stored as a self-contained subdirectory under `runs/`:

```
runs/
  run_TEMPLATE/              ← copy this to start a new run
    condition_a_answers.md
    condition_b_answers.md
    scoring_notes.md
    result.json
    observation_report.md
  run_YYYYMMDDTHHMMSSZ/      ← one directory per completed run
    ...
```

See [`runs/README.md`](runs/README.md) for the step-by-step workflow.

---

## Recording a run

1. Copy `runs/run_TEMPLATE/` to `runs/run_YYYYMMDDTHHMMSSZ/`.
2. Follow [`../HOWTO_RUN.md`](../HOWTO_RUN.md) Step 7 for the full fill-in workflow.
3. Use [`../result_template.md`](../result_template.md) for a human-readable companion record if desired.
