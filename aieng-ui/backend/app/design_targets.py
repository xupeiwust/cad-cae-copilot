"""Design Targets authoring and import for the AIENG Decision Review Workbench.

Provides read/write access to the design-target artifact inside the `.aieng`
package.  Writes are explicit user actions and mutate only the design-target
artifact — no CAD edits, no solver runs, no claim advancement.
"""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

from .config import Settings
from .copilot_loop import _resolve_package
from .project_io import get_project, project_dir, write_artifact_to_package

# Artifact path inside the .aieng package (matches existing convention).
_DESIGN_TARGETS_PATH = "task/design_targets.yaml"

# Supported operators (expanded from existing comparators).
_SUPPORTED_OPERATORS = {
    "<=",
    ">=",
    "<",
    ">",
    "==",
    "within_range",
    "preserve",
    "priority",
    "reduce_by_at_least",
    "increase_by_at_least",
    "reduce_by_percent",
    "increase_by_percent",
}

_SUPPORTED_PRIORITIES = {"required", "preferred", "informational", "high", "medium", "low", "critical"}

_MAX_TARGETS = 100
_MAX_STRING_LEN = 500
_MAX_ID_LEN = 128

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validation_error(field: str, message: str) -> dict[str, Any]:
    return {"field": field, "message": message}


def validate_design_target(target: Any, index: int) -> list[dict[str, Any]]:
    """Validate a single design target. Returns a list of error dicts."""
    errors: list[dict[str, Any]] = []
    if not isinstance(target, dict):
        errors.append(_validation_error(f"targets[{index}]", "Target must be an object."))
        return errors

    tid = target.get("target_id") or target.get("id")
    if not tid:
        errors.append(_validation_error(f"targets[{index}].target_id", "target_id is required."))
    elif not isinstance(tid, str):
        errors.append(_validation_error(f"targets[{index}].target_id", "target_id must be a string."))
    elif len(tid) > _MAX_ID_LEN:
        errors.append(_validation_error(f"targets[{index}].target_id", f"target_id exceeds {_MAX_ID_LEN} characters."))
    elif not _SAFE_ID_RE.match(tid):
        errors.append(_validation_error(f"targets[{index}].target_id", "target_id contains unsafe characters. Use alphanumeric, underscore, or hyphen."))

    label = target.get("label") or target.get("target_type")
    if not label:
        errors.append(_validation_error(f"targets[{index}].label", "label is required."))
    elif not isinstance(label, str):
        errors.append(_validation_error(f"targets[{index}].label", "label must be a string."))
    elif len(label) > _MAX_STRING_LEN:
        errors.append(_validation_error(f"targets[{index}].label", f"label exceeds {_MAX_STRING_LEN} characters."))

    metric = target.get("metric")
    if not metric:
        # Fallback to target_type for backward compatibility with existing fixtures
        metric = target.get("target_type")
    if not metric:
        errors.append(_validation_error(f"targets[{index}].metric", "metric is required."))
    elif not isinstance(metric, str):
        errors.append(_validation_error(f"targets[{index}].metric", "metric must be a string."))
    elif len(metric) > _MAX_STRING_LEN:
        errors.append(_validation_error(f"targets[{index}].metric", f"metric exceeds {_MAX_STRING_LEN} characters."))

    operator = target.get("operator") or target.get("comparator")
    if not operator:
        errors.append(_validation_error(f"targets[{index}].operator", "operator is required."))
    elif operator not in _SUPPORTED_OPERATORS:
        errors.append(_validation_error(f"targets[{index}].operator", f"Unsupported operator: {operator}."))

    value = target.get("value") if target.get("value") is not None else target.get("threshold")
    threshold_min = target.get("threshold_min")
    threshold_max = target.get("threshold_max")
    if value is None and operator == "within_range" and threshold_min is not None and threshold_max is not None:
        value = threshold_max
    if value is None and operator in {"preserve", "priority"}:
        value = 0
    if value is None:
        errors.append(_validation_error(f"targets[{index}].value", "value is required."))
    elif not isinstance(value, (int, float)):
        errors.append(_validation_error(f"targets[{index}].value", "value must be numeric."))
    elif isinstance(value, float) and (value != value):  # NaN check
        errors.append(_validation_error(f"targets[{index}].value", "value must not be NaN."))

    if operator == "within_range":
        for field, raw in (("threshold_min", threshold_min), ("threshold_max", threshold_max)):
            if raw is not None and not isinstance(raw, (int, float)):
                errors.append(_validation_error(f"targets[{index}].{field}", f"{field} must be numeric."))
        if threshold_min is None and threshold_max is None:
            errors.append(_validation_error(f"targets[{index}].threshold_min", "within_range requires threshold_min/threshold_max or value."))

    priority = target.get("priority")
    if priority is not None and priority not in _SUPPORTED_PRIORITIES:
        errors.append(_validation_error(f"targets[{index}].priority", f"Unsupported priority: {priority}."))

    for field in ("unit", "scope", "rationale", "load_case_id"):
        val = target.get(field)
        if isinstance(val, str) and len(val) > _MAX_STRING_LEN:
            errors.append(_validation_error(f"targets[{index}].{field}", f"{field} exceeds {_MAX_STRING_LEN} characters."))

    return errors


