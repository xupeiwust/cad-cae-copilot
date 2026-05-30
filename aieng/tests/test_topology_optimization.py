"""Tests for topology optimization (contract + pluggable optimizer + 2D SIMP)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.shape_ir import (  # noqa: E402
    compile_shape_ir,
    compile_shape_ir_to_build123d_source,
    density_voxel_cells,
)
from aieng.converters.shape_ir_manifold import (  # noqa: E402
    compile_shape_ir_to_manifold_source,
)
from aieng.converters.topology_optimization import (  # noqa: E402
    SHAPE_IR_PATH,
    TOPOLOGY_OPTIMIZATION_PATH,
    available_optimizers,
    run_topology_optimization,
    simp_2d,
    topology_result_to_shape_ir,
    write_shape_ir_from_topology_optimization,
    write_topology_optimization,
)


def test_simp_2d_reduces_compliance_and_meets_volume():
    out = simp_2d({"grid": {"nelx": 24, "nely": 8}, "volfrac": 0.5,
                   "max_iters": 20, "bcs": {"preset": "cantilever"}})
    hist = out["compliance_history"]
    assert len(hist) > 1
    assert hist[-1] < hist[0]                       # optimization lowered compliance
    assert all(h > 0 for h in hist)
    assert abs(out["achieved_volume_fraction"] - 0.5) < 0.05   # volume budget respected
    dens = out["density"]
    assert len(dens) == 8 and len(dens[0]) == 24    # nely x nelx
    assert all(0.0 <= v <= 1.0 for row in dens for v in row)
    assert out["iterations"] > 0


def test_run_topology_optimization_contract_and_provenance():
    res = run_topology_optimization(
        {"grid": {"nelx": 20, "nely": 8}, "volfrac": 0.4, "max_iters": 12,
         "design_space_node": "bracket_body"},
        optimizer="simp_2d",
    )
    assert res["format"] == "aieng.topology_optimization"
    assert res["optimizer"]["name"] == "simp_2d" and res["optimizer"]["dimension"] == 2
    assert res["objective"] == "compliance_minimization"
    assert res["problem"]["design_space_node"] == "bracket_body"
    assert res["provenance"]["design_space_node"] == "bracket_body"
    assert res["result"]["density_grid"]["nrows"] == 8 and res["result"]["density_grid"]["ncols"] == 20
    assert res["result"]["solid_element_count"] >= 0
    assert res["limitations"]  # honest scope recorded


def test_precomputed_optimizer_is_neutral():
    """A non-SIMP optimizer flows through the same contract — proves neutrality."""
    grid = [[0.0, 1.0, 1.0], [1.0, 1.0, 0.0]]
    res = run_topology_optimization(
        {"density": grid, "volfrac": 0.66, "compliance_history": [9.9],
         "final_compliance": 9.9, "design_space_node": "n1"},
        optimizer="precomputed",
    )
    assert res["optimizer"]["name"] == "precomputed" and res["optimizer"]["fallback"] is False
    assert res["result"]["density_grid"]["values"] == grid
    assert res["result"]["final_compliance"] == 9.9


def test_optimizer_registry_and_fallback():
    assert {"simp_2d", "precomputed"} <= set(available_optimizers())
    # unknown optimizer -> falls back to simp_2d and records it
    res = run_topology_optimization({"grid": {"nelx": 12, "nely": 6}, "volfrac": 0.5, "max_iters": 6},
                                    optimizer="does_not_exist")
    assert res["optimizer"]["name"] == "simp_2d" and res["optimizer"]["fallback"] is True
    assert res["optimizer"]["requested"] == "does_not_exist"


# ── writeback: optimization result -> Shape IR representation ────────────────

_TOPO = {
    "format": "aieng.topology_optimization",
    "contract_version": "0.1",
    "optimizer": {"name": "simp_2d"},
    "objective": "compliance_minimization",
    "problem": {"design_space_node": "bracket_body"},
    "provenance": {"design_space_node": "bracket_body"},
    "result": {
        "threshold": 0.5,
        "final_compliance": 12.3,
        "achieved_volume_fraction": 0.5,
        "density_grid": {"nrows": 2, "ncols": 3,
                         "values": [[0.9, 0.1, 0.8], [0.2, 0.95, 0.7]]},
    },
}


def test_density_voxel_cells_thresholds_and_places():
    node = {"type": "density_voxels", "density": [[0.9, 0.1], [0.2, 0.8]],
            "threshold": 0.5, "cell_size": [2.0, 2.0], "thickness": 3.0, "origin": [0, 0, 0]}
    cells, (sx, sy, sz) = density_voxel_cells(node)
    assert (sx, sy, sz) == (2.0, 2.0, 3.0)
    # 2 cells above threshold: (row0,col0) and (row1,col1); centres in XY, z=sz/2
    assert [1.0, 1.0, 1.5] in cells and [3.0, 3.0, 1.5] in cells
    assert len(cells) == 2


def test_topology_result_to_shape_ir_payload():
    payload = topology_result_to_shape_ir(_TOPO, representation="manifold_mesh")
    assert payload["representation"] == "manifold_mesh"
    assert payload["provenance"]["from_topology_optimization"] is True
    assert payload["provenance"]["design_space_node"] == "bracket_body"
    (node,) = payload["parts"]
    assert node["type"] == "density_voxels"
    assert node["id"] == "optimized_bracket_body"
    assert node["density"] == _TOPO["result"]["density_grid"]["values"]
    assert node["threshold"] == 0.5
    assert node["source_optimization"]["design_space_node"] == "bracket_body"


def test_density_voxels_compiles_in_both_backends():
    payload = topology_result_to_shape_ir(_TOPO, representation="manifold_mesh")
    # manifold: a CSG union loop over baked cell centres -> watertight mesh
    msrc = compile_shape_ir_to_manifold_source(payload)
    assert "Manifold.cube" in msrc and "for _c in" in msrc
    assert "result =" in msrc
    # build123d: a Compound of extruded boxes, one labelled named part
    bsrc = compile_shape_ir_to_build123d_source(payload)
    assert "Box(" in bsrc and "Compound(children=" in bsrc
    assert ".label = " in bsrc and "optimized_bracket_body" in bsrc
    # dispatcher routes manifold_mesh to the manifold runtime
    dispatched = compile_shape_ir(payload)
    assert dispatched["representation"] == "manifold_mesh"
    assert "Manifold.cube" in dispatched["source"]


def test_write_shape_ir_from_topology_optimization_into_package(tmp_path: Path):
    pkg = tmp_path / "opt.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "opt"}))
        zf.writestr(TOPOLOGY_OPTIMIZATION_PATH, json.dumps(_TOPO))
    payload = write_shape_ir_from_topology_optimization(pkg, representation="manifold_mesh")
    assert payload["parts"][0]["type"] == "density_voxels"
    with zipfile.ZipFile(pkg) as zf:
        assert SHAPE_IR_PATH in zf.namelist()
        loaded = json.loads(zf.read(SHAPE_IR_PATH))
    assert loaded["representation"] == "manifold_mesh"
    assert loaded["provenance"]["design_space_node"] == "bracket_body"


def test_write_shape_ir_requires_prior_optimization(tmp_path: Path):
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", "{}")
    with pytest.raises(FileNotFoundError):
        write_shape_ir_from_topology_optimization(pkg)


def test_write_topology_optimization_into_package(tmp_path: Path):
    pkg = tmp_path / "m.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/shape_ir.json", json.dumps({"parts": [{"id": "plate", "type": "box"}]}))
    res = write_topology_optimization(
        pkg, {"density": [[1.0, 0.0], [0.0, 1.0]], "design_space_node": "plate"},
        optimizer="precomputed",
    )
    assert res["result"]["density_grid"]["values"] == [[1.0, 0.0], [0.0, 1.0]]
    with zipfile.ZipFile(pkg) as zf:
        assert TOPOLOGY_OPTIMIZATION_PATH in zf.namelist()
        loaded = json.loads(zf.read(TOPOLOGY_OPTIMIZATION_PATH))
    assert loaded["optimizer"]["name"] == "precomputed"
    assert loaded["provenance"]["design_space_node"] == "plate"
