from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from aieng.ai.summary_writer import summarize_package
from aieng.cli import main
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.results.evidence_writer import write_evidence_scaffold_package
from aieng.simulation.mesh_evidence_importer import import_mesh_evidence_package
from aieng.validate import Level, validate_package
from aieng.validation.completeness_writer import write_completeness_report_package

FAKE_STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def _read_json(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _names(pkg: Path) -> set[str]:
    with zipfile.ZipFile(pkg) as zf:
        return set(zf.namelist())


def _pkg_with_topology(tmp_path: Path) -> Path:
    step = tmp_path / "part.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "part.aieng"
    import_step_package(step, pkg)
    extract_topology_package(pkg, backend="mock")
    return pkg


def test_write_mesh_handoff_cli_writes_resource_and_manifest(tmp_path, capsys):
    pkg = _pkg_with_topology(tmp_path)
    write_evidence_scaffold_package(pkg)

    assert main(["write-mesh-handoff", str(pkg)]) == 0
    out = capsys.readouterr().out
    assert "PASS wrote mesh handoff contract" in out
    assert "simulation/mesh_handoff_contract.json" in _names(pkg)

    manifest = _read_json(pkg, "manifest.json")
    assert manifest["resources"]["simulation"]["mesh_handoff_contract"] == "simulation/mesh_handoff_contract.json"


def test_write_mesh_handoff_requires_topology_map(tmp_path, capsys):
    step = tmp_path / "part.step"
    step.write_bytes(FAKE_STEP)
    pkg = tmp_path / "part.aieng"
    import_step_package(step, pkg)

    assert main(["write-mesh-handoff", str(pkg)]) == 2
    err = capsys.readouterr().err
    assert "topology_map" in err


def test_mesh_handoff_schema_and_validate_pass(tmp_path):
    pkg = _pkg_with_topology(tmp_path)
    write_evidence_scaffold_package(pkg)
    assert main(["write-mesh-handoff", str(pkg)]) == 0

    report = validate_package(pkg)
    mesh_fails = [m for m in report.messages if m.level is Level.FAIL and "mesh_handoff" in m.text]
    assert not mesh_fails
    mesh_claim_warnings = [m for m in report.messages if m.level.name == "WARN" and "target_claim_ids" in m.text]
    assert not mesh_claim_warnings


def test_mesh_handoff_validate_fails_unknown_face_reference(tmp_path):
    pkg = _pkg_with_topology(tmp_path)
    write_evidence_scaffold_package(pkg)
    assert main(["write-mesh-handoff", str(pkg)]) == 0

    contract = _read_json(pkg, "simulation/mesh_handoff_contract.json")
    contract["topology_refs"]["face_ids"].append("face_999")

    with zipfile.ZipFile(pkg, "r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != "simulation/mesh_handoff_contract.json"
        ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=tmp_path) as fh:
        tmp_pkg = Path(fh.name)

    try:
        with zipfile.ZipFile(tmp_pkg, "w") as zf:
            for info, data in members:
                zf.writestr(info, data)
            zf.writestr("simulation/mesh_handoff_contract.json", json.dumps(contract, indent=2).encode("utf-8"))
        shutil.move(str(tmp_pkg), str(pkg))
    finally:
        if tmp_pkg.exists():
            tmp_pkg.unlink()

    report = validate_package(pkg)
    assert any(m.level is Level.FAIL and "unknown face IDs" in m.text for m in report.messages)


def test_completeness_includes_mesh_handoff_and_real_geometry_flag(tmp_path):
    pkg = _pkg_with_topology(tmp_path)
    write_completeness_report_package(pkg)
    completeness = _read_json(pkg, "validation/completeness_report.json")

    categories = {c["category"]: c for c in completeness["categories"]}
    assert "mesh_handoff_contract" in categories
    assert categories["mesh_handoff_contract"]["status"] == "missing"
    assert completeness["real_geometry_extraction"] is False


def test_completeness_real_geometry_extraction_true_when_occ_metadata_present(tmp_path):
    pkg = _pkg_with_topology(tmp_path)

    topology = _read_json(pkg, "geometry/topology_map.json")
    topology.setdefault("metadata", {})["extraction_backend"] = "occ"
    topology["metadata"]["real_step_parsing"] = True

    with zipfile.ZipFile(pkg, "r") as zf:
        members = [
            (info, b"" if info.is_dir() else zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != "geometry/topology_map.json"
        ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=tmp_path) as fh:
        tmp_pkg = Path(fh.name)

    try:
        with zipfile.ZipFile(tmp_pkg, "w") as zf:
            for info, data in members:
                zf.writestr(info, data)
            zf.writestr("geometry/topology_map.json", json.dumps(topology, indent=2).encode("utf-8"))
        shutil.move(str(tmp_pkg), str(pkg))
    finally:
        if tmp_pkg.exists():
            tmp_pkg.unlink()

    write_completeness_report_package(pkg)
    completeness = _read_json(pkg, "validation/completeness_report.json")
    assert completeness["real_geometry_extraction"] is True



def test_mesh_handoff_roundtrip_with_mesh_evidence_import_and_summary(tmp_path):
    pkg = _pkg_with_topology(tmp_path)
    write_evidence_scaffold_package(pkg)

    assert main(["write-mesh-handoff", str(pkg)]) == 0

    mesh_file = tmp_path / "mesh.msh"
    mesh_file.write_text(
        """
$MeshFormat
2.2 0 8
$EndMeshFormat
$Nodes
4
1 0 0 0
2 1 0 0
3 0 1 0
4 0 0 1
$EndNodes
$Elements
2
1 2 2 0 1 1 2 3
2 2 2 0 1 1 3 4
$EndElements
""".strip()
        + "\n",
        encoding="utf-8",
    )

    import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )
    summarize_package(pkg)

    report = validate_package(pkg)
    assert not [m for m in report.messages if m.level is Level.FAIL and "mesh_handoff" in m.text]

    with zipfile.ZipFile(pkg) as zf:
        summary = zf.read("ai/summary.md").decode("utf-8")
    assert "mesh evidence imports with known summaries" in summary
    assert "quality_metrics_present=False" in summary
