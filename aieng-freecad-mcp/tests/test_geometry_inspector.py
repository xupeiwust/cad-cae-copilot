"""Tests for freecad_mcp.geometry_inspector.

Unit tests use a mocked subprocess so FreeCAD is not required.
Tests marked @pytest.mark.freecad require a real FreeCAD installation
and are skipped when FreeCAD is not importable (see conftest.py).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from freecad_mcp.geometry_inspector import FREECAD_INSPECT_SCRIPT, run_geometry_inspection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_RESULT = {
    "status": "ok",
    "input_path": "/fake/part.step",
    "freecad_version": "0.21.0",
    "object_count": 1,
    "objects": [
        {
            "name": "Shape",
            "label": "Shape",
            "solid_count": 1,
            "shell_count": 1,
            "face_count": 6,
            "edge_count": 12,
            "vertex_count": 8,
            "volume_mm3": 1000.0,
            "area_mm2": 600.0,
        }
    ],
    "total_solid_count": 1,
    "total_face_count": 6,
    "total_edge_count": 12,
    "total_vertex_count": 8,
    "total_volume_mm3": 1000.0,
    "total_area_mm2": 600.0,
    "bounding_box": {
        "xmin": 0.0, "xmax": 10.0,
        "ymin": 0.0, "ymax": 10.0,
        "zmin": 0.0, "zmax": 10.0,
        "xlen": 10.0, "ylen": 10.0, "zlen": 10.0,
    },
}


@pytest.fixture()
def fake_step(tmp_path: Path) -> Path:
    """Minimal STEP file placeholder (content is not parsed by FreeCAD in mocked tests)."""
    step = tmp_path / "part.step"
    step.write_text("ISO-10303-21;\nDATA;\nEND-SECTION;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return step


@pytest.fixture()
def fake_freecad_cmd(tmp_path: Path) -> Path:
    """Fake FreeCADCmd executable (a zero-byte file whose existence satisfies the check)."""
    cmd = tmp_path / "FreeCADCmd.exe"
    cmd.write_bytes(b"")
    return cmd


# ---------------------------------------------------------------------------
# Unit tests (mocked subprocess)
# ---------------------------------------------------------------------------

class TestRunGeometryInspectionUnit:
    def test_returns_parsed_result_on_success(
        self, fake_step: Path, fake_freecad_cmd: Path, tmp_path: Path
    ) -> None:
        def fake_run(cmd, *, env, capture_output, timeout):
            result_path = Path(env["AIENG_INSPECT_RESULT"])
            result_path.write_text(json.dumps(_MINIMAL_RESULT), encoding="utf-8")
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = b""
            mock.stdout = b""
            return mock

        with patch("freecad_mcp.geometry_inspector.subprocess.run", side_effect=fake_run):
            result = run_geometry_inspection(fake_step, fake_freecad_cmd)

        assert result["status"] == "ok"
        assert result["total_face_count"] == 6
        assert result["bounding_box"]["xlen"] == 10.0
        assert result["object_count"] == 1
        assert result["objects"][0]["solid_count"] == 1

    def test_passes_correct_env_vars(
        self, fake_step: Path, fake_freecad_cmd: Path
    ) -> None:
        captured_env: dict[str, str] = {}

        def fake_run(cmd, *, env, capture_output, timeout):
            captured_env.update(env)
            result_path = Path(env["AIENG_INSPECT_RESULT"])
            result_path.write_text(json.dumps(_MINIMAL_RESULT), encoding="utf-8")
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = b""
            mock.stdout = b""
            return mock

        with patch("freecad_mcp.geometry_inspector.subprocess.run", side_effect=fake_run):
            run_geometry_inspection(fake_step, fake_freecad_cmd)

        assert captured_env["AIENG_INSPECT_INPUT"] == str(fake_step.resolve())
        assert "AIENG_INSPECT_RESULT" in captured_env

    def test_raises_runtime_error_when_no_result_file(
        self, fake_step: Path, fake_freecad_cmd: Path
    ) -> None:
        def fake_run(cmd, *, env, capture_output, timeout):
            mock = MagicMock()
            mock.returncode = 1
            mock.stderr = b"FreeCAD crashed"
            mock.stdout = b""
            return mock

        with patch("freecad_mcp.geometry_inspector.subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="did not produce a result file"):
                run_geometry_inspection(fake_step, fake_freecad_cmd)

    def test_raises_file_not_found_for_missing_input(
        self, tmp_path: Path, fake_freecad_cmd: Path
    ) -> None:
        missing = tmp_path / "nonexistent.step"
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            run_geometry_inspection(missing, fake_freecad_cmd)

    def test_raises_file_not_found_for_missing_cmd(
        self, fake_step: Path, tmp_path: Path
    ) -> None:
        missing_cmd = tmp_path / "FreeCADCmd_missing.exe"
        with pytest.raises(FileNotFoundError, match="FreeCADCmd not found"):
            run_geometry_inspection(fake_step, missing_cmd)

    def test_propagates_timeout_error(
        self, fake_step: Path, fake_freecad_cmd: Path
    ) -> None:
        with patch(
            "freecad_mcp.geometry_inspector.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="FreeCADCmd", timeout=1),
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                run_geometry_inspection(fake_step, fake_freecad_cmd, timeout=1)


# ---------------------------------------------------------------------------
# Script content checks (no subprocess)
# ---------------------------------------------------------------------------

class TestInspectScriptContent:
    def test_script_reads_env_vars(self) -> None:
        assert "AIENG_INSPECT_INPUT" in FREECAD_INSPECT_SCRIPT
        assert "AIENG_INSPECT_RESULT" in FREECAD_INSPECT_SCRIPT

    def test_script_imports_freecad_and_part(self) -> None:
        assert "import FreeCAD" in FREECAD_INSPECT_SCRIPT
        assert "import Part" in FREECAD_INSPECT_SCRIPT

    def test_script_handles_step_extension(self) -> None:
        assert "Part.insert" in FREECAD_INSPECT_SCRIPT

    def test_script_handles_fcstd_extension(self) -> None:
        assert "FreeCAD.open" in FREECAD_INSPECT_SCRIPT

    def test_script_produces_bounding_box(self) -> None:
        assert "bounding_box" in FREECAD_INSPECT_SCRIPT
        assert "BoundBox" in FREECAD_INSPECT_SCRIPT

    def test_script_produces_volume_and_area(self) -> None:
        assert "volume_mm3" in FREECAD_INSPECT_SCRIPT
        assert "area_mm2" in FREECAD_INSPECT_SCRIPT


# ---------------------------------------------------------------------------
# Integration tests — require real FreeCAD
# ---------------------------------------------------------------------------

@pytest.mark.freecad
def test_inspect_geometry_with_real_freecad(tmp_path: Path) -> None:
    """Run the actual FreeCAD subprocess on a minimal STEP string.

    This test is skipped when FreeCAD is not importable (see conftest.py).
    Requires FREECAD_MCP_FREECAD_PATH or FREECAD_HOME to be set.
    """
    import os
    import shutil

    home = os.environ.get("FREECAD_MCP_FREECAD_PATH") or os.environ.get("FREECAD_HOME", "")
    if not home:
        pytest.skip("FREECAD_MCP_FREECAD_PATH not set")

    # Locate FreeCADCmd
    home_path = Path(home)
    candidates = [
        home_path / "bin" / "FreeCADCmd.exe",
        home_path / "bin" / "FreeCADCmd",
        home_path / "bin" / "freecadcmd",
    ]
    cmd = next((c for c in candidates if c.exists()), None)
    if cmd is None:
        pytest.skip(f"FreeCADCmd not found under {home}")

    # Write a minimal STEP cube (unit cube 10x10x10 mm)
    step_content = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Test cube'),'2;1');
FILE_NAME('test_cube.step','2026-01-01T00:00:00',(''),(''),
  'Open CASCADE STEP processor 6.7','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1=PRODUCT_DEFINITION_CONTEXT('part definition',#2,'design');
#2=APPLICATION_CONTEXT('automotive design');
#3=PRODUCT_DEFINITION('',$,#4,#1);
#4=PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',#5,.NOT_KNOWN.);
#5=PRODUCT('TestCube','TestCube','',(#6));
#6=PRODUCT_CONTEXT('',#2,'mechanical');
#7=NEXT_ASSEMBLY_USAGE_OCCURRENCE('','','',#3,#3,$);
ENDSEC;
END-ISO-10303-21;
"""
    step_path = tmp_path / "test_cube.step"
    step_path.write_text(step_content, encoding="utf-8")

    result = run_geometry_inspection(step_path, cmd, timeout=60)

    assert result["status"] == "ok"
    assert isinstance(result["object_count"], int)
    assert "bounding_box" in result
    assert "total_face_count" in result
    assert "freecad_version" in result
