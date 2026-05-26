from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

TASK_SPEC_PATH = "task/task_spec.yaml"
TASK_DIR = "task/"

_KNOWN_MODES = {"proposal_only", "analysis_ready", "execution_ready"}


def write_task_spec_package(
    package_path: str | Path,
    intent: str,
    *,
    task_id: str | None = None,
    mode: str = "proposal_only",
    overwrite: bool = False,
) -> Path:
    """Write task/task_spec.yaml to an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    intent = intent.strip()
    if not intent:
        raise ValueError("intent must not be empty")

    if mode not in _KNOWN_MODES:
        raise ValueError(f"mode '{mode}' is not recognized; expected one of: {sorted(_KNOWN_MODES)}")

    try:
        with zipfile.ZipFile(path, mode="r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if TASK_SPEC_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{TASK_SPEC_PATH} already exists; use --overwrite to replace it"
                )
            manifest = json.loads(zf.read("manifest.json"))
            members = _read_members(zf, exclude={TASK_SPEC_PATH, "manifest.json"})
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    effective_task_id = (task_id or "task_001").strip()
    if not effective_task_id:
        raise ValueError("task_id must not be empty")

    spec = _build_task_spec(intent=intent, task_id=effective_task_id, mode=mode)
    spec_yaml = yaml.dump(spec, sort_keys=False, allow_unicode=True, default_flow_style=False)

    task_resources = manifest.setdefault("resources", {}).setdefault("task", {})
    task_resources["task_spec"] = TASK_SPEC_PATH

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
            zf.writestr(TASK_SPEC_PATH, spec_yaml.encode())
        shutil.move(str(temp), path)
    finally:
        if temp.exists():
            temp.unlink()

    return path


def _build_task_spec(intent: str, task_id: str, mode: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "format_version": FORMAT_VERSION,
        "intent": intent,
        "mode": mode,
        "input_refs": {
            "package": "self",
        },
        "required_outputs": ["patch_proposal"],
        "forbidden_claims": [
            "solver_validated",
            "mesh_validated",
            "safe_to_manufacture",
            "geometry_modified",
        ],
        "allowed_external_tools": [
            "cad_kernel",
            "cae_preprocessor",
            "mesher",
            "solver",
        ],
        "evidence_required_before_acceptance": [
            "geometry_validity",
            "protected_region_integrity",
            "mesh_evidence_from_external_cae",
            "solver_result_from_external_cae",
        ],
        "claim_policy": {
            "no_solver_run_claim": True,
            "no_mesh_generation_claim": True,
            "no_geometry_modification_claim": True,
            "external_tools_execute": True,
        },
    }


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
