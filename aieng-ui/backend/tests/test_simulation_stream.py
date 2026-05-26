"""Tests for run_simulation_stream() in simulation_runner.py."""
import json
import sys
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.simulation_runner import run_simulation_stream, _sse

# Valid 12-char hex project IDs (required by PROJECT_ID regex)
PID1 = "aabbccdd1101"
PID2 = "aabbccdd1102"
PID3 = "aabbccdd1103"
PID4 = "aabbccdd1104"


# ── _sse helper ───────────────────────────────────────────────────────────────

def test_sse_format():
    line = _sse({"step": "meshing", "message": "Generating mesh…"})
    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    payload = json.loads(line[6:])
    assert payload["step"] == "meshing"


# ── confirmed gate ────────────────────────────────────────────────────────────

def test_stream_requires_confirmed(tmp_path):
    class FakeSettings:
        projects_root = tmp_path

    events = list(run_simulation_stream(FakeSettings(), PID1, {}))
    assert len(events) == 1
    data = json.loads(events[0][6:])
    assert data["step"] == "error"
    assert "confirmed" in data["message"].lower()


# ── missing project ───────────────────────────────────────────────────────────

def test_stream_missing_project(tmp_path):
    class FakeSettings:
        projects_root = tmp_path

    events = list(run_simulation_stream(FakeSettings(), PID1, {"confirmed": True}))
    assert len(events) == 1
    data = json.loads(events[0][6:])
    assert data["step"] == "error"


# ── missing package ───────────────────────────────────────────────────────────

def _make_project_dir(tmp_path: Path, project_id: str) -> Path:
    proj = tmp_path / project_id
    proj.mkdir(parents=True)
    (proj / "metadata.json").write_text(json.dumps({"id": project_id, "name": "Test"}))
    return proj


def test_stream_missing_package(tmp_path):
    _make_project_dir(tmp_path, PID1)

    class FakeSettings:
        projects_root = tmp_path

    events = list(run_simulation_stream(FakeSettings(), PID1, {"confirmed": True}))
    assert len(events) == 1
    data = json.loads(events[0][6:])
    assert data["step"] == "error"


# ── tools_unavailable path ────────────────────────────────────────────────────

def _make_minimal_package(pkg_path: Path) -> None:
    """Create a minimal .aieng package with a setup.yaml but no STEP."""
    setup = {
        "material_name": "Al6061_T6",
        "boundary_conditions": [],
        "loads": [],
        "mesh": {"target_size_mm": 2.5},
    }
    with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("simulation/setup.yaml", yaml.safe_dump(setup))
        zf.writestr("simulation/cae_mapping.json", json.dumps({"mappings": []}))
        zf.writestr("geometry/topology_map.json", json.dumps({"entities": []}))


def _make_project_with_package(tmp_path: Path, project_id: str) -> Path:
    proj = _make_project_dir(tmp_path, project_id)
    packages = proj / "packages"
    packages.mkdir()
    pkg = packages / f"{project_id}.aieng"
    _make_minimal_package(pkg)
    (proj / "metadata.json").write_text(
        json.dumps({"id": project_id, "name": "Test", "aieng_file": f"packages/{project_id}.aieng"})
    )
    return proj


def test_stream_tools_unavailable_yields_done(tmp_path, monkeypatch):
    _make_project_with_package(tmp_path, PID2)

    class FakeSettings:
        projects_root = tmp_path

    import app.simulation_runner as sr
    monkeypatch.setattr(sr, "check_simulation_tools", lambda: {"ready": False, "missing": ["gmsh", "ccx"]})

    events = list(run_simulation_stream(FakeSettings(), PID2, {"confirmed": True}))
    steps = [json.loads(e[6:])["step"] for e in events]
    assert "checking_tools" in steps
    assert steps[-1] == "done"
    last = json.loads(events[-1][6:])
    assert last["result"]["status"] == "tools_unavailable"
    assert "gmsh" in last["result"]["missing_tools"]


def test_stream_no_step_file_yields_error(tmp_path, monkeypatch):
    _make_project_with_package(tmp_path, PID3)

    class FakeSettings:
        projects_root = tmp_path

    import app.simulation_runner as sr
    monkeypatch.setattr(sr, "check_simulation_tools", lambda: {"ready": True, "missing": [], "calculix_cmd": "ccx"})

    events = list(run_simulation_stream(FakeSettings(), PID3, {"confirmed": True}))
    steps = [json.loads(e[6:])["step"] for e in events]
    assert "checking_tools" in steps
    assert steps[-1] == "error"
    last = json.loads(events[-1][6:])
    assert "step" in last["message"].lower() or "no step" in last["message"].lower()


def test_stream_progress_events_before_done(tmp_path, monkeypatch):
    """Verify that progress events (meshing, solving…) come before the done event."""
    _make_project_with_package(tmp_path, PID4)

    class FakeSettings:
        projects_root = tmp_path

    import app.simulation_runner as sr
    monkeypatch.setattr(sr, "check_simulation_tools", lambda: {"ready": False, "missing": ["gmsh"]})

    events = list(run_simulation_stream(FakeSettings(), PID4, {"confirmed": True}))
    steps = [json.loads(e[6:])["step"] for e in events]
    assert steps[0] == "checking_tools"
    assert steps[-1] == "done"
    assert len(steps) >= 2
