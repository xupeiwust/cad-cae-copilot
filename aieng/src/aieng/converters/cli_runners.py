"""CLI helper functions for the converter subcommands (Phase 20)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

from .base import CONVERTER_CLAIM_POLICY
from .readiness import build_readiness_report, render_readiness_report
from .registry import available_converters, get_converter
from .writer import write_converted_package


def convert_source(
    *,
    source_path: Path,
    out: Path,
    model_id: str,
    converter_id: str | None,
    overwrite: bool,
    runtime_mode: str = "auto",
    embed_capabilities: bool = True,
) -> Path:
    """Run a registered converter end-to-end and write a .aieng package."""
    resolved_converter_id = converter_id or _infer_converter_id(source_path)
    converter = get_converter(resolved_converter_id)
    result = converter.convert(
        source_path,
        model_id=model_id,
        runtime_mode=runtime_mode,
    )
    return write_converted_package(
        result,
        out,
        overwrite=overwrite,
        embed_converter_profile=converter if embed_capabilities else None,
    )


def list_converter_capabilities() -> list[dict[str, Any]]:
    """Return capability profiles for every registered converter."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    profiles = []
    for converter_id in available_converters():
        converter = get_converter(converter_id)
        profile = converter.capability_profile()
        profiles.append(profile.to_dict(generated_at_utc=now, format_version=FORMAT_VERSION))
    return profiles


def readiness_report_payload(package_path: Path) -> dict[str, Any]:
    return build_readiness_report(package_path)


def readiness_report_text(package_path: Path) -> str:
    return render_readiness_report(build_readiness_report(package_path))


def _infer_converter_id(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix in {".fcstd"}:
        return "freecad_reference"
    raise ValueError(
        f"could not infer converter from source file extension {suffix!r}; "
        f"pass --converter explicitly. Available: {available_converters()}"
    )


__all__ = [
    "CONVERTER_CLAIM_POLICY",
    "convert_source",
    "list_converter_capabilities",
    "readiness_report_payload",
    "readiness_report_text",
]
