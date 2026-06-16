"""Tests for Assembly IR v0 authoring (cad.define_part / cad.define_mate core)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.assembly_ir import (
    ASSEMBLY_IR_PATH,
    CONNECTION_GRAPH_PATH,
    PART_REGISTRY_PATH,
    define_assembly_mate,
    define_assembly_part,
    load_assembly_ir,
)


def _make_pkg(tmp_path: Path, named: tuple[str, ...] = ("base_plate", "pillar")) -> Path:
    """Minimal .aieng with a topology_map naming some solids."""
    pkg = tmp_path / "proj.aieng"
    topo = {
        "format_version": "0.1",
        "entities": [
            {"id": f"body_{i + 1:03d}", "type": "solid", "name": n, "bounding_box": [0, 0, 0, 10, 10, 10]}
            for i, n in enumerate(named)
        ],
    }
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
