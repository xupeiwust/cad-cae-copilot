"""AI-readability / readiness report (Phase 20).

This module derives a structured readiness view from a `.aieng` package and
produces a small, deterministic Python dict that describes:

- which converter (if any) produced the package and at what capability level;
- what engineering information is available, partial, missing, or unsupported,
  pulled directly from `validation/completeness_report.json`;
- what external CAD/CAE actions would be required to advance the package
  further (derived from completeness recommended_actions and any external
  tool handoff resource already in the package).

The readiness report is **derived** and does not represent new engineering
truth. It does not run any external tool.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def build_readiness_report(package_path: str | Path) -> dict[str, Any]:
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            manifest = _read_json(package, "manifest.json")
            conversion_manifest = _read_optional_json(package, "provenance/conversion_manifest.json")
            converter_capabilities = _read_optional_json(
                package, "provenance/converter_capabilities.json"
            )
            completeness = _read_optional_json(package, "validation/completeness_report.json")
            external_tool_requirements = _read_optional_json(
                package, "task/external_tool_requirements.json"
            )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    if manifest is None:
        raise ValueError("package is missing manifest.json")

    converter_section = _converter_section(
        conversion_manifest=conversion_manifest,
        converter_capabilities=converter_capabilities,
        manifest=manifest,
    )

    information_state = _information_state_section(
        completeness=completeness,
        conversion_manifest=conversion_manifest,
    )

    recommended_external_actions = _recommended_external_actions(
        completeness=completeness,
        external_tool_requirements=external_tool_requirements,
    )

    return {
        "package_path": str(path),
        "model_id": manifest.get("model_id"),
        "source_mode": manifest.get("source_mode"),
        "converter": converter_section,
        "information_state": information_state,
        "recommended_external_actions": recommended_external_actions,
        "resources_present": sorted(names),
        "boundary_reminder": (
            ".aieng is a CAD/CAE-to-AI semantic conversion and packaging format. "
            "It does not execute solvers, meshers, optimizers, or CAD edits. "
            "Recommended actions describe what an EXTERNAL tool would do."
        ),
    }


def render_readiness_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"Readiness report for: {report.get('package_path')}")
    lines.append(f"model_id      : {report.get('model_id')}")
    lines.append(f"source_mode   : {report.get('source_mode')}")
    converter = report.get("converter") or {}
    lines.append(f"converter     : {converter.get('converter_id', '(none)')}")
    lines.append(f"  source_system           : {converter.get('source_system', '(unknown)')}")
    lines.append(f"  declared_levels         : {converter.get('declared_levels', [])}")
    lines.append(f"  achieved_levels         : {converter.get('achieved_levels', [])}")
    lines.append(f"  runtime_mode            : {converter.get('runtime_mode', '(unknown)')}")
    if converter.get("level_gap"):
        lines.append(f"  level_gap               : {converter['level_gap']}")
    coverage = converter.get("coverage_categories") or []
    if coverage:
        lines.append("  coverage_categories:")
        for entry in coverage:
            cat = entry.get("category", "?")
            status = entry.get("status", "?")
            lines.append(f"    {cat:25s}: {status}")
    info = report.get("information_state") or {}
    lines.append("information_state:")
    for status_key in ("available", "partial", "missing", "unknown", "unsupported", "not_applicable"):
        items = info.get(status_key) or []
        if items:
            lines.append(f"  {status_key:14s}: {', '.join(items)}")
    actions = report.get("recommended_external_actions") or []
    lines.append("recommended_external_actions:")
    if not actions:
        lines.append("  (none)")
    else:
        for action in actions:
            lines.append(
                f"  - [{action.get('source','?')}] {action.get('category','?')}: {action.get('action','?')}"
            )
            reason = action.get("reason")
            if reason:
                lines.append(f"      reason: {reason}")
    lines.append("")
    lines.append(report.get("boundary_reminder", ""))
    return "\n".join(lines)


def _converter_section(
    *,
    conversion_manifest: Any | None,
    converter_capabilities: Any | None,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(conversion_manifest, dict):
        if manifest.get("source_mode") == "converter":
            return {
                "converter_id": "(missing)",
                "source_system": "(unknown)",
                "declared_levels": [],
                "achieved_levels": [],
                "runtime_mode": "unknown",
                "warning": "source_mode is 'converter' but provenance/conversion_manifest.json is missing",
            }
        return None

    converter_block = conversion_manifest.get("converter") or {}
    declared = sorted(
        {
            int(entry.get("level"))
            for entry in conversion_manifest.get("declared_capability_levels", []) or []
            if isinstance(entry, dict) and isinstance(entry.get("level"), int)
        }
    )
    achieved = sorted(
        {
            int(entry.get("level"))
            for entry in conversion_manifest.get("achieved_capability_levels", []) or []
            if isinstance(entry, dict) and isinstance(entry.get("level"), int)
        }
    )
    gap = sorted(set(declared) - set(achieved))
    section = {
        "converter_id": converter_block.get("converter_id"),
        "display_name": converter_block.get("display_name"),
        "source_system": converter_block.get("source_system"),
        "converter_version": converter_block.get("converter_version"),
        "runtime_mode": converter_block.get("runtime_mode", "unknown"),
        "declared_levels": declared,
        "achieved_levels": achieved,
        "level_gap": gap,
        "coverage_categories": conversion_manifest.get("coverage_categories", []),
        "unsupported_or_missing": conversion_manifest.get("unsupported_or_missing", []),
        "uncertainty_notes": conversion_manifest.get("uncertainty_notes", []),
        "capabilities_profile_present": isinstance(converter_capabilities, dict),
    }
    return section


_COVERAGE_STATUS_TO_BUCKET: dict[str, str] = {
    "complete": "available",
    "partial": "partial",
    "inferred": "partial",
    "missing": "missing",
    "unsupported": "unsupported",
    "unavailable_in_source": "not_applicable",
    "unknown": "unknown",
}


def _information_state_section(
    *,
    completeness: Any | None,
    conversion_manifest: Any | None = None,
) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "available": [],
        "partial": [],
        "missing": [],
        "unknown": [],
        "unsupported": [],
        "conflicting": [],
        "not_applicable": [],
    }

    # Primary: adaptive coverage_categories from the conversion manifest.
    if isinstance(conversion_manifest, dict):
        for entry in conversion_manifest.get("coverage_categories", []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("category")
            status = entry.get("status")
            if isinstance(name, str) and isinstance(status, str):
                bucket = _COVERAGE_STATUS_TO_BUCKET.get(status)
                if bucket and bucket in buckets:
                    buckets[bucket].append(name)

    # Supplement with completeness report categories not already covered.
    already_covered = {item for items in buckets.values() for item in items}
    if isinstance(completeness, dict):
        for category in completeness.get("categories", []) or []:
            if not isinstance(category, dict):
                continue
            name = category.get("category")
            status = category.get("status")
            if isinstance(name, str) and name not in already_covered and isinstance(status, str):
                if status in buckets:
                    buckets[status].append(name)

    for items in buckets.values():
        items.sort()
    return buckets


def _recommended_external_actions(
    *,
    completeness: Any | None,
    external_tool_requirements: Any | None,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if isinstance(completeness, dict):
        for entry in completeness.get("next_recommended_actions", []) or []:
            if isinstance(entry, dict):
                actions.append(
                    {
                        "source": "completeness_report",
                        "category": str(entry.get("category", "")),
                        "action": str(entry.get("action", "")),
                        "reason": str(entry.get("reason", "")),
                    }
                )
    if isinstance(external_tool_requirements, dict):
        for capability in external_tool_requirements.get("required_capabilities", []) or []:
            if not isinstance(capability, dict):
                continue
            actions.append(
                {
                    "source": "external_tool_requirements",
                    "category": str(capability.get("capability", "")),
                    "action": str(capability.get("description", "")),
                    "reason": "External tool required to advance this capability; .aieng does not execute it.",
                }
            )
    return actions


def _read_json(package: zipfile.ZipFile, member: str) -> Any | None:
    if member not in set(package.namelist()):
        return None
    try:
        return json.loads(package.read(member))
    except json.JSONDecodeError:
        return None


def _read_optional_json(package: zipfile.ZipFile, member: str) -> Any | None:
    return _read_json(package, member)
