"""Multi-parameter DOE sizing study runner.

Builds on opt.sizing_sweep: instead of varying one dimension, this explores a
small design space of 2+ editable parameters jointly. Each design point is
built and solved with the real static solver (via solve_package_static); the
existing ranker scores feasibility and recommends the best point. Baseline is
never mutated.
"""
from __future__ import annotations

import itertools
import json
import math
import random
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from aieng.converters.sizing_sweep import rank_sizing_sweep

DesignPoint = dict[str, float]
EvaluateDesignPoint = Callable[[DesignPoint], dict[str, Any]]


def _safe_param_key(feature_id: str, parameter_name: str) -> str:
    return f"{feature_id}#{parameter_name}"


def _parse_param_key(key: str) -> tuple[str, str]:
    feature_id, parameter_name = key.split("#", 1)
    return feature_id, parameter_name


def _expand_parameter_values(
    spec: dict[str, Any],
    package_path: Path,
) -> list[float]:
    """Expand one parameter spec to a list of values (values or range)."""
    from .project_io import _validate_cad_parameter_edit_contract

    feature_id = str(spec.get("featureId") or spec.get("feature_id") or "")
    parameter_name = str(spec.get("parameterName") or spec.get("parameter_name") or "")
    values = spec.get("values")
    range_spec = spec.get("range")
    if values is None and range_spec is None:
        raise ValueError(f"parameter {feature_id}/{parameter_name}: provide values or range")

    contract = _validate_cad_parameter_edit_contract(
        package_path, feature_id, parameter_name, None
    )
    param = contract.get("parameter", {})
    param_min = param.get("min_value")
    param_max = param.get("max_value")

    if values is not None:
        if not isinstance(values, list):
            raise ValueError(f"parameter {feature_id}/{parameter_name}: values must be a list")
        clean: list[float] = []
        seen: set[float] = set()
        for v in values:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv not in seen:
                clean.append(fv)
                seen.add(fv)
        if len(clean) > 25:
            raise ValueError(f"parameter {feature_id}/{parameter_name}: capped at 25 values")
        if not clean:
            raise ValueError(f"parameter {feature_id}/{parameter_name}: values list is empty")
        return clean

    # range expansion
    if not isinstance(range_spec, dict):
        raise ValueError(f"parameter {feature_id}/{parameter_name}: range must be an object")
    rmin = range_spec.get("min")
    rmax = range_spec.get("max")
    if rmin is None or rmax is None:
        raise ValueError(f"parameter {feature_id}/{parameter_name}: range needs min and max")
    try:
        rmin_f = float(rmin)
        rmax_f = float(rmax)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"parameter {feature_id}/{parameter_name}: min/max must be numbers") from exc
    if rmax_f < rmin_f:
        raise ValueError(f"parameter {feature_id}/{parameter_name}: max must be >= min")

    if param_min is not None:
        rmin_f = max(rmin_f, float(param_min))
    if param_max is not None:
        rmax_f = min(rmax_f, float(param_max))

    if "steps" in range_spec:
        steps = int(range_spec["steps"])
        if steps < 2 or steps > 25:
            raise ValueError(f"parameter {feature_id}/{parameter_name}: steps must be 2..25")
        step = (rmax_f - rmin_f) / (steps - 1)
        raw = [rmin_f + i * step for i in range(steps)]
    elif "step" in range_spec:
        step = float(range_spec["step"])
        if step <= 0:
            raise ValueError(f"parameter {feature_id}/{parameter_name}: step must be > 0")
        n_steps = int((rmax_f - rmin_f) / step) + 1
        if n_steps > 25:
            raise ValueError(f"parameter {feature_id}/{parameter_name}: range expands to >25 values")
        raw = [rmin_f + i * step for i in range(n_steps)]
    else:
        raise ValueError(f"parameter {feature_id}/{parameter_name}: range needs steps or step")

    clean = []
    seen = set()
    for v in raw:
        if v not in seen:
            clean.append(v)
            seen.add(v)
    if not clean:
        raise ValueError(f"parameter {feature_id}/{parameter_name}: range is empty after clamping")
    return clean


