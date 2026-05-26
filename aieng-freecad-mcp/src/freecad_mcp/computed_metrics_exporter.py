"""Computed metrics exporter for `results/computed_metrics.json`.

Normalizes externally computed post-processing metrics into the canonical
Phase 6 schema. Does not execute solvers or parse VTU/FRD/ODB fields.

Typical usage:
    from freecad_mcp.computed_metrics_exporter import export_computed_metrics
    result = export_computed_metrics(
        "postprocess_result.json",
        "results/computed_metrics.json",
        load_case_id="load_case_001",
        software="FreeCAD FEM / CalculiX",
    )

Input formats supported:
- Flat JSON with keys like ``max_von_mises_stress_mpa``, ``max_displacement_mm``,
  ``factor_of_safety``.
- JSON already close to the Phase 6 ``computed_metrics`` schema (validated
  and normalized rather than blindly copied).
- CSV with columns ``name``, ``value``, ``unit``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


COMPUTED_METRICS_SCHEMA_VERSION = "0.1"

# Mapping from common flat keys → canonical metric key + default unit
_FLAT_KEY_MAP: dict[str, tuple[str, str | None]] = {
    "max_von_mises_stress_mpa": ("max_von_mises_stress", "MPa"),
    "max_von_mises_stress": ("max_von_mises_stress", "MPa"),
    "max_displacement_mm": ("max_displacement", "mm"),
    "max_displacement": ("max_displacement", "mm"),
    "factor_of_safety": ("minimum_safety_factor", None),
    "minimum_safety_factor": ("minimum_safety_factor", None),
    "safety_factor": ("minimum_safety_factor", None),
}


class ComputedMetricsExportError(Exception):
    """Raised when the export cannot produce valid output."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


def export_computed_metrics(
    input_path: str | Path,
    output_path: str | Path,
    *,
    load_case_id: str = "load_case_001",
    software: str | None = None,
    tool: str = "freecad_mcp_postprocessor",
    source_files: list[str] | None = None,
) -> dict[str, Any]:
    """Read external metrics, normalize to Phase 6 schema, and write JSON.

    Args:
        input_path: Path to input JSON or CSV produced by an external
            post-processor.
        output_path: Destination path for ``computed_metrics.json``.
        load_case_id: Identifier for the load case these metrics belong to.
        software: Name/version of the software that produced the metrics.
        tool: Name of the tool/adapter that performed the export.
        source_files: Original solver result files the metrics were derived from.

    Returns:
        The normalized ``computed_metrics`` dict.

    Raises:
        ComputedMetricsExportError: If the input is unreadable or produces
            no valid metrics.
        FileNotFoundError: If ``input_path`` does not exist.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw = _read_input(input_path)
    if raw is None:
        raise ComputedMetricsExportError(
            f"Could not parse input file: {input_path}",
            {"input_path": str(input_path)},
        )

    # If input already looks like a Phase 6 computed_metrics dict, validate it.
    if isinstance(raw, dict) and "load_cases" in raw and "metrics_source" in raw:
        normalized = _normalize_computed_metrics(raw)
    else:
        normalized = _normalize_from_flat(raw, load_case_id, tool, software, source_files)

    if not normalized["load_cases"] or not any(
        lc.get("metrics") for lc in normalized["load_cases"]
    ):
        normalized["warnings"].append(
            "No recognized metrics found in input; output contains empty load case."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, sort_keys=False)

    return normalized


def _read_input(input_path: Path) -> Any | None:
    """Read and parse JSON or CSV input. Return None on failure."""
    suffix = input_path.suffix.lower()

    if suffix == ".csv":
        return _read_csv(input_path)

    # Default to JSON
    try:
        with input_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _read_csv(input_path: Path) -> list[dict[str, Any]] | None:
    """Read a CSV and return a list of row dicts."""
    try:
        with input_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return rows
    except (csv.Error, OSError):
        return None


def _normalize_computed_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an input that already looks like Phase 6 schema."""
    metrics_source = raw.get("metrics_source") or {}
    load_cases = raw.get("load_cases") or []
    if not isinstance(load_cases, list):
        load_cases = []

    normalized_load_cases: list[dict[str, Any]] = []
    for lc in load_cases:
        if not isinstance(lc, dict):
            continue
        lc_id = lc.get("id") or "load_case_001"
        metrics = lc.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}
        normalized_metrics: dict[str, Any] = {}
        for key in ("max_von_mises_stress", "max_displacement", "minimum_safety_factor"):
            if key in metrics and isinstance(metrics[key], dict) and metrics[key].get("value") is not None:
                normalized_metrics[key] = _normalize_metric_object(metrics[key])
        normalized_load_cases.append({"id": lc_id, "metrics": normalized_metrics})

    return {
        "schema_version": COMPUTED_METRICS_SCHEMA_VERSION,
        "metrics_source": {
            "tool": metrics_source.get("tool") or "external_postprocessor",
            "software": metrics_source.get("software"),
            "source_files": metrics_source.get("source_files") or [],
        },
        "load_cases": normalized_load_cases,
        "warnings": raw.get("warnings") or [],
    }


