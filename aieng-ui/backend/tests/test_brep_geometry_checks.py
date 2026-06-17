"""Integration tests for exact B-Rep geometric checks (#296).

These tests create real STEP files with OCP and run the isolated B-Rep checker.
They are skipped when OCP is not installed so core CI stays fast.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("OCP.STEPControl", reason="OCP not installed; skipping B-Rep integration tests")

from app.brep_geometry_checks import run_brep_checks


def _step_control_as_is():
    """Return STEPControl_AsIs, with version fallback."""
    try:
        from OCP.STEPControl import STEPControl_AsIs
        return STEPControl_AsIs
    except ImportError:
        from OCP.STEPControl import STEPControl_StepModelType
        return STEPControl_StepModelType.STEPControl_AsIs


STEP_CONTROL_AS_IS = _step_control_as_is()


def _make_box_step(tmp_path: Path, x: float, y: float, z: float, *, label: str | None = None) -> Path:
    """Create a STEP file with a single box using OCP."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_Writer
    from OCP.IFSelect import IFSelect_RetDone

    box = BRepPrimAPI_MakeBox(x, y, z).Shape()
    step_path = tmp_path / (f"{label or 'box'}_{int(x)}_{int(y)}_{int(z)}.step")
    writer = STEPControl_Writer()
    writer.Transfer(box, STEP_CONTROL_AS_IS)
    status = writer.Write(str(step_path))
    if status != IFSelect_RetDone:
        pytest.skip(f"OCP STEP writer failed (status={status}); cannot create fixture")
    return step_path


def _make_cylinder_step(tmp_path: Path, radius: float, height: float) -> Path:
    """Create a STEP file with a single cylinder using OCP."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.STEPControl import STEPControl_Writer
    from OCP.IFSelect import IFSelect_RetDone

    cyl = BRepPrimAPI_MakeCylinder(radius, height).Shape()
    step_path = tmp_path / f"cylinder_r{radius}_h{height}.step"
    writer = STEPControl_Writer()
    writer.Transfer(cyl, STEP_CONTROL_AS_IS)
    status = writer.Write(str(step_path))
    if status != IFSelect_RetDone:
        pytest.skip(f"OCP STEP writer failed (status={status}); cannot create fixture")
    return step_path


def _make_compound_step(tmp_path: Path, *shapes) -> Path:
    """Write multiple separate shapes into one STEP file as a compound."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.STEPControl import STEPControl_Writer
    from OCP.IFSelect import IFSelect_RetDone

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    step_path = tmp_path / "compound.step"
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEP_CONTROL_AS_IS)
    status = writer.Write(str(step_path))
    if status != IFSelect_RetDone:
        pytest.skip(f"OCP STEP writer failed (status={status}); cannot create fixture")
    return step_path


