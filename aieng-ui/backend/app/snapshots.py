"""Lightweight .aieng package snapshots for reversible CAD iteration.

After a successful CAD mutation (``cad.execute_build123d`` / ``cad.edit_parameter``
/ ``cad.replace_part`` / ``cad.remove_part``) the current package is copied to
``data/projects/<id>/snapshots/<snapshot_id>.aieng`` and a one-line metadata
record is appended to ``snapshots/manifest.jsonl``. This gives the agent and the
user an undo timeline without growing the package itself.

- ``record_snapshot`` is best-effort and never raises — a snapshot failure must
  not fail the CAD tool that triggered it.
- ``list_snapshots`` returns only the tiny manifest metadata (never package
  bytes into agent context).
- ``restore_snapshot`` copies a snapshot back over the project package and
  republishes the viewer preview (approval-gated at the tool layer).
- Snapshots are bounded to the most recent ``_MAX_SNAPSHOTS`` to cap disk use;
  older ones are pruned (files + manifest rows).
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .config import now_iso

_MAX_SNAPSHOTS = 20
_SNAPSHOT_DIRNAME = "snapshots"
_MANIFEST_NAME = "manifest.jsonl"
_SNAPSHOT_ID_RE = re.compile(r"^snap_\d{4,}$")


def _snapshots_dir(settings: Any, project_id: str) -> Path:
    from .project_io import project_dir

    return project_dir(settings, project_id) / _SNAPSHOT_DIRNAME


def _manifest_path(settings: Any, project_id: str) -> Path:
    return _snapshots_dir(settings, project_id) / _MANIFEST_NAME


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    except Exception:
        return []
    return out


def _write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in records),
        encoding="utf-8",
    )


def _package_metadata(pkg_path: Path) -> dict[str, Any]:
    """Best-effort part_count + named_parts from a package (for manifest rows)."""
    from .cad_generation import _named_parts_from_feature_graph

    named: list[str] = []
    part_count = 0
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = zf.namelist()
            if "graph/feature_graph.json" in names:
                fg = json.loads(zf.read("graph/feature_graph.json").decode("utf-8"))
                named = _named_parts_from_feature_graph(fg)
            if "geometry/topology_map.json" in names:
                topo = json.loads(zf.read("geometry/topology_map.json").decode("utf-8"))
                part_count = sum(
                    1 for e in topo.get("entities", []) if e.get("type") == "solid"
                )
    except Exception:
        pass
    return {"part_count": part_count, "named_parts": named}


def _next_seq(records: list[dict[str, Any]]) -> int:
    """Monotonic next sequence — survives pruning so ids never collide."""
    seq = 0
    for rec in records:
        m = re.search(r"(\d+)$", str(rec.get("snapshot_id") or ""))
        if m:
            seq = max(seq, int(m.group(1)))
    return seq + 1


def _prune(snap_dir: Path, manifest_path: Path, records: list[dict[str, Any]]) -> None:
    """Keep only the most recent _MAX_SNAPSHOTS; delete older files + rows."""
    if len(records) <= _MAX_SNAPSHOTS:
        return
    drop = records[: len(records) - _MAX_SNAPSHOTS]
    keep = records[len(records) - _MAX_SNAPSHOTS :]
    for rec in drop:
        sid = rec.get("snapshot_id")
        if sid:
            try:
                (snap_dir / f"{sid}.aieng").unlink(missing_ok=True)
            except Exception:
                pass
    _write_manifest(manifest_path, keep)


def record_snapshot(settings: Any, project_id: str, tool_name: str) -> dict[str, Any] | None:
    """Copy the current package to a new snapshot + append the manifest.

    Best-effort: returns the snapshot metadata, or ``None`` when there is no
    package yet or anything fails. Never raises — a snapshot failure must not
    fail the CAD tool that triggered it.
    """
    try:
        from .project_io import get_project, resolve_project_path

        project = get_project(settings, project_id)
        pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
        if pkg_path is None or not pkg_path.exists():
            return None

        snap_dir = _snapshots_dir(settings, project_id)
        snap_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = _manifest_path(settings, project_id)
        records = _read_manifest(manifest_path)

        snapshot_id = f"snap_{_next_seq(records):04d}"
        dest = snap_dir / f"{snapshot_id}.aieng"
        shutil.copy2(pkg_path, dest)

        meta = _package_metadata(dest)
        record = {
            "snapshot_id": snapshot_id,
            "created_at": now_iso(),
            "tool_name": tool_name,
            "part_count": meta["part_count"],
            "named_parts": meta["named_parts"],
        }
        with manifest_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        _prune(snap_dir, manifest_path, records + [record])
        return record
    except Exception:
        return None


def list_snapshots(settings: Any, project_id: str, limit: int = _MAX_SNAPSHOTS) -> dict[str, Any]:
    """Return the most-recent snapshot metadata (newest first). Read-only, tiny."""
    try:
        from .project_io import get_project

        get_project(settings, project_id)  # 404s on unknown project
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    records = _read_manifest(_manifest_path(settings, project_id))
    try:
        n = max(1, int(limit))
    except (TypeError, ValueError):
        n = _MAX_SNAPSHOTS
    newest_first = list(reversed(records))[:n]
    return {
        "status": "ok",
        "project_id": project_id,
        "count": len(records),
        "snapshots": newest_first,
        "message": (
            "Restore any of these with cad.restore_snapshot { snapshot_id } "
            "(approval-gated). Snapshots are the most recent "
            f"{_MAX_SNAPSHOTS} successful CAD mutations."
            if records
            else "No snapshots yet — they are recorded after each successful CAD mutation."
        ),
    }


def restore_snapshot(settings: Any, project_id: str, snapshot_id: str) -> dict[str, Any]:
    """Replace the project package with a snapshot and republish the viewer.

    Approval-gated at the tool layer. Validates the id, copies the snapshot back
    over the live package, then reuses the standard preview-publish path so the
    UI viewer and project metadata reflect the restored geometry.
    """
    from . import cad_generation as _cg
    from .project_io import get_project, resolve_project_path

    if not snapshot_id or not _SNAPSHOT_ID_RE.match(str(snapshot_id)):
        return {"status": "error", "code": "invalid_snapshot_id",
                "message": "snapshot_id must look like 'snap_0001'."}

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        return {"status": "error", "code": "project_not_found", "message": f"{exc}"}

    snap_path = _snapshots_dir(settings, project_id) / f"{snapshot_id}.aieng"
    if not snap_path.exists():
        return {"status": "error", "code": "snapshot_not_found",
                "message": f"No snapshot '{snapshot_id}' for this project."}

    pkg_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if pkg_path is None:
        from .main import project_dir as _project_dir, save_project as _save_project

        pkg_name = f"{project_id}.aieng"
        pkg_path = _project_dir(settings, project_id) / pkg_name
        project["aieng_file"] = pkg_name
        _save_project(settings, project)

    try:
        shutil.copy2(snap_path, pkg_path)
    except Exception as exc:
        return {"status": "error", "code": "restore_failed", "message": f"{exc}"}

    # Republish the restored geometry to the viewer (mirrors the build path).
    glb_bytes: bytes | None = None
    stl_bytes: bytes | None = None
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = zf.namelist()
            if "geometry/preview.glb" in names:
                glb_bytes = zf.read("geometry/preview.glb")
            if "geometry/preview.stl" in names:
                stl_bytes = zf.read("geometry/preview.stl")
    except Exception:
        pass

    try:
        from .config import now_iso as _now_iso
        from .main import save_project as _save_project2

        project["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
        project["updated_at"] = _now_iso()
        _save_project2(settings, project)
    except Exception:
        pass

    _cg._publish_preview_to_viewer(settings, project_id, project, glb_bytes, stl_bytes)
    try:
        _cg._clear_revalidation_status(pkg_path)
    except Exception:
        pass

    meta = _package_metadata(pkg_path)
    return {
        "status": "ok",
        "project_id": project_id,
        "restored_from": snapshot_id,
        "part_count": meta["part_count"],
        "named_parts": meta["named_parts"],
        "message": (
            f"Restored snapshot '{snapshot_id}'. The package and viewer now reflect "
            "that earlier state; stale-artifact flags were cleared."
        ),
    }
