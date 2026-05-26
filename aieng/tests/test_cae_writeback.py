from __future__ import annotations

import zipfile

import pytest
import yaml

from aieng.cli import main
from aieng.context.apply_context import apply_context_package
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import recognize_features_package
from aieng.simulation.deck_exporter import UPDATED_DECK_PATH, export_updated_deck_package
from aieng.validation.status_writer import update_validation_status_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

MINIMAL_CONTEXT = """\
material: Al6061-T6
protected_features:
  - feat_hole_pattern_001
simulation:
  type: static_structural
  fixed:
    - feat_hole_pattern_001
  loads:
    - target: feat_base_plate_001
      type: force
      value_n: 500
      direction: [1, 0, 0]
targets:
  max_von_mises_stress_mpa: 120
"""


def _make_context_package(tmp_path):
    step = tmp_path / "bracket.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "bracket.aieng"
    import_step_package(step, pkg)
    extract_topology_package(pkg)
    recognize_features_package(pkg)
    ctx = tmp_path / "context.yaml"
    ctx.write_text(MINIMAL_CONTEXT, encoding="utf-8")
    apply_context_package(pkg, ctx)
    return pkg


def _read_member(pkg, member):
    with zipfile.ZipFile(pkg) as zf:
        return zf.read(member)


def _deck_text(pkg):
    return _read_member(pkg, UPDATED_DECK_PATH).decode()


# --- Happy path ---

def test_export_updated_deck_writes_updated_deck_inp(tmp_path):
    pkg = _make_context_package(tmp_path)

    export_updated_deck_package(pkg)

    with zipfile.ZipFile(pkg) as zf:
        assert UPDATED_DECK_PATH in set(zf.namelist())


def test_updated_deck_contains_scaffold_marker(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    assert "This is not a complete runnable FEA model." in _deck_text(pkg)


def test_updated_deck_contains_material_block(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    deck = _deck_text(pkg)
    assert "*MATERIAL" in deck
    assert "Al6061-T6" in deck


def test_updated_deck_reflects_modified_youngs_modulus(tmp_path):
    pkg = _make_context_package(tmp_path)

    # Patch the setup.yaml directly to simulate a parameter change
    with zipfile.ZipFile(pkg) as zf:
        setup = yaml.safe_load(zf.read("simulation/setup.yaml"))
        members = [(i, zf.read(i.filename) if not i.is_dir() else b"") for i in zf.infolist()]

    setup.setdefault("materials", {}).setdefault("Al6061-T6", {})["youngs_modulus_mpa"] = 99999

    import shutil, tempfile, json
    from pathlib import Path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        temp = Path(fh.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, data in members:
            if info.filename != "simulation/setup.yaml":
                zf.writestr(info, data)
        zf.writestr("simulation/setup.yaml", yaml.dump(setup))
    shutil.move(str(temp), pkg)

    export_updated_deck_package(pkg)

    assert "99999" in _deck_text(pkg)


def test_updated_deck_header_mentions_current_state(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    deck = _deck_text(pkg)
    assert "current simulation/setup.yaml" in deck or "current state" in deck


def test_updated_deck_contains_bc_intent(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    deck = _deck_text(pkg)
    assert "Boundary condition" in deck or "boundary" in deck.lower()


def test_updated_deck_contains_load_intent(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    deck = _deck_text(pkg)
    assert "500" in deck  # load value_n from context


def test_updated_deck_manifest_updated(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    import json
    with zipfile.ZipFile(pkg) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["resources"]["simulation"]["updated_deck"] == UPDATED_DECK_PATH


def test_updated_deck_updates_validation_status_when_present(tmp_path):
    pkg = _make_context_package(tmp_path)
    update_validation_status_package(pkg)

    export_updated_deck_package(pkg, overwrite=True)

    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))
    assert status["cae_import_status"]["updated_deck_exported"] is True
    assert status["cae_import_status"]["updated_deck_path"] == UPDATED_DECK_PATH


def test_updated_deck_does_not_claim_solver_run(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    deck = _deck_text(pkg)
    assert "solver has been run" not in deck.lower() or "No solver has been run" in deck


# --- Overwrite / error paths ---

def test_export_updated_deck_fails_without_setup_yaml(tmp_path):
    step = tmp_path / "bracket.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "bracket.aieng"
    import_step_package(step, pkg)

    with pytest.raises(FileNotFoundError, match="setup.yaml missing"):
        export_updated_deck_package(pkg)


def test_export_updated_deck_fails_if_already_exists(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    with pytest.raises(FileExistsError, match="--overwrite"):
        export_updated_deck_package(pkg)


def test_export_updated_deck_overwrites_with_flag(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)

    export_updated_deck_package(pkg, overwrite=True)

    assert UPDATED_DECK_PATH in set(zipfile.ZipFile(pkg).namelist())


def test_export_updated_deck_writes_external_out(tmp_path):
    pkg = _make_context_package(tmp_path)
    out = tmp_path / "out.inp"

    export_updated_deck_package(pkg, out=out)

    assert out.exists()
    assert "AIENG Updated CalculiX Deck" in out.read_text()


# --- Validation status reporting ---

def test_status_writer_records_updated_deck_exported_false_initially(tmp_path):
    pkg = _make_context_package(tmp_path)
    update_validation_status_package(pkg)

    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))
    assert status["cae_import_status"]["updated_deck_exported"] is False


def test_status_writer_records_updated_deck_exported_true_after_export(tmp_path):
    pkg = _make_context_package(tmp_path)
    export_updated_deck_package(pkg)
    update_validation_status_package(pkg)

    with zipfile.ZipFile(pkg) as zf:
        status = yaml.safe_load(zf.read("validation/status.yaml"))
    assert status["cae_import_status"]["updated_deck_exported"] is True


# --- CLI ---

def test_cli_export_updated_deck_happy_path(tmp_path, capsys):
    pkg = _make_context_package(tmp_path)

    rc = main(["export-updated-deck", str(pkg)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "PASS exported updated deck" in out
    assert "PASS simulation/updated_deck.inp written" in out


def test_cli_export_updated_deck_missing_setup(tmp_path, capsys):
    step = tmp_path / "bracket.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "bracket.aieng"
    import_step_package(step, pkg)

    rc = main(["export-updated-deck", str(pkg)])

    assert rc == 2
    assert "FAIL" in capsys.readouterr().err


def test_cli_export_updated_deck_writes_external_file(tmp_path, capsys):
    pkg = _make_context_package(tmp_path)
    out = tmp_path / "external.inp"

    rc = main(["export-updated-deck", str(pkg), "--out", str(out)])

    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr().out
    assert "external deck copy written" in captured
