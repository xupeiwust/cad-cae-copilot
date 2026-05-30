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
    extruded_region_geometry,
    sample_periodic_catmull_rom,
)
from aieng.converters.shape_ir_manifold import (  # noqa: E402
    compile_shape_ir_to_manifold_source,
)
from aieng.converters.topology_optimization import (  # noqa: E402
    SHAPE_IR_PATH,
    TOPOLOGY_OPTIMIZATION_PATH,
    available_optimizers,
    derive_topopt_problem_from_package,
    extract_density_contours,
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


_TOPO_FRAMED = {
    **_TOPO,
    "problem": {
        "design_space_node": "plate",
        "derivation": {"frame": {
            "origin": [5.0, 10.0, 0.0], "u_axis": "x", "v_axis": "y",
            "cell_size": [40.0, 40.0], "thickness": 10.0}},
    },
}


def test_density_voxel_cells_respects_frame_axes():
    # XZ plane: u=x, v=z, extruded along y; origin offset baked in.
    node = {"type": "density_voxels", "density": [[1.0, 0.0]],
            "threshold": 0.5, "cell_size": [2.0, 3.0], "thickness": 4.0,
            "origin": [10.0, 20.0, 30.0], "u_axis": "x", "v_axis": "z"}
    cells, size = density_voxel_cells(node)
    assert size == (2.0, 4.0, 3.0)            # world x=su, y=thickness, z=sv
    assert cells == [[11.0, 22.0, 31.5]]      # x=10+1, z=30+1.5, y=20+2


def test_topology_result_to_shape_ir_uses_frame():
    payload = topology_result_to_shape_ir(_TOPO_FRAMED)
    node = payload["parts"][0]
    assert node["placed_in_frame"] is True
    assert node["origin"] == [5.0, 10.0, 0.0]
    assert node["cell_size"] == [40.0, 40.0] and node["thickness"] == 10.0
    assert node["u_axis"] == "x" and node["v_axis"] == "y"


def test_topology_result_to_shape_ir_explicit_args_override_frame():
    payload = topology_result_to_shape_ir(_TOPO_FRAMED, cell_size=(2.0, 2.0), origin=(0.0, 0.0, 0.0))
    node = payload["parts"][0]
    assert node["cell_size"] == [2.0, 2.0] and node["origin"] == [0.0, 0.0, 0.0]


def test_topology_result_to_shape_ir_no_frame_defaults_to_unit_grid():
    node = topology_result_to_shape_ir(_TOPO)["parts"][0]   # _TOPO has no derivation frame
    assert node["placed_in_frame"] is False
    assert node["cell_size"] == [1.0, 1.0] and node["origin"] == [0.0, 0.0, 0.0]


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


# ── contour-ized writeback (smooth boundary instead of voxels) ───────────────

def test_extract_density_contours_returns_world_polygons():
    pytest.importorskip("skimage")
    # a solid 3x3 block in the middle of a 5x5 field -> one closed loop
    grid = [[0, 0, 0, 0, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 0, 0, 0, 0]]
    polys = extract_density_contours(grid, 0.5, origin_u=0.0, origin_v=0.0, su=2.0, sv=2.0)
    assert len(polys) == 1
    loop = polys[0]
    assert len(loop) >= 4 and loop[0] == loop[-1]          # closed
    xs = [p[0] for p in loop]; ys = [p[1] for p in loop]
    # the loop hugs the solid block (cols/rows 1..3 -> world ~[1,7] at cell centres)
    assert min(xs) >= 0.0 and max(xs) <= 10.0 and min(ys) >= 0.0 and max(ys) <= 10.0


def test_extruded_region_geometry_bakes_plane_and_holes():
    # XY plane: sign_v=+1, no flip; an outer square with an inner square hole
    node = {"type": "extruded_region", "u_axis": "x", "v_axis": "y", "thickness": 5.0,
            "origin": [0, 0, 2],
            "polygons": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                         [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]]]}
    g = extruded_region_geometry(node)
    assert g["thickness"] == 5.0 and g["base"] == [0.0, 0.0, 2.0]   # base offset on w=z
    assert g["w_vec"] == [0.0, 0.0, 1.0]
    roles = sorted(is_hole for _pts, is_hole in g["classified"])
    assert roles == [False, True]                                   # one solid, one hole


