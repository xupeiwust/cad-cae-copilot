"""Standalone FreeCADCmd-based geometry inspector.

Spawns a FreeCADCmd subprocess to inspect a STEP or FCStd file and returns
a JSON-serializable summary of the geometry (bounding box, face/edge/vertex
counts, volume, surface area). This module has no dependency on the XML-RPC
bridge used by FreecadFemCaeToolset.

Typical usage from aieng-ui:
    from freecad_mcp.geometry_inspector import run_geometry_inspection
    result = run_geometry_inspection("/path/to/part.step", "C:/FreeCAD/bin/FreeCADCmd.exe")
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

FREECAD_INSPECT_SCRIPT = """\
import json
import os
import FreeCAD
import Part

input_path = os.environ["AIENG_INSPECT_INPUT"]
result_path = os.environ["AIENG_INSPECT_RESULT"]

ext = os.path.splitext(input_path)[1].lower()
doc = FreeCAD.newDocument("AiengInspect")

if ext in (".step", ".stp"):
    Part.insert(input_path, doc.Name)
elif ext in (".fcstd",):
    doc = FreeCAD.open(input_path)
else:
    raise ValueError(f"Unsupported file type: {ext!r}. Expected .step, .stp, or .fcstd.")

doc.recompute()

objects = [obj for obj in doc.Objects if hasattr(obj, "Shape")]
if not objects:
    raise ValueError("No geometry objects found after file import.")

shapes = [obj.Shape for obj in objects]
compound = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)
bbox = compound.BoundBox

object_summaries = []
for obj in objects:
    s = obj.Shape
    object_summaries.append({
        "name": obj.Name,
        "label": getattr(obj, "Label", obj.Name),
        "solid_count": len(s.Solids),
        "shell_count": len(s.Shells),
        "face_count": len(s.Faces),
        "edge_count": len(s.Edges),
        "vertex_count": len(s.Vertexes),
        "volume_mm3": round(float(s.Volume), 6),
        "area_mm2": round(float(s.Area), 6),
    })

result = {
    "status": "ok",
    "input_path": input_path,
    "freecad_version": ".".join(str(v) for v in FreeCAD.Version()[:3]),
    "object_count": len(objects),
    "objects": object_summaries,
    "total_solid_count": sum(o["solid_count"] for o in object_summaries),
    "total_face_count": sum(o["face_count"] for o in object_summaries),
    "total_edge_count": sum(o["edge_count"] for o in object_summaries),
    "total_vertex_count": sum(o["vertex_count"] for o in object_summaries),
    "total_volume_mm3": round(float(compound.Volume), 6),
    "total_area_mm2": round(float(compound.Area), 6),
    "bounding_box": {
        "xmin": round(float(bbox.XMin), 6),
        "xmax": round(float(bbox.XMax), 6),
        "ymin": round(float(bbox.YMin), 6),
        "ymax": round(float(bbox.YMax), 6),
        "zmin": round(float(bbox.ZMin), 6),
        "zmax": round(float(bbox.ZMax), 6),
        "xlen": round(float(bbox.XLength), 6),
        "ylen": round(float(bbox.YLength), 6),
        "zlen": round(float(bbox.ZLength), 6),
    },
}

with open(result_path, "w", encoding="utf-8") as _f:
    json.dump(result, _f)
"""


# ---------------------------------------------------------------------------
# Python-level runner
# ---------------------------------------------------------------------------

def run_geometry_inspection(
    input_path: str | Path,
    freecad_cmd: str | Path,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    """Inspect a CAD file using FreeCADCmd and return a geometry summary.

    Args:
        input_path: Absolute path to a .step, .stp, or .fcstd file.
        freecad_cmd: Path to the FreeCADCmd executable.
        timeout: Maximum seconds to wait for FreeCADCmd to finish.

    Returns:
        A dict with keys: status, input_path, freecad_version, object_count,
        objects, total_solid_count, total_face_count, total_edge_count,
        total_vertex_count, total_volume_mm3, total_area_mm2, bounding_box.

    Raises:
        FileNotFoundError: If input_path or freecad_cmd does not exist.
        RuntimeError: If FreeCADCmd fails or does not produce output.
        subprocess.TimeoutExpired: If FreeCADCmd exceeds timeout.
    """
    input_path = Path(input_path)
    freecad_cmd = Path(freecad_cmd)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not freecad_cmd.exists():
        raise FileNotFoundError(f"FreeCADCmd not found: {freecad_cmd}")

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "inspect_geometry.py"
        result_path = Path(tmpdir) / "result.json"

        script_path.write_text(FREECAD_INSPECT_SCRIPT, encoding="utf-8")

        env = {
            **os.environ,
            "AIENG_INSPECT_INPUT": str(input_path.resolve()),
            "AIENG_INSPECT_RESULT": str(result_path),
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

    parser = argparse.ArgumentParser(description="Inspect CAD geometry via FreeCADCmd")
    parser.add_argument("input_path", help="Path to STEP or FCStd file")
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

    # Accept either a path to FreeCADCmd or to the FreeCAD home directory
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
        result = run_geometry_inspection(args.input_path, cmd, timeout=args.timeout)
        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
