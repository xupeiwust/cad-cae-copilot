"""Read-only bridge to the ``aieng verify-cad-modifications`` CLI.

Invokes the aieng CLI as a subprocess and returns the structured JSON
output (verdicts per proposal). The bridge does not re-implement the
verification checks -- schema/manufacturability/regression rules stay
owned by ``aieng``.

Honesty boundary: verification is a pre-execution heuristic check. It
does not replace re-simulation, does not perform geometry-kernel checks,
and does not advance claims.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


__all__ = ["verify_cad_modifications", "STRICTNESS_MODES"]


STRICTNESS_MODES: tuple[str, ...] = ("lenient", "default", "strict")

_DEFAULT_TIMEOUT_SECONDS = 60


def _resolve_aieng_cli(aieng_cli: str | None) -> list[str] | None:
    if aieng_cli:
        return [aieng_cli]
    found = shutil.which("aieng")
    if found:
        return [found]
    try:
        import aieng  # noqa: F401
    except Exception:
        return None
    return [sys.executable, "-m", "aieng.cli"]


def _claim_policy() -> dict[str, Any]:
    return {
        "verification_is_pre_execution": True,
        "verification_does_not_replace_resimulation": True,
        "geometry_kernel_checks_not_performed": True,
        "claims_advanced": False,
    }


def verify_cad_modifications(
    package_path: str | Path,
    *,
    strictness: str = "default",
    proposals: dict[str, Any] | None = None,
    aieng_cli: str | None = None,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Invoke ``aieng verify-cad-modifications`` on ``package_path``.

    If ``proposals`` is supplied (e.g. the JSON payload returned by
    ``recommend_cad_modifications``), it is written to a temporary file
    and passed via ``--proposals``. If omitted, the CLI regenerates
    proposals from the package.

    Returns the parsed JSON payload from the aieng CLI wrapped in a
    small status envelope. Never raises -- failures surface as
    ``ok=False`` with a clear error message.
    """
    if strictness not in STRICTNESS_MODES:
        return {
            "ok": False,
            "package_path": str(Path(package_path)),
            "verification": None,
            "errors": [
                f"strictness must be one of {list(STRICTNESS_MODES)}; "
                f"got {strictness!r}."
            ],
            "warnings": [],
            "claim_policy": _claim_policy(),
        }

    path = Path(package_path)
    argv_prefix = _resolve_aieng_cli(aieng_cli)
    if argv_prefix is None:
        return {
            "ok": False,
            "package_path": str(path),
            "verification": None,
            "errors": [
                "aieng CLI is not available. Install the `aieng` package or "
                "make `aieng` discoverable on PATH."
            ],
            "warnings": [],
            "claim_policy": _claim_policy(),
        }

    proposals_tmp: Path | None = None
    if proposals is not None:
        # Materialise to a temp file so we don't depend on the CLI accepting
        # JSON on stdin (it doesn't today).
        tmp_fd = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        try:
            json.dump(proposals, tmp_fd)
        finally:
            tmp_fd.close()
        proposals_tmp = Path(tmp_fd.name)

    argv = argv_prefix + [
        "verify-cad-modifications",
        str(path),
        "--strictness",
        strictness,
        "--output",
        "json",
    ]
    if proposals_tmp is not None:
        argv.extend(["--proposals", str(proposals_tmp)])

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
        if proposals_tmp is not None and proposals_tmp.exists():
            proposals_tmp.unlink()
        return {
            "ok": False,
            "package_path": str(path),
            "verification": None,
            "errors": [f"aieng CLI timed out after {timeout_seconds}s."],
            "warnings": [],
            "claim_policy": _claim_policy(),
        }
    except FileNotFoundError as exc:
        if proposals_tmp is not None and proposals_tmp.exists():
            proposals_tmp.unlink()
        return {
            "ok": False,
            "package_path": str(path),
            "verification": None,
            "errors": [f"aieng CLI not found: {exc}"],
            "warnings": [],
            "claim_policy": _claim_policy(),
        }
    finally:
        if proposals_tmp is not None and proposals_tmp.exists():
            proposals_tmp.unlink()

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if not stdout.strip():
        return {
            "ok": False,
            "package_path": str(path),
            "verification": None,
            "errors": [
                "aieng CLI returned no stdout."
                + (f" stderr: {stderr.strip()}" if stderr.strip() else "")
            ],
            "exit_code": completed.returncode,
            "warnings": [],
            "claim_policy": _claim_policy(),
        }

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "package_path": str(path),
            "verification": None,
            "errors": [f"Failed to parse aieng CLI JSON output: {exc}"],
            "exit_code": completed.returncode,
            "warnings": [],
            "claim_policy": _claim_policy(),
        }

    summary = payload.get("summary") or {}
    fails = int(summary.get("fail", 0)) if isinstance(summary, dict) else 0

    return {
        "ok": bool(payload.get("ok", False)) and fails == 0,
        "package_path": str(path),
        "strictness": strictness,
        "verification": payload,
        "summary": summary,
        "exit_code": completed.returncode,
        "warnings": payload.get("warnings", []),
        "claim_policy": payload.get("claim_policy", _claim_policy()),
    }
