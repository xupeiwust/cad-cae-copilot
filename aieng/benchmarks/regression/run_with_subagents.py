"""Prepare a regression run for sub-agent execution.

This is the reference implementation of the "sub-agent per prompt" mode
described in AGENT_BENCHMARK_RUNBOOK.md. It initializes a run directory and
emits one isolated task per prompt. The parent agent (orchestrator) must then
spawn one sub-agent per task; each sub-agent sees only its single prompt and
must use its own reasoning to choose MCP tools.

Usage:
    cd aieng/benchmarks/regression
    python run_with_subagents.py --tags core --output runs/run_$(date -u +%Y%m%dT%H%M%SZ)

After the tasks are emitted, spawn one sub-agent per task and wait for all to
finish. Then run:

    python compare.py --baseline runs/run_<baseline> --current runs/run_<this>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SubagentTask(BaseModel):
    """Validated task payload for a single benchmark sub-agent."""

    prompt_id: str = Field(..., min_length=1)
    prompt_dir: str = Field(..., min_length=1)
    metrics_path: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    instructions: str = Field(..., min_length=1)


REGRESSION_DIR = Path(__file__).resolve().parent
INIT_RUN = REGRESSION_DIR / "init_run.py"


def init_run(tags: list[str], output: Path) -> Path:
    """Initialize the run directory and return its path."""
    cmd = [
        sys.executable,
        str(INIT_RUN),
        "--tags",
        *tags,
        "--output",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    return output


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def build_subagent_task(
    run_dir: Path, prompt_id: str, prompt_text: str, tags: list[str]
) -> SubagentTask:
    """Build the validated instruction payload for a single sub-agent."""
    prompt_dir = run_dir / prompt_id
    intent_only = "intent" in tags
    execution_guidance = (
        "This is an intent-only prompt. Do NOT execute CAD/CAE tools. "
        "Only classify the intent, set tool_sequence to [], and record resolved_intent."
        if intent_only
        else "Use MCP tools to fulfill the request. Create projects, run CAD/CAE operations, run critiques, etc. as needed."
    )
    instructions = f"""You are executing a single benchmark prompt in isolation.

The user just sent you this message:

--- USER MESSAGE START ---
{prompt_text}
--- USER MESSAGE END ---

Process it exactly as you would process a real user request. Use your own reasoning to decide which MCP tools to call. Do not process any other prompts. Do not write a batch script.

Working directory: {run_dir.parent}
Prompt directory: {prompt_dir}
Tags: {', '.join(tags)}

Steps:
1. Read {prompt_dir / 'prompt.md'} to confirm the request.
2. {execution_guidance}
3. Capture all required artifacts in {prompt_dir} (e.g. package.aieng, generated.step, thumbnail.png).
4. Write {prompt_dir / 'metrics.json'} with geometry metrics when applicable and always include:
   - "tool_sequence": list of tool names you called (empty for intent-only prompts)
   - "resolved_intent": one of create_geometry, modify_geometry, plan_simulation, critique, explain_project
5. Record the result by calling:
   python record.py --run {run_dir} --prompt {prompt_id} --status <passed|failed> --metrics {prompt_dir / 'metrics.json'} --artifacts <comma-separated artifact names>

If the prompt fails, still call record.py with --status failed and include an "error" field in metrics.json.
"""
    return SubagentTask(
        prompt_id=prompt_id,
        prompt_dir=str(prompt_dir),
        metrics_path=str(prompt_dir / "metrics.json"),
        tags=tags,
        instructions=instructions,
    )


def emit_tasks(run_dir: Path) -> Path:
    """Write subagent_tasks.json with one validated task per prompt."""
    manifest = load_manifest(run_dir)
    tasks: list[SubagentTask] = []

    for entry in sorted(manifest.get("prompts", []), key=lambda e: e["id"]):
        prompt_id = entry["id"]
        prompt_path = run_dir / prompt_id / "prompt.md"
        prompt_text = prompt_path.read_text(encoding="utf-8")
        plan_path = run_dir / prompt_id / "plan.json"
        tags: list[str] = []
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            tags = plan.get("tags", []) or []
        tasks.append(build_subagent_task(run_dir, prompt_id, prompt_text, tags))

    tasks_path = run_dir / "subagent_tasks.json"
    tasks_path.write_text(
        json.dumps([task.model_dump() for task in tasks], indent=2),
        encoding="utf-8",
    )
    return tasks_path


def print_task_summary(tasks_path: Path) -> None:
    tasks = [SubagentTask(**task) for task in json.loads(tasks_path.read_text(encoding="utf-8"))]
    print(f"Prepared {len(tasks)} sub-agent task(s) in: {tasks_path}")
    print()
    print("Next steps:")
    print("1. For each task in subagent_tasks.json, spawn an isolated sub-agent.")
    print("2. Give the sub-agent only the 'instructions' field as its system prompt.")
    print("3. Wait for every sub-agent to finish before moving to the next.")
    print("4. After all prompts are recorded, run compare.py.")
    print()
    print("Example task IDs:")
    for task in tasks:
        print(f"  - {task.prompt_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize a regression run and emit one sub-agent task per prompt."
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        default=["core"],
        help="Tags to filter prompts (default: core)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output run directory",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output)
    init_run(args.tags, output_dir)
    tasks_path = emit_tasks(output_dir)
    print_task_summary(tasks_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
