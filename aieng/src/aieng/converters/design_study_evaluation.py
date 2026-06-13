"""Design-study candidate evaluation from solver-neutral/local evidence (v0).

This module is deliberately backend-only and conservative.  It reads evidence
already present in a candidate workspace, normalizes a small set of
decision-relevant metrics, evaluates declared constraints, and writes
candidate-local artifacts:

  candidates/<candidate_id>/analysis/evaluation.json
  candidates/<candidate_id>/diagnostics/evaluation_report.json

It never runs a solver, never recompiles geometry, never creates/promotes a
candidate, and never overwrites baseline geometry.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.critique_engine import critique_geometry
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH

CANDIDATE_WORKSPACE_ROOT = "candidates/"
CANDIDATE_EVALUATION_REL = "analysis/evaluation.json"
CANDIDATE_EVALUATION_REPORT_REL = "diagnostics/evaluation_report.json"
CANDIDATE_EVALUATION_FORMAT = "aieng.design_study_candidate_evaluation"
CANDIDATE_EVALUATION_REPORT_FORMAT = "aieng.design_study_candidate_evaluation_report"
CANDIDATE_TOPOLOGY_MAP_REL = "geometry/topology_map.json"
CANDIDATE_FEATURE_GRAPH_REL = "graph/feature_graph.json"

_STATIC_METRIC_RELS = (
    "analysis/static_metrics.json",
    "results/static_metrics.json",
)
_COMPUTED_METRIC_RELS = (
    "analysis/computed_metrics.json",
    "results/computed_metrics.json",
    "analysis/assembly_computed_metrics.json",
    "results/assembly_computed_metrics.json",
)
_FIELD_REGION_RELS = (
    "analysis/field_regions.json",
    "results/field_regions.json",
    "analysis/assembly_field_regions.json",
    "results/assembly_field_regions.json",
)
_RESULT_MAP_RELS = (
    "analysis/cae_result_map.json",
    "analysis/assembly_result_map.json",
)
_MANIFEST_RELS = (
    "provenance/geometry_execution_manifest.json",
    "provenance/candidate.json",
)

_CANONICAL_FLAT_KEYS = {
    "mass": ("mass_kg", "mass", "total_mass", "total_mass_kg"),
    "volume": ("volume_mm3", "volume", "total_volume", "total_volume_mm3"),
    "max_stress": (
        "max_stress",
        "max_von_mises_stress",
        "max_von_mises_stress_mpa",
        "von_mises_max",
        "stress_max",
    ),
    "max_deflection": ("max_deflection", "max_displacement", "displacement_max", "deflection_max"),
    "min_safety_factor": ("min_safety_factor", "minimum_safety_factor", "safety_factor_min"),
    "compliance": ("compliance", "compliance_proxy"),
    "stiffness": ("stiffness", "stiffness_proxy"),
}

_DEFAULT_UNITS = {
    "mass": "kg",
    "volume": "mm^3",
    "max_stress": "MPa",
    "max_deflection": "mm",
    "min_safety_factor": None,
    "compliance": None,
    "stiffness": None,
}


def _sanitize_id(cid: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(cid or "candidate"))
    return s.strip("._") or "candidate"


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
    tmp = package_path.with_suffix(".dseval.tmp.aieng")
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
        for k in ("value", "max", "peak", "min", "average"):
            if k in value:
                n = _num(value.get(k))
                if n is not None:
                    return n
    return None


def _unit(value: Any, default: str | None = None) -> str | None:
    if isinstance(value, dict) and value.get("unit") is not None:
        return str(value.get("unit"))
    return default


def _confidence_min(a: str, b: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return a if order.get(a, 0) <= order.get(b, 0) else b


def _flat_key(canonical: str) -> str:
    return {
        "mass": "mass_kg",
        "volume": "volume_mm3",
        "max_stress": "max_stress",
        "max_deflection": "max_deflection",
        "min_safety_factor": "min_safety_factor",
        "compliance": "compliance",
        "stiffness": "stiffness",
    }[canonical]


def _better(canonical: str, old: float | None, new: float) -> bool:
    """Conservative aggregator: maxima for bad extrema, minima for safety factor."""
    if old is None:
        return True
    if canonical in ("min_safety_factor",):
        return new < old
    if canonical in ("max_stress", "max_deflection"):
        return new > old
    return False  # mass/volume/compliance/stiffness keep first explicit source


def _add_metric(
    normalized: dict[str, dict[str, Any]],
    canonical: str,
    value: Any,
    *,
    unit: str | None = None,
    source_path: str,
    load_case_id: str | None = None,
    confidence: str = "medium",
    evidence_role: str = "metric",
    proxy_derived: bool = False,
) -> None:
    n = _num(value)
    if n is None:
        return
    unit = unit or _unit(value, _DEFAULT_UNITS.get(canonical))
    old = normalized.get(canonical)
    if old and not _better(canonical, old.get("value"), n):
        # Preserve source trace for discarded non-conservative duplicates.
        old.setdefault("alternate_sources", []).append({
            "source_path": source_path,
            "load_case_id": load_case_id,
            "value": n,
            "unit": unit,
        })
        old["confidence"] = _confidence_min(old.get("confidence", "medium"), confidence)
        old["proxy_derived"] = bool(old.get("proxy_derived") or proxy_derived)
        return
    normalized[canonical] = {
        "value": n,
        "unit": unit,
        "load_case_id": load_case_id,
        "source_paths": [source_path],
        "evidence_role": evidence_role,
        "confidence": confidence,
        "proxy_derived": proxy_derived,
    }
    if old:
        normalized[canonical]["alternate_sources"] = [
            {
                "source_path": p,
                "load_case_id": old.get("load_case_id"),
                "value": old.get("value"),
                "unit": old.get("unit"),
            }
            for p in old.get("source_paths", [])
        ] + list(old.get("alternate_sources") or [])


def _extract_flat_metrics(
    doc: dict[str, Any],
    normalized: dict[str, dict[str, Any]],
    *,
    source_path: str,
    confidence: str = "medium",
    proxy_derived: bool = False,
) -> None:
    for canonical, keys in _CANONICAL_FLAT_KEYS.items():
        for key in keys:
            if key in doc:
                _add_metric(
                    normalized,
                    canonical,
                    doc.get(key),
                    unit=_unit(doc.get(key), _DEFAULT_UNITS.get(canonical)),
                    source_path=source_path,
                    load_case_id=str(doc.get("load_case_id")) if doc.get("load_case_id") else None,
                    confidence=confidence,
                    proxy_derived=proxy_derived,
                )
                break


def _metric_kind(metric: str, result_type: str = "") -> str | None:
    name = f"{metric} {result_type}".lower()
    if "safety" in name:
        return "min_safety_factor"
    if "stress" in name or "von_mises" in name:
        return "max_stress"
    if "displacement" in name or "deflection" in name:
        return "max_deflection"
    if "mass" in name:
        return "mass"
    if "volume" in name:
        return "volume"
    if "compliance" in name:
        return "compliance"
    if "stiffness" in name:
        return "stiffness"
    return None


def _extract_computed_metrics(
    doc: dict[str, Any],
    normalized: dict[str, dict[str, Any]],
    *,
    source_path: str,
    proxy_derived: bool = False,
) -> None:
    _extract_flat_metrics(doc, normalized, source_path=source_path, confidence="medium", proxy_derived=proxy_derived)
    load_cases = doc.get("load_cases") if isinstance(doc.get("load_cases"), list) else []
    for lc in load_cases:
        if not isinstance(lc, dict):
            continue
        load_case_id = str(lc.get("id") or lc.get("load_case_id") or "load_case_1")
        if isinstance(lc.get("metrics"), dict):
            for metric, value in lc["metrics"].items():
                kind = _metric_kind(str(metric))
                if kind:
                    _add_metric(
                        normalized,
                        kind,
                        value,
                        unit=_unit(value, _DEFAULT_UNITS.get(kind)),
                        source_path=source_path,
                        load_case_id=load_case_id,
                        confidence="medium",
                        proxy_derived=proxy_derived,
                    )
        for res in lc.get("results") or []:
            if not isinstance(res, dict):
                continue
            kind = _metric_kind(str(res.get("metric") or ""), str(res.get("result_type") or ""))
            if not kind:
                continue
            value = res.get("max")
            if kind == "min_safety_factor":
                value = res.get("min", res.get("max", res.get("value")))
            elif value is None:
                value = res.get("value", res.get("peak"))
            _add_metric(
                normalized,
                kind,
                value,
                unit=res.get("unit") or _DEFAULT_UNITS.get(kind),
                source_path=source_path,
                load_case_id=load_case_id,
                confidence="medium",
                proxy_derived=proxy_derived,
            )


def _extract_field_regions(
    doc: dict[str, Any],
    normalized: dict[str, dict[str, Any]],
    *,
    source_path: str,
    proxy_derived: bool = False,
) -> None:
    for region in doc.get("regions") or doc.get("clusters") or []:
        if not isinstance(region, dict):
            continue
        kind = _metric_kind(str(region.get("metric") or ""), str(region.get("result_type") or region.get("field") or ""))
        if kind not in ("max_stress", "max_deflection"):
            continue
        value = region.get("value") or region.get("magnitude") or {}
        _add_metric(
            normalized,
            kind,
            value.get("peak", value.get("max", value.get("value"))) if isinstance(value, dict) else value,
            unit=_unit(value, _DEFAULT_UNITS.get(kind)),
            source_path=source_path,
            load_case_id=str(region.get("load_case_id")) if region.get("load_case_id") else None,
            confidence="low" if proxy_derived or region.get("proxy_derived") else "medium",
            evidence_role="field_region_peak",
            proxy_derived=bool(proxy_derived or region.get("proxy_derived")),
        )


def _extract_manifest(doc: dict[str, Any], normalized: dict[str, dict[str, Any]], *, source_path: str) -> None:
    _extract_flat_metrics(doc, normalized, source_path=source_path, confidence="low")
    if isinstance(doc.get("metrics"), dict):
        _extract_flat_metrics(doc["metrics"], normalized, source_path=source_path, confidence="low")


def _to_flat_metrics(normalized: dict[str, dict[str, Any]]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for canonical, entry in normalized.items():
        value = entry.get("value")
        if value is not None:
            flat[_flat_key(canonical)] = value
    return flat


# Load-case-dependent metrics whose controlling case is worth surfacing.
_LOAD_CASE_METRICS = ("max_stress", "max_deflection", "min_safety_factor")


def _load_case_summary(
    normalized: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Surface which load case produced each controlling metric.

    The worst-case selection in ``_add_metric`` already keeps the controlling
    load case (``load_case_id``) and records the others under
    ``alternate_sources``; this lifts that out of ``normalized_metrics`` into a
    first-class, consumable summary so ranking/recommendation (and the UI) can
    see *which* load case drove each controlling metric without re-deriving it.

    Missing metrics are simply absent — never fabricated. A metric present
    without any load-case attribution reports ``controlling_load_case_id: null``
    honestly rather than inventing one.
    """
    summary: list[dict[str, Any]] = []
    considered: set[str] = set()
    for canonical in _LOAD_CASE_METRICS:
        entry = normalized.get(canonical)
        if not entry or entry.get("value") is None:
            continue
        controlling = entry.get("load_case_id")
        cases: list[str] = [controlling] if controlling else []
        for alt in entry.get("alternate_sources") or []:
            alt_id = alt.get("load_case_id") if isinstance(alt, dict) else None
            if alt_id:
                cases.append(str(alt_id))
        considered.update(cases)
        summary.append({
            "metric": _flat_key(canonical),
            "value": entry.get("value"),
            "unit": entry.get("unit"),
            "controlling_load_case_id": controlling,
            "load_cases_considered": sorted(set(cases)),
        })
    return summary, sorted(considered)


