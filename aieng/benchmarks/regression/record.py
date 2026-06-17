"""Record the result of a single prompt execution in a benchmark run.

Usage:
    python record.py --run runs/run_xxx --prompt 001_cad_create_bracket \\
        --status passed --metrics path/to/metrics.json --artifacts package.aieng,generated.step
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


def load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def _part_index(key: str) -> int | None:
    if not key.startswith("part_"):
        return None
    suffix = key[len("part_"):]
    if not suffix.isdigit():
        return None
    value = int(suffix)
    return value if value > 0 else None


def _extract_named_parts(metrics: dict[str, Any]) -> list[str]:
    """Return the benchmark's best known named-part order.

    Agents normally write ``named_parts`` from ``cad.execute_build123d``. Older
    runs sometimes carried labels under ``part_labels`` or embedded per-part
    objects; accept those shapes so old metrics can be migrated without reruns.
    """
    for key in ("named_parts", "part_labels"):
        raw = metrics.get(key)
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]

    raw_parts = metrics.get("parts")
    if isinstance(raw_parts, list):
        labels: list[str] = []
        for part in raw_parts:
            if isinstance(part, dict):
                label = part.get("label") or part.get("name")
                if label:
                    labels.append(str(label))
        if labels:
            return labels

    report = metrics.get("geometry_report")
    if isinstance(report, dict):
        raw_report_parts = report.get("parts")
        if isinstance(raw_report_parts, list):
            labels = [
                str(part.get("name"))
                for part in raw_report_parts
                if isinstance(part, dict) and part.get("name")
            ]
            if labels:
                return labels
    return []


def normalize_named_part_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy ``part_N`` metric keys to stable named-part labels.

    Unknown labels become ``__unlabeled_N`` and a warning is recorded, so the
    benchmark never silently pretends a synthetic key is a semantic part name.
    """
    normalized = copy.deepcopy(metrics)
    labels = _extract_named_parts(normalized)
    warnings = list(normalized.get("warnings") or [])

    def label_for(key: str) -> str:
        index = _part_index(key)
        if index is None:
            return key
        if index <= len(labels):
            return labels[index - 1]
        synthetic = f"__unlabeled_{index}"
        warnings.append(f"Metric key {key} had no named-part label; migrated to {synthetic}.")
        return synthetic

    for section in ("volumes", "bounding_boxes"):
        raw = normalized.get(section)
        if not isinstance(raw, dict):
            continue
        migrated: dict[str, Any] = {}
        for key, value in raw.items():
            new_key = label_for(str(key))
            if new_key in migrated and new_key != key:
                warnings.append(f"Metric key {key} collided with existing label {new_key}; keeping latest value.")
            migrated[new_key] = value
        normalized[section] = migrated

    if labels:
        normalized["named_parts"] = labels
    elif any(isinstance(normalized.get(section), dict) for section in ("volumes", "bounding_boxes")):
        inferred = sorted({
            str(key)
            for section in ("volumes", "bounding_boxes")
            for key in (normalized.get(section) or {})
            if not str(key).startswith("__unlabeled_")
        })
        if inferred:
            normalized["named_parts"] = inferred

    if warnings:
        normalized["warnings"] = warnings
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a single prompt result")
    parser.add_argument("--run", required=True, help="Run directory")
    parser.add_argument("--prompt", required=True, help="Prompt id")
    parser.add_argument("--status", required=True, choices=["passed", "failed", "skipped"])
    parser.add_argument("--metrics", help="Path to metrics JSON file")
    parser.add_argument("--artifacts", help="Comma-separated artifact filenames (relative to prompt dir)")
    parser.add_argument("--error", help="Short error message if status is failed")
    args = parser.parse_args(argv)

    run_dir = Path(args.run)
    prompt_dir = run_dir / args.prompt
    if not prompt_dir.exists():
        print(f"Prompt directory does not exist: {prompt_dir}")
        return 1

    manifest = load_manifest(run_dir)
    metrics: dict[str, Any] = {}
    if args.metrics:
        metrics_path = Path(args.metrics)
        if not metrics_path.exists():
            print(f"Metrics file not found: {metrics_path}")
            return 1
        metrics_text = metrics_path.read_text(encoding="utf-8")
        metrics = json.loads(metrics_text)
        metrics = normalize_named_part_metrics(metrics)
        # Copy metrics into prompt dir for self-containment.
        (prompt_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    if args.error:
        metrics["error"] = args.error

    artifacts = [a.strip() for a in args.artifacts.split(",") if a.strip()] if args.artifacts else []
    missing = [a for a in artifacts if not (prompt_dir / a).exists()]
    if missing:
        print(f"Warning: artifacts not found in {prompt_dir}: {missing}")

    result = {
        "id": args.prompt,
        "status": args.status,
        "metrics": metrics,
        "artifacts": artifacts,
    }
    (prompt_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    # Update manifest entry.
    found = False
    for entry in manifest.get("prompts", []):
        if entry["id"] == args.prompt:
            entry["status"] = args.status
            entry["metrics"] = metrics
            entry["artifacts"] = artifacts
            found = True
            break
    if not found:
        manifest.setdefault("prompts", []).append(result)

    save_manifest(run_dir, manifest)
    print(f"Recorded {args.prompt}: {args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
