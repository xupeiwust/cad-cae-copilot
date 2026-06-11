"""Tests for the candidate parameter generation (sampler) module (Issue #38).

Covers all four sampling algorithms, bound respect, cap behaviour,
determinism, and package I/O.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.optimization_sampler import (
    OPTIMIZATION_VARIABLES_PATH,
    SAMPLE_CANDIDATES_DIR,
    genetic_sample,
    grid_sample,
    latin_hypercube_sample,
    random_sample,
    sample_candidates,
    sample_candidates_package,
)
from aieng.cli import main


def _variables() -> list[dict]:
    """Canonical test variables fixture — matches design_study_demo fixture."""
    return [
        {
            "id": "wall_t",
            "path": "parts/0/params/WALL_THICKNESS",
            "type": "continuous",
            "current_value": 3.0,
            "min_value": 2.0,
            "max_value": 8.0,
            "allowed_values": None,
            "unit": "mm",
            "scope": "local",
            "safe_to_modify": True,
            "featureId": "feat_wall",
            "parameterName": "thickness",
            "cad_parameter_name": "WALL_THICKNESS",
            "binding_status": "bound",
            "candidate_ids": [],
        },
        {
            "id": "rib_t",
            "path": "parts/0/params/RIB_THICKNESS",
            "type": "continuous",
            "current_value": 5.0,
            "min_value": 3.0,
            "max_value": 10.0,
            "allowed_values": None,
            "unit": "mm",
            "scope": "local",
            "safe_to_modify": True,
            "featureId": "feat_rib",
            "parameterName": "thickness",
            "cad_parameter_name": "RIB_THICKNESS",
            "binding_status": "bound",
            "candidate_ids": [],
        },
        {
            "id": "fillet_r",
            "path": "parts/0/params/FILLET_RADIUS",
            "type": "continuous",
            "current_value": 3.0,
            "min_value": 1.0,
            "max_value": 6.0,
            "allowed_values": None,
            "unit": "mm",
            "scope": "local",
            "safe_to_modify": True,
            "featureId": "feat_fillet",
            "parameterName": "radius",
            "cad_parameter_name": "FILLET_RADIUS",
            "binding_status": "bound",
            "candidate_ids": [],
        },
        {
            "id": "bolt_dia",
            "path": "parts/0/params/BOLT_DIA",
            "type": "discrete",
            "current_value": 8,
            "min_value": None,
            "max_value": None,
            "allowed_values": [6, 8, 10, 12],
            "unit": "mm",
            "scope": "local",
            "safe_to_modify": False,  # protected (mounting hole)
            "featureId": "feat_hole",
            "parameterName": "diameter",
            "cad_parameter_name": "BOLT_DIA",
            "binding_status": "bound",
            "candidate_ids": [],
        },
        {
            "id": "count",
            "path": "parts/0/params/HOLE_COUNT",
            "type": "integer",
            "current_value": 4,
            "min_value": 2,
            "max_value": 8,
            "allowed_values": None,
            "unit": "",
            "scope": "local",
            "safe_to_modify": True,
            "featureId": "feat_hole",
            "parameterName": "count",
            "cad_parameter_name": "HOLE_COUNT",
            "binding_status": "bound",
            "candidate_ids": [],
        },
    ]


def _variables_doc(variables=None) -> dict:
    v = variables or _variables()
    return {
        "format": "aieng.optimization_variables",
        "schema_version": "0.1",
        "study_id": "opt_study_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "variables": v,
        "candidate_ids": [],
        "provenance": {"created_at": "2026-06-10T00:00:00Z", "created_by": "test",
                       "claim_advancement": "none"},
        "claim_policy": {"advisory_only": True, "baseline_unchanged": True,
                         "human_approval_required_for_acceptance": True,
                         "claim_advancement": "none"},
    }


def _study_doc(algorithm="grid", count=5, seed=7) -> dict:
    return {
        "format": "aieng.optimization_study",
        "schema_version": "0.1",
        "study_id": "opt_study_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "algorithm": {"name": algorithm, "phase": 1, "bounded_step": True, "seed": seed},
        "sampling": {"requested_candidate_count": count, "max_candidate_count": 50, "seed": seed},
        "budget": {"max_candidates": 50, "max_iterations": 1, "max_solver_runs": 0},
        "status": "defined",
        "artifact_refs": {"variables": OPTIMIZATION_VARIABLES_PATH,
                          "objectives": "analysis/optimization_objectives.json",
                          "constraints": "analysis/optimization_constraints.json",
                          "decision_log": "analysis/optimization_decision_log.json"},
        "candidate_ids": [],
        "provenance": {"created_at": "2026-06-10T00:00:00Z", "created_by": "test",
                       "claim_advancement": "none"},
        "claim_policy": {"advisory_only": True, "baseline_unchanged": True,
                         "human_approval_required_for_acceptance": True,
                         "claim_advancement": "none"},
    }


def _design_study_problem(variables=None, *, max_variables_per_candidate=6) -> dict:
    source_variables = []
    for variable in variables or _variables():
        source_variables.append(
            {
                key: variable[key]
                for key in (
                    "id",
                    "path",
                    "type",
                    "current_value",
                    "min_value",
                    "max_value",
                    "allowed_values",
                    "unit",
                    "safe_to_modify",
                )
                if key in variable
            }
        )
    return {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": "design_study_001",
        "variables": source_variables,
        "objective": {"sense": "minimize", "metric": "volume"},
        "constraints": [],
        "settings": {
            "max_variables_per_candidate": max_variables_per_candidate,
            "require_reasoning": True,
        },
    }


# ── grid sampler ─────────────────────────────────────────────────────────────


def test_grid_sampler_emits_candidates() -> None:
    result = grid_sample(_variables())
    assert isinstance(result, list)
    assert len(result) > 0
    for c in result:
        assert "candidate_id" in c
        assert c["format"] == "aieng.design_candidate_patch"
        assert c["candidate_id"].startswith("cand_grid_")
        assert "variable_changes" in c
        assert isinstance(c["variable_changes"], list)
        assert len(c["variable_changes"]) > 0


def test_grid_sampler_skips_unsafe_variables() -> None:
    """bolt_dia is safe_to_modify=False — must not appear in any candidate."""
    result = grid_sample(_variables())
    for c in result:
        vids = [v["variable_id"] for v in c["variable_changes"]]
        assert "bolt_dia" not in vids, "protected variable must not appear"


def test_grid_sampler_values_respect_bounds() -> None:
    result = grid_sample(_variables())
    for c in result:
        for vc in c["variable_changes"]:
            vid = vc["variable_id"]
            val = vc["new_value"]
            if vid == "wall_t":
                assert 2.0 <= val <= 8.0, f"wall_t {val} out of bounds"
            elif vid == "rib_t":
                assert 3.0 <= val <= 10.0, f"rib_t {val} out of bounds"
            elif vid == "fillet_r":
                assert 1.0 <= val <= 6.0, f"fillet_r {val} out of bounds"
            elif vid == "count":
                assert 2 <= val <= 8, f"count {val} out of bounds"
                assert isinstance(val, int), "integer type must stay integer"


def test_grid_sampler_deterministic() -> None:
    a = grid_sample(_variables())
    b = grid_sample(_variables())
    assert a == b


def test_grid_sampler_no_variables() -> None:
    assert grid_sample([]) == []
    assert grid_sample([{"id": "x", "type": "continuous", "safe_to_modify": False}]) == []


def test_grid_sampler_boolean_variable() -> None:
    vars_bool = [
        {"id": "flag", "type": "boolean", "safe_to_modify": True,
         "current_value": False, "min_value": None, "max_value": None,
         "allowed_values": None},
    ]
    result = grid_sample(vars_bool)
    # Grid search for a boolean yields 2 candidates: False and True
    assert len(result) == 2
    vals = {c["variable_changes"][0]["new_value"] for c in result}
    assert vals == {False, True}


def test_grid_sampler_discrete_variable() -> None:
    vars_disc = [
        {"id": "material", "type": "categorical", "safe_to_modify": True,
         "current_value": "al", "allowed_values": ["al", "st", "ti"],
         "min_value": None, "max_value": None},
    ]
    result = grid_sample(vars_disc)
    assert len(result) == 3
    vals = {c["variable_changes"][0]["new_value"] for c in result}
    assert vals == {"al", "st", "ti"}


def test_grid_sampler_integer_includes_both_bounds() -> None:
    variable = {
        "id": "count",
        "type": "integer",
        "safe_to_modify": True,
        "min_value": 2,
        "max_value": 8,
    }
    values = [item["variable_changes"][0]["new_value"] for item in grid_sample([variable])]
    assert values[0] == 2
    assert values[-1] == 8


def test_grid_sampler_only_truncates_when_limit_is_explicit() -> None:
    variables = [
        {
            "id": f"x_{index}",
            "type": "continuous",
            "safe_to_modify": True,
            "min_value": 0.0,
            "max_value": 1.0,
        }
        for index in range(5)
    ]

    assert len(grid_sample(variables)) == 5**5
    assert len(grid_sample(variables, limit=7)) == 7


# ── random sampler ───────────────────────────────────────────────────────────


def test_random_sampler_emits_candidates() -> None:
    result = random_sample(_variables(), count=10, seed=42)
    assert len(result) == 10
    for c in result:
        assert c["candidate_id"].startswith("cand_random_")
        assert len(c["variable_changes"]) > 0


def test_random_sampler_skips_unsafe_variables() -> None:
    result = random_sample(_variables(), count=5, seed=42)
    for c in result:
        vids = [v["variable_id"] for v in c["variable_changes"]]
        assert "bolt_dia" not in vids


def test_random_sampler_values_respect_bounds() -> None:
    result = random_sample(_variables(), count=20, seed=42)
    for c in result:
        for vc in c["variable_changes"]:
            vid = vc["variable_id"]
            val = vc["new_value"]
            if vid == "wall_t":
                assert 2.0 <= val <= 8.0
            elif vid == "rib_t":
                assert 3.0 <= val <= 10.0
            elif vid == "fillet_r":
                assert 1.0 <= val <= 6.0
            elif vid == "count":
                assert 2 <= val <= 8
                assert isinstance(val, int)
                assert val == int(round(val))


def test_random_sampler_deterministic() -> None:
    a = random_sample(_variables(), count=10, seed=42)
    b = random_sample(_variables(), count=10, seed=42)
    assert a == b


def test_random_sampler_different_seed_gives_different_results() -> None:
    a = random_sample(_variables(), count=5, seed=1)
    b = random_sample(_variables(), count=5, seed=2)
    # Very unlikely to be identical
    a_vals = [c["variable_changes"][0]["new_value"] for c in a]
    b_vals = [c["variable_changes"][0]["new_value"] for c in b]
    assert a_vals != b_vals


def test_random_sampler_preserves_zero_and_negative_bounds() -> None:
    variables = [
        {
            "id": "offset",
            "type": "continuous",
            "safe_to_modify": True,
            "min_value": -10.0,
            "max_value": 0.0,
        }
    ]
    result = random_sample(variables, count=20, seed=42)
    values = [candidate["variable_changes"][0]["new_value"] for candidate in result]
    assert all(-10.0 <= value <= 0.0 for value in values)
    assert any(value < -1.0 for value in values)


# ── Latin hypercube sampler ──────────────────────────────────────────────────


def test_lhs_sampler_emits_candidates() -> None:
    result = latin_hypercube_sample(_variables(), count=10, seed=42)
    assert len(result) == 10
    for c in result:
        assert c["candidate_id"].startswith("cand_lhs_")
        assert len(c["variable_changes"]) > 0


def test_lhs_sampler_skips_unsafe_variables() -> None:
    result = latin_hypercube_sample(_variables(), count=5, seed=42)
    for c in result:
        vids = [v["variable_id"] for v in c["variable_changes"]]
        assert "bolt_dia" not in vids


def test_lhs_sampler_values_respect_bounds() -> None:
    """LHS values must stay within declared bounds for each variable type."""
    result = latin_hypercube_sample(_variables(), count=30, seed=42)
    for c in result:
        for vc in c["variable_changes"]:
            vid = vc["variable_id"]
            val = vc["new_value"]
            if vid == "wall_t":
                assert 2.0 <= val <= 8.0
            elif vid == "rib_t":
                assert 3.0 <= val <= 10.0
            elif vid == "fillet_r":
                assert 1.0 <= val <= 6.0
            elif vid == "count":
                assert 2 <= val <= 8
                assert isinstance(val, int)


def test_lhs_sampler_deterministic() -> None:
    a = latin_hypercube_sample(_variables(), count=10, seed=42)
    b = latin_hypercube_sample(_variables(), count=10, seed=42)
    assert a == b


def test_lhs_sampler_stratified_coverage() -> None:
    """LHS should spread values across the full [0,1] range for each variable."""
    result = latin_hypercube_sample(_variables(), count=20, seed=42)
    wall_values = [
        c["variable_changes"][0]["new_value"]
        for c in result
        if c["variable_changes"][0]["variable_id"] == "wall_t"
    ]
    assert min(wall_values) < 3.0, "LHS should sample below midpoint"
    assert max(wall_values) > 6.0, "LHS should sample above midpoint"


# ── genetic sampler ──────────────────────────────────────────────────────────


def test_genetic_sampler_emits_candidates() -> None:
    result = genetic_sample(_variables(), count=10, seed=42)
    assert len(result) == 10
    for c in result:
        assert c["candidate_id"].startswith("cand_genetic_")
        assert c["format"] == "aieng.design_candidate_patch"
        assert len(c["variable_changes"]) > 0


def test_genetic_sampler_skips_unsafe_variables() -> None:
    result = genetic_sample(_variables(), count=10, seed=42)
    for c in result:
        vids = [v["variable_id"] for v in c["variable_changes"]]
        assert "bolt_dia" not in vids


def test_genetic_sampler_values_respect_bounds() -> None:
    result = genetic_sample(_variables(), count=20, seed=42)
    for c in result:
        for vc in c["variable_changes"]:
            vid = vc["variable_id"]
            val = vc["new_value"]
            if vid == "wall_t":
                assert 2.0 <= val <= 8.0
            elif vid == "rib_t":
                assert 3.0 <= val <= 10.0
            elif vid == "fillet_r":
                assert 1.0 <= val <= 6.0
            elif vid == "count":
                assert 2 <= val <= 8
                assert isinstance(val, int)


def test_genetic_sampler_deterministic() -> None:
    a = genetic_sample(_variables(), count=10, seed=42)
    b = genetic_sample(_variables(), count=10, seed=42)
    assert a == b


def test_genetic_sampler_different_seed_gives_different_results() -> None:
    a = genetic_sample(_variables(), count=10, seed=1)
    b = genetic_sample(_variables(), count=10, seed=2)
    a_vals = [c["variable_changes"][0]["new_value"] for c in a]
    b_vals = [c["variable_changes"][0]["new_value"] for c in b]
    assert a_vals != b_vals


def test_genetic_sampler_discrete_variables() -> None:
    vars_disc = [
        {
            "id": "material",
            "type": "categorical",
            "safe_to_modify": True,
            "current_value": "al",
            "allowed_values": ["al", "st", "ti"],
            "min_value": None,
            "max_value": None,
        },
    ]
    result = genetic_sample(vars_disc, count=9, seed=42)
    assert len(result) == 9
    for c in result:
        val = c["variable_changes"][0]["new_value"]
        assert val in {"al", "st", "ti"}


def test_genetic_sampler_boolean_variable() -> None:
    vars_bool = [
        {"id": "flag", "type": "boolean", "safe_to_modify": True,
         "current_value": False, "min_value": None, "max_value": None,
         "allowed_values": None},
    ]
    result = genetic_sample(vars_bool, count=8, seed=42)
    assert len(result) == 8
    vals = {c["variable_changes"][0]["new_value"] for c in result}
    assert vals <= {False, True}


def test_genetic_sampler_no_variables() -> None:
    assert genetic_sample([], count=5, seed=42) == []


def test_genetic_sampler_respects_population_size() -> None:
    result = genetic_sample(
        _variables(), count=4, seed=42, population_size=8, generations=2
    )
    assert len(result) == 4


# ── sample_candidates (public entrypoint) ────────────────────────────────────


def test_sample_candidates_grid() -> None:
    result = sample_candidates(_variables(), algorithm="grid",
                                counts={"wall_t": 2, "rib_t": 2, "fillet_r": 2, "count": 2})
    assert result["algorithm"] == "grid"
    assert len(result["candidates"]) > 0
    assert not result["capped"]
    assert result["dropped_count"] == 0


def test_sample_candidates_random() -> None:
    result = sample_candidates(_variables(), algorithm="random", count=10, seed=42)
    assert result["algorithm"] == "random"
    assert len(result["candidates"]) == 10


def test_sample_candidates_lhs() -> None:
    result = sample_candidates(_variables(), algorithm="latin_hypercube", count=8, seed=42)
    assert result["algorithm"] == "latin_hypercube"
    assert len(result["candidates"]) == 8


def test_sample_candidates_genetic() -> None:
    result = sample_candidates(_variables(), algorithm="genetic", count=8, seed=42)
    assert result["algorithm"] == "genetic"
    assert len(result["candidates"]) == 8


def test_sample_candidates_lhs_alias() -> None:
    result = sample_candidates(_variables(), algorithm="lhs", count=5, seed=42)
    assert len(result["candidates"]) == 5


def test_sample_candidates_cap() -> None:
    result = sample_candidates(_variables(), algorithm="grid", max_candidates=3)
    assert result["capped"]
    assert result["dropped_count"] > 0
    assert len(result["candidates"]) == 3


def test_sample_candidates_caps_before_expanding_large_grid() -> None:
    variables = [
        {
            "id": f"v{index}",
            "type": "continuous",
            "safe_to_modify": True,
            "min_value": 0.0,
            "max_value": 1.0,
        }
        for index in range(10)
    ]
    result = sample_candidates(
        variables,
        algorithm="grid",
        counts={f"v{index}": 100 for index in range(10)},
        max_candidates=3,
    )
    assert len(result["candidates"]) == 3
    assert result["total_generated"] == 100**10
    assert result["dropped_count"] == 100**10 - 3


def test_sample_candidates_rejects_invalid_bounds() -> None:
    variables = [
        {
            "id": "bad",
            "type": "continuous",
            "safe_to_modify": True,
            "min_value": None,
            "max_value": 1.0,
        }
    ]
    result = sample_candidates(variables, algorithm="random", count=3)
    assert result["candidates"] == []
    assert any("missing min_value" in warning for warning in result["warnings"])


def test_sample_candidates_no_safe_variables() -> None:
    all_unsafe = [
        {"id": "x", "type": "continuous", "safe_to_modify": False,
         "min_value": 0, "max_value": 10},
    ]
    result = sample_candidates(all_unsafe, algorithm="random", count=5)
    assert len(result["candidates"]) == 0
    assert len(result["warnings"]) > 0


def test_sample_candidates_empty_variables() -> None:
    result = sample_candidates([], algorithm="grid")
    assert len(result["candidates"]) == 0


def test_sample_candidates_unknown_algorithm() -> None:
    result = sample_candidates(_variables(), algorithm="not_real")
    assert len(result["candidates"]) == 0
    assert any("unknown algorithm" in w for w in result["warnings"])
    assert any("genetic" in w for w in result["warnings"])


def test_sample_candidates_grid_includes_all_safe_variables() -> None:
    """Every grid candidate should have a change for each safe variable."""
    result = sample_candidates(_variables(), algorithm="grid", counts={"wall_t": 2, "rib_t": 2, "fillet_r": 2, "count": 2})
    for c in result["candidates"]:
        vids = {v["variable_id"] for v in c["variable_changes"]}
        assert vids == {"wall_t", "rib_t", "fillet_r", "count"}, f"missing variables in {vids}"


# ── package I/O ──────────────────────────────────────────────────────────────


def _write_variables_package(tmp_path: Path, variables=None, study=None, problem=None) -> Path:
    variables_document = variables or _variables_doc()
    pkg = tmp_path / "study.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Study"}))
        zf.writestr(
            "analysis/design_study_problem.json",
            json.dumps(problem or _design_study_problem(variables_document["variables"])),
        )
        zf.writestr(OPTIMIZATION_VARIABLES_PATH, json.dumps(variables_document))
        if study:
            zf.writestr("analysis/optimization_study.json", json.dumps(study))
    return pkg


def test_sample_candidates_package_writes_candidates(tmp_path: Path) -> None:
    pkg = _write_variables_package(tmp_path)
    result = sample_candidates_package(pkg, algorithm="random", count=5, seed=42)
    assert result["status"] == "ok"
    assert len(result["candidates"]) == 5
    assert len(result["candidate_artifacts_written"]) == 5

    with zipfile.ZipFile(pkg, "r") as zf:
        names = set(zf.namelist())
        for path in result["artifacts_written"]:
            assert path in names, f"{path} not in package"


def test_sample_candidates_package_missing_variables(tmp_path: Path) -> None:
    pkg = tmp_path / "empty.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Empty"}))
        zf.writestr("analysis/design_study_problem.json", json.dumps(_design_study_problem()))
    result = sample_candidates_package(pkg)
    assert result["status"] == "error"
    assert result["code"] == "missing_variables"


def test_sample_candidates_package_empty_variables(tmp_path: Path) -> None:
    doc = _variables_doc()
    doc["variables"] = []
    pkg = _write_variables_package(tmp_path, variables=doc)
    result = sample_candidates_package(pkg)
    assert result["status"] == "error", f"expected error, got {result}"
    assert result["code"] == "empty_variables", f"expected empty_variables, got {result.get('code')}"


def test_sample_candidates_package_from_study_config(tmp_path: Path) -> None:
    """When no explicit algorithm is given, read from optimization_study.json."""
    study = _study_doc(algorithm="latin_hypercube", count=6, seed=99)
    pkg = _write_variables_package(tmp_path, study=study)
    result = sample_candidates_package(pkg)
    assert result["status"] == "ok"
    assert len(result["candidates"]) == 6
    assert all(c["candidate_id"].startswith("cand_lhs_") for c in result["candidates"])


def test_sample_candidates_package_genetic_from_study_config(tmp_path: Path) -> None:
    """Genetic algorithm settings are read from optimization_study.json."""
    study = _study_doc(algorithm="genetic", count=6, seed=99)
    study["algorithm"]["settings"] = {
        "population_size": 8,
        "generations": 2,
        "crossover_rate": 0.7,
        "mutation_rate": 0.15,
        "elitism": 1,
    }
    pkg = _write_variables_package(tmp_path, study=study)
    result = sample_candidates_package(pkg)
    assert result["status"] == "ok"
    assert len(result["candidates"]) == 6
    assert all(c["candidate_id"].startswith("cand_genetic_") for c in result["candidates"])


def test_sample_candidates_package_genetic_explicit_options(tmp_path: Path) -> None:
    """Explicit genetic_options override study settings."""
    study = _study_doc(algorithm="genetic", count=4, seed=99)
    study["algorithm"]["settings"] = {"population_size": 20, "generations": 10}
    pkg = _write_variables_package(tmp_path, study=study)
    result = sample_candidates_package(
        pkg,
        genetic_options={"population_size": 6, "generations": 1},
    )
    assert result["status"] == "ok"
    assert len(result["candidates"]) == 4


def test_sample_candidates_package_updates_study_ids(tmp_path: Path) -> None:
    study = _study_doc(algorithm="random", count=3, seed=42)
    pkg = _write_variables_package(tmp_path, study=study)
    result = sample_candidates_package(pkg)
    assert result["status"] == "ok"

    with zipfile.ZipFile(pkg, "r") as zf:
        updated = json.loads(zf.read("analysis/optimization_study.json"))
        variables = json.loads(zf.read(OPTIMIZATION_VARIABLES_PATH))
    assert len(updated["candidate_ids"]) == 3
    assert all(cid.startswith("cand_random_") for cid in updated["candidate_ids"])
    assert variables["candidate_ids"] == updated["candidate_ids"]
    for variable in variables["variables"]:
        if variable["safe_to_modify"]:
            assert variable["candidate_ids"] == updated["candidate_ids"]
        else:
            assert variable["candidate_ids"] == []


def test_sample_candidates_package_overwrite(tmp_path: Path) -> None:
    """Overwriting should replace existing candidates with the same ID."""
    pkg = _write_variables_package(tmp_path)
    first = sample_candidates_package(
        pkg, algorithm="random", count=3, seed=42, overwrite=True
    )
    assert first["status"] == "ok"

    with zipfile.ZipFile(pkg, "r") as zf:
        names_before = sorted(n for n in zf.namelist() if n.startswith(SAMPLE_CANDIDATES_DIR))

    second = sample_candidates_package(
        pkg, algorithm="random", count=5, seed=99, overwrite=True
    )
    assert second["status"] == "ok"

    with zipfile.ZipFile(pkg, "r") as zf:
        names_after = sorted(n for n in zf.namelist() if n.startswith(SAMPLE_CANDIDATES_DIR))
    assert len(names_before) == 3
    assert len(names_after) == 5


def test_sample_candidates_package_no_overwrite_preserves_existing_candidates(
    tmp_path: Path,
) -> None:
    pkg = _write_variables_package(tmp_path)
    first = sample_candidates_package(pkg, algorithm="random", count=3, seed=42)
    second = sample_candidates_package(
        pkg,
        algorithm="random",
        count=3,
        seed=42,
        overwrite=False,
    )
    assert first["status"] == second["status"] == "ok"
    assert set(candidate["candidate_id"] for candidate in first["candidates"]).isdisjoint(
        candidate["candidate_id"] for candidate in second["candidates"]
    )
    with zipfile.ZipFile(pkg) as package:
        names = [
            name for name in package.namelist() if name.startswith(SAMPLE_CANDIDATES_DIR)
        ]
    assert len(names) == 6


def test_sample_candidates_package_respects_study_budget(tmp_path: Path) -> None:
    study = _study_doc(algorithm="random", count=20, seed=42)
    study["budget"]["max_candidates"] = 4
    pkg = _write_variables_package(tmp_path, study=study)
    result = sample_candidates_package(pkg)
    assert result["status"] == "ok"
    assert result["candidate_count"] == 4
    assert result["dropped_count"] == 16


def test_sample_candidates_package_capped(tmp_path: Path) -> None:
    pkg = _write_variables_package(tmp_path)
    result = sample_candidates_package(pkg, algorithm="random", count=20, seed=42, max_candidates=5)
    assert result["capped"]
    assert result["dropped_count"] == 15
    assert len(result["candidates"]) == 5
    with zipfile.ZipFile(pkg) as package:
        decision_log = json.loads(package.read("analysis/optimization_decision_log.json"))
        audit_lines = package.read("audit/events.jsonl").decode().splitlines()
    assert decision_log["entries"][-1]["reason_codes"] == [
        "candidate_cap_reached",
        "budget_exhausted",
    ]
    assert json.loads(audit_lines[-1])["tool"] == "opt.propose_candidates"


def test_sample_candidates_package_not_found(tmp_path: Path) -> None:
    result = sample_candidates_package(tmp_path / "nonexistent.aieng")
    assert result["status"] == "error"
    assert result["code"] == "package_not_found"


def test_sample_candidates_cli_writes_candidates(tmp_path: Path, capsys) -> None:
    pkg = _write_variables_package(tmp_path)

    exit_code = main([
        "sample-candidates",
        str(pkg),
        "--algorithm",
        "random",
        "--count",
        "3",
        "--seed",
        "42",
    ])

    assert exit_code == 0
    assert "PASS sampled candidates (random): 3 written" in capsys.readouterr().out
    with zipfile.ZipFile(pkg) as package:
        candidate_paths = [
            name
            for name in package.namelist()
            if name.startswith(SAMPLE_CANDIDATES_DIR)
        ]
    assert len(candidate_paths) == 3


def test_sample_candidates_cli_genetic(tmp_path: Path, capsys) -> None:
    pkg = _write_variables_package(tmp_path)

    exit_code = main([
        "sample-candidates",
        str(pkg),
        "--algorithm",
        "genetic",
        "--count",
        "4",
        "--seed",
        "42",
    ])

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "PASS sampled candidates (genetic): 4 written" in captured
    with zipfile.ZipFile(pkg) as package:
        candidate_paths = [
            name
            for name in package.namelist()
            if name.startswith(SAMPLE_CANDIDATES_DIR)
        ]
    assert len(candidate_paths) == 4


def test_sample_candidates_package_collision_avoidance(tmp_path: Path) -> None:
    """If a candidate ID already exists, the sampler should avoid collisions."""
    pkg = _write_variables_package(tmp_path)

    # Write a pre-existing candidate
    with zipfile.ZipFile(pkg, "a") as zf:
        zf.writestr(f"{SAMPLE_CANDIDATES_DIR}cand_random_0000.json",
                     json.dumps({"candidate_id": "cand_random_0000", "variable_changes": []}))

    result = sample_candidates_package(
        pkg,
        algorithm="random",
        count=3,
        seed=42,
        overwrite=False,
    )
    assert result["status"] == "ok"
    ids = [c["candidate_id"] for c in result["candidates"]]
    assert "cand_random_0000" not in ids, "must avoid existing ID"
    # Should have generated unique suffixes
    assert len(set(ids)) == 3


def test_sample_candidates_package_only_safe_variables_written(tmp_path: Path) -> None:
    """Candidates must never contain changes for protected/unsafe variables."""
    pkg = _write_variables_package(tmp_path)
    result = sample_candidates_package(pkg, algorithm="grid", counts={"wall_t": 2, "rib_t": 2, "fillet_r": 2, "count": 2})

    with zipfile.ZipFile(pkg, "r") as zf:
        for cname in result["candidate_artifacts_written"]:
            cand = json.loads(zf.read(cname))
            vids = {v["variable_id"] for v in cand["variable_changes"]}
            assert "bolt_dia" not in vids, f"protected var in {cname}"


def test_sample_candidates_package_requires_design_study_problem(tmp_path: Path) -> None:
    pkg = tmp_path / "missing_problem.aieng"
    with zipfile.ZipFile(pkg, "w") as package:
        package.writestr(OPTIMIZATION_VARIABLES_PATH, json.dumps(_variables_doc()))
    result = sample_candidates_package(pkg)
    assert result["status"] == "error"
    assert result["code"] == "missing_design_study_problem"


def test_sample_candidates_package_rejects_inconsistent_variables(tmp_path: Path) -> None:
    document = _variables_doc()
    document["variables"][0]["max_value"] = 99.0
    pkg = _write_variables_package(
        tmp_path,
        variables=document,
        problem=_design_study_problem(),
    )
    result = sample_candidates_package(pkg)
    assert result["status"] == "error"
    assert result["code"] == "invalid_optimization_source"


def test_sample_candidates_package_rejects_executor_incompatible_candidates(
    tmp_path: Path,
) -> None:
    pkg = _write_variables_package(
        tmp_path,
        problem=_design_study_problem(max_variables_per_candidate=2),
    )
    result = sample_candidates_package(pkg, algorithm="random", count=2)
    assert result["status"] == "error"
    assert result["code"] == "generated_candidates_invalid"
    with zipfile.ZipFile(pkg) as package:
        assert not any(
            name.startswith(SAMPLE_CANDIDATES_DIR) for name in package.namelist()
        )
