"""NAFEMS-style V&V verification regression runner.

This module drives three standards-backed linear-static benchmark cases through
AIENG's existing CAE pipeline:

1. Generate a runnable CalculiX ``.inp`` via :mod:`aieng.simulation.deck_generator`.
2. Execute CalculiX (when ``AIENG_CCX_CMD`` or a ``ccx`` binary is available).
3. Extract computed metrics from the resulting ``.frd`` file via
   :mod:`aieng.simulation.frd_result_extractor`.
4. Compare metrics to documented analytical reference values with tolerance
   bands and produce a machine-readable verification report.

Honesty boundary
----------------

* The report records "verified against reference within tolerance", never
  "certified".
* Linear-static verification only; coarse-mesh results are compared against
  analytical beam/rod theory, not official NAFEMS benchmarks or ASME V&V 10
  certification.
"""
from __future__ import annotations

import json
import math
import os
import shlex
import shutil
import subprocess
import tempfile
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from aieng import FORMAT_VERSION
from aieng.cae_verification import VERIFICATION_SCHEMA, _claim_policy
from aieng.simulation.deck_generator import generate_solver_input_package
from aieng.simulation.frd_result_extractor import extract_computed_metrics


_NAFEMS_VV_REPORT_SCHEMA: dict[str, Any] | None = None


NAFEMS_VV_REPORT_PATH = "verification/nafems_vv_report.json"

# Expected reference values and tolerance bands for each case.
# See aieng/docs/nafems_vv_cases.md for derivation and rationale.
REFERENCE_CASES: dict[str, dict[str, Any]] = {
    "tension_rod": {
        "description": "Axial tension of a square steel rod",
        "metrics": {
            "max_displacement": {
                "value": 1000.0 * 100.0 / (210000.0 * 10.0 * 10.0),
                "unit": "mm",
                "tolerance_percent": 10.0,
            },
            "max_von_mises_stress": {
                "value": 1000.0 / (10.0 * 10.0),
                "unit": "MPa",
                "tolerance_percent": 10.0,
            },
        },
    },
    "cantilever_end_load": {
        "description": "End-loaded cantilever beam",
        "metrics": {
            "max_displacement": {
                "value": 0.023809523809523808,  # 100*100^3 / (3*210000*6666.667)
                "unit": "mm",
                "tolerance_percent": 10.0,
            },
            "max_von_mises_stress": {
                "value": 15.0,
                "unit": "MPa",
                "tolerance_percent": 10.0,
            },
        },
    },
    "cantilever_udl": {
        "description": "Uniformly distributed downward load on cantilever",
        "metrics": {
            "max_displacement": {
                "value": 0.008928571428571428,  # w*L^4 / (8*E*I), w=1 N/mm
                "unit": "mm",
                "tolerance_percent": 10.0,
            },
            "max_von_mises_stress": {
                # Standard beam theory: M_max = w*L^2/2, c = h/2 -> sigma = w*L^2*h/(4*I).
                # The starter-suite proposal stated 15 MPa (w*L^2*h/(2*I)); that is a
                # factor-of-two simplification. We anchor the regression to the
                # analytical bending stress 7.5 MPa so the comparison is physically
                # consistent with the applied total force F = 100 N.
                "value": 7.5,
                "unit": "MPa",
                "tolerance_percent": 10.0,
            },
        },
    },
}


def _load_report_schema() -> dict[str, Any]:
    """Load the canonical JSON schema for ``verification/nafems_vv_report.json``."""
    global _NAFEMS_VV_REPORT_SCHEMA
    if _NAFEMS_VV_REPORT_SCHEMA is None:
        _NAFEMS_VV_REPORT_SCHEMA = json.loads(
            files("aieng.schemas").joinpath("nafems_vv_report.schema.json").read_text(encoding="utf-8")
        )
    return _NAFEMS_VV_REPORT_SCHEMA


def _validate_report(report: dict[str, Any]) -> None:
    """Validate a NAFEMS V&V report dict against its schema.

    Raises:
        ValidationError: when the report does not match the schema.
    """
    schema = _load_report_schema()
    Draft202012Validator(schema).validate(report)


