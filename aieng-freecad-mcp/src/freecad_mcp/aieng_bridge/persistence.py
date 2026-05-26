"""Evidence and provenance persistence into .aieng packages.

Rules:
- Append entries; never overwrite existing records.
- Never modify results/claim_map.json.
- Never advance claim status.
- Create files with conservative scaffolds if missing.
- Fail safely with structured errors.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from freecad_mcp.tool_contracts import StandardToolResult
from freecad_mcp.aieng_bridge.evidence import build_evidence_entry
from freecad_mcp.aieng_bridge.trace import build_trace_entry


class PersistenceError(RuntimeError):
    """Raised when evidence or trace persistence fails."""


def _is_zipped_aieng(path: Path) -> bool:
    return path.is_file() and path.suffix == ".aieng"


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically using a temporary file and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_or_init_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "entries" in data:
            return list(data["entries"])
        return []
    except Exception:
        return []


def _load_or_init_array_from_zip(
    zip_path: Path, entry_name: str
) -> list[dict[str, Any]]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(entry_name) as f:
                data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "entries" in data:
            return list(data["entries"])
        return []
    except (KeyError, json.JSONDecodeError, zipfile.BadZipFile, Exception):
        return []


def _save_array(path: Path, entries: list[dict[str, Any]]) -> None:
    _atomic_write_json(path, {"entries": entries})


def _resolve_id(raw: str | None, prefix: str, index: int) -> str:
    """Return a sequential ID if raw is missing or the placeholder 'unknown'."""
    if raw and raw != "unknown":
        return raw
    return f"{prefix}-{index:04d}"


def _repack_aieng(source_dir: Path, dest_zip: Path) -> None:
    """Repack a directory into a .aieng zip, preserving structure."""
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(source_dir).as_posix()
                zf.write(file_path, arcname)


def _atomic_update_aieng_zip(
    zip_path: Path, updates: dict[str, Any]
) -> list[str]:
    """Atomically update JSON files inside a .aieng zip.

    Args:
        zip_path: Path to the .aieng zip file.
        updates: Dict mapping archive entry paths to new JSON-serializable data.

    Returns:
        List of updated archive entry paths.

    Raises:
        PersistenceError: On malformed zip or atomic replace failure.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            extract_dir = tmpdir_path / "extract"
            extract_dir.mkdir()

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            updated_paths: list[str] = []
            for entry_path, content in updates.items():
                file_path = extract_dir / entry_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write_json(file_path, content)
                updated_paths.append(entry_path)

            tmp_zip = tmpdir_path / "updated.aieng"
            _repack_aieng(extract_dir, tmp_zip)
            os.replace(tmp_zip, zip_path)
            return updated_paths
    except zipfile.BadZipFile as exc:
        raise PersistenceError(f"Malformed .aieng zip: {exc}") from exc
    except OSError as exc:
        raise PersistenceError(f"Atomic replace failed: {exc}") from exc


def append_evidence_entry(package_path: str, evidence_entry: dict[str, Any]) -> str:
    """Append an evidence entry to ``results/evidence_index.json``.

    Returns:
        The evidence_id that was written.
    """
    path = Path(package_path)

    if _is_zipped_aieng(path):
        entries = _load_or_init_array_from_zip(path, "results/evidence_index.json")
        evidence_id = _resolve_id(evidence_entry.get("evidence_id"), "ev", len(entries))
        evidence_entry["evidence_id"] = evidence_id
        entries.append(evidence_entry)
        _atomic_update_aieng_zip(
            path, {"results/evidence_index.json": {"entries": entries}}
        )
        return evidence_id

    if not path.is_dir():
        raise PersistenceError(f"Package path is not a directory or .aieng file: {package_path}")

    evidence_path = path / "results" / "evidence_index.json"
    entries = _load_or_init_array(evidence_path)
    evidence_id = _resolve_id(evidence_entry.get("evidence_id"), "ev", len(entries))
    evidence_entry["evidence_id"] = evidence_id
    entries.append(evidence_entry)
    _save_array(evidence_path, entries)
    return evidence_id


def append_trace_entry(package_path: str, trace_entry: dict[str, Any]) -> str:
    """Append a trace entry to ``provenance/tool_trace.json``.

    Returns:
        The trace_id that was written.
    """
    path = Path(package_path)

    if _is_zipped_aieng(path):
        entries = _load_or_init_array_from_zip(path, "provenance/tool_trace.json")
        trace_id = _resolve_id(trace_entry.get("trace_id"), "trace", len(entries))
        trace_entry["trace_id"] = trace_id
        entries.append(trace_entry)
        _atomic_update_aieng_zip(
            path, {"provenance/tool_trace.json": {"entries": entries}}
        )
        return trace_id

    if not path.is_dir():
        raise PersistenceError(f"Package path is not a directory or .aieng file: {package_path}")

    trace_path = path / "provenance" / "tool_trace.json"
    entries = _load_or_init_array(trace_path)
    trace_id = _resolve_id(trace_entry.get("trace_id"), "trace", len(entries))
    trace_entry["trace_id"] = trace_id
    entries.append(trace_entry)
    _save_array(trace_path, entries)
    return trace_id


def persist_standard_result_to_aieng(
    package_path: str,
    result: StandardToolResult,
    operation: str | None = None,
    additional_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a StandardToolResult into an .aieng package.

    Appends evidence and trace entries.  Does not modify claim_map.json.
    Does not advance claims.

    Returns:
        Dict with ``evidence_id``, ``trace_id``, and ``paths_written``.
    """
    path = Path(package_path)

    if _is_zipped_aieng(path):
        op = operation or result.operation or "unknown"
        evidence = build_evidence_entry(result, additional_metadata=additional_metadata)
        trace = build_trace_entry(result, additional_metadata=additional_metadata)

        evidence_entries = _load_or_init_array_from_zip(path, "results/evidence_index.json")
        evidence_id = _resolve_id(evidence.get("evidence_id"), "ev", len(evidence_entries))
        evidence["evidence_id"] = evidence_id
        evidence_entries.append(evidence)

        trace_entries = _load_or_init_array_from_zip(path, "provenance/tool_trace.json")
        trace_id = _resolve_id(trace.get("trace_id"), "trace", len(trace_entries))
        trace["trace_id"] = trace_id
        trace_entries.append(trace)

        _atomic_update_aieng_zip(
            path,
            {
                "results/evidence_index.json": {"entries": evidence_entries},
                "provenance/tool_trace.json": {"entries": trace_entries},
            },
        )

        return {
            "evidence_id": evidence_id,
            "trace_id": trace_id,
            "paths_written": [
                "results/evidence_index.json",
                "provenance/tool_trace.json",
            ],
            "operation": op,
            "claims_advanced": result.claim_policy.claims_advanced,
        }

    if not path.is_dir():
        raise PersistenceError(f"Package path is not a directory or .aieng file: {package_path}")

    op = operation or result.operation or "unknown"
    evidence = build_evidence_entry(result, additional_metadata=additional_metadata)
    trace = build_trace_entry(result, additional_metadata=additional_metadata)

    evidence_id = append_evidence_entry(package_path, evidence)
    trace_id = append_trace_entry(package_path, trace)

    return {
        "evidence_id": evidence_id,
        "trace_id": trace_id,
        "paths_written": [
            str(path / "results" / "evidence_index.json"),
            str(path / "provenance" / "tool_trace.json"),
        ],
        "operation": op,
        "claims_advanced": result.claim_policy.claims_advanced,
    }