def _constraint_metric(constraint: dict[str, Any], flat: dict[str, Any]) -> tuple[str | None, float | None]:
    ctype = constraint.get("type")
    if ctype == "max_stress":
        return "max_stress", _num(flat.get("max_stress"))
    if ctype == "max_deflection":
        return "max_deflection", _num(flat.get("max_deflection"))
    if ctype == "min_safety_factor":
        return "min_safety_factor", _num(flat.get("min_safety_factor"))
    if ctype == "mass_limit":
        return "mass", _num(flat.get("mass_kg"))
    if ctype == "volume_limit":
        return "volume", _num(flat.get("volume_mm3"))
    if ctype == "preserve_interface":
        return "interfaces_preserved", flat.get("interfaces_preserved")
    return None, None


def _evaluate_critique_findings(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool, list[str]]:
    """Map blocking ``cad.critique`` findings into constraint evidence.

    Blocking findings are high-severity geometry problems (e.g. floating
    components) and manufacturing-rule findings at high/medium severity
    (e.g. min wall thickness).  Returns ``(evidence, has_blocking, reasons)``.
    """
    evidence: list[dict[str, Any]] = []
    has_blocking = False
    reasons: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "")
        category = str(finding.get("category") or "")
        rule = str(finding.get("rule") or "")
        is_blocking = (
            (category == "manufacturing_rule" and severity in ("high", "medium"))
            or (category == "geometry" and severity == "high")
        )
        if not is_blocking:
            continue
        has_blocking = True
        reason = f"{rule}: {finding.get('observation') or finding.get('feature', '')}".strip()
        reasons.append(reason)
        evidence.append({
            "id": f"critique_{rule}",
            "type": "manufacturing_rule",
            "rule": rule,
            "feature": finding.get("feature"),
            "feature_id": finding.get("feature_id"),
            "severity": severity,
            "actual": finding.get("observation"),
            "status": "violated",
            "source": "cad.critique",
            "finding_id": finding.get("id"),
        })
    return evidence, has_blocking, reasons


