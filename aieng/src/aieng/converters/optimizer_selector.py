"""Deterministic optimizer selection for agent-guided design studies (#101).

Reads the resolved problem shape from ``analysis/optimization_variables.json`` and
``analysis/optimization_study.json``, picks an optimizer, appends a reason-coded
decision to ``analysis/optimization_decision_log.json``, and returns the choice.
No search or optimization is run inside the call.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.optimization_artifacts import (
    OPTIMIZATION_DECISION_LOG_PATH,
    validate_optimization_artifact_set,
)

OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
OPTIMIZATION_STUDY_PATH = "analysis/optimization_study.json"
DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"

# Tunable thresholds for the deterministic policy.
_LOW_DIMENSIONAL_THRESHOLD = 10

# Variable types considered discrete/categorical for optimizer selection.
_DISCRETE_TYPES = {"discrete", "categorical"}

# Valid optimizer names emitted by this selector.
_VALID_OPTIMIZERS = {"trust_region", "slsqp", "bayesian", "genetic"}


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _surrogate_available() -> bool:
    """Best-effort probe for a Bayesian surrogate library (scikit-optimize)."""
    return importlib.util.find_spec("skopt") is not None


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    """Atomically rewrite multiple members in a zip package."""
    tmp = package_path.with_suffix(".optsel.tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:  # noqa: BLE001
            return None
    return None


def _load_decision_log(
    package_path: Path,
    variables_doc: dict[str, Any],
) -> dict[str, Any]:
    """Load existing decision log or create a fresh scaffold."""
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            existing = _read_json(zf, OPTIMIZATION_DECISION_LOG_PATH, names)
    except Exception:  # noqa: BLE001
        existing = None

    if isinstance(existing, dict) and existing.get("format") == "aieng.optimization_decision_log":
        return existing

    study_id = variables_doc.get("study_id")
    problem_id = variables_doc.get("design_study_problem_id")
    doc: dict[str, Any] = {
        "format": "aieng.optimization_decision_log",
        "schema_version": "0.1",
        "study_id": study_id,
        "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
        "design_study_problem_id": problem_id,
        "entries": [],
        "candidate_ids": [],
        "provenance": {
            "created_at": _utcnow(),
            "created_by": "aieng.optimizer_selector",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }
    if problem_id is None:
        doc.pop("design_study_problem_id")
    return doc


def _variable_types(variables: list[dict[str, Any]]) -> set[str]:
    return {str(v.get("type")).lower() for v in variables if isinstance(v, dict)}


def _safe_variables(variables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [v for v in variables if isinstance(v, dict) and v.get("safe_to_modify")]


def _cae_evaluation_requested(study: dict[str, Any] | None) -> bool:
    """Infer whether the study expects expensive CAE evaluations."""
    if not isinstance(study, dict):
        return False
    budget = study.get("budget") or {}
    max_solver_runs = budget.get("max_solver_runs")
    if isinstance(max_solver_runs, int) and max_solver_runs > 0:
        return True
    # Algorithm settings may explicitly request CAE-backed search.
    algorithm = study.get("algorithm") or {}
    settings = algorithm.get("settings") or {}
    if settings.get("cae_eval") or settings.get("expensive_eval"):
        return True
    return False


def _choose_optimizer(
    *,
    variables: list[dict[str, Any]],
    study: dict[str, Any] | None,
    user_selected: str | None,
) -> tuple[str, list[str], str]:
    """Return (optimizer, reason_codes, note)."""
    safe_count = len(_safe_variables(variables))
    types = _variable_types(variables)

    study_algorithm_name = None
    if isinstance(study, dict):
        algorithm = study.get("algorithm") or {}
        study_algorithm_name = str(algorithm.get("name") or "").lower()

    if user_selected:
        selected = user_selected
        reason_codes = ["user_selected"]
        note = f"User-selected optimizer: {selected}."
    elif study_algorithm_name in _VALID_OPTIMIZERS:
        selected = study_algorithm_name
        reason_codes = ["user_selected"]
        note = f"Study-configured optimizer: {selected}."
    elif types & _DISCRETE_TYPES:
        selected = "genetic"
        reason_codes = ["select_genetic", "discrete_variables_present"]
        note = "Discrete/categorical variables present; genetic algorithm selected."
    elif _cae_evaluation_requested(study) and safe_count <= _LOW_DIMENSIONAL_THRESHOLD:
        if _surrogate_available():
            selected = "bayesian"
            reason_codes = ["select_bayesian", "expensive_cae_eval"]
            note = (
                f"Expensive CAE evaluations requested with {safe_count} safe "
                "design variables; Bayesian optimizer selected."
            )
        else:
            selected = "trust_region"
            reason_codes = ["no_surrogate_available", "expensive_cae_eval"]
            note = (
                f"Expensive CAE evaluations requested with {safe_count} safe "
                "design variables, but no surrogate library is available; "
                "falling back to trust_region/LHS."
            )
    elif safe_count <= _LOW_DIMENSIONAL_THRESHOLD and types <= {"continuous", "integer"}:
        selected = "slsqp"
        reason_codes = ["select_slsqp", "continuous_smooth_problem"]
        if safe_count <= 5:
            reason_codes.append("small_number_of_design_variables")
        note = (
            f"Continuous smooth problem with {safe_count} safe design variables; "
            "SLSQP selected."
        )
    else:
        selected = "trust_region"
        reason_codes = ["no_incumbent_fallback"]
        if safe_count > _LOW_DIMENSIONAL_THRESHOLD:
            reason_codes.append("small_number_of_design_variables")
            note = (
                f"Problem has {safe_count} safe design variables; trust_region "
                "local refinement selected as default."
            )
        else:
            note = "No specialized selector matched; trust_region selected as default."

    return selected, list(dict.fromkeys(reason_codes)), note


def select_optimizer(
    package_path: str | Path,
    *,
    user_selected: str | None = None,
) -> dict[str, Any]:
    """Deterministically select an optimizer for the design study.

    Reads ``analysis/optimization_variables.json`` and
    ``analysis/optimization_study.json`` from the package, applies the selection
    policy, appends one entry to ``analysis/optimization_decision_log.json``, and
    returns the result. The package baseline is never modified.

    Selection order:
      1. Explicit ``user_selected`` override (also honored if the study already
         names a non-default optimizer such as slsqp/bayesian/genetic).
      2. Discrete/categorical variables present -> genetic.
      3. CAE-expensive low-dimensional problem -> bayesian if a surrogate
         library is available, otherwise trust_region with
         ``no_surrogate_available`` fallback.
      4. Continuous smooth low-dimensional problem -> slsqp.
      5. Default -> trust_region.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {
            "status": "error",
            "code": "package_not_found",
            "message": "package not found",
            "baseline_modified": False,
        }

    if user_selected is not None:
        selected_input = str(user_selected).lower().strip()
        if selected_input not in _VALID_OPTIMIZERS:
            return {
                "status": "error",
                "code": "invalid_optimizer",
                "message": (
                    f"user_selected optimizer {selected_input!r} is not one of "
                    f"{sorted(_VALID_OPTIMIZERS)}"
                ),
                "baseline_modified": False,
            }
        user_selected = selected_input

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            variables_doc = _read_json(zf, OPTIMIZATION_VARIABLES_PATH, names)
            study = _read_json(zf, OPTIMIZATION_STUDY_PATH, names)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "code": "read_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "baseline_modified": False,
        }

    if not isinstance(variables_doc, dict):
        return {
            "status": "error",
            "code": "missing_variables",
            "message": f"{OPTIMIZATION_VARIABLES_PATH} not found",
            "baseline_modified": False,
        }

    variables = variables_doc.get("variables") or []
    if not isinstance(variables, list):
        return {
            "status": "error",
            "code": "malformed_variables",
            "message": "optimization_variables.variables must be a list",
            "baseline_modified": False,
        }

    selected, reason_codes, note = _choose_optimizer(
        variables=variables,
        study=study,
        user_selected=user_selected,
    )

    decision_log = _load_decision_log(pkg, variables_doc)
    decision_number = len(decision_log.get("entries") or []) + 1
    entry = {
        "decision_id": f"decision_select_optimizer_{decision_number:04d}",
        "timestamp": _utcnow(),
        "decision": f"select_{selected}",
        "reason_codes": reason_codes,
        "requires_human_review": False,
        "candidate_ids": [],
        "note": note,
    }
    decision_log.setdefault("entries", []).append(entry)
    decision_log["candidate_ids"] = list(dict.fromkeys(list(decision_log.get("candidate_ids") or [])))

    documents: dict[str, Any] = {"variables": variables_doc, "decision_log": decision_log}
    if isinstance(study, dict):
        documents["study"] = study
    issues = validate_optimization_artifact_set(documents)
    if issues:
        return {
            "status": "error",
            "code": "validation_failed",
            "message": "; ".join(issues),
            "baseline_modified": False,
        }

    members: dict[str, bytes] = {OPTIMIZATION_DECISION_LOG_PATH: _dumps(decision_log)}
    try:
        _replace_members(pkg, members)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "code": "write_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "baseline_modified": False,
        }

    return {
        "status": "ok",
        "tool": "opt.select_optimizer",
        "optimizer": selected,
        "reason_codes": reason_codes,
        "decision_id": entry["decision_id"],
        "baseline_modified": False,
        "claim_advancement": "none",
        "artifacts": [OPTIMIZATION_DECISION_LOG_PATH],
    }
