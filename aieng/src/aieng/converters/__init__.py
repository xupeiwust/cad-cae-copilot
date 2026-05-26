"""CAD/CAE-to-.aieng converter framework (Phase 20).

This package contains the general converter contract and reference
implementations. Converters are read-only with respect to engineering
decisions: they convert source CAD/CAE artifacts into structured `.aieng`
resources and explicitly record what is missing or uncertain. They do not
run solvers, meshers, optimizers, or CAD edits.

See `docs/cad_cae_conversion_contract.md` for the full contract.
"""
from __future__ import annotations

from .base import (
    CAPABILITY_LEVEL_NAMES,
    CONVERTER_CLAIM_POLICY,
    Converter,
    ConverterCapabilityProfile,
    ConverterError,
    ConversionResult,
    CoverageCategory,
    EmittedResource,
    SupportedLevel,
    UncertaintyNote,
    UnsupportedItem,
)
from .registry import available_converters, get_converter, register_converter

__all__ = [
    "CAPABILITY_LEVEL_NAMES",
    "CONVERTER_CLAIM_POLICY",
    "Converter",
    "ConverterCapabilityProfile",
    "ConverterError",
    "ConversionResult",
    "CoverageCategory",
    "EmittedResource",
    "SupportedLevel",
    "UncertaintyNote",
    "UnsupportedItem",
    "available_converters",
    "get_converter",
    "register_converter",
]
