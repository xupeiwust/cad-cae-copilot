"""Design-study candidate proposal hints v0.

Backend-only advisory layer that reads an existing design-study problem plus
available evaluation/ranking/CAE/topopt/assembly evidence and writes structured
hints for what a human/agent might try next.

It is explicitly NOT an optimizer: no candidate patches are created, no geometry
is edited/recompiled, no CAE is run, and no baseline artifacts are overwritten.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.design_study_execution import (
    CANDIDATE_WORKSPACE_ROOT,
    DESIGN_STUDY_ITERATIONS_PATH,
)
from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    DESIGN_STUDY_SCORING_REPORT_PATH,
)

DESIGN_STUDY_CANDIDATE_HINTS_PATH = "analysis/design_study_candidate_hints.json"
DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH = "diagnostics/design_study_candidate_hints_report.json"
DESIGN_STUDY_CANDIDATE_HINTS_FORMAT = "aieng.design_study.candidate_hints.v0"
DESIGN_STUDY_CANDIDATE_HINTS_REPORT_FORMAT = "aieng.design_study_candidate_hints_report"

_OPTIONAL_EVIDENCE_PATHS = [
    DESIGN_STUDY_ITERATIONS_PATH,
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    DESIGN_STUDY_SCORING_REPORT_PATH,
    "analysis/design_study_acceptance.json",
    "analysis/assembly_design_recommendations.json",
    "analysis/assembly_next_actions.json",
    "analysis/assembly_result_map.json",
    "analysis/cae_result_map.json",
    "analysis/topology_optimization.json",
    "diagnostics/assembly_post_optimization_verification.json",
]

_PROTECTED_ROLES = {"bolt_hole", "hole_radius", "mounting_face", "interface", "protected_interface"}
_THICKNESS_ROLES = {"wall_thickness", "rib_thickness", "rib", "rib_height", "boss_diameter"}
_STIFFNESS_ROLES = {"wall_thickness", "rib_thickness", "rib", "rib_height", "boss_diameter"}
_FILLET_ROLES = {"fillet_radius", "fillet"}
_PRESERVE_ROLES = {"preserve_radius", "interface", "protected_interface"}
_MASS_REDUCTION_ROLES = {"wall_thickness", "rib_thickness", "rib", "hole_radius"}


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".dshint.tmp.aieng")
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


def _sanitize_id(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "candidate"))
    return s.strip("._") or "candidate"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("value", "actual", "max", "min", "peak"):
            if key in value:
                n = _num(value.get(key))
                if n is not None:
                    return n
    return None


def _role(variable: dict[str, Any]) -> str:
    raw = str(variable.get("semantic_role") or variable.get("role") or "other").lower()
    mapping = {
        "rib": "rib_thickness",
        "fillet": "fillet_radius",
        "bolt_hole": "hole_radius",
    }
    return mapping.get(raw, raw)


def _variable_name(variable: dict[str, Any]) -> str:
    return str(variable.get("name") or variable.get("label") or variable.get("id") or "variable")


def _near_bound(variable: dict[str, Any]) -> list[str]:
    cur = _num(variable.get("current_value"))
    mn = _num(variable.get("min_value"))
    mx = _num(variable.get("max_value"))
    notes: list[str] = []
    if cur is not None and mn is not None and mx is not None and mx > mn:
        pos = (cur - mn) / (mx - mn)
        if pos <= 0.15:
            notes.append("current value is near the lower bound; only small decreases are safe to consider")
        if pos >= 0.85:
            notes.append("current value is near the upper bound; only small increases are safe to consider")
    allowed = variable.get("allowed_values")
    if isinstance(allowed, list) and cur in allowed:
        idx = allowed.index(cur)
        if idx == 0:
            notes.append("current discrete value is at the lowest allowed option")
        if idx == len(allowed) - 1:
            notes.append("current discrete value is at the highest allowed option")
    return notes


def _in_selected_scope(variable: dict[str, Any], selected_part_id: str | None) -> bool:
    if not selected_part_id:
        return True
    part = variable.get("part_id") or variable.get("selected_part_id")
    if part is not None:
        return str(part) == str(selected_part_id)
    return True


def _safe_to_adjust(variable: dict[str, Any], selected_part_id: str | None) -> bool:
    if variable.get("safe_to_modify") is False:
        return False
    if not _in_selected_scope(variable, selected_part_id):
        return False
    role = _role(variable)
    if role in _PROTECTED_ROLES and variable.get("safe_to_modify") is not True:
        return False
    return True


def _evidence(artifact: str, field: str, *, load_case_id: str | None = None,
              result_type: str | None = None, confidence: str = "medium") -> dict[str, Any]:
    return {
        "artifact": artifact,
        "field": field,
        "load_case_id": load_case_id,
        "result_type": result_type,
        "confidence": confidence,
    }


def _make_hint(
    *,
    hid: str,
    htype: str,
    variable: dict[str, Any] | None = None,
    suggested_direction: str,
    suggested_magnitude: str,
    priority: str,
    confidence: str,
    reason: str,
    source_evidence: list[dict[str, Any]] | None = None,
    safety_notes: list[str] | None = None,
    do_not_modify: bool = False,
) -> dict[str, Any]:
    role = _role(variable or {})
    return {
        "id": hid,
        "type": htype,
        "variable_id": (variable or {}).get("id"),
        "variable_name": _variable_name(variable or {}) if variable else None,
        "semantic_role": role,
        "suggested_direction": suggested_direction,
        "suggested_magnitude": suggested_magnitude,
        "priority": priority,
        "confidence": confidence,
        "reason": reason,
        "source_evidence": source_evidence or [],
        "source_evidence_count": len(source_evidence or []),
        "safety_notes": safety_notes or [],
        "do_not_modify": do_not_modify,
    }


def _constraints_by_type(problem: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in problem.get("constraints") or []:
        if isinstance(c, dict) and c.get("type"):
            out[str(c["type"])] = c
    return out


def _load_candidate_evaluations(zf: zipfile.ZipFile, names: set[str]) -> dict[str, dict[str, Any]]:
    evaluations: dict[str, dict[str, Any]] = {}
    prefix = f"{CANDIDATE_WORKSPACE_ROOT}"
    suffix = "/analysis/evaluation.json"
    for name in names:
        if name.startswith(prefix) and name.endswith(suffix):
            parts = name.split("/")
            if len(parts) >= 4:
                cid = parts[1]
                doc = _read_json(zf, name, names)
                if isinstance(doc, dict):
                    evaluations[cid] = doc
    return evaluations


def _collect_evidence_state(
    problem: dict[str, Any],
    artifacts: dict[str, Any],
    evaluations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    objective = problem.get("objective") if isinstance(problem.get("objective"), dict) else {}
    ranking = artifacts.get(DESIGN_STUDY_CANDIDATE_RANKING_PATH) or {}
    accepted = artifacts.get("analysis/design_study_acceptance.json") or {}
    best: dict[str, Any] = {}
    for cand in ranking.get("candidates") or []:
        if cand.get("candidate_id") == ranking.get("best_candidate_id"):
            best = cand
            break
    all_evals = list(evaluations.values())
    stress_violation = False
    deflection_violation = False
    safety_violation = False
    proxy_low_conf = False
    missing_metrics = False
    volume_improved_stress_bad = False
    evidence_links: list[dict[str, Any]] = []

    for cid, ev in evaluations.items():
        ev_art = f"candidates/{cid}/analysis/evaluation.json"
        conf = str(ev.get("confidence") or "medium")
        proxy_low_conf = proxy_low_conf or conf == "low" or bool((ev.get("honesty") or {}).get("proxy_derived"))
        if ev.get("evaluation_status") in ("partial", "insufficient_data"):
            missing_metrics = True
        for ce in ev.get("constraint_evidence") or []:
            if not isinstance(ce, dict):
                continue
            if ce.get("status") == "violated":
                ctype = ce.get("type")
                evidence_links.append(_evidence(ev_art, f"constraint_evidence.{ce.get('id')}", result_type=ctype, confidence=conf))
                stress_violation = stress_violation or ctype == "max_stress"
                deflection_violation = deflection_violation or ctype == "max_deflection"
                safety_violation = safety_violation or ctype == "min_safety_factor"
        metrics = ev.get("metrics") if isinstance(ev.get("metrics"), dict) else {}
        if _num(metrics.get("volume_mm3")) is not None and any(
            isinstance(ce, dict) and ce.get("type") == "max_stress" and ce.get("status") == "violated"
            for ce in ev.get("constraint_evidence") or []
        ):
            volume_improved_stress_bad = True

    for cand in ranking.get("candidates") or []:
        for v in cand.get("constraint_violations") or []:
            text = str(v).lower()
            stress_violation = stress_violation or "stress" in text
            deflection_violation = deflection_violation or "deflection" in text or "displacement" in text
            safety_violation = safety_violation or "safety" in text

    asm_rec = artifacts.get("analysis/assembly_design_recommendations.json") or {}
    asm_next = artifacts.get("analysis/assembly_next_actions.json") or {}
    asm_text = json.dumps([asm_rec, asm_next]).lower()
    interface_issue = any(key in asm_text for key in ("increase_preserve", "review_interface_refs", "request_user_input", "unresolved"))
    topopt_present = isinstance(artifacts.get("analysis/topology_optimization.json"), dict)
    cae_map_present = isinstance(artifacts.get("analysis/cae_result_map.json"), dict)
    asm_map_present = isinstance(artifacts.get("analysis/assembly_result_map.json"), dict)

    return {
        "objective": objective,
        "ranking": ranking,
        "accepted": accepted,
        "best": best,
        "evaluations_count": len(all_evals),
        "stress_violation": stress_violation,
        "deflection_violation": deflection_violation,
        "safety_violation": safety_violation,
        "proxy_low_confidence": proxy_low_conf,
        "missing_metrics": missing_metrics,
        "volume_improved_stress_bad": volume_improved_stress_bad,
        "interface_issue": interface_issue,
        "topopt_present": topopt_present,
        "cae_map_present": cae_map_present,
        "assembly_result_map_present": asm_map_present,
        "violation_evidence": evidence_links,
    }


def _objective_is_mass_or_volume(objective: dict[str, Any]) -> bool:
    metric = str(objective.get("metric") or "").lower()
    sense = str(objective.get("sense") or "").lower()
    return metric in ("mass", "volume", "reduce_mass", "reduce_volume") or (
        sense in ("minimize", "reduce") and metric in ("mass", "volume")
    )


def _hint_sort_key(h: dict[str, Any]) -> tuple[int, int, str]:
    pri = {"high": 0, "medium": 1, "low": 2}.get(h.get("priority"), 3)
    type_order = {
        "adjust_parameter": 0 if any("violat" in str(n).lower() or "stress" in str(n).lower() or "deflection" in str(n).lower() for n in h.get("safety_notes", []) + [h.get("reason")]) else 3,
        "protect_parameter": 1,
        "request_user_input": 2,
        "rerun_evaluation": 2,
        "stop_no_safe_hint": 4,
    }.get(h.get("type"), 5)
    return (pri, type_order, str(h.get("id")))


def _limit_hints(hints: list[dict[str, Any]], max_hints: int) -> list[dict[str, Any]]:
    protected = [h for h in hints if h.get("type") == "protect_parameter"]
    other = [h for h in hints if h.get("type") != "protect_parameter"]
    ordered = protected + sorted(other, key=_hint_sort_key)
    limited = ordered[:max_hints]
    for i, h in enumerate(limited, start=1):
        h["id"] = f"hint_{i:03d}"
    return limited


def _build_hints(problem: dict[str, Any], artifacts: dict[str, Any],
                 evaluations: dict[str, dict[str, Any]], *, max_hints: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], list[str]]:
    variables = [v for v in problem.get("variables") or [] if isinstance(v, dict)]
    selected_part_id = problem.get("selected_part_id")
    state = _collect_evidence_state(problem, artifacts, evaluations)
    warnings: list[str] = []
    rules_triggered: list[str] = []
    hints: list[dict[str, Any]] = []

    # Variable safety/protection hints.
    for var in variables:
        notes = _near_bound(var)
        if notes:
            warnings.extend([f"{var.get('id')}: {n}" for n in notes])
        if var.get("safe_to_modify") is False:
            hints.append(_make_hint(
                hid="pending",
                htype="protect_parameter",
                variable=var,
                suggested_direction="avoid",
                suggested_magnitude="none",
                priority="high",
                confidence="high",
                reason="avoid modifying this variable because safe_to_modify=false in the design-study problem",
                source_evidence=[_evidence(DESIGN_STUDY_PROBLEM_PATH, f"variables.{var.get('id')}.safe_to_modify", confidence="high")],
                safety_notes=[str(var.get("protected_reason") or "protected by design-study contract")] + notes,
                do_not_modify=True,
            ))
            rules_triggered.append("variable_safety_protect")

    adjustable = [v for v in variables if _safe_to_adjust(v, selected_part_id)]
    skipped_scope = [v.get("id") for v in variables if v.get("safe_to_modify") is not False and not _in_selected_scope(v, selected_part_id)]
    if skipped_scope:
        warnings.append(f"skipped non-selected-part variables: {sorted(skipped_scope)}")

    conf = "low" if state["proxy_low_confidence"] else ("medium" if state["evaluations_count"] else "low")
    priority = "medium" if not state["proxy_low_confidence"] else "low"
    vio_ev = state["violation_evidence"] or [_evidence(DESIGN_STUDY_CANDIDATE_RANKING_PATH, "constraint_violations", confidence=conf)]

    # Ranking/acceptance feedback.
    accepted = state["accepted"]
    if accepted.get("status") == "accepted":
        hints.append(_make_hint(
            hid="pending",
            htype="stop_no_safe_hint",
            suggested_direction="keep",
            suggested_magnitude="none",
            priority="low",
            confidence="medium",
            reason="an accepted derived candidate already exists; consider proceeding to review/next stage unless new evidence indicates issues",
            source_evidence=[_evidence("analysis/design_study_acceptance.json", "status", confidence="medium")],
            safety_notes=["does not promote accepted geometry to baseline"],
        ))
        rules_triggered.append("accepted_candidate_stop")

    best = state["best"]
    if best and best.get("recommendation") == "needs_more_evaluation":
        hints.append(_make_hint(
            hid="pending",
            htype="rerun_evaluation",
            suggested_direction="unknown",
            suggested_magnitude="unknown",
            priority="medium",
            confidence="medium",
            reason="best ranked candidate needs more evaluation before proposing additional geometry changes",
            source_evidence=[_evidence(DESIGN_STUDY_CANDIDATE_RANKING_PATH, "best_candidate_id", confidence="medium")],
            safety_notes=["prefer evaluation over additional geometry changes"],
        ))
        rules_triggered.append("ranking_needs_more_evaluation")
    if state["missing_metrics"]:
        hints.append(_make_hint(
            hid="pending",
            htype="rerun_evaluation",
            suggested_direction="unknown",
            suggested_magnitude="unknown",
            priority="medium",
            confidence="medium",
            reason="one or more candidate evaluations are partial or missing metrics; rerun/complete evaluation before stronger design changes",
            source_evidence=[_evidence(DESIGN_STUDY_SCORING_REPORT_PATH, "metrics_missing_summary", confidence="medium")],
        ))
        rules_triggered.append("candidate_comparison_missing_metrics")

    # Safety-driven adjustment rules.
    if state["stress_violation"] or state["safety_violation"]:
        rules_triggered.append("stress_or_safety_violation")
        for var in adjustable:
            role = _role(var)
            if role in _FILLET_ROLES or role in _THICKNESS_ROLES or role in _PRESERVE_ROLES:
                hints.append(_make_hint(
                    hid="pending",
                    htype="adjust_parameter",
                    variable=var,
                    suggested_direction="increase",
                    suggested_magnitude="medium" if state["safety_violation"] else "small",
                    priority="high",
                    confidence=conf,
                    reason="try increasing this parameter to address stress or safety-factor evidence before further mass/volume reduction",
                    source_evidence=vio_ev,
                    safety_notes=_near_bound(var) + ["do not combine with aggressive mass-reduction decreases until re-evaluated"],
                ))

    if state["deflection_violation"]:
        rules_triggered.append("deflection_violation")
        for var in adjustable:
            if _role(var) in _STIFFNESS_ROLES:
                hints.append(_make_hint(
                    hid="pending",
                    htype="adjust_parameter",
                    variable=var,
                    suggested_direction="increase",
                    suggested_magnitude="medium",
                    priority="high",
                    confidence=conf,
                    reason="try increasing stiffness-related geometry because deflection evidence violates or approaches the limit",
                    source_evidence=vio_ev,
                    safety_notes=_near_bound(var),
                ))

    if state["interface_issue"]:
        rules_triggered.append("assembly_interface_preservation")
        ev = [_evidence("analysis/assembly_design_recommendations.json", "recommendations", confidence="medium")]
        preserve_vars = [v for v in adjustable if _role(v) in _PRESERVE_ROLES]
        if preserve_vars:
            for var in preserve_vars:
                hints.append(_make_hint(
                    hid="pending",
                    htype="adjust_parameter",
                    variable=var,
                    suggested_direction="increase",
                    suggested_magnitude="small",
                    priority="high",
                    confidence=_confidence_lower(conf),
                    reason="consider increasing preserve/interface radius because assembly evidence requests interface preservation/review",
                    source_evidence=ev,
                    safety_notes=["assembly evidence is proxy/diagnostic unless backed by physical solver validation"] + _near_bound(var),
                ))
        else:
            hints.append(_make_hint(
                hid="pending",
                htype="request_user_input",
                suggested_direction="unknown",
                suggested_magnitude="unknown",
                priority="high",
                confidence="medium",
                reason="assembly evidence indicates unresolved or preserve-sensitive interfaces, but no safe preserve-radius variable is available",
                source_evidence=ev,
                safety_notes=["do not modify bolt holes or mounting interfaces without explicit safe variable scope"],
            ))

    # Mass/volume opportunity only when not blocked by critical evidence.
    if _objective_is_mass_or_volume(state["objective"]) and not (state["stress_violation"] or state["deflection_violation"] or state["safety_violation"]):
        rules_triggered.append("mass_volume_reduction_opportunity")
        for var in adjustable:
            role = _role(var)
            if role in _MASS_REDUCTION_ROLES:
                direction = "increase" if role == "hole_radius" else "decrease"
                hints.append(_make_hint(
                    hid="pending",
                    htype="adjust_parameter",
                    variable=var,
                    suggested_direction=direction,
                    suggested_magnitude="small",
                    priority=priority,
                    confidence=conf,
                    reason=("consider increasing this safe hole radius to reduce material" if role == "hole_radius"
                            else "consider decreasing this parameter slightly for mass/volume reduction, then rerun evaluation"),
                    source_evidence=[_evidence(DESIGN_STUDY_PROBLEM_PATH, "objective", confidence="medium")],
                    safety_notes=_near_bound(var),
                ))
            elif role in _FILLET_ROLES:
                hints.append(_make_hint(
                    hid="pending",
                    htype="adjust_parameter",
                    variable=var,
                    suggested_direction="keep",
                    suggested_magnitude="none",
                    priority="low",
                    confidence=conf,
                    reason="keep fillet radius during mass/volume reduction unless hotspot evidence suggests increasing it",
                    source_evidence=[_evidence(DESIGN_STUDY_PROBLEM_PATH, "objective", confidence="medium")],
                    safety_notes=_near_bound(var),
                ))

    if state["volume_improved_stress_bad"]:
        rules_triggered.append("candidate_comparison_volume_stress_tradeoff")
        for var in adjustable:
            if _role(var) in _FILLET_ROLES | _THICKNESS_ROLES:
                hints.append(_make_hint(
                    hid="pending",
                    htype="adjust_parameter",
                    variable=var,
                    suggested_direction="increase",
                    suggested_magnitude="small",
                    priority="high",
                    confidence=conf,
                    reason="a prior candidate improved volume but violated stress; try a smaller reduction or offset it with local fillet/thickness increase",
                    source_evidence=vio_ev,
                    safety_notes=_near_bound(var),
                ))

    if state["proxy_low_confidence"]:
        rules_triggered.append("proxy_low_confidence")
        hints.append(_make_hint(
            hid="pending",
            htype="request_user_input",
            suggested_direction="unknown",
            suggested_magnitude="unknown",
            priority="medium",
            confidence="low",
            reason="available evidence is proxy-derived or low confidence; prefer review or better evaluation before aggressive geometry changes",
            source_evidence=[_evidence("candidates/*/analysis/evaluation.json", "honesty.proxy_derived", confidence="low")],
            safety_notes=["contact_physics_modeled:false", "bolt_preload_modeled:false"],
        ))

    # If nothing evidence-specific triggers, emit generic safe low-confidence objective hints.
    if not hints and adjustable and _objective_is_mass_or_volume(state["objective"]):
        for var in adjustable[:2]:
            hints.append(_make_hint(
                hid="pending",
                htype="adjust_parameter",
                variable=var,
                suggested_direction="decrease" if _role(var) in _THICKNESS_ROLES else "unknown",
                suggested_magnitude="small",
                priority="low",
                confidence="low",
                reason="generic low-confidence hint from the objective only; needs evaluation before trusting the direction",
                source_evidence=[_evidence(DESIGN_STUDY_PROBLEM_PATH, "objective", confidence="low")],
                safety_notes=_near_bound(var) + ["no candidate evaluation/ranking evidence was available"],
            ))
        rules_triggered.append("generic_objective_hint")

    limited = _limit_hints(hints, max_hints)
    return limited, state, warnings, sorted(set(rules_triggered))


def _confidence_lower(confidence: str) -> str:
    return {"high": "medium", "medium": "low", "low": "low"}.get(confidence, "low")


def build_design_study_candidate_hints(
    package_path: str | Path,
    *,
    max_hints: int = 10,
) -> dict[str, Any]:
    """Build advisory candidate proposal hints from existing package evidence."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "failed", "reason": "package not found"}
    max_hints = max(1, int(max_hints or 10))

    artifacts: dict[str, Any] = {}
    input_present: list[str] = []
    input_missing: list[str] = []
    evaluations: dict[str, dict[str, Any]] = {}
    names: set[str] = set()
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            if isinstance(problem, dict):
                artifacts[DESIGN_STUDY_PROBLEM_PATH] = problem
                input_present.append(DESIGN_STUDY_PROBLEM_PATH)
            else:
                input_missing.append(DESIGN_STUDY_PROBLEM_PATH)
            for p in _OPTIONAL_EVIDENCE_PATHS:
                doc = _read_json(zf, p, names)
                if isinstance(doc, dict):
                    artifacts[p] = doc
                    input_present.append(p)
                else:
                    input_missing.append(p)
            evaluations = _load_candidate_evaluations(zf, names)
            for cid in evaluations:
                input_present.append(f"candidates/{cid}/analysis/evaluation.json")
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    if not isinstance(artifacts.get(DESIGN_STUDY_PROBLEM_PATH), dict):
        hints_doc = _empty_hints(status="insufficient_data", problem=None, limitations=["design_study_problem missing"])
        report = _report(
            status="insufficient_data",
            input_present=input_present,
            input_missing=input_missing,
            variables=[],
            protected_count=0,
            rules_triggered=[],
            hints=[],
            warnings=[],
            errors=["analysis/design_study_problem.json missing or invalid"],
            no_hints_reason="missing design study problem",
        )
        _replace_members(package_path, {
            DESIGN_STUDY_CANDIDATE_HINTS_PATH: _dumps(hints_doc),
            DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH: _dumps(report),
        })
        return _summary("insufficient_data", hints_doc)

    problem = artifacts[DESIGN_STUDY_PROBLEM_PATH]
    variables = [v for v in problem.get("variables") or [] if isinstance(v, dict)]
    if not variables:
        hints_doc = _empty_hints(status="needs_user_input", problem=problem, limitations=["no design variables available"])
        report = _report(
            status="needs_user_input",
            input_present=input_present,
            input_missing=input_missing,
            variables=[],
            protected_count=0,
            rules_triggered=[],
            hints=[],
            warnings=[],
            errors=["problem contains no variables"],
            no_hints_reason="missing variables",
        )
        _replace_members(package_path, {
            DESIGN_STUDY_CANDIDATE_HINTS_PATH: _dumps(hints_doc),
            DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH: _dumps(report),
        })
        return _summary("needs_user_input", hints_doc)

    hints, state, warnings, rules_triggered = _build_hints(problem, artifacts, evaluations, max_hints=max_hints)
    status = "ready" if hints else "needs_user_input"
    if hints and warnings:
        status = "warning"
    protected = [v for v in variables if v.get("safe_to_modify") is False]
    limitations = [
        "Candidate hints are advisory decision support, not optimization.",
        "No candidate patches are created automatically.",
        "No candidate execution, CAE, ranking, acceptance, or geometry mutation is performed.",
        "Low-confidence/proxy evidence should be reviewed before geometry changes.",
    ]
    if state.get("proxy_low_confidence"):
        limitations.append("Proxy-derived evidence lowers confidence; contact physics and bolt preload are not modeled.")
    hints_doc = {
        "format": DESIGN_STUDY_CANDIDATE_HINTS_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "problem_id": problem.get("id"),
        "target": {
            "selected_part_id": problem.get("selected_part_id"),
            "source_shape_ir": "geometry/shape_ir.json",
            "objective": problem.get("objective"),
        },
        "hints": hints,
        "protected_variables": [
            {
                "variable_id": v.get("id"),
                "variable_name": _variable_name(v),
                "semantic_role": _role(v),
                "protected_reason": v.get("protected_reason") or "safe_to_modify=false",
            }
            for v in protected
        ],
        "evidence_summary": {
            "input_artifacts_present": sorted(set(input_present)),
            "candidate_evaluations_loaded": len(evaluations),
            "ranking_present": DESIGN_STUDY_CANDIDATE_RANKING_PATH in artifacts,
            "assembly_recommendations_present": "analysis/assembly_design_recommendations.json" in artifacts,
            "cae_result_map_present": "analysis/cae_result_map.json" in artifacts,
            "topology_optimization_present": "analysis/topology_optimization.json" in artifacts,
            "stress_violation": state.get("stress_violation"),
            "deflection_violation": state.get("deflection_violation"),
            "safety_violation": state.get("safety_violation"),
            "proxy_low_confidence": state.get("proxy_low_confidence"),
        },
        "limitations": limitations,
        "baseline_modified": False,
    }
    report = _report(
        status=status,
        input_present=input_present,
        input_missing=input_missing,
        variables=variables,
        protected_count=len(protected),
        rules_triggered=rules_triggered,
        hints=hints,
        warnings=warnings,
        errors=[],
        no_hints_reason=None if hints else "no safe hints generated from available evidence",
    )
    _replace_members(package_path, {
        DESIGN_STUDY_CANDIDATE_HINTS_PATH: _dumps(hints_doc),
        DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH: _dumps(report),
    })
    return _summary(status, hints_doc)