def _reference_value(case_id: str, metric: str) -> float:
    """Return the reference value for a metric, raising on unknown input."""
    case = REFERENCE_CASES[case_id]
    return float(case["metrics"][metric]["value"])


def _split_ccx_cmd(command: str, *, platform: str | None = None) -> list[str]:
    """Split an operator-provided ccx command into subprocess argv."""
    platform = platform or os.name
    parts = shlex.split(command, posix=platform != "nt")
    if platform == "nt":
        parts = [
            part[1:-1]
            if len(part) >= 2 and part[0] == part[-1] and part[0] in {"'", '"'}
            else part
            for part in parts
        ]
    return parts


def _find_ccx() -> list[str] | None:
    """Resolve the CalculiX (ccx) command, respecting ``AIENG_CCX_CMD``.

    Returns a list of command parts (e.g. ``["/usr/bin/ccx"]`` or
    ``["conda", "run", "-n", "calculix-env", "ccx"]``) when ccx is available,
    or ``None`` when it cannot be found.
    """
    ccx_env = os.environ.get("AIENG_CCX_CMD")
    if ccx_env:
        try:
            parts = _split_ccx_cmd(ccx_env)
        except ValueError:
            return None
        if parts and shutil.which(parts[0]):
            return parts
        return None
    for candidate in ("ccx", "ccx_linux", "ccx2.21", "ccx_static"):
        path = shutil.which(candidate)
        if path:
            return [path]
    return None


def _extract_solver_input_from_package(package_path: Path, run_id: str) -> str:
    """Return the generated solver input deck text from a package."""
    in_zip_path = f"simulation/runs/{run_id}/solver_input.inp"
    with zipfile.ZipFile(package_path, "r") as zf:
        if in_zip_path not in zf.namelist():
            raise FileNotFoundError(
                f"solver input not found in package: {in_zip_path}"
            )
        return zf.read(in_zip_path).decode("utf-8", errors="replace")


def _run_ccx(ccx_cmd: list[str], working_dir: Path, jobname: str) -> dict[str, Any]:
    """Execute CalculiX in ``working_dir`` for ``jobname`` (without extension)."""
    cmd = list(ccx_cmd) + [jobname]
    try:
        proc = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -1,
            "timed_out": True,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    except FileNotFoundError as exc:
        return {
            "returncode": -1,
            "executable_missing": True,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "returncode": proc.returncode,
        "timed_out": False,
        "executable_missing": False,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_case(
    package_path: str | Path,
    *,
    run_id: str = "nafems_run_001",
) -> dict[str, Any]:
    """Drive a single NAFEMS case through the CAE pipeline.

    Args:
        package_path: Path to the ``.aieng`` package for the case.
        run_id: Solver run identifier used for the generated deck.

    Returns:
        Dict with ``status``, ``computed_metrics``, ``solver_log_tail``,
        ``missing_tools``, and other diagnostics. ``status`` is ``"ok"`` on
        successful extraction of metrics, ``"skipped"`` when ccx is unavailable,
        or ``"error"`` when the solver or extraction fails.
    """
    package_path = Path(package_path)
    ccx_cmd = _find_ccx()
    if ccx_cmd is None:
        return {
            "status": "skipped",
            "missing_tools": ["ccx"],
            "message": (
                "CalculiX not available. Set AIENG_CCX_CMD or add ccx to PATH."
            ),
            "computed_metrics": None,
            "solver_log_tail": None,
        }

    # 1. Generate solver input deck inside the package.
    try:
        gen_result = generate_solver_input_package(
            package_path, run_id=run_id, overwrite=True
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Deck generation failed: {type(exc).__name__}: {exc}",
            "computed_metrics": None,
            "solver_log_tail": None,
        }
    if not gen_result.get("ok"):
        return {
            "status": "error",
            "message": f"Deck generation failed: {gen_result}",
            "computed_metrics": None,
            "solver_log_tail": None,
        }

    # 2. Extract and run in a temp directory.
    try:
        deck_text = _extract_solver_input_from_package(package_path, run_id)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to extract solver input: {type(exc).__name__}: {exc}",
            "computed_metrics": None,
            "solver_log_tail": None,
        }

    with tempfile.TemporaryDirectory(prefix="nafems_vv_") as tmp:
        work = Path(tmp)
        jobname = "solver_input"
        inp_path = work / f"{jobname}.inp"
        try:
            inp_path.write_text(deck_text, encoding="utf-8")
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to write solver deck: {type(exc).__name__}: {exc}",
                "computed_metrics": None,
                "solver_log_tail": None,
            }

        run_info = _run_ccx(ccx_cmd, work, jobname)
        log_tail = (run_info.get("stdout") or "")[-2000:]

        if run_info.get("returncode", -1) != 0:
            return {
                "status": "error",
                "message": "CalculiX solver returned non-zero exit code",
                "returncode": run_info.get("returncode"),
                "solver_log_tail": log_tail,
                "computed_metrics": None,
            }

        frd_path = work / f"{jobname}.frd"
        if not frd_path.exists():
            return {
                "status": "error",
                "message": f"Solver did not produce expected FRD file: {frd_path.name}",
                "solver_log_tail": log_tail,
                "computed_metrics": None,
            }

        metrics = extract_computed_metrics(
            frd_path, load_case_id=run_id, software="CalculiX"
        )

    return {
        "status": "ok",
        "run_id": run_id,
        "computed_metrics": metrics,
        "solver_log_tail": log_tail,
    }


