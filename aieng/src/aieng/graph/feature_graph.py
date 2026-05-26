from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng.geometry.topology_extractor import TOPOLOGY_MAP_PATH
from aieng.graph.aag import AAG_PATH
from aieng.graph.feature_recognition import RuleBasedFeatureRecognizer

FEATURE_GRAPH_PATH = "graph/feature_graph.json"


def recognize_features_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
    recognizer: RuleBasedFeatureRecognizer | None = None,
) -> Path:
    """Write graph/feature_graph.json to an existing .aieng package."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    recognizer = recognizer or RuleBasedFeatureRecognizer()

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if TOPOLOGY_MAP_PATH not in names:
                raise FileNotFoundError(f"{TOPOLOGY_MAP_PATH} missing")
            if FEATURE_GRAPH_PATH in names and not overwrite:
                raise FileExistsError(f"{FEATURE_GRAPH_PATH} already exists; use --overwrite to replace it")

            manifest = json.loads(package.read("manifest.json"))
            topology_map = json.loads(package.read(TOPOLOGY_MAP_PATH))
            aag = json.loads(package.read(AAG_PATH)) if AAG_PATH in names else None
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    feature_graph = recognizer.recognize(topology_map, aag=aag)
    _rewrite_package_with_feature_graph(path, existing_members, manifest, feature_graph)
    return path


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in {"manifest.json", FEATURE_GRAPH_PATH} or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_feature_graph(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    feature_graph: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    graph_resources = resources.setdefault("graph", {})
    if not isinstance(graph_resources, dict):
        raise ValueError("manifest resources.graph must be an object")
    graph_resources["feature_graph"] = FEATURE_GRAPH_PATH

    feature_graph_json = json.dumps(feature_graph, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(FEATURE_GRAPH_PATH, feature_graph_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
