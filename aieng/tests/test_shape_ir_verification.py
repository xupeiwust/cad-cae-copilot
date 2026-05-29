"""Tests for unified Shape IR verification (diagnostics/shape_ir_verification.json)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng.converters.shape_ir_verification import (
    VERIFICATION_PATH,
    verify_shape_ir_package,
    write_shape_ir_verification,
)


def _pkg(tmp_path: Path, members: dict[str, Any], name: str = "m.aieng") -> Path:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        for member, content in members.items():
            data = content if isinstance(content, (bytes, str)) else json.dumps(content)
            zf.writestr(member, data)
    return p


def _manifest(representation: str, *, requested: str | None = None, fallback: bool = False,
              executed: bool = True, backend: str = "build123d", geometry_kind: str = "brep",
              levels: tuple[int, ...] = (0, 1, 2, 3)) -> dict[str, Any]:
    m: dict[str, Any] = {
        "format_version": "0.1",
        "source": {"source_document_metadata": {
            "representation": representation,
            "requested_representation": requested or representation,
            "compile_runtime": backend,
            "representation_fallback": fallback,
        }},
        "achieved_capability_levels": [{"level": n, "name": f"L{n}"} for n in levels],
    }
    if executed:
        m["geometry_execution"] = {"executed": True, "backend": backend,
                                   "geometry_kind": geometry_kind, "real_geometry": True}
    return m


def test_verify_build123d_brep(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"parts": [{"id": "plate", "type": "box", "dimensions": [10, 10, 2]}]},
        "geometry/source.py": "from build123d import *\n# Shape IR node: plate\nresult = Box(10,10,2)\n",
        "geometry/generated.step": "ISO-10303-21;\n",
        "geometry/preview.glb": b"glTF\x00\x00",
        "geometry/topology_map.json": {"metadata": {"extractor": "build123d"}, "entities": [
            {"id": "body_001", "type": "solid"},
            {"id": "face_001", "type": "face", "surface_type": "plane"},
        ]},
        "provenance/conversion_manifest.json": _manifest("brep_build123d", backend="build123d", geometry_kind="brep"),
    })
    r = verify_shape_ir_package(pkg)
    assert r["representation_kind"] == "brep"
    assert r["geometry_kind"] == "brep" and r["executed"] is True
    assert r["lossiness"] == "none" and r["cad_editable"] is True
    assert r["capability_level"] == "L3"
    assert r["status"] == "ok"
    assert r["nodes"][0]["compiled"] is True
    assert r["artifacts"]["geometry/generated.step"] is True
    assert r["checks"]["brep_topology_not_faked"] is True


def test_verify_nurbs_brep_bspline(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "nurbs_brep",
                                   "parts": [{"id": "patch", "type": "nurbs_surface"}]},
        "geometry/source.py": "from build123d import *\n# Shape IR NURBS node: patch\n",
        "geometry/generated.step": "ISO-10303-21;\n",
        "geometry/topology_map.json": {"metadata": {"extractor": "build123d"}, "entities": [
            {"id": "body_001", "type": "solid"},
            {"id": "face_001", "type": "face", "surface_type": "bspline"},
        ]},
        "provenance/conversion_manifest.json": _manifest("nurbs_brep", backend="build123d", geometry_kind="brep"),
    })
    r = verify_shape_ir_package(pkg)
    assert r["representation_kind"] == "nurbs_brep"
    assert r["cad_editable"] is True and r["lossiness"] == "none"
    assert r["surface_type_check"]["nurbs_bspline_ok"] is True
    assert "bspline" in r["surface_type_check"]["observed_surface_types"]
    assert r["nodes"][0]["expected_surface_type"] == "bspline"
    assert r["nodes"][0]["compiled"] is True


def test_verify_implicit_sdf_mesh_not_faked(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "implicit_sdf",
                                   "parts": [{"id": "blob", "type": "sphere", "radius": 5}]},
        "geometry/sdf_source.py": "from sdf import *\n# Shape IR node: blob\nf = sphere(5)\n",
        "geometry/preview.glb": b"glTF\x00\x00",
        "geometry/topology_map.json": {"metadata": {
            "extractor": "SDFRunner", "extraction_mode": "marching_cubes_mesh", "real_step_parsing": False,
        }, "entities": [
            {"id": "body_001", "type": "solid"},
            {"id": "face_001", "type": "face", "surface_type": "freeform", "freeform": True},
        ]},
        "provenance/conversion_manifest.json": _manifest("implicit_sdf", backend="sdf", geometry_kind="mesh"),
    })
    r = verify_shape_ir_package(pkg)
    assert r["representation_kind"] == "implicit_field"
    assert r["geometry_kind"] == "mesh"
    assert r["lossiness"] == "medium" and r["cad_editable"] is False
    assert r["checks"]["brep_topology_not_faked"] is True
    assert any("region-level" in w for w in r["warnings"])
    assert r["nodes"][0]["compiled"] is True


def test_verify_manifold_mesh(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "manifold_mesh",
                                   "parts": [{"id": "b", "type": "box", "dimensions": [10, 10, 10]}]},
        "geometry/manifold_source.py": "from manifold3d import Manifold\n# Shape IR node: b\nresult = Manifold.cube((10,10,10), True)\n",
        "geometry/preview.glb": b"glTF\x00\x00",
        "geometry/topology_map.json": {"metadata": {
            "extractor": "ManifoldRunner", "extraction_mode": "manifold_csg_mesh", "real_step_parsing": False,
        }, "entities": [
            {"id": "body_001", "type": "solid"},
            {"id": "face_001", "type": "face", "surface_type": "mesh_region", "freeform": True},
        ]},
        "provenance/conversion_manifest.json": _manifest("manifold_mesh", backend="manifold", geometry_kind="mesh"),
    })
    r = verify_shape_ir_package(pkg)
    assert r["representation_kind"] == "mesh"
    assert r["geometry_kind"] == "mesh" and r["lossiness"] == "low"
    assert r["cad_editable"] is False
    assert r["checks"]["brep_topology_not_faked"] is True


def test_verify_mesh_faking_brep_is_flagged(tmp_path: Path) -> None:
    """A mesh result that presents analytic B-Rep face types must be flagged."""
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "implicit_sdf", "parts": [{"id": "x", "type": "sphere"}]},
        "geometry/sdf_source.py": "from sdf import *\n# Shape IR node: x\nf = sphere(1)\n",
        "geometry/topology_map.json": {"metadata": {
            "extractor": "SDFRunner", "extraction_mode": "marching_cubes_mesh", "real_step_parsing": False,
        }, "entities": [
            {"id": "face_001", "type": "face", "surface_type": "plane"},  # <- dishonest for a mesh
        ]},
        "provenance/conversion_manifest.json": _manifest("implicit_sdf", backend="sdf", geometry_kind="mesh"),
    })
    r = verify_shape_ir_package(pkg)
    assert r["checks"]["brep_topology_not_faked"] is False
    assert any("INTEGRITY" in w for w in r["warnings"])


def test_verify_fallback_representation(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"representation": "totally_unknown", "parts": [{"id": "n", "type": "box", "dimensions": [1, 1, 1]}]},
        "geometry/source.py": "from build123d import *\n# Shape IR node: n\nresult = Box(1,1,1)\n",
        "geometry/topology_map.json": {"metadata": {}, "entities": [{"id": "body_001", "type": "solid"}]},
        "provenance/conversion_manifest.json": _manifest(
            "brep_build123d", requested="totally_unknown", fallback=True, executed=False),
    })
    r = verify_shape_ir_package(pkg)
    assert r["fallback"] is True
    assert r["requested_representation"] == "totally_unknown"
    assert r["representation"] == "brep_build123d"
    assert r["status"] in {"fallback"}
    assert any("fell back" in w for w in r["warnings"])


def test_write_shape_ir_verification_into_package(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path, {
        "geometry/shape_ir.json": {"parts": [{"id": "plate", "type": "box", "dimensions": [10, 10, 2]}]},
        "geometry/source.py": "# Shape IR node: plate\n",
        "geometry/topology_map.json": {"metadata": {}, "entities": [{"id": "body_001", "type": "solid"}]},
        "provenance/conversion_manifest.json": _manifest("brep_build123d"),
    })
    report = write_shape_ir_verification(pkg)
    assert report["representation_kind"] == "brep"
    with zipfile.ZipFile(pkg) as zf:
        assert VERIFICATION_PATH in zf.namelist()
        written = json.loads(zf.read(VERIFICATION_PATH))
    assert written["representation"] == "brep_build123d"
    assert written["node_count"] == 1
