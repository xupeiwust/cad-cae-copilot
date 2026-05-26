"""CAD-modification recommendation primitive for .aieng packages (Phase 36).

Reads design targets, computed metrics, per-feature stress, and parsed
features from a ``.aieng`` package and emits a ranked list of CAD
modification proposals.

Boundary rules (Phase 36 honesty):

* Recommendations are *hypotheses*, never evidence. Acceptance requires
  re-running the simulation pipeline (Phase 37+ verification gate).
* The module is read-only: it never mutates the package, never advances
  ``claim_map.json``, and never executes CAD/CAE operations.
* No physical-correctness claim is made -- the rules are heuristics over
  artifact-level evidence, not solver predictions.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import yaml


__all__ = [
    "RECOMMENDATIONS_SCHEMA",
    "MODIFICATION_VOCABULARY",
    "generate_cad_modification_recommendations",
    "generate_recommendations_markdown",
]


RECOMMENDATIONS_SCHEMA = "0.1"

MODIFICATION_VOCABULARY: tuple[str, ...] = (
    "thin",
    "thicken",
    "add_fillet",
    "resize_hole",
    "remove",
    "reduce_count",
)

# Feature kinds whose dominant tunable parameter is a thickness -- for
# mass-reduction we propose ``thin``, for stress-rescue we propose
# ``thicken``. Holes and boss groups are handled separately.
_THICKNESS_KINDS: frozenset[str] = frozenset({"wall", "rib", "gusset", "flange", "plate"})


def _read_yaml_member(zf: zipfile.ZipFile, name: str) -> Any | None:
    if name not in zf.namelist():
        return None
    try:
        with zf.open(name) as fh:
            return yaml.safe_load(fh)
    except Exception:
        return None


def _read_json_member(zf: zipfile.ZipFile, name: str) -> Any | None:
    if name not in zf.namelist():
        return None
    try:
        with zf.open(name) as fh:
            return json.load(fh)
    except Exception:
        return None


def _read_inputs(package_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Read the four input artifacts; missing files surface as warnings."""
    warnings: list[str] = []
    inputs: dict[str, Any] = {
        "design_targets": None,
        "computed_metrics": None,
        "stress_by_feature": None,
        "features": None,
    }

    if not package_path.exists():
        warnings.append(f"Package not found: {package_path}")
        return inputs, warnings

    if package_path.is_dir():
        candidates = {
            "design_targets": package_path / "task" / "design_targets.yaml",
            "computed_metrics": package_path / "results" / "computed_metrics.json",
            "stress_by_feature": package_path / "results" / "stress_by_feature.json",
            "features": package_path / "simulation" / "cae_imports" / "parsed_features.json",
        }
        for key, path in candidates.items():
            if not path.exists():
                warnings.append(f"Missing input: {path.relative_to(package_path)}")
                continue
            try:
                if path.suffix == ".yaml":
                    inputs[key] = yaml.safe_load(path.read_text(encoding="utf-8"))
                else:
                    inputs[key] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                warnings.append(f"Failed to parse {path.name}: {type(exc).__name__}: {exc}")
        return inputs, warnings

    if package_path.suffix != ".aieng":
        warnings.append(f"Package path is neither a directory nor a .aieng file: {package_path}")
        return inputs, warnings

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            members = {
                "design_targets": "task/design_targets.yaml",
                "computed_metrics": "results/computed_metrics.json",
                "stress_by_feature": "results/stress_by_feature.json",
                "features": "simulation/cae_imports/parsed_features.json",
            }
            for key, member in members.items():
                if member not in zf.namelist():
                    warnings.append(f"Missing input: {member}")
                    continue
                if member.endswith(".yaml"):
                    inputs[key] = _read_yaml_member(zf, member)
                else:
                    inputs[key] = _read_json_member(zf, member)
                if inputs[key] is None:
                    warnings.append(f"Failed to parse {member}")
    except zipfile.BadZipFile as exc:
        warnings.append(f"Malformed .aieng zip: {exc}")

    return inputs, warnings


