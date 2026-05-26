"""Read-only design target inspection for .aieng packages.

Provides helpers to inspect:
- task/design_targets.yaml
- results/result_summary.json#design_target_comparisons

All functions are read-only. They do not write to packages, do not
mutate claim_map.json, and do not invoke CAD/CAE operations.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def _is_zipped_aieng(path: Path) -> bool:
    return path.is_file() and path.suffix == ".aieng"


def _try_load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def _try_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _try_load_yaml_from_zip(
    zf: zipfile.ZipFile, name: str
) -> dict[str, Any] | None:
    try:
        with zf.open(name) as f:
            import yaml

            return yaml.safe_load(f) or {}
    except (KeyError, Exception):
        return None


def _try_load_json_from_zip(
    zf: zipfile.ZipFile, name: str
) -> dict[str, Any] | None:
    try:
        with zf.open(name) as f:
            return json.load(f)
    except (KeyError, json.JSONDecodeError, Exception):
        return None


def read_design_targets(package_path: str) -> dict[str, Any]:
    """Read task/design_targets.yaml from an .aieng package.

    Returns a structured result. Never raises — errors are returned as
    ok=False with a clear message.
    """
    path = Path(package_path)
    if not path.exists():
        return {
            "ok": False,
            "package_path": str(path),
            "has_design_targets": False,
            "error": f"Package path does not exist: {path}",
            "warnings": [],
        }

    raw: dict[str, Any] | None = None
    warnings: list[str] = []
    found = False

    try:
        if _is_zipped_aieng(path):
            with zipfile.ZipFile(path, "r") as zf:
                name = "task/design_targets.yaml"
                found = name in zf.namelist()
                if found:
                    raw = _try_load_yaml_from_zip(zf, name)
        elif path.is_dir():
            file_path = path / "task" / "design_targets.yaml"
            found = file_path.exists()
            if found:
                raw = _try_load_yaml(file_path)
        else:
            return {
                "ok": False,
                "package_path": str(path),
                "has_design_targets": False,
                "error": f"Package path is not a directory or .aieng file: {path}",
                "warnings": [],
            }
    except zipfile.BadZipFile as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "has_design_targets": False,
            "error": f"Malformed .aieng zip: {exc}",
            "warnings": [],
        }
    except Exception as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "has_design_targets": False,
            "error": f"Failed to read design targets: {type(exc).__name__}: {exc}",
            "warnings": [],
        }

    if not found:
        warnings.append("task/design_targets.yaml not found in package.")
        return {
            "ok": True,
            "package_path": str(path),
            "has_design_targets": False,
            "target_set_id": None,
            "format_version": None,
            "targets": [],
            "claim_policy": {},
            "warnings": warnings,
        }

    if raw is None:
        return {
            "ok": False,
            "package_path": str(path),
            "has_design_targets": False,
            "error": "task/design_targets.yaml is malformed and could not be parsed.",
            "warnings": [],
        }

    if not isinstance(raw, dict):
        return {
            "ok": False,
            "package_path": str(path),
            "has_design_targets": False,
            "error": "task/design_targets.yaml is malformed: expected a mapping, got a non-dict.",
            "warnings": [],
        }

    return {
        "ok": True,
        "package_path": str(path),
        "has_design_targets": True,
        "target_set_id": raw.get("target_set_id"),
        "format_version": raw.get("format_version"),
        "targets": raw.get("targets", []),
        "claim_policy": raw.get("claim_policy", {}),
        "warnings": warnings,
    }


def read_design_target_comparisons(package_path: str) -> dict[str, Any]:
    """Read results/result_summary.json#design_target_comparisons from an .aieng package.

    Returns a structured result. Never raises — errors are returned as
    ok=False with a clear message.
    """
    path = Path(package_path)
    if not path.exists():
        return {
            "ok": False,
            "package_path": str(path),
            "has_comparisons": False,
            "error": f"Package path does not exist: {path}",
            "warnings": [],
        }

    result_summary: dict[str, Any] | None = None
    warnings: list[str] = []
    found = False

    try:
        if _is_zipped_aieng(path):
            with zipfile.ZipFile(path, "r") as zf:
                name = "results/result_summary.json"
                found = name in zf.namelist()
                if found:
                    result_summary = _try_load_json_from_zip(zf, name)
        elif path.is_dir():
            file_path = path / "results" / "result_summary.json"
            found = file_path.exists()
            if found:
                result_summary = _try_load_json(file_path)
        else:
            return {
                "ok": False,
                "package_path": str(path),
                "has_comparisons": False,
                "error": f"Package path is not a directory or .aieng file: {path}",
                "warnings": [],
            }
    except zipfile.BadZipFile as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "has_comparisons": False,
            "error": f"Malformed .aieng zip: {exc}",
            "warnings": [],
        }
    except Exception as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "has_comparisons": False,
            "error": f"Failed to read result summary: {type(exc).__name__}: {exc}",
            "warnings": [],
        }

    if not found:
        warnings.append("results/result_summary.json not found in package.")
        return {
            "ok": True,
            "package_path": str(path),
            "has_comparisons": False,
            "design_target_comparisons": None,
            "summary": None,
            "warnings": warnings,
        }

    if result_summary is None:
        return {
            "ok": False,
            "package_path": str(path),
            "has_comparisons": False,
            "error": "results/result_summary.json is malformed and could not be parsed.",
            "warnings": [],
        }

    if not isinstance(result_summary, dict):
        return {
            "ok": False,
            "package_path": str(path),
            "has_comparisons": False,
            "error": "results/result_summary.json is malformed: expected a mapping, got a non-dict.",
            "warnings": [],
        }

    comparisons = result_summary.get("design_target_comparisons")
    if comparisons is None:
        warnings.append("results/result_summary.json exists but contains no design_target_comparisons block.")
        return {
            "ok": True,
            "package_path": str(path),
            "has_comparisons": False,
            "design_target_comparisons": None,
            "summary": None,
            "warnings": warnings,
        }

    return {
        "ok": True,
        "package_path": str(path),
        "has_comparisons": True,
        "design_target_comparisons": comparisons,
        "summary": comparisons.get("summary") if isinstance(comparisons, dict) else None,
        "warnings": warnings,
    }


def summarize_design_target_context(package_path: str) -> dict[str, Any]:
    """Produce a compact agent-friendly summary of design targets and comparisons.

    This is a convenience wrapper over read_design_targets and
    read_design_target_comparisons. It is read-only and does not
    mutate the package.
    """
    targets_result = read_design_targets(package_path)
    comparisons_result = read_design_target_comparisons(package_path)

    lines: list[str] = []
    warnings = list(targets_result.get("warnings", [])) + list(comparisons_result.get("warnings", []))

    if targets_result.get("has_design_targets"):
        targets = targets_result.get("targets", [])
        lines.append(f"Design targets present: {len(targets)}")
        for t in targets:
            tid = t.get("target_id", "unknown")
            desc = t.get("description", "")
            priority = t.get("priority", "")
            lines.append(f"- {tid}: {desc} [{priority}]")
    else:
        lines.append("No design targets found in package.")

    if comparisons_result.get("has_comparisons"):
        comp = comparisons_result.get("design_target_comparisons", {})
        summary = comp.get("summary", {}) if isinstance(comp, dict) else {}
        total = summary.get("total", 0)
        passed = summary.get("pass", 0)
        failed = summary.get("fail", 0)
        unknown = summary.get("unknown", 0)
        not_evaluated = summary.get("not_evaluated", 0)
        lines.append("")
        lines.append("Comparison status:")
        lines.append(f"- {passed} pass")
        lines.append(f"- {failed} fail")
        lines.append(f"- {unknown} unknown")
        lines.append(f"- {not_evaluated} not_evaluated")
        lines.append(f"- {total} total")
    else:
        lines.append("No design target comparisons available.")

    lines.append("")
    lines.append("Boundary:")
    lines.append("Artifact-level requirements only. Claims are not advanced automatically.")
    lines.append("Pass/fail comparisons are artifact-threshold checks, not engineering certification.")

    return {
        "ok": targets_result.get("ok", False) and comparisons_result.get("ok", False),
        "package_path": str(Path(package_path)),
        "has_design_targets": targets_result.get("has_design_targets", False),
        "has_comparisons": comparisons_result.get("has_comparisons", False),
        "summary_text": "\n".join(lines),
        "warnings": warnings,
    }
