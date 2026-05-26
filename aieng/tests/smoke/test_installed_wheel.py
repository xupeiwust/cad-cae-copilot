"""Minimal installed-wheel smoke test.

Runs against an installed `aieng` package outside the source tree. Confirms:
  * the CLI entry point launches and shows the alpha-aware command surface,
  * packaged schemas can be located via :mod:`importlib.resources`,
  * the core public API can be imported without filesystem assumptions about
    the repo root.

This file is intentionally side-effect free and does not depend on pytest
fixtures from the source tree, so it can be invoked as either a pytest test
or a plain script:

    python -m tests.smoke.test_installed_wheel
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REQUIRED_SCHEMAS = (
    "manifest.schema.json",
    "evidence_index.schema.json",
    "modeling_plan.schema.json",
)


def _cli_subprocess_env() -> dict[str, str]:
    """Return an env that works for source-tree and installed-package smoke runs.

    When this file is run from a checkout, pytest's in-process imports can see
    ``src/`` through test configuration, but a child ``python -m aieng.cli``
    process cannot.  Keep the installed-wheel path unchanged while adding the
    local ``src`` directory only when it exists.
    """
    env = os.environ.copy()
    src = Path(__file__).resolve().parents[2] / "src"
    if src.exists():
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src) if not existing else f"{src}{os.pathsep}{existing}"
    return env


def test_importlib_resources_loads_packaged_schemas() -> None:
    from importlib.resources import files

    schemas = files("aieng.schemas")
    for name in REQUIRED_SCHEMAS:
        resource = schemas.joinpath(name)
        assert resource.is_file(), f"schema missing from installed package: {name}"
        payload = json.loads(resource.read_text(encoding="utf-8"))
        assert isinstance(payload, dict) and payload.get("$schema"), name


def test_public_api_imports_without_repo_root() -> None:
    import aieng  # noqa: F401
    from aieng import (
        FORMAT_VERSION,
        package_consistency,
        review_readiness,
        claim_proposal,
    )

    assert isinstance(FORMAT_VERSION, str) and FORMAT_VERSION
    assert callable(getattr(package_consistency, "run_package_consistency_checks", None))
    assert callable(getattr(review_readiness, "build_review_readiness", None))
    assert callable(getattr(claim_proposal, "build_claim_proposal", None))


def test_cli_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aieng.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_subprocess_env(),
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "aieng" in out
    assert "update-claim" not in out, "update-claim CLI surface must not appear in alpha"


def test_cli_validate_subcommand_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aieng.cli", "validate", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_subprocess_env(),
    )
    assert result.returncode == 0, result.stderr
    assert "validate" in result.stdout.lower()


if __name__ == "__main__":  # pragma: no cover - manual invocation
    test_importlib_resources_loads_packaged_schemas()
    test_public_api_imports_without_repo_root()
    test_cli_help_runs()
    test_cli_validate_subcommand_help()
    print("installed-wheel smoke: OK")
