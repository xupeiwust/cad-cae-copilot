from __future__ import annotations

import json
import textwrap
import zipfile
from pathlib import Path

import pytest

from aieng.assembly.assembly_graph_writer import (
    ASSEMBLY_GRAPH_PATH,
    build_assembly_graph_package,
)
from aieng.cli import main
from aieng.geometry.step_importer import import_step_package
from aieng.validate import validate_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

_MINIMAL_DEF = textwrap.dedent("""\
    parts:
      - part_id: part_a
        label: Part A
      - part_id: part_b
        label: Part B
    mates:
      - mate_id: mate_001
        part_a: part_a
        part_b: part_b
        mate_type: planar
    coordinate_system:
      frame: global_origin
    claim_policy:
      allowed:
        - describe assembly structure
      forbidden:
        - claim assembly is validated without analysis
""")


def _make_package(tmp_path: Path) -> Path:
    step = tmp_path / "part.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "assembly_001.aieng"
    import_step_package(step, pkg)
    return pkg


def _make_def(tmp_path: Path, content: str = _MINIMAL_DEF) -> Path:
    def_file = tmp_path / "assembly_def.yaml"
    def_file.write_text(content, encoding="utf-8")
    return def_file


def _read_member(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_build_assembly_graph_returns_package_path(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    result = build_assembly_graph_package(pkg, def_file)
    assert result == pkg


def test_build_assembly_graph_writes_member(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    with zipfile.ZipFile(pkg) as zf:
        assert ASSEMBLY_GRAPH_PATH in set(zf.namelist())


def test_build_assembly_graph_format_fields(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    data = _read_member(pkg, ASSEMBLY_GRAPH_PATH)
    assert data["format"] == "aieng.assembly_graph"
    assert data["format_version"] == "0.1.0"


def test_build_assembly_graph_parts_written(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    data = _read_member(pkg, ASSEMBLY_GRAPH_PATH)
    part_ids = {p["part_id"] for p in data["parts"]}
    assert "part_a" in part_ids
    assert "part_b" in part_ids


def test_build_assembly_graph_mates_written(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    data = _read_member(pkg, ASSEMBLY_GRAPH_PATH)
    assert data["mates"][0]["mate_id"] == "mate_001"
    assert data["mates"][0]["mate_type"] == "planar"


def test_build_assembly_graph_claim_policy_written(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    data = _read_member(pkg, ASSEMBLY_GRAPH_PATH)
    assert data["claim_policy"]["allowed"]
    assert isinstance(data["claim_policy"]["forbidden"], list)


def test_build_assembly_graph_updates_manifest(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    with zipfile.ZipFile(pkg) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["resources"]["assembly"]["assembly_graph"] == ASSEMBLY_GRAPH_PATH


# ---------------------------------------------------------------------------
# Overwrite behaviour
# ---------------------------------------------------------------------------

def test_build_assembly_graph_rejects_overwrite_without_flag(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    with pytest.raises(FileExistsError, match="--overwrite"):
        build_assembly_graph_package(pkg, def_file)


def test_build_assembly_graph_overwrites_with_flag(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    build_assembly_graph_package(pkg, def_file, overwrite=True)
    data = _read_member(pkg, ASSEMBLY_GRAPH_PATH)
    assert data["format"] == "aieng.assembly_graph"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_build_assembly_graph_missing_package(tmp_path):
    def_file = _make_def(tmp_path)
    with pytest.raises(FileNotFoundError, match="package does not exist"):
        build_assembly_graph_package(tmp_path / "missing.aieng", def_file)


def test_build_assembly_graph_missing_definition(tmp_path):
    pkg = _make_package(tmp_path)
    with pytest.raises(FileNotFoundError, match="definition file does not exist"):
        build_assembly_graph_package(pkg, tmp_path / "missing.yaml")


def test_build_assembly_graph_wrong_suffix(tmp_path):
    def_file = _make_def(tmp_path)
    with pytest.raises(ValueError, match=".aieng"):
        build_assembly_graph_package(tmp_path / "not_a_package.zip", def_file)


def test_build_assembly_graph_duplicate_part_ids(tmp_path):
    pkg = _make_package(tmp_path)
    bad_def = _make_def(tmp_path, textwrap.dedent("""\
        parts:
          - part_id: dup
            label: A
          - part_id: dup
            label: B
        mates: []
        coordinate_system:
          frame: global_origin
        claim_policy:
          allowed: [describe assembly]
          forbidden: []
    """))
    with pytest.raises(ValueError, match="duplicate part_id"):
        build_assembly_graph_package(pkg, bad_def)


def test_build_assembly_graph_empty_claim_policy_allowed(tmp_path):
    pkg = _make_package(tmp_path)
    bad_def = _make_def(tmp_path, textwrap.dedent("""\
        parts:
          - part_id: part_a
            label: A
        mates: []
        coordinate_system:
          frame: global_origin
        claim_policy:
          allowed: []
          forbidden: []
    """))
    with pytest.raises(ValueError, match="claim_policy"):
        build_assembly_graph_package(pkg, bad_def)


def test_build_assembly_graph_invalid_mate_type(tmp_path):
    pkg = _make_package(tmp_path)
    bad_def = _make_def(tmp_path, textwrap.dedent("""\
        parts:
          - part_id: part_a
            label: A
          - part_id: part_b
            label: B
        mates:
          - mate_id: m1
            part_a: part_a
            part_b: part_b
            mate_type: welded
        coordinate_system:
          frame: global_origin
        claim_policy:
          allowed: [describe]
          forbidden: []
    """))
    with pytest.raises(ValueError, match="mate_type"):
        build_assembly_graph_package(pkg, bad_def)


# ---------------------------------------------------------------------------
# Schema validation via validate_package
# ---------------------------------------------------------------------------

def test_assembly_graph_conforms_to_schema(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    report = validate_package(pkg)
    rendered = report.render()
    assert "assembly/assembly_graph.json conforms to assembly_graph.schema.json" in rendered


def test_assembly_graph_semantic_checks_pass(tmp_path):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    build_assembly_graph_package(pkg, def_file)
    report = validate_package(pkg)
    rendered = report.render()
    assert "assembly/assembly_graph.json part_id values are unique" in rendered
    assert "assembly/assembly_graph.json claim_policy is present and non-empty" in rendered


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_build_assembly_graph_happy_path(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    rc = main(["build-assembly-graph", str(pkg), "--definition", str(def_file)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PASS built assembly graph" in out
    assert "PASS assembly/assembly_graph.json written" in out


def test_cli_build_assembly_graph_missing_definition(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    rc = main(["build-assembly-graph", str(pkg), "--definition", str(tmp_path / "no.yaml")])
    assert rc == 2
    assert "FAIL" in capsys.readouterr().err


def test_cli_build_assembly_graph_no_overwrite_by_default(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    main(["build-assembly-graph", str(pkg), "--definition", str(def_file)])
    capsys.readouterr()
    rc = main(["build-assembly-graph", str(pkg), "--definition", str(def_file)])
    assert rc == 2
    assert "FAIL" in capsys.readouterr().err


def test_cli_build_assembly_graph_overwrite(tmp_path, capsys):
    pkg = _make_package(tmp_path)
    def_file = _make_def(tmp_path)
    main(["build-assembly-graph", str(pkg), "--definition", str(def_file)])
    capsys.readouterr()
    rc = main(["build-assembly-graph", str(pkg), "--definition", str(def_file), "--overwrite"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Example definition (bracket_assembly_def.yaml)
# ---------------------------------------------------------------------------

def test_example_definition_is_valid(tmp_path):
    pkg = _make_package(tmp_path)
    example = Path(__file__).parent.parent / "examples" / "bracket_assembly_def.yaml"
    assert example.exists(), "examples/bracket_assembly_def.yaml must exist"
    result = build_assembly_graph_package(pkg, example)
    assert result == pkg
    data = _read_member(pkg, ASSEMBLY_GRAPH_PATH)
    assert data["format"] == "aieng.assembly_graph"
    part_ids = {p["part_id"] for p in data["parts"]}
    assert "bracket_001" in part_ids
    assert "baseplate_001" in part_ids
