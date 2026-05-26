"""Runtime capability detection for FreeCAD, FEM, meshers, and solvers.

Rules:
- Detection is safe: never crash if FreeCAD is missing.
- Detection is informative: report what is available and what is missing.
- Detection does not modify files or run solvers.
"""

from __future__ import annotations

import shutil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FreecadRuntimeCapabilities(BaseModel):
    """Structured report of FreeCAD and CAE runtime capabilities."""

    model_config = ConfigDict(extra="forbid")

    freecad_available: bool = False
    freecad_version: str | None = None
    fem_available: bool = False
    calculix_available: bool = False
    gmsh_available: bool = False
    netgen_available: bool = False
    headless_supported: bool = False
    warnings: list[str] = []
    errors: list[str] = []


def detect_freecad_runtime() -> FreecadRuntimeCapabilities:
    """Detect FreeCAD, FEM workbench, meshers, and solver availability.

    Returns a structured capability report. Never raises.
    """
    caps = FreecadRuntimeCapabilities()
    warnings: list[str] = []
    errors: list[str] = []

    # 1. FreeCAD import
    try:
        import FreeCAD

        caps.freecad_available = True
        try:
            version_info = FreeCAD.Version()
            caps.freecad_version = ".".join(str(v) for v in version_info[:3])
        except Exception as exc:
            warnings.append(f"FreeCAD imported but version could not be read: {exc}")
    except ImportError:
        warnings.append("FreeCAD is not importable.")
        return caps
    except Exception as exc:
        errors.append(f"Unexpected error importing FreeCAD: {exc}")
        return caps

    # 2. FEM workbench
    try:
        import Fem  # noqa: F401

        caps.fem_available = True
    except ImportError:
        warnings.append("FreeCAD FEM workbench (Fem) is not available.")
    except Exception as exc:
        warnings.append(f"FreeCAD FEM workbench import failed: {exc}")

    # 3. Gmsh meshing
    try:
        import femmesh.gmshtools  # noqa: F401

        caps.gmsh_available = True
    except ImportError:
        warnings.append("FreeCAD Gmsh meshing tools (femmesh.gmshtools) are not available.")
    except Exception as exc:
        warnings.append(f"Gmsh tools import failed: {exc}")

    # 4. Netgen meshing
    try:
        import femmesh.netgentools  # noqa: F401

        caps.netgen_available = True
    except ImportError:
        warnings.append("FreeCAD Netgen meshing tools (femmesh.netgentools) are not available.")
    except Exception as exc:
        warnings.append(f"Netgen tools import failed: {exc}")

    # 5. CalculiX binary
    ccx_path = shutil.which("ccx")
    if ccx_path:
        caps.calculix_available = True
    else:
        import os

        ccx_env = os.environ.get("FREECAD_MCP_CCX_BINARY") or os.environ.get("MECH_AGENT_CCX_BINARY")
        if ccx_env:
            caps.calculix_available = True
        else:
            warnings.append("CalculiX binary (ccx) not found in PATH or environment.")

    # 6. Headless support
    try:
        import FreeCAD

        # FreeCAD.GuiUp is 0 in headless mode, 1 in GUI mode
        # If we can import without GUI, headless is supported
        caps.headless_supported = not bool(getattr(FreeCAD, "GuiUp", True))
    except Exception as exc:
        warnings.append(f"Could not determine headless support: {exc}")

    caps.warnings = warnings
    caps.errors = errors
    return caps
