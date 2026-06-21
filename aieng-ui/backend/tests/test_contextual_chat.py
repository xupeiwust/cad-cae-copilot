"""Tests for contextual_chat.py — project context block builder."""
import json
import sys
import zipfile
from pathlib import Path
import tempfile

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.contextual_chat import _read_member, build_context_block


def _make_package(members: dict[str, bytes]) -> Path:
    """Build a minimal .aieng package ZIP in a temp file."""
    tmp = Path(tempfile.mktemp(suffix=".aieng"))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return tmp


# ── build_context_block ───────────────────────────────────────────────────────

def test_no_package_returns_placeholder():
    result = build_context_block(None)
    assert "No project package" in result


def test_nonexistent_package_returns_placeholder():
    result = build_context_block(Path("/nonexistent/path.aieng"))
    assert "No project package" in result


def test_read_member_does_not_enumerate_package(tmp_path, monkeypatch):
    pkg = tmp_path / "context.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("manifest.json", b'{"model_id": "m1"}')

    def fail_namelist(self):
        raise AssertionError("namelist should not be needed for direct member reads")

    monkeypatch.setattr(zipfile.ZipFile, "namelist", fail_namelist)

    assert _read_member(pkg, "manifest.json") == b'{"model_id": "m1"}'


def test_empty_package_shows_not_yet_run():
    pkg = _make_package({})
    try:
        result = build_context_block(pkg)
        assert "not yet run" in result
    finally:
        pkg.unlink(missing_ok=True)


def test_topology_included_in_context():
    topo = {
        "entities": [
            {"id": "f1", "type": "face", "surface_type": "plane",
             "bounding_box": [0, 0, 0, 100, 80, 45]},
            {"id": "f2", "type": "face", "surface_type": "cylinder",
             "bounding_box": [40, 40, 10, 60, 60, 40]},
        ]
    }
    pkg = _make_package({"geometry/topology_map.json": json.dumps(topo).encode()})
    try:
        result = build_context_block(pkg)
        assert "2 faces" in result
        assert "100.0" in result  # xspan
    finally:
        pkg.unlink(missing_ok=True)


def test_setup_yaml_included_in_context():
    setup = {
        "material_name": "Steel-1045",
        "boundary_conditions": [{"id": "bc1"}, {"id": "bc2"}],
        "loads": [{"id": "ld1", "value_n": 500}],
        "mesh": {"target_size_mm": 2.0},
    }
    pkg = _make_package({"simulation/setup.yaml": yaml.safe_dump(setup).encode()})
    try:
        result = build_context_block(pkg)
        assert "Steel-1045" in result
        assert "2 BC" in result
        assert "1 load" in result
        assert "2.0 mm" in result
    finally:
        pkg.unlink(missing_ok=True)


def test_simulation_success_results_included():
    summary = {
        "status": "success",
        "von_mises_max_mpa": 453.2,
        "displacement_max_mm": 0.823,
        "node_count": 4231,
        "mesh_size_mm": 2.5,
        "verdict": {
            "overall": "fail",
            "pass_count": 0,
            "fail_count": 1,
            "items": [
                {
                    "target_id": "s1", "label": "Max stress",
                    "metric": "von_mises_max_mpa", "status": "fail",
                    "actual_value": 453.2, "threshold": 250.0,
                    "operator": "<=", "unit": "MPa",
                }
            ],
        },
    }
    pkg = _make_package({"simulation/results_summary.json": json.dumps(summary).encode()})
    try:
        result = build_context_block(pkg)
        assert "453.1 MPa" in result or "453.2 MPa" in result
        assert "0.823 mm" in result
        assert "FAIL" in result
        assert "Max stress" in result
    finally:
        pkg.unlink(missing_ok=True)


def test_simulation_solver_error_shown():
    summary = {"status": "solver_error", "returncode": 1}
    pkg = _make_package({"simulation/results_summary.json": json.dumps(summary).encode()})
    try:
        result = build_context_block(pkg)
        assert "SOLVER ERROR" in result
    finally:
        pkg.unlink(missing_ok=True)


def test_design_targets_included_in_context():
    targets_doc = {
        "targets": [
            {"target_id": "s1", "label": "Stress limit", "metric": "von_mises_max_mpa",
             "operator": "<=", "value": 250.0, "unit": "MPa"},
            {"target_id": "d1", "label": "Max deflection", "metric": "max_displacement_mm",
             "operator": "<=", "value": 0.5, "unit": "mm"},
        ]
    }
    pkg = _make_package({"task/design_targets.yaml": yaml.safe_dump(targets_doc).encode()})
    try:
        result = build_context_block(pkg)
        assert "Stress limit" in result
        assert "250.0MPa" in result or "250.0 MPa" in result or "250.0" in result
        assert "Max deflection" in result
    finally:
        pkg.unlink(missing_ok=True)


def test_no_design_targets_prompts_add_message():
    pkg = _make_package({})
    try:
        result = build_context_block(pkg)
        assert "design_targets.yaml" in result or "Design Targets" in result
    finally:
        pkg.unlink(missing_ok=True)


def test_full_package_context_is_structured():
    topo = {"entities": [{"id": "f1", "type": "face", "bounding_box": [0, 0, 0, 50, 40, 20]}]}
    setup = {"material_name": "Al6061-T6", "boundary_conditions": [{"id": "bc1"}],
             "loads": [{"id": "l1", "value_n": 1000}], "mesh": {"target_size_mm": 3.0}}
    summary = {"status": "success", "von_mises_max_mpa": 120.0, "displacement_max_mm": 0.2,
               "node_count": 800, "mesh_size_mm": 3.0, "verdict": {"overall": "pass",
               "pass_count": 1, "fail_count": 0, "items": []}}
    targets = {"targets": [{"target_id": "s1", "label": "Stress limit",
               "metric": "von_mises_max_mpa", "operator": "<=", "value": 200.0, "unit": "MPa"}]}
    pkg = _make_package({
        "geometry/topology_map.json": json.dumps(topo).encode(),
        "simulation/setup.yaml": yaml.safe_dump(setup).encode(),
        "simulation/results_summary.json": json.dumps(summary).encode(),
        "task/design_targets.yaml": yaml.safe_dump(targets).encode(),
    })
    try:
        result = build_context_block(pkg)
        assert "Al6061-T6" in result
        assert "120.0 MPa" in result or "120" in result
        assert "PASS" in result
        assert "Stress limit" in result
    finally:
        pkg.unlink(missing_ok=True)
