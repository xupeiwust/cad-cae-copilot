"""Tests for freecad_mcp.step_exporter.

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

from freecad_mcp.step_exporter import FREECAD_EXPORT_SCRIPT, run_step_export


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_RESULT = {
    "status": "ok",
    "inputPath": "/fake/part.step",
    "outputPath": "/fake/part_export.step",
    "adapter": "freecad",
    "freecad_version": "0.21.0",
    "object_count": 1,
    "artifacts": [
        {"path": "/fake/part_export.step", "kind": "step", "role": "primary_geometry"}
    ],
    "warnings": [],
}


@pytest.fixture()
def fake_step(tmp_path: Path) -> Path:
    step = tmp_path / "part.step"
    step.write_text("ISO-10303-21;\nDATA;\nEND-SECTION;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return step


@pytest.fixture()
def fake_freecad_cmd(tmp_path: Path) -> Path:
    cmd = tmp_path / "FreeCADCmd.exe"
    cmd.write_bytes(b"")
    return cmd


# ---------------------------------------------------------------------------
# Unit tests (mocked subprocess)
# ---------------------------------------------------------------------------

class TestRunStepExportUnit:
    def test_returns_parsed_result_on_success(
        self, fake_step: Path, fake_freecad_cmd: Path, tmp_path: Path
    ) -> None:
        def fake_run(cmd, *, env, capture_output, timeout):
            result_path = Path(env["AIENG_EXPORT_RESULT"])
            result_path.write_text(json.dumps(_MINIMAL_RESULT), encoding="utf-8")
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = b""
            mock.stdout = b""
            return mock

        output_path = tmp_path / "out.step"
        with patch("freecad_mcp.step_exporter.subprocess.run", side_effect=fake_run):
            result = run_step_export(fake_step, output_path, fake_freecad_cmd)

        assert result["status"] == "ok"
        assert result["object_count"] == 1
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["kind"] == "step"
        assert result["artifacts"][0]["role"] == "primary_geometry"

    def test_passes_correct_env_vars(
        self, fake_step: Path, fake_freecad_cmd: Path, tmp_path: Path
    ) -> None:
        captured_env: dict[str, str] = {}

        def fake_run(cmd, *, env, capture_output, timeout):
            captured_env.update(env)
            result_path = Path(env["AIENG_EXPORT_RESULT"])
            result_path.write_text(json.dumps(_MINIMAL_RESULT), encoding="utf-8")
            mock = MagicMock()
            mock.returncode = 0
            mock.stderr = b""
            mock.stdout = b""
            return mock

        output_path = tmp_path / "out.step"
        with patch("freecad_mcp.step_exporter.subprocess.run", side_effect=fake_run):
            run_step_export(fake_step, output_path, fake_freecad_cmd)

        assert captured_env["AIENG_EXPORT_INPUT"] == str(fake_step.resolve())
        assert captured_env["AIENG_EXPORT_OUTPUT"] == str(output_path)
        assert "AIENG_EXPORT_RESULT" in captured_env

    def test_raises_runtime_error_when_no_result_file(
        self, fake_step: Path, fake_freecad_cmd: Path, tmp_path: Path
    ) -> None:
        def fake_run(cmd, *, env, capture_output, timeout):
            mock = MagicMock()
            mock.returncode = 1
            mock.stderr = b"FreeCAD crashed"
            mock.stdout = b""
            return mock

        output_path = tmp_path / "out.step"
        with patch("freecad_mcp.step_exporter.subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="did not produce a result file"):
                run_step_export(fake_step, output_path, fake_freecad_cmd)

    def test_raises_file_not_found_for_missing_input(
        self, tmp_path: Path, fake_freecad_cmd: Path
    ) -> None:
        missing = tmp_path / "nonexistent.step"
        output_path = tmp_path / "out.step"
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            run_step_export(missing, output_path, fake_freecad_cmd)

    def test_raises_file_not_found_for_missing_cmd(
        self, fake_step: Path, tmp_path: Path
    ) -> None:
        missing_cmd = tmp_path / "FreeCADCmd_missing.exe"
        output_path = tmp_path / "out.step"
        with pytest.raises(FileNotFoundError, match="FreeCADCmd not found"):
            run_step_export(fake_step, output_path, missing_cmd)

    def test_propagates_timeout_error(
        self, fake_step: Path, fake_freecad_cmd: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "out.step"
        with patch(
            "freecad_mcp.step_exporter.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="FreeCADCmd", timeout=1),
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                run_step_export(fake_step, output_path, fake_freecad_cmd, timeout=1)


# ---------------------------------------------------------------------------
# Script content checks (no subprocess)
# ---------------------------------------------------------------------------

class TestExportScriptContent:
    def test_script_reads_env_vars(self) -> None:
        assert "AIENG_EXPORT_INPUT" in FREECAD_EXPORT_SCRIPT
        assert "AIENG_EXPORT_OUTPUT" in FREECAD_EXPORT_SCRIPT
        assert "AIENG_EXPORT_RESULT" in FREECAD_EXPORT_SCRIPT

    def test_script_imports_freecad_and_part(self) -> None:
        assert "import FreeCAD" in FREECAD_EXPORT_SCRIPT
        assert "import Part" in FREECAD_EXPORT_SCRIPT

    def test_script_handles_step_extension(self) -> None:
        assert "Part.insert" in FREECAD_EXPORT_SCRIPT

    def test_script_handles_fcstd_extension(self) -> None:
        assert "FreeCAD.open" in FREECAD_EXPORT_SCRIPT

    def test_script_calls_export_step(self) -> None:
        assert "exportStep" in FREECAD_EXPORT_SCRIPT

    def test_script_produces_artifacts_list(self) -> None:
        assert '"artifacts"' in FREECAD_EXPORT_SCRIPT
        assert "primary_geometry" in FREECAD_EXPORT_SCRIPT


# ---------------------------------------------------------------------------
# Integration tests — require real FreeCAD
# ---------------------------------------------------------------------------

@pytest.mark.freecad
def test_export_step_with_real_freecad(tmp_path: Path) -> None:
    """Run the actual FreeCAD subprocess on a minimal STEP file.

    This test is skipped when FreeCAD is not importable (see conftest.py).
    Requires FREECAD_MCP_FREECAD_PATH or FREECAD_HOME to be set.
    """
    import os

    home = os.environ.get("FREECAD_MCP_FREECAD_PATH") or os.environ.get("FREECAD_HOME", "")
    if not home:
        pytest.skip("FREECAD_MCP_FREECAD_PATH not set")

    home_path = Path(home)
    candidates = [
        home_path / "bin" / "FreeCADCmd.exe",
        home_path / "bin" / "FreeCADCmd",
        home_path / "bin" / "freecadcmd",
    ]
    cmd = next((c for c in candidates if c.exists()), None)
    if cmd is None:
        pytest.skip(f"FreeCADCmd not found under {home}")

    step_content = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Test cube'),'2;1');
FILE_NAME('test_cube.step','2026-01-01T00:00:00',(''),(''),
  'Open CASCADE STEP processor 6.7','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
ENDSEC;
END-ISO-10303-21;
"""
    input_path = tmp_path / "input.step"
    output_path = tmp_path / "output.step"
    input_path.write_text(step_content, encoding="utf-8")

    result = run_step_export(input_path, output_path, cmd, timeout=60)

    assert result["status"] == "ok"
    assert len(result["artifacts"]) >= 1
    assert result["artifacts"][0]["kind"] == "step"
    assert "freecad_version" in result
