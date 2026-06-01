"""Debug script: test Claude CLI parameter combinations for autopilot adapter.

Tests each parameter set with a simple prompt and measures:
- Return code
- stdout (first 500 chars)
- stderr (first 500 chars)
- Wall-clock duration
- Whether it hung (exceeded timeout)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Simple test prompt that exercises the JSON schema output
TEST_PROMPT = json.dumps(
    {
        "objective": "Create a simple bracket with one mounting hole",
        "system_context": {
            "operating_rules": ["Use named parameters", "Set .label on each part"],
            "available_workbench_tools": [
                {"name": "cad.execute_build123d", "requires_approval": True}
            ],
            "required_action_json_schema": {
                "type": "object",
                "properties": {
                    "thought_summary": {"type": "string"},
                    "action": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "tool_name": {"type": "string"},
                            "input_json": {"type": "string"},
                        },
                    },
                },
            },
        },
        "archive_digest": "No prior history.",
        "working_memory": [],
    },
    ensure_ascii=False,
)

# Even simpler prompt for quick tests
SIMPLE_PROMPT = (
    "You are an AIENG Workbench agent. "
    "The user wants to create a simple Box in build123d. "
    "Return a JSON object with action.type='tool_call', action.tool_name='cad.execute_build123d', "
    "and action.input_json containing code that creates a Box and assigns it to variable 'result'."
)

SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "A_base_create_session",
        "desc": "Create new session with --session-id",
        "cmd": [
            "claude",
            "-p",
            "--bare",
            "--session-id", "a0b1c2d3-e4f5-6789-abcd-ef0123456789",
            "--output-format", "json",
            "--json-schema",
            json.dumps({
                "type": "object",
                "properties": {
                    "thought_summary": {"type": "string"},
                    "action": {"type": "object"},
                },
            }),
            "--permission-mode", "auto",
            "--tools", "Read,Edit,Grep,Glob,LS,Search",
        ],
        "timeout": 120,
    },
    {
        "name": "B_resume_session",
        "desc": "Resume specific session with --resume",
        "cmd": [
            "claude",
            "-p",
            "--bare",
            "--resume", "a0b1c2d3-e4f5-6789-abcd-ef0123456789",
            "--output-format", "json",
            "--json-schema",
            json.dumps({"type": "object", "properties": {"action": {"type": "object"}}}),
            "--permission-mode", "auto",
            "--tools", "Read,Edit,Grep,Glob,LS,Search",
        ],
        "timeout": 120,
    },
    {
        "name": "C_permission_acceptEdits",
        "desc": "--permission-mode acceptEdits",
        "cmd": [
            "claude",
            "-p",
            "--bare",
            "--session-id", "a0b1c2d3-e4f5-6789-abcd-ef0123456789",
            "--output-format", "json",
            "--json-schema",
            json.dumps({"type": "object", "properties": {"action": {"type": "object"}}}),
            "--permission-mode", "acceptEdits",
            "--tools", "Read,Edit,Grep,Glob,LS,Search",
        ],
        "timeout": 120,
    },
    {
        "name": "D_no_bare",
        "desc": "Without --bare (loads hooks, LSP, plugins)",
        "cmd": [
            "claude",
            "-p",
            "--session-id", "a0b1c2d3-e4f5-6789-abcd-ef0123456789",
            "--output-format", "json",
            "--json-schema",
            json.dumps({"type": "object", "properties": {"action": {"type": "object"}}}),
            "--permission-mode", "auto",
            "--tools", "Read,Edit,Grep,Glob,LS,Search",
        ],
        "timeout": 120,
    },
]


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    cmd = list(scenario["cmd"])
    timeout = scenario["timeout"]
    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
    })

    print(f"\n{'='*60}")
    print(f"Scenario: {scenario['name']} — {scenario['desc']}")
    print(f"Timeout: {timeout}s")
    print(f"Command: {' '.join(cmd[:6])} ...")

    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            input=SIMPLE_PROMPT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=env,
            cwd=str(Path(__file__).parent.parent.parent.parent),
        )
        duration = time.perf_counter() - start
        hung = False
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - start
        hung = True
        # Kill the process tree on Windows
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(exc.pid), "/T", "/F"], capture_output=True)
        result = exc

    stdout_preview = (result.stdout or "")[:500] if not hung else (exc.stdout or "")[:500]
    stderr_preview = (result.stderr or "")[:500] if not hung else (exc.stderr or "")[:500]

    report = {
        "name": scenario["name"],
        "duration_s": round(duration, 2),
        "hung": hung,
        "returncode": getattr(result, "returncode", None),
        "stdout_len": len(result.stdout or "") if not hung else len(exc.stdout or ""),
        "stderr_len": len(result.stderr or "") if not hung else len(exc.stderr or ""),
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
    }

    status = "HUNG/TIMEOUT" if hung else ("OK" if result.returncode == 0 else f"EXIT {result.returncode}")
    print(f"Result: {status} in {report['duration_s']}s")
    print(f"stdout ({report['stdout_len']} chars): {stdout_preview[:200]!r}")
    if stderr_preview:
        print(f"stderr ({report['stderr_len']} chars): {stderr_preview[:200]!r}")

    return report


CLAUDE_CMD = shutil.which(os.environ.get("AIENG_CLAUDE_CODE_COMMAND", "claude")) or "claude"


def main() -> None:
    print("Claude CLI Parameter Debug")
    print(f"Resolved CLI path: {CLAUDE_CMD}")

    version_result = subprocess.run([CLAUDE_CMD, "--version"], capture_output=True, text=True, shell=True)
    print(f"Version: {version_result.stdout.strip() or version_result.stderr.strip()}")
    print(f"Working dir: {Path(__file__).parent.parent.parent.parent}")
    print(f"Test prompt length: {len(SIMPLE_PROMPT)} chars")

    results = []
    for scenario in SCENARIOS:
        try:
            result = run_scenario(scenario)
            results.append(result)
        except Exception as exc:
            print(f"ERROR: {exc}")
            results.append({"name": scenario["name"], "error": str(exc)})

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        name = r["name"]
        if "error" in r:
            print(f"  {name}: ERROR — {r['error']}")
        elif r["hung"]:
            print(f"  {name}: HUNG after {r['duration_s']}s")
        elif r["returncode"] != 0:
            print(f"  {name}: FAILED (rc={r['returncode']}) in {r['duration_s']}s")
        else:
            print(f"  {name}: OK in {r['duration_s']}s")

    # Save full report
    report_path = Path(__file__).with_suffix(".report.json")
    report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    main()
