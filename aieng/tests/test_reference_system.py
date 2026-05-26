from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.cli import main
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import recognize_features_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def _make_package(tmp_path: Path) -> Path:
    step = tmp_path / "part.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "part.aieng"
    import_step_package(step, pkg)
    extract_topology_package(pkg, backend="mock")
    recognize_features_package(pkg)
    return pkg


def test_cli_ref_list_features_json(tmp_path, capsys):
    pkg = _make_package(tmp_path)

    assert main(["ref-list", str(pkg), "--type", "feature", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    refs = [item["ref"] for item in payload]
    assert "@aieng[graph/feature_graph.json#feat_base_plate_001]" in refs


def test_cli_ref_inspect_feature_json(tmp_path, capsys):
    pkg = _make_package(tmp_path)

    assert main([
        "ref-inspect",
        str(pkg),
        "@aieng[graph/feature_graph.json#feat_hole_001]",
        "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["id"] == "feat_hole_001"
    assert payload["kind"] == "feature"
    assert payload["record"]["type"] == "mounting_hole"


def test_cli_ref_check_passes_for_valid_package(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    assert main(["write-evidence-scaffold", str(pkg)]) == 0
    capsys.readouterr()

    assert main([
        "record-evidence",
        str(pkg),
        "--kind",
        "validation_report",
        "--producer-kind",
        "aieng_core",
        "--producer-tool",
        "aieng",
        "--artifact-kind",
        "json",
        "--artifact-path",
        "validation/completeness_report.json",
        "--claim-support",
        "claim_task_defined_001",
    ]) == 0
    capsys.readouterr()

    assert main(["ref-check", str(pkg)]) == 0
    output = capsys.readouterr().out
    assert "PASS ref-check indexed" in output
    assert "PASS ref-check cross-resource ID references resolve" in output


