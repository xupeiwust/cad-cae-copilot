"""Verification gate for CAD modification proposals (Phase 37).

Takes a single proposal (shape: see ``cae_recommendation``) plus the source
``.aieng`` package and runs a pre-execution verification pass. Returns a
verdict (``pass`` / ``warn`` / ``fail``) with a list of per-check results.

Boundary rules (Phase 37 honesty):

* Verification is a pre-execution heuristic check. It does NOT replace
  re-simulation as the authoritative check on physical correctness.
* Read-only on the package: never mutates, never advances claims, never
  executes CAD/CAE operations.
* Regression checks use thickness-scaling heuristics; they predict risk,
  they do not guarantee outcomes.
* Geometry-kernel checks (does the modified topology remain valid?) are
  out of scope for this phase — those defer to a future
  ``aieng_freecad_mcp`` Phase 37b.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import yaml

from .cae_recommendation import MODIFICATION_VOCABULARY


__all__ = [
    "VERIFICATION_SCHEMA",
    "STRICTNESS_MODES",
    "MANUFACTURABILITY_FLOORS",
    "verify_cad_modification_proposal",
    "verify_recommendations",
    "generate_verification_markdown",
]


VERIFICATION_SCHEMA = "0.1"

STRICTNESS_MODES: tuple[str, ...] = ("lenient", "default", "strict")

# Hard manufacturability floors. Conservative defaults; deliberately not
# material-aware in the first cut. Tunable in a later phase.
MANUFACTURABILITY_FLOORS: dict[str, float] = {
    "thickness_mm": 1.0,
    "diameter_mm": 2.0,
    "fillet_radius_mm": 0.2,
}

# Heuristic exponent for thickness -> safety-factor scaling on
# bending-dominated features. SF_after ~ SF_before * (t_after / t_before) ** _BENDING_BETA.
# This is intentionally simple; the verification gate's role is to surface
# risk, not to replace re-simulation.
_BENDING_BETA = 2.0


# ---------------------------------------------------------------------------
# Package readers (shared shape with cae_recommendation but lighter)
# ---------------------------------------------------------------------------


def _read_json_member(zf: zipfile.ZipFile, name: str) -> Any | None:
    if name not in zf.namelist():
        return None
    try:
        with zf.open(name) as fh:
            return json.load(fh)
    except Exception:
        return None


def _read_yaml_member(zf: zipfile.ZipFile, name: str) -> Any | None:
    if name not in zf.namelist():
        return None
    try:
        with zf.open(name) as fh:
            return yaml.safe_load(fh)
    except Exception:
        return None


def _read_evidence(package_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Read the minimum evidence needed for verification."""
    warnings: list[str] = []
    out: dict[str, Any] = {
        "design_targets": None,
        "computed_metrics": None,
        "stress_by_feature": None,
        "features": None,
    }

    if not package_path.exists():
        warnings.append(f"Package not found: {package_path}")
        return out, warnings

    if package_path.is_dir():
        candidates = {
            "design_targets": package_path / "task" / "design_targets.yaml",
            "computed_metrics": package_path / "results" / "computed_metrics.json",
            "stress_by_feature": package_path / "results" / "stress_by_feature.json",
            "features": package_path / "simulation" / "cae_imports" / "parsed_features.json",
        }
        for key, p in candidates.items():
            if not p.exists():
                warnings.append(f"Missing evidence: {p.relative_to(package_path)}")
                continue
            try:
                if p.suffix == ".yaml":
                    out[key] = yaml.safe_load(p.read_text(encoding="utf-8"))
                else:
                    out[key] = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                warnings.append(f"Failed to parse {p.name}: {type(exc).__name__}: {exc}")
        return out, warnings

    if package_path.suffix != ".aieng":
        warnings.append(f"Package is neither a directory nor a .aieng file: {package_path}")
        return out, warnings

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            members = {
                "design_targets": "task/design_targets.yaml",
                "computed_metrics": "results/computed_metrics.json",
                "stress_by_feature": "results/stress_by_feature.json",
                "features": "simulation/cae_imports/parsed_features.json",
            }
            for key, name in members.items():
                if name not in zf.namelist():
                    warnings.append(f"Missing evidence: {name}")
                    continue
                if name.endswith(".yaml"):
                    out[key] = _read_yaml_member(zf, name)
                else:
                    out[key] = _read_json_member(zf, name)
    except zipfile.BadZipFile as exc:
        warnings.append(f"Malformed .aieng zip: {exc}")

    return out, warnings


