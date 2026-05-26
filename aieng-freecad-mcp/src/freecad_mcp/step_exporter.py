"""Standalone FreeCADCmd-based STEP exporter.

Spawns a FreeCADCmd subprocess to export a STEP or FCStd file and produces
a new STEP file at the requested output path. Returns a JSON-serializable
result with artifact metadata.

Typical usage from aieng-ui:
    from freecad_mcp.step_exporter import run_step_export
    result = run_step_export("/path/in.step", "/path/out.step", "C:/FreeCAD/bin/FreeCADCmd.exe")
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

FREECAD_EXPORT_SCRIPT = """\
import json
import os
import FreeCAD
import Part

input_path = os.environ["AIENG_EXPORT_INPUT"]
output_path = os.environ["AIENG_EXPORT_OUTPUT"]
result_path = os.environ["AIENG_EXPORT_RESULT"]

ext = os.path.splitext(input_path)[1].lower()
doc = FreeCAD.newDocument("AiengExport")

if ext in (".step", ".stp"):
    Part.insert(input_path, doc.Name)
elif ext in (".fcstd",):
    doc = FreeCAD.open(input_path)
else:
    raise ValueError(f"Unsupported input format: {ext!r}. Expected .step, .stp, or .fcstd.")

doc.recompute()

objects = [obj for obj in doc.Objects if hasattr(obj, "Shape")]
if not objects:
    raise ValueError("No geometry objects found after import.")

shapes = [obj.Shape for obj in objects]
compound = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)

output_dir = os.path.dirname(os.path.abspath(output_path))
if output_dir:
    os.makedirs(output_dir, exist_ok=True)

compound.exportStep(output_path)

result = {
    "status": "ok",
    "inputPath": input_path,
    "outputPath": output_path,
    "adapter": "freecad",
    "freecad_version": ".".join(str(v) for v in FreeCAD.Version()[:3]),
    "object_count": len(objects),
    "artifacts": [
        {"path": output_path, "kind": "step", "role": "primary_geometry"}
    ],
    "warnings": [],
}

with open(result_path, "w", encoding="utf-8") as _f:
    json.dump(result, _f)
"""


# ---------------------------------------------------------------------------
# Python-level runner
# ---------------------------------------------------------------------------

def run_step_export(
    input_path: str | Path,
    output_path: str | Path,
    freecad_cmd: str | Path,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    """Export a CAD file to STEP format using FreeCADCmd.

    Args:
        input_path: Absolute path to a .step, .stp, or .fcstd file.
        output_path: Destination path for the exported STEP file.
        freecad_cmd: Path to the FreeCADCmd executable.
        timeout: Maximum seconds to wait for FreeCADCmd to finish.

    Returns:
        A dict with keys: status, inputPath, outputPath, adapter,
        freecad_version, object_count, artifacts, warnings.
        ``artifacts`` contains a list of ``{path, kind, role}`` dicts.

    Raises:
        FileNotFoundError: If input_path or freecad_cmd does not exist.
        RuntimeError: If FreeCADCmd fails or does not produce output.
        subprocess.TimeoutExpired: If FreeCADCmd exceeds timeout.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    freecad_cmd = Path(freecad_cmd)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not freecad_cmd.exists():
        raise FileNotFoundError(f"FreeCADCmd not found: {freecad_cmd}")

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "export_step.py"
        result_path = Path(tmpdir) / "result.json"

        script_path.write_text(FREECAD_EXPORT_SCRIPT, encoding="utf-8")

        env = {
            **os.environ,
            "AIENG_EXPORT_INPUT": str(input_path.resolve()),
            "AIENG_EXPORT_OUTPUT": str(output_path),
            "AIENG_EXPORT_RESULT": str(result_path),
        }

        proc = subprocess.run(
            [str(freecad_cmd), str(script_path)],
            env=env,
            capture_output=True,
            timeout=timeout,
        )

        if not result_path.exists():
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            stdout = proc.stdout.decode("utf-8", errors="replace").strip()
            detail = stderr or stdout or f"exit code {proc.returncode}"
            raise RuntimeError(
                f"FreeCADCmd did not produce a result file. Detail: {detail}"
            )

        return json.loads(result_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export CAD geometry to STEP via FreeCADCmd")
    parser.add_argument("input_path", help="Path to STEP or FCStd file")
    parser.add_argument("output_path", help="Destination path for STEP output")
    parser.add_argument(
        "--freecad-cmd",
        default=os.environ.get("FREECAD_MCP_FREECAD_PATH", ""),
        help="Path to FreeCADCmd executable or FreeCAD home directory",
    )
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    cmd_path = args.freecad_cmd
    if not cmd_path:
        print("Error: --freecad-cmd is required (or set FREECAD_MCP_FREECAD_PATH)", file=sys.stderr)
        sys.exit(1)

    cmd = Path(cmd_path)
    if cmd.is_dir():
        candidates = [
            cmd / "bin" / "FreeCADCmd.exe",
            cmd / "bin" / "FreeCADCmd",
            cmd / "bin" / "freecadcmd",
        ]
        for cand in candidates:
            if cand.exists():
                cmd = cand
                break
        else:
            print(f"Error: FreeCADCmd not found under {cmd_path}", file=sys.stderr)
            sys.exit(1)

    try:
        result = run_step_export(args.input_path, args.output_path, cmd, timeout=args.timeout)
        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
