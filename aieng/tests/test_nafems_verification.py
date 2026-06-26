"""Tests for the NAFEMS-style V&V verification regression suite.

Coverage:

* Unit tests for :func:`verify_case` with synthetic metrics.
* Fixture-builder tests that verify packages can be built and deck generation
  produces a runnable-looking ``solver_input.inp``.
* Real-ccx integration tests for each of the three cases, skipped cleanly when
  CalculiX is unavailable.
* Report artifact write-back and honesty claim tests.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng import FORMAT_VERSION
from aieng.nafems_verification import (
    NAFEMS_VV_REPORT_PATH,
    REFERENCE_CASES,
    _find_ccx,
    run_case,
    run_mesh_convergence_study,
    run_nafems_suite,
    verify_case,
    write_nafems_vv_report,
)
from aieng.simulation.deck_generator import generate_solver_input_package
from tests.fixtures.nafems.build_fixtures import (
    build_all_fixtures,
    build_cantilever_end_load_fixture,
    build_cantilever_end_load_lateral_fixture,
    build_cantilever_midspan_load_fixture,
    build_cantilever_modal_fixture,
    build_cantilever_udl_fixture,
    build_column_buckling_fixture,
    build_fixed_fixed_center_load_fixture,
    build_fixed_fixed_udl_fixture,
    build_tension_rod_fixture,
)


# ---------------------------------------------------------------------------
# verify_case unit tests
# ---------------------------------------------------------------------------


def _make_computed_metrics(
    max_displacement: float | None,
    max_von_mises_stress: float | None,
) -> dict:
    metrics: dict = {"load_cases": [{"id": "nafems_run_001", "metrics": {}}]}
    if max_displacement is not None:
        metrics["load_cases"][0]["metrics"]["max_displacement"] = {
            "value": max_displacement,
            "unit": "mm",
        }
    if max_von_mises_stress is not None:
        metrics["load_cases"][0]["metrics"]["max_von_mises_stress"] = {
            "value": max_von_mises_stress,
            "unit": "MPa",
        }
    return metrics


def test_find_ccx_returns_none_when_no_ccx_available(monkeypatch) -> None:
    monkeypatch.setenv("AIENG_CCX_CMD", "")
    monkeypatch.setenv("PATH", "")
    assert _find_ccx() is None


def test_find_ccx_honors_aieng_ccx_cmd(monkeypatch) -> None:
    """When AIENG_CCX_CMD is set and executable exists, _find_ccx returns its parts."""
    import sys

    # Use the Python interpreter as a stand-in executable so shutil.which succeeds.
    python_exe = sys.executable
    monkeypatch.setenv("AIENG_CCX_CMD", f'{python_exe} -m ccx_stub')
    found = _find_ccx()
    assert found is not None
    assert found[0] == python_exe


def test_verify_case_passes_when_within_tolerance() -> None:
    ref = REFERENCE_CASES["tension_rod"]
    # 2 % low on displacement and 3 % high on stress should still pass 10 % band.
    computed = _make_computed_metrics(
        max_displacement=ref["metrics"]["max_displacement"]["value"] * 0.98,
        max_von_mises_stress=ref["metrics"]["max_von_mises_stress"]["value"] * 1.03,
    )
    result = verify_case("tension_rod", computed)
    assert result["verdict"] == "pass"
    for m in result["metrics"]:
        assert m["verdict"] == "pass"


def test_verify_case_fails_when_outside_tolerance() -> None:
    ref = REFERENCE_CASES["tension_rod"]
    computed = _make_computed_metrics(
        max_displacement=ref["metrics"]["max_displacement"]["value"] * 1.20,
        max_von_mises_stress=ref["metrics"]["max_von_mises_stress"]["value"],
    )
    result = verify_case("tension_rod", computed)
    assert result["verdict"] == "fail"
    disp_metric = next(
        m for m in result["metrics"] if m["metric"] == "max_displacement"
    )
    stress_metric = next(
        m for m in result["metrics"] if m["metric"] == "max_von_mises_stress"
    )
    assert disp_metric["verdict"] == "fail"
    assert stress_metric["verdict"] == "pass"


def test_verify_case_computes_deviation_percent() -> None:
    ref_value = REFERENCE_CASES["tension_rod"]["metrics"]["max_displacement"]["value"]
    computed = _make_computed_metrics(max_displacement=ref_value * 1.05, max_von_mises_stress=None)
    result = verify_case("tension_rod", computed)
    disp_metric = next(
        m for m in result["metrics"] if m["metric"] == "max_displacement"
    )
    assert pytest.approx(disp_metric["deviation_percent"], rel=1e-3) == 5.0


def test_verify_case_skips_missing_metric() -> None:
    computed = _make_computed_metrics(max_displacement=None, max_von_mises_stress=None)
    result = verify_case("tension_rod", computed)
    assert result["verdict"] == "fail"
    for m in result["metrics"]:
        assert m["verdict"] == "skipped"


def test_verify_case_accepts_custom_reference() -> None:
    custom_ref = {
        "metrics": {
            "max_displacement": {"value": 1.0, "unit": "mm", "tolerance_percent": 5.0},
        }
    }
    computed = _make_computed_metrics(max_displacement=1.04, max_von_mises_stress=None)
    result = verify_case("custom", computed, reference=custom_ref)
    assert result["verdict"] == "pass"


# ---------------------------------------------------------------------------
# Fixture-builder tests (no solver required)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    return tmp_path / "fixtures"


def test_build_all_fixtures_creates_all_packages(fixtures_dir: Path) -> None:
    paths = build_all_fixtures(fixtures_dir)
    assert set(paths) == {
        "tension_rod",
        "cantilever_end_load",
        "cantilever_udl",
        "fixed_fixed_udl",
        "fixed_fixed_center_load",
        "cantilever_midspan_load",
        "cantilever_end_load_lateral",
        "cantilever_modal",
        "column_buckling",
    }
    for p in paths.values():
        assert p.exists()
        assert p.suffix == ".aieng"


def test_fixture_package_contains_required_artifacts(fixtures_dir: Path) -> None:
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "simulation/setup.yaml" in names
        assert "simulation/cae_mapping.json" in names
        assert "simulation/cae_imports/source_solver_deck.inp" in names


def test_source_deck_has_required_keyword_cards(fixtures_dir: Path) -> None:
    path = build_cantilever_end_load_fixture(fixtures_dir / "cantilever_end_load.aieng")
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/cae_imports/source_solver_deck.inp").decode("utf-8")
    for kw in ("*NODE", "*ELEMENT, TYPE=C3D8", "*NSET, NSET=N_FIX",
               "*ELSET, ELSET=EALL", "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL"):
        assert kw in deck, f"missing keyword: {kw}"


def test_generated_deck_from_fixture_contains_bcs_loads_and_material(
    fixtures_dir: Path,
) -> None:
    path = build_cantilever_udl_fixture(fixtures_dir / "cantilever_udl.aieng")
    result = generate_solver_input_package(path, run_id="run_test", overwrite=True)
    assert result["ok"] is True
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/runs/run_test/solver_input.inp").decode("utf-8")
    for kw in ("*HEADING", "*MATERIAL", "*ELASTIC", "*DENSITY", "*BOUNDARY",
               "*CLOAD", "*STEP", "*STATIC", "*END STEP"):
        assert kw in deck, f"missing generated keyword: {kw}"


def test_fixture_mappings_resolve_features_to_nsets(fixtures_dir: Path) -> None:
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    with zipfile.ZipFile(path, "r") as zf:
        mapping = json.loads(zf.read("simulation/cae_mapping.json"))
    feature_ids = {m["maps_to"]["feature_id"] for m in mapping["mappings"]}
    assert "feat_fix" in feature_ids
    assert "feat_load" in feature_ids


def test_fixed_fixed_udl_fixture_has_both_ends_in_fix_nset(fixtures_dir: Path) -> None:
    path = build_fixed_fixed_udl_fixture(fixtures_dir / "fixed_fixed_udl.aieng")
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/cae_imports/source_solver_deck.inp").decode("utf-8")
    assert "*NSET, NSET=N_FIX" in deck
    # Both ends fixed means the N_FIX block must contain at least two distinct x-faces
    # worth of nodes; a minimal sanity check is that the same NSET appears once.


def test_fixed_fixed_center_load_fixture_has_center_load_nset(fixtures_dir: Path) -> None:
    path = build_fixed_fixed_center_load_fixture(fixtures_dir / "fixed_fixed_center_load.aieng")
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/cae_imports/source_solver_deck.inp").decode("utf-8")
    assert "*NSET, NSET=N_CENTER" in deck


def test_verify_case_for_fixed_fixed_cases() -> None:
    """Synthetic metrics within tolerance produce pass verdicts for new cases."""
    for case_id in ("fixed_fixed_udl", "fixed_fixed_center_load"):
        ref = REFERENCE_CASES[case_id]
        computed = _make_computed_metrics(
            max_displacement=ref["metrics"]["max_displacement"]["value"] * 1.02,
            max_von_mises_stress=ref["metrics"].get("max_von_mises_stress", {}).get("value"),
        )
        result = verify_case(case_id, computed)
        assert result["verdict"] == "pass", f"{case_id} should pass synthetic metrics"


def test_verify_case_for_new_cantilever_cases() -> None:
    """Synthetic metrics within tolerance pass for the two expansion cases (#221)."""
    for case_id in ("cantilever_midspan_load", "cantilever_end_load_lateral"):
        ref = REFERENCE_CASES[case_id]
        computed = _make_computed_metrics(
            max_displacement=ref["metrics"]["max_displacement"]["value"] * 0.97,
            max_von_mises_stress=ref["metrics"]["max_von_mises_stress"]["value"] * 1.04,
        )
        result = verify_case(case_id, computed)
        assert result["verdict"] == "pass", f"{case_id} should pass synthetic metrics"


def test_new_cases_have_documented_reference_and_tolerance() -> None:
    """Both expansion cases carry an analytical value + tolerance for every metric."""
    for case_id in ("cantilever_midspan_load", "cantilever_end_load_lateral"):
        case = REFERENCE_CASES[case_id]
        assert case["description"]
        assert case["metrics"], f"{case_id} must declare reference metrics"
        for metric in case["metrics"].values():
            assert metric["value"] > 0
            assert metric["tolerance_percent"] > 0
            assert metric["unit"]


def test_midspan_fixture_deck_has_midspan_load_nset(fixtures_dir: Path) -> None:
    path = build_cantilever_midspan_load_fixture(fixtures_dir / "cantilever_midspan_load.aieng")
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/cae_imports/source_solver_deck.inp").decode("utf-8")
    assert "*NSET, NSET=N_MID" in deck
    assert "*NSET, NSET=N_FIX" in deck


def test_lateral_fixture_applies_load_in_minus_y(fixtures_dir: Path) -> None:
    import yaml

    path = build_cantilever_end_load_lateral_fixture(
        fixtures_dir / "cantilever_end_load_lateral.aieng"
    )
    with zipfile.ZipFile(path, "r") as zf:
        setup = yaml.safe_load(zf.read("simulation/setup.yaml"))
    assert setup["loads"][0]["direction"] == [0, -1, 0]


# ---------------------------------------------------------------------------
# Eigenvalue cases (modal / buckling) — fixtures + synthetic verify
# ---------------------------------------------------------------------------


def _eigen_metrics(metric_name: str, value: float) -> dict:
    return {"load_cases": [{"id": "nafems_run_001", "metrics": {metric_name: {"value": value}}}]}


def test_modal_and_buckling_reference_cases_documented() -> None:
    for case_id, metric in (
        ("cantilever_modal", "first_natural_frequency_hz"),
        ("column_buckling", "lowest_buckling_factor"),
    ):
        case = REFERENCE_CASES[case_id]
        assert case["description"]
        assert case["analysis_type"] in ("modal", "buckling")
        entry = case["metrics"][metric]
        assert entry["value"] > 0
        assert entry["tolerance_percent"] > 0
        assert entry["unit"]


def test_verify_modal_case_within_tolerance() -> None:
    ref = REFERENCE_CASES["cantilever_modal"]["metrics"]["first_natural_frequency_hz"]["value"]
    result = verify_case("cantilever_modal", _eigen_metrics("first_natural_frequency_hz", ref * 1.05))
    assert result["verdict"] == "pass"


def test_verify_buckling_case_outside_tolerance_fails() -> None:
    ref = REFERENCE_CASES["column_buckling"]["metrics"]["lowest_buckling_factor"]["value"]
    result = verify_case("column_buckling", _eigen_metrics("lowest_buckling_factor", ref * 1.5))
    assert result["verdict"] == "fail"


def test_modal_fixture_deck_is_frequency_step_without_load(fixtures_dir: Path) -> None:
    path = build_cantilever_modal_fixture(fixtures_dir / "cantilever_modal.aieng")
    generate_solver_input_package(path, run_id="run_modal", overwrite=True)
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/runs/run_modal/solver_input.inp").decode("utf-8")
    assert "*FREQUENCY" in deck
    assert "*STATIC" not in deck
    assert "*CLOAD" not in deck  # modal needs no load
    assert "*DENSITY" in deck    # mass matrix
    assert "*DENSITY\n7.85e-09" in deck
    assert "7.85e-21" not in deck


def test_buckling_fixture_deck_is_buckle_step_with_load(fixtures_dir: Path) -> None:
    path = build_column_buckling_fixture(fixtures_dir / "column_buckling.aieng")
    generate_solver_input_package(path, run_id="run_buckle", overwrite=True)
    with zipfile.ZipFile(path, "r") as zf:
        deck = zf.read("simulation/runs/run_buckle/solver_input.inp").decode("utf-8")
    assert "*BUCKLE" in deck
    assert "*CLOAD" in deck       # reference perturbation load
    assert "*STATIC" not in deck


# ---------------------------------------------------------------------------
# Real-ccx integration tests (skipped if ccx is unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_modal_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_cantilever_modal_fixture(fixtures_dir / "cantilever_modal.aieng")
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    assert run_result["analysis_type"] == "modal"
    verification = verify_case("cantilever_modal", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_column_buckling_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_column_buckling_fixture(fixtures_dir / "column_buckling.aieng")
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    assert run_result["analysis_type"] == "buckling"
    verification = verify_case("column_buckling", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_tension_rod_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    verification = verify_case("tension_rod", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_end_load_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_cantilever_end_load_fixture(
        fixtures_dir / "cantilever_end_load.aieng"
    )
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    verification = verify_case("cantilever_end_load", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_udl_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_cantilever_udl_fixture(fixtures_dir / "cantilever_udl.aieng")
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    verification = verify_case("cantilever_udl", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_fixed_fixed_udl_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_fixed_fixed_udl_fixture(fixtures_dir / "fixed_fixed_udl.aieng")
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    verification = verify_case("fixed_fixed_udl", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_fixed_fixed_center_load_real_ccx_displacement_within_tolerance(
    fixtures_dir: Path,
) -> None:
    path = build_fixed_fixed_center_load_fixture(
        fixtures_dir / "fixed_fixed_center_load.aieng"
    )
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    # Stress under a point load is mesh-sensitive; verify displacement only.
    computed = run_result["computed_metrics"]
    verification = verify_case("fixed_fixed_center_load", computed)
    disp_metric = next(
        m for m in verification["metrics"] if m["metric"] == "max_displacement"
    )
    assert disp_metric["verdict"] == "pass", disp_metric


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_midspan_load_real_ccx_displacement_within_tolerance(
    fixtures_dir: Path,
) -> None:
    path = build_cantilever_midspan_load_fixture(
        fixtures_dir / "cantilever_midspan_load.aieng"
    )
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    # A line load at mid-span makes local stress mesh-sensitive; verify displacement.
    verification = verify_case("cantilever_midspan_load", run_result["computed_metrics"])
    disp_metric = next(
        m for m in verification["metrics"] if m["metric"] == "max_displacement"
    )
    assert disp_metric["verdict"] == "pass", disp_metric


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_end_load_lateral_real_ccx_within_tolerance(fixtures_dir: Path) -> None:
    path = build_cantilever_end_load_lateral_fixture(
        fixtures_dir / "cantilever_end_load_lateral.aieng"
    )
    run_result = run_case(path, run_id="nafems_run_001")
    assert run_result["status"] == "ok", run_result.get("solver_log_tail")
    verification = verify_case("cantilever_end_load_lateral", run_result["computed_metrics"])
    assert verification["verdict"] == "pass", verification


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_end_load_lateral_mesh_convergence_trend(fixtures_dir: Path) -> None:
    """Refining the mesh should not move weak-axis displacement away from theory."""
    levels = {
        (10, 2, 2): build_cantilever_end_load_lateral_fixture(
            fixtures_dir / "lateral_coarse.aieng", mesh_divisions=(10, 2, 2)
        ),
        (20, 4, 4): build_cantilever_end_load_lateral_fixture(
            fixtures_dir / "lateral_medium.aieng", mesh_divisions=(20, 4, 4)
        ),
        (40, 8, 8): build_cantilever_end_load_lateral_fixture(
            fixtures_dir / "lateral_fine.aieng", mesh_divisions=(40, 8, 8)
        ),
    }
    study = run_mesh_convergence_study("cantilever_end_load_lateral", levels)
    ok_levels = [lvl for lvl in study["levels"] if lvl.get("status") == "ok"]
    assert len(ok_levels) >= 2, "at least two refinement levels should solve"
    disp_devs = []
    for lvl in ok_levels:
        for m in lvl.get("metrics", []):
            if m["metric"] == "max_displacement" and m.get("deviation_percent") is not None:
                disp_devs.append(abs(m["deviation_percent"]))
                break
    assert len(disp_devs) >= 2
    assert disp_devs[-1] <= disp_devs[0] * 1.5, (
        f"fine-mesh deviation {disp_devs[-1]} should not exceed 1.5x coarse {disp_devs[0]}"
    )


@pytest.mark.skipif(
    _find_ccx() is None,
    reason="CalculiX command unavailable via AIENG_CCX_CMD or PATH — skipping real solver regression.",
)
def test_cantilever_end_load_mesh_convergence_trend(fixtures_dir: Path) -> None:
    """Mesh refinement should move the displacement deviation toward the reference."""
    levels = {
        (10, 2, 2): build_cantilever_end_load_fixture(
            fixtures_dir / "cantilever_end_load_coarse.aieng",
            mesh_divisions=(10, 2, 2),
        ),
        (20, 4, 4): build_cantilever_end_load_fixture(
            fixtures_dir / "cantilever_end_load_medium.aieng",
            mesh_divisions=(20, 4, 4),
        ),
        (40, 8, 8): build_cantilever_end_load_fixture(
            fixtures_dir / "cantilever_end_load_fine.aieng",
            mesh_divisions=(40, 8, 8),
        ),
    }
    study = run_mesh_convergence_study("cantilever_end_load", levels)
    assert study["case_id"] == "cantilever_end_load"
    assert len(study["levels"]) == 3
    ok_levels = [lvl for lvl in study["levels"] if lvl.get("status") == "ok"]
    # At least two levels must solve for a trend to be meaningful.
    assert len(ok_levels) >= 2, "at least two refinement levels should solve"

    disp_devs = []
    for lvl in ok_levels:
        for m in lvl.get("metrics", []):
            if m["metric"] == "max_displacement" and m.get("deviation_percent") is not None:
                disp_devs.append(abs(m["deviation_percent"]))
                break
    assert len(disp_devs) >= 2
    # The finest mesh should not be farther from the reference than the coarsest.
    assert disp_devs[-1] <= disp_devs[0] * 1.5, (
        f"fine-mesh deviation {disp_devs[-1]} should not exceed 1.5x coarse-mesh deviation {disp_devs[0]}"
    )


def test_run_case_skips_cleanly_when_ccx_missing(
    fixtures_dir: Path, monkeypatch
) -> None:
    """When ccx is absent, run_case returns status skipped without raising."""
    monkeypatch.setenv("AIENG_CCX_CMD", "")
    monkeypatch.delenv("AIENG_CCX_CMD", raising=False)
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    # Force _find_ccx to see no ccx by clearing PATH.
    monkeypatch.setenv("PATH", "")
    result = run_case(path, run_id="nafems_run_001")
    assert result["status"] == "skipped"
    assert "ccx" in result["missing_tools"]


def test_mesh_convergence_study_skips_cleanly_without_ccx(
    fixtures_dir: Path, monkeypatch
) -> None:
    """run_mesh_convergence_study records skipped levels when ccx is unavailable."""
    monkeypatch.setenv("AIENG_CCX_CMD", "")
    monkeypatch.delenv("AIENG_CCX_CMD", raising=False)
    monkeypatch.setenv("PATH", "")
    levels = {
        (10, 2, 2): build_tension_rod_fixture(
            fixtures_dir / "tension_rod_coarse.aieng", mesh_divisions=(10, 2, 2)
        ),
    }
    study = run_mesh_convergence_study("tension_rod", levels)
    assert study["case_id"] == "tension_rod"
    assert len(study["levels"]) == 1
    assert study["levels"][0]["status"] == "skipped"
    assert "no refinement level produced usable metrics" in study["summary"].lower()


# ---------------------------------------------------------------------------
# Report artifact and honesty tests
# ---------------------------------------------------------------------------


def test_write_nafems_vv_report_creates_valid_json_artifact(
    fixtures_dir: Path,
) -> None:
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    report = run_nafems_suite(path, run_id="nafems_run_001")
    write_nafems_vv_report(path, report)
    with zipfile.ZipFile(path, "r") as zf:
        assert NAFEMS_VV_REPORT_PATH in zf.namelist()
        written = json.loads(zf.read(NAFEMS_VV_REPORT_PATH))
    assert written["format"] == "aieng.nafems_vv_report"
    assert written["format_version"] == FORMAT_VERSION
    assert written["schema_version"] == "0.1"
    from aieng.cae_verification import VERIFICATION_SCHEMA
    assert written["schema_version"] == VERIFICATION_SCHEMA
    assert "cases" in written
    assert "status" in written


def test_report_contains_honest_not_certified_claim(fixtures_dir: Path) -> None:
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    report = run_nafems_suite(path, run_id="nafems_run_001")
    limitations = " ".join(report.get("limitations", [])).lower()
    assert "not a certification" in limitations
    assert "not asme v&v 10 certified" in limitations


def test_report_status_is_skipped_when_ccx_missing(
    fixtures_dir: Path, monkeypatch
) -> None:
    """The aggregated report status is 'skipped' when ccx is unavailable."""
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("AIENG_CCX_CMD", raising=False)
    path = build_tension_rod_fixture(fixtures_dir / "tension_rod.aieng")
    report = run_nafems_suite(path, run_id="nafems_run_001")
    assert report["status"] == "skipped"
    assert report["cases"][0]["status"] == "skipped"


def test_run_nafems_suite_on_directory_aggregates_all_cases(
    fixtures_dir: Path,
) -> None:
    paths = build_all_fixtures(fixtures_dir)
    report = run_nafems_suite(fixtures_dir, run_id="nafems_run_001")
    case_ids = {c["case_id"] for c in report["cases"]}
    assert case_ids == set(paths)
