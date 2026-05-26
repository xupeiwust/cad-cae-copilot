"""Tests for FreeCAD availability check.

Default tests do **not** require FreeCAD.
Tests marked with ``@pytest.mark.freecad`` run only when ``FREECAD_HOME`` is set
and point to a valid installation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from freecad_mcp.aieng_bridge.availability import (
    FreecadAvailabilityResult,
    check_freecad_availability,
)


class TestAvailabilityNoFreeCAD:
    """Tests that do not require FreeCAD."""

    def test_no_config_returns_not_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = check_freecad_availability()
        assert result.configured is False
        assert result.configured_path is None
        assert result.path_exists is False
        assert result.executable is None
        assert result.python_entry_point is None
        assert result.version is None
        assert result.claims_advanced is False
        assert result.freecad_mutated is False
        assert any("FREECAD_HOME is not set" in m for m in result.missing)

    def test_configured_path_not_exists(self, tmp_path: Path) -> None:
        fake_path = str(tmp_path / "nonexistent" / "freecad")
        with patch.dict(os.environ, {"FREECAD_HOME": fake_path}, clear=True):
            result = check_freecad_availability()
        assert result.configured is True
        assert result.configured_path == fake_path
        assert result.path_exists is False
        assert result.claims_advanced is False
        assert any("does not exist" in m for m in result.missing)

    def test_configured_path_exists_but_empty(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"FREECAD_HOME": str(tmp_path)}, clear=True):
            result = check_freecad_availability()
        assert result.configured is True
        assert result.path_exists is True
        assert result.executable is None
        assert result.python_entry_point is None
        assert any("executable not found" in u for u in result.unsupported)
        assert any("lib directory" in u for u in result.unsupported)

    def test_executable_detected(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True)
        exe_name = "FreeCAD.exe" if sys.platform == "win32" else "FreeCAD"
        (bin_dir / exe_name).touch()
        with patch.dict(os.environ, {"FREECAD_HOME": str(tmp_path)}, clear=True):
            result = check_freecad_availability()
        assert result.executable == str(bin_dir / exe_name)
        assert result.python_entry_point is None

    def test_python_entry_point_detected(self, tmp_path: Path) -> None:
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True)
        with patch.dict(os.environ, {"FREECAD_HOME": str(tmp_path)}, clear=True):
            result = check_freecad_availability()
        assert result.python_entry_point == str(lib_dir)
        assert result.executable is None

    def test_mcp_path_takes_precedence_over_home(self, tmp_path: Path) -> None:
        mcp_path = tmp_path / "mcp_freecad"
        home_path = tmp_path / "home_freecad"
        with patch.dict(
            os.environ,
            {
                "FREECAD_MCP_FREECAD_PATH": str(mcp_path),
                "FREECAD_HOME": str(home_path),
            },
            clear=True,
        ):
            result = check_freecad_availability()
        # App-specific override wins even when it does not exist
        assert result.configured_path == str(mcp_path)

    def test_home_used_when_mcp_not_set(self, tmp_path: Path) -> None:
        with patch.dict(
            os.environ,
            {"FREECAD_HOME": str(tmp_path)},
            clear=True,
        ):
            result = check_freecad_availability()
        assert result.configured_path == str(tmp_path)

    def test_result_model_extra_forbidden(self) -> None:
        with pytest.raises(ValueError):
            FreecadAvailabilityResult(
                configured=True,
                unknown_field="bad",  # type: ignore[call-arg]
            )


@pytest.mark.freecad
class TestAvailabilityRealFreeCAD:
    """Tests that require a real FreeCAD installation."""

    def test_real_freecad_availability(self) -> None:
        freecad_home = os.environ.get("FREECAD_HOME")
        if not freecad_home:
            pytest.skip("FREECAD_HOME not set")

        result = check_freecad_availability()
        assert result.configured is True
        assert result.path_exists is True
        assert result.claims_advanced is False
        assert result.freecad_mutated is False
        # When real FreeCAD is present we expect at least the executable or lib
        assert result.executable is not None or result.python_entry_point is not None
