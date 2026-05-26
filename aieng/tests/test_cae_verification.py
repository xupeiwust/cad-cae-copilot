"""Tests for cae_verification (Phase 37 -- verification gate)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

from aieng.cae_recommendation import generate_cad_modification_recommendations
from aieng.cae_verification import (
    MANUFACTURABILITY_FLOORS,
    STRICTNESS_MODES,
    VERIFICATION_SCHEMA,
    generate_verification_markdown,
    verify_cad_modification_proposal,
    verify_recommendations,
)


_DESIGN_TARGETS = {
    "format_version": "0.1.1",
    "target_set_id": "verification_test_v1",
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
    extra_design_targets: list[dict] | None = None,
) -> Path:
    pkg = tmp_path / "verify.aieng"
    targets = json.loads(json.dumps(_DESIGN_TARGETS))
    if extra_design_targets:
        targets["targets"].extend(extra_design_targets)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "verify_test", "resources": {}}))
        zf.writestr("task/design_targets.yaml", yaml.safe_dump(targets, sort_keys=False))
        zf.writestr(
            "simulation/cae_imports/parsed_features.json", json.dumps(_FEATURES)
        )
        zf.writestr("results/stress_by_feature.json", json.dumps(_STRESS_BY_FEATURE))
        zf.writestr("results/computed_metrics.json", json.dumps(_COMPUTED_METRICS))
    return pkg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_schema_and_strictness_constants() -> None:
    assert VERIFICATION_SCHEMA == "0.1"
    assert "lenient" in STRICTNESS_MODES
    assert "default" in STRICTNESS_MODES
    assert "strict" in STRICTNESS_MODES
    assert MANUFACTURABILITY_FLOORS["thickness_mm"] == 1.0


# ---------------------------------------------------------------------------
# Schema-level checks (failures must block execution)
# ---------------------------------------------------------------------------


def test_unknown_action_type_blocks(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_001",
        "feature_ref": "back_wall",
        "action_type": "warp_into_eldritch_horror",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "fail"
    assert any(c["check_id"] == "schema.action_in_vocabulary" and c["status"] == "fail"
               for c in v["checks"])


def test_unknown_feature_ref_blocks(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_002",
        "feature_ref": "nonexistent_feature",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 10.0, "to": 5.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "fail"
    assert any(c["check_id"] == "schema.feature_exists" and c["status"] == "fail"
               for c in v["checks"])


def test_parameter_not_on_feature_blocks(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_003",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "wing_count", "from": 0, "to": 2},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "fail"
    assert any(c["check_id"] == "schema.parameter_change" and c["status"] == "fail"
               for c in v["checks"])


def test_missing_parameter_change_blocks(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {"proposal_id": "p_004", "feature_ref": "back_wall", "action_type": "thin"}
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "fail"


def test_malformed_proposal_blocks_and_returns_early(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    v = verify_cad_modification_proposal("not-a-dict", pkg)
    assert v["verdict"] == "fail"
    # Only the shape check should appear.
    assert all(c["check_id"] == "schema.proposal_shape" for c in v["checks"])


# ---------------------------------------------------------------------------
# Preserved-feature check
# ---------------------------------------------------------------------------


def test_preserved_feature_modification_blocks(tmp_path: Path) -> None:
    preserved_target = {
        "target_id": "preserve_flange",
        "target_type": "preserved_interface",
        "comparator": "preserve",
        "priority": "critical",
        "protected_features": [{"feature_id": "flange", "feature_type": "flange"}],
    }
    pkg = _build_package(tmp_path, extra_design_targets=[preserved_target])
    proposal = {
        "proposal_id": "p_010",
        "feature_ref": "flange",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 12.0, "to": 6.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "fail"
    blocker_ids = {c["check_id"] for c in v["blockers"]}
    assert "schema.preserved_feature_not_modified" in blocker_ids


# ---------------------------------------------------------------------------
# Manufacturability floor
# ---------------------------------------------------------------------------


def test_manufacturability_floor_blocks_too_thin(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_020",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 0.5},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "fail"
    blocker_ids = {c["check_id"] for c in v["blockers"]}
    assert "manufacturability.parameter_floor" in blocker_ids


def test_manufacturability_floor_passes_at_or_above(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_021",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 1.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    mfg_check = next(c for c in v["checks"] if c["check_id"] == "manufacturability.parameter_floor")
    assert mfg_check["status"] == "pass"


# ---------------------------------------------------------------------------
# Regression: thinning SF prediction
# ---------------------------------------------------------------------------


def test_safe_thinning_passes_regression(tmp_path: Path) -> None:
    """back_wall has SF=15.9, t=20.0 -> 10.0; predicted SF >> floor=1.5."""
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_030",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    assert v["verdict"] == "pass"
    reg = next(c for c in v["checks"] if c["check_id"] == "regression.thinning_sf_floor")
    assert reg["status"] == "pass"


def test_dangerous_thinning_fails_regression_in_default_mode(tmp_path: Path) -> None:
    """central_rib has SF=1.79, t=8.0 -> 4.0; predicted SF = 1.79 * (0.5)^2 = 0.4475 < 1.5."""
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_031",
        "feature_ref": "central_rib",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 8.0, "to": 4.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg, strictness="default")
    assert v["verdict"] == "fail"
    blocker_ids = {c["check_id"] for c in v["blockers"]}
    assert "regression.thinning_sf_floor" in blocker_ids


def test_dangerous_thinning_warns_in_lenient_mode(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_032",
        "feature_ref": "central_rib",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 8.0, "to": 4.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg, strictness="lenient")
    # Regression check should warn rather than fail; no other check should fail.
    reg = next(c for c in v["checks"] if c["check_id"] == "regression.thinning_sf_floor")
    assert reg["status"] == "warn"
    assert v["verdict"] == "warn"


def test_strict_mode_promotes_any_warning_to_fail(tmp_path: Path) -> None:
    """A feature already at SF>=floor + thicken proposal warns; strict mode blocks."""
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_033",
        "feature_ref": "back_wall",
        "action_type": "thicken",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 30.0},
    }
    v_default = verify_cad_modification_proposal(proposal, pkg, strictness="default")
    v_strict = verify_cad_modification_proposal(proposal, pkg, strictness="strict")
    assert v_default["verdict"] == "warn"
    assert v_strict["verdict"] == "fail"


# ---------------------------------------------------------------------------
# End-to-end: verify the Phase 36 recommender's output
# ---------------------------------------------------------------------------


def test_verifies_full_phase36_recommendations(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    recs = generate_cad_modification_recommendations(pkg)
    assert recs["proposals"], "expected proposals from Phase 36"
    result = verify_recommendations(recs, pkg)
    assert result["schema_version"] == "0.1"
    assert result["summary"]["total"] == len(recs["proposals"])
    # The top proposal (back_wall thin) must pass.
    top = result["verdicts"][0]
    assert top["proposal_id"] == recs["proposals"][0]["proposal_id"]
    assert top["verdict"] == "pass"


# ---------------------------------------------------------------------------
# Honesty boundaries
# ---------------------------------------------------------------------------


def test_package_is_not_mutated(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    before = pkg.read_bytes()
    proposal = {
        "proposal_id": "p_999",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
    }
    _ = verify_cad_modification_proposal(proposal, pkg)
    after = pkg.read_bytes()
    assert before == after


def test_claim_policy_block_present_and_honest(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    proposal = {
        "proposal_id": "p_998",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg)
    policy = v["claim_policy"]
    assert policy["verification_is_pre_execution"] is True
    assert policy["verification_does_not_replace_resimulation"] is True
    assert policy["geometry_kernel_checks_not_performed"] is True
    assert policy["claims_advanced"] is False


def test_invalid_strictness_raises() -> None:
    with pytest.raises(ValueError):
        verify_cad_modification_proposal(
            {"feature_ref": "x", "action_type": "thin"},
            "/tmp/does-not-matter.aieng",
            strictness="paranoid",
        )


def test_markdown_includes_verdict_and_boundary(tmp_path: Path) -> None:
    pkg = _build_package(tmp_path)
    recs = generate_cad_modification_recommendations(pkg)
    result = verify_recommendations(recs, pkg)
    md = generate_verification_markdown(result)
    assert "# CAD Modification Verification" in md
    assert "Boundary" in md
    assert "re-simulation" in md.lower()


def test_directory_form_package_supported(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "verify_dir"
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
    proposal = {
        "proposal_id": "p_dir",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
    }
    v = verify_cad_modification_proposal(proposal, pkg_dir)
    assert v["verdict"] == "pass"
