"""AIENG read-only tools wrapped as inspect_ai ``Tool``s.

The goal is to give an evaluation LLM the same kind of evidence-layer access
a real agent would get through the MCP bridge, but without going through HTTP
— the eval runs in-process against ``aieng`` directly.

Read-only on purpose. Mutation / approval-gated tools are added in later
phases of the roadmap (see github issue #54). For Phase 30's first scenario
("diagnose why this CAE setup fails") read access is sufficient.

Tools intentionally return JSON-serializable dicts so the eval transcript is
inspectable verbatim.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from inspect_ai.tool import tool

from aieng.cae_artifact_detector import detect_cae_artifacts
from aieng.cae_preprocessing_summary import generate_preprocessing_summary


_TEXT_SUFFIXES = frozenset({".json", ".md", ".txt", ".yaml", ".yml", ".inp", ".csv", ".log"})
_MAX_TEXT_BYTES = 256 * 1024


@tool
def aieng_inspect_package():
    """List artifacts present in a .aieng package and report mode/CAE coverage."""

    async def execute(package_path: str) -> dict[str, Any]:
        """List every artifact present in a .aieng package and return the CAE
        artifact detection result (mode + per-artifact presence + counts).

        Args:
            package_path: Path on disk to the .aieng ZIP package.

        Returns:
            ``{"members": [...], "cae_detection": {...}}``. ``members`` is the
            raw ZIP namelist. ``cae_detection`` is the canonical artifact
            detector output (mode, has_cae_setup, has_mesh, has_results,
            artifacts dict, detected_count, total_count).
        """
        path = Path(package_path)
        if not path.exists():
            return {"error": f"package not found: {package_path}"}
        with zipfile.ZipFile(path, "r") as zf:
            members = sorted(zf.namelist())
        return {
            "members": members,
            "cae_detection": detect_cae_artifacts(path),
        }

    return execute


@tool
def aieng_read_artifact():
    """Read a single artifact (JSON or text) from a .aieng package."""

    async def execute(package_path: str, artifact_path: str) -> dict[str, Any]:
        """Read one artifact from a .aieng package as parsed JSON or text.

        Args:
            package_path: Path on disk to the .aieng ZIP package.
            artifact_path: Path of the artifact inside the package
                (e.g. ``simulation/cae_imports/parsed_materials.json``).

        Returns:
            ``{"path", "exists", "size_bytes", "parsed_json"?, "text"?, "warnings"}``.
            JSON files are parsed automatically. Text-classified files (.md, .txt,
            .yaml, .inp, …) up to 256 KB are inlined as text. Missing artifacts
            return ``exists: false``; oversized or non-text suppressed with a
            warning.
        """
        path = Path(package_path)
        if not path.exists():
            return {"error": f"package not found: {package_path}"}
        result: dict[str, Any] = {
            "path": artifact_path,
            "exists": False,
            "warnings": [],
        }
        with zipfile.ZipFile(path, "r") as zf:
            try:
                info = zf.getinfo(artifact_path)
            except KeyError:
                return result
            result["exists"] = True
            result["size_bytes"] = info.file_size
            data = zf.read(artifact_path)

        suffix = Path(artifact_path).suffix.lower()
        if b"\x00" in data[:4096]:
            result["warnings"].append("binary content detected; text omitted")
            return result
        if suffix in _TEXT_SUFFIXES:
            if info.file_size <= _MAX_TEXT_BYTES:
                try:
                    result["text"] = data.decode("utf-8")
                except UnicodeDecodeError:
                    result["warnings"].append("utf-8 decode failed; text omitted")
            else:
                result["warnings"].append(
                    f"file size {info.file_size} bytes exceeds inline cap "
                    f"{_MAX_TEXT_BYTES}; text omitted"
                )
        if suffix == ".json" and "text" in result:
            try:
                result["parsed_json"] = json.loads(data)
            except json.JSONDecodeError as exc:
                result["warnings"].append(f"json parse failed: {exc.msg}")
        return result

    return execute


@tool
def aieng_cae_preprocessing_summary():
    """Generate the honest CAE pre-processing readiness summary for a package."""

    async def execute(package_path: str) -> dict[str, Any]:
        """Run aieng's CAE preprocessing summarizer and return the dict.

        Reports readiness (materials, loads, boundary conditions, mesh,
        solver settings, load cases, cae mapping), ``ready_for_solver``,
        ``missing_items``, and any structural warnings encountered while
        reading the package. Honest: artifact-presence only, no physical
        validation.

        Args:
            package_path: Path on disk to the .aieng ZIP package.
        """
        path = Path(package_path)
        if not path.exists():
            return {"error": f"package not found: {package_path}"}
        return generate_preprocessing_summary(path)

    return execute


AIENG_TOOLS = [
    aieng_inspect_package(),
    aieng_read_artifact(),
    aieng_cae_preprocessing_summary(),
]
"""Convenience list — pass directly to ``use_tools(*AIENG_TOOLS)``."""
