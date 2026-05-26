from __future__ import annotations

from pathlib import Path

import pytest

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "src" / "aieng" / "schemas"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip geometry-marked tests when OCC is installed but STEP parsing is broken.

    When OCC is absent, pytest.importorskip guards in each test handle skipping.
    This hook handles the trickier case: OCP importable but STEP extraction fails
    (e.g. 'OCC/OCP found no transferable shapes in the STEP file'), which would
    otherwise cause false failures that block unrelated PRs.
    """
    try:
        from aieng.geometry.backend import detect_occ_runtime

        if not detect_occ_runtime()["available"]:
            return  # OCC absent; per-test importorskip guards are sufficient

        from _geometry_capability import has_working_occ_step_backend

        if has_working_occ_step_backend():
            return  # OCC present and working; run all geometry tests normally
    except Exception:
        return  # never block collection on probe errors

    skip = pytest.mark.skip(
        reason="OCP installed but STEP backend non-functional in this environment "
               "(no transferable shapes); see tests/_geometry_capability.py"
    )
    for item in items:
        if item.get_closest_marker("geometry"):
            item.add_marker(skip)
