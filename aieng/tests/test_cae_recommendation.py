"""Tests for cae_recommendation (Phase 36 — CAD-modification recommendation primitive)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

from aieng.cae_recommendation import (
    MODIFICATION_VOCABULARY,
    RECOMMENDATIONS_SCHEMA,
    generate_cad_modification_recommendations,
    generate_recommendations_markdown,
)


# ---------------------------------------------------------------------------
# Fixture construction (re-uses the benchmark scenario shape directly so the
# recommender is tested against the same artifact contract the agent sees).
# ---------------------------------------------------------------------------


_DESIGN_TARGETS = {
    "format_version": "0.1.1",
    "target_set_id": "recommendation_test_v1",
    "targets": [
        {
            "target_id": "mass_reduce_10pct",
            "target_type": "mass_reduction_target",
            "comparator": "reduce_by_at_least",
            "threshold": 10.0,
            "priority": "high",
        },
        {
            "target_id": "safety_factor_min",
            "target_type": "minimum_safety_factor",
            "comparator": ">=",
            "threshold": 1.5,
            "priority": "critical",
        },
    ],
    "claim_policy": {
        "targets_are_acceptance_criteria": True,
        "compliance_requires_evidence": True,
        "physical_correctness_not_claimed": True,
    },
}


_FEATURES = {
    "features": [
        {
            "id": "back_wall",
            "kind": "wall",
            "parameters": {"thickness_mm": 20.0, "width_mm": 120.0, "height_mm": 80.0},
            "mass_contribution_kg": 1.51,
        },
        {
            "id": "central_rib",
            "kind": "rib",
            "parameters": {"thickness_mm": 8.0, "length_mm": 100.0},
            "mass_contribution_kg": 0.38,
        },
        {
            "id": "mounting_hole",
            "kind": "hole",
            "parameters": {"diameter_mm": 10.0, "depth_mm": 20.0},
            "mass_contribution_kg": -0.012,
        },
        {
            "id": "mounting_bosses",
            "kind": "boss_group",
            "parameters": {"count": 4, "diameter_mm": 14.0, "height_mm": 8.0},
            "mass_contribution_kg": 0.09,
        },
        {
            "id": "flange",
            "kind": "flange",
            "parameters": {"thickness_mm": 12.0, "width_mm": 80.0},
            "mass_contribution_kg": 0.24,
        },
    ],
}


_STRESS_BY_FEATURE = {
    "schema_version": "0.1",
    "load_case_id": "load_case_001",
    "yield_strength_mpa": 350.0,
    "minimum_required_safety_factor": 1.5,
    "max_allowable_stress_mpa": 233.0,
    "features": [
        {"feature_ref": "back_wall", "max_von_mises_stress_mpa": 22.0, "safety_factor": 15.91},
        {"feature_ref": "central_rib", "max_von_mises_stress_mpa": 195.0, "safety_factor": 1.79},
        {"feature_ref": "mounting_hole", "max_von_mises_stress_mpa": 195.0, "safety_factor": 1.79},
        {"feature_ref": "mounting_bosses", "max_von_mises_stress_mpa": 48.0, "safety_factor": 7.29},
        {"feature_ref": "flange", "max_von_mises_stress_mpa": 110.0, "safety_factor": 3.18},
    ],
}


_COMPUTED_METRICS = {
    "schema_version": "0.1",
    "metrics_source": {"tool": "external_postprocessor", "software": "CalculiX"},
    "load_cases": [
        {
            "id": "load_case_001",
            "metrics": {
                "max_von_mises_stress": {"value": 195.0, "unit": "MPa"},
                "minimum_safety_factor": {"value": 1.79},
                "total_mass": {"value": 2.30, "unit": "kg"},
            },
        }
    ],
}


def _build_package(
    tmp_path: Path,
    *,
    include_design_targets: bool = True,
    include_features: bool = True,
    include_stress: bool = True,
    include_metrics: bool = True,
    extra_design_targets: list[dict] | None = None,
    override_min_sf_in_metrics: float | None = None,
) -> Path:
    pkg = tmp_path / "rec.aieng"
    targets = json.loads(json.dumps(_DESIGN_TARGETS))
    if extra_design_targets:
        targets["targets"].extend(extra_design_targets)
    metrics = json.loads(json.dumps(_COMPUTED_METRICS))
    if override_min_sf_in_metrics is not None:
        metrics["load_cases"][0]["metrics"]["minimum_safety_factor"]["value"] = (
            override_min_sf_in_metrics
        )
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "rec_test", "resources": {}}))
        if include_design_targets:
            zf.writestr("task/design_targets.yaml", yaml.safe_dump(targets, sort_keys=False))
        if include_features:
            zf.writestr(
                "simulation/cae_imports/parsed_features.json", json.dumps(_FEATURES)
            )
        if include_stress:
            zf.writestr("results/stress_by_feature.json", json.dumps(_STRESS_BY_FEATURE))
        if include_metrics:
            zf.writestr("results/computed_metrics.json", json.dumps(metrics))
    return pkg


# ---------------------------------------------------------------------------
# Schema + happy path
# ---------------------------------------------------------------------------


def test_schema_and_vocabulary_constants() -> None:
    assert RECOMMENDATIONS_SCHEMA == "0.1"
    assert "thin" in MODIFICATION_VOCABULARY
    assert "thicken" in MODIFICATION_VOCABULARY
    assert "add_fillet" in MODIFICATION_VOCABULARY
    assert "resize_hole" in MODIFICATION_VOCABULARY


def test_ranked_mass_reduction_top_pick_is_back_wall(tmp_path: Path) -> None:
    """The fixture is engineered so back_wall (SF=15.9, mass=1.51 kg) dominates."""
    pkg = _build_package(tmp_path)
    result = generate_cad_modification_recommendations(pkg)

    assert result["ok"] is True
    assert result["schema_version"] == "0.1"
    assert result["claim_policy"]["proposals_are_hypotheses"] is True
    assert result["claim_policy"]["requires_verification_simulation"] is True
    assert result["claim_policy"]["claims_advanced"] is False

    proposals = result["proposals"]
    assert proposals, "expected at least one proposal"
    top = proposals[0]
    assert top["rank"] == 1
    assert top["feature_ref"] == "back_wall"
    assert top["action_type"] == "thin"
    change = top["parameter_change"]
    assert change["name"] == "thickness_mm"
    assert change["from"] == 20.0
    assert change["to"] == 10.0
    assert top["confidence"] == "high"
    assert "mass_reduce_10pct" in top["targets_addressed"]


def test_low_safety_margin_features_not_proposed_for_thinning(tmp_path: Path) -> None:
    """central_rib and mounting_hole sit at SF=1.79 vs floor=1.5 (ratio<1.2).

    The recommender must refuse to propose thinning either of them, because
    the residual margin is too thin for a heuristic action.
    """
    pkg = _build_package(tmp_path)
    result = generate_cad_modification_recommendations(pkg)

    thin_targets = {
        p["feature_ref"] for p in result["proposals"] if p["action_type"] == "thin"
    }
    assert "central_rib" not in thin_targets
    # mounting_hole is a hole, not a thickness feature; also must not appear
    # as a mass-reduction proposal (negative mass).
    assert "mounting_hole" not in thin_targets


def test_holes_excluded_from_mass_reduction(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    result = generate_cad_modification_recommendations(pkg)
    # mounting_hole has mass_contribution = -0.012; it must be skipped.
    skipped_ids = {s["feature_ref"] for s in result["skipped_features"]}
    assert "mounting_hole" in skipped_ids


def test_preserved_features_are_skipped(tmp_path: Path) -> None:
    """A protected feature in design_targets must never appear in proposals."""
    preserved_target = {
        "target_id": "preserve_flange",
        "target_type": "preserved_interface",
        "comparator": "preserve",
        "priority": "critical",
        "protected_features": [{"feature_id": "flange", "feature_type": "flange"}],
    }
    pkg = _build_package(tmp_path, extra_design_targets=[preserved_target])
    result = generate_cad_modification_recommendations(pkg)

    proposed_ids = {p["feature_ref"] for p in result["proposals"]}
    assert "flange" not in proposed_ids
    assert "flange" in result["evidence"]["preserved_feature_ids"]
    skipped = result["skipped_features"]
    assert any(s["feature_ref"] == "flange" and s["reason"] == "preserved_interface" for s in skipped)


def test_stress_rescue_triggers_when_current_sf_below_floor(tmp_path: Path) -> None:
    """When computed minimum_safety_factor is below the design floor, the
    recommender must add stress-rescue proposals for the lowest-SF features."""
    pkg = _build_package(tmp_path, override_min_sf_in_metrics=1.3)
    result = generate_cad_modification_recommendations(pkg)

    actions = {p["action_type"] for p in result["proposals"]}
    assert "thicken" in actions or "add_fillet" in actions, (
        f"expected stress-rescue action; got {actions}"
    )


# ---------------------------------------------------------------------------
# Honesty boundaries
# ---------------------------------------------------------------------------


def test_package_is_not_mutated(tmp_path: Path) -> None:
    """Pure read-only check: byte-identical package before and after."""
    pkg = _build_package(tmp_path)
    before = pkg.read_bytes()
    _ = generate_cad_modification_recommendations(pkg)
    after = pkg.read_bytes()
    assert before == after


def test_missing_inputs_surface_as_warnings_not_exceptions(tmp_path: Path) -> None:
    pkg = _build_package(
        tmp_path,
        include_design_targets=False,
        include_stress=False,
    )
    result = generate_cad_modification_recommendations(pkg)
    assert result["ok"] is False
    assert result["proposals"] == []
    # Both missing inputs should be reported.
    joined = "\n".join(result["warnings"])
    assert "design_targets.yaml" in joined
    assert "stress_by_feature.json" in joined


def test_missing_package_returns_warning_not_raise(tmp_path: Path) -> None:
    result = generate_cad_modification_recommendations(tmp_path / "does_not_exist.aieng")
    assert result["ok"] is False
    assert any("Package not found" in w for w in result["warnings"])


def test_markdown_includes_boundary_and_proposals(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    result = generate_cad_modification_recommendations(pkg)
    md = generate_recommendations_markdown(result)
    assert "# CAD Modification Recommendations" in md
    assert "back_wall" in md
    assert "Boundary" in md
    assert "verification" in md.lower()


def test_directory_form_package_supported(tmp_path: Path) -> None:
    """The recommender must accept directory-form packages as well as zipped ones."""
    pkg_dir = tmp_path / "rec_dir"
    (pkg_dir / "task").mkdir(parents=True)
    (pkg_dir / "results").mkdir(parents=True)
    (pkg_dir / "simulation" / "cae_imports").mkdir(parents=True)

    (pkg_dir / "task" / "design_targets.yaml").write_text(
        yaml.safe_dump(_DESIGN_TARGETS, sort_keys=False), encoding="utf-8"
    )
    (pkg_dir / "simulation" / "cae_imports" / "parsed_features.json").write_text(
        json.dumps(_FEATURES), encoding="utf-8"
    )
    (pkg_dir / "results" / "stress_by_feature.json").write_text(
        json.dumps(_STRESS_BY_FEATURE), encoding="utf-8"
    )
    (pkg_dir / "results" / "computed_metrics.json").write_text(
        json.dumps(_COMPUTED_METRICS), encoding="utf-8"
    )

    result = generate_cad_modification_recommendations(pkg_dir)
    assert result["ok"] is True
    assert result["proposals"], "expected proposals from directory-form package"


def test_no_unsupported_action_types_emitted(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path, override_min_sf_in_metrics=1.2)
    result = generate_cad_modification_recommendations(pkg)
    for p in result["proposals"]:
        assert p["action_type"] in MODIFICATION_VOCABULARY


def test_llm_summary_present_with_honest_limitations(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    result = generate_cad_modification_recommendations(pkg)
    s = result["llm_summary"]
    assert s["one_line"]
    assert any("vocabulary" in lim.lower() for lim in s["limitations"])
    assert any("re-simulation" in r.lower() or "verify" in r.lower() for r in s["risks"])