def validate_design_targets_document(doc: Any) -> list[dict[str, Any]]:
    """Validate a design-targets document. Returns a list of error dicts."""
    errors: list[dict[str, Any]] = []
    if not isinstance(doc, dict):
        errors.append(_validation_error("root", "Document must be an object."))
        return errors

    targets = doc.get("targets")
    if targets is None:
        errors.append(_validation_error("targets", "targets array is required."))
        return errors
    if not isinstance(targets, list):
        errors.append(_validation_error("targets", "targets must be an array."))
        return errors
    if len(targets) > _MAX_TARGETS:
        errors.append(_validation_error("targets", f"Too many targets: {len(targets)} (max {_MAX_TARGETS})."))

    seen_ids: set[str] = set()
    for i, target in enumerate(targets):
        t_errors = validate_design_target(target, i)
        errors.extend(t_errors)
        tid = (target.get("target_id") or target.get("id")) if isinstance(target, dict) else None
        if tid and isinstance(tid, str):
            if tid in seen_ids:
                errors.append(_validation_error(f"targets[{i}].target_id", f"Duplicate target_id: {tid}."))
            seen_ids.add(tid)

    return errors


def get_design_targets(settings: Settings, project_id: str) -> dict[str, Any]:
    """Read design targets from the project's .aieng package.

    Returns a structured response with the targets document, or an empty
    targets list with a warning if the artifact is missing.
    """
    try:
        pkg = _resolve_package(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "ok": False,
                "project_id": project_id,
                "artifact_path": None,
                "document": None,
                "targets": [],
                "warnings": ["Project has no .aieng package."],
            }
        raise

    with zipfile.ZipFile(pkg, "r") as zf:
        names = set(zf.namelist())
        # Try the primary path, then fallback paths used by existing code.
        for path in ("task/design_targets.yaml", "task/design_targets.yml", "targets/design_targets.json"):
            if path in names:
                raw = zf.read(path).decode("utf-8", errors="replace")
                try:
                    doc = yaml.safe_load(raw)
                except Exception:
                    doc = None
                if doc is None:
                    return {
                        "ok": False,
                        "project_id": project_id,
                        "artifact_path": path,
                        "document": None,
                        "targets": [],
                        "warnings": [f"Design target artifact exists at {path} but is not valid YAML/JSON."],
                    }
                targets = doc.get("targets") if isinstance(doc, dict) else None
                if not isinstance(targets, list):
                    return {
                        "ok": False,
                        "project_id": project_id,
                        "artifact_path": path,
                        "document": doc,
                        "targets": [],
                        "warnings": [f"Design target artifact at {path} has no 'targets' array."],
                    }
                return {
                    "ok": True,
                    "project_id": project_id,
                    "artifact_path": path,
                    "document": doc,
                    "targets": targets,
                    "warnings": [],
                }

    return {
        "ok": True,
        "project_id": project_id,
        "artifact_path": None,
        "document": None,
        "targets": [],
        "warnings": ["No design target artifact found in package."],
    }


def save_design_targets(
    settings: Settings,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate and save design targets into the project's .aieng package.

    Writes only the design-target artifact.  Does not modify CAD/CAE
    artifacts, run solvers, or advance claims.
    """
    pkg = _resolve_package(settings, project_id)

    # Normalize payload to a document with targets array.
    if isinstance(payload, list):
        doc: dict[str, Any] = {"schema_version": "0.1", "targets": payload}
    elif isinstance(payload, dict):
        doc = dict(payload)
        if "targets" not in doc:
            doc["targets"] = []
    else:
        raise HTTPException(status_code=400, detail="Payload must be an object or an array of targets.")

    errors = validate_design_targets_document(doc)
    if errors:
        raise HTTPException(status_code=422, detail={"ok": False, "errors": errors})

    # Write to a temp YAML file, then into the package.
    tmp = Path(tempfile.gettempdir()) / f"design_targets_{project_id}.yaml"
    tmp.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")

    try:
        artifact = write_artifact_to_package(pkg, _DESIGN_TARGETS_PATH, tmp, overwrite=True)
    finally:
        if tmp.exists():
            tmp.unlink()

    return {
        "ok": True,
        "project_id": project_id,
        "artifact_path": artifact["path"],
        "document": doc,
        "targets": doc.get("targets", []),
        "warnings": [],
    }