def test_extruded_region_geometry_flips_v_on_xz_plane():
    # XZ plane: y_dir = w×u = (0,1,0)×(1,0,0) = (0,0,-1) = -v -> sign_v=-1
    node = {"type": "extruded_region", "u_axis": "x", "v_axis": "z", "thickness": 4.0,
            "origin": [0, 6, 0], "polygons": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
    g = extruded_region_geometry(node)
    assert g["base"] == [0.0, 6.0, 0.0] and g["w_vec"] == [0.0, 1.0, 0.0]
    # local v-coordinates are negated so the body lands on +z after the affine
    assert all(pt[1] <= 0 for pt in g["local_polys"][0])


def test_contour_writeback_emits_extruded_region_and_compiles():
    pytest.importorskip("skimage")
    framed = {**_TOPO_FRAMED, "result": {"threshold": 0.5, "density_grid": {
        "nrows": 5, "ncols": 5,
        "values": [[0, 0, 0, 0, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 0, 0, 0, 0]]}}}
    payload = topology_result_to_shape_ir(framed, method="contour")
    node = payload["parts"][0]
    assert node["type"] == "extruded_region" and node["polygons"]
    assert node["placed_in_frame"] is True
    msrc = compile_shape_ir_to_manifold_source(payload)
    assert "CrossSection" in msrc and ".transform(" in msrc
    bsrc = compile_shape_ir_to_build123d_source(payload)
    assert "BuildSketch(Plane(" in bsrc and "extrude(amount=" in bsrc


def test_contour_writeback_falls_back_to_voxels_when_empty():
    pytest.importorskip("skimage")
    empty = {**_TOPO_FRAMED, "result": {"threshold": 0.5,
             "density_grid": {"nrows": 2, "ncols": 2, "values": [[0.0, 0.0], [0.0, 0.0]]}}}
    node = topology_result_to_shape_ir(empty, method="contour")["parts"][0]
    assert node["type"] == "density_voxels"                          # honest fallback
    assert "contour_fallback" in node["source_optimization"]


def test_contour_executes_in_manifold_within_design_space(tmp_path: Path):
    pytest.importorskip("skimage")
    pytest.importorskip("manifold3d")
    framed = {**_TOPO_FRAMED, "result": {"threshold": 0.5, "density_grid": {
        "nrows": 5, "ncols": 5,
        "values": [[0, 0, 0, 0, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 0, 0, 0, 0]]}}}
    # frame: origin [5,10,0], cell 40x40 -> design plane spans [5,205]x[10,210]
    payload = topology_result_to_shape_ir(framed, method="contour")
    src = compile_shape_ir_to_manifold_source(payload)
    ns: dict = {}
    exec(compile(src, "<m>", "exec"), ns)
    m = ns["result"]
    import numpy as np
    verts = np.asarray(m.to_mesh().vert_properties)[:, :3]
    assert m.volume() > 0
    assert verts[:, 2].min() >= -1e-6 and verts[:, 2].max() <= 10.0 + 1e-6   # extruded along z by thickness
    assert verts[:, 0].min() >= 5.0 - 1e-6 and verts[:, 1].min() >= 10.0 - 1e-6  # placed at frame origin


# ── spline / smooth-curve boundary (vs raw polyline) ─────────────────────────

_RING = {**_TOPO_FRAMED, "result": {"threshold": 0.5, "density_grid": {
    "nrows": 7, "ncols": 7, "values": [
        [0, 0, 0, 0, 0, 0, 0],
        [0, 1, 1, 1, 1, 1, 0],
        [0, 1, 0, 0, 0, 1, 0],
        [0, 1, 0, 0, 0, 1, 0],
        [0, 1, 0, 0, 0, 1, 0],
        [0, 1, 1, 1, 1, 1, 0],
        [0, 0, 0, 0, 0, 0, 0]]}}}


def test_sample_periodic_catmull_rom_densifies_and_stays_closed():
    pts = [[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0]]
    dense = sample_periodic_catmull_rom(pts, subdiv=8)
    assert len(dense) == 4 * 8                       # subdiv per segment, periodic
    assert dense[0] == [0.0, 0.0]                    # passes through the through-points
    # stays within a sane neighbourhood of the loop (mild interpolant overshoot)
    assert all(-3 <= p[0] <= 13 and -3 <= p[1] <= 11 for p in dense)


def test_spline_boundary_emits_true_spline_in_brep_and_densifies_in_mesh():
    pytest.importorskip("skimage")
    payload = topology_result_to_shape_ir(_RING, method="contour", boundary="spline")
    node = payload["parts"][0]
    assert node["type"] == "extruded_region" and node["boundary"] == "spline"
    bsrc = compile_shape_ir_to_build123d_source(payload)
    assert "Spline(" in bsrc and "periodic=True" in bsrc and "make_face" in bsrc
    assert "Polygon(" not in bsrc                     # spline path, not polyline
    msrc = compile_shape_ir_to_manifold_source(payload)
    assert "spline->densified" in msrc and "CrossSection" in msrc


def test_polygon_boundary_fallback_preserved():
    pytest.importorskip("skimage")
    payload = topology_result_to_shape_ir(_RING, method="contour", boundary="polygon")
    node = payload["parts"][0]
    assert node["boundary"] == "polygon"
    bsrc = compile_shape_ir_to_build123d_source(payload)
    assert "Polygon(" in bsrc and "Spline(" not in bsrc   # raw polyline preserved


def test_spline_boundary_extracts_hole_and_subtracts():
    pytest.importorskip("skimage")
    # a ring (solid border, hollow centre) -> outer + inner loop; inner is a hole
    node = topology_result_to_shape_ir(_RING, method="contour", boundary="spline",
                                       simplify_tol=0.4)["parts"][0]
    assert len(node["polygons"]) == 2
    bsrc = compile_shape_ir_to_build123d_source(node and {"parts": [node], "representation": "brep_build123d"})
    assert "make_face(mode=Mode.ADD)" in bsrc and "make_face(mode=Mode.SUBTRACT)" in bsrc


def test_spline_falls_back_to_polygon_on_design_space_overshoot():
    pytest.importorskip("skimage")
    # design space exactly the solid block's extent -> a spline through boundary
    # cell-centres bulges outside it -> must fall back to polygon for safety.
    framed = {
        "optimizer": {"name": "simp_2d"}, "objective": "compliance_minimization",
        "provenance": {"design_space_node": "blk"},
        "problem": {"design_space_node": "blk", "derivation": {
            "design_space_bbox": [0, 0, 0, 50, 50, 10],
            "frame": {"origin": [0, 0, 0], "u_axis": "x", "v_axis": "y",
                      "cell_size": [10.0, 10.0], "thickness": 10.0}}},
        "result": {"threshold": 0.5, "density_grid": {"nrows": 5, "ncols": 5, "values": [
            [1, 1, 1, 1, 1], [1, 0, 0, 0, 1], [1, 0, 0, 0, 1], [1, 0, 0, 0, 1], [1, 1, 1, 1, 1]]}},
    }
    node = topology_result_to_shape_ir(framed, method="contour", boundary="spline")["parts"][0]
    assert node["type"] == "extruded_region"
    assert node["boundary"] == "polygon"                       # fell back
    assert "spline_fallback" in node["source_optimization"]


def test_spline_kept_when_within_envelope():
    pytest.importorskip("skimage")
    # generous design space (margin around the part) -> spline stays inside -> kept.
    framed = {
        "optimizer": {"name": "simp_2d"}, "objective": "compliance_minimization",
        "provenance": {"design_space_node": "blk"},
        "problem": {"design_space_node": "blk", "derivation": {
            "design_space_bbox": [-40, -40, 0, 90, 90, 10],
            "frame": {"origin": [0, 0, 0], "u_axis": "x", "v_axis": "y",
                      "cell_size": [10.0, 10.0], "thickness": 10.0}}},
        "result": {"threshold": 0.5, "density_grid": {"nrows": 5, "ncols": 5, "values": [
            [0, 0, 0, 0, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 1, 1, 1, 0], [0, 0, 0, 0, 0]]}},
    }
    node = topology_result_to_shape_ir(framed, method="contour", boundary="spline")["parts"][0]
    assert node["boundary"] == "spline"                        # within envelope -> kept
    assert "spline_fallback" not in node["source_optimization"]


def test_spline_boundary_executes_in_manifold(tmp_path: Path):
    pytest.importorskip("skimage")
    pytest.importorskip("manifold3d")
    payload = topology_result_to_shape_ir(_RING, method="contour", boundary="spline")
    src = compile_shape_ir_to_manifold_source(payload)
    ns: dict = {}
    exec(compile(src, "<m>", "exec"), ns)
    m = ns["result"]
    import numpy as np
    verts = np.asarray(m.to_mesh().vert_properties)[:, :3]
    assert m.volume() > 0
    # placed in the _TOPO_FRAMED frame (origin [5,10,0], thickness 10 along z)
    assert verts[:, 2].min() >= -1e-6 and verts[:, 2].max() <= 10.0 + 1e-6
    assert verts[:, 0].min() >= 5.0 - 1.0 and verts[:, 1].min() >= 10.0 - 1.0


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


# ── derive a problem from CAE setup + geometry ───────────────────────────────

def test_simp_2d_explicit_bcs_solve_and_reduce_compliance():
    """A left-edge support + right-tip downward load (cell-based) behaves like a
    cantilever, lowering compliance — proves explicit BCs feed the solver."""
    nelx, nely = 24, 8
    supports = [{"cells": [[0, j] for j in range(nely)]}]          # clamp left column
    loads = [{"cells": [[nelx - 1, nely // 2]], "fx": 0.0, "fy": -1.0}]  # tip load down
    out = simp_2d({"grid": {"nelx": nelx, "nely": nely}, "volfrac": 0.5, "max_iters": 20,
                   "bcs": {"supports": supports, "loads": loads}})
    assert out["bcs_source"] == "explicit" and out["bcs_preset"] is None
    hist = out["compliance_history"]
    assert hist[-1] < hist[0] and all(h > 0 for h in hist)


def test_simp_2d_degenerate_explicit_falls_back_to_preset():
    # support but no load -> degenerate -> preset fallback (still solves)
    out = simp_2d({"grid": {"nelx": 12, "nely": 6}, "volfrac": 0.5, "max_iters": 6,
                   "bcs": {"supports": [{"cells": [[0, 0]]}], "loads": []}})
    assert out["bcs_source"] == "preset" and out["bcs_preset"] == "cantilever"


def _write_cae_project(pkg: Path) -> None:
    """A 120x80x10 plate: left face fixed, right face loaded -X... downward (-Z)."""
    topo = {"entities": [
        {"id": "body_plate", "type": "solid", "source_ir_node": "plate",
         "bounding_box": [0, 0, 0, 120, 80, 10]},
        {"id": "face_left", "type": "face", "body_id": "body_plate",
         "bounding_box": [0, 0, 0, 0, 80, 10], "normal": [-1, 0, 0]},
        {"id": "face_right", "type": "face", "body_id": "body_plate",
         "bounding_box": [120, 0, 0, 120, 80, 10], "normal": [1, 0, 0]},
    ]}
    cae_map = {"mappings": [
        {"maps_to": {"feature_id": "feat_fix"}, "cae_entity": "N_FIX", "face_ids": ["face_left"]},
        {"maps_to": {"feature_id": "feat_load"}, "cae_entity": "N_LOAD", "face_ids": ["face_right"]},
    ]}
    setup = (
        "boundary_conditions:\n"
        "  - id: bc1\n    target_feature: feat_fix\n    type: fixed\n"
        "loads:\n"
        "  - id: ld1\n    target_feature: feat_load\n    type: force\n"
        "    value_n: 500.0\n    direction: [0.0, 0.0, -1.0]\n"
    )
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/topology_map.json", json.dumps(topo))
        zf.writestr("simulation/cae_mapping.json", json.dumps(cae_map))
        zf.writestr("simulation/setup.yaml", setup)


def test_derive_problem_from_package_maps_supports_loads(tmp_path: Path):
    pytest.importorskip("yaml")
    pkg = tmp_path / "plate.aieng"
    _write_cae_project(pkg)
    prob = derive_topopt_problem_from_package(pkg, resolution=40)
    d = prob["derivation"]
    # plane = the two largest dims (x=120 > y=80 > z=10): u=x, v=y, out-of-plane=z
    assert d["plane"] == {"u_axis": "x", "v_axis": "y", "out_of_plane_axis": "z"}
    assert prob["grid"]["nelx"] == 40 and prob["grid"]["nely"] == round(40 * 80 / 120)
    assert prob["design_space_node"] == "plate"
    # support maps to the left column (i=0) — populated even though the load is dropped
    sup_cells = prob["bcs"]["supports"][0]["cells"]
    assert sup_cells and all(c[0] == 0 for c in sup_cells)
    # the load is -Z (purely out-of-plane); in-plane fx,fy are 0 -> dropped + warned,
    # so there is no usable load and the problem is NOT fully derived (preset fallback)
    assert prob["bcs"]["loads"] == [] and d["derived"] is False
    assert any("out-of-plane" in w for w in d["warnings"])
    assert prob["bcs"]["preset"] == "cantilever"
    # frame carries origin + cell size + thickness for a later writeback
    assert d["frame"]["thickness"] == 10.0 and d["frame"]["cell_size"][0] == round(120 / 40, 6)


def test_derive_in_plane_load_produces_usable_problem_and_solves(tmp_path: Path):
    pytest.importorskip("yaml")
    pkg = tmp_path / "plate2.aieng"
    _write_cae_project(pkg)
    # rewrite the load to act in-plane (-Y) so derivation yields a real load
    setup = (
        "boundary_conditions:\n  - {id: bc1, target_feature: feat_fix, type: fixed}\n"
        "loads:\n  - {id: ld1, target_feature: feat_load, type: force, value_n: 500.0, direction: [0.0, -1.0, 0.0]}\n"
    )
    import zipfile as _z
    tmp = pkg.with_suffix(".tmp.aieng")
    with _z.ZipFile(pkg) as src, _z.ZipFile(tmp, "w") as dst:
        for it in src.infolist():
            if it.filename != "simulation/setup.yaml":
                dst.writestr(it, src.read(it.filename))
        dst.writestr("simulation/setup.yaml", setup)
    tmp.replace(pkg)

    prob = derive_topopt_problem_from_package(pkg, resolution=24, max_iters=15)
    assert prob["derivation"]["derived"] is True
    assert prob["bcs"]["loads"][0]["fy"] == -500.0
    res = run_topology_optimization(prob)
    assert res["problem"]["bcs_source"] == "explicit"
    assert res["problem"]["derivation"]["plane"]["u_axis"] == "x"
    assert res["result"]["compliance_history"][-1] < res["result"]["compliance_history"][0]


def test_derive_falls_back_to_preset_without_bcs(tmp_path: Path):
    pkg = tmp_path / "bare.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("geometry/topology_map.json", json.dumps(
            {"entities": [{"id": "b", "type": "solid", "bounding_box": [0, 0, 0, 30, 10, 5]}]}))
    prob = derive_topopt_problem_from_package(pkg)
    assert prob["derivation"]["derived"] is False
    assert prob["bcs"]["preset"] == "cantilever"
    assert any("falling back" in w for w in prob["derivation"]["warnings"])
    # still solves via the preset fallback
    assert run_topology_optimization(prob)["result"]["compliance_history"]


def test_derive_run_writeback_places_body_in_design_space(tmp_path: Path):
    """Full chain: derive (frame) -> run -> writeback. The density_voxels node lands
    in the design-space frame, so nelx*su == design width and the body spans the bbox."""
    pytest.importorskip("yaml")
    pkg = tmp_path / "plate.aieng"
    _write_cae_project(pkg)  # 120 x 80 x 10 plate, origin at 0
    problem = derive_topopt_problem_from_package(pkg, resolution=12, max_iters=6)
    res = run_topology_optimization(problem)
    node = topology_result_to_shape_ir(res)["parts"][0]
    nelx, nely = problem["grid"]["nelx"], problem["grid"]["nely"]
    frame = problem["derivation"]["frame"]
    assert node["placed_in_frame"] is True
    assert node["origin"] == frame["origin"] == [0.0, 0.0, 0.0]
    assert node["cell_size"] == frame["cell_size"] and node["thickness"] == 10.0
    # the grid exactly tiles the in-plane design-space extents
    assert abs(nelx * node["cell_size"][0] - 120) < 1e-6
    assert abs(nely * node["cell_size"][1] - 80) < 1e-6


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
