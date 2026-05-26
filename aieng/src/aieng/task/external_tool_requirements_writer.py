from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

EXTERNAL_TOOL_REQUIREMENTS_PATH = "task/external_tool_requirements.json"
TASK_SPEC_PATH = "task/task_spec.yaml"
TASK_DIR = "task/"


def write_external_tool_requirements_package(
    package_path: str | Path,
    *,
    handoff_id: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Write task/external_tool_requirements.json to an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    effective_handoff_id = (handoff_id or "handoff_001").strip()
    if not effective_handoff_id:
        raise ValueError("handoff_id must not be empty")

    try:
        with zipfile.ZipFile(path, mode="r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if EXTERNAL_TOOL_REQUIREMENTS_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{EXTERNAL_TOOL_REQUIREMENTS_PATH} already exists; use --overwrite to replace it"
                )
            manifest = json.loads(zf.read("manifest.json"))
            source_task_id: str | None = None
            if TASK_SPEC_PATH in names:
                task_spec = yaml.safe_load(zf.read(TASK_SPEC_PATH))
                if isinstance(task_spec, dict):
                    source_task_id = task_spec.get("task_id")
            members = _read_members(zf, exclude={EXTERNAL_TOOL_REQUIREMENTS_PATH, "manifest.json"})
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    requirements = _build_external_tool_requirements(
        handoff_id=effective_handoff_id,
        source_task_id=source_task_id,
    )
    requirements_json = (json.dumps(requirements, indent=2, sort_keys=True) + "\n").encode()

    task_resources = manifest.setdefault("resources", {}).setdefault("task", {})
    task_resources["external_tool_requirements"] = EXTERNAL_TOOL_REQUIREMENTS_PATH

    manifest_json = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp = Path(fh.name)

    try:
        with zipfile.ZipFile(temp, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            if TASK_DIR not in names:
                zf.writestr(TASK_DIR, b"")
            zf.writestr("manifest.json", manifest_json)
            zf.writestr(EXTERNAL_TOOL_REQUIREMENTS_PATH, requirements_json)
        shutil.move(str(temp), path)
    finally:
        if temp.exists():
            temp.unlink()

    return path


def _build_external_tool_requirements(
    handoff_id: str,
    source_task_id: str | None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "handoff_id": handoff_id,
        "required_capabilities": [
            {
                "capability": "inspect_current_state",
                "tool_role": "agent_runtime",
                "required": True,
                "reason": "Agent must inspect package state before proposing actions.",
            },
            {
                "capability": "modify_cad_geometry",
                "tool_role": "cad_runtime",
                "required": False,
                "reason": "Only needed after an accepted geometry-modification proposal.",
            },
            {
                "capability": "generate_mesh",
                "tool_role": "cae_preprocessor",
                "required": False,
                "reason": "Mesh generation must be done by external CAE software.",
            },
            {
                "capability": "run_solver",
                "tool_role": "solver",
                "required": False,
                "reason": "Solver execution must be done by external CAE software.",
            },
            {
                "capability": "export_solver_artifacts",
                "tool_role": "solver",
                "required": False,
                "reason": "Solver artifacts are needed before stress/displacement claims.",
            },
        ],
        "candidate_tools": [
            {
                "tool_id": "mechanical_agent",
                "tool_role": "agent_runtime",
                "status": "candidate",
                "capabilities": ["inspect_current_state", "run_workflow", "writeback_evidence"],
                "notes": "External execution/testbed candidate; not a core dependency.",
            },
            {
                "tool_id": "sim_cli",
                "tool_role": "cae_runtime",
                "status": "candidate",
                "capabilities": ["check_solver", "execute_bounded_step", "collect_artifacts"],
                "notes": "Inspired by SVD AI Lab sim-cli style runtime; optional external adapter only.",
            },
            {
                "tool_id": "freecad",
                "tool_role": "cad_runtime",
                "status": "candidate",
                "capabilities": ["modify_cad_geometry", "export_step"],
                "notes": "External CAD runtime.",
            },
            {
                "tool_id": "calculix",
                "tool_role": "solver",
                "status": "candidate",
                "capabilities": ["run_solver", "export_solver_artifacts"],
                "notes": "External solver runtime.",
            },
        ],
        "handoff_policy": {
            "aieng_core_executes_external_tools": False,
            "bounded_steps_only": True,
            "external_tools_execute": True,
            "inspect_before_execution": True,
            "record_artifacts": True,
            "record_tool_trace": True,
            "reinspect_after_external_change": True,
        },
        "writeback_requirements": [
            "validation_status_update",
            "artifact_provenance",
            "evidence_index_update",
            "claim_map_update",
            "tool_trace",
        ],
        "forbidden_core_actions": [
            "modify_cad_geometry",
            "generate_mesh",
            "run_solver",
            "claim_solver_validated_results",
            "claim_manufacturing_validity",
        ],
    }
    if source_task_id is not None:
        data["source_task_id"] = source_task_id
    return data


def _read_members(
    zf: zipfile.ZipFile,
    exclude: set[str],
) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in zf.infolist():
        if info.filename in exclude or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else zf.read(info.filename)
        members.append((info, data))
    return members
