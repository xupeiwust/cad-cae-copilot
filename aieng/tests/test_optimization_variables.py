"""Tests for optimization variable resolution and shape-bearing detection (#102)."""

from __future__ import annotations

from aieng.converters.optimization_variables import is_shape_bearing, resolve_optimization_variables


# ── is_shape_bearing ─────────────────────────────────────────────────────────


def test_fillet_radius_is_shape_bearing():
    assert is_shape_bearing(semantic_role="fillet_radius", cad_parameter_name="FILLET_RADIUS")


def test_hole_diameter_is_shape_bearing():
    assert is_shape_bearing(semantic_role="hole_diameter", cad_parameter_name="HOLE_DIAMETER")


def test_slot_position_is_shape_bearing():
    assert is_shape_bearing(semantic_role="slot_position", cad_parameter_name="SLOT_POSITION")


def test_rib_thickness_is_shape_bearing():
    assert is_shape_bearing(semantic_role="rib_thickness", cad_parameter_name="RIB_THICKNESS")


def test_gusset_width_is_shape_bearing():
    assert is_shape_bearing(semantic_role="gusset", cad_parameter_name="GUSSET_WIDTH")


def test_chamfer_size_is_shape_bearing():
    assert is_shape_bearing(semantic_role="chamfer", cad_parameter_name="CHAMFER_SIZE")


def test_taper_angle_is_shape_bearing():
    assert is_shape_bearing(semantic_role="taper", cad_parameter_name="TAPER_ANGLE")


def test_draft_angle_is_shape_bearing():
    assert is_shape_bearing(semantic_role="draft", cad_parameter_name="DRAFT_ANGLE")


def test_wall_thickness_is_not_shape_bearing():
    assert not is_shape_bearing(semantic_role="wall_thickness", cad_parameter_name="WALL_THICKNESS")


def test_generic_thickness_is_not_shape_bearing():
    assert not is_shape_bearing(semantic_role="thickness", cad_parameter_name="THICKNESS")


def test_hole_count_is_shape_bearing():
    # hole_count contains "hole" → shape-bearing (even though count is sizing-like)
    assert is_shape_bearing(semantic_role="count", cad_parameter_name="HOLE_COUNT")


def test_bolt_hole_is_shape_bearing():
    # bolt_hole contains "hole" → shape-bearing (protected but still shape-bearing)
    assert is_shape_bearing(semantic_role="bolt_hole", cad_parameter_name="BOLT_DIA")


def test_shape_bearing_from_semantic_role_only():
    assert is_shape_bearing(semantic_role="fillet", cad_parameter_name=None)


def test_shape_bearing_from_cad_name_only():
    assert is_shape_bearing(semantic_role=None, cad_parameter_name="FILLET_RADIUS")


def test_null_inputs_are_not_shape_bearing():
    assert not is_shape_bearing(semantic_role=None, cad_parameter_name=None)


# ── resolve_optimization_variables ───────────────────────────────────────────


def _problem():
    return {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "bracket_001",
        "variables": [
            {"id": "wall_t", "path": "parts/0/params/WALL_THICKNESS", "type": "continuous",
             "current_value": 3.0, "min_value": 2.0, "max_value": 8.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
            {"id": "fillet_r", "path": "parts/0/params/FILLET_RADIUS", "type": "continuous",
             "current_value": 2.0, "min_value": 1.0, "max_value": 4.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "fillet_radius"},
            {"id": "hole_d", "path": "parts/0/params/HOLE_DIA", "type": "continuous",
             "current_value": 5.0, "min_value": 3.0, "max_value": 10.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "hole_diameter"},
        ],
        "objective": {"sense": "minimize", "metric": "mass"},
    }


def test_resolve_sets_shape_bearing_correctly():
    doc = resolve_optimization_variables(_problem(), study_id="opt_001")
    assert doc["format"] == "aieng.optimization_variables"
    assert doc["schema_version"] == "0.2"
    assert doc["study_id"] == "opt_001"
    vars_by_id = {v["id"]: v for v in doc["variables"]}
    assert len(vars_by_id) == 3
    # wall thickness is sizing-only
    assert vars_by_id["wall_t"]["shape_bearing"] is False
    # fillet radius is shape-bearing
    assert vars_by_id["fillet_r"]["shape_bearing"] is True
    # hole diameter is shape-bearing
    assert vars_by_id["hole_d"]["shape_bearing"] is True


def test_resolve_without_parameter_index():
    doc = resolve_optimization_variables(_problem(), study_id="opt_001")
    v = doc["variables"][0]
    assert v["binding_status"] == "unverified"
    assert v["scope"] == "unscoped"
    assert v["cad_parameter_name"] == "WALL_THICKNESS"
    assert v["featureId"] is None
    assert v["parameterName"] is None


def test_resolve_with_parameter_index():
    problem = _problem()
    index = [
        {
            "feature_id": "feat_wall",
            "feature_name": "wall",
            "feature_type": "box",
            "scope": "local",
            "parameter_name": "thickness",
            "cad_parameter_name": "WALL_THICKNESS",
            "current_value": 3.0,
            "min_value": 2.0,
            "max_value": 8.0,
            "search_tokens": ["wall", "thickness"],
        },
    ]
    doc = resolve_optimization_variables(problem, study_id="opt_001", parameter_index=index)
    v = [var for var in doc["variables"] if var["id"] == "wall_t"][0]
    assert v["binding_status"] == "bound"
    assert v["featureId"] == "feat_wall"
    assert v["parameterName"] == "thickness"
    assert v["scope"] == "local"


def test_resolve_populates_problem_ref():
    doc = resolve_optimization_variables(_problem(), study_id="opt_001")
    assert doc["design_study_problem_ref"] == "analysis/design_study_problem.json"
    assert doc["design_study_problem_id"] == "bracket_001"


def test_resolve_claim_policy():
    doc = resolve_optimization_variables(_problem(), study_id="opt_001")
    assert doc["claim_policy"]["advisory_only"] is True
    assert doc["claim_policy"]["baseline_unchanged"] is True
    assert doc["claim_policy"]["human_approval_required_for_acceptance"] is True
