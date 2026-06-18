"""Tests for the version-surface anti-drift script.

The version surface records hashes of MCP tool schemas, artifact schemas, and
agent skill prompts.  This suite verifies that the maintenance script detects
stale and missing surfaces correctly.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import update_version_surface as vss  # noqa: E402


@pytest.fixture
def temp_surface_path() -> Path:
    """Return a temporary path inside the repo so relative paths work."""
    test_dir = REPO_ROOT / "tmp_version_surface_test"
    test_dir.mkdir(exist_ok=True)
    path = test_dir / "version_surface.json"
    yield path
    shutil.rmtree(test_dir, ignore_errors=True)


def _write_valid_surface(path: Path) -> None:
    """Run the updater with the surface file redirected to a temp path."""
    with patch.object(vss, "VERSION_SURFACE_PATH", path):
        assert vss.main([]) == 0


def test_check_passes_when_surface_is_current(
    temp_surface_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A freshly-written surface passes the stale check."""
    _write_valid_surface(temp_surface_path)

    with patch.object(vss, "VERSION_SURFACE_PATH", temp_surface_path):
        assert vss.main(["--check"]) == 0

    captured = capsys.readouterr()
    assert "match" in captured.out.lower()


def test_check_fails_when_surface_hash_is_stale(
    temp_surface_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tampered hash is detected and reported as a mismatch."""
    _write_valid_surface(temp_surface_path)

    surface = json.loads(temp_surface_path.read_text(encoding="utf-8"))
    surface["surfaces"]["mcp_tool_surface"]["sha256"] = "0" * 64
    temp_surface_path.write_text(json.dumps(surface), encoding="utf-8")

    with patch.object(vss, "VERSION_SURFACE_PATH", temp_surface_path):
        assert vss.main(["--check"]) == 1

    captured = capsys.readouterr()
    assert "MISMATCH" in captured.err
    assert "mcp_tool_surface" in captured.err


def test_check_fails_when_surface_file_is_missing(
    temp_surface_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing surface file is treated as a mismatch."""
    assert not temp_surface_path.exists()

    with patch.object(vss, "VERSION_SURFACE_PATH", temp_surface_path):
        assert vss.main(["--check"]) == 1

    captured = capsys.readouterr()
    assert "missing" in captured.err.lower()


def test_write_surface_creates_file_with_expected_shape(
    temp_surface_path: Path,
) -> None:
    """The writer produces a well-formed version surface document."""
    with patch.object(vss, "VERSION_SURFACE_PATH", temp_surface_path):
        assert vss.main([]) == 0

    surface = json.loads(temp_surface_path.read_text(encoding="utf-8"))
    assert surface.get("format") == "aieng.version_surface.v1"
    for name in ("mcp_tool_surface", "artifact_schemas", "skill_prompts"):
        assert name in surface["surfaces"]
        assert len(surface["surfaces"][name]["sha256"]) == 64
