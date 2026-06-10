"""Validated package writes for optimization-study front-end artifacts."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng.audit_event import build_audit_event
from aieng.optimization_artifacts import (
    DESIGN_STUDY_PROBLEM_PATH,
    OPTIMIZATION_ARTIFACT_PATHS,
    validate_optimization_artifact_set,
)

from .project_io import (
    _append_audit_event_to_package,
    _read_revalidation_status,
    write_artifact_to_package,
)


def save_optimization_artifact(
    package_path: str | Path,
    artifact_kind: str,
    document: dict[str, Any],
    *,
    tool_name: str,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Validate and atomically save one optimization artifact.

    Existing optimization artifacts and the design-study problem are loaded so
    a write cannot introduce a conflicting study ID or silently fork the source
    variables/objective/constraints. The write records an audit event but does
    not modify geometry or revalidation state.
    """
    path = Path(package_path)
    artifact_path = OPTIMIZATION_ARTIFACT_PATHS.get(artifact_kind)
    if artifact_path is None:
        raise ValueError(f"unknown optimization artifact kind: {artifact_kind!r}")

    existing, design_study_problem = _load_artifact_set(path)
    candidate_set = {**existing, artifact_kind: document}
    issues = validate_optimization_artifact_set(
        candidate_set,
        design_study_problem=design_study_problem,
    )
    if issues:
        raise ValueError("invalid optimization artifact set: " + "; ".join(issues))

    before_revalidation = _read_revalidation_status(path)
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".json",
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)

    try:
        artifact = write_artifact_to_package(
            path,
            artifact_path,
            temp_path,
            overwrite=overwrite,
        )
    finally:
        temp_path.unlink(missing_ok=True)

    _append_audit_event_to_package(
        path,
        build_audit_event(
            tool=tool_name,
            event_type="optimization_artifact_written",
            status="completed",
            artifacts_written=[artifact_path],
            evidence_created=[],
            state_changes={
                "artifact_kind": artifact_kind,
                "study_id": document.get("study_id"),
                "candidate_ids": list(document.get("candidate_ids") or []),
                "baseline_modified": False,
            },
            geometry_revision=(
                before_revalidation.get("current_geometry_revision")
                if isinstance(before_revalidation, dict)
                else None
            ),
            revalidation_status=(
                "stale"
                if isinstance(before_revalidation, dict)
                and before_revalidation.get("requires_revalidation")
                else None
            ),
        ),
    )
    return {
        "ok": True,
        "artifact_kind": artifact_kind,
        "artifact_path": artifact["path"],
        "study_id": document.get("study_id"),
        "candidate_ids": list(document.get("candidate_ids") or []),
        "baseline_modified": False,
        "claim_advancement": "none",
    }


def _load_artifact_set(
    package_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if package_path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")
    with zipfile.ZipFile(package_path, "r") as package:
        names = set(package.namelist())
        if DESIGN_STUDY_PROBLEM_PATH not in names:
            raise ValueError(
                f"package is missing required source artifact {DESIGN_STUDY_PROBLEM_PATH}"
            )
        problem = json.loads(package.read(DESIGN_STUDY_PROBLEM_PATH))
        existing: dict[str, dict[str, Any]] = {}
        for kind, artifact_path in OPTIMIZATION_ARTIFACT_PATHS.items():
            if artifact_path in names:
                value = json.loads(package.read(artifact_path))
                if isinstance(value, dict):
                    existing[kind] = value
    return existing, problem