def _normalize_from_flat(
    raw: dict[str, Any] | list[dict[str, Any]],
    load_case_id: str,
    tool: str,
    software: str | None,
    source_files: list[str] | None,
) -> dict[str, Any]:
    """Normalize a flat JSON dict or CSV row list into Phase 6 schema."""
    metrics: dict[str, Any] = {}
    warnings: list[str] = []

    if isinstance(raw, list):
        # CSV-style row list
        for row in raw:
            if not isinstance(row, dict):
                continue
            name = row.get("name") or row.get("metric")
            value = row.get("value")
            unit = row.get("unit")
            if name is None or value is None:
                continue
            mapped = _FLAT_KEY_MAP.get(name)
            if mapped:
                canonical_key, default_unit = mapped
                metrics[canonical_key] = {
                    "value": _coerce_numeric(value),
                    "unit": unit or default_unit,
                    "field": canonical_key,
                }
            else:
                warnings.append(f"Unrecognized metric name skipped: {name}")
    elif isinstance(raw, dict):
        for key, value in raw.items():
            if value is None:
                continue
            mapped = _FLAT_KEY_MAP.get(key)
            if mapped:
                canonical_key, default_unit = mapped
                # If value is already a metric object, keep it
                if isinstance(value, dict) and "value" in value:
                    metrics[canonical_key] = _normalize_metric_object(value)
                else:
                    metrics[canonical_key] = {
                        "value": _coerce_numeric(value),
                        "unit": default_unit,
                        "field": canonical_key,
                    }
            else:
                warnings.append(f"Unrecognized metric key skipped: {key}")

    return {
        "schema_version": COMPUTED_METRICS_SCHEMA_VERSION,
        "metrics_source": {
            "tool": tool,
            "software": software,
            "source_files": source_files or [],
        },
        "load_cases": [{"id": load_case_id, "metrics": metrics}],
        "warnings": warnings,
    }


def _normalize_metric_object(metric: dict[str, Any]) -> dict[str, Any]:
    """Ensure a metric object has the minimum required fields."""
    result: dict[str, Any] = {
        "value": metric.get("value"),
        "unit": metric.get("unit"),
    }
    if "location" in metric and isinstance(metric["location"], dict):
        result["location"] = metric["location"]
    if "field" in metric:
        result["field"] = metric["field"]
    if "basis" in metric:
        result["basis"] = metric["basis"]
    return result


def _coerce_numeric(value: Any) -> float | int | Any:
    """Try to coerce a value to a numeric type."""
    if isinstance(value, (int, float)):
        return value
    try:
        # Try int first, then float
        return int(value)
    except (ValueError, TypeError):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="computed-metrics-export",
        description="Normalize external post-processing metrics into computed_metrics.json",
    )
    parser.add_argument("--input", required=True, help="Path to input JSON or CSV")
    parser.add_argument("--output", required=True, help="Path for computed_metrics.json output")
    parser.add_argument("--load-case-id", default="load_case_001", help="Load case identifier")
    parser.add_argument("--software", default=None, help="Software that produced the metrics")
    parser.add_argument("--tool", default="freecad_mcp_postprocessor", help="Exporter tool name")
    parser.add_argument(
        "--source-file",
        action="append",
        dest="source_files",
        default=[],
        help="Original solver result file(s); may be given multiple times",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = export_computed_metrics(
            args.input,
            args.output,
            load_case_id=args.load_case_id,
            software=args.software,
            tool=args.tool,
            source_files=args.source_files or [],
        )
        # Machine-readable JSON on stdout; logs to stderr
        print(json.dumps({"status": "ok", "output": args.output, "metrics_count": _count_metrics(result)}))
        return 0
    except ComputedMetricsExportError as exc:
        print(json.dumps({"status": "error", "message": exc.message, "details": exc.details}), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1


def _count_metrics(result: dict[str, Any]) -> int:
    count = 0
    for lc in result.get("load_cases", []):
        count += len(lc.get("metrics", {}))
    return count


if __name__ == "__main__":
    sys.exit(main())
