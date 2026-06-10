"""Design study problem contract + candidate patch validation (v0).

Backend contract for agent-guided PARAMETER design studies and SAFE candidate-patch validation.

v0 is CONTRACT + VALIDATION ONLY:
  - validate_design_study_problem    -> diagnostics/design_study_problem_diagnostics.json
  - validate_design_candidate_patch  -> per-candidate validation record
  - process_design_study_package     -> validates the problem + every candidate in a package and
                                        writes diagnostics/design_study_candidate_validation.json

It does NOT execute patches, does NOT recompile geometry, does NOT run CAE, and does NOT run any
optimization/search. Valid candidates are NORMALIZED but never applied; the baseline geometry is
never modified. Assembly recommendation artifacts may be REFERENCED as evidence (evidence_refs)
but are not deeply consumed in v0.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"
DESIGN_STUDY_PROBLEM_DIAGNOSTICS_PATH = "diagnostics/design_study_problem_diagnostics.json"
DESIGN_CANDIDATES_DIR = "patches/design_candidates/"
DESIGN_STUDY_CANDIDATE_VALIDATION_PATH = "diagnostics/design_study_candidate_validation.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"

VARIABLE_TYPES = {"continuous", "integer", "discrete", "categorical", "boolean"}
_BOUNDED_TYPES = {"continuous", "integer"}
_DISCRETE_TYPES = {"discrete", "categorical"}

# Semantic roles that mark a variable as an assembly/interface dimension — protected by default.
PROTECTED_SEMANTIC_ROLES = {
    "mounting_hole", "bolt_hole", "bolt_pattern", "interface_face", "load_interface",
    "mounting_interface", "mounting_face", "flange", "weld_face", "contact_face",
}

DEFAULT_MAX_VARIABLES_PER_CANDIDATE = 6
DEFAULT_REQUIRE_REASONING = True


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _settings(problem: dict[str, Any]) -> dict[str, Any]:
    return problem.get("settings") if isinstance(problem.get("settings"), dict) else {}


# ── problem contract validation ───────────────────────────────────────────────

def validate_design_study_problem(problem: Any) -> dict[str, Any]:
    """Validate a design_study_problem document. Returns diagnostics (never raises).

    Constraints and the objective are RECORDED, not executed.
    """
    errors: list[str] = []
    warnings: list[str] = []
    limitations = [
        "Design study v0: contract + validation only. No optimization/search is run.",
        "Constraints and objective are recorded but NOT executed. No patch is applied; "
        "baseline geometry is never modified.",
    ]
    if not isinstance(problem, dict):
        return {"format": "aieng.design_study_problem_diagnostics", "format_version": FORMAT_VERSION,
                "schema_version": "0.1", "status": "failed",
                "errors": ["design_study_problem is not a JSON object"], "warnings": [],
                "limitations": limitations, "summary": {}}

    variables = [v for v in (problem.get("variables") or []) if isinstance(v, dict)]
    if not variables:
        errors.append("no variables declared")

    assembly_aware = bool(problem.get("assembly_aware"))
    selected_part = problem.get("selected_part_id")

    seen: set[str] = set()
    for idx, var in enumerate(variables):
        vid = var.get("id")
        if not vid:
            errors.append(f"variable[{idx}] has no id")
            continue
        if vid in seen:
            errors.append(f"duplicate variable id: {vid}")
        seen.add(vid)
        if not var.get("path"):
            errors.append(f"variable '{vid}' has no path")
        vtype = var.get("type")
        if vtype not in VARIABLE_TYPES:
            errors.append(f"variable '{vid}' has invalid type '{vtype}'")
            continue
        # bounds / allowed-values consistency
        if vtype in _BOUNDED_TYPES:
            lo, hi = var.get("min_value"), var.get("max_value")
            if lo is None or hi is None:
                warnings.append(f"variable '{vid}' ({vtype}) is missing min_value/max_value")
            elif _is_number(lo) and _is_number(hi) and lo > hi:
                errors.append(f"variable '{vid}' has min_value > max_value")
        elif vtype in _DISCRETE_TYPES:
            if not isinstance(var.get("allowed_values"), list) or not var.get("allowed_values"):
                errors.append(f"variable '{vid}' ({vtype}) has no allowed_values")
        # current value sanity (warn only — informational)
        cv = var.get("current_value")
        if cv is None:
            warnings.append(f"variable '{vid}' has no current_value")
        if "safe_to_modify" not in var:
            warnings.append(f"variable '{vid}' has no safe_to_modify flag (treated as not safe)")
        if assembly_aware and not var.get("part_id"):
            warnings.append(f"variable '{vid}' has no part_id but study is assembly_aware")

    if assembly_aware and selected_part:
        part_ids = {v.get("part_id") for v in variables}
        if selected_part not in part_ids:
            warnings.append(f"selected_part_id '{selected_part}' matches no variable's part_id")

    settings = _settings(problem)
    if "max_variables_per_candidate" in settings:
        mv = settings["max_variables_per_candidate"]
        if not isinstance(mv, int) or mv < 1:
            errors.append("settings.max_variables_per_candidate must be a positive integer")

    status = "failed" if errors else ("warning" if warnings else "passed")
    safe_count = sum(1 for v in variables if v.get("safe_to_modify") is True)
    return {
        "format": "aieng.design_study_problem_diagnostics", "format_version": FORMAT_VERSION,
        "schema_version": "0.1", "status": status,
        "errors": errors, "warnings": warnings, "limitations": limitations,
        "summary": {
            "variable_count": len(variables),
            "safe_to_modify_count": safe_count,
            "protected_count": sum(1 for v in variables if _is_protected(v)),
            "assembly_aware": assembly_aware,
            "selected_part_id": selected_part,
            "max_variables_per_candidate": settings.get("max_variables_per_candidate",
                                                         DEFAULT_MAX_VARIABLES_PER_CANDIDATE),
            "require_reasoning": settings.get("require_reasoning", DEFAULT_REQUIRE_REASONING),
            "constraint_count": len(problem.get("constraints") or []),
            "has_objective": bool(problem.get("objective")),
        },
    }


def _is_protected(var: dict[str, Any]) -> bool:
    return bool(var.get("protected")) or var.get("semantic_role") in PROTECTED_SEMANTIC_ROLES


# ── candidate patch validation ────────────────────────────────────────────────

def _value_matches_type(vtype: str, value: Any) -> bool:
    if vtype == "boolean":
        return isinstance(value, bool)
    if vtype == "continuous":
        return _is_number(value)
    if vtype == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, float):
            return float(value).is_integer()
        return False
    if vtype in _DISCRETE_TYPES:
        return True  # validity is decided by allowed_values, not Python type
    return False


def _normalize_value(vtype: str, value: Any) -> Any:
    if vtype == "integer" and isinstance(value, float):
        return int(round(value))
    return value


def validate_design_candidate_patch(problem: Any, candidate: Any) -> dict[str, Any]:
    """Validate ONE candidate patch against the problem. Valid candidates are normalized but
    NOT applied. Returns a per-candidate validation record (never raises).
    """
    errors: list[str] = []
    warnings: list[str] = []
    problem = problem if isinstance(problem, dict) else {}
    candidate = candidate if isinstance(candidate, dict) else {}

    var_index = {v.get("id"): v for v in (problem.get("variables") or [])
                 if isinstance(v, dict) and v.get("id")}
    settings = _settings(problem)
    max_vars = settings.get("max_variables_per_candidate", DEFAULT_MAX_VARIABLES_PER_CANDIDATE)
    require_reasoning = settings.get("require_reasoning", DEFAULT_REQUIRE_REASONING)
    assembly_aware = bool(problem.get("assembly_aware"))
    scope_part = candidate.get("selected_part_id") or problem.get("selected_part_id")

    cid = candidate.get("candidate_id") or "candidate"
    changes = candidate.get("variable_changes")
    if not isinstance(changes, list):
        changes = []
        errors.append("variable_changes is missing or not a list")

    # reasoning presence
    reasoning = candidate.get("reasoning")
    if not (isinstance(reasoning, str) and reasoning.strip()):
        (errors if require_reasoning else warnings).append("reasoning is missing")

    # candidate-level: too many variables
    if len(changes) > max_vars:
        errors.append(f"too many variables: {len(changes)} > max_variables_per_candidate {max_vars}")

    seen_vars: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for ci, change in enumerate(changes):
        if not isinstance(change, dict):
            errors.append(f"variable_changes[{ci}] is not an object")
            continue
        vid = change.get("variable_id")
        new_value = change.get("new_value")
        if not vid:
            errors.append(f"variable_changes[{ci}] has no variable_id")
            continue
        if vid in seen_vars:
            errors.append(f"variable '{vid}' changed more than once in one candidate")
        seen_vars.add(vid)

        var = var_index.get(vid)
        if var is None:
            errors.append(f"unknown variable '{vid}'")
            continue
        # protected / safety gates (protected is the more specific reason)
        if _is_protected(var):
            errors.append(f"variable '{vid}' is protected (interface/assembly dimension) — rejected")
            continue
        if var.get("safe_to_modify") is not True:
            errors.append(f"variable '{vid}' is not safe_to_modify — rejected")
            continue
        # assembly scope
        if assembly_aware and scope_part and var.get("part_id") not in (None, scope_part):
            errors.append(f"variable '{vid}' belongs to part '{var.get('part_id')}', "
                          f"outside selected_part_id '{scope_part}'")
            continue
        vtype = var.get("type")
        if not _value_matches_type(vtype, new_value):
            errors.append(f"variable '{vid}' new_value {new_value!r} is not a valid {vtype}")
            continue
        # bounds / allowed values
        if vtype in _BOUNDED_TYPES:
            lo, hi = var.get("min_value"), var.get("max_value")
            if (lo is not None and new_value < lo) or (hi is not None and new_value > hi):
                errors.append(f"variable '{vid}' new_value {new_value} out of bounds [{lo}, {hi}]")
                continue
        elif vtype in _DISCRETE_TYPES:
            allowed = var.get("allowed_values") or []
            if new_value not in allowed:
                errors.append(f"variable '{vid}' new_value {new_value!r} not in allowed_values")
                continue

        normalized.append({
            "variable_id": vid, "path": var.get("path"),
            "old_value": var.get("current_value"),
            "new_value": _normalize_value(vtype, new_value),
            "type": vtype, "unit": var.get("unit"),
            "semantic_role": var.get("semantic_role"), "part_id": var.get("part_id"),
        })

    status = "rejected" if errors else ("valid_with_warnings" if warnings else "valid")
    record = {
        "candidate_id": cid,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "change_count": len(changes),
        "applied": False,          # v0 NEVER applies
        "baseline_modified": False,
    }
    if status != "rejected":
        record["normalized_changes"] = normalized
        record["selected_part_id"] = scope_part
    return record


# ── package integration ──────────────────────────────────────────────────────

def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".tmp.aieng")
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


def process_design_study_package(package_path: str | Path) -> dict[str, Any]:
    """Best-effort: if a package carries analysis/design_study_problem.json, validate the problem
    and EVERY candidate under patches/design_candidates/, writing both diagnostics files. A package
    without the problem artifact is left untouched. Never applies a patch; never touches geometry.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"design_study_present": False, "reason": "package not found"}
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if DESIGN_STUDY_PROBLEM_PATH not in names:
                return {"design_study_present": False}
            try:
                problem = json.loads(zf.read(DESIGN_STUDY_PROBLEM_PATH))
            except Exception:
                problem = None
            candidate_docs = []
            for name in sorted(names):
                if name.startswith(DESIGN_CANDIDATES_DIR) and name.endswith(".json"):
                    try:
                        candidate_docs.append((name, json.loads(zf.read(name))))
                    except Exception:
                        candidate_docs.append((name, None))
    except Exception as exc:  # noqa: BLE001
        return {"design_study_present": False, "error": f"{type(exc).__name__}: {exc}"}

    problem_diag = validate_design_study_problem(problem)

    records = []
    for name, cand in candidate_docs:
        if cand is None:
            records.append({"candidate_id": name, "status": "rejected",
                            "errors": ["candidate file is not valid JSON"], "warnings": [],
                            "applied": False, "baseline_modified": False, "source": name})
            continue
        rec = validate_design_candidate_patch(problem, cand)
        rec["source"] = name
        records.append(rec)

    tally: dict[str, int] = {}
    for r in records:
        tally[r["status"]] = tally.get(r["status"], 0) + 1

    # Check whether sampling is available (no candidates yet but variables exist)
    sampling_available = False
    if isinstance(problem, dict) and OPTIMIZATION_VARIABLES_PATH in names:
        safe_vars = [v for v in (problem.get("variables") or [])
                     if isinstance(v, dict) and v.get("safe_to_modify") is True]
        sampling_available = bool(safe_vars) and len(records) == 0

    candidate_diag = {
        "format": "aieng.design_study_candidate_validation", "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "problem_status": problem_diag["status"],
        "candidates": records,
        "summary": {"candidate_count": len(records), **tally},
        "limitations": [
            "Validation only — no candidate is applied, no geometry recompiled, no CAE run.",
            "Baseline geometry is never modified.",
        ],
        "provenance": {"created_by": "aieng.design_study", "applied": False,
                       "baseline_modified": False, "optimization_executed": False},
    }

    _rewrite_package_members(package_path, {
        DESIGN_STUDY_PROBLEM_DIAGNOSTICS_PATH: _dumps(problem_diag),
        DESIGN_STUDY_CANDIDATE_VALIDATION_PATH: _dumps(candidate_diag),
    })
    result: dict[str, Any] = {
        "design_study_present": True,
        "problem_status": problem_diag["status"],
        "candidate_count": len(records),
        "candidate_status_tally": tally,
        "artifacts": [DESIGN_STUDY_PROBLEM_DIAGNOSTICS_PATH, DESIGN_STUDY_CANDIDATE_VALIDATION_PATH],
    }
    if sampling_available:
        result["sampling_available"] = True
        result["sampling_suggestion"] = (
            "No candidates found but safe-to-modify variables exist. "
            "Use `opt.propose_candidates` / `aieng sample-candidates` / "
            "`POST /api/projects/{id}/design-study/sample` to auto-generate candidates."
        )
    return result