def _evaluate_constraints(problem: dict[str, Any] | None, flat: dict[str, Any]) -> tuple[list[dict[str, Any]], str, list[str]]:
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    feasibility = "unknown"
    constraints = problem.get("constraints") if isinstance(problem, dict) else []
    any_evaluated = False
    any_violation = False

    for constraint in constraints or []:
        if not isinstance(constraint, dict):
            continue
        ctype = str(constraint.get("type") or "")
        cid = str(constraint.get("id") or ctype or "constraint")
        if ctype in ("manufacturability", "manufacturability_hint"):
            evidence.append({"id": cid, "type": ctype, "status": "warning_only", "reason": "manufacturability hints are advisory in v0"})
            warnings.append(f"{cid}: manufacturability hint recorded as warning only")
            continue
        metric, actual = _constraint_metric(constraint, flat)
        if ctype == "preserve_interface":
            expected = constraint.get("preserved", True)
            status = "unknown" if actual is None else ("satisfied" if bool(actual) == bool(expected) else "violated")
            any_evaluated = any_evaluated or actual is not None
            any_violation = any_violation or status == "violated"
            evidence.append({"id": cid, "type": ctype, "metric": metric, "actual": actual, "expected": expected, "status": status})
            continue
        limit = _num(constraint.get("limit"))
        if metric is None or limit is None:
            evidence.append({"id": cid, "type": ctype, "status": "unsupported", "reason": "constraint type or limit is unsupported"})
            continue
        if actual is None:
            evidence.append({"id": cid, "type": ctype, "metric": metric, "limit": limit, "status": "unknown", "reason": "required metric missing"})
            continue
        any_evaluated = True
        if ctype in ("max_stress", "max_deflection", "mass_limit", "volume_limit"):
            violated = actual > limit
            relation = "<="
        elif ctype == "min_safety_factor":
            violated = actual < limit
            relation = ">="
        else:
            violated = False
            relation = "?"
        any_violation = any_violation or violated
        evidence.append({
            "id": cid,
            "type": ctype,
            "metric": metric,
            "actual": actual,
            "limit": limit,
            "relation": relation,
            "unit": constraint.get("unit"),
            "status": "violated" if violated else "satisfied",
        })

    if any_violation:
        feasibility = "infeasible"
    elif any_evaluated:
        feasibility = "feasible"
    return evidence, feasibility, warnings