def _generate_design_points(
    parameter_values: dict[str, list[float]],
    method: str,
    budget: int,
    seed: int | None = None,
) -> list[DesignPoint]:
    """Generate design points from per-parameter value lists."""
    keys = list(parameter_values.keys())
    value_lists = [parameter_values[k] for k in keys]

    if method == "full_factorial":
        total = math.prod(len(v) for v in value_lists)
        if total > budget:
            raise ValueError(
                f"full_factorial would produce {total} points; budget is {budget}. "
                "Increase budget or use lhs."
            )
        return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]

    if method == "lhs":
        if budget < 2:
            raise ValueError("lhs budget must be >= 2")
        # Simple Latin-hypercube style sampling: for each dimension shuffle the
        # (possibly repeated) value list and take the i-th entry for each sample.
        rng = random.Random(seed)
        n_dim = len(keys)
        per_dim: list[list[float]] = []
        for values in value_lists:
            # Replicate values to reach budget, then shuffle.
            extended = (values * ((budget // len(values)) + 1))[:budget]
            rng.shuffle(extended)
            per_dim.append(extended)
        return [{keys[d]: per_dim[d][i] for d in range(n_dim)} for i in range(budget)]

    raise ValueError(f"unknown DOE method: {method}")


def _summarize_point(point: DesignPoint) -> str:
    return ", ".join(f"{k.split('#', 1)[1]}={v:g}" for k, v in point.items())


def _apply_source_replacements(source_code: str, replacements: list[tuple[str, float]]) -> str:
    """Apply multiple UPPER_SNAKE_CASE constant replacements to source.py."""
    lines = source_code.splitlines()
    new_lines: list[str] = []
    replaced: set[str] = set()
    for line in lines:
        out_line = line
        for cad_parameter_name, value in replacements:
            if cad_parameter_name in replaced:
                continue
            pattern = rf"^([ \t]*)({re.escape(cad_parameter_name)})([ \t]*=[ \t]*)([0-9]+\.?[0-9]*)(.*)$"
            m = re.match(pattern, out_line)
            if m:
                out_line = f"{m.group(1)}{m.group(2)}{m.group(3)}{value}{m.group(5)}"
                replaced.add(cad_parameter_name)
        new_lines.append(out_line)
    return "\n".join(new_lines)


def make_default_evaluate_design_point(
    settings: Any,
    baseline_pkg: Path,
    parameter_specs: list[dict[str, Any]],
    *,
    mesh_size_mm: float | None,
    timeout: int,
    density: float | None,
) -> EvaluateDesignPoint:
    """Return an evaluator that builds and solves one multi-parameter design point."""
    from . import cad_generation as _cg
    from .project_io import _validate_cad_parameter_edit_contract
    from .simulation_runner import solve_package_static

    # Pre-compute cad_parameter_name lookups by validating against the baseline.
    contract_map: dict[str, dict[str, Any]] = {}
    for spec in parameter_specs:
        key = _safe_param_key(
            str(spec.get("featureId") or spec.get("feature_id") or ""),
            str(spec.get("parameterName") or spec.get("parameter_name") or ""),
        )
        feature_id, parameter_name = _parse_param_key(key)
        contract = _validate_cad_parameter_edit_contract(
            baseline_pkg, feature_id, parameter_name, None
        )
        contract_map[key] = contract

    def _evaluate(point: DesignPoint) -> dict[str, Any]:
        tmp_dir = Path(tempfile.mkdtemp(prefix="aieng_doe_"))
        tmp_pkg = tmp_dir / "variant.aieng"
        try:
            import shutil
            shutil.copy2(baseline_pkg, tmp_pkg)

            replacements: list[tuple[str, float]] = []
            for key, value in point.items():
                feature_id, parameter_name = _parse_param_key(key)
                contract = contract_map[key]
                try:
                    _validate_cad_parameter_edit_contract(
                        tmp_pkg, feature_id, parameter_name, value
                    )
                except ValueError as exc:
                    return {
                        "value": _summarize_point(point),
                        "parameters": dict(point),
                        "metrics": {},
                        "solver_executed": False,
                        "error": f"invalid edit: {exc}",
                    }
                cad_parameter_name = contract["parameter"].get("cad_parameter_name") or parameter_name
                replacements.append((cad_parameter_name, value))

            with zipfile.ZipFile(tmp_pkg, "r") as zf:
                source_code = zf.read("geometry/source.py").decode("utf-8")

            modified_source = _apply_source_replacements(source_code, replacements)
            if len(replacements) != len({r[0] for r in replacements}):
                return {
                    "value": _summarize_point(point),
                    "parameters": dict(point),
                    "metrics": {},
                    "solver_executed": False,
                    "error": "duplicate cad parameter names across parameters",
                }

            # Use the first contract's model_kind; mixed kinds are unlikely.
            first_contract = next(iter(contract_map.values()))
            try:
                built = _cg._execute_build123d_cached(
                    settings,
                    modified_source,
                    mode="replace",
                    model_kind=first_contract.get("model_kind", "auto"),
                    timeout=timeout,
                )
            except Exception as exc:  # noqa: BLE001
                return {
                    "value": _summarize_point(point),
                    "parameters": dict(point),
                    "metrics": {},
                    "solver_executed": False,
                    "error": f"build failed: {type(exc).__name__}: {exc}",
                }

            _cg._write_cad_artifacts(
                pkg_path=tmp_pkg,
                step_bytes=built["step_bytes"],
                stl_bytes=built.get("stl_bytes") or b"",
                topology_map=built["topo"],
                feature_graph=built["feature_graph"],
                generated_code=modified_source,
                glb_bytes=built.get("glb_bytes"),
            )

            solve = solve_package_static(
                tmp_pkg,
                mesh_size_mm=mesh_size_mm,
                timeout=timeout,
                rebind_faces=True,
                baseline_package_path=baseline_pkg,
            )

            metrics: dict[str, Any] = dict(solve.get("metrics") or {})
            if density is not None and "volume_mm3" in metrics:
                metrics["mass"] = float(metrics["volume_mm3"]) * density * 1e-9
            elif "mass" not in metrics and "volume_mm3" in metrics:
                metrics["mass"] = float(metrics["volume_mm3"])

            return {
                "value": _summarize_point(point),
                "parameters": dict(point),
                "metrics": metrics,
                "solver_executed": bool(solve.get("solver_executed")),
                "error": solve.get("error"),
            }
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return _evaluate


def run_doe_sizing_study(
    settings: Any,
    project_id: str,
    *,
    parameters: list[dict[str, Any]],
    method: str = "full_factorial",
    budget: int = 64,
    objective: str = "min_mass",
    stress_limit: float | None = None,
    safety_factor: float = 1.0,
    displacement_limit: float | None = None,
    mesh_size_mm: float | None = None,
    timeout: int = 180,
    density: float | None = None,
    seed: int | None = None,
    evaluate_design_point: EvaluateDesignPoint | None = None,
) -> dict[str, Any]:
    """Run a multi-parameter DOE sizing study.

    Each design point is built and solved with the real static solver. The
    baseline package is never mutated. Returns a ranker report enriched with the
    per-point solve-status table and the parameter names.
    """
    from .project_io import get_project, resolve_project_path

    if not parameters:
        return {"status": "error", "code": "bad_input", "message": "parameters list is required"}
    if len(parameters) < 2:
        return {
            "status": "error",
            "code": "bad_input",
            "message": "DOE study requires at least 2 parameters; use opt.sizing_sweep for one.",
        }

    try:
        project = get_project(settings, project_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "project_not_found", "message": str(exc)}
    pkg = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg is None or not Path(pkg).exists():
        return {"status": "error", "code": "no_package", "message": ".aieng package not found"}

    try:
        parameter_values: dict[str, list[float]] = {}
        for spec in parameters:
            key = _safe_param_key(
                str(spec.get("featureId") or spec.get("feature_id") or ""),
                str(spec.get("parameterName") or spec.get("parameter_name") or ""),
            )
            if not key or "#" not in key or key.endswith("#"):
                return {"status": "error", "code": "bad_input", "message": "each parameter needs featureId and parameterName"}
            parameter_values[key] = _expand_parameter_values(spec, Path(pkg))
    except ValueError as exc:
        return {"status": "error", "code": "bad_input", "message": str(exc)}

    try:
        design_points = _generate_design_points(parameter_values, method, budget, seed=seed)
    except ValueError as exc:
        return {"status": "error", "code": "bad_input", "message": str(exc)}

    if evaluate_design_point is None:
        evaluate_design_point = make_default_evaluate_design_point(
            settings,
            Path(pkg),
            parameters,
            mesh_size_mm=mesh_size_mm,
            timeout=timeout,
            density=density,
        )

    variants = [evaluate_design_point(point) for point in design_points]

    report = rank_sizing_sweep(
        variants,
        objective=objective,
        stress_limit=stress_limit,
        safety_factor=safety_factor,
        displacement_limit=displacement_limit,
        parameter_name="design_point",
    )
    report.update({
        "status": "ok",
        "tool": "opt.doe_sizing_study",
        "project_id": project_id,
        "method": method,
        "budget": budget,
        "design_points_count": len(design_points),
        "parameters": [
            {
                "feature_id": spec.get("featureId") or spec.get("feature_id"),
                "parameter_name": spec.get("parameterName") or spec.get("parameter_name"),
                "values": parameter_values[_safe_param_key(
                    str(spec.get("featureId") or spec.get("feature_id") or ""),
                    str(spec.get("parameterName") or spec.get("parameter_name") or ""),
                )],
            }
            for spec in parameters
        ],
        "next_step": (
            "Apply the recommended design point through approval-gated cad.edit_parameter "
            "calls (one per parameter). This study modified nothing."
            if report.get("recommended") is not None
            else "No feasible design point found — relax constraints or expand the design space."
        ),
    })
    # If the ranker recommended a summary value, recover the full parameter dict.
    recommended = report.get("recommended")
    if recommended is not None:
        for v in variants:
            if v.get("value") == recommended.get("value"):
                recommended["parameters"] = v.get("parameters", {})
                break
    return report
