from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

EVIDENCE_INDEX_PATH = "results/evidence_index.json"
RESULTS_DIR = "results/"
TASK_SPEC_PATH = "task/task_spec.yaml"
EXTERNAL_TOOL_REQUIREMENTS_PATH = "task/external_tool_requirements.json"

WRITEBACK_REQUIRED_PATHS = (EVIDENCE_INDEX_PATH,)
_EVIDENCE_ID_PREFIX = {
    "solver_result": "ev_solver_result",
    "mesh_evidence": "ev_mesh_evidence",
    "geometry_modification": "ev_geometry_modification",
    "validation_report": "ev_validation_report",
}
_EVIDENCE_VERIFICATION_STATUSES = {"available", "missing", "unverified", "schema_validated"}
_EVIDENCE_TYPES = {
    "task_spec",
    "external_tool_requirements",
    "solver_result",
    "mesh_evidence",
    "geometry_modification",
    "validation_report",
}
_PRODUCER_KINDS = {"aieng_core", "external_cad", "external_cae", "external_solver", "external_agent"}
_ARTIFACT_KINDS = {"yaml", "json", "inp", "step", "result_file"}
_NO_CORE_EXTERNAL_EVIDENCE_TYPES = {"solver_result", "mesh_evidence", "geometry_modification"}


