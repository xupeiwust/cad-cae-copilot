from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.package import (
    PACKAGE_DIRECTORIES,
    build_step_import_manifest,
    model_id_from_package_path,
)

STEP_EXTENSIONS = {".step", ".stp"}
SOURCE_STEP_PATH = "geometry/source.step"
NORMALIZED_STEP_PATH = "geometry/normalized.step"


def import_step_package(step_file: str | Path, out: str | Path, *, overwrite: bool = False) -> Path:
    """Create a Phase 1 .aieng package by copying a STEP file as geometry resources.

    This function intentionally does not parse STEP, extract topology, normalize geometry,
    or call CAD kernels. For Phase 1, normalized.step is a byte-for-byte copy of the
    imported source STEP file.
    """
    step_path = Path(step_file)
    out_path = Path(out)

    if not step_path.exists():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    if not step_path.is_file():
        raise ValueError(f"STEP path is not a file: {step_path}")
    if step_path.suffix.lower() not in STEP_EXTENSIONS:
        raise ValueError("STEP file must have .step or .stp extension")
    if out_path.suffix != ".aieng":
        raise ValueError("output path must end with .aieng")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"package already exists: {out_path}")

    step_bytes = step_path.read_bytes()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_step_import_manifest(model_id_from_package_path(out_path))
    with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for directory in PACKAGE_DIRECTORIES:
            package.writestr(directory, b"")
        package.writestr(SOURCE_STEP_PATH, step_bytes)
        package.writestr(NORMALIZED_STEP_PATH, step_bytes)

    return out_path
