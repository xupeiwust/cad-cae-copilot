"""Read-only bridge to the ``aieng recommend-cad-modifications`` CLI.

Invokes the aieng CLI as a subprocess and returns the structured JSON
output. The CLI is the stable interface between ``aieng_freecad_mcp``
and ``aieng`` -- the bridge does not re-implement the recommendation
logic, so ranking heuristics + claim policy stay owned by ``aieng``.

Honesty boundary: the bridge is read-only. It does not mutate the
package, does not advance claims, and does not execute CAD/CAE
operations. Recommendation payloads are *hypotheses*; verification by
re-simulation remains a separate step.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


__all__ = ["recommend_cad_modifications"]


_DEFAULT_TIMEOUT_SECONDS = 60


def _resolve_aieng_cli(aieng_cli: str | None) -> list[str] | None:
    """Return the argv prefix to invoke the aieng CLI, or None if not found."""
    if aieng_cli:
        return [aieng_cli]
    found = shutil.which("aieng")
    if found:
        return [found]
    # Fallback: invoke via the current Python interpreter if the aieng
    # module is importable in the running environment.
    try:
        import aieng  # noqa: F401  -- intentional importability probe
    except Exception:
        return None
    return [sys.executable, "-m", "aieng.cli"]


def recommend_cad_modifications(
    package_path: str | Path,
    *,
    aieng_cli: str | None = None,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Invoke ``aieng recommend-cad-modifications`` on ``package_path``.

    Returns the parsed JSON payload from the aieng CLI, wrapped with a
    small status envelope. Never raises -- malformed output, missing CLI,
    or non-zero exit codes are reported as ``ok=False`` with a clear
    error message.

    ``aieng_cli`` overrides the discovered CLI command (used in tests).
    """
    path = Path(package_path)
    argv_prefix = _resolve_aieng_cli(aieng_cli)
    if argv_prefix is None:
        return {
            "ok": False,
            "package_path": str(path),
            "recommendations": None,
            "errors": [
                "aieng CLI is not available. Install the `aieng` package or "
                "make `aieng` discoverable on PATH."
            ],
            "warnings": [],
            "claim_policy": {
                "proposals_are_hypotheses": True,
                "requires_verification_simulation": True,
                "claims_advanced": False,
            },
        }

    argv = argv_prefix + [
        "recommend-cad-modifications",
        str(path),
        "--output",
        "json",
    ]

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "package_path": str(path),
            "recommendations": None,
            "errors": [f"aieng CLI timed out after {timeout_seconds}s."],
            "warnings": [],
            "claim_policy": {
                "proposals_are_hypotheses": True,
                "requires_verification_simulation": True,
                "claims_advanced": False,
            },
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "recommendations": None,
            "errors": [f"aieng CLI not found: {exc}"],
            "warnings": [],
            "claim_policy": {
                "proposals_are_hypotheses": True,
                "requires_verification_simulation": True,
                "claims_advanced": False,
            },
        }

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if not stdout.strip():
        return {
            "ok": False,
            "package_path": str(path),
            "recommendations": None,
            "errors": [
                "aieng CLI returned no stdout."
                + (f" stderr: {stderr.strip()}" if stderr.strip() else "")
            ],
            "exit_code": completed.returncode,
            "warnings": [],
            "claim_policy": {
                "proposals_are_hypotheses": True,
                "requires_verification_simulation": True,
                "claims_advanced": False,
            },
        }

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "recommendations": None,
            "errors": [f"Failed to parse aieng CLI JSON output: {exc}"],
            "exit_code": completed.returncode,
            "warnings": [],
            "claim_policy": {
                "proposals_are_hypotheses": True,
                "requires_verification_simulation": True,
                "claims_advanced": False,
            },
        }

    # The CLI returns exit code 0 on success, 2 when the inputs were
    # incomplete (ok=False inside the payload). We surface both.
    return {
        "ok": bool(payload.get("ok", False)),
        "package_path": str(path),
        "recommendations": payload,
        "exit_code": completed.returncode,
        "warnings": payload.get("warnings", []),
        "claim_policy": payload.get(
            "claim_policy",
            {
                "proposals_are_hypotheses": True,
                "requires_verification_simulation": True,
                "claims_advanced": False,
            },
        ),
    }
