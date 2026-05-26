from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.cli import main
from aieng.ai.summary_writer import summarize_package
from aieng.package import create_package
from aieng.results.evidence_writer import write_evidence_scaffold_package
from aieng.simulation.mesh_evidence_importer import import_mesh_evidence_package


def _make_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "test.aieng"
    create_package("test_model", pkg)
    write_evidence_scaffold_package(pkg)
    return pkg


def _read_json_member(pkg: Path, member: str) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(member))


def _names(pkg: Path) -> set[str]:
    with zipfile.ZipFile(pkg) as zf:
        return set(zf.namelist())


def test_import_mesh_evidence_extracts_known_gmsh_counts(tmp_path: Path):
    pkg = _make_package(tmp_path)
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

    _, summary = import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )

    assert summary["detected_format"] == "gmsh"
    assert summary["nodes_declared"] == 4
    assert summary["elements_declared"] == 2


def test_import_mesh_evidence_records_summary_in_notes(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh.msh"
    mesh_file.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n", encoding="utf-8")

    import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )

    evidence_index = _read_json_member(pkg, "results/evidence_index.json")
    mesh_items = [item for item in evidence_index["evidence_items"] if item.get("evidence_type") == "mesh_evidence"]
    assert mesh_items
    notes = mesh_items[-1].get("notes", "")
    assert "[import-mesh-evidence] mesh_summary=" in notes



def test_cli_import_mesh_evidence_happy_path(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh.msh"
    mesh_file.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n", encoding="utf-8")

    rc = main(
        [
            "import-mesh-evidence",
            str(pkg),
            "--mesh-file",
            str(mesh_file),
            "--format",
            "gmsh_msh",
        ]
    )
    assert rc == 0


def test_import_mesh_evidence_extracts_known_gmsh_v4_counts(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh_v4.msh"
    mesh_file.write_text(
        """
$MeshFormat
4.1 0 8
$EndMeshFormat
$Nodes
1 4 1 4
2 1 0 4
1
2
3
4
0 0 0
1 0 0
0 1 0
0 0 1
$EndNodes
$Elements
1 2 1 2
2 1 2 2
1 1 2 3
2 1 3 4
$EndElements
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _, summary = import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )

    assert summary["detected_format"] == "gmsh"
    assert summary["format_version"] == "4.1"
    assert summary["nodes_declared"] == 4
    assert summary["elements_declared"] == 2
    assert summary["quality_metrics_present"] is False


def test_import_mesh_evidence_always_reports_quality_metrics_not_found(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh.msh"
    mesh_file.write_text(
        "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n4\n"
        "1 0 0 0\n2 1 0 0\n3 0 1 0\n4 0 0 1\n$EndNodes\n"
        "$Elements\n2\n1 2 2 0 1 1 2 3\n2 2 2 0 1 1 3 4\n$EndElements\n",
        encoding="utf-8",
    )

    _, summary = import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )

    assert "quality_metrics_not_found" in summary
    assert set(summary["quality_metrics_not_found"]) == {"min_element_quality", "max_aspect_ratio"}
    assert summary["quality_metrics_present"] is False


def test_import_mesh_evidence_non_gmsh_file_still_reports_quality_not_found(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh.msh"
    mesh_file.write_text("some mesh data without gmsh markers\n", encoding="utf-8")

    _, summary = import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )

    assert summary["detected_format"] == "unknown"
    assert set(summary["quality_metrics_not_found"]) == {"min_element_quality", "max_aspect_ratio"}


def test_import_mesh_evidence_copies_artifact_and_records_structured_payload(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh.msh"
    mesh_text = "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n1\n1 0 0 0\n$EndNodes\n$Elements\n0\n$EndElements\n"
    mesh_file.write_bytes(mesh_text.encode("utf-8"))

    import_mesh_evidence_package(
        pkg,
        mesh_file=mesh_file,
        mesh_format="gmsh_msh",
        producer_tool="gmsh",
        claim_support=["claim_mesh_evidence_001"],
    )

    artifact_path = "results/mesh_artifacts/ev_mesh_evidence_001.msh"
    assert artifact_path in _names(pkg)
    with zipfile.ZipFile(pkg) as zf:
        assert zf.read(artifact_path).decode("utf-8") == mesh_text

    evidence_index = _read_json_member(pkg, "results/evidence_index.json")
    item = next(item for item in evidence_index["evidence_items"] if item["evidence_id"] == "ev_mesh_evidence_001")
    assert item["artifact"]["path"] == artifact_path
    payload = item["structured_payload"]
    assert payload["payload_type"] == "mesh_artifact_summary"
    assert payload["mesh_format"] == "gmsh_msh"
    assert payload["parser"]["parser_id"] == "gmsh_msh_ascii_summary_v1"
    assert payload["artifact"]["storage_mode"] == "copied_into_package"
    assert payload["artifact"]["package_path"] == artifact_path
    assert payload["summary"]["nodes_declared"] == 1
    assert payload["summary"]["elements_declared"] == 0
    assert payload["summary"]["quality_metrics"]["status"] == "unknown"


def test_cli_import_mesh_evidence_reference_only_records_external_reference(tmp_path: Path):
    pkg = _make_package(tmp_path)
    mesh_file = tmp_path / "mesh.msh"
    mesh_file.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n", encoding="utf-8")

    rc = main(
        [
            "import-mesh-evidence",
            str(pkg),
            "--mesh-file",
            str(mesh_file),
            "--format",
            "gmsh_msh",
            "--reference-only",
        ]
    )

    assert rc == 0
    assert not any(name.startswith("results/mesh_artifacts/") for name in _names(pkg))
    evidence_index = _read_json_member(pkg, "results/evidence_index.json")
    item = next(item for item in evidence_index["evidence_items"] if item["evidence_id"] == "ev_mesh_evidence_001")
    assert item["artifact"]["path"] == str(mesh_file)
    assert item["structured_payload"]["artifact"]["storage_mode"] == "external_reference"
    assert item["structured_payload"]["artifact"]["external_path"] == str(mesh_file)


def test_summary_surfaces_mesh_evidence_quality_gap(tmp_path: Path):
    pkg = _make_package(tmp_path)
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

    with zipfile.ZipFile(pkg) as zf:
        summary = zf.read("ai/summary.md").decode("utf-8")

    assert "mesh evidence imports with known summaries" in summary
    assert "quality_metrics_present=False" in summary
    assert "mesh quality metrics not declared" in summary
