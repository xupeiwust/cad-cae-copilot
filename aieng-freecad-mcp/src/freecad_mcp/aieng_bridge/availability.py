"""Read-only FreeCAD availability check for MVP 1C-A.

Rules:
- Never modifies CAD state, documents, or files.
- Never imports FreeCAD unless a valid Python entry point is discovered.
- Reports what is available, what is missing, and what is unsupported.
- Always returns ``claims_advanced: false``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class FreecadAvailabilityResult(BaseModel):
    """Deterministic report of FreeCAD installation availability."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    configured_path: str | None = None
    path_exists: bool = False
    executable: str | None = None
    python_entry_point: str | None = None
    version: str | None = None
    missing: list[str] = []
    unsupported: list[str] = []
    claims_advanced: bool = False
    freecad_mutated: bool = False


def _resolve_configured_path() -> str | None:
    """Return the effective FreeCAD path from environment variables.

    Priority:
    1. ``FREECAD_MCP_FREECAD_PATH`` (app-specific override)
    2. ``FREECAD_HOME`` (standard convention)
    """
    return os.environ.get("FREECAD_MCP_FREECAD_PATH") or os.environ.get("FREECAD_HOME")


def _find_executable(home: Path) -> str | None:
    candidates = [
        home / "bin" / "FreeCAD.exe",
        home / "bin" / "freecad.exe",
        home / "FreeCAD.exe",
        home / "freecad.exe",
        home / "bin" / "FreeCAD",
        home / "bin" / "freecad",
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def _find_python_lib(home: Path) -> str | None:
    candidates = [
        home / "lib",
        home / "bin" / "lib",
    ]
    for cand in candidates:
        if cand.is_dir():
            return str(cand)
    return None


def _try_get_version(lib_path: str) -> str | None:
    """Safely attempt to import FreeCAD and read its version.

    Temporarily modifies ``sys.path`` if needed, but always restores it.
    """
    inserted = False
    try:
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
            inserted = True
        import FreeCAD  # noqa: F401

        version_info = FreeCAD.Version()
        return ".".join(str(v) for v in version_info[:3])
    except Exception:
        return None
    finally:
        if inserted and lib_path in sys.path:
            sys.path.remove(lib_path)


def check_freecad_availability() -> FreecadAvailabilityResult:
    """Check FreeCAD availability from environment configuration.

    Returns a deterministic result. Never raises.
    """
    missing: list[str] = []
    unsupported: list[str] = []

    configured_path = _resolve_configured_path()

    if not configured_path:
        missing.append("FREECAD_HOME is not set")
        return FreecadAvailabilityResult(
            configured=False,
            missing=missing,
            unsupported=unsupported,
        )

    home = Path(configured_path)
    path_exists = home.exists()

    if not path_exists:
        missing.append(f"Configured path does not exist: {configured_path}")

    executable = _find_executable(home) if path_exists else None
    python_entry_point = _find_python_lib(home) if path_exists else None

    if path_exists and not executable:
        unsupported.append("FreeCAD executable not found in configured path")
    if path_exists and not python_entry_point:
        unsupported.append("Python entry point (lib directory) not found")

    version = None
    if python_entry_point and path_exists:
        version = _try_get_version(python_entry_point)
        if version is None:
            unsupported.append("FreeCAD Python module not importable from entry point")

    return FreecadAvailabilityResult(
        configured=True,
        configured_path=configured_path,
        path_exists=path_exists,
        executable=executable,
        python_entry_point=python_entry_point,
        version=version,
        missing=missing,
        unsupported=unsupported,
    )
