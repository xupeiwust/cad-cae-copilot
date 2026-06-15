"""Real static solve for a design-study candidate's geometry.

The core ``design_study_cae_evaluation`` defines an injectable ``solver_fn`` seam
(it cannot import the backend's compile/mesh/solver pipeline). This module is that
runner: given a package and a candidate id, it compiles the candidate's Shape IR
into a throwaway ``.aieng``, overlays the baseline CAE setup, solves it statically
(Gmsh + CalculiX via :func:`simulation_runner.solve_package_static`), and returns
the resulting ``computed_metrics`` doc.

Safety: the baseline package is NEVER mutated — all work happens on a temp copy.
Honest degradation: if the candidate geometry is missing, build123d/Gmsh/ccx are
unavailable, or the candidate's faces no longer match the baseline CAE mapping
(stale topology), it returns ``solver_executed=False`` with a reason — never a
fabricated result.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any


def _read_member(pkg: Path, name: str) -> bytes | None:
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            if name in zf.namelist():
                return zf.read(name)
    except Exception:
        return None
    return None


def _overlay_member(pkg: Path, name: str, data: bytes) -> None:
    tmp = pkg.with_suffix(".overlay.tmp.aieng")
    try:
        with zipfile.ZipFile(pkg, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename != name:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(name, data)
        tmp.replace(pkg)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def solve_candidate_geometry(
    package_path: str | Path,
    candidate_id: str,
    *,
    timeout: int = 180,
    mesh_size_mm: float | None = None,
) -> dict[str, Any]:
    """Compile + statically solve a design-study candidate. Baseline untouched.

    Returns ``{solver_executed, computed_metrics, warnings, [error], status}`` —
    the contract the core ``solver_fn`` seam expects.
    """
    package_path = Path(package_path)
    ws = f"candidates/{candidate_id}/"
    warnings: list[str] = []

    cand_shape_ir = _read_member(package_path, f"{ws}geometry/shape_ir.json")
    if cand_shape_ir is None:
        return {"solver_executed": False, "status": "no_candidate_geometry",
                "error": f"candidate Shape IR not found at {ws}geometry/shape_ir.json", "warnings": warnings}

    from . import cad_generation as _cg
    from .simulation_runner import solve_package_static

    tmp_dir = Path(tempfile.mkdtemp(prefix="aieng_candidate_solve_"))
    tmp_pkg = tmp_dir / "candidate.aieng"
    try:
        # Throwaway package = baseline (carries simulation/setup.yaml + cae_mapping.json)
        # with the candidate's Shape IR swapped in.
        shutil.copy2(package_path, tmp_pkg)
        _overlay_member(tmp_pkg, "geometry/shape_ir.json", cand_shape_ir)

        # Recompile the candidate geometry (writes generated.step + topology_map).
        try:
            recompiled = _cg.recompile_shape_ir_package(tmp_pkg, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return {"solver_executed": False, "status": "compile_failed",
                    "error": f"candidate geometry recompile failed: {type(exc).__name__}: {exc}",
                    "warnings": warnings}
        if isinstance(recompiled, dict) and recompiled.get("status") not in (None, "ok", "success"):
            warnings.append(f"recompile status: {recompiled.get('status')}")

        solve = solve_package_static(tmp_pkg, mesh_size_mm=mesh_size_mm, timeout=timeout)
        warnings.extend(solve.get("warnings") or [])
        if solve.get("solver_executed") and isinstance(solve.get("computed_metrics"), dict):
            return {
                "solver_executed": True,
                "status": "success",
                "computed_metrics": solve["computed_metrics"],
                "warnings": warnings,
            }
        return {
            "solver_executed": False,
            "status": solve.get("status", "solve_failed"),
            "error": solve.get("error") or "candidate solve did not produce metrics",
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
