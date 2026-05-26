"""Design targets via chat: parse natural language into structured targets and persist them.

Handles phrases like:
  "set max stress to 250 MPa"
  "displacement must be less than 0.5 mm"
  "stress limit 200 MPa"
  "add a displacement target <= 1 mm"

No LLM call needed — regex + keyword heuristics cover the common patterns.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException


# ── Metric + operator vocabulary ──────────────────────────────────────────────

_STRESS_KEYWORDS = frozenset({
    "stress", "von mises", "von_mises", "mises", "sigma", "sigma_max",
    "max stress", "maximum stress",
})
_DISP_KEYWORDS = frozenset({
    "displacement", "deflection", "deformation", "delta", "u_max",
    "max displacement", "maximum displacement", "max deflection",
})

# Longer phrases first so they match before shorter substrings
_OPERATOR_PHRASES: list[tuple[str, str]] = [
    ("must not exceed", "<="),
    ("should not exceed", "<="),
    ("no more than", "<="),
    ("not more than", "<="),
    ("not exceed", "<="),
    ("less than or equal", "<="),
    ("less than or equal to", "<="),
    ("at most", "<="),
    ("below", "<="),
    ("under", "<="),
    ("less than", "<"),
    ("greater than or equal", ">="),
    ("greater than or equal to", ">="),
    ("at least", ">="),
    ("above", ">="),
    ("over", ">="),
    ("greater than", ">"),
    ("should be", "<="),   # default sense: "stress should be 250 MPa" → ≤
    ("must be", "<="),
    ("<=", "<="),
    (">=", ">="),
    ("<", "<"),
    (">", ">"),
    ("=", "=="),
]

_UNIT_ALIASES: dict[str, str] = {
    "mpa": "MPa", "megapascal": "MPa", "mega pascal": "MPa",
    "gpa": "GPa", "gigapascal": "GPa",
    "kpa": "kPa",
    "pa": "Pa",
    "mm": "mm", "millimeter": "mm", "millimetre": "mm",
    "cm": "cm",
    "m": "m",
    "kn": "kN",
    "n": "N",
    "%": "%",
}

_METRIC_LABELS: dict[str, str] = {
    "von_mises_max_mpa": "Max von Mises stress",
    "max_displacement_mm": "Max displacement",
}
_METRIC_DEFAULT_UNITS: dict[str, str] = {
    "von_mises_max_mpa": "MPa",
    "max_displacement_mm": "mm",
}


def _detect_metric(lower: str) -> str | None:
    for kw in _STRESS_KEYWORDS:
        if kw in lower:
            return "von_mises_max_mpa"
    for kw in _DISP_KEYWORDS:
        if kw in lower:
            return "max_displacement_mm"
    return None


def _detect_operator(lower: str) -> str:
    for phrase, op in _OPERATOR_PHRASES:
        if phrase in lower:
            return op
    return "<="  # sensible engineering default: "stress 250 MPa" means ≤ 250


def _extract_value_and_unit(lower: str) -> tuple[float, str] | None:
    # Match number (int or decimal) optionally followed by a unit keyword
    pattern = r"(\d+(?:\.\d+)?)\s*(mpa|gpa|kpa|pa|kn|mm|cm|%|n\b)?"
    for match in re.finditer(pattern, lower):
        value = float(match.group(1))
        raw_unit = (match.group(2) or "").strip()
        unit = _UNIT_ALIASES.get(raw_unit, raw_unit.upper() if raw_unit else "")
        return value, unit
    return None


# ── Public parse function ─────────────────────────────────────────────────────

def parse_target_from_text(text: str) -> dict[str, Any] | None:
    """Extract a structured design target from a natural-language chat message.

    Returns a target dict compatible with design_targets.yaml schema, or None if
    the text doesn't describe a recognisable target.
    """
    lower = text.lower()

    metric = _detect_metric(lower)
    if metric is None:
        return None

    extracted = _extract_value_and_unit(lower)
    if extracted is None:
        return None

    value, unit = extracted
    if not unit:
        unit = _METRIC_DEFAULT_UNITS.get(metric, "")

    operator = _detect_operator(lower)
    label = _METRIC_LABELS.get(metric, metric)

    # Build a stable, readable target_id
    safe_val = str(int(value)) if value == int(value) else str(value).replace(".", "p")
    target_id = f"chat_{metric}_{safe_val}"

    return {
        "target_id": target_id,
        "label": label,
        "metric": metric,
        "operator": operator,
        "value": value,
        "unit": unit,
        "priority": "required",
    }


# ── Package I/O ───────────────────────────────────────────────────────────────

def _read_targets(package_path: Path) -> list[dict[str, Any]]:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            for candidate in ("task/design_targets.yaml", "task/design_targets.yml"):
                if candidate in zf.namelist():
                    raw = zf.read(candidate).decode("utf-8", errors="replace")
                    doc = yaml.safe_load(raw)
                    if isinstance(doc, dict):
                        targets = doc.get("targets") or []
                        return targets if isinstance(targets, list) else []
    except Exception:
        pass
    return []


def _write_targets(package_path: Path, targets: list[dict[str, Any]]) -> None:
    """Atomically replace task/design_targets.yaml in the package."""
    doc = {"schema_version": "0.1", "targets": targets}
    content = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True).encode()
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with zipfile.ZipFile(package_path, "r") as src, \
             zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename != "task/design_targets.yaml":
                    dst.writestr(item, src.read(item.filename))
            dst.writestr("task/design_targets.yaml", content)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── Orchestration ─────────────────────────────────────────────────────────────

def add_target_from_chat(
    settings: Any,
    project_id: str,
    text: str,
) -> dict[str, Any]:
    """Parse a natural-language target, upsert it into design_targets.yaml, return summary."""
    from .copilot_loop import _resolve_package

    try:
        package_path = _resolve_package(settings, project_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Project package not found")

    target = parse_target_from_text(text)
    if target is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not parse a design target from the message. "
                "Try: \"set max stress to 250 MPa\" or \"displacement must be less than 0.5 mm\"."
            ),
        )

    existing = _read_targets(package_path)

    # Upsert: replace existing target with same ID, otherwise append
    updated = [t for t in existing if t.get("target_id") != target["target_id"]]
    was_update = len(updated) < len(existing)
    updated.append(target)

    _write_targets(package_path, updated)

    return {
        "ok": True,
        "project_id": project_id,
        "target": target,
        "action": "updated" if was_update else "added",
        "total_targets": len(updated),
        "artifact_path": "task/design_targets.yaml",
    }