def _read_candidate_sources(zf: zipfile.ZipFile, names: set[str], ws: str) -> dict[str, Any]:
    docs: dict[str, Any] = {}
    for rel in (
        *_STATIC_METRIC_RELS,
        *_COMPUTED_METRIC_RELS,
        *_FIELD_REGION_RELS,
        *_RESULT_MAP_RELS,
        *_MANIFEST_RELS,
        CANDIDATE_EVALUATION_REL,
        CANDIDATE_TOPOLOGY_MAP_REL,
        CANDIDATE_FEATURE_GRAPH_REL,
    ):
        path = f"{ws}{rel}"
        doc = _read_json(zf, path, names)
        if isinstance(doc, dict):
            docs[path] = doc
    return docs


def evaluate_design_study_candidate(package_path: str | Path, candidate_id: str) -> dict[str, Any]:
    """Evaluate one candidate from candidate-local artifacts.  No solver/compile is run."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "failed", "reason": "package not found"}
    sid = _sanitize_id(candidate_id)
    ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"
    eval_path = f"{ws}{CANDIDATE_EVALUATION_REL}"
    report_path = f"{ws}{CANDIDATE_EVALUATION_REPORT_REL}"

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            if not any(n.startswith(ws) for n in names):
                return {
                    "status": "insufficient_data",
                    "candidate_id": sid,
                    "reason": f"candidate workspace not found at {ws}",
                    "baseline_modified": False,
                }
            docs = _read_candidate_sources(zf, names, ws)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    normalized: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    errors: list[str] = []
    source_paths: list[str] = []
    proxy_derived = False

    for path, doc in docs.items():
        rel = path[len(ws):]
        source_paths.append(path)
        is_assembly = "assembly_" in rel or bool(doc.get("proxy_derived"))
        proxy_derived = proxy_derived or is_assembly
        if rel == CANDIDATE_EVALUATION_REL:
            # Legacy/static evaluation input.  If already normalized, also preserve
            # normalized_metrics; otherwise read its flat metrics.
            nm = doc.get("normalized_metrics")
            if isinstance(nm, dict) and nm:
                for k, v in nm.items():
                    if isinstance(v, dict) and _num(v.get("value")) is not None:
                        _add_metric(
                            normalized, k, v.get("value"), unit=v.get("unit"),
                            source_path=path, load_case_id=v.get("load_case_id"),
                            confidence=v.get("confidence", "medium"),
                            proxy_derived=bool(v.get("proxy_derived")),
                        )
            if isinstance(doc.get("metrics"), dict):
                _extract_flat_metrics(doc["metrics"], normalized, source_path=path, confidence="medium", proxy_derived=is_assembly)
            warnings.extend([str(w) for w in doc.get("warnings") or []])
            errors.extend([str(e) for e in doc.get("errors") or []])
        elif rel in _STATIC_METRIC_RELS:
            _extract_flat_metrics(doc, normalized, source_path=path, confidence="medium", proxy_derived=is_assembly)
        elif rel in _COMPUTED_METRIC_RELS:
            _extract_computed_metrics(doc, normalized, source_path=path, proxy_derived=is_assembly)
            warnings.extend([str(w) for w in doc.get("warnings") or []])
        elif rel in _FIELD_REGION_RELS:
            _extract_field_regions(doc, normalized, source_path=path, proxy_derived=is_assembly)
            warnings.extend([str(w) for w in doc.get("warnings") or []])
        elif rel in _MANIFEST_RELS:
            _extract_manifest(doc, normalized, source_path=path)

    flat = _to_flat_metrics(normalized)
    # Pass through explicit interface preservation booleans from static/legacy evidence.
    for path, doc in docs.items():
        metrics_doc = doc.get("metrics") if isinstance(doc.get("metrics"), dict) else doc
        if isinstance(metrics_doc, dict) and "interfaces_preserved" in metrics_doc:
            flat["interfaces_preserved"] = bool(metrics_doc.get("interfaces_preserved"))

    constraint_evidence, feasibility, c_warnings = _evaluate_constraints(problem if isinstance(problem, dict) else None, flat)
    warnings.extend(c_warnings)

    # Run deterministic cad.critique on candidate workspace geometry if available.
    topo = docs.get(f"{ws}{CANDIDATE_TOPOLOGY_MAP_REL}")
    fg = docs.get(f"{ws}{CANDIDATE_FEATURE_GRAPH_REL}")
    critique_result: dict[str, Any] | None = None
    critique_blocking = False
    critique_reasons: list[str] = []
    critique_available = isinstance(topo, dict) and isinstance(fg, dict)
    compile_status = docs.get(f"{ws}{CANDIDATE_EVALUATION_REL}", {}).get("compile_status", "not_run")
    geometry_expected = compile_status in ("compile_succeeded", "compiled")
    if critique_available:
        critique_result = critique_geometry(topo, fg, mode="engineering")
        if critique_result.get("status") == "ok":
            critique_evidence, critique_blocking, critique_reasons = _evaluate_critique_findings(
                critique_result.get("findings", [])
            )
            constraint_evidence.extend(critique_evidence)
            if critique_blocking:
                feasibility = "infeasible"
        else:
            warnings.append(f"cad.critique failed: {critique_result.get('message') or critique_result.get('code')}")
            if geometry_expected and feasibility == "feasible":
                feasibility = "unknown"
    elif geometry_expected:
        warnings.append("candidate workspace geometry not available for cad.critique; feasibility is unknown")
        if feasibility == "feasible":
            feasibility = "unknown"

    if not flat and not critique_available:
        eval_status = "insufficient_data"
        feasibility = "unknown"
    elif errors:
        eval_status = "partial"
    elif any(e.get("status") == "unknown" for e in constraint_evidence):
        eval_status = "partial"
    else:
        eval_status = "complete"

    load_case_summary, load_cases_considered = _load_case_summary(normalized)

    confidence = "high" if flat and not proxy_derived and eval_status == "complete" else ("medium" if flat else "low")
    if proxy_derived:
        confidence = _confidence_min(confidence, "medium")
        warnings.append("assembly/proxy evidence lowers confidence; contact physics and bolt preload are not modeled")

    evaluation = {
        "format": CANDIDATE_EVALUATION_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "candidate_id": sid,
        "evaluation_status": eval_status,
        "compile_status": docs.get(f"{ws}{CANDIDATE_EVALUATION_REL}", {}).get("compile_status", "not_run"),
        "feasibility": feasibility,
        "confidence": confidence,
        "metrics": flat,  # backward-compatible flat metrics consumed by PR3 ranking.
        "normalized_metrics": normalized,
        "load_case_summary": load_case_summary,
        "load_cases_considered": load_cases_considered,
        "constraint_evidence": constraint_evidence,
        "source_artifact_paths": sorted(set(source_paths)),
        "warnings": sorted(set(warnings)),
        "errors": errors,
        "honesty": {
            "solver_executed": False,
            "baseline_modified": False,
            "candidate_workspace_only": True,
            "proxy_derived": proxy_derived,
            "contact_physics_modeled": False if proxy_derived else None,
            "bolt_preload_modeled": False if proxy_derived else None,
            "production_ready": False,
        },
        "baseline_modified": False,
        "reason": "candidate-local solver-neutral/static evidence normalized; no solver or geometry recompile was run",
        "critique": critique_result,
        "critique_blocking": critique_blocking,
        "critique_reasons": critique_reasons,
    }
    report = {
        "format": CANDIDATE_EVALUATION_REPORT_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "candidate_id": sid,
        "status": eval_status,
        "metrics_found": sorted(flat.keys()),
        "metrics_missing": [
            name for name in ("mass_kg", "volume_mm3", "max_stress", "max_deflection", "min_safety_factor")
            if name not in flat
        ],
        "controlling_load_cases": {
            item["metric"]: item["controlling_load_case_id"] for item in load_case_summary
        },
        "load_cases_considered": load_cases_considered,
        "constraint_summary": {
            "evaluated": len([e for e in constraint_evidence if e.get("status") in ("satisfied", "violated")]),
            "violated": len([e for e in constraint_evidence if e.get("status") == "violated"]),
            "unknown": len([e for e in constraint_evidence if e.get("status") == "unknown"]),
            "warning_only": len([e for e in constraint_evidence if e.get("status") == "warning_only"]),
        },
        "critique": {
            "available": critique_available,
            "blocking": critique_blocking,
            "reasons": critique_reasons,
            "verdict": critique_result.get("verdict") if critique_result else None,
        },
        "source_artifact_paths": sorted(set(source_paths)),
        "warnings": evaluation["warnings"],
        "errors": errors,
        "provenance": {
            "created_by": "aieng.design_study_evaluation",
            "baseline_modified": False,
            "solver_executed": False,
            "geometry_recompiled": False,
        },
    }

    _replace_members(package_path, {eval_path: _dumps(evaluation), report_path: _dumps(report)})
    return {
        "status": "ok" if eval_status != "insufficient_data" else "insufficient_data",
        "candidate_id": sid,
        "evaluation_status": eval_status,
        "feasibility": feasibility,
        "confidence": confidence,
        "baseline_modified": False,
        "artifacts": [eval_path, report_path],
        "critique_blocking": critique_blocking,
        "critique_reasons": critique_reasons,
    }
