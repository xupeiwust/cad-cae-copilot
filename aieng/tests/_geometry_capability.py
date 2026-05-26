"""Backend capability probe for geometry integration tests.

Usage:
    from _geometry_capability import has_working_occ_step_backend

    @pytest.mark.skipif(
        not has_working_occ_step_backend(),
        reason="requires working OCC/OCP STEP backend"
    )
    def test_real_geometry_extraction():
        ...

The probe checks more than import success. It confirms that OCP can parse a
known-good STEP fixture (examples/real_bracket.step) and return at least one
transferable shape.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path


def _ocp_importable() -> bool:
    return importlib.util.find_spec("OCP") is not None


def _ocp_can_parse_real_step() -> bool:
    """Return True iff OCP.STEPControl can read examples/real_bracket.step."""
    real_step = Path(__file__).resolve().parents[1] / "examples" / "real_bracket.step"
    if not real_step.exists():
        return False

    try:
        from OCP.STEPControl import STEPControl_Reader
        from OCP.IFSelect import IFSelect_RetDone
    except ImportError:
        return False

    step_bytes = real_step.read_bytes()
    fd, temp_path = tempfile.mkstemp(suffix=".step")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(step_bytes)

        reader = STEPControl_Reader()
        status = reader.ReadFile(temp_path)
        if status != IFSelect_RetDone:
            return False

        n_roots = reader.NbRootsForTransfer()
        return n_roots > 0
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def has_working_occ_step_backend() -> bool:
    """Return True when OCP is installed AND can parse a known-good STEP file."""
    return _ocp_importable() and _ocp_can_parse_real_step()
