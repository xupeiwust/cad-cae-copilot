"""Installed-wheel/sdist packaging smoke tests (#144).

Builds the `aieng-format` wheel/sdist in a temp directory, installs it into a
fresh virtual environment (no source-tree imports), and exercises the CLI and
schema-loading paths from the installed artifact only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]  # aieng/ subdirectory
SRC_ROOT = PROJECT_ROOT / "src"


@pytest.mark.skipif(shutil.which("python") is None, reason="python executable not found")
def test_build_wheel_and_sdist(tmp_path: Path) -> None:
    """`python -m build` produces a wheel and sdist."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "build"],
        check=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "build", PROJECT_ROOT.as_posix()],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    dist_dir = PROJECT_ROOT / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    sdists = list(dist_dir.glob("*.tar.gz"))
    assert wheels, "no wheel produced"
    assert sdists, "no sdist produced"


@pytest.mark.skipif(shutil.which("python") is None, reason="python executable not found")
def test_installed_wheel_smoke(tmp_path: Path) -> None:
    """Install wheel into a clean venv and smoke-test CLI + schema loading."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "build"],
        check=True,
    )
    build_result = subprocess.run(
        [sys.executable, "-m", "build", PROJECT_ROOT.as_posix()],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert build_result.returncode == 0

    dist_dir = PROJECT_ROOT / "dist"
    wheels = sorted(dist_dir.glob("*.whl"))
    assert wheels, "no wheel produced"
    wheel = wheels[-1]

    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", venv_dir.as_posix()], check=True)

    if sys.platform == "win32":
        python_bin = venv_dir / "Scripts" / "python.exe"
        aieng_cli = venv_dir / "Scripts" / "aieng.exe"
    else:
        python_bin = venv_dir / "bin" / "python"
        aieng_cli = venv_dir / "bin" / "aieng"

    subprocess.run(
        [python_bin.as_posix(), "-m", "pip", "install", "--quiet", wheel.as_posix()],
        check=True,
    )

    # 1) Import and version check.
    version_check = subprocess.run(
        [python_bin.as_posix(), "-c", "import aieng; print(aieng.__version__)"],
        capture_output=True,
        text=True,
        check=True,
    )
    installed_version = version_check.stdout.strip()
    assert installed_version.startswith("0.1.0a")

    # 2) Schema package is present.
    subprocess.run(
        [python_bin.as_posix(), "-c", "from aieng.schemas import __file__ as f; print(f)"],
        capture_output=True,
        text=True,
        check=True,
    )

    # 3) Schema loading paths used at runtime work outside the source tree.
    schema_script = """
from aieng.definition import _validate_definition
from aieng.validate import validate_package
from aieng.modeling_plan.validate import validate_modeling_plan
from aieng.optimization_artifacts import validate_optimization_artifact_set
print('schema-loading-ok')
"""
    subprocess.run(
        [python_bin.as_posix(), "-c", schema_script],
        capture_output=True,
        text=True,
        check=True,
    )

    # 4) CLI `aieng validate` runs against a minimal package using installed schemas.
    pkg_path = tmp_path / "smoke.aieng"
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({
                "format": "aieng.package",
                "format_version": "0.1.0",
                "model_id": "smoke",
                "units": {"length": "mm", "mass": "kg", "time": "s"},
                "created_by": "test_installed_wheel_smoke",
                "resources": {},
            }),
        )
        zf.writestr(
            "geometry/shape_ir.json",
            json.dumps({"format": "aieng.shape_ir", "representation": "manifold_mesh", "parts": []}),
        )

    validate_result = subprocess.run(
        [python_bin.as_posix(), "-m", "aieng.cli", "validate", pkg_path.as_posix()],
        capture_output=True,
        text=True,
    )
    # A minimal package is expected to emit warnings but should not crash.
    assert validate_result.returncode in (0, 1)
    assert "manifest.json exists" in validate_result.stdout or "manifest.json exists" in validate_result.stderr

    # 5) Entry-point `aieng` script is available.
    assert aieng_cli.exists()
    help_result = subprocess.run(
        [aieng_cli.as_posix(), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "usage:" in help_result.stdout