def _classify_targets(design_targets: Any) -> dict[str, Any]:
    """Split targets into the four families the recommender understands."""
    out: dict[str, Any] = {
        "mass_reduction": [],
        "stress_limit": [],
        "safety_floor": [],
        "preserved_feature_ids": set(),
        "all_target_ids": [],
        "min_required_sf": None,
        "max_allowable_stress": None,
    }
    if not isinstance(design_targets, dict):
        return out

    for raw in design_targets.get("targets") or []:
        if not isinstance(raw, dict):
            continue
        tid = raw.get("target_id") or raw.get("id")
        if tid:
            out["all_target_ids"].append(tid)
        ttype = raw.get("target_type") or raw.get("metric")
        threshold = raw.get("threshold")
        if threshold is None:
            threshold = raw.get("value")
        priority = raw.get("priority")
        entry = {
            "target_id": tid,
            "target_type": ttype,
            "threshold": threshold,
            "priority": priority,
        }
        if ttype in ("mass_reduction_target", "mass_reduction_percent"):
            out["mass_reduction"].append(entry)
        elif ttype in ("maximum_von_mises_stress", "max_von_mises_stress"):
            out["stress_limit"].append(entry)
            if isinstance(threshold, (int, float)):
                cur = out["max_allowable_stress"]
                if cur is None or threshold < cur:
                    out["max_allowable_stress"] = float(threshold)
        elif ttype in ("minimum_safety_factor",):
            out["safety_floor"].append(entry)
            if isinstance(threshold, (int, float)):
                cur = out["min_required_sf"]
                if cur is None or threshold > cur:
                    out["min_required_sf"] = float(threshold)
        elif ttype in ("preserved_interface", "preserved_feature"):
            for prot in raw.get("protected_features") or []:
                if isinstance(prot, dict):
                    fid = prot.get("feature_id")
                    if fid:
                        out["preserved_feature_ids"].add(fid)
                elif isinstance(prot, str):
                    out["preserved_feature_ids"].add(prot)
    return out


