"""Write provenance/tool_trace.json to an existing .aieng package.

This module records externally executed tool steps as provenance entries.
It does NOT execute any external tools itself.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

TOOL_TRACE_PATH = "provenance/tool_trace.json"
PROVENANCE_DIR = "provenance/"
TASK_SPEC_PATH = "task/task_spec.yaml"
EXTERNAL_TOOL_REQUIREMENTS_PATH = "task/external_tool_requirements.json"

_TOOL_ROLES = frozenset({
    "agent_runtime",
    "cad_runtime",
    "cae_runtime",
    "cae_preprocessor",
    "solver",
    "postprocessor",
    "manufacturing_checker",
})
_EXIT_STATUSES = frozenset({"success", "failure", "skipped"})

_CLAIM_POLICY: dict[str, Any] = {
    "aieng_core_executes_external_tools": False,
    "external_tools_execute": True,
}


def record_trace_package(
    package_path: str | Path,
    *,
    tool_id: str,
    tool_role: str,
    step_name: str,
    exit_status: str,
    tool_version: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    artifacts_recorded: list[str] | None = None,
    claims_advanced: list[str] | None = None,
    notes: list[str] | None = None,
) -> Path:
    """Append a provenance trace entry to provenance/tool_trace.json.

    Creates the file on first call, appends on subsequent calls.
    Does not execute external tools; records only what the caller provides.
    Does not modify results/evidence_index.json or results/claim_map.json.
    """
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    if not tool_id or not isinstance(tool_id, str):
        raise ValueError("tool_id must be a non-empty string")
    if tool_role not in _TOOL_ROLES:
        raise ValueError(f"tool_role must be one of {sorted(_TOOL_ROLES)}")
    if not step_name or not isinstance(step_name, str):
        raise ValueError("step_name must be a non-empty string")
    if exit_status not in _EXIT_STATUSES:
        raise ValueError(f"exit_status must be one of {sorted(_EXIT_STATUSES)}")

    try:
        with zipfile.ZipFile(path, mode="r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            manifest = json.loads(zf.read("manifest.json"))

            # Read existing trace if present
            existing_trace: dict[str, Any] | None = None
            if TOOL_TRACE_PATH in names:
                existing_trace = json.loads(zf.read(TOOL_TRACE_PATH))

            # Read source IDs from existing package resources
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

            members = _read_members(zf, exclude={TOOL_TRACE_PATH, "manifest.json"})
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    # Build or update the trace document
    if existing_trace is None:
        trace_id = "tool_trace_001"
        entries: list[dict[str, Any]] = []
        trace_doc: dict[str, Any] = {
            "claim_policy": dict(_CLAIM_POLICY),
            "entries": entries,
            "format_version": FORMAT_VERSION,
            "tool_trace_id": trace_id,
        }
        if source_task_id is not None:
            trace_doc["source_task_id"] = source_task_id
        if source_handoff_id is not None:
            trace_doc["source_handoff_id"] = source_handoff_id
    else:
        trace_doc = existing_trace
        entries = trace_doc.get("entries", [])
        if not isinstance(entries, list):
            entries = []
            trace_doc["entries"] = entries

    # Determine next entry ID
    entry_id = _next_entry_id(entries)

    # Build timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Build tool ref
    tool_ref: dict[str, Any] = {
        "tool_id": tool_id,
        "tool_role": tool_role,
    }
    if tool_version is not None:
        tool_ref["version"] = tool_version

    # Build step record
    step_record: dict[str, Any] = {
        "exit_status": exit_status,
        "inputs": list(inputs or []),
        "name": step_name,
        "outputs": list(outputs or []),
    }

    # Build entry
    entry: dict[str, Any] = {
        "artifacts_recorded": list(artifacts_recorded or []),
        "claims_advanced": list(claims_advanced or []),
        "entry_id": entry_id,
        "notes": list(notes or []),
        "step": step_record,
        "timestamp_utc": timestamp,
        "tool": tool_ref,
    }

    entries.append(entry)
    trace_doc["entries"] = entries

    # Update manifest
    provenance_resources = manifest.setdefault("resources", {}).setdefault("provenance", {})
    provenance_resources["tool_trace"] = TOOL_TRACE_PATH
    manifest_json = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    trace_json = (json.dumps(trace_doc, indent=2, sort_keys=True) + "\n").encode()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp = Path(fh.name)

    try:
        with zipfile.ZipFile(temp, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            if PROVENANCE_DIR not in names:
                zf.writestr(PROVENANCE_DIR, b"")
            zf.writestr("manifest.json", manifest_json)
            zf.writestr(TOOL_TRACE_PATH, trace_json)
        shutil.move(str(temp), path)
    finally:
        if temp.exists():
            temp.unlink()

    return path


def _next_entry_id(entries: list[dict[str, Any]]) -> str:
    """Return the next deterministic entry ID: trace_0001, trace_0002, ..."""
    existing_ids = {
        e.get("entry_id", "")
        for e in entries
        if isinstance(e, dict)
    }
    index = 1
    while True:
        candidate = f"trace_{index:04d}"
        if candidate not in existing_ids:
            return candidate
        index += 1


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
