"""Read-only FreeCAD feature/parameter reader for the AIENG decision-review workbench.

This module exposes ``inspect_features(source_path)`` — a safe, read-only
function that AIENG's ``aieng-ui`` discovery layer (v0.16) picks up via the
candidate ``freecad_mcp.aieng_bridge.inspect_features``.

The reader spawns FreeCADCmd in a controlled subprocess, runs a fixed
embedded script that opens the CAD file and walks its document objects,
and returns a JSON-serialisable feature/parameter manifest. It NEVER:

  - mutates the input CAD file or document on disk;
  - saves the FreeCAD document;
  - edits parameters or runs macros / Python supplied by the caller;
  - exports STEP/STL/IGES;
  - generates meshes or runs solvers;
  - advances or certifies any engineering claim.

When FreeCADCmd is not configured on the host, the function raises a clear
``RuntimeError`` so the upstream caller (aieng-ui's v0.16 bridge discovery)
can convert that into an honest ``status: skipped, reason: bridge_unavailable``
response.

Public surface:

    from freecad_mcp.aieng_bridge import inspect_features
    result = inspect_features("/path/to/part.FCStd")
    # result == {"features": [...], "schema_version": "0.1", ...}
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = frozenset({".FCStd", ".fcstd", ".step", ".stp", ".STEP", ".STP"})


# Environment variable name the embedded script reads the source path from.
# Kept stable so a future contract change is explicit.
_ENV_INPUT = "AIENG_FEATURE_INSPECT_INPUT"
_ENV_RESULT = "AIENG_FEATURE_INSPECT_RESULT"


# Fixed embedded inspection script. The script is a string constant — caller
# input never reaches the code FreeCADCmd executes. The only caller-controlled
# data is the source-path environment variable, which is consumed safely by
# the script and passed to FreeCAD's read-only document import.
FREECAD_FEATURE_INSPECT_SCRIPT = r'''
import json
import os
import sys

INPUT_PATH = os.environ.get("AIENG_FEATURE_INSPECT_INPUT")
RESULT_PATH = os.environ.get("AIENG_FEATURE_INSPECT_RESULT")
if not INPUT_PATH or not RESULT_PATH:
    sys.stderr.write("AIENG_FEATURE_INSPECT_INPUT / AIENG_FEATURE_INSPECT_RESULT must be set\n")
    raise SystemExit(2)


def _safe_write_result(payload):
    try:
        with open(RESULT_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except Exception as exc:
        sys.stderr.write("could not write result file: %s\n" % exc)


def _classify_property(value):
    """Return a JSON-safe representation of ``value`` plus a unit hint.

    Returns (json_value, unit_or_None, scalar_kind) or None if the value is
    not a scalar we are willing to expose.
    """
    # FreeCAD's Quantity exposes .Value (mm-equivalent for length) and a
    # readable unit string; fall back to the raw float when absent.
    try:
        from FreeCAD import Units  # noqa: F401
    except Exception:
        Units = None  # type: ignore[assignment]

    # Quantity-like: has .Value and .Unit attributes.
    value_attr = getattr(value, "Value", None)
    unit_attr = getattr(value, "Unit", None)
    if value_attr is not None and unit_attr is not None:
        try:
            unit_str = str(unit_attr)
        except Exception:
            unit_str = None
        try:
            float_value = float(value_attr)
        except (TypeError, ValueError):
            return None
        return float_value, unit_str, "quantity"

    if isinstance(value, bool):
        return value, None, "bool"
    if isinstance(value, (int, float)):
        return value, None, "number"
    if isinstance(value, str):
        # Cap length so a stray long property cannot bloat the response.
        return value[:512], None, "string"
    return None


def _classify_editor_mode(obj, prop_name):
    """Return ("editable" or "read_only" or "hidden") best-effort."""
    try:
        modes = obj.getEditorMode(prop_name) or []
    except Exception:
        return "editable"
    if "ReadOnly" in modes:
        return "read_only"
    if "Hidden" in modes:
        return "hidden"
    return "editable"


def _walk_object(obj, idx):
    name = getattr(obj, "Name", None) or "Object_%d" % idx
    label = getattr(obj, "Label", name) or name
    type_id = getattr(obj, "TypeId", "Unknown")
    visibility = getattr(obj, "Visibility", None)
    has_shape = hasattr(obj, "Shape")

    parameters = []
    try:
        props = list(obj.PropertiesList)
    except Exception:
        props = []
    for prop in sorted(props):
        try:
            raw_value = obj.getPropertyByName(prop)
        except Exception:
            continue
        classification = _classify_property(raw_value)
        if classification is None:
            continue
        json_value, unit, kind = classification
        editor_mode = _classify_editor_mode(obj, prop)
        parameters.append({
            "name": str(prop),
            "value": json_value,
            "unit": unit,
            "kind": kind,
            "editable": editor_mode == "editable",
            "editor_mode": editor_mode,
        })

    return {
        "id": str(name),
        "label": str(label),
        "type": str(type_id),
        "source_object": str(name),
        "parameters": parameters,
        "metadata": {
            "visibility": bool(visibility) if visibility is not None else None,
            "has_shape": has_shape,
            "property_count": len(parameters),
        },
    }


def _run():
    try:
        import FreeCAD
    except Exception as exc:
        _safe_write_result({
            "status": "error",
            "error": "FreeCAD module is not importable inside this subprocess: %s" % exc,
        })
        raise SystemExit(3)

    ext = os.path.splitext(INPUT_PATH)[1].lower()
    doc = None
    try:
        if ext in (".step", ".stp"):
            try:
                import Part
            except Exception as exc:
                _safe_write_result({
                    "status": "error",
                    "error": "FreeCAD Part workbench unavailable: %s" % exc,
                })
                raise SystemExit(4)
            doc = FreeCAD.newDocument("AiengFeatureInspect")
            Part.insert(INPUT_PATH, doc.Name)
        elif ext == ".fcstd":
            doc = FreeCAD.open(INPUT_PATH)
        else:
            _safe_write_result({
                "status": "error",
                "error": "Unsupported extension for feature inspection: %r" % ext,
            })
            raise SystemExit(5)

        # Read-only walk; we do NOT recompute geometry, we do NOT save, we do
        # NOT modify any property. We only enumerate metadata.
        objects = list(getattr(doc, "Objects", []))
        features = [_walk_object(obj, idx) for idx, obj in enumerate(objects)]

        try:
            version_tuple = FreeCAD.Version()[:3]
            freecad_version = ".".join(str(v) for v in version_tuple)
        except Exception:
            freecad_version = None

        _safe_write_result({
            "status": "ok",
            "schema_version": "0.1",
            "input_path": INPUT_PATH,
            "freecad_version": freecad_version,
            "feature_count": len(features),
            "features": features,
        })
    finally:
        # Do not save; closing without saving guarantees no mutation.
        try:
            if doc is not None:
                FreeCAD.closeDocument(doc.Name)
        except Exception:
            pass


_run()
'''


def _resolve_freecad_cmd(freecad_cmd: str | Path | None) -> Path:
    """Resolve the FreeCADCmd path from an explicit argument or env var.

    Raises ``RuntimeError`` with a clear message when no usable command can
    be located. Never invokes anything.
    """
    candidate: Path | None = None
    if freecad_cmd:
        candidate = Path(freecad_cmd)
        if candidate.is_dir():
            for option in (
                candidate / "bin" / "FreeCADCmd.exe",
                candidate / "bin" / "FreeCADCmd",
                candidate / "FreeCADCmd",
                candidate / "FreeCADCmd.exe",
            ):
                if option.exists():
                    candidate = option
                    break
    if candidate is None:
        env_value = os.environ.get("FREECAD_MCP_FREECAD_PATH")
        if env_value:
            return _resolve_freecad_cmd(env_value)
        raise RuntimeError(
            "FreeCADCmd is not available. Set FREECAD_MCP_FREECAD_PATH or pass "
            "freecad_cmd=... to inspect_features()."
        )
    if not candidate.exists():
        raise RuntimeError(
            f"FreeCADCmd is not available: {candidate!s} does not exist."
        )
    return candidate


def inspect_features(
    source_path: str | Path,
    *,
    freecad_cmd: str | Path | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Inspect a CAD file's document objects and parameters via FreeCADCmd.

    Args:
        source_path: Absolute or relative path to a ``.FCStd``, ``.step``,
            or ``.stp`` file.
        freecad_cmd: Optional path to the ``FreeCADCmd`` executable or to
            the FreeCAD home directory. Falls back to the
            ``FREECAD_MCP_FREECAD_PATH`` environment variable.
        timeout: Subprocess timeout in seconds.

    Returns:
        A JSON-serialisable dict with shape::

            {
              "status": "ok",
              "schema_version": "0.1",
              "input_path": "...",
              "freecad_version": "...",
              "feature_count": N,
              "features": [
                {
                  "id": "Pad",
                  "label": "Pad",
                  "type": "PartDesign::Pad",
                  "source_object": "Pad",
                  "parameters": [
                    {"name": "Length", "value": 10.0, "unit": "mm",
                     "kind": "quantity", "editable": True,
                     "editor_mode": "editable"}
                  ],
                  "metadata": {"visibility": True, "has_shape": True,
                               "property_count": 1}
                }
              ]
            }

    Raises:
        FileNotFoundError: If ``source_path`` does not exist.
        ValueError: If ``source_path`` has an unsupported extension.
        RuntimeError: If ``FreeCADCmd`` cannot be located, the subprocess
            times out, exits non-zero, or returns invalid JSON.
        subprocess.TimeoutExpired: Re-raised from ``subprocess.run`` when
            the embedded script does not finish within ``timeout`` seconds.

    The function is intentionally read-only:
        * the FreeCAD document is opened, walked, and closed without saving;
        * no property is modified;
        * the subprocess command line is a fixed embedded script written
          into a temp file — caller input never enters the executed code;
        * the only caller-controlled data is the source-path environment
          variable, consumed by the script for a read-only document import.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source CAD file not found: {source}")
    extension = source.suffix
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension for feature inspection: {extension!r}. "
            f"Expected one of: {', '.join(sorted({e.lower() for e in SUPPORTED_EXTENSIONS}))}."
        )

    cmd_path = _resolve_freecad_cmd(freecad_cmd)

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        script_path = tmpdir / "inspect_features.py"
        result_path = tmpdir / "result.json"
        script_path.write_text(FREECAD_FEATURE_INSPECT_SCRIPT, encoding="utf-8")

        env = {
            **os.environ,
            _ENV_INPUT: str(source.resolve()),
            _ENV_RESULT: str(result_path),
        }

        try:
            proc = subprocess.run(
                [str(cmd_path), str(script_path)],
                env=env,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"FreeCAD inspection timed out after {timeout}s while inspecting {source}."
            ) from exc

        if not result_path.exists():
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            detail = stderr or stdout or f"exit code {proc.returncode}"
            raise RuntimeError(
                f"FreeCADCmd did not produce a feature-inspection result file. Detail: {detail}"
            )

        raw = result_path.read_text(encoding="utf-8")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"FreeCAD inspection returned invalid JSON: {exc}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            f"FreeCAD inspection returned an unexpected top-level shape: {type(result).__name__}"
        )

    if result.get("status") == "error":
        raise RuntimeError(
            f"FreeCAD inspection failed: {result.get('error') or 'unknown error'}"
        )

    return result