def _two_boxes_step(tmp_path: Path, gap: float) -> Path:
    """Two 10x10x10 boxes separated by ``gap`` along X."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    a = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 10.0, 10.0, 10.0).Shape()
    b = BRepPrimAPI_MakeBox(gp_Pnt(10.0 + gap, 0, 0), 10.0, 10.0, 10.0).Shape()
    return _make_compound_step(tmp_path, a, b)


def test_runner_returns_unknown_when_step_missing() -> None:
    results = run_brep_checks(
        "/nonexistent/path.step",
        [{"id": "t1", "kind": "no_interference", "part_a": 0, "part_b": 1}],
    )
    assert "error" in results
    assert results["results"]["t1"]["status"] == "unknown"


def test_no_interference_passes_for_separated_boxes(tmp_path: Path) -> None:
    step_path = _two_boxes_step(tmp_path, gap=5.0)
    topo = {
        "entities": [
            {"id": "b1", "type": "solid", "name": "box_a", "bounding_box": [0, 0, 0, 10, 10, 10]},
            {"id": "b2", "type": "solid", "name": "box_b", "bounding_box": [15, 0, 0, 25, 10, 10]},
        ]
    }
    report = run_brep_checks(
        step_path,
        [{"id": "t1", "kind": "no_interference", "part_a": "box_a", "part_b": "box_b"}],
        topology_map=topo,
    )
    assert "error" not in report
    assert report["results"]["t1"]["status"] == "pass"
    assert report["results"]["t1"]["measured"] == pytest.approx(0.0, abs=1e-5)


def test_no_interference_fails_for_overlapping_boxes(tmp_path: Path) -> None:
    step_path = _two_boxes_step(tmp_path, gap=-2.0)
    topo = {
        "entities": [
            {"id": "b1", "type": "solid", "name": "box_a", "bounding_box": [0, 0, 0, 10, 10, 10]},
            {"id": "b2", "type": "solid", "name": "box_b", "bounding_box": [8, 0, 0, 18, 10, 10]},
        ]
    }
    report = run_brep_checks(
        step_path,
        [{"id": "t1", "kind": "no_interference", "part_a": 0, "part_b": 1}],
        topology_map=topo,
    )
    assert "error" not in report
    assert report["results"]["t1"]["status"] == "fail"
    assert report["results"]["t1"]["measured"] > 0


def test_clearance_within_band(tmp_path: Path) -> None:
    step_path = _two_boxes_step(tmp_path, gap=0.3)
    topo = {
        "entities": [
            {"id": "b1", "type": "solid", "name": "box_a", "bounding_box": [0, 0, 0, 10, 10, 10]},
            {"id": "b2", "type": "solid", "name": "box_b", "bounding_box": [10.3, 0, 0, 20.3, 10, 10]},
        ]
    }
    report = run_brep_checks(
        step_path,
        [{"id": "t1", "kind": "clearance_within", "part_a": "box_a", "part_b": "box_b",
          "min_clearance_mm": 0.1, "max_clearance_mm": 0.5}],
        topology_map=topo,
    )
    assert "error" not in report
    assert report["results"]["t1"]["status"] == "pass"
    assert report["results"]["t1"]["measured"] == pytest.approx(0.3, abs=1e-3)


def test_coaxial_within_detects_offset_cylinders(tmp_path: Path) -> None:
    """Two coaxial cylinders, one offset by 2mm in X."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir

    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    a = BRepPrimAPI_MakeCylinder(ax, 5.0, 20.0).Shape()
    ax2 = gp_Ax2(gp_Pnt(2.0, 0, 0), gp_Dir(0, 0, 1))
    b = BRepPrimAPI_MakeCylinder(ax2, 5.0, 20.0).Shape()
    step_path = _make_compound_step(tmp_path, a, b)

    topo = {
        "entities": [
            {"id": "c1", "type": "solid", "name": "shaft", "bounding_box": [-5, -5, 0, 5, 5, 20]},
            {"id": "c2", "type": "solid", "name": "bore", "bounding_box": [-3, -5, 0, 7, 5, 20]},
        ]
    }
    report = run_brep_checks(
        step_path,
        [{"id": "t1", "kind": "coaxial_within", "part_a": "shaft", "part_b": "bore", "tolerance_mm": 0.1}],
        topology_map=topo,
    )
    assert "error" not in report
    assert report["results"]["t1"]["status"] == "fail"
    measured = report["results"]["t1"]["measured"]
    assert measured["axis_distance_mm"] >= 1.5


def test_faces_flush_within_detects_gap(tmp_path: Path) -> None:
    """Two boxes whose adjacent faces are parallel but separated by 0.5mm."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    a = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 10.0, 10.0, 10.0).Shape()
    b = BRepPrimAPI_MakeBox(gp_Pnt(0, 10.5, 0), 10.0, 10.0, 10.0).Shape()
    step_path = _make_compound_step(tmp_path, a, b)

    topo = {
        "entities": [
            {"id": "b1", "type": "solid", "name": "a", "bounding_box": [0, 0, 0, 10, 10, 10]},
            {"id": "b2", "type": "solid", "name": "b", "bounding_box": [0, 10.5, 0, 10, 20.5, 10]},
        ]
    }
    report = run_brep_checks(
        step_path,
        [{"id": "t1", "kind": "faces_flush_within", "part_a": "a", "part_b": "b", "tolerance_mm": 0.1}],
        topology_map=topo,
    )
    assert "error" not in report
    assert report["results"]["t1"]["status"] == "fail"
    measured = report["results"]["t1"]["measured"]
    assert measured["plane_distance_mm"] >= 0.4


def test_missing_ocp_returns_graceful_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the runner subprocess cannot import OCP, we surface an error honestly."""
    step_path = _make_box_step(tmp_path, 10, 10, 10)

    def _fake_run(*args, **kwargs):
        class _FakeProc:
            returncode = 1
            stderr = "OCP import failed"
            stdout = ""
        return _FakeProc()

    monkeypatch.setattr("app.brep_geometry_checks.subprocess.run", _fake_run)
    report = run_brep_checks(
        step_path,
        [{"id": "t1", "kind": "no_interference", "part_a": 0, "part_b": 1}],
    )
    assert "error" in report
    assert report["results"]["t1"]["status"] == "unknown"