def _metric_value(metrics: dict[str, Any], metric_name: str) -> float | None:
    """Pull a scalar metric value out of the computed_metrics dict."""
    load_cases = metrics.get("load_cases") or []
    if not load_cases:
        return None
    first_case = load_cases[0]
    if not isinstance(first_case, dict):
        return None
    m = first_case.get("metrics", {}).get(metric_name)
    if not isinstance(m, dict):
        return None
    value = m.get("value")
    return float(value) if isinstance(value, (int, float)) else None


def verify_case(
    case_id: str,
    computed_metrics: dict[str, Any],
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare computed metrics to reference tolerances for one case.

    Args:
        case_id: One of the keys in :data:`REFERENCE_CASES`.
        computed_metrics: Dict in ``results/computed_metrics.json`` shape.
        reference: Optional override reference dict; defaults to the built-in
            analytical reference for ``case_id``.

    Returns:
        Per-case verification dict with ``case_id``, ``reference``, ``computed``,
        ``deviation_percent``, ``tolerance_percent``, and ``verdict`` (``"pass"``,
        ``"fail"``, or ``"skipped"``).
    """
    if reference is None:
        if case_id not in REFERENCE_CASES:
            raise KeyError(f"unknown NAFEMS case_id: {case_id}")
        reference = REFERENCE_CASES[case_id]

    ref_metrics = reference.get("metrics", {}) if isinstance(reference, dict) else {}
    metric_results: list[dict[str, Any]] = []
    overall_verdict = "pass"

    for metric_name, ref_entry in ref_metrics.items():
        ref_value = float(ref_entry.get("value", 0.0))
        tolerance_percent = float(ref_entry.get("tolerance_percent", 10.0))
        computed_value = _metric_value(computed_metrics, metric_name)

        if computed_value is None:
            metric_results.append(
                {
                    "metric": metric_name,
                    "reference": ref_value,
                    "computed": None,
                    "deviation_percent": None,
                    "tolerance_percent": tolerance_percent,
                    "verdict": "skipped",
                    "message": "Metric not present in computed results",
                }
            )
            overall_verdict = "fail"
            continue

        if ref_value == 0.0:
            deviation_percent = 0.0 if math.isclose(computed_value, 0.0, abs_tol=1e-12) else math.inf
        else:
            deviation_percent = 100.0 * (computed_value - ref_value) / ref_value

        within = abs(deviation_percent) <= tolerance_percent
        verdict = "pass" if within else "fail"
        if not within:
            overall_verdict = "fail"

        metric_results.append(
            {
                "metric": metric_name,
                "reference": ref_value,
                "computed": computed_value,
                "deviation_percent": round(deviation_percent, 4),
                "tolerance_percent": tolerance_percent,
                "verdict": verdict,
            }
        )

    return {
        "case_id": case_id,
        "verdict": overall_verdict,
        "metrics": metric_results,
    }


def run_nafems_suite(
    package_path_or_dir: str | Path,
    *,
    run_id: str = "nafems_run_001",
) -> dict[str, Any]:
    """Build (if necessary), run, and verify all three NAFEMS-style cases.

    Args:
        package_path_or_dir: Either a directory containing ``*.aieng`` packages
            named ``tension_rod.aieng``, ``cantilever_end_load.aieng``, and
            ``cantilever_udl.aieng``, or a single package path (in which case only
            that case is run).
        run_id: Solver run identifier.

    Returns:
        Aggregated verification report dict ready to be written by
        :func:`write_nafems_vv_report`.
    """
    path = Path(package_path_or_dir)
    if path.is_dir():
        cases_to_run: dict[str, Path] = {
            case_id: path / f"{case_id}.aieng"
            for case_id in REFERENCE_CASES
        }
    else:
        case_id = path.stem
        if case_id not in REFERENCE_CASES:
            raise ValueError(f"unknown case_id from path: {case_id}")
        cases_to_run = {case_id: path}

    case_results: list[dict[str, Any]] = []
    any_fail = False
    any_skip = False

    for case_id, pkg_path in cases_to_run.items():
        run_result = run_case(pkg_path, run_id=run_id)
        if run_result["status"] == "skipped":
            any_skip = True
            case_results.append(
                {
                    "case_id": case_id,
                    "verdict": "skipped",
                    "status": "skipped",
                    "missing_tools": run_result.get("missing_tools"),
                    "message": run_result.get("message"),
                    "metrics": [],
                }
            )
            continue

        if run_result["status"] != "ok" or run_result.get("computed_metrics") is None:
            any_fail = True
            case_results.append(
                {
                    "case_id": case_id,
                    "verdict": "fail",
                    "status": run_result["status"],
                    "message": run_result.get("message"),
                    "solver_log_tail": run_result.get("solver_log_tail"),
                    "metrics": [],
                }
            )
            continue

        verification = verify_case(case_id, run_result["computed_metrics"])
        if verification["verdict"] != "pass":
            any_fail = True
        case_results.append(verification)

    if any_fail:
        status = "failed"
    elif any_skip:
        status = "skipped"
    else:
        status = "passed"

    return {
        "format": "aieng.nafems_vv_report",
        "format_version": FORMAT_VERSION,
        "schema_version": VERIFICATION_SCHEMA,
        "status": status,
        "cases": case_results,
        "claim_policy": _claim_policy(),
        "limitations": [
            "Linear-static verification only; no modal, buckling, nonlinear, or dynamic checks.",
            "Reference values are analytical beam/rod theory for the documented geometry and loads.",
            "Meshes are intentionally coarse for fast CI runtime; tolerance bands reflect mesh discretisation.",
            "Verified against reference values within tolerance; this is not a certification.",
            "Not an official NAFEMS benchmark certificate and not ASME V&V 10 certified.",
            "Results depend on CalculiX version, element formulation, and numerical tolerances.",
        ],
    }


def write_nafems_vv_report(
    package_path: Path | str,
    report: dict[str, Any],
) -> Path:
    """Atomically write the verification report into ``.aieng`` package.

    The report is written to ``verification/nafems_vv_report.json`` inside the
    package. The manifest is left unchanged except for the standard atomic ZIP
    rewrite.

    Returns:
        Path to the updated package.
    """
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    _validate_report(report)

    report_path = NAFEMS_VV_REPORT_PATH
    report_bytes = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()

    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise ValueError("package is missing manifest.json")
        manifest = json.loads(zf.read("manifest.json"))
        members: list[tuple[zipfile.ZipInfo, bytes]] = []
        seen: set[str] = set()
        for info in zf.infolist():
            if info.filename in seen or info.filename in {report_path, "manifest.json"}:
                continue
            seen.add(info.filename)
            data = b"" if info.is_dir() else zf.read(info.filename)
            members.append((info, data))

    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    verification_dir = str(Path(report_path).parent) + "/"

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".aieng", dir=path.parent
    ) as fh:
        tmp_path = Path(fh.name)

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            if verification_dir not in names:
                zf.writestr(verification_dir, b"")
            zf.writestr("manifest.json", manifest_bytes)
            zf.writestr(report_path, report_bytes)
        shutil.move(str(tmp_path), path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return path
