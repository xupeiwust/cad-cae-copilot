from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from aieng.cli import main
from aieng.context.apply_context import apply_context_package
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import recognize_features_package
from aieng.validate import Level, validate_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _read_json(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _names(pkg: Path) -> set[str]:
    with zipfile.ZipFile(pkg) as zf:
        return set(zf.namelist())


def _pkg_with_features(tmp_path: Path) -> Path:
    step = tmp_path / "part.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "part.aieng"
    import_step_package(step, pkg)
    extract_topology_package(pkg, backend="mock")
    recognize_features_package(pkg)
    return pkg


def _rewrite_member(pkg: Path, member: str, data: dict) -> None:
    with zipfile.ZipFile(pkg, "r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != member
        ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=pkg.parent) as fh:
        tmp_pkg = Path(fh.name)

    try:
        with zipfile.ZipFile(tmp_pkg, "w") as zf:
            for info, payload in members:
                zf.writestr(info, payload)
            zf.writestr(member, json.dumps(data, indent=2).encode("utf-8"))
        shutil.move(str(tmp_pkg), str(pkg))
    finally:
        if tmp_pkg.exists():
            tmp_pkg.unlink()


def test_build_allowed_operations_catalog_cli_writes_resource_and_manifest(tmp_path, capsys):
    pkg = _pkg_with_features(tmp_path)

    assert main(["build-allowed-operations-catalog", str(pkg)]) == 0
    out = capsys.readouterr().out
    assert "PASS built allowed operations catalog" in out
    assert "graph/allowed_operations_catalog.json" in _names(pkg)

    manifest = _read_json(pkg, "manifest.json")
    assert manifest["resources"]["graph"]["allowed_operations_catalog"] == "graph/allowed_operations_catalog.json"


def test_build_allowed_operations_catalog_respects_protected_features(tmp_path):
    pkg = _pkg_with_features(tmp_path)
    apply_context_package(pkg, EXAMPLES_DIR / "bracket_user_context.yaml")

    assert main(["build-allowed-operations-catalog", str(pkg)]) == 0

    catalog = _read_json(pkg, "graph/allowed_operations_catalog.json")
    protected_entries = [entry for entry in catalog["feature_operations"] if entry.get("protected") is True]
    assert protected_entries

    for entry in protected_entries:
        modify_op = next(op for op in entry["operations"] if op["operation_type"] == "modify_parameter")
        assert modify_op["status"] == "forbidden"


def test_allowed_operations_catalog_validation_passes(tmp_path):
    pkg = _pkg_with_features(tmp_path)
    apply_context_package(pkg, EXAMPLES_DIR / "bracket_user_context.yaml")
    assert main(["build-allowed-operations-catalog", str(pkg)]) == 0

    report = validate_package(pkg)
    catalog_fails = [
        m for m in report.messages if m.level is Level.FAIL and "allowed_operations_catalog" in m.text
    ]
    assert not catalog_fails


def test_allowed_operations_catalog_validation_fails_unknown_constraint_ref(tmp_path):
    pkg = _pkg_with_features(tmp_path)
    apply_context_package(pkg, EXAMPLES_DIR / "bracket_user_context.yaml")
    assert main(["build-allowed-operations-catalog", str(pkg)]) == 0

    catalog = _read_json(pkg, "graph/allowed_operations_catalog.json")
    first_entry = catalog["feature_operations"][0]
    first_entry["operations"][0]["blocked_by_constraints"] = ["constr_missing_999"]
    _rewrite_member(pkg, "graph/allowed_operations_catalog.json", catalog)

    report = validate_package(pkg)
    assert any(
        m.level is Level.FAIL and "references unknown constraints" in m.text
        for m in report.messages
    )


def test_allowed_operations_catalog_uses_interface_roles_for_preconditions(tmp_path):
    pkg = _pkg_with_features(tmp_path)
    apply_context_package(pkg, EXAMPLES_DIR / "bracket_user_context.yaml")
    assert main(["build-interface-graph", str(pkg)]) == 0
    assert main(["build-allowed-operations-catalog", str(pkg), "--overwrite"]) == 0

    catalog = _read_json(pkg, "graph/allowed_operations_catalog.json")
    by_feature = {entry["feature_id"]: entry for entry in catalog["feature_operations"]}

    hole_pattern = by_feature["feat_hole_pattern_001"]
    assert "fixed_support_interface" in hole_pattern["interface_roles"]
    assign_bc = next(op for op in hole_pattern["operations"] if op["operation_type"] == "assign_boundary_condition")
    assert any("fixed_support_interface" in text for text in assign_bc["preconditions"])

    base_plate = by_feature["feat_base_plate_001"]
    assert "load_application_interface" in base_plate["interface_roles"]
    assign_load = next(op for op in base_plate["operations"] if op["operation_type"] == "assign_load")
    assert any("load_application_interface" in text for text in assign_load["preconditions"])


def test_allowed_operations_catalog_source_files_include_interface_graph_when_present(tmp_path):
    pkg = _pkg_with_features(tmp_path)
    apply_context_package(pkg, EXAMPLES_DIR / "bracket_user_context.yaml")
    assert main(["build-interface-graph", str(pkg)]) == 0
    assert main(["build-allowed-operations-catalog", str(pkg), "--overwrite"]) == 0

    catalog = _read_json(pkg, "graph/allowed_operations_catalog.json")
    assert "objects/interface_graph.json" in catalog["source_files"]
