:warning: **For AI agents only** — This file is the entry point for an AI agent running the regression benchmark. Human readers should start with `README.md`.

---

# Workbench Regression Benchmark — Agent Runbook

## Your goal

Execute a fixed set of prompts against the workbench through MCP and produce a run directory that can be compared against a previous baseline.

Each prompt must be treated as an independent user message and executed in isolation. Preferably, spawn one sub-agent per prompt so that the executor only ever sees a single user request and must use its own reasoning to choose MCP tools. Do not change the prompts. Do not skip prompts unless explicitly instructed by the user. Record honest results, including failures.

## Prerequisites

1. You are connected to the workbench MCP server (`aieng-workbench`).
2. The workbench backend is running and reachable.
3. You can use tools such as `aieng.create_project`, `cad.execute_build123d`, `cad.critique`, `cae.prepare_solver_run`, `cae.run_solver`, `opt.run_topology_optimization`, etc.
4. (Optional but recommended) Your agent runtime supports spawning isolated sub-agents.

## Execution mode

This benchmark is designed to exercise the real agent path: tool choice, intent routing, approval handling, and final artifacts. To prevent the meta-task "run the benchmark" from collapsing into a batch script, execute prompts in one of the following modes.

### Mode A: Sub-agent per prompt (preferred)

If your runtime supports spawning sub-agents (e.g. Claude Code tasks, Codex agents, or an `Agent` tool), create one isolated sub-agent for each prompt:

1. Initialize the run directory with `init_run.py`.
2. For each prompt directory in sorted order:
   1. Spawn a sub-agent whose entire context is limited to this single prompt.
   2. Give it this exact instruction:
      - Read `<run_dir>/<prompt_id>/prompt.md`.
      - Treat its contents exactly as if the user just sent it to you.
      - Use your own reasoning to choose and call MCP tools.
      - Capture the required artifacts in the prompt directory.
      - Write `metrics.json` in the prompt directory, including `tool_sequence` and `resolved_intent`.
      - Call `record.py` to record the result.
   3. Wait for the sub-agent to finish before starting the next one.
3. After all prompts are recorded, call `compare.py`.

A reference task generator is provided in `run_with_subagents.py`. It initializes a run and emits one task description per prompt; the parent agent still spawns the sub-agents itself.

### Mode B: Sequential processing in the same session

If your runtime does not support sub-agents, process prompts one at a time in your own session:

1. Read one `prompt.md`.
2. Treat it as a new user message.
3. Use reasoning to choose and call MCP tools.
4. Capture artifacts, write `metrics.json`, and call `record.py`.
5. Move to the next prompt only after recording the current one.

### Forbidden

Do **not** write a Python/shell script to batch-run all prompts. Do **not** submit prompts to the workbench chat/autopilot endpoint and treat the backend autopilot response as the benchmark result — you are the agent being evaluated, not the workbench autopilot.

## Quick workflow

```bash
# 1. Initialize a run directory
cd aieng/benchmarks/regression
python init_run.py --tags core --output runs/run_$(date -u +%Y%m%dT%H%M%SZ)

# 2. Execute each prompt in isolation (see Execution mode above).
#    Preferred: spawn one sub-agent per prompt.
#    Fallback: process prompts sequentially in your own session.
#    Example after a sub-agent or your own session finishes prompt 001:
python record.py \
  --run runs/run_20260615T083000Z \
  --prompt 001_cad_create_bracket \
  --status passed \
  --metrics runs/run_20260615T083000Z/001_cad_create_bracket/metrics.json \
  --artifacts package.aieng,generated.step

# 3. After all prompts are recorded, compare against a baseline:
python compare.py \
  --baseline runs/run_20260610T000000Z \
  --current runs/run_20260615T083000Z
```

## Prompt categories and expected MCP tools

### CAD create prompts (001–005)

These prompts ask you to create geometry. You will likely need:
- `aieng.create_project` or equivalent to create a fresh project.
- `cad.execute_build123d` (or `cad.plan_build123d_skill`) with build123d code that satisfies the prompt.
- Capture:
  - `package.aieng`
  - `generated.step`
  - thumbnail image if available
  - `metrics.json` with volumes and bounding boxes (you may compute these with build123d)

### CAD modify prompts (006–008)

