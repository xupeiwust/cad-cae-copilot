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

# Sampling (Issue #38) — candidate parameter generation
from .optimization_sampler import sample_candidates, sample_candidates_package

# Batch execution (Issue #39) + batch evaluation (Issue #40)
from .design_study_batch import (
    discover_candidate_ids,
    discover_executed_candidate_ids,
    run_design_study_batch,
    run_design_study_evaluation_batch,
)

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
    "sample_candidates",
    "sample_candidates_package",
    "discover_candidate_ids",
    "discover_executed_candidate_ids",
    "run_design_study_batch",
    "run_design_study_evaluation_batch",
]
