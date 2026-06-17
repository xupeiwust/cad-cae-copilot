"""Smoke tests for the regression benchmark kit plumbing.

These tests do not require a live MCP connection or LLM; they verify that
init_run.py, record.py, and compare.py work together.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REGRESSION_DIR = Path(__file__).resolve().parents[1]
INIT_RUN = REGRESSION_DIR / "init_run.py"
RECORD = REGRESSION_DIR / "record.py"
COMPARE = REGRESSION_DIR / "compare.py"


def test_init_run_creates_prompt_directories(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(INIT_RUN), "--tags", "core", "--output", str(tmp_path / "run1")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    run_dir = tmp_path / "run1"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert all(p["status"] == "pending" for p in manifest["prompts"])
    for prompt in manifest["prompts"]:
        assert (run_dir / prompt["id"] / "prompt.md").exists()
        assert (run_dir / prompt["id"] / "plan.json").exists()


def test_record_updates_manifest(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(INIT_RUN), "--tags", "core", "--output", str(tmp_path / "run1")],
        check=True,
        timeout=30,
    )
    run_dir = tmp_path / "run1"
    first_prompt = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["prompts"][0]["id"]

    metrics = {
        "named_parts": ["bracket"],
        "volumes": {"part_1": 12345.67},
        "bounding_boxes": {"part_1": {"x": 40.0, "y": 110.0, "z": 5.0}},
        "part_count": 1,
    }
    metrics_path = run_dir / first_prompt / "metrics.json"
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(RECORD),
            "--run",
            str(run_dir),
            "--prompt",
            first_prompt,
            "--status",
            "passed",
            "--metrics",
            str(metrics_path),
            "--artifacts",
            "package.aieng",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (run_dir / first_prompt / "result.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    entry = next(p for p in manifest["prompts"] if p["id"] == first_prompt)
    assert entry["status"] == "passed"
    assert entry["metrics"]["volumes"]["bracket"] == 12345.67
    assert "part_1" not in entry["metrics"]["volumes"]
    assert entry["metrics"]["bounding_boxes"]["bracket"]["x"] == 40.0


def test_record_migrates_unlabeled_part_keys_with_warning(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(INIT_RUN), "--tags", "core", "--output", str(tmp_path / "run1")],
        check=True,
        timeout=30,
    )
    run_dir = tmp_path / "run1"
    first_prompt = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["prompts"][0]["id"]

    metrics = {"named_parts": ["bracket"], "volumes": {"part_1": 10.0, "part_2": 2.0}}
    metrics_path = run_dir / first_prompt / "metrics.json"
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RECORD), "--run", str(run_dir), "--prompt", first_prompt, "--status", "passed", "--metrics", str(metrics_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    entry = next(p for p in json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["prompts"] if p["id"] == first_prompt)
    assert entry["metrics"]["volumes"]["bracket"] == 10.0
    assert entry["metrics"]["volumes"]["__unlabeled_2"] == 2.0
    assert any("__unlabeled_2" in warning for warning in entry["metrics"]["warnings"])


def test_compare_two_runs(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(INIT_RUN), "--tags", "core", "--output", str(tmp_path / "base")],
        check=True,
        timeout=30,
    )
    subprocess.run(
        [sys.executable, str(INIT_RUN), "--tags", "core", "--output", str(tmp_path / "curr")],
        check=True,
        timeout=30,
    )

    # Record one passed prompt in both runs with different metrics.
    for run_name, volume in [("base", 10000.0), ("curr", 12000.0)]:
        run_dir = tmp_path / run_name
        prompt_id = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["prompts"][0]["id"]
        metrics_path = run_dir / prompt_id / "metrics.json"
        metrics_path.write_text(json.dumps({"named_parts": ["bracket"], "volumes": {"part_1": volume}}), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(RECORD), "--run", str(run_dir), "--prompt", prompt_id, "--status", "passed", "--metrics", str(metrics_path)],
            check=True,
            timeout=30,
        )

    result = subprocess.run(
        [
            sys.executable,
            str(COMPARE),
            "--baseline",
            str(tmp_path / "base"),
            "--current",
            str(tmp_path / "curr"),
            "--output",
            str(tmp_path / "diff.md"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    diff = (tmp_path / "diff.md").read_text(encoding="utf-8")
    assert "Baseline" in diff
    assert "bracket.volume" in diff
    # Verify the delta between 10000 and 12000 is rendered.
    assert any(token in diff for token in ("+2000", "2000.00", "20.0%"))


def test_compare_reports_named_part_add_remove_warning(tmp_path: Path) -> None:
    for run_name, part_name in [("base", "bracket"), ("curr", "mount")]:
        subprocess.run(
            [sys.executable, str(INIT_RUN), "--tags", "core", "--output", str(tmp_path / run_name)],
            check=True,
            timeout=30,
        )
        run_dir = tmp_path / run_name
        prompt_id = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["prompts"][0]["id"]
        metrics_path = run_dir / prompt_id / "metrics.json"
        metrics_path.write_text(json.dumps({"volumes": {part_name: 100.0}, "part_count": 1}), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(RECORD), "--run", str(run_dir), "--prompt", prompt_id, "--status", "passed", "--metrics", str(metrics_path)],
            check=True,
            timeout=30,
        )

    result = subprocess.run(
        [
            sys.executable,
            str(COMPARE),
            "--baseline",
            str(tmp_path / "base"),
            "--current",
            str(tmp_path / "curr"),
            "--output",
            str(tmp_path / "diff.md"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    diff = (tmp_path / "diff.md").read_text(encoding="utf-8")
    assert "Removed: `bracket`" in diff
    assert "Added: `mount`" in diff
    assert "may be a rename" in diff
