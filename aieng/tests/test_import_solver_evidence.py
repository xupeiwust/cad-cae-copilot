from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.package import create_package
from aieng.results.evidence_writer import write_evidence_scaffold_package
from aieng.simulation.solver_evidence_importer import import_solver_evidence_package


def _make_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "test.aieng"
    create_package("test_model", pkg)
    write_evidence_scaffold_package(pkg)
    return pkg


def _read_json_member(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def test_import_solver_evidence_extracts_known_numeric_observations(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text(
        """
CALCULIX RESULT SUMMARY
Maximum von Mises stress: 123.4 MPa
Maximum displacement magnitude: 0.021 mm
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _, summary = import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="calculix",
        claim_support=["claim_solver_result_001"],
    )

    numeric = summary["numeric_observations"]
    assert numeric["max_von_mises"]["value"] == 123.4
    assert numeric["max_von_mises"]["unit"] == "MPa"
    assert numeric["max_displacement"]["value"] == 0.021
    assert numeric["max_displacement"]["unit"] == "mm"


    payload = summary['structured_payload']
    assert payload['parser']['status'] == 'matched'
    assert payload['observations']['max_von_mises']['status'] == 'observed'
    assert payload['observations']['max_displacement']['status'] == 'observed'


def test_import_solver_evidence_records_numeric_observations_in_notes(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text(
        """
mises stress maximum = 210.0 MPa
displacement max = 1.2e-03 m
""".strip()
        + "\n",
        encoding="utf-8",
    )

    import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="ccx_2_21",
        claim_support=["claim_solver_result_001"],
    )

    evidence_index = _read_json_member(pkg, "results/evidence_index.json")
    solver_items = [item for item in evidence_index["evidence_items"] if item.get("evidence_type") == "solver_result"]
    assert solver_items
    notes = solver_items[-1].get("notes", "")
    assert "known_numeric_observations=" in notes
    assert "max_von_mises" in notes
    assert "max_displacement" in notes




def test_import_solver_evidence_records_structured_numeric_payload(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / 'job.dat'
    result_file.write_text(
        '''
mises stress maximum = 210.0 MPa
displacement max = 1.2e-03 m
'''.strip()
        + '\n',
        encoding='utf-8',
    )

    import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format='calculix_dat',
        producer_tool='ccx_2_21',
        claim_support=['claim_solver_result_001'],
    )

    evidence_index = _read_json_member(pkg, 'results/evidence_index.json')
    solver_items = [item for item in evidence_index['evidence_items'] if item.get('evidence_type') == 'solver_result']
    assert solver_items
    payload = solver_items[-1]['structured_payload']
    assert payload['payload_type'] == 'solver_numeric_observations'
    assert payload['parser']['parser_id'] == 'calculix_dat_utf8_numeric_v1'
    assert payload['parser']['status'] == 'matched'
    assert payload['observations']['max_von_mises']['value'] == 210.0
    assert payload['observations']['max_von_mises']['unit'] == 'MPa'
    assert payload['observations']['max_displacement']['value'] == 1.2e-03
    assert payload['observations']['max_displacement']['unit'] == 'm'

def test_import_solver_evidence_handles_missing_numeric_patterns_explicitly(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text("solver log with no numeric stress/displacement summary\n", encoding="utf-8")

    _, summary = import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="calculix",
        claim_support=["claim_solver_result_001"],
    )

    numeric = summary["numeric_observations"]
    assert "max_von_mises" not in numeric
    assert "max_displacement" not in numeric
    assert "max_reaction_force" not in numeric
    assert set(numeric["not_found"]) == {"max_von_mises", "max_displacement", "max_reaction_force"}
    assert summary["claim_review_suggestions"] == []


def test_import_solver_evidence_not_found_lists_only_unmatched_keys(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text(
        "Maximum von Mises stress: 87.5 MPa\n",
        encoding="utf-8",
    )

    _, summary = import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="calculix",
        claim_support=["claim_solver_result_001"],
    )

    numeric = summary["numeric_observations"]
    assert numeric["max_von_mises"]["value"] == 87.5
    assert "max_displacement" not in numeric
    assert "max_reaction_force" not in numeric
    assert set(numeric["not_found"]) == {"max_displacement", "max_reaction_force"}


def test_import_solver_evidence_extracts_max_reaction_force(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text(
        "Maximum von Mises stress: 150.0 MPa\nMaximum reaction force: 2500.0 N\n",
        encoding="utf-8",
    )

    _, summary = import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="calculix",
        claim_support=["claim_solver_result_001"],
    )

    numeric = summary["numeric_observations"]
    assert numeric["max_reaction_force"]["value"] == 2500.0
    assert numeric["max_reaction_force"]["unit"] == "N"
    assert "max_reaction_force" not in numeric["not_found"]


def test_import_solver_evidence_records_unknown_status_in_structured_payload(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / 'job.dat'
    result_file.write_text('solver log with no numeric summary\n', encoding='utf-8')

    import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format='calculix_dat',
        producer_tool='calculix',
        claim_support=['claim_solver_result_001'],
    )

    evidence_index = _read_json_member(pkg, 'results/evidence_index.json')
    solver_item = next(item for item in evidence_index['evidence_items'] if item.get('evidence_type') == 'solver_result')
    payload = solver_item['structured_payload']
    assert payload['parser']['status'] == 'unsupported'
    assert payload['observations']['max_von_mises']['status'] == 'unknown'
    assert payload['observations']['max_displacement']['status'] == 'unknown'
    assert 'no supported calculix_dat pattern matched' in payload['observations']['max_von_mises']['reason']
    assert 'no supported calculix_dat pattern matched' in payload['observations']['max_displacement']['reason']

def test_import_solver_evidence_parses_scientific_notation_without_unit(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text(
        """
maximum stress (mises) = 2.345e+02
max disp = 6.70E-04
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _, summary = import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="calculix",
        claim_support=["claim_solver_result_001"],
    )

    numeric = summary["numeric_observations"]
    assert numeric["max_von_mises"]["value"] == 234.5
    assert "unit" not in numeric["max_von_mises"]
    assert numeric["max_displacement"]["value"] == 6.7e-04
    assert "unit" not in numeric["max_displacement"]


def test_import_solver_evidence_returns_manual_claim_review_suggestions(tmp_path: Path):
    pkg = _make_package(tmp_path)
    result_file = tmp_path / "job.dat"
    result_file.write_text(
        """
von mises stress = 321.0 MPa
displacement max = 0.031 mm
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _, summary = import_solver_evidence_package(
        pkg,
        result_file=result_file,
        result_format="calculix_dat",
        producer_tool="calculix",
        claim_support=["claim_solver_result_001"],
    )

    suggestions = summary["claim_review_suggestions"]
    assert suggestions
    assert all(item["action"] == "human_review_required" for item in suggestions)
    assert all(item["claim_id"] == "claim_solver_result_001" for item in suggestions)


