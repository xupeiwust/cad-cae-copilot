"""Base types for CAD/CAE-to-.aieng converters (Phase 20).

The converter contract is defined in `docs/cad_cae_conversion_contract.md`.

A Converter:

1. Reads a CAD/CAE source artifact.
2. Returns a ConversionResult describing what `.aieng` resources to emit and
   what is unsupported, missing, or uncertain. It does NOT write the package
   itself; the conversion writer is responsible for that.
3. Declares a static capability profile (the levels it can support in general)
   and an achieved set of levels for each individual run.

Crucially, the converter must not:

- run a mesher, solver, optimizer, or simulation;
- execute CAD edits or regenerate geometry;
- propose engineering decisions;
- silently fabricate missing engineering facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


CAPABILITY_LEVEL_NAMES: dict[int, str] = {
    0: "source_metadata",
    1: "geometry_topology",
    2: "object_registry",
    3: "feature_aware",
    4: "editability_metadata",
    5: "roundtrip_writeback_metadata",
}


CONVERTER_CLAIM_POLICY: dict[str, bool] = {
    "best_effort_conversion": True,
    "missingness_explicit": True,
    "do_not_infer_missing_information": True,
    "unsupported_is_not_false": True,
    "external_tools_execute": True,
    "aieng_core_executes_external_tools": False,
    "aieng_core_executes_solvers_meshers_or_optimizers": False,
    "aieng_core_performs_cad_edits": False,
}


class ConverterError(Exception):
    """Raised when a converter cannot read or interpret its source."""


@dataclass(frozen=True)
class SupportedLevel:
    level: int
    name: str
    supported: bool = True
    conditional_requirements: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_profile_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "level": self.level,
            "name": self.name,
            "supported": self.supported,
        }
        if self.conditional_requirements:
            entry["conditional_requirements"] = list(self.conditional_requirements)
        if self.notes:
            entry["notes"] = list(self.notes)
        return entry

    def to_manifest_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"level": self.level, "name": self.name}
        if self.notes:
            entry["notes"] = list(self.notes)
        return entry


@dataclass(frozen=True)
class EmittedResource:
    path: str
    kind: str
    level: int | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"path": self.path, "kind": self.kind}
        if self.level is not None:
            entry["level"] = self.level
        if self.notes:
            entry["notes"] = list(self.notes)
        return entry


@dataclass(frozen=True)
class UnsupportedItem:
    category: str
    status: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "status": self.status,
            "description": self.description,
        }


@dataclass(frozen=True)
class CoverageCategory:
    """Adaptive per-category record of what a conversion run captured.

    This is the primary interface in the conversion manifest. Capability
    levels (L0–L5) are retained as optional documentation shorthand.
    """

    category: str
    status: str  # complete | partial | inferred | missing | unsupported | unavailable_in_source | unknown
    resources_emitted: tuple[str, ...] = ()
    missing_items: tuple[str, ...] = ()
    inferred_items: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"category": self.category, "status": self.status}
        if self.resources_emitted:
            entry["resources_emitted"] = list(self.resources_emitted)
        if self.missing_items:
            entry["missing_items"] = list(self.missing_items)
        if self.inferred_items:
            entry["inferred_items"] = list(self.inferred_items)
        if self.notes:
            entry["notes"] = self.notes
        return entry


@dataclass(frozen=True)
class UncertaintyNote:
    scope: str
    description: str
    affected_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"scope": self.scope, "description": self.description}
        if self.affected_ids:
            entry["affected_ids"] = list(self.affected_ids)
        return entry


@dataclass(frozen=True)
class ConverterCapabilityProfile:
    """Static, source-agnostic declaration of what a converter can do."""

    converter_id: str
    source_system: str
    supported_levels: tuple[SupportedLevel, ...]
    display_name: str | None = None
    converter_version: str | None = None
    source_file_extensions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self, *, generated_at_utc: str, format_version: str) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "format_version": format_version,
            "converter_id": self.converter_id,
            "source_system": self.source_system,
            "supported_levels": [level.to_profile_dict() for level in self.supported_levels],
            "claim_policy": dict(CONVERTER_CLAIM_POLICY),
            "generated_at_utc": generated_at_utc,
        }
        if self.display_name:
            entry["display_name"] = self.display_name
        if self.converter_version:
            entry["converter_version"] = self.converter_version
        if self.source_file_extensions:
            entry["source_file_extensions"] = list(self.source_file_extensions)
        if self.notes:
            entry["notes"] = list(self.notes)
        return entry


@dataclass
class ConversionResult:
    """Describes the structured outcome of a single converter run.

    The conversion writer takes this and emits the package: it writes
    `manifest.json`, all package files listed in `package_files`, and the
    derived `provenance/conversion_manifest.json` + optional
    `provenance/converter_capabilities.json`.
    """

    model_id: str
    converter_id: str
    source_system: str
    converter_version: str | None
    display_name: str | None
    runtime_mode: str  # "offline" | "runtime" | "unknown"
    source_filename: str
    source_byte_size: int
    source_content_sha256: str | None
    source_document_metadata: dict[str, Any]
    declared_levels: tuple[SupportedLevel, ...]
    achieved_levels: tuple[SupportedLevel, ...]
    emitted_resources: list[EmittedResource]
    unsupported: list[UnsupportedItem]
    uncertainty: list[UncertaintyNote]
    coverage_categories: list[CoverageCategory] = field(default_factory=list)
    package_files: dict[str, bytes] = field(default_factory=dict)
    """Map of in-package path -> raw bytes. The writer copies these verbatim."""

    notes: tuple[str, ...] = ()

    def declared_level_numbers(self) -> tuple[int, ...]:
        return tuple(level.level for level in self.declared_levels)

    def achieved_level_numbers(self) -> tuple[int, ...]:
        return tuple(level.level for level in self.achieved_levels)


@runtime_checkable
class Converter(Protocol):
    """Protocol all CAD/CAE-to-.aieng converters must satisfy."""

    converter_id: str
    source_system: str

    def capability_profile(self) -> ConverterCapabilityProfile:
        """Return the static capability profile for this converter."""

    def convert(
        self,
        source_path: Path,
        *,
        model_id: str,
        runtime_mode: str = "auto",
        options: Mapping[str, Any] | None = None,
    ) -> ConversionResult:
        """Read the source artifact and produce a ConversionResult.

        ``runtime_mode`` may be ``"auto"``, ``"offline"``, or ``"runtime"``.
        Converters that have no runtime path should treat anything other than
        ``"offline"`` as ``"auto"`` (best effort: prefer offline).
        """