def _feature_index(features: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(features, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for f in features.get("features") or []:
        if isinstance(f, dict) and f.get("id"):
            out[f["id"]] = f
    return out


def _stress_index(stress_by_feature: Any) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {}
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(stress_by_feature, dict):
        return out, meta
    meta = {
        "yield_strength_mpa": stress_by_feature.get("yield_strength_mpa"),
        "minimum_required_safety_factor": stress_by_feature.get("minimum_required_safety_factor"),
        "max_allowable_stress_mpa": stress_by_feature.get("max_allowable_stress_mpa"),
    }
    for s in stress_by_feature.get("features") or []:
        if isinstance(s, dict) and s.get("feature_ref"):
            out[s["feature_ref"]] = s
    return out, meta


def _sf_ratio(safety_factor: float | None, min_sf: float | None) -> float | None:
    if not isinstance(safety_factor, (int, float)) or not isinstance(min_sf, (int, float)) or min_sf <= 0:
        return None
    return float(safety_factor) / float(min_sf)


def _confidence_from_margin(sf_ratio: float | None) -> str:
    if sf_ratio is None:
        return "low"
    if sf_ratio >= 5.0:
        return "high"
    if sf_ratio >= 2.0:
        return "medium"
    return "low"


def _propose_mass_reduction(
    *,
    feature_id: str,
    feature: dict[str, Any],
    stress: dict[str, Any] | None,
    min_sf: float | None,
    targets_addressed: list[str],
    proposal_idx: int,
) -> dict[str, Any] | None:
    """Propose a mass-reduction modification for a single feature.

    Returns None if the feature kind is not supported, or if the safety
    margin is too thin to recommend any reduction.
    """
    kind = (feature.get("kind") or "").lower()
    mass = feature.get("mass_contribution_kg")
    params = feature.get("parameters") or {}
    sf = stress.get("safety_factor") if isinstance(stress, dict) else None
    sf_ratio = _sf_ratio(sf, min_sf)

    # Refuse to recommend reductions on features already near the SF floor.
    if sf_ratio is not None and sf_ratio < 1.2:
        return None

    confidence = _confidence_from_margin(sf_ratio)
    rationale_bits: list[str] = []
    if isinstance(sf, (int, float)):
        rationale_bits.append(f"SF={sf:.2f}")
    if isinstance(min_sf, (int, float)):
        rationale_bits.append(f"required_min_SF={min_sf}")
    if isinstance(mass, (int, float)):
        rationale_bits.append(f"mass_contribution={mass:.3f} kg")

    proposal_id = f"p_{proposal_idx:03d}"
    base: dict[str, Any] = {
        "proposal_id": proposal_id,
        "feature_ref": feature_id,
        "confidence": confidence,
        "targets_addressed": targets_addressed,
        "rationale": ", ".join(rationale_bits) if rationale_bits else "evidence-incomplete",
        "risks": [],
    }

    if kind in _THICKNESS_KINDS:
        thickness = params.get("thickness_mm")
        if not isinstance(thickness, (int, float)) or thickness <= 0:
            return None
        new_thickness = round(float(thickness) / 2.0, 3)
        # Heuristic risk note for thin-walled stress redistribution.
        risks = []
        if sf_ratio is not None and sf_ratio < 2.5:
            risks.append(
                "Thinning may push the feature's SF below the floor; "
                "verify by re-simulation before accepting."
            )
        base.update(
            {
                "action_type": "thin",
                "parameter_change": {
                    "name": "thickness_mm",
                    "from": float(thickness),
                    "to": new_thickness,
                },
                "expected_impact": (
                    f"Approximately halves the mass contribution of {feature_id} "
                    f"(~ {mass / 2:.3f} kg saved)"
                    if isinstance(mass, (int, float))
                    else "Reduces feature mass; magnitude unknown without re-simulation"
                ),
                "risks": risks,
            }
        )
        return base

    if kind == "boss_group":
        count = params.get("count")
        if not isinstance(count, int) or count < 4:
            return None
        new_count = max(2, count // 2)
        base.update(
            {
                "action_type": "reduce_count",
                "parameter_change": {
                    "name": "count",
                    "from": count,
                    "to": new_count,
                },
                "expected_impact": (
                    f"Halves boss count (~ {(mass or 0) / 2:.3f} kg saved); "
                    "compromises mounting redundancy"
                ),
                "risks": [
                    "Reducing mounting bosses changes the bolted-interface "
                    "load distribution; must be verified by re-simulation."
                ],
                "confidence": "low",
            }
        )
        return base

    # Holes contribute negative mass -- not useful for mass-reduction.
    return None


def _propose_stress_rescue(
    *,
    feature_id: str,
    feature: dict[str, Any],
    stress: dict[str, Any] | None,
    proposal_idx: int,
    targets_addressed: list[str],
) -> dict[str, Any] | None:
    """Propose a stress-rescue modification when SF is near or below the floor."""
    kind = (feature.get("kind") or "").lower()
    params = feature.get("parameters") or {}
    sf = stress.get("safety_factor") if isinstance(stress, dict) else None
    max_stress = stress.get("max_von_mises_stress_mpa") if isinstance(stress, dict) else None

    proposal_id = f"p_{proposal_idx:03d}"
    rationale_bits: list[str] = []
    if isinstance(sf, (int, float)):
        rationale_bits.append(f"SF={sf:.2f}")
    if isinstance(max_stress, (int, float)):
        rationale_bits.append(f"max_stress={max_stress} MPa")

    base: dict[str, Any] = {
        "proposal_id": proposal_id,
        "feature_ref": feature_id,
        "confidence": "medium",
        "targets_addressed": targets_addressed,
        "rationale": ", ".join(rationale_bits) if rationale_bits else "evidence-incomplete",
        "risks": [
            "Stress-rescue magnitude is a heuristic; re-simulate to confirm "
            "the change brings SF above the required floor."
        ],
    }

    if kind in _THICKNESS_KINDS:
        thickness = params.get("thickness_mm")
        if not isinstance(thickness, (int, float)) or thickness <= 0:
            return None
        new_thickness = round(float(thickness) * 1.5, 3)
        base.update(
            {
                "action_type": "thicken",
                "parameter_change": {
                    "name": "thickness_mm",
                    "from": float(thickness),
                    "to": new_thickness,
                },
                "expected_impact": (
                    f"Increases bending stiffness of {feature_id}; "
                    "typically reduces max stress in the load path"
                ),
            }
        )
        return base

    if kind == "hole":
        diameter = params.get("diameter_mm")
        if not isinstance(diameter, (int, float)) or diameter <= 0:
            return None
        base.update(
            {
                "action_type": "add_fillet",
                "parameter_change": {
                    "name": "fillet_radius_mm",
                    "from": 0.0,
                    "to": round(float(diameter) * 0.1, 3),
                },
                "expected_impact": (
                    "Filleting the hole boundary typically reduces the local "
                    "stress concentration factor"
                ),
            }
        )
        return base

    return None


def _build_evidence_block(
    inputs: dict[str, Any],
    classified: dict[str, Any],
    feature_idx: dict[str, dict[str, Any]],
    stress_idx: dict[str, dict[str, Any]],
    stress_meta: dict[str, Any],
) -> dict[str, Any]:
    cm = inputs.get("computed_metrics") or {}
    cm_load_cases = cm.get("load_cases") if isinstance(cm, dict) else None
    current_metrics: dict[str, Any] = {}
    if isinstance(cm_load_cases, list) and cm_load_cases:
        first = cm_load_cases[0]
        if isinstance(first, dict):
            current_metrics = first.get("metrics") or {}
    return {
        "has_design_targets": inputs.get("design_targets") is not None,
        "has_computed_metrics": inputs.get("computed_metrics") is not None,
        "has_stress_by_feature": inputs.get("stress_by_feature") is not None,
        "has_parsed_features": inputs.get("features") is not None,
        "feature_count": len(feature_idx),
        "stress_record_count": len(stress_idx),
        "all_target_ids": list(classified.get("all_target_ids", [])),
        "min_required_safety_factor": classified.get("min_required_sf"),
        "max_allowable_stress_mpa": classified.get("max_allowable_stress")
            or stress_meta.get("max_allowable_stress_mpa"),
        "preserved_feature_ids": sorted(classified.get("preserved_feature_ids", set())),
        "current_metrics": current_metrics,
    }


def _llm_summary(
    proposals: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    one_line = (
        f"{len(proposals)} CAD modification candidate(s) proposed; "
        "verification by re-simulation required before acceptance."
    )
    key_findings = [
        f"Top proposal: {proposals[0]['feature_ref']} "
        f"({proposals[0]['action_type']}, confidence={proposals[0]['confidence']})"
    ] if proposals else ["No CAD modifications proposed under the current evidence."]
    risks = [
        "Proposals are evidence-grounded hypotheses, not solver predictions.",
        "Re-simulation is required to confirm that any proposal satisfies the targets.",
    ]
    limitations = [
        "Modification vocabulary is limited to: " + ", ".join(MODIFICATION_VOCABULARY),
        "No CAD execution, no claim advancement, no physical-correctness claim.",
    ]
    if skipped:
        limitations.append(f"{len(skipped)} feature(s) skipped (preserved or non-actionable).")
    if warnings:
        limitations.append(f"{len(warnings)} input warning(s) -- see warnings list.")
    return {
        "one_line": one_line,
        "key_findings": key_findings,
        "risks": risks,
        "limitations": limitations,
    }


def generate_cad_modification_recommendations(
    package_path: str | Path,
) -> dict[str, Any]:
    """Generate a ranked list of CAD modification proposals.

    Reads ``task/design_targets.yaml``, ``results/computed_metrics.json``,
    ``results/stress_by_feature.json``, and ``simulation/cae_imports/parsed_features.json``
    from a ``.aieng`` package (zipped or directory form). Returns a structured
    proposals block with rank, action_type, parameter_change, rationale,
    expected_impact, confidence, targets_addressed, and risks.

    The function is read-only. It never writes to the package, never advances
    ``claim_map.json``, and never executes CAD/CAE operations.
    """
    path = Path(package_path)
    inputs, warnings = _read_inputs(path)

    classified = _classify_targets(inputs.get("design_targets"))
    feature_idx = _feature_index(inputs.get("features"))
    stress_idx, stress_meta = _stress_index(inputs.get("stress_by_feature"))

    # Use the stress_by_feature minimum_required_safety_factor if design targets
    # don't carry one; design targets win when both are present.
    min_sf = classified.get("min_required_sf") or stress_meta.get("minimum_required_safety_factor")
    preserved = classified.get("preserved_feature_ids", set())

    # Resolve current safety state from computed metrics if available.
    current_min_sf: float | None = None
    cm = inputs.get("computed_metrics") or {}
    if isinstance(cm, dict):
        for lc in cm.get("load_cases") or []:
            if not isinstance(lc, dict):
                continue
            sf_metric = (lc.get("metrics") or {}).get("minimum_safety_factor")
            if isinstance(sf_metric, dict):
                val = sf_metric.get("value")
                if isinstance(val, (int, float)):
                    current_min_sf = float(val)
                    break

    wants_mass_reduction = bool(classified.get("mass_reduction"))
    wants_stress_rescue = (
        bool(classified.get("stress_limit") or classified.get("safety_floor"))
        and isinstance(current_min_sf, (int, float))
        and isinstance(min_sf, (int, float))
        and current_min_sf < min_sf
    )

    mass_target_ids = [t["target_id"] for t in classified.get("mass_reduction", []) if t.get("target_id")]
    sf_target_ids = [t["target_id"] for t in classified.get("safety_floor", []) if t.get("target_id")]
    stress_target_ids = [t["target_id"] for t in classified.get("stress_limit", []) if t.get("target_id")]
    rescue_target_ids = sf_target_ids + stress_target_ids

    proposals: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    proposal_idx = 1

    if wants_mass_reduction:
        # Rank features by (safety_factor / min_sf) * mass_contribution.
        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for fid, feat in feature_idx.items():
            if fid in preserved:
                skipped.append({"feature_ref": fid, "reason": "preserved_interface"})
                continue
            stress = stress_idx.get(fid)
            sf = stress.get("safety_factor") if isinstance(stress, dict) else None
            mass = feat.get("mass_contribution_kg")
            if not isinstance(mass, (int, float)) or mass <= 0:
                # Holes contribute negative mass; skip from mass-reduction list.
                if isinstance(mass, (int, float)) and mass <= 0:
                    skipped.append({"feature_ref": fid, "reason": "non_positive_mass"})
                else:
                    skipped.append({"feature_ref": fid, "reason": "no_mass_data"})
                continue
            sf_ratio = _sf_ratio(sf, min_sf) or 0.0
            score = sf_ratio * float(mass)
            ranked.append((score, fid, feat))
        ranked.sort(key=lambda t: t[0], reverse=True)

        for _, fid, feat in ranked:
            proposal = _propose_mass_reduction(
                feature_id=fid,
                feature=feat,
                stress=stress_idx.get(fid),
                min_sf=min_sf if isinstance(min_sf, (int, float)) else None,
                targets_addressed=list(mass_target_ids),
                proposal_idx=proposal_idx,
            )
            if proposal is not None:
                proposals.append(proposal)
                proposal_idx += 1
            else:
                skipped.append({"feature_ref": fid, "reason": "not_actionable_for_mass_reduction"})

    if wants_stress_rescue:
        # Rank features by lowest SF first.
        ranked_stress: list[tuple[float, str, dict[str, Any]]] = []
        for fid, feat in feature_idx.items():
            if fid in preserved:
                continue
            stress = stress_idx.get(fid)
            sf = stress.get("safety_factor") if isinstance(stress, dict) else None
            if not isinstance(sf, (int, float)):
                continue
            ranked_stress.append((sf, fid, feat))
        ranked_stress.sort(key=lambda t: t[0])

        for _, fid, feat in ranked_stress[:3]:
            proposal = _propose_stress_rescue(
                feature_id=fid,
                feature=feat,
                stress=stress_idx.get(fid),
                proposal_idx=proposal_idx,
                targets_addressed=list(rescue_target_ids),
            )
            if proposal is not None:
                proposals.append(proposal)
                proposal_idx += 1

    for i, p in enumerate(proposals, start=1):
        p["rank"] = i

    evidence = _build_evidence_block(inputs, classified, feature_idx, stress_idx, stress_meta)

    ok = (
        evidence["has_design_targets"]
        and evidence["has_stress_by_feature"]
        and evidence["has_parsed_features"]
    )

    return {
        "schema_version": RECOMMENDATIONS_SCHEMA,
        "ok": ok,
        "package_path": str(path),
        "modification_vocabulary": list(MODIFICATION_VOCABULARY),
        "evidence": evidence,
        "proposals": proposals,
        "skipped_features": skipped,
        "warnings": warnings,
        "llm_summary": _llm_summary(proposals, skipped, warnings),
        "claim_policy": {
            "proposals_are_hypotheses": True,
            "requires_verification_simulation": True,
            "physical_correctness_not_claimed": True,
            "claims_advanced": False,
        },
    }


def generate_recommendations_markdown(recommendations: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# CAD Modification Recommendations")
    lines.append("")
    lines.append(
        "Proposals below are evidence-grounded hypotheses derived from design "
        "targets, computed metrics, and per-feature stress. They require "
        "verification by re-simulation before acceptance -- no physical "
        "correctness is claimed."
    )
    lines.append("")
    evidence = recommendations.get("evidence", {})
    if evidence:
        lines.append("## Evidence inputs")
        for key in (
            "has_design_targets",
            "has_computed_metrics",
            "has_stress_by_feature",
            "has_parsed_features",
        ):
            lines.append(f"- {key}: {evidence.get(key, False)}")
        if evidence.get("preserved_feature_ids"):
            lines.append(f"- preserved_feature_ids: {evidence['preserved_feature_ids']}")
        lines.append("")

    proposals = recommendations.get("proposals", [])
    if proposals:
        lines.append(f"## Proposals ({len(proposals)})")
        for p in proposals:
            lines.append("")
            lines.append(
                f"### {p.get('rank', '?')}. {p.get('feature_ref', '?')} -- "
                f"{p.get('action_type', '?')} (confidence={p.get('confidence', '?')})"
            )
            change = p.get("parameter_change") or {}
            if change:
                lines.append(
                    f"- parameter_change: {change.get('name')} {change.get('from')} -> {change.get('to')}"
                )
            if p.get("rationale"):
                lines.append(f"- rationale: {p['rationale']}")
            if p.get("expected_impact"):
                lines.append(f"- expected_impact: {p['expected_impact']}")
            if p.get("targets_addressed"):
                lines.append(f"- targets_addressed: {p['targets_addressed']}")
            for r in p.get("risks") or []:
                lines.append(f"- risk: {r}")
    else:
        lines.append("## Proposals")
        lines.append("- _No CAD modification proposals under the current evidence._")

    skipped = recommendations.get("skipped_features", [])
    if skipped:
        lines.append("")
        lines.append("## Skipped features")
        for s in skipped:
            lines.append(f"- {s.get('feature_ref')}: {s.get('reason')}")

    warnings = recommendations.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w}")

    lines.append("")
    lines.append("## Boundary")
    lines.append(
        "- Proposals are hypotheses, not evidence. Verification requires "
        "re-running the simulation pipeline (Phase 37+ verification gate)."
    )
    lines.append("- The recommender does not mutate the package or advance claims.")

    return "\n".join(lines)
