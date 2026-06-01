"""Engineering domain schemas for the CAE boundary.

This module is intentionally decoupled from workflow-private types.
All models use ``extra="forbid"`` for strict validation, except where
noted for forward-compatibility.

Design note: There is NO ``part_family`` field. Agents operate on explicit
geometry references (face names, edge names) discovered through inspection tools.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Material & constraints
# ---------------------------------------------------------------------------

class MaterialSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    elastic_modulus_mpa: float
    poisson_ratio: float
    density_kg_m3: float
    yield_strength_mpa: float


class EnvelopeConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_width_mm: float
    max_height_mm: float
    max_depth_mm: float

    @field_validator("max_width_mm", "max_height_mm", "max_depth_mm")
    @classmethod
    def positive_dimensions(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Envelope dimensions must be positive.")
        return value


class MountingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixed_feature: Literal["mounting_holes", "mounting_face"]
    location: str
    hole_count: int
    hole_diameter_mm: float
    hole_spacing_mm: float | None = None


class LoadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    target_feature: Literal["load_hole", "load_face"]
    force_magnitude_n: float
    force_direction: Literal["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
    load_hole_diameter_mm: float | None = None

    @field_validator("force_magnitude_n")
    @classmethod
    def positive_force(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Force magnitude must be positive.")
        return value


class AcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_von_mises_stress_mpa: float
    max_displacement_mm: float

    @field_validator("max_von_mises_stress_mpa", "max_displacement_mm")
    @classmethod
    def positive_limits(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Acceptance limits must be positive.")
        return value


# ---------------------------------------------------------------------------
# Task & CAD spec (legacy high-level wrapper, optional)
# ---------------------------------------------------------------------------

class TaskSpec(BaseModel):
    """High-level task description. Kept for backward-compat workflows."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    source_document: str
    units: Literal["mm_N_MPa"] = "mm_N_MPa"
    description: str
    material: MaterialSpec
    envelope: Any | None = None  # relaxed
    thickness_mm: float
    mounting: MountingSpec
    load_case: LoadSpec
    acceptance_criteria: AcceptanceCriteria
    extracted_at: str = Field(default_factory=utc_now_iso)

    @field_validator("thickness_mm")
    @classmethod
    def positive_thickness(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Thickness must be positive.")
        return value


class BracketParameters(BaseModel):
    """Known parameter set for L-bracket-like parts."""

    model_config = ConfigDict(extra="forbid")

    width_mm: float
    vertical_leg_mm: float
    horizontal_leg_mm: float
    thickness_mm: float
    mounting_hole_count: int
    mounting_hole_diameter_mm: float
    mounting_hole_spacing_mm: float | None = None
    load_hole_diameter_mm: float | None = None
    inner_fillet_radius_mm: float


class FlatPlateParameters(BaseModel):
    """Known parameter set for flat-plate-like parts."""

    model_config = ConfigDict(extra="forbid")

    width_mm: float
    height_mm: float
    thickness_mm: float
    mounting_hole_count: int
    mounting_hole_diameter_mm: float
    mounting_hole_spacing_mm: float | None = None
    load_hole_diameter_mm: float | None = None
    edge_margin_mm: float


class CadSpec(BaseModel):
    """CAD specification. No part_family — agents use explicit geometry refs."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    document_name: str
    build_strategy: str
    parameters: dict[str, Any]
    requested_outputs: list[str] = [
        "task_spec.json",
        "cad_spec.json",
        "model_document",
        "step_export",
        "mass_properties",
    ]

    def as_bracket(self) -> BracketParameters:
        return BracketParameters.model_validate(self.parameters)

    def as_flat_plate(self) -> FlatPlateParameters:
        return FlatPlateParameters.model_validate(self.parameters)


# ---------------------------------------------------------------------------
# Analysis & results
# ---------------------------------------------------------------------------

class BoundaryCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    constraint_type: Literal["fixed"]


class LoadCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    load_type: Literal["force"]
    magnitude_n: float
    direction: Literal["+X", "-X", "+Y", "-Y", "+Z", "-Z"]


class MeshSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_size_mm: float
    element_type: str
    refinement_regions: list[str] = []


class AnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    analysis_type: Literal["static_structural"] = "static_structural"
    solver_mode: Literal["surrogate_static", "calculix", "freecad_fem"]
    material: MaterialSpec
    boundary_conditions: list[BoundaryCondition]
    loads: list[LoadCondition]
    mesh: MeshSpec
    assumptions: list[str]


class MassProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volume_mm3: float
    mass_kg: float
    center_of_gravity_mm: list[float]


class ResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    success: bool
    solver_mode: str
    generated_with_real_solver: bool
    producer_kind: Literal["surrogate", "freecad_fem", "calculix"] | None = None
    solver_executed: bool = False
    mesh_generated: bool = False
    engineering_validation: bool = False
    claims_advanced: bool = False
    max_von_mises_stress_mpa: float
    max_displacement_mm: float
    factor_of_safety: float
    meets_stress_limit: bool
    meets_displacement_limit: bool
    notes: list[str]


# ---------------------------------------------------------------------------
# Thermal analysis schemas
# ---------------------------------------------------------------------------

class HeatSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    heat_flux_w_m2: float | None = None
    total_heat_w: float | None = None


class ThermalBC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    bc_type: Literal["fixed_temperature", "heat_flux", "convection"]
    temperature_c: float | None = None
    heat_flux_w_m2: float | None = None
    film_coefficient_w_m2k: float | None = None
    ambient_temperature_c: float | None = None


class ThermalAnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    analysis_type: Literal["thermal_steady_state"] = "thermal_steady_state"
    solver_mode: Literal["surrogate_thermal", "calculix_thermal", "freecad_fem"]
    material: MaterialSpec
    thermal_conductivity_w_mk: float = 50.0
    heat_sources: list[HeatSource] = []
    thermal_boundary_conditions: list[ThermalBC]
    mesh: MeshSpec
    assumptions: list[str]


class ThermalResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    success: bool
    solver_mode: str
    generated_with_real_solver: bool
    producer_kind: Literal["surrogate", "freecad_fem", "calculix"] | None = None
    solver_executed: bool = False
    mesh_generated: bool = False
    engineering_validation: bool = False
    claims_advanced: bool = False
    max_temperature_c: float
    min_temperature_c: float
    max_heat_flux_w_m2: float
    temperature_limit_c: float | None = None
    meets_temperature_limit: bool
    notes: list[str]


# ---------------------------------------------------------------------------
# Modal analysis schemas
# ---------------------------------------------------------------------------

class ModalAnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    analysis_type: Literal["modal"] = "modal"
    solver_mode: Literal["surrogate_modal", "calculix_modal", "freecad_fem"]
    material: MaterialSpec
    boundary_conditions: list[BoundaryCondition]
    mesh: MeshSpec
    num_modes: int = 10
    freq_range_hz: list[float] | None = None
    mass_scaling: float = 1.0
    assumptions: list[str]


class ModalResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    success: bool
    solver_mode: str
    generated_with_real_solver: bool
    producer_kind: Literal["surrogate", "freecad_fem", "calculix"] | None = None
    solver_executed: bool = False
    mesh_generated: bool = False
    engineering_validation: bool = False
    claims_advanced: bool = False
    natural_frequencies_hz: list[float]
    mode_shapes_available: bool
    notes: list[str]


# ---------------------------------------------------------------------------
# Buckling analysis schemas
# ---------------------------------------------------------------------------

class BucklingAnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    analysis_type: Literal["buckling"] = "buckling"
    solver_mode: Literal["surrogate_buckling", "calculix_buckling", "freecad_fem"]
    material: MaterialSpec
    boundary_conditions: list[BoundaryCondition]
    loads: list[LoadCondition]
    mesh: MeshSpec
    num_buckling_modes: int = 5
    assumptions: list[str]


class BucklingResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    success: bool
    solver_mode: str
    generated_with_real_solver: bool
    producer_kind: Literal["surrogate", "freecad_fem", "calculix"] | None = None
    solver_executed: bool = False
    mesh_generated: bool = False
    engineering_validation: bool = False
    claims_advanced: bool = False
    critical_load_factor: float
    all_load_factors: list[float]
    is_stable: bool
    mode_shapes_available: bool
    notes: list[str]


# ---------------------------------------------------------------------------
# Geometry inspection (new)
# ---------------------------------------------------------------------------

class FaceDescriptor(BaseModel):
    """Descriptor for a single face, returned by inspect_geometry."""

    model_config = ConfigDict(extra="forbid")

    face: str
    surface_type: str
    area: float
    center: list[float]
    normal: list[float] | None = None
    bbox: dict[str, float]


class GeometryInspection(BaseModel):
    """Result of inspecting a solid for FEM setup."""

    model_config = ConfigDict(extra="forbid")

    document_path: str
    object_name: str
    global_bbox: dict[str, float]
    faces: list[FaceDescriptor]
    suggested_fixed: list[str]
    suggested_load: list[str]
    notes: list[str]