def write_evidence_scaffold_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write results/evidence_index.json to an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            existing = [p for p in (EVIDENCE_INDEX_PATH,) if p in names]
            if existing and not overwrite:
                raise FileExistsError(
                    f"evidence resources already exist: {', '.join(existing)}; use --overwrite to replace them"
                )
            manifest = json.loads(zf.read("manifest.json"))
            source_task_id: str | None = None
            if TASK_SPEC_PATH in names:
                task_spec = yaml.safe_load(zf.read(TASK_SPEC_PATH))
                if isinstance(task_spec, dict):
                    source_task_id = task_spec.get("task_id")
            source_handoff_id: str | None = None
            if EXTERNAL_TOOL_REQUIREMENTS_PATH in names:
                ext_req = json.loads(zf.read(EXTERNAL_TOOL_REQUIREMENTS_PATH))
                if isinstance(ext_req, dict):
                    source_handoff_id = ext_req.get("handoff_id")
            members = _read_members(zf, exclude={EVIDENCE_INDEX_PATH, "manifest.json"})
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    evidence_index = _build_evidence_scaffold(
        names=names,
        source_task_id=source_task_id,
        source_handoff_id=source_handoff_id,
    )
    evidence_json = (json.dumps(evidence_index, indent=2, sort_keys=True) + "\n").encode()

    results_resources = manifest.setdefault("resources", {}).setdefault("results", {})
    results_resources["evidence_index"] = EVIDENCE_INDEX_PATH
    manifest_json = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp = Path(fh.name)

    try:
        with zipfile.ZipFile(temp, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            if RESULTS_DIR not in names:
                zf.writestr(RESULTS_DIR, b"")
            zf.writestr("manifest.json", manifest_json)
            zf.writestr(EVIDENCE_INDEX_PATH, evidence_json)
        shutil.move(str(temp), path)
    finally:
        if temp.exists():
            temp.unlink()

    return path


def _build_evidence_scaffold(
    names: set[str],
    source_task_id: str | None,
    source_handoff_id: str | None,
) -> dict[str, Any]:
    evidence_items: list[dict[str, Any]] = []

    claim_policy: dict[str, Any] = {
        "aieng_core_generates_mesh_evidence": False,
        "aieng_core_generates_solver_evidence": False,
        "aieng_core_modifies_cad_geometry": False,
        "external_tools_execute": True,
    }

    if TASK_SPEC_PATH in names:
        evidence_items.append({
            "artifact": {
                "kind": "yaml",
                "notes": "Structured agent task contract written by aieng write-task-spec.",
                "path": TASK_SPEC_PATH,
            },
            "claim_support": ["claim_task_defined_001"],
            "evidence_id": "ev_task_spec_001",
            "evidence_type": "task_spec",
            "notes": "Task specification produced by aieng core from user intent and package state.",
            "producer": {
                "kind": "aieng_core",
            },
            "verification": {
                "notes": "task/task_spec.yaml present in package; schema validated by aieng validate.",
                "status": "schema_validated",
            },
        })

    if EXTERNAL_TOOL_REQUIREMENTS_PATH in names:
        evidence_items.append({
            "artifact": {
                "kind": "json",
                "notes": "Structured external tool handoff contract written by aieng write-external-tool-requirements.",
                "path": EXTERNAL_TOOL_REQUIREMENTS_PATH,
            },
            "claim_support": ["claim_handoff_defined_001"],
            "evidence_id": "ev_handoff_001",
            "evidence_type": "external_tool_requirements",
            "notes": "Handoff contract produced by aieng core from package state.",
            "producer": {
                "kind": "aieng_core",
            },
            "verification": {
                "notes": "task/external_tool_requirements.json present in package; schema validated by aieng validate.",
                "status": "schema_validated",
            },
        })

    evidence_index: dict[str, Any] = {
        "claim_policy": claim_policy,
        "evidence_index_id": "evidence_index_001",
        "evidence_items": evidence_items,
        "format_version": FORMAT_VERSION,
    }
    if source_task_id is not None:
        evidence_index["source_task_id"] = source_task_id
    if source_handoff_id is not None:
        evidence_index["source_handoff_id"] = source_handoff_id

    return evidence_index


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


def record_evidence_package(
    package_path: str | Path,
    *,
    evidence_type: str,
    producer_kind: str,
    producer_tool: str,
    artifact_kind: str,
    artifact_path: str,
    claim_support: list[str],
    evidence_id: str | None = None,
    verification_status: str = "available",
    notes: list[str] | None = None,
    structured_payload: dict[str, Any] | None = None,
) -> Path:
    path = Path(package_path)
    evidence_index, members = _load_writeback_resources(path)

    if evidence_type not in _EVIDENCE_TYPES:
        raise ValueError(f"unsupported evidence type: {evidence_type}")
    if producer_kind not in _PRODUCER_KINDS:
        raise ValueError(f"unsupported producer kind: {producer_kind}")
    if artifact_kind not in _ARTIFACT_KINDS:
        raise ValueError(f"unsupported artifact kind: {artifact_kind}")
    if verification_status not in _EVIDENCE_VERIFICATION_STATUSES:
        raise ValueError(f"unsupported verification status: {verification_status}")
    if not artifact_path:
        raise ValueError("artifact_path must be non-empty")
    if evidence_type in _NO_CORE_EXTERNAL_EVIDENCE_TYPES and producer_kind == "aieng_core":
        raise ValueError(
            "producer_kind 'aieng_core' is not allowed for solver_result, mesh_evidence, or geometry_modification"
        )

    if not claim_support:
        raise ValueError("claim_support must contain at least one claim ID")
    cleaned_claim_support = _normalize_id_list(claim_support)
    if not cleaned_claim_support:
        raise ValueError("claim_support must contain at least one claim ID")

    evidence_items = evidence_index.setdefault("evidence_items", [])
    if not isinstance(evidence_items, list):
        raise ValueError("results/evidence_index.json evidence_items must be an array")
    existing_evidence_ids = {
        item.get("evidence_id")
        for item in evidence_items
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }

    final_evidence_id = evidence_id.strip() if isinstance(evidence_id, str) else ""
    if not final_evidence_id:
        final_evidence_id = _next_evidence_id(evidence_type, existing_evidence_ids)
    if final_evidence_id in existing_evidence_ids:
        raise ValueError(f"duplicate evidence_id: {final_evidence_id}")

    note_text = _join_notes(notes)
    evidence_item: dict[str, Any] = {
        "artifact": {
            "kind": artifact_kind,
            "path": artifact_path,
        },
        "claim_support": cleaned_claim_support,
        "evidence_id": final_evidence_id,
        "evidence_type": evidence_type,
        "producer": {
            "kind": producer_kind,
            "tool_id": producer_tool,
        },
        "verification": {
            "status": verification_status,
        },
    }
    if note_text:
        evidence_item["notes"] = note_text
    if structured_payload is not None:
        evidence_item["structured_payload"] = structured_payload

    evidence_items.append(evidence_item)
    _sort_evidence_items(evidence_items)

    _rewrite_with_updates(
        path,
        members,
        {
            EVIDENCE_INDEX_PATH: _to_deterministic_json_bytes(evidence_index),
        },
    )
    return path


def _load_writeback_resources(path: Path) -> tuple[dict[str, Any], list[tuple[zipfile.ZipInfo, bytes]]]:
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as zf:
            names = set(zf.namelist())
            missing = [member for member in WRITEBACK_REQUIRED_PATHS if member not in names]
            if missing:
                joined = ", ".join(missing)
                raise FileNotFoundError(
                    f"missing evidence scaffold resources: {joined}; run 'aieng write-evidence-scaffold {path}'"
                )

            evidence_index = json.loads(zf.read(EVIDENCE_INDEX_PATH))
            if not isinstance(evidence_index, dict):
                raise ValueError(f"{EVIDENCE_INDEX_PATH} must be a JSON object")
            members = _read_members(zf, exclude=set())
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in evidence resources: {exc}") from exc

    return evidence_index, members


def _normalize_id_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _next_evidence_id(evidence_type: str, existing_ids: set[str]) -> str:
    prefix = _EVIDENCE_ID_PREFIX.get(evidence_type, f"ev_{evidence_type}")
    max_num = 0
    for ev_id in existing_ids:
        if not ev_id.startswith(f"{prefix}_"):
            continue
        suffix = ev_id.removeprefix(f"{prefix}_")
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return f"{prefix}_{max_num + 1:03d}"


def _join_notes(notes: list[str] | None) -> str | None:
    if not notes:
        return None
    cleaned = [note.strip() for note in notes if isinstance(note, str) and note.strip()]
    if not cleaned:
        return None
    return "\n".join(cleaned)


def _sort_evidence_items(items: list[dict[str, Any]]) -> None:
    items.sort(key=lambda item: str(item.get("evidence_id", "")))


def _to_deterministic_json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


def _rewrite_with_updates(
    path: Path,
    members: list[tuple[zipfile.ZipInfo, bytes]],
    updates: dict[str, bytes],
) -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp = Path(fh.name)

    try:
        with zipfile.ZipFile(temp, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                if info.filename in updates:
                    zf.writestr(info.filename, updates[info.filename])
                else:
                    zf.writestr(info, data)
        shutil.move(str(temp), path)
    finally:
        if temp.exists():
            temp.unlink()
