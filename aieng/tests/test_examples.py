"""Smoke tests for examples shipped with the core package."""

from __future__ import annotations

import importlib.util
import runpy
from pathlib import Path


def _cookbook_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "package_semantics_cookbook.py"


def test_package_semantics_cookbook_imports_and_builds_outputs() -> None:
    spec = importlib.util.spec_from_file_location("package_semantics_cookbook", _cookbook_path())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    outputs = module.build_cookbook_outputs()

    assert outputs["package_consistency"]["rollup"] == "ok"
    assert outputs["review_readiness"]["status"] == "ready"
    assert outputs["claim_proposal"]["claim_advancement"] == "none"
    assert outputs["audit_event"]["claim_advancement"] == "none"
    assert outputs["revalidation_transitions"]["after_geometry_edit"]["requires_revalidation"] is True
    assert outputs["revalidation_transitions"]["after_solver_validation"]["requires_revalidation"] is False


def test_package_semantics_cookbook_runs_as_script(capsys) -> None:  # type: ignore[no-untyped-def]
    runpy.run_path(str(_cookbook_path()), run_name="__main__")
    captured = capsys.readouterr()
    assert '"claim_advancement": "none"' in captured.out
