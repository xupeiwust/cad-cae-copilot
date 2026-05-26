from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

MODEL_MANIFEST_PATH = "visual/model_manifest.json"
VISUAL_DIR = "visual/"
MODEL_MANIFEST_FORMAT = "aieng.visual_model_manifest"
ANNOTATION_LAYERS_PATH = "visual/annotation_layers.json"


def build_visual_manifest_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write visual/model_manifest.json to an existing .aieng package."""
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
            if MODEL_MANIFEST_PATH in names and not overwrite:
                raise FileExistsError(
                    f"{MODEL_MANIFEST_PATH} already exists; use --overwrite to replace it"
                )

            manifest = json.loads(package.read("manifest.json"))
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    model_manifest = _build_model_manifest(names)
    _rewrite_package_with_visual_manifest(path, existing_members, manifest, model_manifest)
    return path


def _build_model_manifest(names: set[str]) -> dict[str, Any]:
    has_annotation_layers = ANNOTATION_LAYERS_PATH in names
    annotation_status = "present" if has_annotation_layers else "missing"

    source_files = ["manifest.json"]
    if has_annotation_layers:
        source_files.append(ANNOTATION_LAYERS_PATH)

    return {
        "format": MODEL_MANIFEST_FORMAT,
        "format_version": FORMAT_VERSION,
        "source_files": source_files,
        "visual_resources": {
            "annotation_layers": {
                "path": ANNOTATION_LAYERS_PATH,
                "status": annotation_status,
                "type": "annotation_metadata",
                "description": "Structured feature/topology visual annotation metadata.",
            },
            "model_gltf": {
                "path": "visual/model.glb",
                "status": "not_generated",
                "type": "rendered_or_viewable_geometry",
                "description": "Future rendered/viewable geometry asset. Not generated in Phase 8B.",
            },
            "feature_snapshots": {
                "path": "visual/feature_snapshots/",
                "status": "not_generated",
                "type": "image_snapshots",
                "description": "Future per-feature snapshots. Not generated in Phase 8B.",
            },
            "screenshots": {
                "path": "visual/screenshots/",
                "status": "not_generated",
                "type": "rendered_images",
                "description": "Future screenshots. Not generated in Phase 8B.",
            },
        },
        "rendering_status": {
            "rendered_geometry_present": False,
            "screenshots_present": False,
            "feature_snapshots_present": False,
            "viewer_ready": False,
        },
        "claim_policy": {
            "allowed_claims": [
                "visual annotation metadata may be present if visual/annotation_layers.json exists"
            ],
            "forbidden_claims": [
                "a rendered 3D model is present",
                "model.glb exists",
                "feature snapshots exist",
                "screenshots exist",
                "the AI has visually inspected rendered geometry",
            ],
        },
    }


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {"manifest.json", MODEL_MANIFEST_PATH}
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_visual_manifest(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    model_manifest: dict[str, Any],
) -> None:
    resources = manifest.setdefault("resources", {})
    visual_resources = resources.setdefault("visual", {})
    if not isinstance(visual_resources, dict):
        raise ValueError("manifest resources.visual must be an object")
    visual_resources["model_manifest"] = MODEL_MANIFEST_PATH

    model_manifest_json = json.dumps(model_manifest, indent=2, sort_keys=True) + "\n"
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            if VISUAL_DIR not in existing_filenames:
                out_package.writestr(VISUAL_DIR, b"")
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(MODEL_MANIFEST_PATH, model_manifest_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()