def _feature_by_id(features: Any, feature_id: str) -> dict[str, Any] | None:
    if not isinstance(features, dict):
        return None
    for f in features.get("features") or []:
        if isinstance(f, dict) and f.get("id") == feature_id:
            return f
    return None


def _stress_for_feature(stress_by_feature: Any, feature_id: str) -> dict[str, Any] | None:
    if not isinstance(stress_by_feature, dict):
        return None
    for s in stress_by_feature.get("features") or []:
        if isinstance(s, dict) and s.get("feature_ref") == feature_id:
            return s
    return None


def _design_target_min_sf(design_targets: Any) -> float | None:
    if not isinstance(design_targets, dict):
        return None
    best: float | None = None
    for t in design_targets.get("targets") or []:
        if not isinstance(t, dict):
            continue
        ttype = t.get("target_type") or t.get("metric")
        if ttype == "minimum_safety_factor":
            val = t.get("threshold")
            if val is None:
                val = t.get("value")
            if isinstance(val, (int, float)):
                best = float(val) if best is None else max(best, float(val))
    return best


def _preserved_feature_ids(design_targets: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(design_targets, dict):
        return out
    for t in design_targets.get("targets") or []:
        if not isinstance(t, dict):
            continue
        ttype = t.get("target_type") or t.get("metric")
        if ttype not in ("preserved_interface", "preserved_feature"):
            continue
        for prot in t.get("protected_features") or []:
            if isinstance(prot, dict) and prot.get("feature_id"):
                out.add(prot["feature_id"])
            elif isinstance(prot, str):
                out.add(prot)
    return out


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check(
    check_id: str,
    category: str,
    status: str,
    message: str,
    *,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "status": status,
        "message": message,
        "evidence_refs": evidence_refs or [],
    }


def _check_proposal_shape(proposal: Any) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        return _check(
            "schema.proposal_shape",
            "schema",
            "fail",
            f"Proposal must be a dict; got {type(proposal).__name__}.",
        )
    missing = [k for k in ("feature_ref", "action_type") if not proposal.get(k)]
    if missing:
        return _check(
            "schema.proposal_shape",
            "schema",
            "fail",
            f"Proposal missing required fields: {missing}.",
        )
    return _check(
        "schema.proposal_shape",
        "schema",
        "pass",
        "Proposal has required fields.",
    )


def _check_action_vocabulary(action_type: str) -> dict[str, Any]:
    if action_type in MODIFICATION_VOCABULARY:
        return _check(
            "schema.action_in_vocabulary",
            "schema",
            "pass",
            f"action_type '{action_type}' is in the supported vocabulary.",
        )
    return _check(
        "schema.action_in_vocabulary",
        "schema",
        "fail",
        f"action_type '{action_type}' is not in vocabulary {list(MODIFICATION_VOCABULARY)}.",
    )


def _check_feature_exists(
    feature_id: str, feature: dict[str, Any] | None
) -> dict[str, Any]:
    if feature is None:
        return _check(
            "schema.feature_exists",
            "schema",
            "fail",
            f"feature_ref '{feature_id}' does not exist in parsed_features.json.",
            evidence_refs=["simulation/cae_imports/parsed_features.json"],
        )
    return _check(
        "schema.feature_exists",
        "schema",
        "pass",
        f"feature_ref '{feature_id}' exists.",
        evidence_refs=["simulation/cae_imports/parsed_features.json"],
    )


def _check_parameter_change(
    proposal: dict[str, Any], feature: dict[str, Any] | None
) -> dict[str, Any]:
    change = proposal.get("parameter_change")
    if not isinstance(change, dict):
        return _check(
            "schema.parameter_change",
            "schema",
            "fail",
            "Proposal is missing a parameter_change block.",
        )
    name = change.get("name")
    from_val = change.get("from")
    to_val = change.get("to")
    if not name or from_val is None or to_val is None:
        return _check(
            "schema.parameter_change",
            "schema",
            "fail",
            "parameter_change must include name, from, and to.",
        )
    if feature is not None:
        params = feature.get("parameters") or {}
        if name not in params:
            return _check(
                "schema.parameter_change",
                "schema",
                "fail",
                f"parameter '{name}' is not declared on feature "
                f"'{feature.get('id', '?')}'; declared params: "
                f"{sorted(params.keys())}.",
            )
        declared = params.get(name)
        if isinstance(declared, (int, float)) and not isinstance(from_val, (int, float)):
            return _check(
                "schema.parameter_change",
                "schema",
                "fail",
                f"parameter '{name}' is numeric in feature; proposal.from is "
                f"{type(from_val).__name__}.",
            )
    return _check(
        "schema.parameter_change",
        "schema",
        "pass",
        f"parameter_change targets '{name}' with valid from/to.",
    )


def _check_preserved_feature(
    feature_id: str, preserved: set[str]
) -> dict[str, Any]:
    if feature_id in preserved:
        return _check(
            "schema.preserved_feature_not_modified",
            "schema",
            "fail",
            f"feature '{feature_id}' is in a preserved_interface target and "
            "must not be modified.",
            evidence_refs=["task/design_targets.yaml"],
        )
    return _check(
        "schema.preserved_feature_not_modified",
        "schema",
        "pass",
        f"feature '{feature_id}' is not preserved.",
    )


def _check_manufacturability(
    action_type: str, parameter_change: dict[str, Any]
) -> dict[str, Any]:
    name = parameter_change.get("name") if isinstance(parameter_change, dict) else None
    to_val = parameter_change.get("to") if isinstance(parameter_change, dict) else None
    floor = MANUFACTURABILITY_FLOORS.get(name) if isinstance(name, str) else None
    if floor is None or not isinstance(to_val, (int, float)):
        return _check(
            "manufacturability.parameter_floor",
            "manufacturability",
            "skipped",
            f"No manufacturability floor for parameter '{name}'.",
        )
    if to_val < floor:
        return _check(
            "manufacturability.parameter_floor",
            "manufacturability",
            "fail",
            f"Proposed {name}={to_val} is below the manufacturability floor "
            f"({floor}); reject before execution.",
        )
    return _check(
        "manufacturability.parameter_floor",
        "manufacturability",
        "pass",
        f"Proposed {name}={to_val} meets the manufacturability floor ({floor}).",
    )


def _predict_sf_after_thinning(
    *,
    sf_before: float,
    thickness_before: float,
    thickness_after: float,
) -> float | None:
    if thickness_before <= 0 or thickness_after <= 0:
        return None
    ratio = thickness_after / thickness_before
    return float(sf_before) * (ratio ** _BENDING_BETA)


def _check_regression_thinning_sf(
    *,
    action_type: str,
    parameter_change: dict[str, Any],
    feature: dict[str, Any] | None,
    stress: dict[str, Any] | None,
    min_required_sf: float | None,
    strictness: str,
) -> dict[str, Any]:
    """Predict post-thinning SF and compare to the design floor."""
    if action_type != "thin":
        return _check(
            "regression.thinning_sf_floor",
            "regression",
            "skipped",
            "Not a thinning proposal.",
        )
    name = parameter_change.get("name") if isinstance(parameter_change, dict) else None
    from_val = parameter_change.get("from") if isinstance(parameter_change, dict) else None
    to_val = parameter_change.get("to") if isinstance(parameter_change, dict) else None
    if name != "thickness_mm" or not isinstance(from_val, (int, float)) or not isinstance(to_val, (int, float)):
        return _check(
            "regression.thinning_sf_floor",
            "regression",
            "skipped",
            "Thinning proposal does not have a thickness_mm parameter_change with numeric from/to.",
        )
    sf_before = stress.get("safety_factor") if isinstance(stress, dict) else None
    if not isinstance(sf_before, (int, float)) or not isinstance(min_required_sf, (int, float)):
        return _check(
            "regression.thinning_sf_floor",
            "regression",
            "skipped",
            "Missing pre-change safety_factor or required min_SF; cannot predict regression.",
        )
    predicted = _predict_sf_after_thinning(
        sf_before=float(sf_before),
        thickness_before=float(from_val),
        thickness_after=float(to_val),
    )
    if predicted is None:
        return _check(
            "regression.thinning_sf_floor",
            "regression",
            "skipped",
            "Could not predict post-change SF (non-positive thickness).",
        )

    msg = (
        f"Predicted post-thinning SF = {predicted:.2f} "
        f"(pre {sf_before:.2f}, thickness {from_val} -> {to_val}, beta={_BENDING_BETA}); "
        f"required min_SF = {min_required_sf}."
    )
    if predicted < min_required_sf:
        # In lenient mode, downgrade the predicted-violation to a warning
        # because the heuristic is rough. In default and strict modes the
        # predicted violation blocks execution.
        status = "warn" if strictness == "lenient" else "fail"
        return _check(
            "regression.thinning_sf_floor",
            "regression",
            status,
            msg + " Proposal predicted to violate the SF floor.",
            evidence_refs=["results/stress_by_feature.json", "task/design_targets.yaml"],
        )
    return _check(
        "regression.thinning_sf_floor",
        "regression",
        "pass",
        msg + " Predicted to remain above the SF floor.",
        evidence_refs=["results/stress_by_feature.json", "task/design_targets.yaml"],
    )


def _check_unnecessary_thickening(
    *,
    action_type: str,
    feature_id: str,
    stress: dict[str, Any] | None,
    min_required_sf: float | None,
) -> dict[str, Any]:
    if action_type != "thicken":
        return _check(
            "regression.thicken_when_unnecessary",
            "regression",
            "skipped",
            "Not a thickening proposal.",
        )
    sf = stress.get("safety_factor") if isinstance(stress, dict) else None
    if not isinstance(sf, (int, float)) or not isinstance(min_required_sf, (int, float)):
        return _check(
            "regression.thicken_when_unnecessary",
            "regression",
            "skipped",
            "Cannot evaluate whether thickening is necessary without SF + floor.",
        )
    if sf >= min_required_sf:
        return _check(
            "regression.thicken_when_unnecessary",
            "regression",
            "warn",
            f"Feature '{feature_id}' already has SF={sf:.2f} >= {min_required_sf}; "
            "thickening adds mass without addressing a margin violation.",
            evidence_refs=["results/stress_by_feature.json"],
        )
    return _check(
        "regression.thicken_when_unnecessary",
        "regression",
        "pass",
        f"Feature '{feature_id}' SF={sf:.2f} < {min_required_sf}; thickening is justified.",
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _verdict_from_checks(checks: list[dict[str, Any]], strictness: str) -> str:
    statuses = {c.get("status") for c in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "fail" if strictness == "strict" else "warn"
    return "pass"


def _claim_policy() -> dict[str, Any]:
    return {
        "verification_is_pre_execution": True,
        "verification_does_not_replace_resimulation": True,
        "physical_correctness_not_claimed": True,
        "geometry_kernel_checks_not_performed": True,
        "claims_advanced": False,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify_cad_modification_proposal(
    proposal: Any,
    package_path: str | Path,
    *,
    strictness: str = "default",
) -> dict[str, Any]:
    """Run a verification pass on a single CAD modification proposal.

    Returns a verdict dict with ``status`` in ``{pass, warn, fail}`` and a
    list of per-check results. Read-only; never mutates the package and
    never executes CAD/CAE operations.

    Strictness modes:
    * ``lenient`` -- regression predicted-violations are downgraded to warnings.
    * ``default`` -- regression predicted-violations block execution.
    * ``strict`` -- any warning blocks execution.
    """
    if strictness not in STRICTNESS_MODES:
        raise ValueError(
            f"strictness must be one of {STRICTNESS_MODES}; got {strictness!r}"
        )

    path = Path(package_path)
    evidence, evidence_warnings = _read_evidence(path)

    checks: list[dict[str, Any]] = []
    shape_check = _check_proposal_shape(proposal)
    checks.append(shape_check)

    if shape_check["status"] == "fail":
        return {
            "schema_version": VERIFICATION_SCHEMA,
            "ok": False,
            "verdict": "fail",
            "proposal_id": proposal.get("proposal_id") if isinstance(proposal, dict) else None,
            "feature_ref": proposal.get("feature_ref") if isinstance(proposal, dict) else None,
            "action_type": proposal.get("action_type") if isinstance(proposal, dict) else None,
            "strictness": strictness,
            "checks": checks,
            "blockers": [shape_check],
            "warnings": evidence_warnings,
            "claim_policy": _claim_policy(),
        }

    action_type = proposal.get("action_type")
    feature_id = proposal.get("feature_ref")
    parameter_change = proposal.get("parameter_change") or {}

    feature = _feature_by_id(evidence.get("features"), feature_id)
    stress = _stress_for_feature(evidence.get("stress_by_feature"), feature_id)
    preserved = _preserved_feature_ids(evidence.get("design_targets"))
    min_required_sf = _design_target_min_sf(evidence.get("design_targets"))
    # Fall back to stress_by_feature's minimum_required_safety_factor.
    if min_required_sf is None and isinstance(evidence.get("stress_by_feature"), dict):
        m = evidence["stress_by_feature"].get("minimum_required_safety_factor")
        if isinstance(m, (int, float)):
            min_required_sf = float(m)

    checks.append(_check_action_vocabulary(action_type))
    checks.append(_check_feature_exists(feature_id, feature))
    checks.append(_check_parameter_change(proposal, feature))
    checks.append(_check_preserved_feature(feature_id, preserved))
    checks.append(_check_manufacturability(action_type, parameter_change))
    checks.append(
        _check_regression_thinning_sf(
            action_type=action_type,
            parameter_change=parameter_change,
            feature=feature,
            stress=stress,
            min_required_sf=min_required_sf,
            strictness=strictness,
        )
    )
    checks.append(
        _check_unnecessary_thickening(
            action_type=action_type,
            feature_id=feature_id,
            stress=stress,
            min_required_sf=min_required_sf,
        )
    )

    verdict = _verdict_from_checks(checks, strictness)
    blockers = [c for c in checks if c.get("status") == "fail"]
    warns = [c for c in checks if c.get("status") == "warn"]

    return {
        "schema_version": VERIFICATION_SCHEMA,
        "ok": True,
        "verdict": verdict,
        "proposal_id": proposal.get("proposal_id"),
        "feature_ref": feature_id,
        "action_type": action_type,
        "strictness": strictness,
        "checks": checks,
        "blockers": blockers,
        "warnings_from_checks": warns,
        "warnings": evidence_warnings,
        "claim_policy": _claim_policy(),
    }


def verify_recommendations(
    recommendations: dict[str, Any],
    package_path: str | Path,
    *,
    strictness: str = "default",
) -> dict[str, Any]:
    """Verify every proposal in a Phase 36 recommendations block.

    ``recommendations`` is the dict produced by
    ``cae_recommendation.generate_cad_modification_recommendations``.
    Returns a verdicts-per-proposal block plus an aggregate counter.
    """
    proposals = recommendations.get("proposals") if isinstance(recommendations, dict) else None
    if not isinstance(proposals, list):
        return {
            "schema_version": VERIFICATION_SCHEMA,
            "ok": False,
            "package_path": str(Path(package_path)),
            "strictness": strictness,
            "verdicts": [],
            "summary": {"pass": 0, "warn": 0, "fail": 0, "total": 0},
            "warnings": ["recommendations.proposals is not a list."],
            "claim_policy": _claim_policy(),
        }

    verdicts: list[dict[str, Any]] = []
    for p in proposals:
        verdicts.append(
            verify_cad_modification_proposal(p, package_path, strictness=strictness)
        )

    summary = {
        "pass": sum(1 for v in verdicts if v.get("verdict") == "pass"),
        "warn": sum(1 for v in verdicts if v.get("verdict") == "warn"),
        "fail": sum(1 for v in verdicts if v.get("verdict") == "fail"),
        "total": len(verdicts),
    }
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "ok": True,
        "package_path": str(Path(package_path)),
        "strictness": strictness,
        "verdicts": verdicts,
        "summary": summary,
        "warnings": [],
        "claim_policy": _claim_policy(),
    }


def generate_verification_markdown(verification: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# CAD Modification Verification")
    lines.append("")
    lines.append(
        "Verification is a pre-execution heuristic check. It does not replace "
        "re-simulation. No geometry-kernel checks are performed in this phase."
    )
    lines.append("")
    if "verdicts" in verification:
        s = verification.get("summary", {})
        lines.append(
            f"Strictness: {verification.get('strictness')} -- "
            f"{s.get('total', 0)} proposal(s): {s.get('pass', 0)} pass, "
            f"{s.get('warn', 0)} warn, {s.get('fail', 0)} fail."
        )
        lines.append("")
        for v in verification.get("verdicts", []):
            lines.append(
                f"## [{v.get('verdict', '?').upper()}] "
                f"{v.get('proposal_id', '?')} -- {v.get('feature_ref', '?')} "
                f"({v.get('action_type', '?')})"
            )
            for c in v.get("checks", []):
                lines.append(
                    f"- [{c.get('status', '?')}] {c.get('check_id', '?')}: {c.get('message', '')}"
                )
            lines.append("")
    else:
        v = verification
        lines.append(
            f"## [{v.get('verdict', '?').upper()}] "
            f"{v.get('proposal_id', '?')} -- {v.get('feature_ref', '?')} "
            f"({v.get('action_type', '?')})"
        )
        for c in v.get("checks", []):
            lines.append(
                f"- [{c.get('status', '?')}] {c.get('check_id', '?')}: {c.get('message', '')}"
            )
    lines.append("")
    lines.append("## Boundary")
    lines.append(
        "- Verification surfaces risk; it does not certify physical correctness."
    )
    lines.append(
        "- Re-simulation is required after applying any change before claim advancement."
    )
    lines.append("- The verifier is read-only and never advances claims.")
    return "\n".join(lines)
