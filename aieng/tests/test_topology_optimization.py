"""Tests for topology optimization (contract + pluggable optimizer + 2D SIMP)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from aieng.converters.topology_optimization import (  # noqa: E402
    TOPOLOGY_OPTIMIZATION_PATH,
    available_optimizers,
    run_topology_optimization,
    simp_2d,
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
