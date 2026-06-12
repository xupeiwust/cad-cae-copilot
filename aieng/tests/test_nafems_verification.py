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
    run_nafems_suite,
    verify_case,
    write_nafems_vv_report,
)
from aieng.simulation.deck_generator import generate_solver_input_package
from tests.fixtures.nafems.build_fixtures import (
    build_all_fixtures,
    build_cantilever_end_load_fixture,
    build_cantilever_udl_fixture,
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


def test_build_all_fixtures_creates_three_packages(fixtures_dir: Path) -> None:
    paths = build_all_fixtures(fixtures_dir)
    assert set(paths) == {"tension_rod", "cantilever_end_load", "cantilever_udl"}
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


# ---------------------------------------------------------------------------
# Real-ccx integration tests (skipped if ccx is unavailable)
# ---------------------------------------------------------------------------


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
