"""Parametric sizing-sweep orchestration — the optimize→verify loop on static FEA.

Sweeps ONE editable dimension across a set of values, **solving each variant with
the real static solver** (Gmsh + CalculiX), then ranks the variants by an
objective (min mass / displacement / stress) subject to a stress/displacement
constraint via the pure :mod:`aieng.converters.sizing_sweep` ranker.

Honesty + safety contract:
- The **baseline package is never mutated** — each variant is built and solved on a
  throwaway copy.
- **Recommend-only**: the winning value is returned for the caller to apply through
  the existing approval-gated ``cad.edit_parameter``; this module applies nothing.
- A variant that fails to build or solve is reported honestly (``solver_executed``
  False) and can never be recommended as verified.

The per-variant build+solve step is injected as ``evaluate_value`` so the
orchestration is unit-testable without Gmsh/CalculiX; the production default wires
the real package-copy edit + :func:`simulation_runner.solve_package_static`.
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from aieng.converters.sizing_sweep import rank_sizing_sweep

SIZING_SWEEP_REPORT_PATH = "analysis/sizing_sweep_report.json"

# A per-variant evaluator: value → {value, metrics, solver_executed, [error]}.
EvaluateValue = Callable[[float], dict[str, Any]]


def _total_solid_volume(topology_map: dict[str, Any]) -> float | None:
    """Sum solid-entity volumes from a topology map (mass ∝ volume for one material)."""
    if not isinstance(topology_map, dict):
        return None
    total = 0.0
    seen = False
    for ent in topology_map.get("entities", []) or []:
        if isinstance(ent, dict) and ent.get("type") == "solid":
            vol = ent.get("volume")
            if isinstance(vol, (int, float)) and not isinstance(vol, bool):
                total += float(vol)
                seen = True
    return total if seen else None


def make_default_evaluate_value(
    settings: Any,
    baseline_pkg: Path,
    *,
    feature_id: str,
    parameter_name: str,
    mesh_size_mm: float | None,
    timeout: int,
    density: float | None,
) -> EvaluateValue:
    """Build the production per-variant evaluator: copy → edit → solve → metrics.

    Each call copies ``baseline_pkg`` to a throwaway, applies the parametric edit
    at package level (reusing the same primitives as ``cad.edit_parameter``),
    solves the new geometry, and returns scalar metrics plus a volume-based ``mass``
    proxy. The baseline is never touched.
    """
    from . import cad_generation as _cg
    from .project_io import _validate_cad_parameter_edit_contract
    from .simulation_runner import solve_package_static
    import re

    def _evaluate(value: float) -> dict[str, Any]:
        tmp_dir = Path(tempfile.mkdtemp(prefix="aieng_sweep_"))
        tmp_pkg = tmp_dir / "variant.aieng"
        try:
            shutil.copy2(baseline_pkg, tmp_pkg)

            # 1. Validate the edit contract (bounds, cad_parameter_name) on the copy.
            try:
                contract = _validate_cad_parameter_edit_contract(
                    tmp_pkg, feature_id, parameter_name, value
                )
            except ValueError as exc:
                return {"value": value, "metrics": {}, "solver_executed": False,
                        "error": f"invalid edit: {exc}"}
            cad_parameter_name = contract["parameter"].get("cad_parameter_name") or parameter_name

            # 2. Text-replace the UPPER_SNAKE_CASE constant (mirrors edit_build123d_parameter).
            with zipfile.ZipFile(tmp_pkg, "r") as zf:
                source_code = zf.read("geometry/source.py").decode("utf-8")
            pattern = rf'^([ \t]*)({re.escape(cad_parameter_name)})([ \t]*=[ \t]*)([0-9]+\.?[0-9]*)(.*)$'
            new_lines, found = [], False
            for line in source_code.splitlines():
                m = re.match(pattern, line)
                if m:
                    new_lines.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{value}{m.group(5)}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                return {"value": value, "metrics": {}, "solver_executed": False,
                        "error": f"constant {cad_parameter_name} not found in source.py"}
            modified_source = "\n".join(new_lines)

            # 3. Re-execute build123d and write the new geometry into the copy.
            try:
                built = _cg._execute_build123d_cached(
                    settings, modified_source, mode="replace",
                    model_kind=contract.get("model_kind", "auto"), timeout=timeout,
                )
            except Exception as exc:  # noqa: BLE001  (DesignRuleViolation, build errors)
                return {"value": value, "metrics": {}, "solver_executed": False,
                        "error": f"build failed: {type(exc).__name__}: {exc}"}
            topo = built["topo"]
            _cg._write_cad_artifacts(
                pkg_path=tmp_pkg,
                step_bytes=built["step_bytes"],
                stl_bytes=built.get("stl_bytes") or b"",
                topology_map=topo,
                feature_graph=built["feature_graph"],
                generated_code=modified_source,
                glb_bytes=built.get("glb_bytes"),
            )

            # 4. Solve the variant geometry.
            solve = solve_package_static(tmp_pkg, mesh_size_mm=mesh_size_mm, timeout=timeout)
            metrics = dict(solve.get("metrics") or {})

            # 5. Mass proxy from solid volume (∝ mass for a single material).
            volume = _total_solid_volume(topo)
            if volume is not None:
                metrics["volume"] = volume
                metrics["mass"] = volume * density if density else volume

            return {
                "value": value,
                "metrics": metrics,
                "solver_executed": bool(solve.get("solver_executed")),
                "error": solve.get("error") if not solve.get("solver_executed") else None,
                "solve_status": solve.get("status"),
            }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return _evaluate


def run_sizing_sweep(
    settings: Any,
    project_id: str,
    *,
    feature_id: str,
    parameter_name: str,
    values: list[float],
    objective: str = "min_mass",
    stress_limit: float | None = None,
    safety_factor: float = 1.0,
    displacement_limit: float | None = None,
    mesh_size_mm: float | None = None,
    timeout: int = 180,
    density: float | None = None,
    evaluate_value: EvaluateValue | None = None,
) -> dict[str, Any]:
    """Sweep one parameter across ``values``, solve each variant, and rank them.

    Resolves the project's package, evaluates each value via ``evaluate_value``
    (production default: copy → edit → solve), and feeds the per-variant results to
    the pure ranker. Returns the ranker report enriched with project/parameter
    context. Recommend-only; the baseline is never modified.
    """
    from .project_io import get_project, resolve_project_path

    clean_values: list[float] = []
    for v in values or []:
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv not in clean_values:
            clean_values.append(fv)
    if not clean_values:
        return {"status": "error", "code": "bad_input",
                "message": "values must be a non-empty list of numbers"}
    if len(clean_values) > 25:
        return {"status": "error", "code": "too_many_values",
                "message": "sweep is capped at 25 values per run (MVP scope)"}

    try:
        project = get_project(settings, project_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "project_not_found", "message": str(exc)}
    pkg = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg is None or not Path(pkg).exists():
        return {"status": "error", "code": "no_package", "message": ".aieng package not found"}

    if evaluate_value is None:
        evaluate_value = make_default_evaluate_value(
            settings, Path(pkg), feature_id=feature_id, parameter_name=parameter_name,
            mesh_size_mm=mesh_size_mm, timeout=timeout, density=density,
        )

    variants = [evaluate_value(v) for v in clean_values]

    report = rank_sizing_sweep(
        variants,
        objective=objective,
        stress_limit=stress_limit,
        safety_factor=safety_factor,
        displacement_limit=displacement_limit,
        parameter_name=parameter_name,
    )
    report.update({
        "status": "ok",
        "tool": "opt.sizing_sweep",
        "project_id": project_id,
        "feature_id": feature_id,
        "swept_values": clean_values,
        "next_step": (
            "Apply the recommended value with cad.edit_parameter (approval-gated). "
            "This sweep modified nothing."
            if report.get("recommended") is not None
            else "No value recommended — see recommendation_reason."
        ),
    })

    try:
        from .project_io import write_json_artifact_to_package
        write_json_artifact_to_package(pkg, SIZING_SWEEP_REPORT_PATH, report)
        report["artifact_path"] = SIZING_SWEEP_REPORT_PATH
    except Exception as exc:  # noqa: BLE001
        report["artifact_write_error"] = str(exc)

    return report
