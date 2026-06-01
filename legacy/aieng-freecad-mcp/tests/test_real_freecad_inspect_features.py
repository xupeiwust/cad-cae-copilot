"""Opt-in real FreeCAD integration test for ``inspect_features`` (AIENG v0.22).

This test runs only when explicitly enabled. By default it is skipped.

To run:
    AIENG_RUN_FREECAD_INTEGRATION=1 python -m pytest -q -k "real_freecad_inspect"

Requires FreeCADCmd to be available on PATH or set via FREECAD_MCP_FREECAD_PATH.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from freecad_mcp.aieng_bridge import inspect_features


# ------------------------------------------------------------------
# Gating
# ------------------------------------------------------------------


def _integration_enabled() -> bool:
    return os.environ.get("AIENG_RUN_FREECAD_INTEGRATION", "") == "1"


def _freecad_cmd_available() -> Path | None:
    """Return path to FreeCADCmd if available, else None."""
    env_path = os.environ.get("FREECAD_MCP_FREECAD_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_dir():
            for name in ("FreeCADCmd.exe", "bin/FreeCADCmd.exe", "FreeCADCmd", "bin/FreeCADCmd"):
                cand = candidate / name
                if cand.exists():
                    return cand
        elif candidate.exists():
            return candidate
    # Try PATH
    for name in ("FreeCADCmd.exe", "FreeCADCmd"):
        import shutil as _shutil
        found = _shutil.which(name)
        if found:
            return Path(found)
    return None


def _skip_or_fail() -> None:
    if not _integration_enabled():
        pytest.skip("Set AIENG_RUN_FREECAD_INTEGRATION=1 to run real FreeCAD tests")
    cmd = _freecad_cmd_available()
    if cmd is None:
        pytest.skip("FreeCADCmd not available. Install FreeCAD or set FREECAD_MCP_FREECAD_PATH")
    return cmd


# ------------------------------------------------------------------
# Fixture generation
# ------------------------------------------------------------------


_GENERATE_MINIMAL_FCSTD_SCRIPT = r'''
import FreeCAD as App
import Part

doc = App.newDocument("MinimalBox")
box = doc.addObject("Part::Box", "Box")
box.Length = 10.0
box.Width = 5.0
box.Height = 3.0
doc.recompute()

doc.saveAs("__OUTPUT_PATH__")
'''


def _generate_minimal_fcstd(output_path: Path, freecad_cmd: Path) -> None:
    """Generate a tiny FCStd file using FreeCADCmd."""
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        script_path = tmpdir / "generate.py"
        script_content = _GENERATE_MINIMAL_FCSTD_SCRIPT.replace("__OUTPUT_PATH__", str(output_path.resolve()).replace("\\", "/"))
        script_path.write_text(script_content, encoding="utf-8")

        proc = subprocess.run(
            [str(freecad_cmd), str(script_path)],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"FreeCADCmd failed to generate fixture. stderr: {stderr}\nstdout: {stdout}"
            )


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.freecad
class TestRealFreecadInspectFeatures:
    def test_inspect_minimal_fcstd(self, tmp_path: Path) -> None:
        """Generate a minimal box FCStd and inspect it read-only."""
        freecad_cmd = _skip_or_fail()

        fixture_path = tmp_path / "minimal_box.FCStd"
        _generate_minimal_fcstd(fixture_path, freecad_cmd)
        assert fixture_path.exists(), "Fixture generation did not create the FCStd file"

        before_stat = fixture_path.stat()

        result = inspect_features(fixture_path, freecad_cmd=freecad_cmd, timeout=120)

        after_stat = fixture_path.stat()

        # --- Result shape assertions ---
        assert isinstance(result, dict)
        assert result.get("status") == "ok"
        assert result.get("schema_version") == "0.1"
        assert "features" in result
        features = result["features"]
        assert isinstance(features, list)
        assert len(features) >= 1, "Expected at least one feature from the minimal box"

        # --- Feature content assertions ---
        feature_ids = {f.get("id") for f in features if isinstance(f, dict)}
        assert "Box" in feature_ids, f"Expected 'Box' feature, got {feature_ids}"

        box_feature = next((f for f in features if f.get("id") == "Box"), None)
        assert box_feature is not None
        assert box_feature.get("type") == "Part::Box"
        assert "parameters" in box_feature
        params = box_feature["parameters"]
        assert isinstance(params, list)
        param_names = {p.get("name") for p in params}
        assert "Length" in param_names or "Width" in param_names or "Height" in param_names

        # --- Metadata assertions ---
        assert result.get("feature_count") >= 1
        assert "freecad_version" in result
        assert result.get("input_path") == str(fixture_path.resolve())

        # --- Read-only safety assertions ---
        assert before_stat.st_size == after_stat.st_size, "FCStd file size changed after inspection"
        assert before_stat.st_mtime_ns == after_stat.st_mtime_ns, "FCStd file mtime changed after inspection"

    def test_inspect_parametric_bracket_example(self, tmp_path: Path) -> None:
        """Inspect the existing parametric_bracket example FCStd if available."""
        freecad_cmd = _skip_or_fail()

        example_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "parametric_bracket"
            / "freecad"
            / "source.FCStd"
        )
        if not example_path.exists():
            pytest.skip("parametric_bracket example FCStd not found")

        before_stat = example_path.stat()

        result = inspect_features(example_path, freecad_cmd=freecad_cmd, timeout=120)

        after_stat = example_path.stat()

        assert result.get("status") == "ok"
        features = result.get("features") or []
        assert len(features) >= 1

        # Read-only check
        assert before_stat.st_size == after_stat.st_size
        assert before_stat.st_mtime_ns == after_stat.st_mtime_ns
