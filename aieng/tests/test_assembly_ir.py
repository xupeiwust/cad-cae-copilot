"""Tests for Assembly IR v0 — representation, validation, registry, connection graph,
and the solver-neutral CAE setup draft. No solver execution, no contact/bolt-preload physics.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.assembly_ir import (
    ASSEMBLY_CAE_DRAFT_PATH,
    ASSEMBLY_IR_PATH,
    ASSEMBLY_VALIDATION_PATH,
    CONNECTION_GRAPH_PATH,
    PART_REGISTRY_PATH,
    build_assembly_cae_setup_draft,
    build_connection_graph,
    build_part_registry,
    process_assembly_package,
    validate_assembly_ir,
)


def _two_part_assembly(**overrides):
    asm = {
        "format": "aieng.assembly_ir", "schema_version": "0.1", "unit": "mm",
        "parts": [
            {"id": "bracket", "name": "Bracket", "role": "design_part",
             "geometry_ref": "geometry/bracket.step",
             "transform": {"translation": [0, 0, 0], "rotation_euler_deg": [0, 0, 0], "unit": "mm"},
             "material": "AlSi10Mg"},
            {"id": "wall", "name": "Mounting wall", "role": "reference_part",
             "geometry_ref": "geometry/wall.step",
             "transform": {"translation": [0, 0, -5], "unit": "mm"},
             "material": "Steel"},
        ],
        "interfaces": [
            {"id": "iface_bracket_mount", "part_id": "bracket", "semantic_role": "mounting_face",
             "topology_refs": {"face_ids": ["f_back_001"]}},
            {"id": "iface_wall_mount", "part_id": "wall", "semantic_role": "support_face",
             "topology_refs": {"face_ids": ["f_front_002"]}},
        ],
        "connections": [
            {"id": "conn_bolted", "type": "bolted_proxy", "part_a": "bracket", "part_b": "wall",
             "interface_a": "iface_bracket_mount", "interface_b": "iface_wall_mount",
             "behavior": ["load_transfer", "preserve_interface"], "confidence": "medium",
             "limitations": ["No bolt preload; modeled as rigid tie over the mating face."]},
        ],
        "analysis_intent": {"design_parts": ["bracket"], "frozen_parts": ["wall"],
                            "preserve_interfaces": ["iface_bracket_mount"]},
        "provenance": {"created_by": "test", "assumptions": ["coincident mating faces"]},
    }
    asm.update(overrides)
    return asm


# ── Part B: validation ─────────────────────────────────────────────────────────

def test_valid_two_part_assembly_passes():
    v = validate_assembly_ir(_two_part_assembly())
    assert v["status"] == "passed", v["errors"] + v["warnings"]
    assert not v["errors"]
    assert v["summary"]["part_count"] == 2 and v["summary"]["connection_count"] == 1
    assert v["summary"]["design_part_count"] == 1
    # topology refs are reported, not silently trusted
    assert v["summary"]["unresolved_ref_count"] == 2 and len(v["unresolved_refs"]) == 2


def test_duplicate_part_id_fails():
    asm = _two_part_assembly()
    asm["parts"][1]["id"] = "bracket"
    v = validate_assembly_ir(asm)
    assert v["status"] == "failed"
    assert any("duplicate part id" in e for e in v["errors"])


def test_missing_connection_target_fails():
    asm = _two_part_assembly()
    asm["connections"][0]["part_b"] = "ghost"
    v = validate_assembly_ir(asm)
    assert v["status"] == "failed"
    assert any("unknown part 'ghost'" in e for e in v["errors"])


def test_unresolved_topology_refs_recorded():
    v = validate_assembly_ir(_two_part_assembly())
    tokens = v["unresolved_refs"]
    assert any("f_back_001" in t for t in tokens)
    assert any("f_front_002" in t for t in tokens)


def test_proxy_without_limitations_warns():
    asm = _two_part_assembly()
    asm["connections"][0].pop("limitations")
    v = validate_assembly_ir(asm)
    assert v["status"] == "warning"
    assert any("declares no limitations" in w for w in v["warnings"])


def test_no_design_parts_fails():
    asm = _two_part_assembly()
    asm["parts"][0]["role"] = "reference_part"
    asm["analysis_intent"] = {}
    v = validate_assembly_ir(asm)
    assert v["status"] == "failed"
    assert any("no design parts" in e for e in v["errors"])


def test_unrecognized_connection_type_flagged():
    asm = _two_part_assembly()
    asm["connections"][0]["type"] = "magnetic_proxy"
    v = validate_assembly_ir(asm)
    assert "magnetic_proxy" in v["unsupported_connection_types"]
    assert any("unrecognized type" in w for w in v["warnings"])


def test_design_part_missing_geometry_errors():
    asm = _two_part_assembly()
    asm["parts"][0].pop("geometry_ref")
    v = validate_assembly_ir(asm)
    assert v["status"] == "failed"
    assert any("design part 'bracket' has no geometry_ref" in e for e in v["errors"])


def test_non_dict_assembly_fails_cleanly():
    v = validate_assembly_ir("not an object")
    assert v["status"] == "failed" and v["errors"]


# ── Part C: registry + connection graph ──────────────────────────────────────

def test_registry_two_entries_editability():
    reg = build_part_registry(_two_part_assembly())
    assert len(reg["parts"]) == 2
    by_id = {p["part_id"]: p for p in reg["parts"]}
    assert by_id["bracket"]["editable"] is True       # design_part
    assert by_id["wall"]["editable"] is False         # reference_part
    assert by_id["bracket"]["topology_available"] is True
    assert by_id["bracket"]["topology_refs_present"] is True
    assert reg["provenance"]["is_proxy_model"] is True


def test_registry_explicit_editable_override():
    asm = _two_part_assembly()
    asm["parts"][1]["editable"] = True   # explicit override on a reference part
    reg = build_part_registry(asm)
    assert {p["part_id"]: p["editable"] for p in reg["parts"]}["wall"] is True


def test_connection_graph_one_edge_proxy():
    g = build_connection_graph(_two_part_assembly())
    assert len(g["nodes"]) == 2 and len(g["edges"]) == 1
    edge = g["edges"][0]
    assert edge["type"] == "bolted_proxy" and edge["is_proxy"] is True
    assert edge["load_transfer"] is True
    assert edge["part_a"] == "bracket" and edge["part_b"] == "wall"
    assert g["provenance"]["contact_physics_modeled"] is False


def test_positioning_only_connection_no_load_transfer():
    asm = _two_part_assembly()
    asm["connections"][0]["type"] = "rigid_tie"
    asm["connections"][0]["behavior"] = ["positioning_only"]
    g = build_connection_graph(asm)
    assert g["edges"][0]["load_transfer"] is False


# ── Part D: CAE setup draft ──────────────────────────────────────────────────

def test_rigid_tie_produces_tie_draft():
    asm = _two_part_assembly()
    asm["connections"][0]["type"] = "rigid_tie"
    d = build_assembly_cae_setup_draft(asm)
    assert d["status"] == "draft"
    c = d["connections"][0]
    assert c["draft_type"] == "tie_constraint" and c["supported"] is True


def test_bolted_proxy_draft_has_limitation():
    d = build_assembly_cae_setup_draft(_two_part_assembly())
    c = d["connections"][0]
    assert c["draft_type"] == "connector_proxy" and c["supported"] is True
    assert c["limitations"]  # carried from the IR


def test_contact_proxy_unsupported_warns():
    asm = _two_part_assembly()
    asm["connections"][0]["type"] = "contact_proxy"
    d = build_assembly_cae_setup_draft(asm)
    c = d["connections"][0]
    assert c["draft_type"] == "contact_unsupported" and c["supported"] is False
    assert c.get("draft_only") is True
    assert any("unsupported/draft-only" in w for w in d["warnings"])


def test_missing_interface_needs_user_input():
    asm = _two_part_assembly()
    asm["connections"][0].pop("interface_a")
    asm["connections"][0].pop("interface_b")
    d = build_assembly_cae_setup_draft(asm)
    assert d["status"] == "needs_user_input"
    assert any("missing interface_a/interface_b" in n for n in d["needs_user_input"])


def test_draft_preserves_design_and_frozen():
    d = build_assembly_cae_setup_draft(_two_part_assembly())
    by_id = {p["part_id"]: p for p in d["parts"]}
    assert by_id["bracket"]["frozen"] is False and by_id["bracket"]["editable"] is True
    assert by_id["wall"]["frozen"] is True
    assert "iface_bracket_mount" in d["preserve_interfaces"]
    assert d["materials"] == {"bracket": "AlSi10Mg", "wall": "Steel"}
    assert d["supports"] and d["provenance"]["solver_executed"] is False


# ── Part E: package integration ──────────────────────────────────────────────

def _write_package(tmp_path: Path, *, with_assembly: bool, assembly=None) -> Path:
    pkg = tmp_path / "asm.aieng"
    manifest = {"format": "aieng.conversion_manifest",
                "geometry_execution": {"executed": True, "geometry_kind": "brep"}}
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "Assembly"}))
        zf.writestr("provenance/conversion_manifest.json", json.dumps(manifest))
        if with_assembly:
            zf.writestr(ASSEMBLY_IR_PATH, json.dumps(assembly or _two_part_assembly()))
    return pkg


def test_package_without_assembly_unchanged(tmp_path: Path):
    pkg = _write_package(tmp_path, with_assembly=False)
    before = set(zipfile.ZipFile(pkg).namelist())
    result = process_assembly_package(pkg)
    after = set(zipfile.ZipFile(pkg).namelist())
    assert result["assembly_present"] is False
    assert before == after  # no new artifacts written


def test_package_with_assembly_writes_artifacts(tmp_path: Path):
    pkg = _write_package(tmp_path, with_assembly=True)
    result = process_assembly_package(pkg)
    assert result["assembly_present"] is True and result["validation_status"] == "passed"
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        for art in (ASSEMBLY_VALIDATION_PATH, PART_REGISTRY_PATH,
                    CONNECTION_GRAPH_PATH, ASSEMBLY_CAE_DRAFT_PATH):
            assert art in names
        # no solver-specific files produced
        assert not any(n.lower().endswith((".inp", ".frd", ".step", ".stp")) for n in names)
        manifest = json.loads(zf.read("provenance/conversion_manifest.json"))
        assert manifest["assembly"]["present"] is True
        assert manifest["assembly"]["solver_executed"] is False


def test_invalid_assembly_degrades_honestly(tmp_path: Path):
    bad = _two_part_assembly()
    bad["parts"][1]["id"] = "bracket"   # duplicate id -> validation failed
    pkg = _write_package(tmp_path, with_assembly=True, assembly=bad)
    result = process_assembly_package(pkg)
    assert result["assembly_present"] is True
    assert result["validation_status"] == "failed"
    with zipfile.ZipFile(pkg) as zf:
        v = json.loads(zf.read(ASSEMBLY_VALIDATION_PATH))
        assert v["status"] == "failed" and v["errors"]
        # artifacts still written despite invalid input (honest degradation, no crash)
        assert PART_REGISTRY_PATH in zf.namelist()
