"""Standalone FreeCADCmd-based macro runner.

Spawns a FreeCADCmd subprocess to execute a FreeCAD macro (.FCMacro or .py)
against an optional working document. Captures stdout, stderr, and return code.

Typical usage from aieng-ui:
    from freecad_mcp.macro_runner import run_macro
    result = run_macro(
        "/path/to/macro.py",
        "C:/FreeCAD/bin/FreeCADCmd.exe",
        document_path="/path/to/part.fcstd",
    )
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Embedded FreeCAD script
# ---------------------------------------------------------------------------

FREECAD_MACRO_RUNNER_SCRIPT = """\
import json
import os
import sys
import FreeCAD

macro_path = os.environ["AIENG_MACRO_PATH"]
document_path = os.environ.get("AIENG_MACRO_DOCUMENT", "")
result_path = os.environ["AIENG_MACRO_RESULT"]
save_document = os.environ.get("AIENG_MACRO_SAVE_DOCUMENT", "false").lower() == "true"

stdout_lines = []
stderr_lines = []

# Redirect stdout/stderr so we can capture them
class _Capture:
    def __init__(self, buf, orig):
        self.buf = buf
        self.orig = orig
    def write(self, text):
        self.buf.append(text)
        self.orig.write(text)
    def flush(self):
        self.orig.flush()

sys.stdout = _Capture(stdout_lines, sys.stdout)
sys.stderr = _Capture(stderr_lines, sys.stderr)

try:
    doc = None
    if document_path and os.path.exists(document_path):
        ext = os.path.splitext(document_path)[1].lower()
        if ext == ".fcstd":
            doc = FreeCAD.open(document_path)
        elif ext in (".step", ".stp"):
            import Part
            doc = FreeCAD.newDocument("MacroDoc")
            Part.insert(document_path, doc.Name)
        else:
            doc = FreeCAD.newDocument("MacroDoc")
    else:
        doc = FreeCAD.newDocument("MacroDoc")

    doc.recompute()

    # Execute the macro file
    with open(macro_path, "r", encoding="utf-8") as f:
        macro_code = f.read()

    # Provide the document as a global variable for the macro
    globals_dict = {
        "__name__": "__main__",
        "__file__": macro_path,
        "FreeCAD": FreeCAD,
        "doc": doc,
        "document": doc,
    }
    exec(macro_code, globals_dict)

    doc.recompute()

    if save_document and doc:
        doc.save()

    result = {
        "status": "ok",
        "macro_path": macro_path,
        "document_path": document_path,
        "freecad_version": ".".join(str(v) for v in FreeCAD.Version()[:3]),
        "stdout": "".join(stdout_lines),
        "stderr": "".join(stderr_lines),
        "warnings": [],
    }
except Exception as exc:
    result = {
        "status": "error",
        "macro_path": macro_path,
        "document_path": document_path,
        "freecad_version": ".".join(str(v) for v in FreeCAD.Version()[:3]),
        "error": str(exc),
        "error_type": type(exc).__name__,
        "stdout": "".join(stdout_lines),
        "stderr": "".join(stderr_lines),
        "warnings": [],
    }

with open(result_path, "w", encoding="utf-8") as _f:
    json.dump(result, _f)
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_macro(
    macro_path: str | Path,
    freecad_cmd: str | Path,
    *,
    document_path: str | Path | None = None,
    save_document: bool = False,
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute a FreeCAD macro via FreeCADCmd subprocess.

    Args:
        macro_path: Path to the macro file (.FCMacro or .py).
        freecad_cmd: Path to the FreeCADCmd executable.
        document_path: Optional path to a working document (.FCStd or .step)
            to open before executing the macro.
        save_document: If True, save the document after macro execution.
        timeout: Seconds before FreeCADCmd is considered hung.

    Returns:
        A JSON-serializable dict with ``status``, ``stdout``, ``stderr``,
        ``freecad_version``, and optionally ``error`` / ``error_type``.

    Raises:
        FileNotFoundError: If ``macro_path`` or ``freecad_cmd`` does not exist.
        RuntimeError: If FreeCADCmd does not produce a result file.
    """
    macro_path = Path(macro_path)
    freecad_cmd = Path(freecad_cmd)

    if not macro_path.exists():
        raise FileNotFoundError(f"Macro file not found: {macro_path}")
    if not freecad_cmd.exists():
        raise FileNotFoundError(f"FreeCADCmd not found: {freecad_cmd}")

    with tempfile.TemporaryDirectory(prefix="aieng-macro-") as temp_dir:
        temp_root = Path(temp_dir)
        script_path = temp_root / "macro_runner.py"
        result_path = temp_root / "result.json"
        script_path.write_text(FREECAD_MACRO_RUNNER_SCRIPT + "\n", encoding="utf-8")

        env = {
            **os.environ,
            "AIENG_MACRO_PATH": str(macro_path),
            "AIENG_MACRO_RESULT": str(result_path),
            "AIENG_MACRO_SAVE_DOCUMENT": "true" if save_document else "false",
            "PYTHONIOENCODING": "utf-8",
        }
        if document_path:
            env["AIENG_MACRO_DOCUMENT"] = str(document_path)

        completed = subprocess.run(
            [str(freecad_cmd), str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        if not result_path.exists():
            raise RuntimeError(
                f"FreeCADCmd macro runner did not write a result file. "
                f"returncode={completed.returncode}, "
                f"stdout={completed.stdout[:400]!r}, "
                f"stderr={completed.stderr[:400]!r}"
            )

        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["return_code"] = completed.returncode
        # If the embedded script succeeded but FreeCADCmd itself returned non-zero,
        # surface that as a warning rather than overwriting the embedded result.
        if completed.returncode != 0 and result.get("status") == "ok":
            result["status"] = "warning"
            result.setdefault("warnings", []).append(
                f"FreeCADCmd exited with code {completed.returncode}"
            )
        return result
