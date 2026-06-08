"""Tests for lightweight .aieng package snapshots (undo timeline)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.config import Settings

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project(settings: Settings, name: str) -> str:
    from app.main import default_project, save_project
    return save_project(settings, default_project(name))["id"]


def _topology_bbox_x(settings: Settings, project_id: str) -> float:
    from app.main import project_dir
    from app.project_io import get_project
    project = get_project(settings, project_id)
    pkg = project_dir(settings, project_id) / project["aieng_file"]
    with zipfile.ZipFile(pkg, "r") as zf:
        topo = json.loads(zf.read("geometry/topology_map.json"))
    solid = next(e for e in topo["entities"] if e.get("type") == "solid")
    bb = solid["bounding_box"]
    return bb[3] - bb[0]


# ── pure helpers ─────────────────────────────────────────────────────────────

def test_next_seq_is_monotonic_and_survives_pruning() -> None:
    from app import snapshots

    assert snapshots._next_seq([]) == 1
    assert snapshots._next_seq([{"snapshot_id": "snap_0003"}, {"snapshot_id": "snap_0007"}]) == 8


def test_prune_keeps_most_recent(tmp_path: Path, monkeypatch) -> None:
    from app import snapshots

    monkeypatch.setattr(snapshots, "_MAX_SNAPSHOTS", 3)
    manifest = tmp_path / "manifest.jsonl"
    records = []
    for i in range(1, 6):
        sid = f"snap_{i:04d}"
        (tmp_path / f"{sid}.aieng").write_bytes(b"pkg")
        records.append({"snapshot_id": sid})

    snapshots._prune(tmp_path, manifest, records)

    assert not (tmp_path / "snap_0001.aieng").exists()
    assert not (tmp_path / "snap_0002.aieng").exists()
    assert (tmp_path / "snap_0005.aieng").exists()
    kept = [r["snapshot_id"] for r in snapshots._read_manifest(manifest)]
    assert kept == ["snap_0003", "snap_0004", "snap_0005"]


def test_record_snapshot_without_package_is_noop(tmp_path: Path) -> None:
    from app import snapshots

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "no-geo")
    assert snapshots.record_snapshot(settings, pid, "cad.execute_build123d") is None


def test_list_snapshots_empty(tmp_path: Path) -> None:
    from app import snapshots

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "empty")
    out = snapshots.list_snapshots(settings, pid)
    assert out["status"] == "ok" and out["count"] == 0 and out["snapshots"] == []


def test_restore_validates_id_and_existence(tmp_path: Path) -> None:
    from app import snapshots

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "restore-validate")
    assert snapshots.restore_snapshot(settings, pid, "nope")["code"] == "invalid_snapshot_id"
    assert snapshots.restore_snapshot(settings, pid, "snap_0099")["code"] == "snapshot_not_found"


# ── end-to-end roundtrip (needs build123d) ───────────────────────────────────

def test_snapshot_record_list_restore_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    from app.cad_generation import execute_build123d_code
    from app import snapshots

    settings = _make_settings(tmp_path)
    pid = _make_project(settings, "snap-roundtrip")

    # Build v1 (100mm long), snapshot it.
    execute_build123d_code(settings, pid, {
        "code": "from build123d import *\nbody = Box(100, 40, 10); body.label='base'\nresult = Compound(children=[body])\n",
        "thumbnail": False,
    })
    snap1 = snapshots.record_snapshot(settings, pid, "cad.execute_build123d")
    assert snap1 and snap1["snapshot_id"] == "snap_0001"
    assert "base" in snap1["named_parts"] and snap1["part_count"] == 1
    assert abs(_topology_bbox_x(settings, pid) - 100) < 1.0

    # Build v2 (200mm long), snapshot it.
    execute_build123d_code(settings, pid, {
        "code": "from build123d import *\nbody = Box(200, 40, 10); body.label='base'\nresult = Compound(children=[body])\n",
        "thumbnail": False,
    })
    snap2 = snapshots.record_snapshot(settings, pid, "cad.execute_build123d")
    assert snap2 and snap2["snapshot_id"] == "snap_0002"
    assert abs(_topology_bbox_x(settings, pid) - 200) < 1.0

    listed = snapshots.list_snapshots(settings, pid)
    assert listed["count"] == 2
    assert [s["snapshot_id"] for s in listed["snapshots"]] == ["snap_0002", "snap_0001"]  # newest first

    # Restore v1 → package geometry reverts to the 100mm box.
    restored = snapshots.restore_snapshot(settings, pid, "snap_0001")
    assert restored["status"] == "ok" and restored["restored_from"] == "snap_0001"
    assert abs(_topology_bbox_x(settings, pid) - 100) < 1.0
