from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Protocol

from .backend import MockGeometryBackend, OCCGeometryBackend, get_backend

TOPOLOGY_MAP_PATH = "geometry/topology_map.json"
NORMALIZED_STEP_PATH = "geometry/normalized.step"


class TopologyExtractor(Protocol):
    """Protocol for pluggable topology extraction backends."""

    def extract(self, normalized_step: bytes) -> dict[str, Any]:
        """Return a topology map for normalized STEP bytes."""


class MockTopologyExtractor:
    """Legacy wrapper around MockGeometryBackend; maintained for backward compatibility."""

    def extract(self, normalized_step: bytes) -> dict[str, Any]:
        return MockGeometryBackend().extract_topology(normalized_step)


class OCCBasedTopologyExtractor:
    """Legacy wrapper around OCCGeometryBackend; maintained for backward compatibility."""

    def extract(self, normalized_step: bytes) -> dict[str, Any]:
        return OCCGeometryBackend().extract_topology(normalized_step)


def extract_topology_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
    extractor: TopologyExtractor | None = None,
    backend: str | None = None,
) -> Path:
    """Write geometry/topology_map.json to an existing .aieng package.

    Resolution order: backend string > extractor object > MockGeometryBackend default.
    """
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if NORMALIZED_STEP_PATH not in names:
                raise FileNotFoundError(f"{NORMALIZED_STEP_PATH} missing")
            if TOPOLOGY_MAP_PATH in names and not overwrite:
                raise FileExistsError(f"{TOPOLOGY_MAP_PATH} already exists; use --overwrite to replace it")

            manifest = json.loads(package.read("manifest.json"))
            normalized_step = package.read(NORMALIZED_STEP_PATH)
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    if backend is not None:
        resolved_backend = get_backend(backend)
        topology_map = resolved_backend.extract_topology(normalized_step)
    elif extractor is not None:
        topology_map = extractor.extract(normalized_step)
    else:
        topology_map = MockGeometryBackend().extract_topology(normalized_step)

    _rewrite_package_with_topology(path, existing_members, manifest, topology_map)
    return path


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in {"manifest.json", TOPOLOGY_MAP_PATH} or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_topology(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    topology_map: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    geometry_resources = resources.setdefault("geometry", {})
    if not isinstance(geometry_resources, dict):
        raise ValueError("manifest resources.geometry must be an object")
    geometry_resources["topology_map"] = TOPOLOGY_MAP_PATH

    topology_json = json.dumps(topology_map, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(TOPOLOGY_MAP_PATH, topology_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
