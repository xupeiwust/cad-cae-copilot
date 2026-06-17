"""Compare two regression runs and emit a Markdown diff report.

Usage:
    python compare.py --baseline runs/run_20260610T000000Z --current runs/run_20260615T083000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from record import normalize_named_part_metrics


def load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def format_pct(value: float | str | None) -> str:
    """Format a percentage value for the diff report."""
    if value is None:
        return "0.0%"
    if isinstance(value, str):
        return value
    return f"{value:+.1f}%"


def metric_delta(baseline: dict[str, Any], current: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Compute a simple numeric delta for a scalar metric."""
    b = baseline.get(key)
    c = current.get(key)
    if b is None or c is None:
        return None
    try:
        b_val = float(b)
        c_val = float(c)
        delta = c_val - b_val
        if b_val == 0:
            delta_pct = None if c_val == 0 else "∞"
        else:
            delta_pct = delta / b_val * 100
        return {"baseline": b_val, "current": c_val, "delta": delta, "delta_pct": delta_pct}
    except (TypeError, ValueError):
        return None


def _metric_part_names(metrics: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    raw_named = metrics.get("named_parts")
    if isinstance(raw_named, list):
        names.update(str(item) for item in raw_named if str(item).strip())
    for section in ("volumes", "bounding_boxes"):
        raw = metrics.get(section)
        if isinstance(raw, dict):
            names.update(str(key) for key in raw if str(key).strip())
    return names


def _format_name_list(names: set[str]) -> str:
    return ", ".join(f"`{name}`" for name in sorted(names)) if names else "-"


def build_diff(baseline_dir: Path, current_dir: Path) -> str:
    baseline = load_manifest(baseline_dir)
    current = load_manifest(current_dir)

    lines = [
        "# Regression Diff Report",
        "",
        f"- Baseline: `{baseline.get('run_id')}`",
        f"- Current: `{current.get('run_id')}`",
        f"- Baseline started: {baseline.get('started_at', 'unknown')}",
        f"- Current started: {current.get('started_at', 'unknown')}",
        "",
        "## Summary",
        "",
    ]

    baseline_prompts = {p["id"]: p for p in baseline.get("prompts", [])}
    current_prompts = {p["id"]: p for p in current.get("prompts", [])}
    all_ids = sorted(set(baseline_prompts) | set(current_prompts))

    status_table = []
    for pid in all_ids:
        b_status = baseline_prompts.get(pid, {}).get("status", "missing")
        c_status = current_prompts.get(pid, {}).get("status", "missing")
        marker = ""
        if b_status != c_status:
            marker = " ⚠️"
        status_table.append(f"| {pid} | {b_status} | {c_status} |{marker}")

    lines.append("| Prompt | Baseline | Current |")
    lines.append("|---|---|---|")
    lines.extend(status_table)
    lines.append("")

    for pid in all_ids:
        b = baseline_prompts.get(pid, {})
        c = current_prompts.get(pid, {})
        lines.append(f"## {pid}")
        lines.append("")
        lines.append(f"- Baseline status: {b.get('status', 'missing')}")
        lines.append(f"- Current status: {c.get('status', 'missing')}")

        b_metrics = normalize_named_part_metrics(b.get("metrics", {}))
        c_metrics = normalize_named_part_metrics(c.get("metrics", {}))
        if b_metrics or c_metrics:
            lines.append("")
            lines.append("### Metrics")
            lines.append("")
            b_parts = _metric_part_names(b_metrics)
            c_parts = _metric_part_names(c_metrics)
            removed_parts = b_parts - c_parts
            added_parts = c_parts - b_parts
            if removed_parts or added_parts:
                lines.append("### Named Parts")
                lines.append("")
                lines.append(f"- Removed: {_format_name_list(removed_parts)}")
                lines.append(f"- Added: {_format_name_list(added_parts)}")
                if removed_parts and added_parts:
                    lines.append("- Warning: named parts changed; this may be a rename rather than a geometric addition/removal.")
                lines.append("")

            warnings = list(b_metrics.get("warnings") or []) + list(c_metrics.get("warnings") or [])
            if warnings:
                lines.append("### Warnings")
                lines.append("")
                for warning in warnings:
                    lines.append(f"- {warning}")
                lines.append("")

            lines.append("### Scalar Deltas")
            lines.append("")
            lines.append("| Metric | Baseline | Current | Delta |")
            lines.append("|---|---|---|---|")

            # Volume per named part
            b_volumes = b_metrics.get("volumes", {})
            c_volumes = c_metrics.get("volumes", {})
            for part in sorted(set(b_volumes) | set(c_volumes)):
                d = metric_delta(b_volumes, c_volumes, part)
                if d:
                    lines.append(
                        f"| {part}.volume | {d['baseline']:.2f} | {d['current']:.2f} | {d['delta']:+.2f} ({format_pct(d['delta_pct'])}) |"
                    )
                else:
                    lines.append(f"| {part}.volume | {b_volumes.get(part, '-')} | {c_volumes.get(part, '-')} | - |")

            # Bounding boxes per named part
            b_bboxes = b_metrics.get("bounding_boxes", {})
            c_bboxes = c_metrics.get("bounding_boxes", {})
            for part in sorted(set(b_bboxes) | set(c_bboxes)):
                for axis in ("x", "y", "z"):
                    d = metric_delta(b_bboxes.get(part, {}), c_bboxes.get(part, {}), axis)
                    if d:
                        lines.append(
                            f"| {part}.bbox.{axis} | {d['baseline']:.2f} | {d['current']:.2f} | {d['delta']:+.2f} ({format_pct(d['delta_pct'])}) |"
                        )

            # Part count
            d = metric_delta(b_metrics, c_metrics, "part_count")
            if d:
                lines.append(f"| part_count | {int(d['baseline'])} | {int(d['current'])} | {int(d['delta']):+d} |")

            # Resolved intent (text comparison)
            b_intent = b_metrics.get("resolved_intent")
            c_intent = c_metrics.get("resolved_intent")
            if b_intent is not None or c_intent is not None:
                b_intent_str = b_intent if b_intent is not None else "-"
                c_intent_str = c_intent if c_intent is not None else "-"
                lines.append(
                    f"| resolved_intent | {b_intent_str} | {c_intent_str} | {'⚠️' if b_intent != c_intent else ''} |"
                )

            # Tool sequence (text comparison)
            b_tools = b_metrics.get("tool_sequence")
            c_tools = c_metrics.get("tool_sequence")
            if b_tools is not None or c_tools is not None:
                if b_tools is None:
                    b_tools_str = "-"
                elif isinstance(b_tools, list):
                    b_tools_str = ", ".join(str(t) for t in b_tools)
                else:
                    b_tools_str = str(b_tools)
                if c_tools is None:
                    c_tools_str = "-"
                elif isinstance(c_tools, list):
                    c_tools_str = ", ".join(str(t) for t in c_tools)
                else:
                    c_tools_str = str(c_tools)
                match_marker = "⚠️" if b_tools != c_tools else ""
                lines.append(f"| tool_sequence | {b_tools_str} | {c_tools_str} | {match_marker} |")

        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two regression runs")
    parser.add_argument("--baseline", required=True, help="Baseline run directory")
    parser.add_argument("--current", required=True, help="Current run directory")
    parser.add_argument("--output", default=None, help="Output path for diff.md")
    args = parser.parse_args(argv)

    baseline_dir = Path(args.baseline)
    current_dir = Path(args.current)

    report = build_diff(baseline_dir, current_dir)

    output_path = Path(args.output) if args.output else current_dir / "diff_against_baseline.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Diff report written to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
