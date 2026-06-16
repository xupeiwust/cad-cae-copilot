"""Tests for Assembly IR v0 authoring (cad.define_part / cad.define_mate core)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.assembly_ir import (
    ASSEMBLY_IR_PATH,
    CONNECTION_GRAPH_PATH,
    PART_REGISTRY_PATH,
    define_assembly_interface,
    define_assembly_mate,
    define_assembly_part,
    load_assembly_ir,
)


def _make_pkg(tmp_path: Path, named: tuple[str, ...] = ("base_plate", "pillar")) -> Path:
    """Minimal .aieng with a topology_map naming some solids, each with one face."""
    pkg = tmp_path / "proj.aieng"
    entities: list[dict] = []
    for i, n in enumerate(named):
        bid = f"body_{i + 1:03d}"
        entities.append({"id": bid, "type": "solid", "name": n, "bounding_box": [0, 0, 0, 10, 10, 10]})
        # one planar face per solid so interfaces have a B-Rep entity to bind to
        entities.append({
            "id": f"face_{i + 1:03d}", "type": "face", "body_id": bid, "surface_type": "plane",
            "bounding_box": [0, 0, 0, 10, 10, 0], "center": [5, 5, 0], "normal": [0, 0, 1],
        })
    topo = {"format_version": "0.1", "entities": entities}
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "p"}))
        zf.writestr("geometry/topology_map.json", json.dumps(topo))
    return pkg


def test_define_part_links_named_geometry(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    out = define_assembly_part(pkg, geometry_ref="base_plate", role="design_part")
    assert out["status"] == "ok"
    assert out["geometry_ref_known"] is True
    assert out["part"]["id"] == "base_plate"
    air = load_assembly_ir(pkg)
    assert any(p["id"] == "base_plate" for p in air["parts"])


def test_define_part_unresolved_ref_is_honest_false(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    out = define_assembly_part(pkg, part_id="ghost", geometry_ref="ghost")
    assert out["status"] == "ok"
    assert out["geometry_ref_known"] is False  # index exists, value absent -> not found (never fabricated)


def test_define_part_no_topology_is_unverified_none(tmp_path: Path) -> None:
    pkg = tmp_path / "empty.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", "{}")
    out = define_assembly_part(pkg, part_id="x")
    assert out["status"] == "ok"
    assert out["geometry_ref_known"] is None  # no index -> unverified, not a false negative


def test_define_part_rejects_bad_role(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    out = define_assembly_part(pkg, part_id="p", role="sidekick")
    assert out["status"] == "error"
    assert out["code"] == "bad_role"


def test_define_mate_requires_existing_parts(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    out = define_assembly_mate(pkg, connection_type="bolted_proxy", part_a="base_plate", part_b="pillar")
    assert out["status"] == "error"
    assert out["code"] == "unknown_parts"
    assert "pillar" in out["message"]


def test_define_mate_proxy_autofills_limitations(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    define_assembly_part(pkg, geometry_ref="pillar")
    out = define_assembly_mate(pkg, connection_type="bolted_proxy", part_a="base_plate", part_b="pillar")
    assert out["status"] == "ok"
    assert out["is_proxy"] is True
    assert out["connection"]["limitations"]  # never recorded without honest limitations
    air = load_assembly_ir(pkg)
    assert len(air["connections"]) == 1


def test_define_mate_rejects_bad_type_and_self(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    define_assembly_part(pkg, geometry_ref="pillar")
    bad = define_assembly_mate(pkg, connection_type="glue", part_a="base_plate", part_b="pillar")
    assert bad["status"] == "error" and bad["code"] == "bad_type"
    selfc = define_assembly_mate(pkg, connection_type="rigid_tie", part_a="base_plate", part_b="base_plate")
    assert selfc["status"] == "error" and selfc["code"] == "self_connection"


def test_define_interface_links_faces(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    out = define_assembly_interface(pkg, part_id="base_plate", semantic_role="mounting_face", face_ids=["face_001"])
    assert out["status"] == "ok"
    assert out["face_ids_known"] is True
    assert out["interface"]["part_id"] == "base_plate"
    assert out["interface"]["topology_refs"]["face_ids"] == ["face_001"]
    # interfaces present -> geometry resolution ran -> a per-interface status exists
    assert out["resolution_status"] in {"resolved", "partially_resolved", "unresolved"}


def test_define_interface_unknown_face_is_honest_false(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    out = define_assembly_interface(pkg, part_id="base_plate", semantic_role="mounting_face", face_ids=["face_999"])
    assert out["status"] == "ok"
    assert out["face_ids_known"] is False
    assert "face_999" in out["unknown_face_ids"]


def test_define_interface_requires_known_part_and_refs(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    bad_part = define_assembly_interface(pkg, part_id="ghost", semantic_role="mounting_face", face_ids=["face_001"])
    assert bad_part["status"] == "error" and bad_part["code"] == "unknown_part"
    define_assembly_part(pkg, geometry_ref="base_plate")
    bad_role = define_assembly_interface(pkg, part_id="base_plate", semantic_role="glue", face_ids=["face_001"])
    assert bad_role["code"] == "bad_role"
    no_refs = define_assembly_interface(pkg, part_id="base_plate", semantic_role="mounting_face")
    assert no_refs["code"] == "missing_refs"


def test_mate_with_interfaces_gets_geometry_status(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    define_assembly_part(pkg, geometry_ref="pillar")
    define_assembly_interface(pkg, part_id="base_plate", semantic_role="mounting_face",
                              face_ids=["face_001"], interface_id="if_a")
    define_assembly_interface(pkg, part_id="pillar", semantic_role="mounting_face",
                              face_ids=["face_002"], interface_id="if_b")
    mate = define_assembly_mate(
        pkg, connection_type="bolted_proxy", part_a="base_plate", part_b="pillar",
        interface_a="if_a", interface_b="if_b",
    )
    assert mate["status"] == "ok"
    assert mate["connection_geometry"] is not None
    assert mate["connection_geometry"]["geometry_status"] in {
        "plausible", "warning", "invalid", "insufficient_data",
    }


def test_authoring_refreshes_derived_artifacts(tmp_path: Path) -> None:
    pkg = _make_pkg(tmp_path)
    define_assembly_part(pkg, geometry_ref="base_plate")
    define_assembly_part(pkg, geometry_ref="pillar")
    out = define_assembly_mate(pkg, connection_type="rigid_tie", part_a="base_plate", part_b="pillar")
    assert out["processed"]["assembly_present"] is True
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
    assert ASSEMBLY_IR_PATH in names
    assert PART_REGISTRY_PATH in names
    assert CONNECTION_GRAPH_PATH in names
