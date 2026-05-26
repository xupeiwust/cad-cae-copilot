"""Write a converter ConversionResult to a .aieng package on disk (Phase 20).

The writer is the only component that touches the filesystem: it takes a
ConversionResult and emits the package zip, the conversion manifest, an
optional converter-capabilities snapshot, the updated manifest.json, and
(when requested) a refreshed completeness report.

The writer does not execute external tools. It only serializes structured
state. Converters that need to invoke optional source-tool runtimes do that
in their own ``convert()`` method, not here.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION, __version__

from ..package import DEFAULT_UNITS, PACKAGE_DIRECTORIES
from ..validation.completeness_writer import write_completeness_report_package
from .base import (
    CONVERTER_CLAIM_POLICY,
    ConversionResult,
    Converter,
)


CONVERSION_MANIFEST_PATH = "provenance/conversion_manifest.json"
CONVERTER_CAPABILITIES_PATH = "provenance/converter_capabilities.json"


def write_converted_package(
    result: ConversionResult,
    out: Path,
    *,
    overwrite: bool = False,
    embed_converter_profile: Converter | None = None,
    refresh_completeness: bool = True,
) -> Path:
    """Write ``result`` to a .aieng package at ``out``.

    If ``embed_converter_profile`` is provided, its static capability profile
    is also embedded as ``provenance/converter_capabilities.json`` so the
    package is self-describing.

    If ``refresh_completeness`` is True, ``validation/completeness_report.json``
    is regenerated after writing (so the new ``source_conversion`` category
    reflects the conversion that just happened).
    """
    if out.suffix != ".aieng":
        raise ValueError("output path must end with .aieng")
    if out.exists() and not overwrite:
        raise FileExistsError(f"package already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    manifest = _build_manifest(result, now)
    conversion_manifest = _build_conversion_manifest(result, now)

    capabilities_payload: dict[str, Any] | None = None
    if embed_converter_profile is not None:
        profile = embed_converter_profile.capability_profile()
        capabilities_payload = profile.to_dict(
            generated_at_utc=now,
            format_version=FORMAT_VERSION,
        )
        manifest["resources"].setdefault("provenance", {})
        manifest["resources"]["provenance"]["converter_capabilities"] = CONVERTER_CAPABILITIES_PATH

    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    conversion_manifest_bytes = (
        json.dumps(conversion_manifest, indent=2, sort_keys=True) + "\n"
    ).encode()

    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", manifest_bytes)
        for directory in PACKAGE_DIRECTORIES:
            package.writestr(directory, b"")
        for path, payload in sorted(result.package_files.items()):
            package.writestr(path, payload)
        package.writestr(CONVERSION_MANIFEST_PATH, conversion_manifest_bytes)
        if capabilities_payload is not None:
            package.writestr(
                CONVERTER_CAPABILITIES_PATH,
                (json.dumps(capabilities_payload, indent=2, sort_keys=True) + "\n").encode(),
            )

    if refresh_completeness:
        write_completeness_report_package(out, overwrite=True)

    return out


def _build_manifest(result: ConversionResult, now: str) -> dict[str, Any]:
    """Construct manifest.json reflecting the converter's emitted resources."""
    resources: dict[str, Any] = {}
    for emitted in result.emitted_resources:
        bucket = _resource_bucket(emitted.path)
        if bucket is None:
            continue
        bucket_obj = resources.setdefault(bucket["bucket"], {})
        if not isinstance(bucket_obj, dict):
            continue
        bucket_obj[bucket["key"]] = emitted.path

    # Provenance bucket always carries the conversion manifest path.
    provenance = resources.setdefault("provenance", {})
    provenance["conversion_manifest"] = CONVERSION_MANIFEST_PATH

    manifest = {
        "model_id": result.model_id,
        "format_version": FORMAT_VERSION,
        "units": dict(DEFAULT_UNITS),
        "resources": resources,
        "created_by": {
            "tool": f"aieng {__version__}",
            "created_at": now,
            "converter_id": result.converter_id,
            "source_system": result.source_system,
        },
        "source_mode": "converter",
    }
    if result.converter_version:
        manifest["created_by"]["converter_version"] = result.converter_version
    return manifest


def _resource_bucket(path: str) -> dict[str, str] | None:
    """Map a package-relative path to its manifest resource bucket/key.

    Returns None when the path does not belong in a typed resource bucket
    (e.g. README_FOR_AI.md is top-level)."""
    mapping = {
        "geometry/source.step": ("geometry", "source"),
        "geometry/normalized.step": ("geometry", "normalized"),
        "geometry/topology_map.json": ("geometry", "topology_map"),
        "graph/feature_graph.json": ("graph", "feature_graph"),
        "graph/aag.json": ("graph", "aag"),
        "graph/constraints.json": ("graph", "constraints"),
        "graph/allowed_operations_catalog.json": ("graph", "allowed_operations_catalog"),
        "ai/protected_regions.json": ("ai", "protected_regions"),
        "ai/summary.md": ("ai", "summary"),
        "objects/object_registry.json": ("objects", "object_registry"),
        "objects/interface_graph.json": ("objects", "interface_graph"),
        "simulation/setup.yaml": ("simulation", "setup"),
        "validation/status.yaml": ("validation", "status"),
        "validation/completeness_report.json": ("validation", "completeness_report"),
    }
    if path in mapping:
        bucket, key = mapping[path]
        return {"bucket": bucket, "key": key}
    return None


def _build_conversion_manifest(result: ConversionResult, now: str) -> dict[str, Any]:
    converter_block: dict[str, Any] = {
        "converter_id": result.converter_id,
        "source_system": result.source_system,
        "runtime_mode": result.runtime_mode,
    }
    if result.display_name:
        converter_block["display_name"] = result.display_name
    if result.converter_version:
        converter_block["converter_version"] = result.converter_version

    source_block: dict[str, Any] = {
        "filename": result.source_filename,
        "byte_size": result.source_byte_size,
        "source_system": result.source_system,
    }
    if result.source_content_sha256:
        source_block["content_sha256"] = result.source_content_sha256
    if result.source_document_metadata:
        source_block["source_document_metadata"] = dict(result.source_document_metadata)

    manifest = {
        "format_version": FORMAT_VERSION,
        "manifest_id": "conversion_001",
        "generated_at_utc": now,
        "converter": converter_block,
        "source": source_block,
        "coverage_categories": [cat.to_dict() for cat in result.coverage_categories],
        "declared_capability_levels": [
            level.to_manifest_dict() for level in result.declared_levels
        ],
        "achieved_capability_levels": [
            level.to_manifest_dict() for level in result.achieved_levels
        ],
        "emitted_resources": [resource.to_dict() for resource in result.emitted_resources],
        "unsupported_or_missing": [item.to_dict() for item in result.unsupported],
        "uncertainty_notes": [note.to_dict() for note in result.uncertainty],
        "claim_policy": dict(CONVERTER_CLAIM_POLICY),
    }
    if result.notes:
        manifest["notes"] = list(result.notes)
    return manifest


def compute_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()
