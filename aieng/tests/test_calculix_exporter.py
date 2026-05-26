from __future__ import annotations

import zipfile

import pytest
import yaml

from aieng.cli import main
from aieng.context.apply_context import apply_context_package
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import recognize_features_package
from aieng.package import read_manifest
from aieng.simulation.calculix_exporter import SOLVER_DECK_PATH, export_calculix_package
from aieng.validate import validate_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

VALID_CONTEXT = {
    "material": "Al6061-T6",
    "protected_features": ["feat_hole_pattern_001"],
    "simulation": {
        "type": "static_structural",
        "fixed": ["feat_hole_pattern_001"],
        "loads": [{"target": "feat_base_plate_001", "type": "force", "value_n": 500, "direction": [1, 0, 0]}],
    },
    "targets": {"max_von_mises_stress_mpa": 120},
    "assumptions": ["Mounting hole pattern is treated as fixed support."],
}


def _build_phase5_package(tmp_path):
    """Build a package through Phase 4 apply-context (minimum for export-calculix)."""
    step = tmp_path / "bracket.step"
    step.write_bytes(FAKE_STEP)
    ctx = tmp_path / "context.yaml"
    ctx.write_text(yaml.safe_dump(VALID_CONTEXT), encoding="utf-8")
    pkg = tmp_path / "bracket.aieng"
    import_step_package(step, pkg)
    extract_topology_package(pkg)
    recognize_features_package(pkg)
    apply_context_package(pkg, ctx)
    return pkg


def _read_deck_from_package(pkg_path: object) -> str:
    with zipfile.ZipFile(pkg_path) as z:
        return z.read(SOLVER_DECK_PATH).decode("utf-8")


# ---- Happy path ----

def test_export_calculix_happy_path(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    result = export_calculix_package(pkg)
    assert result == pkg
    with zipfile.ZipFile(pkg) as z:
        assert SOLVER_DECK_PATH in z.namelist()


def test_export_calculix_writes_solver_deck_inside_package(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    with zipfile.ZipFile(pkg) as z:
        assert SOLVER_DECK_PATH in z.namelist()


def test_export_calculix_updates_manifest(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    manifest = read_manifest(pkg)
    assert manifest["resources"]["simulation"]["solver_deck"] == SOLVER_DECK_PATH


def test_export_calculix_writes_external_out_file(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    out = tmp_path / "build" / "solver_deck.inp"
    export_calculix_package(pkg, out=out)
    assert out.exists()
    assert out.read_text(encoding="utf-8").strip()


def test_export_calculix_external_out_matches_package_deck(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    out = tmp_path / "solver_deck.inp"
    export_calculix_package(pkg, out=out)
    deck_in_pkg = _read_deck_from_package(pkg)
    assert out.read_text(encoding="utf-8") == deck_in_pkg


# ---- Deck content ----

def test_deck_contains_scaffold_warning(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "This is not a complete runnable FEA model." in deck


def test_deck_contains_no_solver_run_header(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "No solver has been run." in deck


def test_deck_contains_material(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "Al6061-T6" in deck
    assert "*MATERIAL" in deck


def test_deck_contains_elastic_values(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "*ELASTIC" in deck
    assert "69000" in deck
    assert "0.33" in deck


def test_deck_contains_density(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "*DENSITY" in deck
    assert "2700" in deck


def test_deck_contains_fixed_feature(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "feat_hole_pattern_001" in deck


def test_deck_contains_load_target(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "feat_base_plate_001" in deck


def test_deck_contains_force_value(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "500" in deck


def test_deck_contains_validation_target(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "max_von_mises_stress_mpa" in deck
    assert "120" in deck


def test_deck_contains_protected_region_notes(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    # Protected regions section should mention feat_hole_pattern_001
    assert "feat_hole_pattern_001" in deck


def test_deck_contains_missing_mesh_notice(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "No mesh has been generated" in deck or "mesh" in deck.lower()


def test_deck_contains_required_next_steps(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    deck = _read_deck_from_package(pkg)
    assert "Required next steps" in deck or "next steps" in deck.lower()


# ---- Overwrite behavior ----

def test_export_calculix_does_not_overwrite_by_default(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    with pytest.raises(FileExistsError):
        export_calculix_package(pkg)


def test_export_calculix_overwrites_with_flag(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    export_calculix_package(pkg, overwrite=True)  # must not raise
    with zipfile.ZipFile(pkg) as z:
        assert SOLVER_DECK_PATH in z.namelist()


def test_export_calculix_external_out_does_not_overwrite_by_default(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    out = tmp_path / "deck.inp"
    out.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_calculix_package(pkg, out=out)


def test_export_calculix_external_out_overwrites_with_flag(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    out = tmp_path / "deck.inp"
    out.write_text("existing", encoding="utf-8")
    export_calculix_package(pkg, out=out, overwrite=True)
    assert "AIENG" in out.read_text(encoding="utf-8")


# ---- Error paths ----

def test_export_calculix_fails_if_package_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="package does not exist"):
        export_calculix_package(tmp_path / "missing.aieng")


def test_export_calculix_fails_if_setup_yaml_missing(tmp_path):
    step = tmp_path / "bracket.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "bracket.aieng"
    import_step_package(step, pkg)
    with pytest.raises(FileNotFoundError, match="simulation/setup.yaml missing"):
        export_calculix_package(pkg)


def test_export_calculix_fails_with_non_aieng_extension(tmp_path):
    p = tmp_path / "bracket.zip"
    p.touch()
    with pytest.raises(ValueError, match=".aieng"):
        export_calculix_package(p)


# ---- CLI ----

def test_cli_export_calculix_happy_path(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    ret = main([
        "export-calculix", str(pkg),
        "--out", str(tmp_path / "solver_deck.inp"),
    ])
    assert ret == 0
    assert (tmp_path / "solver_deck.inp").exists()


def test_cli_export_calculix_missing_package(tmp_path):
    ret = main(["export-calculix", str(tmp_path / "missing.aieng")])
    assert ret == 2


def test_cli_export_calculix_overwrite(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    main(["export-calculix", str(pkg)])
    ret = main(["export-calculix", str(pkg), "--overwrite"])
    assert ret == 0


# ---- Validator integration ----

def test_validate_passes_after_export_calculix(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    report = validate_package(pkg)
    assert report.ok
    rendered = report.render()
    assert "solver_deck.inp" in rendered
    assert "FAIL" not in rendered


def test_validate_checks_scaffold_warning(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    report = validate_package(pkg)
    rendered = report.render()
    assert "scaffold warning" in rendered


def test_validate_checks_non_empty(tmp_path):
    pkg = _build_phase5_package(tmp_path)
    export_calculix_package(pkg)
    report = validate_package(pkg)
    rendered = report.render()
    assert "non-empty" in rendered