def _empty_hints(status: str, problem: dict[str, Any] | None, limitations: list[str]) -> dict[str, Any]:
    return {
        "format": DESIGN_STUDY_CANDIDATE_HINTS_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "problem_id": problem.get("id") if isinstance(problem, dict) else None,
        "target": {
            "selected_part_id": problem.get("selected_part_id") if isinstance(problem, dict) else None,
            "source_shape_ir": "geometry/shape_ir.json",
            "objective": problem.get("objective") if isinstance(problem, dict) else None,
        },
        "hints": [],
        "protected_variables": [],
        "evidence_summary": {},
        "limitations": limitations,
        "baseline_modified": False,
    }


def _report(*, status: str, input_present: list[str], input_missing: list[str],
            variables: list[dict[str, Any]], protected_count: int, rules_triggered: list[str],
            hints: list[dict[str, Any]], warnings: list[str], errors: list[str],
            no_hints_reason: str | None) -> dict[str, Any]:
    conf_dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for h in hints:
        conf = h.get("confidence")
        if conf in conf_dist:
            conf_dist[conf] += 1
    return {
        "format": DESIGN_STUDY_CANDIDATE_HINTS_REPORT_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "input_artifacts_present": sorted(set(input_present)),
        "input_artifacts_missing": sorted(set(input_missing)),
        "variables_loaded": len(variables),
        "protected_variables_count": protected_count,
        "rules_evaluated": [
            "variable_safety",
            "mass_volume_reduction_opportunity",
            "stress_hotspot",
            "deflection_stiffness",
            "safety_factor",
            "assembly_interface_preservation",
            "ranking_feedback",
            "candidate_comparison",
            "proxy_low_confidence",
        ],
        "rules_triggered": sorted(set(rules_triggered)),
        "hints_generated": len(hints),
        "confidence_distribution": conf_dist,
        "limitations": [
            "Advisory only; does not create candidate patches.",
            "No optimization/search/random/grid/Bayesian/Pareto loop is run.",
            "No geometry, baseline, candidate execution, CAE, ranking, or acceptance mutation is performed.",
        ],
        "warnings": sorted(set(warnings)),
        "errors": errors,
        "no_hints_reason": no_hints_reason,
        "provenance": {
            "created_by": "aieng.design_study_hints",
            "baseline_modified": False,
            "candidate_patches_created": False,
            "candidates_executed": False,
            "solver_executed": False,
        },
    }


def _summary(status: str, hints_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "design_study_present": hints_doc.get("problem_id") is not None,
        "hint_count": len(hints_doc.get("hints") or []),
        "protected_variable_count": len(hints_doc.get("protected_variables") or []),
        "baseline_modified": False,
        "candidate_patches_created": False,
        "candidates_executed": False,
        "artifacts": [DESIGN_STUDY_CANDIDATE_HINTS_PATH, DESIGN_STUDY_CANDIDATE_HINTS_REPORT_PATH],
    }