Each prompt has `seed_package` in its front-matter. Start from that seed package (or recreate the base geometry yourself). You will likely need:
- Load/import the seed project.
- `cad.edit_parameter`, `cad.replace_part`, or `cad.execute_build123d` in `append` mode.
- Capture modified artifacts and metric deltas.

### CAE prompts (009–012)

These prompts ask you to run simulation. You will likely need:
- Ensure the model has material, loads, and constraints configured.
- `cae.prepare_solver_run`.
- `cae.run_solver`.
- `cae.extract_solver_results`.
- Capture:
  - solver status
  - `computed_metrics.json` or extracted metrics
  - `.frd` result file if available
  - For `012_cae_missing_load`, the expected outcome is a readiness/honesty report stating that required inputs are missing.

### Optimization / design study prompts (013–015)

These prompts ask you to optimize or run a design study. You will likely need:
- `opt.run_topology_optimization`, `opt.sizing_sweep`, or the full `opt.propose_candidates` → `opt.run_candidates` → `opt.rank_candidates` flow.
- Capture the optimized geometry and ranking metrics.

### Critique prompts (016–017)

These prompts ask for manufacturability/assembly feedback. You will likely need:
- `cad.critique` or `cad.design_review`.
- Capture the findings list.

### Autopilot intent prompts (018–022)

These prompts are short and ambiguous by design. Do **not** execute CAD/CAE tools for them. Instead:
1. Read the prompt as a user message.
2. Use your own reasoning to classify the intent:
   - "Create an aluminum L-bracket..." → `create_geometry` → `/build`
   - "Make the wall thicker." → `modify_geometry` → `/modify`
   - "Run a stress analysis..." → `plan_simulation` → `/simulate`
   - "Is this bracket manufacturable?" → `critique` → `/critique`
   - "Explain this part." → `explain_project` → `/explain`
3. Record `resolved_intent` and `command` in `metrics.json` with an empty `tool_sequence`.

## Recording a result

For every prompt you execute, call `record.py`:

```bash
python record.py \
  --run <run_directory> \
  --prompt <prompt_id> \
  --status {passed|failed|skipped} \
  [--metrics <path/to/metrics.json>] \
  [--artifacts <comma-separated filenames relative to prompt dir>]
```

Create `metrics.json` as a plain object, for example:

```json
{
  "named_parts": ["bracket"],
  "volumes": {"bracket": 21748.67},
  "bounding_boxes": {"bracket": {"x": 40.0, "y": 110.0, "z": 5.0}},
  "part_count": 1,
  "tool_sequence": ["aieng.create_project", "cad.execute_build123d"],
  "resolved_intent": "create_geometry"
}
```

Use stable named-part labels from `cad.execute_build123d` / `feature_graph` as
metric keys. Do not write `part_1`, `part_2`, etc. unless a part is genuinely
unlabeled; `record.py` will migrate legacy `part_N` keys to labels when
`named_parts` is present and will flag unknown labels as `__unlabeled_N`.

Always include `tool_sequence` (the list of tool names called) and `resolved_intent` (e.g. `create_geometry`, `modify_geometry`, `plan_simulation`, `critique`, `explain_project`) so the benchmark captures the reasoning path, not just the geometry.

If a prompt fails, set `--status failed` and include an `error` field in `metrics.json`:

```json
{"error": "cad.execute_build123d returned solver_status: failed"}
```

## Tag conventions

- `core`: fastest, most stable prompts — run these first
- `cad_create`, `cad_modify`, `cae`, `optimization`, `critique`, `intent`: capability groups
- `mechanical`: mechanical engineering prompts

Default tag for a quick check: `--tags core`.

## Approval handling

The workbench gates mutation tools (`cad.execute_build123d`, `cae.run_solver`, etc.) behind approval. In a benchmark context, you may auto-approve your own tool calls if your MCP client supports it. Record honestly if a tool was blocked by approval.

## What to capture per prompt

In each prompt subdirectory, ensure these files exist when applicable:

- `prompt.md` — written by `init_run.py`
- `result.json` — written by `record.py`
- `metrics.json` — optional, referenced by `record.py`
- `package.aieng` — resulting package
- `generated.step` — exported STEP
- `thumbnail.png` — render if available
- `tool_trace.jsonl` — list of tool calls and responses (highly recommended)

## Final step: compare

After all prompts are recorded:

```bash
python compare.py \
  --baseline runs/<previous_run> \
  --current runs/<this_run>
```

The report is written to `<this_run>/diff_against_baseline.md`. A human will review it.
